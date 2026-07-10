from __future__ import annotations

from dataclasses import fields

import pytest

import body_map_services
import db
import services
from body_map_services import NormalizedBodyRecord, get_records_for_body_part


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "body-map.db"
    db.init_db(path)
    return path


def _person(db_path, name="Person A"):
    return services.create_person({"name": name}, db_path=db_path)


def _add(table, person_id, data, db_path):
    return services.create_item(table, person_id, data, db_path=db_path)


def test_retrieval_returns_only_selected_person_records(db_path):
    selected = _person(db_path)
    other = _person(db_path, "Person B")
    for person_id in (selected, other):
        _add("lab_results", person_id, {"test_name": "LDL", "lab_date": "2026-01-01"}, db_path)

    records = get_records_for_body_part(selected, "heart", db_path)

    assert [record.person_id for record in records] == [selected]
    assert records[0].raw_record["person_id"] == selected


def test_every_record_adapter_applies_person_filter(db_path, monkeypatch):
    person_id = _person(db_path)
    calls = []
    original = services.list_items

    def tracked(table, selected_person_id, *args, **kwargs):
        calls.append((table, selected_person_id))
        return original(table, selected_person_id, *args, **kwargs)

    monkeypatch.setattr(body_map_services.services, "list_items", tracked)
    get_records_for_body_part(person_id, "heart", db_path)

    assert calls == [(table, person_id) for table in body_map_services._RECORD_ADAPTERS]


@pytest.mark.parametrize(
    ("test_name", "body_part"),
    [("LDL", "heart"), ("creatinine", "kidneys"), ("ALT", "liver"), ("thyroid-stimulating hormone", "thyroid")],
)
def test_curated_lab_mappings(test_name, body_part, db_path):
    person_id = _person(db_path)
    _add("lab_results", person_id, {"test_name": test_name, "lab_date": "2026-01-01"}, db_path)

    assert [record.name for record in get_records_for_body_part(person_id, body_part, db_path)] == [test_name]


def test_unmapped_record_is_excluded(db_path):
    person_id = _person(db_path)
    _add("lab_results", person_id, {"test_name": "Unknown marker", "lab_date": "2026-01-01"}, db_path)

    assert get_records_for_body_part(person_id, "heart", db_path) == []


def test_stored_mapping_takes_precedence_without_mutating_source(db_path):
    person_id = _person(db_path)
    _add(
        "health_entries",
        person_id,
        {"title": "LDL", "entry_date": "2026-01-01", "body_part": "Lungs", "body_system": "Respiratory"},
        db_path,
    )
    source = services.list_items("health_entries", person_id, db_path=db_path)[0]

    assert get_records_for_body_part(person_id, "heart", db_path) == []
    record = get_records_for_body_part(person_id, "lungs", db_path)[0]
    assert record.mapping_source == "stored"
    assert record.body_parts == ("lungs",)
    assert source == services.list_items("health_entries", person_id, db_path=db_path)[0]


def test_explicit_system_mapping_is_honored_without_related_system_expansion(db_path):
    person_id = _person(db_path)
    _add(
        "health_entries",
        person_id,
        {"title": "Lung note", "entry_date": "2026-01-01", "body_system": "Respiratory"},
        db_path,
    )

    assert len(get_records_for_body_part(person_id, "lungs", db_path)) == 1
    assert get_records_for_body_part(person_id, "heart", db_path) == []


def test_explicit_body_part_does_not_expand_to_organs_sharing_its_system(db_path):
    person_id = _person(db_path)
    _add(
        "health_entries",
        person_id,
        {"title": "Thyroid note", "entry_date": "2026-01-01", "body_part": "Thyroid"},
        db_path,
    )

    assert len(get_records_for_body_part(person_id, "thyroid", db_path)) == 1
    assert get_records_for_body_part(person_id, "pancreas", db_path) == []


def test_explicit_cross_system_record_appears_once_under_each_part(db_path):
    person_id = _person(db_path)
    record_id = _add(
        "health_entries",
        person_id,
        {
            "title": "Cardiopulmonary follow-up",
            "entry_date": "2026-01-01",
            "body_part": "Heart, Lungs",
            "body_system": "Cardiovascular, Respiratory",
        },
        db_path,
    )

    for body_part in ("heart", "lungs"):
        records = get_records_for_body_part(person_id, body_part, db_path)
        assert [record.record_id for record in records] == [record_id]
        assert records[0].body_parts == ("heart", "lungs")
        assert records[0].body_systems == ("cardiovascular", "respiratory")


@pytest.mark.parametrize(
    ("table", "data", "body_part"),
    [
        ("lab_results", {"test_name": "LDL", "lab_date": "2026-01-01"}, "heart"),
        ("medications", {"name": "LDL", "status": "Active"}, "heart"),
        ("health_entries", {"title": "Entry", "entry_date": "2026-01-01", "body_part": "Heart"}, "heart"),
        ("appointments", {"title": "LDL", "appointment_date": "2026-01-01"}, "heart"),
        ("wearable_records", {"metric_type": "Glucose", "value": 100, "timestamp": "2026-01-01T10:00:00"}, "pancreas"),
    ],
)
def test_each_existing_record_type_is_normalized(table, data, body_part, db_path):
    person_id = _person(db_path)
    record_id = _add(table, person_id, data, db_path)

    record = get_records_for_body_part(person_id, body_part, db_path)[0]

    assert isinstance(record, NormalizedBodyRecord)
    assert (record.source_table, record.record_id, record.person_id) == (table, record_id, person_id)


def test_normalized_shape_and_missing_optional_fields(db_path):
    person_id = _person(db_path)
    _add("lab_results", person_id, {"test_name": "LDL", "lab_date": "2026-01-01"}, db_path)

    record = get_records_for_body_part(str(person_id), "heart", db_path)[0]

    assert {field.name for field in fields(record)} == {
        "record_id", "person_id", "source_table", "record_type", "name", "display_name", "date",
        "value", "unit", "status_flag", "reference_range", "body_parts", "body_systems",
        "relevance_type", "relationship_strength", "mapping_source", "mapping_confidence",
        "summary_text", "raw_record",
    }
    assert record.value is record.unit is record.status_flag is record.reference_range is record.summary_text is None
    assert record.body_parts == ("heart",)
    assert record.body_systems == ("cardiovascular",)


def test_different_source_records_are_not_collapsed(db_path):
    person_id = _person(db_path)
    _add("lab_results", person_id, {"test_name": "LDL", "lab_date": "2026-01-01"}, db_path)
    _add("appointments", person_id, {"title": "LDL", "appointment_date": "2026-01-01"}, db_path)

    assert len(get_records_for_body_part(person_id, "heart", db_path)) == 2


def test_invalid_body_part_id_is_rejected(db_path):
    with pytest.raises(ValueError, match="Unknown body part ID"):
        get_records_for_body_part(1, "chest", db_path)


def test_valid_body_part_with_no_records_returns_empty_list(db_path):
    person_id = _person(db_path)
    assert get_records_for_body_part(person_id, "brain", db_path) == []


def test_database_error_is_not_reported_as_no_data(db_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(body_map_services.services, "list_items", fail)
    with pytest.raises(RuntimeError, match="database unavailable"):
        get_records_for_body_part(1, "heart", db_path)
