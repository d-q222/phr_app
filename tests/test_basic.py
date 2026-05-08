import sqlite3
import sys
import json
import socket
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db  # noqa: E402
import ai_config  # noqa: E402
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
