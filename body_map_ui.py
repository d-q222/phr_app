from __future__ import annotations

from collections.abc import MutableMapping, Sequence
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import condition_charts
import db
from body_map_config import BODY_PART_IDS, BODY_PARTS, BODY_SYSTEMS
from body_map_services import NormalizedBodyRecord, get_records_for_body_part
from body_map_summary import BodyPartHealthSummary, summarize_body_part_health

SVG_PATH = Path(__file__).resolve().parent / "assets" / "body_map_front.svg"
COMPONENT_PATH = Path(__file__).resolve().parent / "components" / "body_map"
BODY_MAP_COMPONENT = components.declare_component("body_map_selector", path=COMPONENT_PATH)
PROFILE_STATE_KEY = "body_map_profile_scope"
SELECTED_STATE_KEY = "selected_body_part"
TREND_STATE_KEY = "body_map_trend_record"


def sync_profile_state(state: MutableMapping[str, object], person_id: int, db_path: Path | str) -> None:
    """Clear body-map selection whenever the selected profile changes."""

    scope = (str(Path(db_path).resolve()), person_id)
    if state.get(PROFILE_STATE_KEY) != scope:
        state[PROFILE_STATE_KEY] = scope
        state.pop(SELECTED_STATE_KEY, None)
        state.pop(TREND_STATE_KEY, None)
    if state.get(SELECTED_STATE_KEY) not in BODY_PARTS:
        state.pop(SELECTED_STATE_KEY, None)


def apply_component_selection(state: MutableMapping[str, object], component_key: str) -> None:
    """Copy one canonical component selection into the shared body-map filter state."""

    event = state.get(component_key)
    body_part = event.get("body_part") if isinstance(event, dict) else None
    if isinstance(body_part, str) and body_part in BODY_PARTS:
        state[SELECTED_STATE_KEY] = body_part


def render_svg(selected_body_part: str | None, svg_path: Path = SVG_PATH) -> str:
    """Return the replaceable SVG asset with only the selected canonical region highlighted."""

    svg = svg_path.read_text(encoding="utf-8")
    if selected_body_part in BODY_PARTS:
        marker = f'id="{selected_body_part}"'
        svg = svg.replace(marker, f'{marker} class="selected-organ"', 1)
    return svg


def group_records(records: Sequence[NormalizedBodyRecord]) -> dict[str, list[NormalizedBodyRecord]]:
    """Group normalized Part 2 records once, without changing their medical meaning."""

    grouped = {name: [] for name in ("Labs", "Vitals", "Medications", "Notes", "Imaging", "Wearables")}
    categories = {
        "lab": "Labs",
        "vital": "Vitals",
        "medication": "Medications",
        "health_entry": "Notes",
        "appointment": "Notes",
        "imaging": "Imaging",
        "wearable": "Wearables",
    }
    seen: set[tuple[str, int]] = set()
    for record in records:
        key = (record.source_table, record.record_id)
        category = categories.get(record.record_type)
        if category and key not in seen:
            grouped[category].append(record)
            seen.add(key)
    return grouped


def rows_by_source_table(records: Sequence[NormalizedBodyRecord]) -> dict[str, list[dict]]:
    """Group the original database rows behind normalized records by their source table.

    Feeds `condition_charts.trend_frame`, which is keyed by table name and allowlists only
    `lab_results` and `wearable_records` -- so medications, appointments and health entries are
    excluded here by construction rather than by a filter anyone has to remember.

    Unlike `group_records` above this needs no de-duplication: `get_records_for_body_part` yields at
    most one normalized record per source row, and grouping by table cannot merge two record types
    into one bucket the way the category mapping can.
    """

    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record.source_table, []).append(record.raw_record)
    return grouped


def _record_rows(records: Sequence[NormalizedBodyRecord]) -> list[dict[str, object]]:
    return [
        {
            "Date": record.date or "Date unavailable",
            "Record": record.display_name,
            "Value": record.value,
            "Unit": record.unit,
            "Source flag": record.status_flag,
            "Details": record.summary_text,
        }
        for record in records
    ]


def _render_records(records: Sequence[NormalizedBodyRecord], empty_label: str) -> None:
    if not records:
        st.info(f"No {empty_label.lower()} records found for this body area.")
        return
    st.dataframe(pd.DataFrame(_record_rows(records)), width="stretch", hide_index=True)


def _render_summary(summary: BodyPartHealthSummary, record_count: int) -> None:
    st.subheader(summary.status_label)
    st.write(summary.status_reason)
    columns = st.columns(4)
    columns[0].metric("Relevant records", record_count)
    columns[1].metric("Current flagged", len(summary.current_flagged_records))
    columns[2].metric("Historical flagged", len(summary.historical_flagged_records))
    columns[3].metric("Latest relevant date", summary.latest_relevant_date or "Not available")


@st.fragment
def render_body_map_page(person: dict | None, db_path: Path | str | None = None) -> None:
    """Render Part 4 for one selected, already-authorized profile."""
    db_path = db.DB_PATH if db_path is None else db_path

    if not person:
        st.info("Select a profile to view the body map.")
        return

    person_id = int(person["id"])
    sync_profile_state(st.session_state, person_id, db_path)
    selected = st.session_state.get(SELECTED_STATE_KEY)

    scope = st.session_state[PROFILE_STATE_KEY]
    component_key = f"body_map_selector:{scope[0]}:{scope[1]}"
    BODY_MAP_COMPONENT(
        svg=render_svg(selected),
        key=component_key,
        default=None,
        on_change=lambda: apply_component_selection(st.session_state, component_key),
    )
    options = [None, *BODY_PART_IDS]
    selected = st.selectbox(
        "Select a body part",
        options,
        index=options.index(selected) if selected in BODY_PARTS else 0,
        format_func=lambda item: "Choose a body part" if item is None else BODY_PARTS[item].display_name,
        key=SELECTED_STATE_KEY,
    )
    if selected is None:
        st.caption("Select an organ on the body model or use the selector to view records.")
        return

    part = BODY_PARTS[selected]
    systems = ", ".join(BODY_SYSTEMS[item].display_name for item in part.primary_systems)
    st.header(f"{part.display_name} / {systems}")
    try:
        records = get_records_for_body_part(person_id, selected, db_path=db_path)
        summary = summarize_body_part_health(records)
    except Exception:
        st.error("Body map records could not be loaded. Please try again.")
        return

    _render_summary(summary, len(records))
    if not records:
        st.info("No records found for this body area in the selected profile.")

    grouped = group_records(records)
    tabs = st.tabs(["Overview", "Labs", "Vitals", "Medications", "Notes", "Imaging", "Wearables", "Trends"])
    with tabs[0]:
        _render_records(records, "Overview")
    # strict=True: group_records() seeds exactly the six categories rendered as tabs[1:7].
    # If that list and the st.tabs() list above ever drift apart, fail loudly instead of
    # silently dropping a category's records.
    for tab, category in zip(tabs[1:7], grouped, strict=True):
        with tab:
            _render_records(grouped[category], category)
    with tabs[7]:
        _render_trends(records)


def _render_trends(records: Sequence[NormalizedBodyRecord]) -> None:
    """Chart the dated numeric records for one body area, then symptom severity separately."""

    grouped = rows_by_source_table(records)
    trends = condition_charts.trend_frame(grouped)
    if trends.empty:
        st.info("No dated numeric records are available for trends.")
    else:
        names = sorted(str(name) for name in trends["record"].dropna().unique())
        name = st.selectbox("Trend record", names, key=TREND_STATE_KEY)
        st.altair_chart(condition_charts.build_trend_chart(trends[trends["record"] == name]), width="stretch")
        st.caption(condition_charts.FLAG_CAPTION)

    # Labs with a written result but no number are named rather than silently missing from the chart.
    missing = sum(1 for row in grouped.get("lab_results", []) if row.get("numeric_value") is None)
    if missing:
        st.caption(condition_charts.missing_numeric_value_caption(missing))

    # Severity keeps its own chart rather than joining the trend above: a self-reported 1-10 scale
    # does not belong on an axis of clinical measurements.
    severity = condition_charts.severity_frame(grouped.get("health_entries", []))
    if not severity.empty:
        st.subheader("Symptom severity")
        st.altair_chart(condition_charts.build_severity_chart(severity), width="stretch")
