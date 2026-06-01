from __future__ import annotations

import json
import tempfile
import uuid
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import ai_chat
import ai_config
import db
import fhir
import imports_exports
import insights
import security
import services
import validation
from models import (
    APPOINTMENT_STATUSES,
    BODY_SYSTEMS,
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
    "Profiles",
    "Health Timeline",
    "Medications",
    "Allergies",
    "Labs",
    "Appointments",
    "Reminders",
    "Wearables",
    "Provider Summary",
    "Emergency Snapshot",
    "Health Insights",
    "AI Chat",
    "Import/Export",
    "Settings",
]

NAV_SECTIONS = {
    "Overview": ["Dashboard", "Health Insights", "AI Chat"],
    "Records": ["Health Timeline", "Medications", "Allergies", "Labs", "Appointments", "Reminders", "Wearables"],
    "Documents": ["Provider Summary", "Emergency Snapshot", "Import/Export"],
    "Admin": ["Profiles", "Settings"],
}

PAGE_DESCRIPTIONS = {
    "Dashboard": "A quick operational view of medications, allergies, labs, reminders, appointments, and recent notes.",
    "Profiles": "Manage family member profiles and local profile access settings.",
    "Health Timeline": "Record symptoms, observations, body systems, and dated health notes.",
    "Medications": "Track current and past medications, dose details, reasons, and notes.",
    "Allergies": "Keep allergy, reaction, and severity information easy to scan.",
    "Labs": "Review lab results, flags, reference ranges, and simple trends.",
    "Appointments": "Track provider visits, status, location, and preparation notes.",
    "Reminders": "Manage follow-up items and routine health tasks.",
    "Wearables": "Import and review manually recorded wearable metrics.",
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
    padding-top: 1.4rem;
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
}


def format_label(name: str) -> str:
    return name.replace("_", " ").title()


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


def selected_profile_banner(person: dict | None) -> None:
    if not person:
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


def page_navigation() -> str:
    section_names = list(NAV_SECTIONS)
    section = st.sidebar.selectbox("Section", section_names, key="nav_section")
    pages = NAV_SECTIONS[section]
    return st.sidebar.selectbox("Page", pages, key=f"nav_page_{section}")


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
        if st.button("Exit demo mode", key="exit_demo_mode"):
            exit_demo_mode()
            st.rerun()
        return
    if st.button("Demo mode", key="start_demo_mode"):
        start_demo_mode()
        st.rerun()


def show_errors(errors: list[str]) -> None:
    for error in errors:
        st.error(error)


def clean_payload(payload: dict) -> dict:
    cleaned = {}
    for key, value in payload.items():
        if value == "":
            cleaned[key] = None
        else:
            cleaned[key] = value
    for key in ["numeric_value", "reference_low", "reference_high"]:
        if key in cleaned:
            cleaned[key] = validation.normalize_optional_number(cleaned[key])
    if "value" in cleaned and not validation.is_blank(cleaned["value"]):
        cleaned["value"] = float(cleaned["value"])
    if "severity" in cleaned and validation.is_blank(cleaned["severity"]):
        cleaned["severity"] = None
    elif "severity" in cleaned:
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


def selected_profile_sidebar(db_path: Path | str = db.DB_PATH, demo_mode: bool = False) -> tuple[str, dict | None]:
    people = services.list_people(db_path=db_path)
    names = [f"{person['name']} (ID {person['id']})" for person in people]
    label = "Demo profile" if demo_mode else "Selected profile"
    key = "demo_selected_profile" if demo_mode else "selected_profile"
    selection = st.sidebar.selectbox(label, names or ["No profile selected"], key=key)
    if not people:
        return selection, None
    index = names.index(selection)
    return selection, people[index]


def unlock_screen(person: dict) -> None:
    st.warning("This profile is password-protected.")
    if person.get("profile_password_hint"):
        st.caption(f"Password hint: {person['profile_password_hint']}")
    password = st.text_input("Password", type="password")
    if st.button("Unlock profile"):
        if security.verify_password(password, person.get("profile_password_hash") or ""):
            security.unlock_profile(int(person["id"]))
            st.rerun()
        st.error("Incorrect password.")


def require_profile(person: dict | None) -> bool:
    if person:
        return True
    st.info("Create a profile before adding health records.")
    return False


def dataframe(rows: list[dict]) -> None:
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("No records yet.")


def toggle_add_form(key: str) -> None:
    st.session_state[key] = not st.session_state.get(key, False)


def close_form(key: str) -> None:
    st.session_state[key] = False


def record_label(row: dict) -> str:
    label = row.get("title") or row.get("name") or row.get("test_name") or row.get("allergen") or row.get("metric_type")
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


def password_settings(person: dict, db_path: Path | str = db.DB_PATH) -> None:
    st.subheader("Profile Password")
    if person.get("profile_password_enabled"):
        st.info("Password protection is enabled for this profile.")
        if st.button("Lock profile"):
            security.lock_profile(int(person["id"]))
            st.rerun()
        if st.button("Remove password"):
            services.update_person(
                int(person["id"]),
                {"profile_password_enabled": 0, "profile_password_hash": None, "profile_password_hint": None},
                db_path=db_path,
            )
            security.unlock_profile(int(person["id"]))
            st.success("Password removed.")
            st.rerun()
    with st.form(f"password_form_{person['id']}"):
        password = st.text_input("Set/change password", type="password")
        hint = st.text_input("Password hint", value=person.get("profile_password_hint") or "")
        submitted = st.form_submit_button("Save password")
        if submitted:
            if not password:
                st.error("Password cannot be blank.")
            else:
                services.update_person(
                    int(person["id"]),
                    {
                        "profile_password_enabled": 1,
                        "profile_password_hash": security.hash_password(password),
                        "profile_password_hint": hint,
                    },
                    db_path=db_path,
                )
                security.lock_profile(int(person["id"]))
                st.success("Password saved. Profile is now locked.")


def ai_settings() -> None:
    st.subheader("Zhipu AI BigModel")
    if ai_config.zhipu_key_configured():
        st.success("Zhipu AI API key is configured.")
    else:
        st.warning("Zhipu AI API key is not configured. AI safety-checked insights will not run.")
    st.caption(f"AI provider: {ai_config.AI_PROVIDER}")
    st.caption(f"Model: {ai_config.ZHIPU_MODEL}")
    st.caption(f"AI Chat model candidates: {', '.join(ai_chat.chat_model_candidates())}")
    st.caption(f"Max response tokens: {ai_config.ZHIPU_MAX_TOKENS}")
    st.caption(f"Max AI context bytes: {ai_config.ZHIPU_CONTEXT_BYTE_LIMIT}")
    st.caption("Default setup uses BigModel's free low-power text model with a compact patient-data packet.")
    with st.form("zhipu_api_key_form"):
        api_key = st.text_input("Zhipu AI API key", type="password")
        submitted = st.form_submit_button("Save API key")
        if submitted:
            ok, message = ai_config.store_zhipu_api_key(api_key)
            if ok:
                st.success(message)
            else:
                st.error(message)
                st.rerun()
    if st.button("Test BigModel API key"):
        ok, message, detail = insights.validate_zhipu_connection()
        if ok:
            st.success(message)
        else:
            st.error(message)
            if detail:
                with st.expander("Provider details"):
                    st.code(detail)


def page_profiles(person: dict | None, db_path: Path | str = db.DB_PATH, demo_mode: bool = False) -> None:
    page_header("Profiles")
    people = services.list_people(db_path=db_path)
    dataframe(people)
    if demo_mode:
        st.info("Demo profiles are loaded from sample data and are separate from your saved profiles. Exit demo mode to manage real profiles.")
        return

    add_profile_key = "show_add_profile_form"
    if add_profile_key not in st.session_state:
        st.session_state[add_profile_key] = False

    if st.button("Add profile", key="toggle_add_profile", on_click=toggle_add_form, args=(add_profile_key,)):
        pass

    if st.session_state[add_profile_key]:
        with st.form("add_profile"):
            data = profile_form(key_prefix="add_profile")
            enable_password = st.checkbox("Enable profile password")
            password = st.text_input("Password", type="password") if enable_password else ""
            hint = st.text_input("Password hint") if enable_password else ""
            submit_col, cancel_col = st.columns([1, 1])
            with submit_col:
                submitted = st.form_submit_button("Create profile")
            with cancel_col:
                cancelled = st.form_submit_button("Cancel")
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
                    services.create_person(clean_payload(data), db_path=db_path)
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
    profile_labels.update({str(row["id"]): record_label(row) for row in people})
    selected_profile_id = st.selectbox(
        "Edit profile",
        profile_options,
        format_func=lambda value: profile_labels[value],
        key=f"edit_profile_selection_{st.session_state[profile_edit_reset_key]}",
    )
    if not selected_profile_id:
        return

    row = next(item for item in people if str(item["id"]) == selected_profile_id)
    with st.form(f"edit_profile_{row['id']}"):
        data = profile_form(row, key_prefix=f"edit_profile_{row['id']}")
        save_col, delete_col, cancel_col = st.columns([1, 1, 1])
        with save_col:
            submitted = st.form_submit_button("Save changes")
        with delete_col:
            deleted = st.form_submit_button("Delete profile")
        with cancel_col:
            cancelled = st.form_submit_button("Cancel")
        if cancelled:
            st.session_state[profile_edit_reset_key] += 1
            st.rerun()
        if deleted:
            services.delete_person(int(row["id"]), db_path=db_path)
            st.warning("Profile deleted.")
            st.session_state[profile_edit_reset_key] += 1
            st.rerun()
        if submitted:
            errors = validation.validate_person(data)
            if errors:
                show_errors(errors)
            else:
                services.update_person(int(row["id"]), clean_payload(data), db_path=db_path)
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


def generic_record_page(table: str, person: dict, db_path: Path | str = db.DB_PATH, demo_mode: bool = False) -> None:
    config = FIELD_CONFIGS[table]
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
        rows = services.filter_health_entries(int(person["id"]), start, end, body_system or None, body_part or None, search or None, db_path=db_path)
    elif table == "lab_results":
        start, end = date_range_controls("labs")
        test_search = st.text_input("Test search")
        flag = st.selectbox("Lab flag", ["", *LAB_FLAGS])
        rows = services.filter_labs(int(person["id"]), start, end, test_search or None, flag or None, db_path=db_path)
    elif table == "medications":
        status = st.selectbox("Medication status", ["", *MEDICATION_STATUSES])
        rows = services.medication_filters(int(person["id"]), status or None, db_path=db_path)
    elif table == "reminders":
        status = st.selectbox("Reminder status", ["", *REMINDER_STATUSES])
        rows = services.reminder_filters(int(person["id"]), status or None, db_path=db_path)
    else:
        rows = services.list_items(table, int(person["id"]), filters, config["order_by"], descending=table not in {"allergies", "medications"}, db_path=db_path)

    dataframe(rows)

    singular_title = SINGULAR_TITLES.get(config["title"], config["title"])
    add_form_key = f"show_add_{table}_form"
    if add_form_key not in st.session_state:
        st.session_state[add_form_key] = False

    if st.button(f"Add {singular_title}", key=f"toggle_add_{table}", on_click=toggle_add_form, args=(add_form_key,)):
        pass

    if st.session_state[add_form_key]:
        with st.form(f"add_{table}"):
            data = {name: input_field(name, kind, key=f"add_{table}_{name}") for name, kind in config["fields"]}
            submit_col, cancel_col = st.columns([1, 1])
            with submit_col:
                submitted = st.form_submit_button("Add record")
            with cancel_col:
                cancelled = st.form_submit_button("Cancel")
            if cancelled:
                close_form(add_form_key)
                st.rerun()
            if submitted:
                errors = config["validator"](data)
                if errors:
                    show_errors(errors)
                else:
                    services.create_item(table, int(person["id"]), clean_payload(data), db_path=db_path)
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
        dataframe(services.wearable_summary(int(person["id"]), db_path=db_path))

    if not rows:
        return

    edit_reset_key = f"edit_{table}_selection_reset"
    if edit_reset_key not in st.session_state:
        st.session_state[edit_reset_key] = 0
    edit_options = [""] + [str(row["id"]) for row in rows]
    edit_labels = {"": "Select a record to edit"}
    edit_labels.update({str(row["id"]): record_label(row) for row in rows})
    selected_record_id = st.selectbox(
        "Edit existing record",
        edit_options,
        format_func=lambda value: edit_labels[value],
        key=f"edit_{table}_selection_{st.session_state[edit_reset_key]}",
    )
    if not selected_record_id:
        return

    row = next(item for item in rows if str(item["id"]) == selected_record_id)
    with st.form(f"edit_{table}_{row['id']}"):
        data = {name: input_field(name, kind, row.get(name), key=f"edit_{table}_{row['id']}_{name}") for name, kind in config["fields"]}
        if table == "reminders":
            save_col, complete_col, dismiss_col, delete_col, cancel_col = st.columns([1, 1, 1, 1, 1])
            with save_col:
                submitted = st.form_submit_button("Save changes")
            with complete_col:
                completed = st.form_submit_button("Mark complete")
            with dismiss_col:
                dismissed = st.form_submit_button("Dismiss")
            with delete_col:
                deleted = st.form_submit_button("Delete")
            with cancel_col:
                cancelled = st.form_submit_button("Cancel")
        else:
            save_col, delete_col, cancel_col = st.columns([1, 1, 1])
            with save_col:
                submitted = st.form_submit_button("Save changes")
            with delete_col:
                deleted = st.form_submit_button("Delete")
            with cancel_col:
                cancelled = st.form_submit_button("Cancel")
            completed = dismissed = False

        if cancelled:
            st.session_state[edit_reset_key] += 1
            st.rerun()
        if completed:
            services.update_item("reminders", int(row["id"]), {"status": "Completed"}, db_path=db_path)
            st.session_state[edit_reset_key] += 1
            st.rerun()
        if dismissed:
            services.update_item("reminders", int(row["id"]), {"status": "Dismissed"}, db_path=db_path)
            st.session_state[edit_reset_key] += 1
            st.rerun()
        if deleted:
            services.delete_item(table, int(row["id"]), db_path=db_path)
            st.warning("Record deleted.")
            st.session_state[edit_reset_key] += 1
            st.rerun()
        if submitted:
            errors = config["validator"](data)
            if errors:
                show_errors(errors)
            else:
                services.update_item(table, int(row["id"]), clean_payload(data), db_path=db_path)
                st.success("Record updated.")
                st.session_state[edit_reset_key] += 1
                st.rerun()


def page_dashboard(person: dict, db_path: Path | str = db.DB_PATH) -> None:
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


def page_provider_summary(person: dict, db_path: Path | str = db.DB_PATH) -> None:
    page_header("Provider Summary")
    start, end = date_range_controls("provider")
    include_labs = st.checkbox("Include labs", value=True)
    include_timeline = st.checkbox("Include health timeline", value=True)
    include_wearables = st.checkbox("Include wearables", value=True)
    markdown = services.generate_provider_summary(int(person["id"]), start, end, include_labs, include_timeline, include_wearables, db_path=db_path)
    st.download_button("Download Markdown", markdown, file_name="provider_summary.md", mime="text/markdown")
    st.markdown(markdown)


def page_emergency_snapshot(person: dict, db_path: Path | str = db.DB_PATH) -> None:
    page_header("Emergency Snapshot")
    markdown = services.generate_emergency_snapshot(int(person["id"]), db_path=db_path)
    st.download_button("Download Markdown", markdown, file_name="emergency_snapshot.md", mime="text/markdown")
    st.markdown(markdown)


def page_import_export(person: dict | None, db_path: Path | str = db.DB_PATH, demo_mode: bool = False) -> None:
    page_header("Import/Export")
    if demo_mode:
        st.caption("Imports and restores in demo mode modify only the session demo database.")
    if person:
        st.subheader("CSV Imports")
        labs_file = st.file_uploader("Import labs CSV", type=["csv"])
        if labs_file and st.button("Import labs"):
            st.write(imports_exports.import_labs_csv(labs_file, int(person["id"]), db_path=db_path))
        wearable_file = st.file_uploader("Import wearables CSV", type=["csv"])
        if wearable_file and st.button("Import wearables"):
            st.write(imports_exports.import_wearables_csv(wearable_file, int(person["id"]), db_path=db_path))
        st.download_button("Download sample labs CSV", imports_exports.sample_labs_csv(), "sample_labs.csv", "text/csv")
        st.download_button("Download sample wearables CSV", imports_exports.sample_wearables_csv(), "sample_wearables.csv", "text/csv")

    st.subheader("FHIR Interoperability")
    fhir_version = st.selectbox("FHIR version", fhir.SUPPORTED_FHIR_VERSIONS, key="fhir_version")
    export_scope = "All profiles"
    if person:
        export_scope = st.selectbox("FHIR export scope", ["Selected profile", "All profiles"], key="fhir_export_scope")
    export_person_id = int(person["id"]) if person and export_scope == "Selected profile" else None
    fhir_bundle = imports_exports.export_fhir_bundle(fhir_version, person_id=export_person_id, db_path=db_path)
    st.download_button(
        f"Export FHIR {fhir_version} Bundle",
        fhir_bundle,
        file_name=f"phr_fhir_{fhir_version.lower()}_bundle.json",
        mime=fhir.FHIR_MIME_TYPE,
    )
    fhir_file = st.file_uploader("Import FHIR Bundle", type=["json"], key="fhir_bundle_upload")
    clear_existing_fhir = st.checkbox("Clear existing records before FHIR import", key="fhir_clear_existing")
    if fhir_file and st.button("Import FHIR Bundle"):
        result = imports_exports.import_fhir_bundle(fhir_file.read().decode("utf-8"), clear_existing=clear_existing_fhir, db_path=db_path)
        st.write(result)
        st.success("FHIR import completed.")
        st.rerun()

    st.subheader("JSON Backup")
    backup = imports_exports.export_json_backup(db_path=db_path)
    st.download_button("Export JSON backup", backup, "phr_backup.json", "application/json")
    backup_file = st.file_uploader("Restore JSON backup", type=["json"])
    clear_existing = st.checkbox("Clear existing records before restore")
    if backup_file and st.button("Restore backup"):
        imports_exports.import_json_backup(backup_file.read().decode("utf-8"), clear_existing=clear_existing, db_path=db_path)
        st.success("Backup restored.")
        st.rerun()


def page_insights(person: dict, db_path: Path | str = db.DB_PATH) -> None:
    page_header("Health Insights")
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
    if st.button("Generate rule-based report"):
        st.markdown(insights.generate_rule_based_insights(context, focus_area))
    if st.button("Generate AI safety-checked insights"):
        result = insights.generate_ai_insight_result(context, focus_area)
        if result.get("warning"):
            st.warning(result["warning"])
            if result.get("provider_details"):
                with st.expander("Provider details"):
                    st.code(result["provider_details"])
        st.markdown(result["report"])


def page_ai_chat(person: dict, db_path: Path | str = db.DB_PATH) -> None:
    page_header("AI Health Assistant", PAGE_DESCRIPTIONS["AI Chat"])
    ai_chat.render_ai_chatbot(int(person["id"]), db_path=db_path)


def main() -> None:
    st.set_page_config(page_title="Family Personal Health Record", page_icon="PHR", layout="wide")
    apply_global_styles()
    db.init_db()

    with st.sidebar:
        st.markdown("### Family PHR")
        st.caption("Local-first private prototype")
        st.divider()
        demo_mode_controls()
        st.divider()
        page = page_navigation()
        st.divider()
        demo_mode = is_demo_mode()
        current_db_path = active_db_path()
        _, person = selected_profile_sidebar(current_db_path, demo_mode=demo_mode)
        if person:
            label = "Demo profile" if demo_mode else "Active profile"
            st.caption(f"{label}: {person['name']}")

    if page == "Profiles":
        page_profiles(person, current_db_path, demo_mode=demo_mode)
        return
    if not require_profile(person):
        if page == "Import/Export":
            page_import_export(person, current_db_path, demo_mode=demo_mode)
        return
    if page == "Settings":
        page_header("Settings")
        selected_profile_banner(person)
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
    if not security.health_data_visible(person):
        unlock_screen(person)
        return

    selected_profile_banner(person)

    if page == "Dashboard":
        page_dashboard(person, db_path=current_db_path)
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
