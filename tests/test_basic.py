import sqlite3
import sys
import json
import socket
import urllib.error
from io import BytesIO, StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db  # noqa: E402
import ai_chat  # noqa: E402
import ai_config  # noqa: E402
import app  # noqa: E402
import fhir  # noqa: E402
import imports_exports  # noqa: E402
import insights  # noqa: E402
import security  # noqa: E402
import services  # noqa: E402


def test_database_initializes(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    assert db_path.exists()
    with sqlite3.connect(db_path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert {
        "people",
        "allergies",
        "medications",
        "lab_results",
        "health_entries",
        "appointments",
        "reminders",
        "wearable_records",
    }.issubset(table_names)


def test_default_zhipu_setup_uses_compact_free_model():
    assert ai_config.ZHIPU_MODEL == "glm-4.5-flash"
    assert "glm-4.7-flash" in ai_config.zhipu_model_candidates()
    assert ai_config.ZHIPU_MAX_TOKENS <= 220
    assert ai_config.ZHIPU_CONTEXT_BYTE_LIMIT <= 1200


def test_display_dataframe_uses_readable_column_titles_and_hides_internal_fields():
    rows = [
        {
            "id": 1,
            "person_id": 2,
            "date_of_birth": "1990-01-02",
            "profile_password_hash": "secret-hash",
            "lab_date": "2026-01-01",
            "result_value": "5.5",
            "created_at": "2026-06-01T17:24:30",
            "updated_at": "2026-06-01T17:30:00",
        }
    ]

    frame = app.display_dataframe(rows)

    assert list(frame.columns) == ["ID", "Date of Birth", "Lab Date", "Result", "Created", "Updated"]
    assert frame.loc[0, "Date of Birth"] == "Jan 2, 1990"
    assert frame.loc[0, "Lab Date"] == "Jan 1, 2026"
    assert frame.loc[0, "Created"] == "5:24 PM, Jun 1, 2026"
    assert frame.loc[0, "Updated"] == "5:30 PM, Jun 1, 2026"
    assert rows[0]["created_at"] == "2026-06-01T17:24:30"


def test_display_dataframe_keeps_unparseable_dates_unchanged():
    frame = app.display_dataframe(
        [
            {
                "id": 1,
                "timestamp": "not-a-date",
                "latest_timestamp": "2026-02-03",
            }
        ]
    )

    assert frame.loc[0, "Timestamp"] == "not-a-date"
    assert frame.loc[0, "Latest Timestamp"] == "Feb 3, 2026"


def test_person_medication_active_filter_lab_latest_password_reminder_insights_backup_and_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_config, "AI_PROVIDER", "none")
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)

    person_id = services.create_person({"name": "Test Person"}, db_path=db_path)
    person = services.get_person(person_id, db_path=db_path)
    assert person["name"] == "Test Person"

    services.create_item(
        "medications",
        person_id,
        {"name": "Med A", "status": "Active", "dose": "10 mg"},
        db_path=db_path,
    )
    services.create_item(
        "medications",
        person_id,
        {"name": "Med B", "status": "Stopped"},
        db_path=db_path,
    )
    active = services.active_medications(person_id, db_path=db_path)
    assert [row["name"] for row in active] == ["Med A"]

    services.create_item(
        "lab_results",
        person_id,
        {
            "test_name": "A1c",
            "result_value": "5.5",
            "numeric_value": 5.5,
            "flag": "Normal",
            "lab_date": "2026-01-01",
        },
        db_path=db_path,
    )
    services.create_item(
        "lab_results",
        person_id,
        {
            "test_name": "A1c",
            "result_value": "6.0",
            "numeric_value": 6.0,
            "flag": "High",
            "lab_date": "2026-02-01",
        },
        db_path=db_path,
    )
    latest = services.latest_labs(person_id, db_path=db_path)
    assert len(latest) == 1
    assert latest[0]["result_value"] == "6.0"

    stored_hash = security.hash_password("secret")
    assert security.verify_password("secret", stored_hash)
    assert not security.verify_password("wrong", stored_hash)
    assert not security.health_data_visible({"id": person_id, "profile_password_enabled": 1}, unlocked=False)

    services.create_item(
        "reminders",
        person_id,
        {"reminder_type": "Lab", "title": "Repeat test", "due_date": "2020-01-01", "status": "Upcoming"},
        db_path=db_path,
    )
    assert services.overdue_reminders(person_id, db_path=db_path)[0]["title"] == "Repeat test"

    context = insights.collect_health_context(
        person_id,
        None,
        include_appointments=False,
        include_wearables=False,
    )
    report = insights.generate_rule_based_insights(context)
    assert "Health Insights Report" in report
    assert insights.DISCLAIMER in report

    ai_packet = insights.compact_context_for_ai(context)
    assert "active_medications" in ai_packet
    assert "recent_abnormal_labs" in ai_packet
    assert "medications" not in ai_packet
    assert all("test_name" in lab for lab in ai_packet["recent_abnormal_labs"])
    assert insights._json_size(ai_packet) <= ai_config.ZHIPU_CONTEXT_BYTE_LIMIT

    ai_result = insights.generate_ai_insight_result(context)
    assert ai_result["used_fallback"] is True
    assert "Health Insights Report" in ai_result["report"]

    backup = imports_exports.export_json_backup(db_path=db_path)
    assert '"people"' in backup
    assert '"medications"' in backup

    csv_text = (
        "test_name,result_value,numeric_value,unit,reference_low,reference_high,flag,lab_date,notes\n"
        "LDL,120,120,mg/dL,0,100,High,2026-03-01,\n"
    )
    result = imports_exports.import_labs_csv(StringIO(csv_text), person_id, db_path=db_path)
    assert result["imported"] == 1
    assert result["skipped"] == []


def test_demo_database_loads_sample_data_without_touching_real_profiles(tmp_path):
    real_db_path = tmp_path / "real.db"
    demo_db_path = tmp_path / "demo.db"
    db.init_db(real_db_path)
    real_person_id = services.create_person({"name": "Real Person"}, db_path=real_db_path)

    first_demo_id = app.create_demo_database(demo_db_path)

    real_people = services.list_people(db_path=real_db_path)
    demo_people = services.list_people(db_path=demo_db_path)
    demo_labs = services.list_items("lab_results", int(first_demo_id), db_path=demo_db_path)
    demo_context = insights.collect_health_context(int(first_demo_id), None, db_path=demo_db_path)

    assert [person["id"] for person in real_people] == [real_person_id]
    assert [person["name"] for person in real_people] == ["Real Person"]
    assert [person["name"] for person in demo_people] == ["Alex Rivera", "Maya Rivera"]
    assert demo_labs
    assert demo_context["person"]["name"] == "Alex Rivera"
    assert services.list_items("lab_results", real_person_id, db_path=real_db_path) == []


def test_fhir_r4_and_r5_export_and_import_round_trip(tmp_path):
    source_db_path = tmp_path / "source.db"
    target_db_path = tmp_path / "target.db"
    db.init_db(source_db_path)
    db.init_db(target_db_path)
    person_id = services.create_person(
        {
            "name": "FHIR Person",
            "date_of_birth": "1990-01-02",
            "sex": "Female",
            "relationship": "Self",
            "emergency_contact": "FHIR Contact",
        },
        db_path=source_db_path,
    )
    services.create_item("allergies", person_id, {"allergen": "Peanuts", "reaction": "Hives", "severity": "Moderate"}, db_path=source_db_path)
    services.create_item(
        "medications",
        person_id,
        {"name": "Med A", "dose": "10 mg", "frequency": "Daily", "status": "Active", "start_date": "2026-01-01"},
        db_path=source_db_path,
    )
    services.create_item(
        "lab_results",
        person_id,
        {"test_name": "LDL", "numeric_value": 120, "unit": "mg/dL", "flag": "High", "lab_date": "2026-02-01"},
        db_path=source_db_path,
    )
    services.create_item(
        "health_entries",
        person_id,
        {"entry_date": "2026-02-03", "title": "Headache", "body_system": "Neurologic", "severity": 4, "note": "Mild afternoon headache."},
        db_path=source_db_path,
    )
    services.create_item(
        "appointments",
        person_id,
        {"appointment_date": "2026-02-04", "title": "Primary care follow-up", "provider": "Dr. Example", "status": "Scheduled"},
        db_path=source_db_path,
    )
    services.create_item(
        "reminders",
        person_id,
        {"reminder_type": "Lab", "title": "Repeat LDL", "due_date": "2026-03-01", "status": "Upcoming"},
        db_path=source_db_path,
    )
    services.create_item(
        "wearable_records",
        person_id,
        {"metric_type": "Steps", "value": 7500, "unit": "steps", "timestamp": "2026-02-02", "source": "Manual"},
        db_path=source_db_path,
    )

    r4_bundle = json.loads(fhir.export_bundle("R4", db_path=source_db_path))
    r5_bundle = json.loads(fhir.export_bundle("R5", db_path=source_db_path))
    r4_medication = next(entry["resource"] for entry in r4_bundle["entry"] if entry["resource"]["resourceType"] == "MedicationStatement")
    r5_medication = next(entry["resource"] for entry in r5_bundle["entry"] if entry["resource"]["resourceType"] == "MedicationStatement")

    assert r4_bundle["resourceType"] == "Bundle"
    assert r5_bundle["resourceType"] == "Bundle"
    assert r4_medication["medicationCodeableConcept"]["text"] == "Med A"
    assert r5_medication["medication"]["concept"]["text"] == "Med A"

    patient_full_url = next(entry["fullUrl"] for entry in r5_bundle["entry"] if entry["resource"]["resourceType"] == "Patient")
    for entry in r5_bundle["entry"]:
        resource = entry["resource"]
        for key in ["patient", "subject", "for"]:
            if resource.get(key, {}).get("reference"):
                resource[key]["reference"] = patient_full_url

    result = fhir.import_bundle(json.dumps(r5_bundle), db_path=target_db_path)
    imported_person = services.list_people(db_path=target_db_path)[0]

    assert result["skipped"] == []
    assert imported_person["name"] == "FHIR Person"
    assert services.list_items("allergies", int(imported_person["id"]), db_path=target_db_path)[0]["allergen"] == "Peanuts"
    assert services.list_items("medications", int(imported_person["id"]), db_path=target_db_path)[0]["name"] == "Med A"
    assert services.list_items("lab_results", int(imported_person["id"]), db_path=target_db_path)[0]["test_name"] == "LDL"
    assert services.list_items("health_entries", int(imported_person["id"]), db_path=target_db_path)[0]["title"] == "Headache"
    assert services.list_items("appointments", int(imported_person["id"]), db_path=target_db_path)[0]["title"] == "Primary care follow-up"
    assert services.list_items("reminders", int(imported_person["id"]), db_path=target_db_path)[0]["title"] == "Repeat LDL"
    assert services.list_items("wearable_records", int(imported_person["id"]), db_path=target_db_path)[0]["metric_type"] == "Steps"


def test_ai_insight_prompt_requires_safe_unobtrusive_suggestions(monkeypatch):
    captured = {}

    monkeypatch.setattr(ai_config, "AI_PROVIDER", "zhipu")
    monkeypatch.setattr(ai_config, "get_zhipu_api_key", lambda: "test-key")

    def fake_call(request):
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return {"choices": [{"message": {"content": "# AI Safety-Checked Insights\n\n- Consider tracking symptoms."}}]}

    monkeypatch.setattr(insights, "_call_zhipu_chat_completion", fake_call)

    result = insights.generate_ai_insight_result(
        {
            "person": {"relationship": "Self"},
            "medications": [{"name": "Med A", "status": "Active"}],
            "allergies": [],
            "labs": [{"test_name": "A1c", "flag": "High", "result_value": "6.0", "lab_date": "2026-02-01"}],
            "health_entries": [{"entry_date": "2026-02-02", "title": "Headache", "body_system": "Neurologic"}],
            "appointments": [],
            "reminders": [],
            "wearables": [],
        }
    )

    assert result["used_fallback"] is False
    assert captured["body"]["model"] == ai_config.ZHIPU_MODEL
    system_message = captured["body"]["messages"][0]["content"]
    user_prompt = json.loads(captured["body"]["messages"][1]["content"])
    safety_rules = " ".join(user_prompt["safety_rules"])
    assert "non-diagnostic insights" in system_message
    assert "Do not diagnose" in safety_rules
    assert "Do not prescribe, stop, start, or change medications or supplements." in safety_rules
    assert "safe low-risk actions" in user_prompt["task"]


def test_ai_insight_retries_next_model_on_429(monkeypatch):
    seen_models = []

    monkeypatch.setattr(ai_config, "AI_PROVIDER", "zhipu")
    monkeypatch.setattr(ai_config, "ZHIPU_MODEL", "busy-model")
    monkeypatch.setattr(ai_config, "ZHIPU_FALLBACK_MODELS", "working-model")
    monkeypatch.setattr(ai_config, "get_zhipu_api_key", lambda: "test-key")

    def fake_call(request):
        model = json.loads(request.data.decode("utf-8"))["model"]
        seen_models.append(model)
        if model == "busy-model":
            raise insights.ZhipuAPIError(429, "1305", "model is busy")
        return {"choices": [{"message": {"content": "# AI Safety-Checked Insights\n\n- Consider tracking symptoms."}}]}

    monkeypatch.setattr(insights, "_call_zhipu_chat_completion", fake_call)

    result = insights.generate_ai_insight_result({"person": {}, "medications": [], "labs": []})

    assert result["used_fallback"] is False
    assert seen_models == ["busy-model", "working-model"]
    assert "fallback model working-model" in result["warning"]


def test_ai_insight_retries_next_model_on_timeout(monkeypatch):
    seen_models = []

    monkeypatch.setattr(ai_config, "AI_PROVIDER", "zhipu")
    monkeypatch.setattr(ai_config, "ZHIPU_MODEL", "timeout-model")
    monkeypatch.setattr(ai_config, "ZHIPU_FALLBACK_MODELS", "working-model")
    monkeypatch.setattr(ai_config, "get_zhipu_api_key", lambda: "test-key")

    def fake_call(request):
        model = json.loads(request.data.decode("utf-8"))["model"]
        seen_models.append(model)
        if model == "timeout-model":
            raise insights.ZhipuRetryableError(str(socket.timeout("The read operation timed out")))
        return {"choices": [{"message": {"content": "# AI Safety-Checked Insights\n\n- Consider tracking symptoms."}}]}

    monkeypatch.setattr(insights, "_call_zhipu_chat_completion", fake_call)

    result = insights.generate_ai_insight_result({"person": {}, "medications": [], "labs": []})

    assert result["used_fallback"] is False
    assert seen_models == ["timeout-model", "working-model"]
    assert "fallback model working-model" in result["warning"]


def test_ai_chat_context_is_scoped_to_selected_person(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    selected_id = services.create_person({"name": "Selected Person", "sex": "Female", "relationship": "Self"}, db_path=db_path)
    other_id = services.create_person({"name": "Other Person", "sex": "Male", "relationship": "Child"}, db_path=db_path)

    services.create_item("allergies", selected_id, {"allergen": "Penicillin", "reaction": "Rash", "severity": "Moderate"}, db_path=db_path)
    services.create_item("allergies", other_id, {"allergen": "Peanuts", "reaction": "Hives", "severity": "Severe"}, db_path=db_path)
    services.create_item("medications", selected_id, {"name": "Selected Med", "status": "Active", "dose": "10 mg"}, db_path=db_path)
    services.create_item("medications", other_id, {"name": "Other Med", "status": "Active", "dose": "5 mg"}, db_path=db_path)
    services.create_item(
        "lab_results",
        selected_id,
        {"test_name": "A1c", "result_value": "6.0", "flag": "High", "lab_date": "2026-05-01"},
        db_path=db_path,
    )
    services.create_item(
        "health_entries",
        selected_id,
        {"entry_date": "2026-05-02", "title": "Headache", "body_system": "Neurologic", "note": "Afternoon headache."},
        db_path=db_path,
    )
    services.create_item("appointments", selected_id, {"appointment_date": "2099-01-01", "title": "Checkup", "provider": "Dr. Test"}, db_path=db_path)
    services.create_item("reminders", selected_id, {"reminder_type": "Lab", "title": "Repeat A1c", "due_date": "2020-01-01", "status": "Upcoming"}, db_path=db_path)

    context_text = ai_chat.build_patient_context(selected_id, db_path=db_path)
    context = json.loads(context_text)

    assert context["basic_profile"]["name"] == "Selected Person"
    assert context["allergies"][0]["allergen"] == "Penicillin"
    assert context["active_medications"][0]["name"] == "Selected Med"
    assert context["recent_labs"][0]["test_name"] == "A1c"
    assert context["recent_health_entries"][0]["title"] == "Headache"
    assert context["appointments"][0]["title"] == "Checkup"
    assert context["overdue_reminders"][0]["title"] == "Repeat A1c"
    assert "Other Person" not in context_text
    assert "Other Med" not in context_text
    assert "Peanuts" not in context_text


def test_ai_chat_api_key_prefers_streamlit_secret_then_env(monkeypatch):
    monkeypatch.setattr(ai_chat, "_streamlit_secret", lambda name: "secret-key" if name == "ZAI_API_KEY" else None)
    monkeypatch.setenv("ZAI_API_KEY", "env-key")
    assert ai_chat.get_zhipu_api_key() == "secret-key"

    monkeypatch.setattr(ai_chat, "_streamlit_secret", lambda name: None)
    assert ai_chat.get_zhipu_api_key() == "env-key"


def test_ai_chat_prompt_and_call_defaults(monkeypatch):
    captured = {}

    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.delenv("ZHIPU_CHAT_MODEL", raising=False)
    monkeypatch.delenv("ZHIPU_CHAT_FALLBACK_MODELS", raising=False)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "Chat answer"}}]}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(ai_chat.urllib.request, "urlopen", fake_urlopen)

    answer = ai_chat.call_zhipu_chat([{"role": "user", "content": "Summarize my recent labs."}])

    assert answer == "Chat answer"
    assert captured["body"]["model"] == "glm-5.1"
    assert captured["body"]["temperature"] == 0.3
    assert captured["body"]["max_tokens"] == 1200
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert "You are not a doctor" in ai_chat.build_ai_system_prompt()
    assert "Use only the selected patient context" in ai_chat.build_ai_system_prompt()


def test_ai_chat_handles_rate_limit(monkeypatch):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "busy-model")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "")

    def fake_urlopen(request, timeout):
        body = BytesIO(json.dumps({"error": {"code": "1305", "message": "model is busy"}}).encode("utf-8"))
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", hdrs=None, fp=body)

    monkeypatch.setattr(ai_chat.urllib.request, "urlopen", fake_urlopen)

    try:
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])
    except ai_chat.RateLimitError as exc:
        assert "could not complete" in exc.message
        assert "model is busy" in (exc.detail or "")
    else:
        raise AssertionError("Expected RateLimitError")


def test_ai_chat_falls_back_when_primary_model_has_no_resource_package(monkeypatch):
    seen_models = []

    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "glm-5.1")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "glm-4.5-flash")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "Fallback answer"}}]}).encode("utf-8")

    def fake_urlopen(request, timeout):
        model = json.loads(request.data.decode("utf-8"))["model"]
        seen_models.append(model)
        if model == "glm-5.1":
            body = BytesIO(json.dumps({"error": {"code": "1113", "message": "no resource package"}}).encode("utf-8"))
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", hdrs=None, fp=body)
        return FakeResponse()

    monkeypatch.setattr(ai_chat.urllib.request, "urlopen", fake_urlopen)

    answer = ai_chat.call_zhipu_chat([{"role": "user", "content": "Summarize labs"}])

    assert answer == "Fallback answer"
    assert seen_models == ["glm-5.1", "glm-4.5-flash"]
