from __future__ import annotations

import json
import tempfile
import uuid
from collections.abc import Callable
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import ai_chat
import ai_config
import body_map_ui
import condition_ui
import db
import display_format
import fhir
import imports_exports
import insights
import security
import services
import validation
from models import (
    APPOINTMENT_STATUSES,
    BODY_SYSTEMS,
    CONDITION_SOURCES,
    LAB_FLAGS,
    MEDICATION_STATUSES,
    REMINDER_STATUSES,
    WEARABLE_METRIC_TYPES,
)

SAMPLE_DATA_PATH = Path(__file__).resolve().parent / "sample_test_data.json"
DEMO_MODE_KEY = "demo_mode_enabled"
DEMO_DB_PATH_KEY = "demo_db_path"


PAGES = [
    "Dashboard",
    "Body Map",
    "Profiles",
    "Health Timeline",
    "Medications",
    "Allergies",
    "Labs",
    "Appointments",
    "Reminders",
    "Wearables",
    "Tracked Conditions",
    "Provider Summary",
    "Emergency Snapshot",
    "Health Insights",
    "AI Chat",
    "Import/Export",
    "Settings",
]

NAV_SECTIONS = {
    "Overview": ["Dashboard", "Body Map", "Health Insights", "AI Chat"],
    "Records": [
        "Health Timeline",
        "Medications",
        "Allergies",
        "Labs",
        "Appointments",
        "Reminders",
        "Wearables",
        "Tracked Conditions",
    ],
    "Documents": ["Provider Summary", "Emergency Snapshot", "Import/Export"],
    "Admin": ["Profiles", "Settings"],
}

PAGE_EMOJIS = {
    "Dashboard": "📊",
    "Body Map": "🫀",
    "Profiles": "👤",
    "Health Timeline": "🗓️",
    "Medications": "💊",
    "Allergies": "⚠️",
    "Labs": "🧪",
    "Appointments": "📅",
    "Reminders": "🔔",
    "Wearables": "⌚",
    "Tracked Conditions": "🩺",
    "Provider Summary": "📝",
    "Emergency Snapshot": "🚑",
    "Health Insights": "💡",
    "AI Chat": "💬",
    "Import/Export": "🔄",
    "Settings": "⚙️",
}

ACTION_EMOJIS = {
    "Exit demo mode": "↩️",
    "Demo mode": "🧪",
    "Unlock profile": "🔓",
    "Lock profile": "🔒",
    "Remove password": "🗑️",
    "Save password": "💾",
    "Save API key": "🔑",
    "Test BigModel API key": "🧪",
    "Add profile": "➕",
    "Create profile": "✅",
    "Cancel": "✖️",
    "Save changes": "💾",
    "Delete profile": "🗑️",
    "Add record": "➕",
    "Mark complete": "✅",
    "Dismiss": "↩️",
    "Delete": "🗑️",
    "Download Markdown": "⬇️",
    "Download sample labs CSV": "⬇️",
    "Download sample wearables CSV": "⬇️",
    "Import labs": "⬆️",
    "Import wearables": "⬆️",
    "Import FHIR Bundle": "⬆️",
    "Export JSON backup": "📤",
    "Restore backup": "♻️",
    "Generate rule-based report": "📄",
    "Generate AI safety-checked insights": "✨",
}

ACTION_PREFIX_EMOJIS = {
    "Add ": "➕",
    "Export FHIR ": "📤",
}

PAGE_DESCRIPTIONS = {
    "Dashboard": "A quick operational view of medications, allergies, labs, reminders, appointments, and recent notes.",
    "Body Map": "Explore profile-specific records by body area without medical interpretation.",
    "Profiles": "Manage family member profiles and local profile access settings.",
    "Health Timeline": "Record symptoms, observations, body systems, and dated health notes.",
    "Medications": "Track current and past medications, dose details, reasons, and notes.",
    "Allergies": "Keep allergy, reaction, and severity information easy to scan.",
    "Labs": "Review lab results, flags, reference ranges, and simple trends.",
    "Appointments": "Track provider visits, status, location, and preparation notes.",
    "Reminders": "Manage follow-up items and routine health tasks.",
    "Wearables": "Import and review manually recorded wearable metrics.",
    "Tracked Conditions": "Chart the records commonly tracked for a condition you have noted, and record new conditions.",
    "Provider Summary": "Generate a provider-ready Markdown summary from selected records.",
    "Emergency Snapshot": "Create a concise emergency Markdown snapshot.",
    "Health Insights": "Generate rule-based reports or safety-checked AI insights from a compact data packet.",
    "AI Chat": "Ask selected-profile questions using a concise health context sent to Zhipu AI.",
    "Import/Export": "Import CSV records, exchange FHIR bundles, and manage local JSON backups.",
    "Settings": "Manage local profile protection and optional BigModel API settings.",
}

SINGULAR_TITLES = {
    "Allergies": "Allergy",
    "Medications": "Medication",
    "Labs": "Lab",
    "Health Timeline": "Timeline entry",
    "Appointments": "Appointment",
    "Reminders": "Reminder",
    "Wearables": "Wearable record",
    "Tracked Conditions": "Condition",
}

DISPLAY_COLUMN_LABELS = {
    "id": "ID",
    "person_id": "Profile ID",
    "name": "Name",
    "date_of_birth": "Date of Birth",
    "sex": "Sex",
    "relationship": "Relationship",
    "emergency_contact": "Emergency Contact",
    "notes": "Notes",
    "note": "Note",
    "profile_password_enabled": "Password Protected",
    "profile_password_hint": "Password Hint",
    "created_at": "Created",
    "updated_at": "Updated",
    "allergen": "Allergen",
    "reaction": "Reaction",
    "severity": "Severity",
    "dose": "Dose",
    "frequency": "Frequency",
    "start_date": "Start Date",
    "end_date": "End Date",
    "status": "Status",
    "reason": "Reason",
    "test_name": "Test",
    "result_value": "Result",
    "numeric_value": "Numeric Result",
    "unit": "Unit",
    "reference_low": "Reference Low",
    "reference_high": "Reference High",
    "flag": "Flag",
    "lab_date": "Lab Date",
    "entry_date": "Entry Date",
    "title": "Title",
    "body_system": "Body System",
    "body_part": "Body Part",
    "appointment_date": "Appointment Date",
    "provider": "Provider",
    "location": "Location",
    "reminder_type": "Reminder Type",
    "due_date": "Due Date",
    "metric_type": "Metric",
    "condition_name": "Condition",
    "noted_date": "Noted",
    "value": "Value",
    "timestamp": "Timestamp",
    "source": "Source",
    "latest": "Latest",
    "latest_timestamp": "Latest Timestamp",
    "average": "Average",
    "minimum": "Minimum",
    "maximum": "Maximum",
    "count": "Count",
}

HIDDEN_DISPLAY_COLUMNS = {"person_id", "profile_password_hash"}

DATE_DISPLAY_COLUMNS = {
    "date_of_birth",
    "start_date",
    "end_date",
    "lab_date",
    "entry_date",
    "appointment_date",
    "due_date",
    "noted_date",
}

DATETIME_DISPLAY_COLUMNS = {
    "created_at",
    "updated_at",
    "timestamp",
    "latest_timestamp",
}

APP_CSS = """
<style>
:root {
    --phr-bg: #f6f8f7;
    --phr-panel: #ffffff;
    --phr-border: #d9e1dd;
    --phr-text: #17211d;
    --phr-muted: #5f6f68;
    --phr-accent: #16705c;
    --phr-accent-soft: #e4f2ed;
    --phr-warn: #a86112;
    --phr-danger: #b42318;
}

.stApp {
    background: var(--phr-bg);
    color: var(--phr-text);
}

[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"] {
    background: var(--phr-bg);
    color: var(--phr-text);
}

[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
    background: #eef4f1;
    color: var(--phr-text);
}

.stMarkdown,
.stMarkdown p,
.stMarkdown li,
.stMarkdown span,
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] span,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p,
label,
p {
    color: var(--phr-text);
}

.block-container {
    padding-top: 1.75rem;
    padding-bottom: 3rem;
    max-width: 1180px;
}

h1, h2, h3 {
    letter-spacing: 0;
}

h1 {
    font-size: 2rem;
    line-height: 1.15;
}

h2 {
    font-size: 1.35rem;
}

h3 {
    font-size: 1.05rem;
}

.phr-topbar {
    border-bottom: 1px solid var(--phr-border);
    padding-bottom: 0.85rem;
    margin-bottom: 1rem;
}

.phr-topbar h1 {
    margin: 0 0 0.25rem 0;
}

.phr-kicker {
    color: var(--phr-accent);
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}

.phr-subtitle {
    color: var(--phr-muted);
    font-size: 0.98rem;
    max-width: 760px;
}

.phr-profile-strip {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
    align-items: center;
    background: var(--phr-panel);
    color: var(--phr-text);
    border: 1px solid var(--phr-border);
    border-radius: 8px;
    padding: 0.8rem 0.95rem;
    margin: 0.5rem 0 1.1rem 0;
}

.phr-profile-name {
    font-weight: 700;
}

.phr-pill {
    border: 1px solid var(--phr-border);
    background: #f9fbfa;
    border-radius: 999px;
    padding: 0.18rem 0.62rem;
    color: var(--phr-muted);
    font-size: 0.82rem;
}

.phr-dashboard-note {
    background: var(--phr-panel);
    border-left: 4px solid var(--phr-accent);
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin-bottom: 1rem;
    color: var(--phr-muted);
}

[data-testid="stMetric"] {
    background: var(--phr-panel);
    color: var(--phr-text);
    border: 1px solid var(--phr-border);
    border-radius: 8px;
    padding: 0.95rem 1rem;
}

[data-testid="stMetricLabel"] {
    color: var(--phr-muted);
}

[data-testid="stMetricValue"] {
    color: var(--phr-text);
    font-weight: 750;
}

.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] button {
    border-radius: 8px;
    border: 1px solid var(--phr-accent);
    color: #ffffff;
    background: var(--phr-accent);
    font-weight: 650;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] button:hover {
    border-color: #0d5948;
    background: #0d5948;
    color: #ffffff;
}

.stButton > button p,
.stDownloadButton > button p,
[data-testid="stFormSubmitButton"] button p {
    color: #ffffff;
}

.st-key-nav_menu .stButton {
    margin-bottom: 0.1rem;
}

.st-key-nav_menu .stButton > button {
    background: transparent;
    border: 0;
    box-shadow: none;
    color: var(--phr-text);
    justify-content: flex-start;
    min-height: 2rem;
    padding: 0.3rem 0.55rem;
    text-align: left;
    width: 100%;
}

.st-key-nav_menu .stButton > button:hover {
    background: #dfeae5;
    border: 0;
    color: var(--phr-text);
}

.st-key-nav_menu .stButton > button:disabled {
    background: #c6ded5;
    border: 0;
    color: var(--phr-accent);
    cursor: default;
    font-weight: 700;
    opacity: 1;
}

.st-key-nav_menu .stButton > button p {
    color: inherit;
}

[data-testid="stExpander"] {
    background: var(--phr-panel);
    color: var(--phr-text);
    border: 1px solid var(--phr-border);
    border-radius: 8px;
}

[data-testid="stDataFrame"] {
    border: 1px solid var(--phr-border);
    border-radius: 8px;
}

input,
textarea,
[data-baseweb="input"],
[data-baseweb="textarea"],
[data-baseweb="select"],
[data-baseweb="select"] > div {
    background: var(--phr-panel);
    color: var(--phr-text);
    border-color: var(--phr-border);
    border-radius: 8px;
}

input::placeholder,
textarea::placeholder {
    color: var(--phr-muted);
    opacity: 1;
}

[data-baseweb="select"] *,
[data-baseweb="popover"] *,
[role="listbox"] *,
[role="option"] * {
    color: var(--phr-text);
}

[data-baseweb="popover"],
[role="listbox"],
[role="option"] {
    background: var(--phr-panel);
    color: var(--phr-text);
}

[role="option"]:hover {
    background: var(--phr-accent-soft);
}

small, .caption {
    color: var(--phr-muted);
}
</style>
"""

FIELD_CONFIGS = {
    "allergies": {
        "title": "Allergies",
        "fields": [("allergen", "text"), ("reaction", "text"), ("severity", "text"), ("notes", "textarea")],
        "validator": validation.validate_allergy,
        "order_by": "allergen",
    },
    "medications": {
        "title": "Medications",
        "fields": [
            ("name", "text"),
            ("dose", "text"),
            ("frequency", "text"),
            ("start_date", "date_text"),
            ("end_date", "date_text"),
            ("status", MEDICATION_STATUSES),
            ("reason", "text"),
            ("notes", "textarea"),
        ],
        "validator": validation.validate_medication,
        "order_by": "name",
    },
    "lab_results": {
        "title": "Labs",
        "fields": [
            ("test_name", "text"),
            ("result_value", "text"),
            ("numeric_value", "number_optional"),
            ("unit", "text"),
            ("reference_low", "number_optional"),
            ("reference_high", "number_optional"),
            ("flag", LAB_FLAGS),
            ("lab_date", "date_text"),
            ("notes", "textarea"),
        ],
        "validator": validation.validate_lab,
        "order_by": "lab_date",
    },
    "health_entries": {
        "title": "Health Timeline",
        "fields": [
            ("entry_date", "date_text"),
            ("title", "text"),
            ("body_system", BODY_SYSTEMS),
            ("body_part", "text"),
            ("severity", "int_optional"),
            ("note", "textarea"),
        ],
        "validator": validation.validate_health_entry,
        "order_by": "entry_date",
    },
    "appointments": {
        "title": "Appointments",
        "fields": [
            ("appointment_date", "date_text"),
            ("title", "text"),
            ("provider", "text"),
            ("location", "text"),
            ("status", ["", *APPOINTMENT_STATUSES]),
            ("notes", "textarea"),
        ],
        "validator": validation.validate_appointment,
        "order_by": "appointment_date",
    },
    "reminders": {
        "title": "Reminders",
        "fields": [
            ("reminder_type", "text"),
            ("title", "text"),
            ("due_date", "date_text"),
            ("status", REMINDER_STATUSES),
            ("notes", "textarea"),
        ],
        "validator": validation.validate_reminder,
        "order_by": "due_date",
    },
    "wearable_records": {
        "title": "Wearables",
        "fields": [
            ("metric_type", WEARABLE_METRIC_TYPES),
            ("value", "number"),
            ("unit", "text"),
            ("timestamp", "date_text"),
            ("source", "text"),
        ],
        "validator": validation.validate_wearable,
        "order_by": "timestamp",
    },
    "conditions": {
        "title": "Tracked Conditions",
        "fields": [
            ("condition_name", "text"),
            ("source", ["", *CONDITION_SOURCES]),
            # Plain text, not "date_text": that kind prefills today when empty, which would invent a
            # date the user never gave and re-stamp one on every unrelated edit. Still format-checked
            # by validate_condition, and still rendered as a date via DATE_DISPLAY_COLUMNS.
            ("noted_date", "text"),
            ("notes", "textarea"),
        ],
        "validator": validation.validate_condition,
        "order_by": "condition_name",
    },
}


def format_label(name: str) -> str:
    return name.replace("_", " ").title()


def display_column_label(name: str) -> str:
    return DISPLAY_COLUMN_LABELS.get(name, format_label(name).replace(" Id", " ID"))


def display_dataframe(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    hidden_columns = [column for column in HIDDEN_DISPLAY_COLUMNS if column in frame.columns]
    if hidden_columns:
        frame = frame.drop(columns=hidden_columns)
    for column in DATE_DISPLAY_COLUMNS.intersection(frame.columns):
        frame[column] = frame[column].apply(lambda value: "" if pd.isna(value) else display_format.format_display_date(value))
    for column in DATETIME_DISPLAY_COLUMNS.intersection(frame.columns):
        frame[column] = frame[column].apply(lambda value: "" if pd.isna(value) else display_format.format_display_datetime(value))
    return frame.rename(columns={column: display_column_label(column) for column in frame.columns})


def apply_global_styles() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)


def page_header(title: str, description: str | None = None, kicker: str = "Local personal health record") -> None:
    description = description or PAGE_DESCRIPTIONS.get(title, "")
    st.markdown(
        f"""
        <div class="phr-topbar">
            <div class="phr-kicker">{escape(kicker)}</div>
            <h1>{escape(title)}</h1>
            <div class="phr-subtitle">{escape(description)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def is_locked_profile(person: dict | None, db_path: Path | str | None = None) -> bool:
    db_path = db.DB_PATH if db_path is None else db_path
    return bool(person and person.get("profile_password_enabled") and not security.health_data_visible(person, db_path=db_path))


def profile_selection_label(person: dict, db_path: Path | str | None = None) -> str:
    db_path = db.DB_PATH if db_path is None else db_path
    if is_locked_profile(person, db_path):
        return f"Protected profile (ID {person['id']})"
    return f"{person['name']} (ID {person['id']})"


def display_safe_people(people: list[dict], db_path: Path | str | None = None) -> list[dict]:
    db_path = db.DB_PATH if db_path is None else db_path
    rows = []
    for person in people:
        if not is_locked_profile(person, db_path):
            rows.append(person)
            continue
        rows.append(
            {
                "id": person["id"],
                "name": "Protected profile",
                "profile_password_enabled": person.get("profile_password_enabled"),
            }
        )
    return rows


def locked_profiles(db_path: Path | str | None = None) -> list[dict]:
    db_path = db.DB_PATH if db_path is None else db_path
    return [person for person in services.list_people(db_path=db_path) if is_locked_profile(person, db_path)]


def selected_profile_banner(person: dict | None, db_path: Path | str | None = None) -> None:
    db_path = db.DB_PATH if db_path is None else db_path
    if not person:
        return
    if is_locked_profile(person, db_path):
        st.markdown(
            """
            <div class="phr-profile-strip">
                <span class="phr-profile-name">Protected profile</span>
                <span class="phr-pill">Password protected</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return
    details = []
    if person.get("relationship"):
        details.append(str(person["relationship"]))
    if person.get("date_of_birth"):
        details.append(f"DOB {person['date_of_birth']}")
    if person.get("sex"):
        details.append(str(person["sex"]))
    detail_html = "".join(f'<span class="phr-pill">{escape(detail)}</span>' for detail in details)
    st.markdown(
        f"""
        <div class="phr-profile-strip">
            <span class="phr-profile-name">{escape(str(person['name']))}</span>
            {detail_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_navigation(container=None) -> str:
    """Render the sidebar navigation and return the page to show.

    No page is hidden any more. Navigation used to depend on profile data -- it hid Condition
    Details for a profile with none -- which made nav visibility an observable side channel for
    whether a locked profile had conditions. That page is gone, and so is the whole surface.

    The fallback survives in a more general form: a `nav_page` left in session state by an older
    build (Condition Details, say) matches no dispatch branch and would render a blank page.
    Anything not in PAGES falls back to the Dashboard, and the fallback is written back so a nav
    button is still marked current.
    """
    current_page = st.session_state.get("nav_page", NAV_SECTIONS["Overview"][0])
    if current_page not in PAGES:
        current_page = NAV_SECTIONS["Overview"][0]
        st.session_state["nav_page"] = current_page

    target = st.sidebar.container(key="nav_menu") if container is None else container
    with target:
        st.caption("Navigation")
        for section, pages in NAV_SECTIONS.items():
            st.markdown(f"**{section}**")
            for page in pages:
                is_current = page == current_page
                if st.button(
                    page_button_label(page),
                    key=f"nav_page_{page}",
                    type="primary" if is_current else "secondary",
                    disabled=is_current,
                    use_container_width=True,
                ):
                    st.session_state["nav_page"] = page
                    st.rerun()

    return current_page


def page_button_label(page: str) -> str:
    return f"{PAGE_EMOJIS.get(page, '•')} {page}"


def action_button_label(label: str) -> str:
    emoji = ACTION_EMOJIS.get(label)
    if emoji:
        return f"{emoji} {label}"
    for prefix, prefix_emoji in ACTION_PREFIX_EMOJIS.items():
        if label.startswith(prefix):
            return f"{prefix_emoji} {label}"
    return label


def warning_label(message: str) -> str:
    return f"⚠️ {message}"


def create_demo_database(demo_db_path: Path | str, sample_data_path: Path | str = SAMPLE_DATA_PATH) -> int | None:
    payload = json.loads(Path(sample_data_path).read_text(encoding="utf-8"))
    tables = payload.get("tables", payload)
    db.init_db(demo_db_path)
    db.import_all_tables(tables, clear_existing=True, db_path=demo_db_path)
    people = services.list_people(db_path=demo_db_path)
    return int(people[0]["id"]) if people else None


def is_demo_mode() -> bool:
    return bool(st.session_state.get(DEMO_MODE_KEY) and st.session_state.get(DEMO_DB_PATH_KEY))


def active_db_path() -> Path | str:
    if is_demo_mode():
        return st.session_state.get(DEMO_DB_PATH_KEY, db.DB_PATH)
    return db.DB_PATH


def start_demo_mode() -> None:
    demo_db_path = Path(tempfile.gettempdir()) / f"phr_demo_{uuid.uuid4().hex}.db"
    create_demo_database(demo_db_path)
    st.session_state[DEMO_MODE_KEY] = True
    st.session_state[DEMO_DB_PATH_KEY] = str(demo_db_path)


def exit_demo_mode() -> None:
    demo_db_path = st.session_state.get(DEMO_DB_PATH_KEY)
    st.session_state.pop(DEMO_MODE_KEY, None)
    st.session_state.pop(DEMO_DB_PATH_KEY, None)
    if demo_db_path:
        try:
            Path(demo_db_path).unlink(missing_ok=True)
        except OSError:
            pass


def demo_mode_controls() -> None:
    if is_demo_mode():
        st.success("Demo mode active")
        st.caption("Using session-only sample data.")
        if st.button(action_button_label("Exit demo mode"), key="exit_demo_mode"):
            exit_demo_mode()
            st.rerun()
        return
    if st.button(action_button_label("Demo mode"), key="start_demo_mode"):
        start_demo_mode()
        st.rerun()


def show_errors(errors: list[str]) -> None:
    for error in errors:
        st.error(error)


def clean_payload(table: str, payload: dict) -> dict:
    cleaned = {}
    for key, value in payload.items():
        if value == "":
            cleaned[key] = None
        else:
            cleaned[key] = value
    if table == "lab_results":
        for key in ["numeric_value", "reference_low", "reference_high"]:
            if key in cleaned:
                cleaned[key] = validation.normalize_optional_number(cleaned[key])
    if table == "wearable_records" and "value" in cleaned and not validation.is_blank(cleaned["value"]):
        cleaned["value"] = float(cleaned["value"])
    if table in {"allergies", "health_entries"} and "severity" in cleaned:
        if validation.is_blank(cleaned["severity"]):
            cleaned["severity"] = None
        elif table == "health_entries":
            cleaned["severity"] = int(cleaned["severity"])
    return cleaned


def input_field(name: str, kind, default=None, key: str | None = None):
    label = format_label(name)
    key = key or name
    default = "" if default is None else default
    if isinstance(kind, list):
        options = kind
        index = options.index(default) if default in options else 0
        return st.selectbox(label, options, index=index, key=key)
    if kind == "textarea":
        return st.text_area(label, value=str(default or ""), key=key)
    if kind == "number":
        return st.text_input(label, value=str(default or ""), key=key)
    if kind == "number_optional":
        return st.text_input(label, value="" if default is None else str(default), key=key)
    if kind == "int_optional":
        return st.text_input(label, value="" if default is None else str(default), key=key)
    if kind == "date_text":
        return st.text_input(label, value=str(default or date.today().isoformat()), key=key)
    return st.text_input(label, value=str(default or ""), key=key)


def selected_profile_sidebar(db_path: Path | str | None = None, demo_mode: bool = False) -> tuple[str, dict | None]:
    db_path = db.DB_PATH if db_path is None else db_path
    people = services.list_people(db_path=db_path)
    names = [profile_selection_label(person, db_path) for person in people]
    label = "Demo profile" if demo_mode else "Selected profile"
    key = "demo_selected_profile" if demo_mode else "selected_profile"
    selection = st.sidebar.selectbox(label, names or ["No profile selected"], key=key)
    if not people:
        return selection, None
    index = names.index(selection)
    return selection, people[index]


def unlock_screen(person: dict, db_path: Path | str | None = None) -> None:
    db_path = db.DB_PATH if db_path is None else db_path
    st.warning(warning_label("This profile is password-protected."))
    if person.get("profile_password_hint"):
        st.caption(f"Password hint: {person['profile_password_hint']}")
    password = st.text_input("Password", type="password")
    if st.button(action_button_label("Unlock profile")):
        if security.verify_password(password, person.get("profile_password_hash") or ""):
            security.unlock_profile(int(person["id"]), db_path=db_path)
            st.rerun()
        st.error("Incorrect password.")


def require_profile(person: dict | None) -> bool:
    if person:
        return True
    st.info("Create a profile before adding health records.")
    return False


def dataframe(rows: list[dict]) -> None:
    if rows:
        st.dataframe(display_dataframe(rows), width="stretch", hide_index=True)
    else:
        st.info("No records yet.")


def toggle_add_form(key: str) -> None:
    st.session_state[key] = not st.session_state.get(key, False)


def close_form(key: str) -> None:
    st.session_state[key] = False


def record_label(row: dict) -> str:
    label = (
        row.get("title")
        or row.get("name")
        or row.get("test_name")
        or row.get("allergen")
        or row.get("metric_type")
        or row.get("condition_name")
    )
    return f"{label or 'Record'} (ID {row['id']})"


def profile_form(existing: dict | None = None, key_prefix: str = "profile") -> dict:
    return {
        "name": st.text_input("Name", value=(existing or {}).get("name") or "", key=f"{key_prefix}_name"),
        "date_of_birth": st.text_input("Date of birth", value=(existing or {}).get("date_of_birth") or "", key=f"{key_prefix}_dob"),
        "sex": st.text_input("Sex", value=(existing or {}).get("sex") or "", key=f"{key_prefix}_sex"),
        "relationship": st.text_input("Relationship", value=(existing or {}).get("relationship") or "", key=f"{key_prefix}_relationship"),
        "emergency_contact": st.text_input("Emergency contact", value=(existing or {}).get("emergency_contact") or "", key=f"{key_prefix}_emergency"),
        "notes": st.text_area("Notes", value=(existing or {}).get("notes") or "", key=f"{key_prefix}_notes"),
    }


def password_settings(person: dict, db_path: Path | str | None = None) -> None:
    db_path = db.DB_PATH if db_path is None else db_path
    st.subheader("Profile Password")
    if person.get("profile_password_enabled"):
        if not security.health_data_visible(person, db_path=db_path):
            unlock_screen(person, db_path=db_path)
            return
        st.info("Password protection is enabled for this profile.")
        if st.button(action_button_label("Lock profile")):
            security.lock_profile(int(person["id"]), db_path=db_path)
            st.rerun()
        confirm_remove = st.checkbox("Confirm password removal", key=f"confirm_remove_password_{person['id']}")
        if st.button(action_button_label("Remove password")):
            if not confirm_remove:
                st.error("Confirm password removal before continuing.")
                return
            if apply_record_change(
                lambda: services.update_person(
                    int(person["id"]),
                    {"profile_password_enabled": 0, "profile_password_hash": None, "profile_password_hint": None},
                    db_path=db_path,
                )
            ):
                security.unlock_profile(int(person["id"]), db_path=db_path)
                st.success("Password removed.")
                st.rerun()
    with st.form(f"password_form_{person['id']}"):
        password = st.text_input("Set/change password", type="password")
        hint = st.text_input("Password hint", value=person.get("profile_password_hint") or "")
        submitted = st.form_submit_button(action_button_label("Save password"))
        if submitted:
            if not password:
                st.error("Password cannot be blank.")
            elif apply_record_change(
                lambda: services.update_person(
                    int(person["id"]),
                    {
                        "profile_password_enabled": 1,
                        "profile_password_hash": security.hash_password(password),
                        "profile_password_hint": hint,
                    },
                    db_path=db_path,
                )
            ):
                security.lock_profile(int(person["id"]), db_path=db_path)
                st.success("Password saved. Profile is now locked.")
                # Rerun so the sidebar recomputes. Navigation visibility was already decided for
                # this render against the unlocked profile, so without this the screen says locked
                # while still listing profile-data-dependent pages -- which is itself a disclosure.
                st.rerun()


def ai_settings() -> None:
    st.subheader("Zhipu AI BigModel")
    if ai_config.zhipu_key_configured():
        st.success("Zhipu AI API key is configured.")
    else:
        st.warning(warning_label("Zhipu AI API key is not configured. AI safety-checked insights will not run."))
    st.caption(f"AI provider: {ai_config.AI_PROVIDER}")
    st.caption(f"Model: {ai_config.ZHIPU_MODEL}")
    st.caption(f"AI Chat model candidates: {', '.join(ai_chat.chat_model_candidates())}")
    st.caption(f"Max response tokens: {ai_config.ZHIPU_MAX_TOKENS}")
    st.caption(f"Max AI context bytes: {ai_config.ZHIPU_CONTEXT_BYTE_LIMIT}")
    st.caption("Default setup uses BigModel's free low-power text model with a compact patient-data packet.")
    with st.form("zhipu_api_key_form"):
        api_key = st.text_input("Zhipu AI API key", type="password")
        submitted = st.form_submit_button(action_button_label("Save API key"))
        if submitted:
            ok, message = ai_config.store_zhipu_api_key(api_key)
            if ok:
                st.success(message)
            else:
                st.error(message)
                st.rerun()
    if st.button(action_button_label("Test BigModel API key")):
        ok, message, detail = insights.validate_zhipu_connection()
        if ok:
            st.success(message)
        else:
            st.error(message)
            if detail:
                with st.expander("Provider details"):
                    st.code(detail)


def page_profiles(person: dict | None, db_path: Path | str | None = None, demo_mode: bool = False) -> None:  # noqa: C901, PLR0915
    db_path = db.DB_PATH if db_path is None else db_path
    page_header("Profiles")
    people = services.list_people(db_path=db_path)
    dataframe(display_safe_people(people, db_path))
    if demo_mode:
        st.info("Demo profiles are loaded from sample data and are separate from your saved profiles. Exit demo mode to manage real profiles.")
        return

    add_profile_key = "show_add_profile_form"
    if add_profile_key not in st.session_state:
        st.session_state[add_profile_key] = False

    if st.button(action_button_label("Add profile"), key="toggle_add_profile", on_click=toggle_add_form, args=(add_profile_key,)):
        pass

    if st.session_state[add_profile_key]:
        with st.form("add_profile"):
            data = profile_form(key_prefix="add_profile")
            enable_password = st.checkbox("Enable profile password")
            password = st.text_input("Password", type="password") if enable_password else ""
            hint = st.text_input("Password hint") if enable_password else ""
            submit_col, cancel_col = st.columns([1, 1])
            with submit_col:
                submitted = st.form_submit_button(action_button_label("Create profile"))
            with cancel_col:
                cancelled = st.form_submit_button(action_button_label("Cancel"))
            if cancelled:
                close_form(add_profile_key)
                st.rerun()
            if submitted:
                errors = validation.validate_person(data)
                if enable_password and not password:
                    errors.append("Password is required when password protection is enabled.")
                if errors:
                    show_errors(errors)
                else:
                    if enable_password:
                        data["profile_password_enabled"] = 1
                        data["profile_password_hash"] = security.hash_password(password)
                        data["profile_password_hint"] = hint
                    if apply_record_change(
                        lambda: services.create_person(clean_payload("people", data), db_path=db_path)
                    ):
                        st.success("Profile created.")
                        st.session_state[add_profile_key] = False
                        st.rerun()

    if not people:
        return

    profile_edit_reset_key = "edit_profile_selection_reset"
    if profile_edit_reset_key not in st.session_state:
        st.session_state[profile_edit_reset_key] = 0
    profile_options = [""] + [str(row["id"]) for row in people]
    profile_labels = {"": "Select a profile to edit"}
    profile_labels.update({str(row["id"]): profile_selection_label(row, db_path) for row in people})
    selected_profile_id = st.selectbox(
        "Edit profile",
        profile_options,
        format_func=lambda value: profile_labels[value],
        key=f"edit_profile_selection_{st.session_state[profile_edit_reset_key]}",
    )
    if not selected_profile_id:
        return

    row = next(item for item in people if str(item["id"]) == selected_profile_id)
    if is_locked_profile(row, db_path):
        selected_profile_banner(row, db_path=db_path)
        unlock_screen(row, db_path=db_path)
        return
    with st.form(f"edit_profile_{row['id']}"):
        data = profile_form(row, key_prefix=f"edit_profile_{row['id']}")
        confirm_delete = st.checkbox("Confirm profile delete", key=f"confirm_delete_profile_{row['id']}")
        save_col, delete_col, cancel_col = st.columns([1, 1, 1])
        with save_col:
            submitted = st.form_submit_button(action_button_label("Save changes"))
        with delete_col:
            deleted = st.form_submit_button(action_button_label("Delete profile"))
        with cancel_col:
            cancelled = st.form_submit_button(action_button_label("Cancel"))
        if cancelled:
            st.session_state[profile_edit_reset_key] += 1
            st.rerun()
        if deleted:
            if not confirm_delete:
                st.error("Confirm profile delete before continuing.")
                return
            if apply_record_change(lambda: services.delete_person(int(row["id"]), db_path=db_path)):
                st.warning(warning_label("Profile deleted."))
                st.session_state[profile_edit_reset_key] += 1
                st.rerun()
        if submitted:
            errors = validation.validate_person(data)
            if errors:
                show_errors(errors)
            elif apply_record_change(
                lambda: services.update_person(int(row["id"]), clean_payload("people", data), db_path=db_path)
            ):
                st.success("Profile updated.")
                st.session_state[profile_edit_reset_key] += 1
                st.rerun()
    with st.expander("Profile password"):
        password_settings(row, db_path=db_path)


def date_range_controls(prefix: str) -> tuple[str | None, str | None]:
    cols = st.columns(2)
    with cols[0]:
        start = st.text_input("Start date", value="", key=f"{prefix}_start")
    with cols[1]:
        end = st.text_input("End date", value="", key=f"{prefix}_end")
    return start or None, end or None


def apply_record_change(action: Callable[[], None]) -> bool:
    """Run a person-scoped write, reporting a clean message if the record is not available.

    `db.RecordNotFound` means the target — a record, or the profile itself for
    profile-level writes — no longer exists or is out of scope for the caller, e.g.
    after a concurrent delete in another session.
    """
    try:
        action()
    except db.RecordNotFound:
        st.error("That record is no longer available. Refresh and try again.")
        return False
    except db.DatabaseBusyError:
        st.error("The health record database is busy. Wait a moment and try again.")
        return False
    return True


def record_page_scope(table: str, person_id: int, db_path: Path | str) -> str:
    """Return the stable database/profile/table identity for write-capable UI state."""
    return f"{Path(db_path).resolve()}:{person_id}:{table}"


def generic_record_page(table: str, person: dict, db_path: Path | str | None = None, demo_mode: bool = False, render_header: bool = True) -> None:  # noqa: C901, PLR0915
    """Render a table's list and add/edit forms.

    `render_header` exists for Tracked Conditions, which composes its own page header above a
    detail view and nests this CRUD block in an expander beneath it. Defaulting to True keeps every
    other caller byte-for-byte unchanged.
    """
    db_path = db.DB_PATH if db_path is None else db_path
    config = FIELD_CONFIGS[table]
    person_id = int(person["id"])
    state_scope = record_page_scope(table, person_id, db_path)
    if render_header:
        page_header(config["title"])
    if demo_mode:
        st.caption("Demo changes stay in this Streamlit session and do not affect saved profiles.")

    filters = {}
    start = end = None
    if table == "health_entries":
        start, end = date_range_controls("timeline")
        body_system = st.selectbox("Body system", ["", *BODY_SYSTEMS])
        body_part = st.text_input("Body part")
        search = st.text_input("Search title/notes")
        rows = services.filter_health_entries(person_id, start, end, body_system or None, body_part or None, search or None, db_path=db_path)
    elif table == "lab_results":
        start, end = date_range_controls("labs")
        test_search = st.text_input("Test search")
        flag = st.selectbox("Lab flag", ["", *LAB_FLAGS])
        rows = services.filter_labs(person_id, start, end, test_search or None, flag or None, db_path=db_path)
    elif table == "medications":
        status = st.selectbox("Medication status", ["", *MEDICATION_STATUSES])
        rows = services.medication_filters(person_id, status or None, db_path=db_path)
    elif table == "reminders":
        status = st.selectbox("Reminder status", ["", *REMINDER_STATUSES])
        rows = services.reminder_filters(person_id, status or None, db_path=db_path)
    else:
        rows = services.list_items(table, person_id, filters, config["order_by"], descending=table not in {"allergies", "medications", "conditions"}, db_path=db_path)

    dataframe(rows)

    singular_title = SINGULAR_TITLES.get(config["title"], config["title"])
    add_form_key = f"{state_scope}:add:open"
    if add_form_key not in st.session_state:
        st.session_state[add_form_key] = False

    if st.button(action_button_label(f"Add {singular_title}"), key=f"{state_scope}:add:toggle", on_click=toggle_add_form, args=(add_form_key,)):
        pass

    if st.session_state[add_form_key]:
        with st.form(f"{state_scope}:add:form"):
            data = {name: input_field(name, kind, key=f"{state_scope}:add:{name}") for name, kind in config["fields"]}
            submit_col, cancel_col = st.columns([1, 1])
            with submit_col:
                submitted = st.form_submit_button(action_button_label("Add record"))
            with cancel_col:
                cancelled = st.form_submit_button(action_button_label("Cancel"))
            if cancelled:
                close_form(add_form_key)
                st.rerun()
            if submitted:
                errors = config["validator"](data)
                if errors:
                    show_errors(errors)
                else:
                    if apply_record_change(
                        lambda: services.create_item(
                            table,
                            person_id,
                            clean_payload(table, data),
                            db_path=db_path,
                        )
                    ):
                        st.success("Record added.")
                        st.session_state[add_form_key] = False
                        st.rerun()

    if table == "lab_results":
        numeric_rows = [row for row in rows if row.get("numeric_value") is not None]
        if numeric_rows:
            trend = pd.DataFrame(numeric_rows)
            selected_test = st.selectbox("Trend test", sorted(trend["test_name"].unique()))
            chart_data = trend[trend["test_name"] == selected_test].sort_values("lab_date")
            st.line_chart(chart_data, x="lab_date", y="numeric_value")
    if table == "wearable_records" and rows:
        chart_data = pd.DataFrame(rows).sort_values("timestamp")
        metric = st.selectbox("Trend metric", sorted(chart_data["metric_type"].unique()))
        st.line_chart(chart_data[chart_data["metric_type"] == metric], x="timestamp", y="value")
        dataframe(services.wearable_summary(person_id, db_path=db_path))

    if not rows:
        return

    edit_reset_key = f"{state_scope}:edit:reset"
    if edit_reset_key not in st.session_state:
        st.session_state[edit_reset_key] = 0
    edit_options = [""] + [str(row["id"]) for row in rows]
    edit_labels = {"": "Select a record to edit"}
    edit_labels.update({str(row["id"]): record_label(row) for row in rows})
    selected_record_id = st.selectbox(
        "Edit existing record",
        edit_options,
        format_func=lambda value: edit_labels[value],
        key=f"{state_scope}:edit:selection:{st.session_state[edit_reset_key]}",
    )
    if not selected_record_id:
        return

    row = next(item for item in rows if str(item["id"]) == selected_record_id)
    record_scope = f"{state_scope}:edit:{row['id']}"
    with st.form(f"{record_scope}:form"):
        data = {name: input_field(name, kind, row.get(name), key=f"{record_scope}:{name}") for name, kind in config["fields"]}
        confirm_delete = st.checkbox("Confirm record delete", key=f"{record_scope}:confirm_delete")
        if table == "reminders":
            save_col, complete_col, dismiss_col, delete_col, cancel_col = st.columns([1, 1, 1, 1, 1])
            with save_col:
                submitted = st.form_submit_button(action_button_label("Save changes"))
            with complete_col:
                completed = st.form_submit_button(action_button_label("Mark complete"))
            with dismiss_col:
                dismissed = st.form_submit_button(action_button_label("Dismiss"))
            with delete_col:
                deleted = st.form_submit_button(action_button_label("Delete"))
            with cancel_col:
                cancelled = st.form_submit_button(action_button_label("Cancel"))
        else:
            save_col, delete_col, cancel_col = st.columns([1, 1, 1])
            with save_col:
                submitted = st.form_submit_button(action_button_label("Save changes"))
            with delete_col:
                deleted = st.form_submit_button(action_button_label("Delete"))
            with cancel_col:
                cancelled = st.form_submit_button(action_button_label("Cancel"))
            completed = dismissed = False

        if cancelled:
            st.session_state[edit_reset_key] += 1
            st.rerun()
        if completed:
            if apply_record_change(lambda: services.update_item("reminders", person_id=person_id, record_id=int(row["id"]), data={"status": "Completed"}, db_path=db_path)):
                st.session_state[edit_reset_key] += 1
                st.rerun()
        if dismissed:
            if apply_record_change(lambda: services.update_item("reminders", person_id=person_id, record_id=int(row["id"]), data={"status": "Dismissed"}, db_path=db_path)):
                st.session_state[edit_reset_key] += 1
                st.rerun()
        if deleted:
            if not confirm_delete:
                st.error("Confirm record delete before continuing.")
                return
            if apply_record_change(lambda: services.delete_item(table, person_id=person_id, record_id=int(row["id"]), db_path=db_path)):
                st.warning(warning_label("Record deleted."))
                st.session_state[edit_reset_key] += 1
                st.rerun()
        if submitted:
            errors = config["validator"](data)
            if errors:
                show_errors(errors)
            elif apply_record_change(lambda: services.update_item(table, person_id=person_id, record_id=int(row["id"]), data=clean_payload(table, data), db_path=db_path)):
                st.success("Record updated.")
                st.session_state[edit_reset_key] += 1
                st.rerun()


def condition_display_lines(rows: list[dict]) -> list[str]:
    """Format tracked-condition rows as "Condition — Source" display lines.

    Pure formatting over rows already scoped to a single profile. The source is omitted when the
    record does not carry one; nothing is inferred about the condition beyond what was entered.
    """
    lines = []
    for row in rows:
        name = str(row.get("condition_name") or "").strip()
        if not name:
            continue
        source = str(row.get("source") or "").strip()
        lines.append(f"{name} — {source}" if source else name)
    return lines


def render_dashboard_conditions(person_id: int, rows: list[dict], db_path: Path | str) -> None:
    """Render the dashboard's tracked-condition list and the preview for the selected one.

    Reads only rows already scoped to `person_id`. Selecting a condition shows the records the
    deterministic mapping associates with it; nothing here interprets those records.
    """
    lines = condition_display_lines(rows)
    names = [str(row.get("condition_name") or "").strip() for row in rows]
    names = [name for name in dict.fromkeys(names) if name]
    # Before the empty-profile return, so a stale selection is dropped either way.
    condition_ui.sync_valid_conditions(st.session_state, names)
    if not lines:
        st.caption("No conditions are being tracked.")
    else:
        for line in lines:
            st.markdown(f"- {line}")
        selected = st.pills(
            "Condition preview", names, default=names[0], key=condition_ui.SELECTED_CONDITION_KEY
        )
        if isinstance(selected, str) and selected in names:
            condition_ui.render_condition_preview(person_id, selected, db_path=db_path)
    # Outside the empty-condition branch on purpose. The dashboard carries the accessible slice and
    # the detail view is a click away rather than a page to hunt for in the sidebar -- and a profile
    # with no conditions needs that route most, since the page it leads to is where the first one
    # gets recorded.
    if st.button("View full condition detail →", key="dashboard_condition_detail"):
        st.session_state["nav_page"] = "Tracked Conditions"
        st.rerun()


def page_tracked_conditions(person: dict, db_path: Path | str | None = None, demo_mode: bool = False) -> None:
    """The detailed condition view, with the record list and forms beneath it.

    Ordered detail-first because that is what the page is for; the CRUD block keeps working exactly
    as it does on every other record page, just nested in an expander. The expander starts open when
    the profile has no conditions, since adding one is then the only useful thing on the page --
    the page is never hidden, because it is where a condition is created.
    """
    db_path = db.DB_PATH if db_path is None else db_path
    page_header("Tracked Conditions")
    rows = services.tracked_conditions(int(person["id"]), db_path=db_path)
    condition_ui.render_tracked_conditions_detail(person, rows, db_path=db_path)
    st.divider()
    with st.expander("Manage tracked conditions", expanded=not rows):
        generic_record_page("conditions", person, db_path, demo_mode=demo_mode, render_header=False)


def page_dashboard(person: dict, db_path: Path | str | None = None) -> None:
    db_path = db.DB_PATH if db_path is None else db_path
    page_header("Dashboard")
    data = services.dashboard_data(int(person["id"]), db_path=db_path)
    st.markdown(
        f"""
        <div class="phr-dashboard-note">
            <strong>{escape(str(data["person"]["name"]))}</strong><br>
            {escape(str(data["person"].get("notes") or "No profile notes."))}
        </div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(4)
    cols[0].metric("Active medications", len(data["active_medications"]))
    cols[1].metric("Allergies", len(data["allergies"]))
    cols[2].metric("Latest labs", len(data["latest_labs"]))
    cols[3].metric("Overdue reminders", len(data["overdue_reminders"]))
    dashboard_sections = [
        ("Allergies", data["allergies"]),
        ("Active Medications", data["active_medications"]),
        ("Latest Labs", data["latest_labs"]),
        ("Recent Health Timeline", data["recent_entries"]),
        ("Upcoming Appointments", data["upcoming_appointments"]),
        ("Overdue Reminders", data["overdue_reminders"]),
        ("Recent Wearable Summary", data["wearable_summary"]),
    ]
    section_map = dict(dashboard_sections)
    section = st.selectbox("Dashboard section", list(section_map), key="dashboard_section")
    st.subheader(section)
    dataframe(section_map[section])
    st.subheader("Tracked Conditions")
    render_dashboard_conditions(int(person["id"]), data["conditions"], db_path)


def page_provider_summary(person: dict, db_path: Path | str | None = None) -> None:
    db_path = db.DB_PATH if db_path is None else db_path
    page_header("Provider Summary")
    start, end = date_range_controls("provider")
    include_labs = st.checkbox("Include labs", value=True)
    include_timeline = st.checkbox("Include health timeline", value=True)
    include_wearables = st.checkbox("Include wearables", value=True)
    markdown = services.generate_provider_summary(int(person["id"]), start, end, include_labs, include_timeline, include_wearables, db_path=db_path)
    st.download_button(action_button_label("Download Markdown"), markdown, file_name="provider_summary.md", mime="text/markdown")
    st.markdown(markdown)


def page_emergency_snapshot(person: dict, db_path: Path | str | None = None) -> None:
    db_path = db.DB_PATH if db_path is None else db_path
    page_header("Emergency Snapshot")
    markdown = services.generate_emergency_snapshot(int(person["id"]), db_path=db_path)
    st.download_button(action_button_label("Download Markdown"), markdown, file_name="emergency_snapshot.md", mime="text/markdown")
    st.markdown(markdown)


def page_import_export(person: dict | None, db_path: Path | str | None = None, demo_mode: bool = False) -> None:  # noqa: C901, PLR0915
    db_path = db.DB_PATH if db_path is None else db_path
    page_header("Import/Export")
    if demo_mode:
        st.caption("Imports and restores in demo mode modify only the session demo database.")
    if person:
        st.subheader("CSV Imports")
        labs_file = st.file_uploader("Import labs CSV", type=["csv"])
        if labs_file and st.button(action_button_label("Import labs")):
            try:
                st.write(imports_exports.import_labs_csv(labs_file, int(person["id"]), db_path=db_path))
            except db.DatabaseBusyError as exc:
                st.error(f"{exc} Some rows may already be imported; review the table before retrying.")
        wearable_file = st.file_uploader("Import wearables CSV", type=["csv"])
        if wearable_file and st.button(action_button_label("Import wearables")):
            try:
                st.write(imports_exports.import_wearables_csv(wearable_file, int(person["id"]), db_path=db_path))
            except db.DatabaseBusyError as exc:
                st.error(f"{exc} Some rows may already be imported; review the table before retrying.")
        st.download_button(action_button_label("Download sample labs CSV"), imports_exports.sample_labs_csv(), "sample_labs.csv", "text/csv")
        st.download_button(action_button_label("Download sample wearables CSV"), imports_exports.sample_wearables_csv(), "sample_wearables.csv", "text/csv")

    st.subheader("FHIR Interoperability")
    fhir_version = st.selectbox("FHIR version", fhir.SUPPORTED_FHIR_VERSIONS, key="fhir_version")
    protected_locked = locked_profiles(db_path)
    all_profile_export_available = not protected_locked
    export_scope = "All profiles" if not person else "Selected profile"
    if person:
        options = ["Selected profile"]
        if all_profile_export_available:
            options.append("All profiles")
        export_scope = st.selectbox("FHIR export scope", options, key="fhir_export_scope")
    elif not all_profile_export_available:
        st.warning(warning_label("Unlock protected profiles before exporting all-profile FHIR data."))
        export_scope = None
    export_person_id = int(person["id"]) if person and export_scope == "Selected profile" else None
    if export_scope:
        fhir_bundle = imports_exports.export_fhir_bundle(fhir_version, person_id=export_person_id, db_path=db_path)
        st.download_button(
            action_button_label(f"Export FHIR {fhir_version} Bundle"),
            fhir_bundle,
            file_name=f"phr_fhir_{fhir_version.lower()}_bundle.json",
            mime=fhir.FHIR_MIME_TYPE,
        )
    fhir_file = st.file_uploader("Import FHIR Bundle", type=["json"], key="fhir_bundle_upload")
    clear_existing_fhir = st.checkbox("Clear existing records before FHIR import", key="fhir_clear_existing")
    confirm_clear_fhir = st.checkbox("Confirm FHIR clear import", key="confirm_fhir_clear") if clear_existing_fhir else True
    if fhir_file and st.button(action_button_label("Import FHIR Bundle")):
        if not confirm_clear_fhir:
            st.error("Confirm FHIR clear import before continuing.")
        else:
            try:
                result = imports_exports.import_fhir_bundle(fhir_file.read().decode("utf-8"), clear_existing=clear_existing_fhir, db_path=db_path)
            except (ValueError, json.JSONDecodeError, db.DatabaseBusyError) as exc:
                st.error(f"FHIR import failed: {exc}")
            else:
                st.write(result)
                st.success("FHIR import completed.")
                st.rerun()

    st.subheader("JSON Backup")
    backup_scope = "All profiles" if not person else "Selected profile"
    if person:
        options = ["Selected profile"]
        if all_profile_export_available:
            options.append("All profiles")
        backup_scope = st.selectbox("JSON backup export scope", options, key="json_backup_scope")
    elif not all_profile_export_available:
        st.warning(warning_label("Unlock protected profiles before exporting all-profile JSON backup data."))
        backup_scope = None
    if backup_scope:
        backup_person_id = int(person["id"]) if person and backup_scope == "Selected profile" else None
        backup = imports_exports.export_json_backup(db_path=db_path, person_id=backup_person_id)
        st.download_button(action_button_label("Export JSON backup"), backup, "phr_backup.json", "application/json")
    backup_file = st.file_uploader("Restore JSON backup", type=["json"])
    clear_existing = st.checkbox("Clear existing records before restore")
    confirm_restore = st.checkbox("Confirm backup restore", key="confirm_backup_restore")
    if backup_file and st.button(action_button_label("Restore backup")):
        if not confirm_restore:
            st.error("Confirm backup restore before continuing.")
        else:
            try:
                imports_exports.import_json_backup(backup_file.read().decode("utf-8"), clear_existing=clear_existing, db_path=db_path)
            except (ValueError, json.JSONDecodeError, db.DatabaseBusyError) as exc:
                st.error(f"Backup restore failed: {exc}")
            else:
                st.success("Backup restored.")
                st.rerun()


def page_insights(person: dict, db_path: Path | str | None = None) -> None:
    db_path = db.DB_PATH if db_path is None else db_path
    page_header("Health Insights")
    person_id = int(person["id"])
    start, end = date_range_controls("insights")
    include_medications = st.checkbox("Include medications", value=True)
    include_allergies = st.checkbox("Include allergies", value=True)
    include_labs = st.checkbox("Include labs", value=True)
    include_entries = st.checkbox("Include health timeline", value=True)
    include_appointments = st.checkbox("Include appointments", value=True)
    include_reminders = st.checkbox("Include reminders", value=True)
    include_wearables = st.checkbox("Include wearables", value=True)
    focus_area = st.selectbox(
        "Focus area",
        [
            "General overview",
            "Medication adherence",
            "Lab trends",
            "Activity and sleep",
            "Weight trend",
            "Symptoms by body system",
            "Doctor visit preparation",
            "Follow-up reminders",
        ],
    )
    context = insights.collect_health_context(
        int(person["id"]),
        (start, end) if start or end else None,
        include_medications,
        include_allergies,
        include_labs,
        include_entries,
        include_appointments,
        include_reminders,
        include_wearables,
        db_path=db_path,
    )
    if st.button(action_button_label("Generate rule-based report")):
        st.markdown(insights.generate_rule_based_insights(context, focus_area))
    consent_key = f"{record_page_scope('insights', person_id, db_path)}:ai_consent"
    ai_consent = st.checkbox(
        "I understand selected profile context will be sent to Zhipu AI.", key=consent_key
    )
    if st.button(action_button_label("Generate AI safety-checked insights")):
        if not ai_consent:
            st.error("Confirm AI context sharing before generating AI insights.")
        else:
            result = insights.generate_ai_insight_result(context, focus_area)
            if result.get("warning"):
                st.warning(warning_label(result["warning"]))
                if result.get("provider_details"):
                    with st.expander("Provider details"):
                        st.code(result["provider_details"])
            st.markdown(result["report"])


def page_ai_chat(person: dict, db_path: Path | str | None = None) -> None:
    db_path = db.DB_PATH if db_path is None else db_path
    page_header("AI Health Assistant", PAGE_DESCRIPTIONS["AI Chat"])
    ai_chat.render_ai_chatbot(int(person["id"]), db_path=db_path)


def main() -> None:  # noqa: C901, PLR0915
    st.set_page_config(page_title="Family Personal Health Record", page_icon="PHR", layout="wide")
    apply_global_styles()
    st.write("")  # Top spacer to prevent Streamlit UI cutoff
    try:
        # Pass the module attribute explicitly: the keyword default was bound at import
        # time, and tests repoint db.DB_PATH at temporary databases.
        db.init_db(db.DB_PATH)
    except db.DatabaseBusyError as exc:
        st.error(str(exc))
        st.stop()

    with st.sidebar:
        st.markdown("### Family PHR")
        st.caption("Local-first private prototype")
        st.divider()
        demo_mode_controls()
        st.divider()
        # Created here so navigation keeps its position in the sidebar, but filled below: which
        # pages are visible depends on the selected profile, which is not resolved until after.
        nav_slot = st.container(key="nav_menu")
        st.divider()
        demo_mode = is_demo_mode()
        current_db_path = active_db_path()
        _, person = selected_profile_sidebar(current_db_path, demo_mode=demo_mode)
        if person:
            label = "Demo profile" if demo_mode else "Active profile"
            st.caption(f"{label}: {profile_selection_label(person, current_db_path)}")
        # Unconditional, and here rather than in a page: switching profiles while on any other page
        # must still drop the previous profile's condition selection out of session state. Lock state
        # is part of the scope, so locking clears it too.
        locked = person is not None and is_locked_profile(person, current_db_path)
        condition_ui.sync_profile_scope(
            st.session_state, condition_ui.profile_scope(person, current_db_path, locked)
        )
        page = page_navigation(nav_slot)

    if page == "Profiles":
        page_profiles(person, current_db_path, demo_mode=demo_mode)
        return
    if page == "Body Map" and not person:
        page_header("Body Map")
        body_map_ui.render_body_map_page(None, current_db_path)
        return
    if not require_profile(person):
        if page == "Import/Export":
            page_import_export(person, current_db_path, demo_mode=demo_mode)
        return
    if page == "Settings":
        page_header("Settings")
        selected_profile_banner(person, db_path=current_db_path)
        if demo_mode:
            st.info("Profile password settings are not available in demo mode. Exit demo mode to manage saved profiles.")
        else:
            password_settings(person, db_path=current_db_path)
        ai_settings()
        st.info(
            "Future TODO: encryption at rest, audit logging, stronger authentication, family sharing permissions, "
            "provider sharing, consent tracking, SMART-on-FHIR authorization, provider-connected EHR workflows, "
            "production FHIR profiles, PDF export, and mobile interface."
        )
        return
    if not security.health_data_visible(person, db_path=current_db_path):
        unlock_screen(person, db_path=current_db_path)
        return

    selected_profile_banner(person, db_path=current_db_path)

    if page == "Dashboard":
        page_dashboard(person, db_path=current_db_path)
    elif page == "Body Map":
        page_header("Body Map")
        body_map_ui.render_body_map_page(person, db_path=current_db_path)
    elif page == "Import/Export":
        page_import_export(person, current_db_path, demo_mode=demo_mode)
    elif page == "Health Timeline":
        generic_record_page("health_entries", person, current_db_path, demo_mode=demo_mode)
    elif page == "Medications":
        generic_record_page("medications", person, current_db_path, demo_mode=demo_mode)
    elif page == "Allergies":
        generic_record_page("allergies", person, current_db_path, demo_mode=demo_mode)
    elif page == "Labs":
        generic_record_page("lab_results", person, current_db_path, demo_mode=demo_mode)
    elif page == "Appointments":
        generic_record_page("appointments", person, current_db_path, demo_mode=demo_mode)
    elif page == "Reminders":
        generic_record_page("reminders", person, current_db_path, demo_mode=demo_mode)
    elif page == "Wearables":
        generic_record_page("wearable_records", person, current_db_path, demo_mode=demo_mode)
    elif page == "Tracked Conditions":
        page_tracked_conditions(person, current_db_path, demo_mode=demo_mode)
    elif page == "Provider Summary":
        page_provider_summary(person, db_path=current_db_path)
    elif page == "Emergency Snapshot":
        page_emergency_snapshot(person, db_path=current_db_path)
    elif page == "Health Insights":
        page_insights(person, db_path=current_db_path)
    elif page == "AI Chat":
        page_ai_chat(person, db_path=current_db_path)


if __name__ == "__main__":
    main()
