from __future__ import annotations

from collections.abc import Collection, Mapping, MutableMapping, Sequence
from math import isfinite
from pathlib import Path

import pandas as pd
import streamlit as st

import db
import services
from condition_config import get_condition_record_mapping
from condition_services import get_records_for_condition

PROFILE_STATE_KEY = "condition_profile_scope"
SELECTED_CONDITION_KEY = "selected_condition"
TREND_STATE_KEY = "condition_trend_record"

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
        ("Source flag", "flag"),
        ("Details", "notes"),
    ),
    "medications": (
        ("Date", "start_date"),
        ("Record", "name"),
        ("Dose", "dose"),
        ("Frequency", "frequency"),
        ("Status", "status"),
        ("Details", "reason"),
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
        ("Source severity", "severity"),
        ("Details", "note"),
    ),
}
_NUMERIC_FIELDS = {
    "wearable_records": ("timestamp", "value", "metric_type"),
    "lab_results": ("lab_date", "numeric_value", "test_name"),
}
_EMPTY_TREND_COLUMNS = ["date", "value", "record"]


def sync_profile_state(
    state: MutableMapping[str, object],
    person_id: int,
    db_path: Path | str,
    valid_names: Collection[str],
) -> None:
    """Clear condition selection and trend state when profile, database, or valid names change."""

    scope = (str(Path(db_path).resolve()), person_id)
    if state.get(PROFILE_STATE_KEY) != scope:
        state[PROFILE_STATE_KEY] = scope
        state.pop(SELECTED_CONDITION_KEY, None)
        state.pop(TREND_STATE_KEY, None)
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


def _record_rows(rows: Sequence[dict], table: str) -> list[dict[str, object]]:
    fields = _RECORD_DISPLAY_FIELDS.get(table, ())
    display_rows = []
    for row in rows:
        display = {label: row.get(column) for label, column in fields}
        if table == "lab_results" and display.get("Value") in (None, ""):
            display["Value"] = row.get("numeric_value")
        if "Date" in display and display["Date"] in (None, ""):
            display["Date"] = "Date unavailable"
        display_rows.append(display)
    return display_rows


def _numeric_series(rows: Sequence[dict], table: str) -> pd.DataFrame:
    """Return dated, finite source numeric values for a supported record table."""

    fields = _NUMERIC_FIELDS.get(table)
    if fields is None:
        return pd.DataFrame(columns=_EMPTY_TREND_COLUMNS)

    date_column, value_column, name_column = fields
    values = []
    for row in rows:
        date_value = row.get(date_column)
        raw_value = row.get(value_column)
        if date_value in (None, "") or isinstance(raw_value, bool):
            continue
        try:
            value = float(raw_value)
            parsed_date = pd.to_datetime(date_value, errors="raise")
        except (TypeError, ValueError, OverflowError):
            continue
        if pd.isna(parsed_date) or not isfinite(value):
            continue
        values.append({"date": parsed_date, "value": value, "record": row.get(name_column)})
    return pd.DataFrame(values, columns=_EMPTY_TREND_COLUMNS)


def _render_preview_table(table: str, rows: Sequence[dict]) -> None:
    st.caption(f"{_table_label(table)}: {len(rows)} record(s)")
    if rows:
        st.dataframe(pd.DataFrame(_record_rows(rows[:3], table)), width="stretch", hide_index=True)


def _render_record_table(table: str, rows: Sequence[dict]) -> None:
    st.subheader(_table_label(table))
    st.caption(f"{len(rows)} record(s) matching this condition.")
    if rows:
        st.dataframe(pd.DataFrame(_record_rows(rows, table)), width="stretch", hide_index=True)
    else:
        st.info("No records matching this condition were found in this record type.")


def _render_trends(records_by_table: Mapping[str, Sequence[dict]]) -> None:
    frames = [_numeric_series(rows, table) for table, rows in records_by_table.items()]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        st.info("No dated numeric records are available for trends.")
        return

    trends = pd.concat(frames, ignore_index=True)
    names = sorted(str(name) for name in trends["record"].dropna().unique())
    if not names:
        st.info("No named numeric records are available for trends.")
        return
    selected = st.selectbox("Trend record", names, key=TREND_STATE_KEY)
    st.line_chart(trends[trends["record"] == selected].sort_values("date"), x="date", y="value")


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

    st.caption("Commonly tracked for this condition. Records matching this condition are shown below.")
    for table in mapping:
        _render_preview_table(table, records_by_table.get(table, []))


def render_condition_focus_page(
    person: dict | None,
    db_path: Path | str | None = None,
) -> None:
    """Render condition selection, grouped records, and an optional last-place trend view."""

    db_path = db.DB_PATH if db_path is None else db_path
    if not person:
        st.info("Select a profile to view condition records.")
        return

    person_id = int(person["id"])
    try:
        names = _condition_names(services.tracked_conditions(person_id, db_path=db_path))
    except Exception:
        st.error("Conditions could not be loaded. Please try again.")
        return
    # Sync before the empty-profile return: switching to a profile with no conditions must still
    # clear the previous profile's selection out of session state, not leave it parked there.
    sync_profile_state(st.session_state, person_id, db_path, names)
    if not names:
        st.info("No conditions are being tracked for this profile.")
        return

    # Default to the first condition so the page opens on content rather than an empty prompt.
    # `default` only applies on first paint, so an explicit deselection is still respected.
    selected = st.pills("Condition", names, default=names[0], key=SELECTED_CONDITION_KEY)
    if not isinstance(selected, str) or selected not in names:
        st.caption("Select a condition to view records.")
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
    st.caption("Commonly tracked for this condition. Records matching this condition are shown by record type.")
    tables = list(mapping)
    tabs = st.tabs([_table_label(table) for table in tables] + ["Numeric trends"])
    for tab, table in zip(tabs[:-1], tables, strict=True):
        with tab:
            _render_record_table(table, records_by_table.get(table, []))
    with tabs[-1]:
        _render_trends(records_by_table)
