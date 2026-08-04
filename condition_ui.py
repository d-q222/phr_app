from __future__ import annotations

from collections.abc import Collection, Mapping, MutableMapping, Sequence
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import condition_charts
import db
import services
from condition_config import get_condition_record_mapping
from condition_services import get_primary_series, get_records_for_condition
from display_format import format_display_date, format_display_datetime

PROFILE_STATE_KEY = "condition_profile_scope"
SELECTED_CONDITION_KEY = "selected_condition"
# Per-condition widget keys live under this prefix so they can be cleared wholesale when the profile
# changes. A key that encoded only the condition name would let two profiles sharing a condition
# inherit each other's selection, which AGENTS.md section 4 counts as a leak surface even when what
# leaks is only a choice of series.
SERIES_KEY_PREFIX = "tracked_condition_series"
RANGE_KEY_PREFIX = "tracked_condition_range"
# Flags that mean the source marked the result, as opposed to recording it without comment.
SOURCE_FLAGGED = frozenset({"High", "Low", "Abnormal", "Critical"})

_TABLE_LABELS = {
    "lab_results": "Lab results",
    "medications": "Medications",
    "wearable_records": "Wearable records",
    "health_entries": "Health entries",
}
_RECORD_DISPLAY_FIELDS = {
    "lab_results": (
        ("Date", "lab_date"),
        ("Record", "test_name"),
        ("Value", "result_value"),
        ("Unit", "unit"),
        ("Flag", "flag"),
        ("Notes", "notes"),
    ),
    "medications": (
        ("Date", "start_date"),
        ("Record", "name"),
        ("Dose", "dose"),
        ("Frequency", "frequency"),
        ("Status", "status"),
        ("Reason", "reason"),
    ),
    "wearable_records": (
        ("Date", "timestamp"),
        ("Record", "metric_type"),
        ("Value", "value"),
        ("Unit", "unit"),
        ("Source", "source"),
    ),
    "health_entries": (
        ("Date", "entry_date"),
        ("Record", "title"),
        ("Severity", "severity"),
        ("Note", "note"),
    ),
}
_DATE_COLUMNS = {"lab_date", "start_date", "entry_date", "noted_date"}
_DATETIME_COLUMNS = {"timestamp"}


def profile_scope(person: dict | None, db_path: Path | str, locked: bool) -> tuple:
    """Identity of the currently-selected profile, used to detect stale condition selections.

    Four components, each guarding a distinct way the person on screen can change:

    - the resolved database path, which catches a real <-> demo switch;
    - the profile id, which catches an ordinary profile switch;
    - the profile's `created_at`, which catches a *different person arriving at the same id* -- a
      clear-and-restore can replace profile 1 with someone else entirely, and path and id alone
      cannot see that;
    - lock state, because locking is an authorization change at an otherwise identical scope.

    Computed from the profile row alone; it deliberately issues no query, so it is safe to build for
    a locked or unselected profile, where reading conditions would itself be a leak.
    """
    resolved = str(Path(db_path).resolve())
    if person is None:
        return (resolved, None, None, locked)
    return (resolved, int(person["id"]), str(person.get("created_at") or ""), locked)


def sync_profile_scope(state: MutableMapping[str, object], scope: tuple) -> None:
    """Drop condition selection state whenever the profile scope changes.

    Call this where the profile is *selected*, not from a page: a page-local call runs only when that
    page renders, which would leave one profile's selection parked in session state while a different
    profile is active.
    """
    if state.get(PROFILE_STATE_KEY) != scope:
        state[PROFILE_STATE_KEY] = scope
        state.pop(SELECTED_CONDITION_KEY, None)
        # Prefix sweep rather than named pops: the detail page creates one widget key per condition,
        # so the set of keys to clear is not knowable in advance.
        for key in [key for key in list(state) if str(key).startswith((SERIES_KEY_PREFIX, RANGE_KEY_PREFIX))]:
            state.pop(key, None)


def sync_valid_conditions(state: MutableMapping[str, object], valid_names: Collection[str]) -> None:
    """Drop a stored selection that is not one of this profile's current conditions.

    Complements `sync_profile_scope`, which handles the profile changing underneath the selection;
    this handles the selection's condition being deleted while the profile stays the same.
    """
    if state.get(SELECTED_CONDITION_KEY) not in valid_names:
        state.pop(SELECTED_CONDITION_KEY, None)


def _condition_names(rows: Sequence[dict]) -> list[str]:
    names = []
    for row in rows:
        value = row.get("condition_name")
        if isinstance(value, str) and value.strip() and value not in names:
            names.append(value)
    return names


def _table_label(table: str) -> str:
    return _TABLE_LABELS.get(table, table.replace("_", " ").title())


def _display_value(column: str, value: object) -> object:
    """Format dates the way every other page in the app does; leave other values untouched."""
    if value in (None, ""):
        return value
    if column in _DATE_COLUMNS:
        return format_display_date(value)
    if column in _DATETIME_COLUMNS:
        return format_display_datetime(value)
    return value


def _record_rows(rows: Sequence[dict], table: str) -> list[dict[str, object]]:
    fields = _RECORD_DISPLAY_FIELDS.get(table, ())
    display_rows = []
    for row in rows:
        display = {label: _display_value(column, row.get(column)) for label, column in fields}
        if table == "lab_results" and display.get("Value") in (None, ""):
            display["Value"] = row.get("numeric_value")
        if "Date" in display and display["Date"] in (None, ""):
            display["Date"] = "Date unavailable"
        display_rows.append(display)
    return display_rows


def _render_preview_table(table: str, rows: Sequence[dict]) -> None:
    st.caption(f"{_table_label(table)}: {len(rows)} record(s)")
    if rows:
        st.dataframe(pd.DataFrame(_record_rows(rows[:3], table)), width="stretch", hide_index=True)


def _render_record_table(table: str, rows: Sequence[dict]) -> None:
    st.subheader(_table_label(table))
    st.caption(f"{len(rows)} record(s) of a type commonly tracked for this condition.")
    if rows:
        st.dataframe(pd.DataFrame(_record_rows(rows, table)), width="stretch", hide_index=True)
    else:
        st.info("No records of this type were found for this profile.")


def render_condition_preview(
    person_id: int,
    condition_name: str,
    db_path: Path | str | None = None,
) -> None:
    """Render counts and a few profile-scoped records commonly tracked for a condition."""

    db_path = db.DB_PATH if db_path is None else db_path
    mapping = get_condition_record_mapping(condition_name)
    if not mapping:
        st.info("No records are mapped to this condition yet.")
        return
    try:
        records_by_table = get_records_for_condition(person_id, condition_name, db_path=db_path)
    except Exception:
        st.error("Condition records could not be loaded. Please try again.")
        return

    st.caption("Record types commonly tracked for this condition.")
    for table in mapping:
        _render_preview_table(table, records_by_table.get(table, []))


# --- the Tracked Conditions detail view -----------------------------------------------------------
#
# Rendering only. Every frame and every chart specification comes from `condition_charts`, which
# imports no Streamlit, so the charts stay assertable without driving a browser.


def _most_recent_record_date(records_by_table: Mapping[str, Sequence[dict]]) -> pd.Timestamp | None:
    """The latest date across every linked record, not only the dated numeric ones.

    Derived from `trends` before, which covers only lab and wearable rows carrying a finite number.
    A condition linked solely to a medication -- or to a qualitative lab stored as text with a NULL
    `numeric_value` -- therefore reported "Most recent record: None" on the same metric row that
    reported those records existing. Counts and this date now read the same set.
    """

    stamps = []
    for table, rows in records_by_table.items():
        date_column = condition_charts.DATE_FIELDS.get(table)
        if date_column is None:
            continue
        for row in rows:
            parsed = pd.to_datetime(row.get(date_column), errors="coerce")
            if pd.isna(parsed):
                continue
            if parsed.tzinfo is not None:
                # Wall clock, not UTC -- same reasoning as `condition_charts._coerce_point`: a UTC
                # conversion can move a reading onto a different calendar day than the record shows.
                parsed = parsed.tz_localize(None)
            stamps.append(parsed)
    return max(stamps) if stamps else None


def _render_at_a_glance(records_by_table: Mapping[str, Sequence[dict]], trends: pd.DataFrame) -> None:
    """Four counts. No deltas are coloured, because a rise is not inherently good or bad."""

    labs = records_by_table.get("lab_results", [])
    flagged = sum(1 for row in labs if str(row.get("flag") or "") in SOURCE_FLAGGED)
    latest = _most_recent_record_date(records_by_table)
    columns = st.columns(4)
    columns[0].metric("Linked records", sum(len(rows) for rows in records_by_table.values()))
    columns[1].metric("Source-flagged results", flagged)
    columns[2].metric("Medications recorded", len(records_by_table.get("medications", [])))
    columns[3].metric(
        "Most recent record",
        format_display_date(latest.date().isoformat()) if latest is not None and not pd.isna(latest) else "None",
    )


def _render_measurement_trends(
    condition_name: str,
    records_by_table: Mapping[str, Sequence[dict]],
    trends: pd.DataFrame,
) -> None:
    st.subheader("Measurement trends")
    if trends.empty:
        st.info("No dated numeric records are available for this condition.")
        return
    names = sorted(str(name) for name in trends["record"].dropna().unique())
    selected = st.multiselect(
        "Series", names, default=names[:1], key=f"{SERIES_KEY_PREFIX}:{condition_name}"
    )
    if not selected:
        st.caption("Select at least one series to chart.")
        return
    spans = condition_charts.medication_spans(records_by_table.get("medications", []), date.today().isoformat())
    chart = condition_charts.build_trend_with_medications(trends[trends["record"].isin(selected)], spans)
    st.altair_chart(chart, width="stretch")
    st.caption(
        "Point colour and shape show the flag recorded by the source, not an assessment by this app. "
        "Records with no flag are drawn hollow."
    )
    if not spans.empty:
        st.caption(
            "Timing only — records show when a medication was recorded, not whether it affected any result."
        )


def _render_first_latest(trends: pd.DataFrame) -> None:
    st.subheader("First and most recent")
    summary = condition_charts.first_latest(trends)
    if summary.empty:
        st.info("No dated numeric records are available for this condition.")
        return
    display = pd.DataFrame(
        {
            "Record": summary["record"],
            "Unit": summary["unit"],
            "First": summary["first_value"],
            "First flag": summary["first_flag"],
            "Latest": summary["latest_value"],
            "Latest flag": summary["latest_flag"],
            "Change": summary["change"],
            "Results": summary["results"],
        }
    )
    st.dataframe(display, width="stretch", hide_index=True)
    st.caption("Change is the difference between the first and most recent stored values.")


def _render_flag_history(records_by_table: Mapping[str, Sequence[dict]]) -> None:
    st.subheader("Source-flag history")
    history = condition_charts.flag_history(records_by_table.get("lab_results", []))
    if history.empty:
        # Some conditions have no lab that is commonly tracked for them at all. Saying so is better
        # than leaving a gap, and far better than mapping a test just to fill the panel.
        st.info(
            "No lab results are linked to this condition. Not every condition has a lab test that "
            "is commonly tracked for it."
        )
        return
    st.altair_chart(condition_charts.build_flag_strip(history), width="stretch")
    st.caption("One mark per result, showing the flag the source recorded at the time.")


def _render_cadence(records_by_table: Mapping[str, Sequence[dict]]) -> None:
    st.subheader("Monitoring cadence")
    counts = condition_charts.monthly_counts(records_by_table)
    if counts.empty:
        st.info("No dated records are linked to this condition.")
        return
    st.altair_chart(condition_charts.build_density_chart(counts), width="stretch")
    st.caption("How many linked records exist each month. It does not evaluate whether that cadence was right.")


def _render_variability(condition_name: str, trends: pd.DataFrame) -> None:
    st.subheader("Variability")
    dense = condition_charts.series_with_a_visible_range(trends)
    if not dense:
        st.info("No series has two or more readings in any single period, so there is no spread to show.")
        return
    # Already ordered densest first, so the section opens on the series with the most to show rather
    # than whichever name happens to sort first.
    selected = st.selectbox("Series", dense, key=f"{RANGE_KEY_PREFIX}:{condition_name}")
    period = condition_charts.choose_range_period(trends, selected)
    if period is None:
        st.info("No ranges are available for this series.")
        return
    code, label = period
    ranges = condition_charts.value_ranges(trends, selected, period=code)
    st.altair_chart(condition_charts.build_range_band_chart(ranges), width="stretch")
    # The bucket widens for sparse series, so the caption has to say which one is on screen -- a
    # band labelled "each month" that is actually per year would misstate the data.
    st.caption(f"Shaded band is each {label}'s lowest to highest reading; the line is that {label}'s mean.")


def _render_severity(records_by_table: Mapping[str, Sequence[dict]]) -> None:
    st.subheader("Recorded symptom severity")
    entries = condition_charts.severity_frame(records_by_table.get("health_entries", []))
    if entries.empty:
        st.info("No linked health entries carry a severity rating.")
        return
    st.altair_chart(condition_charts.build_severity_chart(entries), width="stretch")
    st.caption("Severity as entered by the person on the 1-10 scale the entry form uses.")


def _render_all_conditions(person_id: int, names: Sequence[str], db_path: Path | str) -> None:
    st.subheader("All tracked conditions")
    try:
        series = get_primary_series(person_id, names, db_path=db_path)
    except Exception:
        st.error("Condition records could not be loaded. Please try again.")
        return
    frame = condition_charts.sparkline_frame(series)
    if frame.empty:
        st.info("No numeric records are available for the conditions on this profile.")
        return
    st.altair_chart(condition_charts.build_sparklines(frame), width="stretch")
    st.caption(
        "One commonly-followed measurement per condition, each on its own scale. "
        "A condition appears here only when its records include that measurement."
    )


def _render_linked_records(mapping: Mapping[str, tuple], records_by_table: Mapping[str, Sequence[dict]]) -> None:
    st.subheader("Linked records")
    st.caption(
        "Record types commonly tracked for this condition, grouped by type. "
        "Listing a record here does not mean it was recorded for this condition."
    )
    tables = list(mapping)
    for tab, table in zip(st.tabs([_table_label(table) for table in tables]), tables, strict=True):
        with tab:
            _render_record_table(table, records_by_table.get(table, []))


def _render_condition_sections(
    person_id: int,
    condition_name: str,
    names: Sequence[str],
    mapping: Mapping[str, tuple],
    records_by_table: Mapping[str, Sequence[dict]],
    db_path: Path | str,
) -> None:
    """Render every section for one selected condition, in reading order."""

    trends = condition_charts.trend_frame(records_by_table)
    _render_at_a_glance(records_by_table, trends)
    _render_measurement_trends(condition_name, records_by_table, trends)
    _render_first_latest(trends)
    _render_flag_history(records_by_table)
    _render_cadence(records_by_table)
    _render_variability(condition_name, trends)
    _render_severity(records_by_table)
    _render_all_conditions(person_id, names, db_path)
    _render_linked_records(mapping, records_by_table)


def render_tracked_conditions_detail(
    person: dict | None,
    rows: Sequence[dict] | None = None,
    db_path: Path | str | None = None,
) -> None:
    """Render the detailed, chart-driven view of one tracked condition.

    Inputs the selected profile, optionally its already-fetched condition rows, and a database path.
    Renders nothing but Streamlit; all frames and chart specifications come from `condition_charts`
    and all retrieval from `condition_services`.

    `rows` is accepted so the caller that already listed the profile's conditions -- to decide
    whether the manage form should open -- does not make this function query for them again.
    """

    db_path = db.DB_PATH if db_path is None else db_path
    if not person:
        st.info("Select a profile to view condition records.")
        return

    person_id = int(person["id"])
    try:
        if rows is None:
            rows = services.tracked_conditions(person_id, db_path=db_path)
        names = _condition_names(rows)
    except Exception:
        st.error("Conditions could not be loaded. Please try again.")
        return
    # Before the empty-profile return, so a stale selection is dropped either way.
    sync_valid_conditions(st.session_state, names)
    if not names:
        st.info("No conditions are being tracked for this profile. Add one below to see its records.")
        return

    # `default` applies on first paint only, so the page opens on content while an explicit
    # deselection is still respected.
    selected = st.pills("Condition", names, default=names[0], key=SELECTED_CONDITION_KEY)
    if not isinstance(selected, str) or selected not in names:
        st.caption("Select a condition to view its records.")
        return

    try:
        mapping = get_condition_record_mapping(selected)
        records_by_table = get_records_for_condition(person_id, selected, db_path=db_path)
    except Exception:
        st.error("Condition records could not be loaded. Please try again.")
        return
    if not mapping:
        st.info("No records are mapped to this condition yet.")
        return

    st.header(selected)
    _render_condition_sections(person_id, selected, names, mapping, records_by_table, db_path)
