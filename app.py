from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

import ai_config
import db
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
    "Import/Export",
    "Settings",
]

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


def selected_profile_sidebar() -> tuple[str, dict | None]:
    people = services.list_people()
    names = [f"{person['name']} (ID {person['id']})" for person in people]
    selection = st.sidebar.selectbox("Selected profile", names or ["No profile selected"])
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
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No records yet.")


def profile_form(existing: dict | None = None, key_prefix: str = "profile") -> dict:
    return {
        "name": st.text_input("Name", value=(existing or {}).get("name") or "", key=f"{key_prefix}_name"),
        "date_of_birth": st.text_input("Date of birth", value=(existing or {}).get("date_of_birth") or "", key=f"{key_prefix}_dob"),
        "sex": st.text_input("Sex", value=(existing or {}).get("sex") or "", key=f"{key_prefix}_sex"),
        "relationship": st.text_input("Relationship", value=(existing or {}).get("relationship") or "", key=f"{key_prefix}_relationship"),
        "emergency_contact": st.text_input("Emergency contact", value=(existing or {}).get("emergency_contact") or "", key=f"{key_prefix}_emergency"),
        "notes": st.text_area("Notes", value=(existing or {}).get("notes") or "", key=f"{key_prefix}_notes"),
    }


def password_settings(person: dict) -> None:
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


def page_profiles(person: dict | None) -> None:
    st.header("Profiles")
    with st.expander("Add profile", expanded=not bool(person)):
        with st.form("add_profile"):
            data = profile_form(key_prefix="add_profile")
            enable_password = st.checkbox("Enable profile password")
            password = st.text_input("Password", type="password") if enable_password else ""
            hint = st.text_input("Password hint") if enable_password else ""
            if st.form_submit_button("Create profile"):
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
                    services.create_person(clean_payload(data))
                    st.success("Profile created.")
                    st.rerun()

    people = services.list_people()
    dataframe(people)
    for row in people:
        with st.expander(f"Edit {row['name']}"):
            with st.form(f"edit_profile_{row['id']}"):
                data = profile_form(row, key_prefix=f"edit_profile_{row['id']}")
                submitted = st.form_submit_button("Save changes")
                if submitted:
                    errors = validation.validate_person(data)
                    if errors:
                        show_errors(errors)
                    else:
                        services.update_person(int(row["id"]), clean_payload(data))
                        st.success("Profile updated.")
                        st.rerun()
            if st.button("Delete profile", key=f"delete_profile_{row['id']}"):
                services.delete_person(int(row["id"]))
                st.warning("Profile deleted.")
                st.rerun()
            password_settings(row)


def date_range_controls(prefix: str) -> tuple[str | None, str | None]:
    cols = st.columns(2)
    with cols[0]:
        start = st.text_input("Start date", value="", key=f"{prefix}_start")
    with cols[1]:
        end = st.text_input("End date", value="", key=f"{prefix}_end")
    return start or None, end or None


def generic_record_page(table: str, person: dict) -> None:
    config = FIELD_CONFIGS[table]
    st.header(config["title"])

    with st.expander(f"Add {config['title'][:-1] if config['title'].endswith('s') else config['title']}", expanded=True):
        with st.form(f"add_{table}"):
            data = {name: input_field(name, kind, key=f"add_{table}_{name}") for name, kind in config["fields"]}
            if st.form_submit_button("Add record"):
                errors = config["validator"](data)
                if errors:
                    show_errors(errors)
                else:
                    services.create_item(table, int(person["id"]), clean_payload(data))
                    st.success("Record added.")
                    st.rerun()

    filters = {}
    start = end = None
    if table == "health_entries":
        start, end = date_range_controls("timeline")
        body_system = st.selectbox("Body system", ["", *BODY_SYSTEMS])
        body_part = st.text_input("Body part")
        search = st.text_input("Search title/notes")
        rows = services.filter_health_entries(int(person["id"]), start, end, body_system or None, body_part or None, search or None)
    elif table == "lab_results":
        start, end = date_range_controls("labs")
        test_search = st.text_input("Test search")
        flag = st.selectbox("Lab flag", ["", *LAB_FLAGS])
        rows = services.filter_labs(int(person["id"]), start, end, test_search or None, flag or None)
    elif table == "medications":
        status = st.selectbox("Medication status", ["", *MEDICATION_STATUSES])
        rows = services.medication_filters(int(person["id"]), status or None)
    elif table == "reminders":
        status = st.selectbox("Reminder status", ["", *REMINDER_STATUSES])
        rows = services.reminder_filters(int(person["id"]), status or None)
    else:
        rows = services.list_items(table, int(person["id"]), filters, config["order_by"], descending=table not in {"allergies", "medications"})

    dataframe(rows)

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
        dataframe(services.wearable_summary(int(person["id"])))

    for row in rows:
        label = row.get("title") or row.get("name") or row.get("test_name") or row.get("allergen") or row.get("metric_type") or f"Record {row['id']}"
        with st.expander(f"Edit {label}"):
            with st.form(f"edit_{table}_{row['id']}"):
                data = {name: input_field(name, kind, row.get(name), key=f"edit_{table}_{row['id']}_{name}") for name, kind in config["fields"]}
                if st.form_submit_button("Save changes"):
                    errors = config["validator"](data)
                    if errors:
                        show_errors(errors)
                    else:
                        services.update_item(table, int(row["id"]), clean_payload(data))
                        st.success("Record updated.")
                        st.rerun()
            cols = st.columns(3)
            if table == "reminders":
                with cols[0]:
                    if st.button("Mark complete", key=f"complete_{row['id']}"):
                        services.update_item("reminders", int(row["id"]), {"status": "Completed"})
                        st.rerun()
                with cols[1]:
                    if st.button("Dismiss", key=f"dismiss_{row['id']}"):
                        services.update_item("reminders", int(row["id"]), {"status": "Dismissed"})
                        st.rerun()
            with cols[-1]:
                if st.button("Delete", key=f"delete_{table}_{row['id']}"):
                    services.delete_item(table, int(row["id"]))
                    st.warning("Record deleted.")
                    st.rerun()


def page_dashboard(person: dict) -> None:
    st.header("Dashboard")
    data = services.dashboard_data(int(person["id"]))
    st.subheader(data["person"]["name"])
    st.write(data["person"].get("notes") or "No profile notes.")
    cols = st.columns(4)
    cols[0].metric("Active medications", len(data["active_medications"]))
    cols[1].metric("Allergies", len(data["allergies"]))
    cols[2].metric("Latest labs", len(data["latest_labs"]))
    cols[3].metric("Overdue reminders", len(data["overdue_reminders"]))
    for title, rows in [
        ("Allergies", data["allergies"]),
        ("Active Medications", data["active_medications"]),
        ("Latest Labs", data["latest_labs"]),
        ("Recent Health Timeline", data["recent_entries"]),
        ("Upcoming Appointments", data["upcoming_appointments"]),
        ("Overdue Reminders", data["overdue_reminders"]),
        ("Recent Wearable Summary", data["wearable_summary"]),
    ]:
        st.subheader(title)
        dataframe(rows)


def page_provider_summary(person: dict) -> None:
    st.header("Provider Summary")
    start, end = date_range_controls("provider")
    include_labs = st.checkbox("Include labs", value=True)
    include_timeline = st.checkbox("Include health timeline", value=True)
    include_wearables = st.checkbox("Include wearables", value=True)
    markdown = services.generate_provider_summary(int(person["id"]), start, end, include_labs, include_timeline, include_wearables)
    st.download_button("Download Markdown", markdown, file_name="provider_summary.md", mime="text/markdown")
    st.markdown(markdown)


def page_emergency_snapshot(person: dict) -> None:
    st.header("Emergency Snapshot")
    markdown = services.generate_emergency_snapshot(int(person["id"]))
    st.download_button("Download Markdown", markdown, file_name="emergency_snapshot.md", mime="text/markdown")
    st.markdown(markdown)


def page_import_export(person: dict | None) -> None:
    st.header("Import/Export")
    if person:
        st.subheader("CSV Imports")
        labs_file = st.file_uploader("Import labs CSV", type=["csv"])
        if labs_file and st.button("Import labs"):
            st.write(imports_exports.import_labs_csv(labs_file, int(person["id"])))
        wearable_file = st.file_uploader("Import wearables CSV", type=["csv"])
        if wearable_file and st.button("Import wearables"):
            st.write(imports_exports.import_wearables_csv(wearable_file, int(person["id"])))
        st.download_button("Download sample labs CSV", imports_exports.sample_labs_csv(), "sample_labs.csv", "text/csv")
        st.download_button("Download sample wearables CSV", imports_exports.sample_wearables_csv(), "sample_wearables.csv", "text/csv")
    st.subheader("JSON Backup")
    backup = imports_exports.export_json_backup()
    st.download_button("Export JSON backup", backup, "phr_backup.json", "application/json")
    backup_file = st.file_uploader("Restore JSON backup", type=["json"])
    clear_existing = st.checkbox("Clear existing records before restore")
    if backup_file and st.button("Restore backup"):
        imports_exports.import_json_backup(backup_file.read().decode("utf-8"), clear_existing=clear_existing)
        st.success("Backup restored.")
        st.rerun()


def page_insights(person: dict) -> None:
    st.header("Health Insights")
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


def main() -> None:
    st.set_page_config(page_title="Family Personal Health Record", page_icon="PHR", layout="wide")
    db.init_db()
    st.title("Family Personal Health Record")
    st.caption("Local-first private prototype")

    with st.sidebar:
        st.header("Navigation")
        page = st.radio("Page", PAGES)
        st.divider()
        _, person = selected_profile_sidebar()

    if page == "Profiles":
        page_profiles(person)
        return
    if not require_profile(person):
        if page == "Import/Export":
            page_import_export(person)
        return
    if page == "Settings":
        st.header("Settings")
        password_settings(person)
        ai_settings()
        st.info("Future TODO: encryption at rest, audit logging, stronger authentication, family sharing permissions, provider sharing, consent tracking, and FHIR/SMART integration.")
        return
    if not security.health_data_visible(person):
        unlock_screen(person)
        return

    if page == "Dashboard":
        page_dashboard(person)
    elif page == "Import/Export":
        page_import_export(person)
    elif page == "Health Timeline":
        generic_record_page("health_entries", person)
    elif page == "Medications":
        generic_record_page("medications", person)
    elif page == "Allergies":
        generic_record_page("allergies", person)
    elif page == "Labs":
        generic_record_page("lab_results", person)
    elif page == "Appointments":
        generic_record_page("appointments", person)
    elif page == "Reminders":
        generic_record_page("reminders", person)
    elif page == "Wearables":
        generic_record_page("wearable_records", person)
    elif page == "Provider Summary":
        page_provider_summary(person)
    elif page == "Emergency Snapshot":
        page_emergency_snapshot(person)
    elif page == "Health Insights":
        page_insights(person)


if __name__ == "__main__":
    main()
