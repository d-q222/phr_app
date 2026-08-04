import http.client
import inspect
import json
import sqlite3
import sys
import time
import urllib.error
from io import BytesIO, StringIO
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ai_chat  # noqa: E402
import ai_config  # noqa: E402
import app  # noqa: E402
import body_map_services  # noqa: E402
import db  # noqa: E402
import fhir  # noqa: E402
import imports_exports  # noqa: E402
import insights  # noqa: E402
import security  # noqa: E402
import services  # noqa: E402
import validation  # noqa: E402

CHILD_TABLE_SEEDS = {
    "allergies": {"allergen": "Peanuts", "severity": "Severe"},
    "medications": {"name": "Med A"},
    "lab_results": {"test_name": "A1c", "lab_date": "2026-01-01"},
    "health_entries": {"title": "Headache", "entry_date": "2026-01-01"},
    "appointments": {"title": "Checkup", "appointment_date": "2026-01-01"},
    "reminders": {"reminder_type": "Lab", "title": "Draw", "due_date": "2026-01-01"},
    "wearable_records": {
        "metric_type": "Steps",
        "value": 100,
        "timestamp": "2026-01-01T08:00:00",
    },
    "conditions": {"condition_name": "Asthma"},
}


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
        index_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
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
    assert {
        "idx_lab_results_person_date",
        "idx_health_entries_person_date",
        "idx_reminders_person_due_status",
        "idx_wearable_records_person_timestamp",
    }.issubset(index_names)


def test_default_zhipu_setup_uses_compact_free_model():
    assert ai_config.ZHIPU_MODEL == "glm-4.5-flash"
    assert "glm-4.7-flash" in ai_config.zhipu_model_candidates()
    assert ai_config.ZHIPU_MAX_TOKENS <= 220
    assert ai_config.ZHIPU_CONTEXT_BYTE_LIMIT <= 1200


def test_zhipu_api_key_prefers_streamlit_secret_then_env_then_keychain(monkeypatch):
    monkeypatch.setattr(ai_config, "_get_streamlit_secret", lambda name: "secret-key" if name == "ZAI_API_KEY" else None)
    monkeypatch.setattr(ai_config, "_get_keychain_password", lambda: "keychain-key")
    monkeypatch.setenv("ZAI_API_KEY", "env-key")

    assert ai_config.get_zhipu_api_key() == "secret-key"

    monkeypatch.setattr(ai_config, "_get_streamlit_secret", lambda name: None)
    assert ai_config.get_zhipu_api_key() == "env-key"

    monkeypatch.delenv("ZAI_API_KEY")
    assert ai_config.get_zhipu_api_key() == "keychain-key"


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
        db_path=db_path,
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


def test_json_restore_upserts_existing_records_without_deleting_children(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Original Name"}, db_path=db_path)
    services.create_item(
        "medications",
        person_id,
        {"name": "Med A", "status": "Active"},
        db_path=db_path,
    )

    backup = json.loads(imports_exports.export_json_backup(db_path=db_path))
    backup["tables"]["people"][0]["name"] = "Restored Name"

    imports_exports.import_json_backup(json.dumps(backup), clear_existing=False, db_path=db_path)

    assert services.get_person(person_id, db_path=db_path)["name"] == "Restored Name"
    meds = services.list_items("medications", person_id, db_path=db_path)
    assert len(meds) == 1
    assert meds[0]["name"] == "Med A"


def test_json_restore_rejects_malformed_backup_shapes(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)

    with pytest.raises(ValueError, match="Backup JSON must be an object"):
        imports_exports.import_json_backup("[]", db_path=db_path)

    with pytest.raises(ValueError, match="tables"):
        imports_exports.import_json_backup('{"tables": []}', db_path=db_path)

    with pytest.raises(ValueError, match="must be a list"):
        imports_exports.import_json_backup('{"tables": {"people": {}}}', db_path=db_path)

    with pytest.raises(ValueError, match="non-object"):
        imports_exports.import_json_backup('{"tables": {"people": [1]}}', db_path=db_path)


def test_invalid_reminder_dates_are_skipped_in_due_calculations(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Reminder Person"}, db_path=db_path)
    services.create_item(
        "reminders",
        person_id,
        {"reminder_type": "Lab", "title": "Bad date", "due_date": "not-a-date", "status": "Upcoming"},
        db_path=db_path,
    )
    services.create_item(
        "reminders",
        person_id,
        {"reminder_type": "Lab", "title": "Overdue", "due_date": "2020-01-01", "status": "Upcoming"},
        db_path=db_path,
    )

    assert [row["title"] for row in services.overdue_reminders(person_id, db_path=db_path)] == ["Overdue"]
    assert services.due_soon_reminders(person_id, db_path=db_path) == []


def test_delete_person_removes_child_records(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Delete Me"}, db_path=db_path)
    services.create_item("allergies", person_id, {"allergen": "Dust"}, db_path=db_path)
    services.create_item("medications", person_id, {"name": "Med A"}, db_path=db_path)
    services.create_item("lab_results", person_id, {"test_name": "A1c", "lab_date": "2026-01-01"}, db_path=db_path)

    services.delete_person(person_id, db_path=db_path)

    assert services.get_person(person_id, db_path=db_path) is None
    assert db.list_records("allergies", person_id=person_id, db_path=db_path) == []
    assert db.list_records("medications", person_id=person_id, db_path=db_path) == []
    assert db.list_records("lab_results", person_id=person_id, db_path=db_path) == []


def test_delete_person_rolls_back_every_child_when_parent_delete_fails(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Keep Me"}, db_path=db_path)
    snapshots = {}
    for table, payload in CHILD_TABLE_SEEDS.items():
        record_id = services.create_item(table, person_id, payload, db_path=db_path)
        snapshots[table] = db.get_record(table, record_id, db_path=db_path)

    with db.get_connection(db_path) as connection:
        connection.execute(
            """CREATE TRIGGER block_person_delete BEFORE DELETE ON people
            BEGIN SELECT RAISE(ABORT, 'blocked parent delete'); END"""
        )

    with pytest.raises(sqlite3.IntegrityError, match="blocked parent delete"):
        services.delete_person(person_id, db_path=db_path)

    assert services.get_person(person_id, db_path=db_path)["name"] == "Keep Me"
    for table, snapshot in snapshots.items():
        assert db.get_record(table, snapshot["id"], db_path=db_path) == snapshot


def _two_profiles_with_allergies(tmp_path):
    """Alice and Bob, each with one allergy. Returns (db_path, alice, bob, bob_record_id)."""
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    alice = services.create_person({"name": "Alice"}, db_path=db_path)
    bob = services.create_person({"name": "Bob"}, db_path=db_path)
    services.create_item("allergies", alice, {"allergen": "Penicillin"}, db_path=db_path)
    bob_record = services.create_item(
        "allergies", bob, {"allergen": "Peanuts", "severity": "Severe"}, db_path=db_path
    )
    return db_path, alice, bob, bob_record


def test_update_item_rejects_a_record_owned_by_another_profile(tmp_path):
    db_path, alice, bob, bob_record = _two_profiles_with_allergies(tmp_path)

    with pytest.raises(db.RecordNotFound):
        services.update_item(
            "allergies",
            person_id=alice,
            record_id=bob_record,
            data={"allergen": "Overwritten"},
            db_path=db_path,
        )

    survivor = db.get_record("allergies", bob_record, db_path=db_path)
    assert survivor["allergen"] == "Peanuts"
    assert survivor["severity"] == "Severe"
    assert survivor["person_id"] == bob


def test_delete_item_rejects_a_record_owned_by_another_profile(tmp_path):
    db_path, alice, bob, bob_record = _two_profiles_with_allergies(tmp_path)

    with pytest.raises(db.RecordNotFound):
        services.delete_item("allergies", person_id=alice, record_id=bob_record, db_path=db_path)

    assert db.get_record("allergies", bob_record, db_path=db_path) is not None
    assert [row["allergen"] for row in db.list_records("allergies", person_id=bob, db_path=db_path)] == [
        "Peanuts"
    ]


def test_update_and_delete_still_work_for_the_owning_profile(tmp_path):
    db_path, _alice, bob, bob_record = _two_profiles_with_allergies(tmp_path)

    services.update_item(
        "allergies", person_id=bob, record_id=bob_record, data={"allergen": "Tree nuts"}, db_path=db_path
    )
    assert db.get_record("allergies", bob_record, db_path=db_path)["allergen"] == "Tree nuts"

    services.delete_item("allergies", person_id=bob, record_id=bob_record, db_path=db_path)
    assert db.get_record("allergies", bob_record, db_path=db_path) is None


def test_update_item_rejects_a_record_id_that_does_not_exist(tmp_path):
    db_path, alice, _bob, bob_record = _two_profiles_with_allergies(tmp_path)

    with pytest.raises(db.RecordNotFound):
        services.update_item(
            "allergies", person_id=alice, record_id=bob_record + 999, data={"allergen": "X"}, db_path=db_path
        )


def test_person_and_record_ids_are_keyword_only_on_scoped_writes():
    """Swapping two adjacent ints would be a silent isolation failure, so positional is banned."""
    for fn in (services.update_item, services.delete_item):
        kinds = {
            name: param.kind
            for name, param in inspect.signature(fn).parameters.items()
            if name in {"person_id", "record_id"}
        }
        assert kinds == {
            "person_id": inspect.Parameter.KEYWORD_ONLY,
            "record_id": inspect.Parameter.KEYWORD_ONLY,
        }, f"{fn.__name__} must keep person_id/record_id keyword-only"
        signature = inspect.signature(fn).parameters
        assert signature["person_id"].default is inspect.Parameter.empty
        assert signature["record_id"].default is inspect.Parameter.empty


def test_person_scoped_write_guard_covers_every_child_table(tmp_path):
    """Each person-scoped table rejects a cross-profile write, not just allergies."""
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    alice = services.create_person({"name": "Alice"}, db_path=db_path)
    bob = services.create_person({"name": "Bob"}, db_path=db_path)
    for table, payload in CHILD_TABLE_SEEDS.items():
        record_id = services.create_item(table, bob, payload, db_path=db_path)
        protected = db.get_record(table, record_id, db_path=db_path)
        with pytest.raises(db.RecordNotFound):
            services.update_item(
                table,
                person_id=alice,
                record_id=record_id,
                data={next(iter(payload)): "tampered"},
                db_path=db_path,
            )
        with pytest.raises(db.RecordNotFound):
            services.delete_item(table, person_id=alice, record_id=record_id, db_path=db_path)
        assert db.get_record(table, record_id, db_path=db_path) == protected


def test_child_db_writes_require_non_null_person_scope(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    owner = services.create_person({"name": "Owner"}, db_path=db_path)

    for table, payload in CHILD_TABLE_SEEDS.items():
        with pytest.raises(ValueError, match="person_id is required"):
            db.create_record(table, payload, db_path=db_path)
        with pytest.raises(ValueError, match="person_id is required"):
            db.create_record(table, {**payload, "person_id": None}, db_path=db_path)
        with pytest.raises(ValueError, match="person_id is required"):
            services.create_item(table, None, payload, db_path=db_path)
        record_id = services.create_item(table, owner, payload, db_path=db_path)
        protected = db.get_record(table, record_id, db_path=db_path)
        for scope in ("omitted", None):
            update_kwargs = {} if scope == "omitted" else {"person_id": None}
            with pytest.raises(ValueError, match="person_id is required"):
                db.update_record(
                    table,
                    record_id,
                    {next(iter(payload)): "tampered"},
                    db_path=db_path,
                    **update_kwargs,
                )
            with pytest.raises(ValueError, match="person_id is required"):
                db.delete_record(table, record_id, db_path=db_path, **update_kwargs)
            assert db.get_record(table, record_id, db_path=db_path) == protected


def test_service_writes_reject_none_scope_and_preserve_victim(tmp_path):
    db_path, _alice, bob, bob_record = _two_profiles_with_allergies(tmp_path)
    protected = db.get_record("allergies", bob_record, db_path=db_path)

    with pytest.raises(ValueError, match="person_id is required"):
        services.update_item(
            "allergies",
            person_id=None,
            record_id=bob_record,
            data={"allergen": "tampered"},
            db_path=db_path,
        )
    with pytest.raises(ValueError, match="person_id is required"):
        services.delete_item(
            "allergies", person_id=None, record_id=bob_record, db_path=db_path
        )

    assert db.get_record("allergies", bob_record, db_path=db_path) == protected
    assert services.list_items("allergies", bob, db_path=db_path) == [protected]


def test_person_id_is_immutable_during_scoped_updates(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    alice = services.create_person({"name": "Alice"}, db_path=db_path)
    bob = services.create_person({"name": "Bob"}, db_path=db_path)
    record_id = services.create_item(
        "allergies", alice, {"allergen": "Dust", "severity": "Moderate"}, db_path=db_path
    )
    protected = db.get_record("allergies", record_id, db_path=db_path)

    # bob = transfer attempt, alice = unchanged current owner, None = null injection:
    # the key itself is forbidden regardless of value.
    for update in (services.update_item, db.update_record):
        for injected_owner in (bob, alice, None):
            with pytest.raises(ValueError, match="person_id cannot be changed"):
                if update is services.update_item:
                    update(
                        "allergies",
                        person_id=alice,
                        record_id=record_id,
                        data={"person_id": injected_owner, "allergen": "Injected"},
                        db_path=db_path,
                    )
                else:
                    update(
                        "allergies",
                        record_id,
                        {"person_id": injected_owner, "allergen": "Injected"},
                        db_path=db_path,
                        person_id=alice,
                    )

    assert db.get_record("allergies", record_id, db_path=db_path) == protected
    assert services.list_items("allergies", bob, db_path=db_path) == []


def test_failed_owner_transfer_stays_out_of_other_profile_surfaces(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    alice = services.create_person({"name": "Alice"}, db_path=db_path)
    bob = services.create_person({"name": "Bob"}, db_path=db_path)
    marker = "Alice-only fictional marker"
    record_id = services.create_item(
        "health_entries",
        alice,
        {
            "entry_date": "2026-07-31",
            "title": marker,
            "body_part": "heart",
            "note": "Fictional test note",
        },
        db_path=db_path,
    )
    protected = db.get_record("health_entries", record_id, db_path=db_path)

    with pytest.raises(ValueError, match="person_id cannot be changed"):
        services.update_item(
            "health_entries",
            person_id=alice,
            record_id=record_id,
            data={"person_id": bob, "title": "Injected"},
            db_path=db_path,
        )

    assert db.get_record("health_entries", record_id, db_path=db_path) == protected
    alice_surfaces = [
        json.dumps(services.dashboard_data(alice, db_path=db_path)),
        services.generate_provider_summary(alice, db_path=db_path),
        services.generate_emergency_snapshot(alice, db_path=db_path),
        imports_exports.export_json_backup(db_path=db_path, person_id=alice),
        ai_chat.build_patient_context(alice, db_path=db_path),
    ]
    bob_surfaces = [
        json.dumps(services.dashboard_data(bob, db_path=db_path)),
        services.generate_provider_summary(bob, db_path=db_path),
        services.generate_emergency_snapshot(bob, db_path=db_path),
        imports_exports.export_json_backup(db_path=db_path, person_id=bob),
        ai_chat.build_patient_context(bob, db_path=db_path),
    ]
    assert all(marker in surface for surface in alice_surfaces)
    assert all(marker not in surface for surface in bob_surfaces)
    assert any(
        record.display_name == marker
        for record in body_map_services.get_records_for_body_part(
            alice, "heart", db_path=db_path
        )
    )
    assert not body_map_services.get_records_for_body_part(bob, "heart", db_path=db_path)


def test_ui_payload_normalization_preserves_allergy_text_and_health_severity(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Fictional Person"}, db_path=db_path)

    allergy_data = {"allergen": "Dust", "severity": "Severe"}
    assert app.FIELD_CONFIGS["allergies"]["validator"](allergy_data) == []
    allergy_id = services.create_item(
        "allergies",
        person_id,
        app.clean_payload("allergies", allergy_data),
        db_path=db_path,
    )
    allergy_update = {"allergen": "Dust", "severity": "Moderate"}
    assert app.FIELD_CONFIGS["allergies"]["validator"](allergy_update) == []
    services.update_item(
        "allergies",
        person_id=person_id,
        record_id=allergy_id,
        data=app.clean_payload("allergies", allergy_update),
        db_path=db_path,
    )

    health_data = {
        "entry_date": "2026-01-01",
        "title": "Headache",
        "severity": "7",
    }
    assert app.FIELD_CONFIGS["health_entries"]["validator"](health_data) == []
    # Assert the int conversion happens in clean_payload itself; the stored-type
    # assertions below are also satisfied by SQLite INTEGER column affinity.
    cleaned_health = app.clean_payload("health_entries", health_data)
    assert cleaned_health["severity"] == 7
    assert type(cleaned_health["severity"]) is int
    health_id = services.create_item(
        "health_entries",
        person_id,
        cleaned_health,
        db_path=db_path,
    )
    health_update = {**health_data, "severity": "4"}
    assert app.FIELD_CONFIGS["health_entries"]["validator"](health_update) == []
    services.update_item(
        "health_entries",
        person_id=person_id,
        record_id=health_id,
        data=app.clean_payload("health_entries", health_update),
        db_path=db_path,
    )

    allergy = db.get_record("allergies", allergy_id, db_path=db_path)
    health_entry = db.get_record("health_entries", health_id, db_path=db_path)
    assert allergy["severity"] == "Moderate"
    assert isinstance(allergy["severity"], str)
    assert health_entry["severity"] == 4
    assert isinstance(health_entry["severity"], int)


def test_blank_and_whitespace_severity_normalize_to_none_for_both_severity_tables():
    for table in ("allergies", "health_entries"):
        assert app.clean_payload(table, {"severity": ""})["severity"] is None
        assert app.clean_payload(table, {"severity": "   "})["severity"] is None
    assert app.clean_payload("allergies", {"severity": "Severe"})["severity"] == "Severe"
    # Payloads that never mention severity must not gain a severity key.
    assert "severity" not in app.clean_payload("allergies", {"allergen": "Dust"})


def test_record_add_draft_is_scoped_to_selected_profile_with_apptest(tmp_path, monkeypatch):
    db_path = tmp_path / "real.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db(db_path)
    alice = services.create_person({"name": "Alice"}, db_path=db_path)
    bob = services.create_person({"name": "Bob"}, db_path=db_path)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Allergies"
    test_app.session_state["selected_profile"] = f"Alice (ID {alice})"
    test_app.run()

    alice_scope = app.record_page_scope("allergies", alice, db_path)
    test_app.button(key=f"{alice_scope}:add:toggle").click().run()
    test_app.text_input(key=f"{alice_scope}:add:allergen").set_value(
        "Unsubmitted Alice draft"
    ).run()
    test_app.selectbox(key="selected_profile").select(f"Bob (ID {bob})").run()

    bob_scope = app.record_page_scope("allergies", bob, db_path)
    assert not test_app.exception
    assert test_app.session_state[f"{bob_scope}:add:open"] is False
    test_app.button(key=f"{bob_scope}:add:toggle").click().run()
    assert test_app.text_input(key=f"{bob_scope}:add:allergen").value == ""
    assert services.list_items("allergies", bob, db_path=db_path) == []


def test_record_edit_state_is_scoped_across_databases_with_overlapping_ids(
    tmp_path, monkeypatch
):
    real_db = tmp_path / "real.db"
    demo_db = tmp_path / "demo.db"
    monkeypatch.setattr(db, "DB_PATH", real_db)
    db.init_db(real_db)
    db.init_db(demo_db)
    real_person = services.create_person({"name": "Real Person"}, db_path=real_db)
    demo_person = services.create_person({"name": "Demo Person"}, db_path=demo_db)
    real_record = services.create_item(
        "allergies", real_person, {"allergen": "Real allergy"}, db_path=real_db
    )
    demo_record = services.create_item(
        "allergies", demo_person, {"allergen": "Demo allergy"}, db_path=demo_db
    )
    assert (real_person, real_record) == (demo_person, demo_record) == (1, 1)

    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Allergies"
    test_app.session_state[app.DEMO_MODE_KEY] = True
    test_app.session_state[app.DEMO_DB_PATH_KEY] = str(demo_db)
    test_app.session_state["demo_selected_profile"] = "Demo Person (ID 1)"
    test_app.run()

    demo_scope = app.record_page_scope("allergies", demo_person, demo_db)
    test_app.selectbox(key=f"{demo_scope}:edit:selection:0").select("1").run()
    test_app.text_input(key=f"{demo_scope}:edit:1:allergen").set_value(
        "Unsubmitted demo edit"
    ).run()

    test_app.session_state[app.DEMO_MODE_KEY] = False
    test_app.session_state["selected_profile"] = "Real Person (ID 1)"
    test_app.run()
    real_scope = app.record_page_scope("allergies", real_person, real_db)
    test_app.selectbox(key=f"{real_scope}:edit:selection:0").select("1").run()

    assert not test_app.exception
    assert test_app.text_input(key=f"{real_scope}:edit:1:allergen").value == "Real allergy"
    save = next(
        button
        for button in test_app.button
        if button.label == app.action_button_label("Save changes")
    )
    save.click().run()
    assert db.get_record("allergies", 1, db_path=real_db)["allergen"] == "Real allergy"
    assert db.get_record("allergies", 1, db_path=demo_db)["allergen"] == "Demo allergy"


def test_ai_insight_consent_is_scoped_by_profile_and_database(tmp_path, monkeypatch):
    real_db = tmp_path / "real.db"
    demo_db = tmp_path / "demo.db"
    monkeypatch.setattr(db, "DB_PATH", real_db)
    db.init_db(real_db)
    db.init_db(demo_db)
    alice = services.create_person({"name": "Alice"}, db_path=real_db)
    bob = services.create_person({"name": "Bob"}, db_path=real_db)
    demo_person = services.create_person({"name": "Demo Person"}, db_path=demo_db)

    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Health Insights"
    test_app.session_state["selected_profile"] = f"Alice (ID {alice})"
    test_app.run()
    alice_key = f"{app.record_page_scope('insights', alice, real_db)}:ai_consent"
    test_app.checkbox(key=alice_key).check().run()
    assert test_app.checkbox(key=alice_key).value is True

    test_app.selectbox(key="selected_profile").select(f"Bob (ID {bob})").run()
    bob_key = f"{app.record_page_scope('insights', bob, real_db)}:ai_consent"
    assert test_app.checkbox(key=bob_key).value is False

    test_app.session_state[app.DEMO_MODE_KEY] = True
    test_app.session_state[app.DEMO_DB_PATH_KEY] = str(demo_db)
    test_app.session_state["demo_selected_profile"] = f"Demo Person (ID {demo_person})"
    test_app.run()
    demo_key = f"{app.record_page_scope('insights', demo_person, demo_db)}:ai_consent"
    assert not test_app.exception
    assert test_app.checkbox(key=demo_key).value is False


def test_stale_owner_update_and_concurrent_delete_fail_closed(tmp_path, monkeypatch):
    db_path, alice, bob, bob_record = _two_profiles_with_allergies(tmp_path)
    original_get_connection = db.get_connection
    stale_connection = db.get_connection(db_path)
    other_connection = db.get_connection(db_path)
    try:
        assert stale_connection.execute(
            "SELECT person_id FROM allergies WHERE id = ?", (bob_record,)
        ).fetchone()[0] == bob
        other_connection.execute(
            "UPDATE allergies SET person_id = ? WHERE id = ?", (alice, bob_record)
        )
        other_connection.commit()
        protected = dict(
            other_connection.execute(
                "SELECT * FROM allergies WHERE id = ?", (bob_record,)
            ).fetchone()
        )
        monkeypatch.setattr(db, "get_connection", lambda _path: stale_connection)

        with pytest.raises(db.RecordNotFound):
            db.update_record(
                "allergies",
                bob_record,
                {"allergen": "stale overwrite"},
                db_path=db_path,
                person_id=bob,
            )
        assert dict(
            stale_connection.execute(
                "SELECT * FROM allergies WHERE id = ?", (bob_record,)
            ).fetchone()
        ) == protected
    finally:
        other_connection.close()
        stale_connection.close()

    monkeypatch.setattr(db, "get_connection", original_get_connection)
    deleted_record = services.create_item(
        "allergies", alice, {"allergen": "Pollen"}, db_path=db_path
    )
    stale_connection = db.get_connection(db_path)
    other_connection = db.get_connection(db_path)
    try:
        assert stale_connection.execute(
            "SELECT id FROM allergies WHERE id = ?", (deleted_record,)
        ).fetchone()
        other_connection.execute("DELETE FROM allergies WHERE id = ?", (deleted_record,))
        other_connection.commit()
        monkeypatch.setattr(db, "get_connection", lambda _path: stale_connection)
        with pytest.raises(db.RecordNotFound):
            db.delete_record(
                "allergies", deleted_record, db_path=db_path, person_id=alice
            )
    finally:
        other_connection.close()
        stale_connection.close()


def test_locked_write_uses_bounded_wait_and_clean_error(tmp_path, monkeypatch):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Owner"}, db_path=db_path)
    record_id = services.create_item(
        "allergies", person_id, {"allergen": "Dust"}, db_path=db_path
    )
    monkeypatch.setattr(db, "DATABASE_BUSY_TIMEOUT_MS", 20)
    holder = sqlite3.connect(db_path)
    holder.execute("BEGIN EXCLUSIVE")
    started = time.monotonic()
    try:
        with pytest.raises(db.DatabaseBusyError):
            services.update_item(
                "allergies",
                person_id=person_id,
                record_id=record_id,
                data={"allergen": "Duplicate"},
                db_path=db_path,
            )
    finally:
        holder.rollback()
        holder.close()

    assert time.monotonic() - started < 1
    assert db.get_record("allergies", record_id, db_path=db_path)["allergen"] == "Dust"


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (db.RecordNotFound(), "no longer available"),
        (db.DatabaseBusyError(), "database is busy"),
    ],
)
def test_record_change_errors_return_false_with_clean_ui_message(
    monkeypatch, error, message
):
    messages = []
    fake_streamlit = type("FakeStreamlit", (), {"error": messages.append})()
    monkeypatch.setattr(app, "st", fake_streamlit)

    def fail():
        raise error

    assert app.apply_record_change(fail) is False
    assert message in messages[0]


def test_unscoped_db_writes_reject_tables_that_are_not_person_scoped(tmp_path):
    """`people` has no person_id column; scoping it is a programming error, not a silent pass."""
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Alice"}, db_path=db_path)

    with pytest.raises(ValueError):
        db.update_record("people", person_id, {"name": "X"}, db_path=db_path, person_id=person_id)

    # The unscoped path that services.update_person uses stays working.
    services.update_person(person_id, {"name": "Renamed"}, db_path=db_path)
    assert services.get_person(person_id, db_path=db_path)["name"] == "Renamed"


def test_profile_unlock_state_is_scoped_by_database(monkeypatch, tmp_path):
    fake_streamlit = type("FakeStreamlit", (), {"session_state": {}})()
    monkeypatch.setattr(security, "st", fake_streamlit)
    person = {"id": 1, "profile_password_enabled": 1}
    first_db = tmp_path / "first.db"
    second_db = tmp_path / "second.db"

    security.unlock_profile(1, db_path=first_db)

    assert security.health_data_visible(person, db_path=first_db)
    assert not security.health_data_visible(person, db_path=second_db)


def test_locked_profiles_are_masked_in_display_helpers(monkeypatch, tmp_path):
    fake_streamlit = type("FakeStreamlit", (), {"session_state": {}})()
    monkeypatch.setattr(security, "st", fake_streamlit)
    locked = {
        "id": 7,
        "name": "Private Person",
        "date_of_birth": "1990-01-01",
        "sex": "Female",
        "relationship": "Self",
        "emergency_contact": "Private Contact",
        "notes": "Private note",
        "profile_password_enabled": 1,
        "profile_password_hint": "hint",
    }

    assert app.profile_selection_label(locked, tmp_path / "phr.db") == "Protected profile (ID 7)"
    safe_rows = app.display_safe_people([locked], tmp_path / "phr.db")

    assert safe_rows == [
        {
            "id": 7,
            "name": "Protected profile",
            "profile_password_enabled": 1,
        }
    ]


def test_selected_json_backup_excludes_other_profiles(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    selected_id = services.create_person({"name": "Selected"}, db_path=db_path)
    other_id = services.create_person({"name": "Other"}, db_path=db_path)
    services.create_item("medications", selected_id, {"name": "Selected Med"}, db_path=db_path)
    services.create_item("medications", other_id, {"name": "Other Med"}, db_path=db_path)

    backup = json.loads(imports_exports.export_json_backup(db_path=db_path, person_id=selected_id))

    assert [person["name"] for person in backup["tables"]["people"]] == ["Selected"]
    assert [med["name"] for med in backup["tables"]["medications"]] == ["Selected Med"]
    assert "Other" not in json.dumps(backup)


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
    imported_medication = services.list_items("medications", int(imported_person["id"]), db_path=target_db_path)[0]
    assert imported_medication["name"] == "Med A"
    assert imported_medication["dose"] == "10 mg"
    assert imported_medication["frequency"] == "Daily"
    assert services.list_items("lab_results", int(imported_person["id"]), db_path=target_db_path)[0]["test_name"] == "LDL"
    assert services.list_items("health_entries", int(imported_person["id"]), db_path=target_db_path)[0]["title"] == "Headache"
    assert services.list_items("appointments", int(imported_person["id"]), db_path=target_db_path)[0]["title"] == "Primary care follow-up"
    assert services.list_items("reminders", int(imported_person["id"]), db_path=target_db_path)[0]["title"] == "Repeat LDL"
    assert services.list_items("wearable_records", int(imported_person["id"]), db_path=target_db_path)[0]["metric_type"] == "Steps"


def test_fhir_import_skips_bad_patient_references_and_missing_required_fields(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1", "name": [{"text": "One"}]}},
            {"resource": {"resourceType": "Patient", "id": "p2", "name": [{"text": "Two"}]}},
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "bad-ref",
                    "category": [{"text": "Laboratory"}],
                    "code": {"text": "LDL"},
                    "subject": {"reference": "Patient/missing"},
                    "effectiveDateTime": "2026-01-01",
                    "valueQuantity": {"value": 120},
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "missing-date",
                    "category": [{"text": "Laboratory"}],
                    "code": {"text": "A1c"},
                    "subject": {"reference": "Patient/p1"},
                    "valueQuantity": {"value": 5.6},
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "missing-value",
                    "category": [{"text": "Wearable"}],
                    "code": {"text": "Steps"},
                    "subject": {"reference": "Patient/p1"},
                    "effectiveDateTime": "2026-01-02",
                }
            },
        ],
    }

    result = fhir.import_bundle(json.dumps(bundle), db_path=db_path)

    assert result["imported"]["people"] == 2
    assert result["imported"]["lab_results"] == 0
    assert result["imported"]["wearable_records"] == 0
    assert {item["id"] for item in result["skipped"]} == {"bad-ref", "missing-date", "missing-value"}


def test_latest_labs_tie_breaks_same_day_by_newer_record(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Lab Person"}, db_path=db_path)
    services.create_item(
        "lab_results",
        person_id,
        {"test_name": "A1c", "result_value": "5.6", "lab_date": "2026-01-01"},
        db_path=db_path,
    )
    services.create_item(
        "lab_results",
        person_id,
        {"test_name": "A1c", "result_value": "5.9", "lab_date": "2026-01-01"},
        db_path=db_path,
    )

    assert services.latest_labs(person_id, db_path=db_path)[0]["result_value"] == "5.9"


def test_json_restore_rejects_semantically_invalid_rows(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    payload = {
        "tables": {
            "medications": [{"person_id": 1, "name": "Med", "status": "Invalid"}],
            "lab_results": [{"person_id": 1, "test_name": "A1c", "flag": "Invalid", "lab_date": "2026-01-01"}],
        }
    }

    with pytest.raises(ValueError, match="medications.*Medication status"):
        imports_exports.import_json_backup(json.dumps(payload), db_path=db_path)


def test_malformed_wearable_values_do_not_crash_summaries():
    context = {"wearables": [{"metric_type": "Steps", "value": "bad"}, {"metric_type": "Weight", "value": "bad"}]}

    assert insights.compact_context_for_ai(context)["trend_summary"] == {}


def test_ai_insight_prompt_requires_safe_unobtrusive_suggestions(monkeypatch):
    captured = {}

    monkeypatch.setattr(ai_config, "AI_PROVIDER", "zhipu")
    monkeypatch.setattr(ai_config, "get_zhipu_api_key", lambda: "test-key")

    def fake_call(request, **_kwargs):
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

    def fake_call(request, **_kwargs):
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


def test_ai_insight_transport_timeout_does_not_try_fallback_models(monkeypatch):
    seen_models = []

    monkeypatch.setattr(ai_config, "AI_PROVIDER", "zhipu")
    monkeypatch.setattr(ai_config, "ZHIPU_MODEL", "timeout-model")
    monkeypatch.setattr(ai_config, "ZHIPU_FALLBACK_MODELS", "working-model")
    monkeypatch.setattr(ai_config, "get_zhipu_api_key", lambda: "test-key")

    def fake_call(request, **_kwargs):
        model = json.loads(request.data.decode("utf-8"))["model"]
        seen_models.append(model)
        raise insights.ZhipuRetryableError(str(TimeoutError("The read operation timed out")))

    monkeypatch.setattr(insights, "_call_zhipu_chat_completion", fake_call)

    result = insights.generate_ai_insight_result({"person": {}, "medications": [], "labs": []})

    assert result["used_fallback"] is True
    assert seen_models == ["timeout-model"]
    assert "timed out" in result["warning"].lower()


def test_ai_insight_account_error_does_not_retry_or_fallback(monkeypatch):
    monkeypatch.setattr(ai_config, "ZHIPU_MODEL", "primary")
    monkeypatch.setattr(ai_config, "ZHIPU_FALLBACK_MODELS", "fallback")
    attempts = {"count": 0}

    def fake_call(request, **_kwargs):
        attempts["count"] += 1
        raise insights.ZhipuAPIError(429, "1113", "no resource package")

    monkeypatch.setattr(insights, "_call_zhipu_chat_completion", fake_call)

    with pytest.raises(insights.ZhipuAPIError):
        insights._call_zhipu_with_model_fallback("key", [], 20, 0.2)
    assert attempts["count"] == 1


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


def test_ai_chat_context_is_byte_limited(tmp_path, monkeypatch):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Selected Person", "notes": "profile " * 400}, db_path=db_path)
    for index in range(12):
        services.create_item(
            "health_entries",
            person_id,
            {
                "entry_date": f"2026-01-{index + 1:02d}",
                "title": f"Entry {index}",
                "body_system": "General",
                "note": "long note " * 200,
            },
            db_path=db_path,
        )

    monkeypatch.setattr(ai_chat, "CHAT_CONTEXT_BYTE_LIMIT", 2500)
    context_text = ai_chat.build_patient_context(person_id, db_path=db_path)

    assert len(context_text.encode("utf-8")) <= 3000
    assert "Selected Person" in context_text


def test_zhipu_model_candidates_ignore_blank_primary(monkeypatch):
    monkeypatch.setattr(ai_config, "ZHIPU_MODEL", "")
    monkeypatch.setattr(ai_config, "ZHIPU_FALLBACK_MODELS", "fallback-a, fallback-b")

    assert ai_config.zhipu_model_candidates() == ["fallback-a", "fallback-b"]


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

        def read(self, amt=None):
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

        def read(self, amt=None):
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


def test_ai_chat_maps_auth_and_invalid_responses(monkeypatch):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "glm-5.1")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "")

    def fake_auth_error(request, timeout):
        body = BytesIO(json.dumps({"error": {"code": "401", "message": "bad key"}}).encode("utf-8"))
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=body)

    monkeypatch.setattr(ai_chat.urllib.request, "urlopen", fake_auth_error)
    with pytest.raises(ai_chat.MissingAPIKeyError):
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])

    class InvalidJsonResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, amt=None):
            return b"not-json"

    monkeypatch.setattr(ai_chat.urllib.request, "urlopen", lambda request, timeout: InvalidJsonResponse())
    with pytest.raises(ai_chat.InvalidAIResponseError):
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])


@pytest.mark.parametrize("raw", [b"\xff", b"not-json"])
def test_ai_chat_rejects_unreadable_response_bytes(monkeypatch, raw):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "only-model")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, amt=None):
            return raw

    monkeypatch.setattr(
        ai_chat.urllib.request, "urlopen", lambda request, timeout: FakeResponse()
    )

    with pytest.raises(ai_chat.InvalidAIResponseError):
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])


@pytest.mark.parametrize("content", [None, {"text": "answer"}, ["answer"], "", "   "])
def test_ai_chat_rejects_non_string_content(monkeypatch, content):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "only-model")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, amt=None):
            return json.dumps(
                {"choices": [{"message": {"content": content}}]}
            ).encode("utf-8")

    monkeypatch.setattr(
        ai_chat.urllib.request, "urlopen", lambda request, timeout: FakeResponse()
    )

    with pytest.raises(ai_chat.InvalidAIResponseError):
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])


@pytest.mark.parametrize(
    "read_error", [ConnectionResetError("reset"), http.client.IncompleteRead(b"partial")]
)
def test_ai_chat_maps_response_read_transport_failures(monkeypatch, read_error):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "primary")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "fallback")
    attempts = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, amt=None):
            raise read_error

    def fake_urlopen(request, timeout):
        attempts["count"] += 1
        return FakeResponse()

    monkeypatch.setattr(ai_chat.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ai_chat.NetworkAIChatError):
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])
    assert attempts["count"] == 1


def test_ai_chat_timeout_is_model_independent_and_not_retried(monkeypatch):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "primary")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "fallback-a,fallback-b")
    timeouts = []

    def fake_urlopen(request, timeout):
        timeouts.append(timeout)
        raise TimeoutError("slow")

    monkeypatch.setattr(ai_chat.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ai_chat.NetworkAIChatError):
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])

    assert len(timeouts) == 1
    assert 0 < timeouts[0] <= ai_chat.CHAT_TIMEOUT_SECONDS


def test_ai_chat_fallbacks_share_one_monotonic_deadline(monkeypatch):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "model-1")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "model-2,model-3")
    monotonic_values = iter([0.0, 0.0, 30.0, 50.0])
    timeouts = []

    def fake_urlopen(request, timeout):
        timeouts.append(timeout)
        body = BytesIO(
            json.dumps({"error": {"code": "1305", "message": "model busy"}}).encode(
                "utf-8"
            )
        )
        raise urllib.error.HTTPError(
            request.full_url, 429, "Too Many Requests", hdrs=None, fp=body
        )

    monkeypatch.setattr(ai_chat.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(ai_chat.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ai_chat.NetworkAIChatError, match="time budget"):
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])

    assert timeouts == [45.0, 15.0]


def test_ai_chat_eligible_429_uses_fallback_model(monkeypatch):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "busy-model")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "working-model")
    seen_models = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, amt=None):
            return json.dumps(
                {"choices": [{"message": {"content": "Fallback answer"}}]}
            ).encode("utf-8")

    def fake_urlopen(request, timeout):
        model = json.loads(request.data.decode("utf-8"))["model"]
        seen_models.append(model)
        if model == "busy-model":
            body = BytesIO(
                json.dumps(
                    {"error": {"code": "1305", "message": "model busy"}}
                ).encode("utf-8")
            )
            raise urllib.error.HTTPError(
                request.full_url, 429, "Too Many Requests", hdrs=None, fp=body
            )
        return FakeResponse()

    monkeypatch.setattr(ai_chat.urllib.request, "urlopen", fake_urlopen)

    assert ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}]) == "Fallback answer"
    assert seen_models == ["busy-model", "working-model"]


def test_insight_urlopen_timeout_stops_without_retry_or_sleep(monkeypatch):
    attempts = {"count": 0}

    def fake_urlopen(request, timeout):
        attempts["count"] += 1
        raise TimeoutError("slow")

    monkeypatch.setattr(insights.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(insights.time, "sleep", lambda seconds: None)

    with pytest.raises(insights.ZhipuRetryableError):
        insights._call_zhipu_chat_completion(
            urllib.request.Request("https://example.invalid")
        )

    assert attempts["count"] == 1


def test_delete_person_missing_id_raises_and_rolls_back(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    keeper = services.create_person({"name": "Keeper"}, db_path=db_path)
    keeper_record = services.create_item(
        "allergies", keeper, {"allergen": "Dust"}, db_path=db_path
    )
    missing_id = keeper + 999
    # Raw connections leave foreign keys OFF, so an orphan child row can be seeded;
    # the missing-parent delete must roll back the child DELETE that matched it.
    orphan_connection = sqlite3.connect(db_path)
    cursor = orphan_connection.execute(
        "INSERT INTO allergies (person_id, allergen, created_at, updated_at) VALUES (?,?,?,?)",
        (missing_id, "Orphan", "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    orphan_id = cursor.lastrowid
    orphan_connection.commit()
    orphan_connection.close()

    with pytest.raises(db.RecordNotFound):
        services.delete_person(missing_id, db_path=db_path)

    assert db.get_record("allergies", orphan_id, db_path=db_path)["allergen"] == "Orphan"
    assert db.get_record("allergies", keeper_record, db_path=db_path) is not None


def test_non_busy_operational_errors_propagate_untranslated(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Owner"}, db_path=db_path)
    with db.get_connection(db_path) as connection:
        connection.execute("DROP TABLE wearable_records")

    with pytest.raises(sqlite3.OperationalError):
        db.update_record(
            "wearable_records", 1, {"value": 1}, db_path=db_path, person_id=person_id
        )


def test_init_db_busy_maps_to_database_busy_error(tmp_path, monkeypatch):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    monkeypatch.setattr(db, "DATABASE_BUSY_TIMEOUT_MS", 20)
    holder = sqlite3.connect(db_path)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(db.DatabaseBusyError):
            db.init_db(db_path)
    finally:
        holder.rollback()
        holder.close()


def test_child_table_seeds_cover_every_person_scoped_table():
    person_scoped = {t for t, columns in db.TABLE_COLUMNS.items() if "person_id" in columns}
    assert set(CHILD_TABLE_SEEDS) == person_scoped


def test_create_record_rejects_person_id_for_unscoped_tables(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    with pytest.raises(ValueError, match="not person-scoped"):
        db.create_record("people", {"name": "Ghost", "person_id": 7}, db_path=db_path)
    with pytest.raises(ValueError, match="not person-scoped"):
        services.create_item("people", 7, {"name": "Ghost"}, db_path=db_path)
    assert services.list_people(db_path=db_path) == []


def _fake_provider_response(raw):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, amt=None):
            return raw

    return FakeResponse()


@pytest.mark.parametrize(
    "payload", [[], {}, {"choices": []}, {"choices": "x"}, {"choices": [{"message": "oops"}]}]
)
def test_ai_chat_rejects_malformed_response_shapes(monkeypatch, payload):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "only-model")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "")
    monkeypatch.setattr(
        ai_chat.urllib.request,
        "urlopen",
        lambda request, timeout: _fake_provider_response(json.dumps(payload).encode("utf-8")),
    )

    with pytest.raises(ai_chat.InvalidAIResponseError):
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])


def test_ai_chat_rejects_pathologically_nested_json_response(monkeypatch):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "only-model")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "")
    nested = b"[" * 20_000 + b"]" * 20_000
    monkeypatch.setattr(
        ai_chat.urllib.request,
        "urlopen",
        lambda request, timeout: _fake_provider_response(nested),
    )

    with pytest.raises(ai_chat.InvalidAIResponseError):
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])


def test_ai_chat_rejects_oversized_response_body(monkeypatch):
    monkeypatch.setattr(ai_chat, "get_zhipu_api_key", lambda: "test-key")
    monkeypatch.setenv("ZHIPU_CHAT_MODEL", "only-model")
    monkeypatch.setenv("ZHIPU_CHAT_FALLBACK_MODELS", "")
    monkeypatch.setattr(ai_config, "ZHIPU_RESPONSE_BYTE_LIMIT", 16)
    monkeypatch.setattr(
        ai_chat.urllib.request,
        "urlopen",
        lambda request, timeout: _fake_provider_response(b"x" * 17),
    )

    with pytest.raises(ai_chat.InvalidAIResponseError, match="oversized"):
        ai_chat.call_zhipu_chat([{"role": "user", "content": "Question"}])


def test_insight_rejects_oversized_response_body(monkeypatch):
    monkeypatch.setattr(ai_config, "ZHIPU_RESPONSE_BYTE_LIMIT", 16)
    monkeypatch.setattr(
        insights.urllib.request,
        "urlopen",
        lambda request, timeout: _fake_provider_response(b"x" * 17),
    )

    with pytest.raises(insights.ZhipuAPIError) as excinfo:
        insights._call_zhipu_chat_completion(urllib.request.Request("https://example.invalid"))

    assert "oversized" in excinfo.value.detail


def test_insight_1113_makes_exactly_one_request_without_retry_or_sleep(monkeypatch):
    attempts = {"count": 0}
    sleeps = []

    def fake_urlopen(request, timeout):
        attempts["count"] += 1
        detail = {"error": {"code": "1113", "message": "no resource package"}}
        body = BytesIO(json.dumps(detail).encode("utf-8"))
        raise urllib.error.HTTPError(
            request.full_url, 429, "Too Many Requests", hdrs=None, fp=body
        )

    monkeypatch.setattr(insights.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(insights.time, "sleep", sleeps.append)

    with pytest.raises(insights.ZhipuAPIError) as excinfo:
        insights._call_zhipu_chat_completion(urllib.request.Request("https://example.invalid"))

    assert excinfo.value.provider_code == "1113"
    assert attempts["count"] == 1
    assert sleeps == []


def test_insight_empty_model_candidates_raise_config_error_not_typeerror(monkeypatch):
    monkeypatch.setattr(ai_config, "ZHIPU_MODEL", "")
    monkeypatch.setattr(ai_config, "ZHIPU_FALLBACK_MODELS", "")

    with pytest.raises(insights.ZhipuAPIError) as excinfo:
        insights._call_zhipu_with_model_fallback("key", [], 20, 0.2)

    assert "No Zhipu model" in excinfo.value.detail

    monkeypatch.setattr(ai_config, "AI_PROVIDER", "zhipu")
    monkeypatch.setattr(ai_config, "get_zhipu_api_key", lambda: "test-key")
    ok, message, _detail = insights.validate_zhipu_connection()
    assert ok is False
    assert "No Zhipu model" in message


def test_http_error_parsers_tolerate_pathologically_nested_error_bodies():
    nested = b"[" * 20_000 + b"]" * 20_000
    for parser in (ai_chat._parse_http_error, insights._parse_http_error):
        error = urllib.error.HTTPError(
            "https://example.invalid", 429, "Too Many Requests", hdrs=None, fp=BytesIO(nested)
        )
        code, detail = parser(error)
        assert code is None
        assert "429" in detail


def test_profile_write_busy_shows_clean_error_with_apptest(tmp_path, monkeypatch):
    db_path = tmp_path / "real.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db(db_path)
    alice = services.create_person({"name": "Alice"}, db_path=db_path)

    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Profiles"
    test_app.run()
    test_app.selectbox(key="edit_profile_selection_0").select(str(alice)).run()

    def busy_update(*_args, **_kwargs):
        raise db.DatabaseBusyError(
            "The health record database is busy. Wait a moment and try again."
        )

    monkeypatch.setattr(services, "update_person", busy_update)
    save = next(
        button
        for button in test_app.button
        if button.label == app.action_button_label("Save changes")
    )
    save.click().run()

    assert not test_app.exception
    assert any("database is busy" in error.value for error in test_app.error)


def test_omitted_db_path_resolves_at_call_time_not_import_time(tmp_path, monkeypatch):
    """A bare call must honour a repointed db.DB_PATH.

    This is the property that import-time `db_path=db.DB_PATH` defaults silently broke:
    the default froze the real database into the function object, so the patch below
    could never reach it.
    """
    patched = tmp_path / "late_bound.db"
    monkeypatch.setattr(db, "DB_PATH", patched)
    db.init_db(patched)

    person_id = services.create_person({"name": "Late Bound"})

    assert patched.exists()
    assert [row["name"] for row in services.list_people()] == ["Late Bound"]
    assert services.get_person(person_id)["name"] == "Late Bound"


def test_no_caller_forwards_none_into_profile_unlock_scoping(tmp_path, monkeypatch):
    """`security._db_scope(None)` is a real bucket, not a sentinel -- so None must never reach it.

    `_db_scope` hashes a real path but returns the literal "default" for None. If a caller
    forwarded None, unlock state for a locked profile would be shared across every database,
    merging demo and real sessions. security.py imports no `db`, so it cannot resolve the
    path itself; the caller must.
    """
    fake_streamlit = type("FakeStreamlit", (), {"session_state": {}})()
    monkeypatch.setattr(security, "st", fake_streamlit)
    monkeypatch.setattr(app, "st", type("FakeAppSt", (), {"markdown": staticmethod(lambda *a, **k: None)})())
    real_db = tmp_path / "real.db"
    monkeypatch.setattr(db, "DB_PATH", real_db)

    seen = []
    original_scope = security._db_scope
    monkeypatch.setattr(security, "_db_scope", lambda db_path=None: seen.append(db_path) or original_scope(db_path))

    person = {"id": 1, "name": "Scoped Person", "profile_password_enabled": 1}
    security.unlock_profile(1, db_path=real_db)
    before = len(seen)  # the unlock above already recorded one call

    assert app.is_locked_profile(person) is False
    app.selected_profile_banner(person)
    app.display_safe_people([person])
    app.profile_selection_label(person)

    assert len(seen) > before, "expected the profile helpers to consult _db_scope"
    assert None not in seen, f"a caller forwarded None into _db_scope: {seen}"


def test_locked_profile_stays_locked_when_db_path_is_omitted(tmp_path, monkeypatch):
    """Unlocking under one database must not unlock a bare call scoped to another."""
    fake_streamlit = type("FakeStreamlit", (), {"session_state": {}})()
    monkeypatch.setattr(security, "st", fake_streamlit)
    other_db = tmp_path / "other.db"
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "real.db")

    person = {"id": 1, "profile_password_enabled": 1}
    security.unlock_profile(1, db_path=other_db)

    assert app.is_locked_profile(person, other_db) is False
    assert app.is_locked_profile(person) is True


# --- Chronic conditions (person-scoped record type) ---------------------------------------------


def _two_profiles_with_conditions(tmp_path):
    """Alice and Bob, each with one condition. Returns (db_path, alice, bob, bob_record_id)."""
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    alice = services.create_person({"name": "Alice"}, db_path=db_path)
    bob = services.create_person({"name": "Bob"}, db_path=db_path)
    services.create_item(
        "conditions", alice, {"condition_name": "Diabetes", "source": "Endocrinologist"}, db_path=db_path
    )
    bob_record = services.create_item(
        "conditions", bob, {"condition_name": "Hypertension", "source": "Cardiologist"}, db_path=db_path
    )
    return db_path, alice, bob, bob_record


def test_condition_crud_round_trip(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Alex"}, db_path=db_path)

    record_id = services.create_item(
        "conditions",
        person_id,
        {"condition_name": "Diabetes", "source": "Endocrinologist", "noted_date": "2026-01-15"},
        db_path=db_path,
    )
    rows = services.tracked_conditions(person_id, db_path=db_path)
    assert [row["condition_name"] for row in rows] == ["Diabetes"]
    assert rows[0]["source"] == "Endocrinologist"

    services.update_item(
        "conditions",
        person_id=person_id,
        record_id=record_id,
        data={"source": "Primary Care"},
        db_path=db_path,
    )
    assert services.tracked_conditions(person_id, db_path=db_path)[0]["source"] == "Primary Care"

    services.delete_item("conditions", person_id=person_id, record_id=record_id, db_path=db_path)
    assert services.tracked_conditions(person_id, db_path=db_path) == []


def test_tracked_conditions_orders_by_name_ascending(tmp_path):
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Alex"}, db_path=db_path)
    for name in ("Hypertension", "Asthma", "Diabetes"):
        services.create_item("conditions", person_id, {"condition_name": name}, db_path=db_path)

    names = [row["condition_name"] for row in services.tracked_conditions(person_id, db_path=db_path)]
    assert names == ["Asthma", "Diabetes", "Hypertension"]


def test_validate_condition_accepts_and_rejects():
    assert validation.validate_condition(
        {"condition_name": "Diabetes", "source": "Endocrinologist", "noted_date": "2026-01-15"}
    ) == []
    # A blank source is allowed; the column is optional.
    assert validation.validate_condition({"condition_name": "Diabetes", "source": ""}) == []
    assert validation.validate_condition({"condition_name": ""}) == ["Condition name is required."]
    assert validation.validate_condition(
        {"condition_name": "Diabetes", "source": "Astrologer"}
    ) != []
    assert validation.validate_condition(
        {"condition_name": "Diabetes", "noted_date": "not-a-date"}
    ) != []


def test_validate_condition_does_not_mutate_input():
    data = {"condition_name": "Diabetes", "source": "Endocrinologist"}
    validation.validate_condition(data)
    assert data == {"condition_name": "Diabetes", "source": "Endocrinologist"}


def test_conditions_are_isolated_between_profiles(tmp_path):
    db_path, alice, bob, _ = _two_profiles_with_conditions(tmp_path)

    alice_names = [row["condition_name"] for row in services.tracked_conditions(alice, db_path=db_path)]
    bob_names = [row["condition_name"] for row in services.tracked_conditions(bob, db_path=db_path)]
    assert alice_names == ["Diabetes"]
    assert bob_names == ["Hypertension"]

    alice_dashboard = services.dashboard_data(alice, db_path=db_path)
    assert [row["condition_name"] for row in alice_dashboard["conditions"]] == ["Diabetes"]
    assert "Hypertension" not in json.dumps(alice_dashboard)


def test_selected_json_backup_excludes_other_profiles_conditions(tmp_path):
    db_path, alice, _, _ = _two_profiles_with_conditions(tmp_path)

    backup = json.loads(imports_exports.export_json_backup(db_path=db_path, person_id=alice))

    assert [row["condition_name"] for row in backup["tables"]["conditions"]] == ["Diabetes"]
    assert "Hypertension" not in json.dumps(backup)
    assert "Cardiologist" not in json.dumps(backup)


def test_condition_update_rejects_a_record_owned_by_another_profile(tmp_path):
    db_path, alice, _, bob_record = _two_profiles_with_conditions(tmp_path)

    with pytest.raises(db.RecordNotFound):
        services.update_item(
            "conditions", person_id=alice, record_id=bob_record, data={"condition_name": "Owned"}, db_path=db_path
        )
    with pytest.raises(db.RecordNotFound):
        services.delete_item("conditions", person_id=alice, record_id=bob_record, db_path=db_path)


def test_delete_person_removes_conditions_without_foreign_key_error(tmp_path):
    """Regression: conditions must be in db.TABLES or this raises IntegrityError."""
    db_path, alice, bob, _ = _two_profiles_with_conditions(tmp_path)

    db.delete_person(alice, db_path=db_path)

    assert services.tracked_conditions(alice, db_path=db_path) == []
    assert [row["condition_name"] for row in services.tracked_conditions(bob, db_path=db_path)] == [
        "Hypertension"
    ]


def test_json_backup_round_trip_preserves_conditions(tmp_path):
    """Regression: conditions must be in BACKUP_VALIDATORS or restore raises KeyError."""
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    person_id = services.create_person({"name": "Alex"}, db_path=db_path)
    services.create_item(
        "conditions",
        person_id,
        {"condition_name": "Diabetes", "source": "Endocrinologist", "noted_date": "2026-01-15"},
        db_path=db_path,
    )

    backup = imports_exports.export_json_backup(db_path=db_path, person_id=person_id)

    restore_path = tmp_path / "restored.db"
    db.init_db(restore_path)
    imports_exports.import_json_backup(backup, db_path=restore_path)

    restored_people = services.list_people(db_path=restore_path)
    assert len(restored_people) == 1
    rows = services.tracked_conditions(int(restored_people[0]["id"]), db_path=restore_path)
    assert [(row["condition_name"], row["source"]) for row in rows] == [("Diabetes", "Endocrinologist")]


def test_init_db_adds_conditions_table_to_a_pre_existing_database(tmp_path):
    """Schema idempotency: an older database gains the table, and re-running is a no-op."""
    db_path = tmp_path / "phr.db"
    db.init_db(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE conditions")
        connection.commit()

    db.init_db(db_path)
    db.init_db(db_path)

    person_id = services.create_person({"name": "Alex"}, db_path=db_path)
    services.create_item("conditions", person_id, {"condition_name": "Asthma"}, db_path=db_path)
    assert [row["condition_name"] for row in services.tracked_conditions(person_id, db_path=db_path)] == [
        "Asthma"
    ]


def test_condition_display_lines_omits_missing_source_and_blank_rows():
    lines = app.condition_display_lines(
        [
            {"condition_name": "Diabetes", "source": "Endocrinologist"},
            {"condition_name": "Asthma", "source": None},
            {"condition_name": "  ", "source": "Primary Care"},
        ]
    )
    assert lines == ["Diabetes — Endocrinologist", "Asthma"]


# --- regressions from the 2026-08-04 independent review ---------------------------------------


def test_fhir_replace_import_refuses_to_delete_what_it_cannot_restore(tmp_path):
    """A FHIR bundle carries no Condition, so clear-and-replace used to destroy tracked conditions.

    Reproduced before the fix: export a profile's own bundle, re-import it with clear-existing, and
    every condition was gone -- while the result dict reported `conditions: 0`, which is
    indistinguishable from "the bundle had none to import". Medications and every other table came
    back, so nothing on screen suggested a loss had happened.
    """
    database = tmp_path / "fhir_guard.db"
    db.init_db(database)
    person_id = services.create_person({"name": "Test Person", "relationship": "Self"}, db_path=database)
    services.create_item(
        "conditions",
        person_id,
        {"condition_name": "Hypertension", "source": "Primary Care", "noted_date": "2025-01-01"},
        db_path=database,
    )
    services.create_item("medications", person_id, {"name": "Lisinopril", "start_date": "2025-02-10"}, db_path=database)
    bundle = fhir.export_bundle("R4", person_id=person_id, db_path=database)

    with pytest.raises(ValueError) as excinfo:
        imports_exports.import_fhir_bundle(bundle, clear_existing=True, db_path=database)

    assert "conditions" in str(excinfo.value)
    # The refusal happens before anything is deleted, so both tables are untouched.
    assert [row["condition_name"] for row in services.tracked_conditions(person_id, db_path=database)] == ["Hypertension"]
    assert len(services.list_items("medications", person_id, db_path=database)) == 1


def test_fhir_replace_import_refuses_to_unlock_a_password_protected_profile(tmp_path):
    """A table-level check passed this and the profile came back UNLOCKED.

    `Patient` carries name, birth date, sex, relationship and emergency contact -- and nothing for
    `profile_password_enabled`, `profile_password_hash` or `profile_password_hint`. So a protected
    profile with no conditions cleared the table-level guard, and clear-and-replace reset
    `profile_password_enabled` to 0: an import silently unlocking a profile, which is the failure
    AGENTS.md section 4 exists to prevent. Its notes were overwritten with a fixed string too.
    """
    database = tmp_path / "fhir_guard.db"
    db.init_db(database)
    person_id = services.create_person(
        {"name": "Protected Person", "relationship": "Self", "notes": "Keep private."}, db_path=database
    )
    db.update_record(
        "people",
        person_id,
        {
            "profile_password_enabled": 1,
            "profile_password_hash": security.hash_password("correct horse"),
            "profile_password_hint": "the usual one",
        },
        db_path=database,
    )
    bundle = fhir.export_bundle("R4", person_id=person_id, db_path=database)

    with pytest.raises(ValueError) as excinfo:
        imports_exports.import_fhir_bundle(bundle, clear_existing=True, db_path=database)

    assert "unlocked" in str(excinfo.value)
    row = db.list_records("people", db_path=database)[0]
    assert row["profile_password_enabled"] == 1
    assert row["profile_password_hint"] == "the usual one"
    assert row["notes"] == "Keep private."
    assert security.verify_password("correct horse", row["profile_password_hash"])


def test_faithful_person_columns_match_what_a_patient_resource_actually_carries(tmp_path):
    """Anti-drift: the declared faithful set must not out-run `_person_from_patient`.

    If a column is added to `FAITHFUL_PERSON_COLUMNS` without the converter learning to restore it,
    the guard starts permitting exactly the loss it exists to block -- silently.
    """
    produced = fhir._person_from_patient(
        {
            "id": "person-1",
            "name": [{"text": "Test Person"}],
            "birthDate": "1990-01-01",
            "gender": "female",
            "contact": [{"name": {"text": "Next Of Kin"}}],
            "extension": [{"url": "http://example.org/profile-relationship", "valueString": "Self"}],
        }
    )

    # Every faithful column is one the converter actually produces...
    assert fhir.FAITHFUL_PERSON_COLUMNS <= set(produced)
    # ...and `notes` is produced but deliberately excluded, because the value is invented.
    assert produced["notes"] == "Imported from FHIR."
    assert "notes" not in fhir.FAITHFUL_PERSON_COLUMNS
    # Nothing faithful may be missing from the real people schema either.
    assert fhir.FAITHFUL_PERSON_COLUMNS <= set(db.TABLE_COLUMNS["people"])


def test_fhir_replace_import_still_works_when_nothing_would_be_lost(tmp_path):
    """The guard is scoped to state that actually exists, so a plain profile is unaffected."""
    database = tmp_path / "fhir_guard.db"
    db.init_db(database)
    person_id = services.create_person({"name": "Test Person", "relationship": "Self"}, db_path=database)
    services.create_item("medications", person_id, {"name": "Lisinopril", "start_date": "2025-02-10"}, db_path=database)
    bundle = fhir.export_bundle("R4", person_id=person_id, db_path=database)

    result = imports_exports.import_fhir_bundle(bundle, clear_existing=True, db_path=database)

    assert result["imported"]["medications"] == 1
    restored = services.list_people(db_path=database)
    assert len(restored) == 1


def test_every_table_is_either_fhir_restorable_or_guarded(tmp_path):
    """Derived, not hand-listed: the next table added cannot slip through the same way.

    `conditions` was only ever lost because `db.TABLES` happened to equal the set FHIR could emit
    until it was added, so the replace-import was lossless by coincidence rather than by check.
    """
    database = tmp_path / "fhir_guard.db"
    db.init_db(database)
    person_id = services.create_person({"name": "Test Person"}, db_path=database)
    unrestorable = set(db.TABLES) - fhir.restorable_tables()

    assert unrestorable, "if this is ever empty the guard is dead code -- delete it deliberately"
    for table in unrestorable:
        seed = dict(CHILD_TABLE_SEEDS[table])
        services.create_item(table, person_id, seed, db_path=database)

    blocked = fhir.unrestorable_state(database)

    assert set(blocked) >= unrestorable


def test_the_fhir_clear_guard_sees_every_profile_not_just_the_bundle_s_own(tmp_path):
    """The clear is database-global, so the guard must be too.

    A one-profile fixture cannot tell a global count from a person-scoped one. If the guard were
    ever scoped to the bundle's Patient -- which looks like the natural response to the fact that it
    reports on profiles the importer did not choose -- then profile B could clear-import while
    profile A's conditions were destroyed, and every other test here would stay green.
    """
    database = tmp_path / "fhir_guard.db"
    db.init_db(database)
    keeper = services.create_person({"name": "Profile A"}, db_path=database)
    services.create_item("conditions", keeper, {"condition_name": "Asthma"}, db_path=database)
    importer = services.create_person({"name": "Profile B"}, db_path=database)
    bundle = fhir.export_bundle("R4", person_id=importer, db_path=database)

    with pytest.raises(ValueError):
        imports_exports.import_fhir_bundle(bundle, clear_existing=True, db_path=database)

    assert [row["condition_name"] for row in services.tracked_conditions(keeper, db_path=database)] == ["Asthma"]


def test_the_fhir_clear_refusal_names_what_is_lost_but_never_how_much(tmp_path):
    """A locked profile's row count is health data, and this string reaches st.error verbatim.

    AGENTS.md section 4 lists error messages among the channels a locked profile must not leak
    through, and the guard is database-global by necessity -- it sees locked profiles too.
    """
    database = tmp_path / "fhir_guard.db"
    db.init_db(database)
    locked = services.create_person({"name": "Locked Profile"}, db_path=database)
    for name in ("Asthma", "Gout", "Hypertension"):
        services.create_item("conditions", locked, {"condition_name": name}, db_path=database)
    db.update_record(
        "people",
        locked,
        {"profile_password_enabled": 1, "profile_password_hash": security.hash_password("secret")},
        db_path=database,
    )
    bundle = fhir.export_bundle("R4", person_id=locked, db_path=database)

    with pytest.raises(ValueError) as excinfo:
        imports_exports.import_fhir_bundle(bundle, clear_existing=True, db_path=database)

    message = str(excinfo.value)
    assert "conditions" in message
    assert "3" not in message


def test_a_lab_observation_with_no_interpretation_imports_without_a_flag(tmp_path):
    """A round trip must not turn "nobody flagged this" into the recorded flag "Unknown"."""
    database = tmp_path / "fhir_guard.db"
    db.init_db(database)
    person_id = services.create_person({"name": "Test Person"}, db_path=database)
    services.create_item(
        "lab_results",
        person_id,
        {"test_name": "Hemoglobin A1c", "numeric_value": 5.5, "unit": "%", "lab_date": "2026-01-01"},
        db_path=database,
    )
    bundle = fhir.export_bundle("R4", person_id=person_id, db_path=database)

    target = tmp_path / "fhir_target.db"
    db.init_db(target)
    imports_exports.import_fhir_bundle(bundle, clear_existing=False, db_path=target)

    imported = db.list_records("lab_results", db_path=target)[0]
    assert not imported["flag"]
