from __future__ import annotations

from copy import deepcopy

import pytest

from body_map_services import NormalizedBodyRecord
from body_map_summary import summarize_body_part_health


def _record(
    record_id: int = 1,
    *,
    name: str = "LDL",
    record_type: str = "lab",
    source_table: str = "lab_results",
    date: str | None = "2026-01-01",
    flag: str | None = None,
    value: object = None,
    confidence: str = "high",
) -> NormalizedBodyRecord:
    return NormalizedBodyRecord(
        record_id=record_id,
        person_id=1,
        source_table=source_table,
        record_type=record_type,
        name=name,
        display_name=name,
        date=date,
        value=value,
        unit=None,
        status_flag=flag,
        reference_range=None,
        body_parts=("heart",),
        body_systems=("cardiovascular",),
        relevance_type="risk_marker",
        relationship_strength="primary",
        mapping_source="curated_default",
        mapping_confidence=confidence,
        summary_text=None,
        raw_record={"id": record_id},
    )


def test_empty_records_return_no_data():
    summary = summarize_body_part_health([])

    assert summary.status_label == "No data"
    assert summary.latest_records == ()
    assert summary.latest_relevant_date is None


def test_records_without_flags_return_data_available():
    assert summarize_body_part_health([_record()]).status_label == "Data available"
    assert summarize_body_part_health([_record(flag="unknown")]).status_label == "Data available"


def test_current_flagged_record_returns_needs_review():
    summary = summarize_body_part_health([_record(flag="high")])

    assert summary.status_label == "Needs review"
    assert summary.current_flagged_records == summary.latest_records
    assert summary.status_reason == "1 latest relevant record is source-flagged high."


def test_newer_unflagged_record_preserves_old_flag_as_historical():
    older = _record(1, date="2025-01-01", flag="high")
    newer = _record(2, date="2026-01-01")

    summary = summarize_body_part_health([older, newer])

    assert summary.status_label == "Historical flag found"
    assert summary.latest_records == (newer,)
    assert summary.current_flagged_records == ()
    assert summary.historical_flagged_records == (older,)


def test_no_flagged_items_when_usable_flags_are_normal():
    assert summarize_body_part_health([_record(flag="within range")]).status_label == "No flagged items"


def test_uncertain_mappings_return_mapping_uncertain():
    summary = summarize_body_part_health([_record(confidence="low", flag="high")])

    assert summary.status_label == "Mapping uncertain"
    assert summary.current_flagged_records
    assert "source-flagged high" in summary.status_reason


def test_mixed_mapping_confidence_keeps_reliable_status_and_surfaces_uncertainty():
    reliable = _record(1, flag="normal")
    uncertain = _record(2, name="HDL", confidence="low")

    summary = summarize_body_part_health([reliable, uncertain])

    assert summary.status_label == "No flagged items"
    assert summary.uncertain_mapping_records == (uncertain,)
    assert "low-confidence mapping" in summary.status_reason


def test_latest_record_is_selected_per_comparable_key():
    older = _record(1, date="2024-01-01", flag="normal")
    newer = _record(2, date="2025-01-01", flag="normal")

    assert summarize_body_part_health([older, newer]).latest_records == (newer,)


def test_different_tests_are_not_grouped_together():
    ldl = _record(1, name="LDL", date="2025-01-01", flag="high")
    hdl = _record(2, name="HDL", date="2026-01-01", flag="normal")

    summary = summarize_body_part_health([ldl, hdl])

    assert summary.latest_records == (hdl, ldl)
    assert summary.current_flagged_records == (ldl,)
    assert summary.historical_flagged_records == ()


@pytest.mark.parametrize("flag", ["high", "H", "HIGH", "low", "L", "abnormal", "critical"])
def test_source_flag_variants_are_normalized(flag):
    assert summarize_body_part_health([_record(flag=flag)]).status_label == "Needs review"


@pytest.mark.parametrize("flag", [None, "", "unknown", "active", "completed"])
def test_blank_unknown_and_workflow_statuses_are_not_abnormal(flag):
    assert summarize_body_part_health([_record(flag=flag)]).status_label == "Data available"


def test_positive_is_abnormal_only_for_lab_source_flags():
    lab = summarize_body_part_health([_record(flag="positive")])
    appointment = summarize_body_part_health(
        [_record(flag="positive", source_table="appointments", record_type="appointment")]
    )

    assert lab.status_label == "Needs review"
    assert appointment.status_label == "Data available"


def test_raw_values_do_not_create_abnormal_flags():
    assert summarize_body_part_health([_record(value=999999)]).status_label == "Data available"


def test_missing_dates_do_not_crash_or_become_current():
    missing = _record(1, date=None, flag="high")
    malformed = _record(2, name="HDL", date="not-a-date")

    summary = summarize_body_part_health([missing, malformed])

    assert summary.status_label == "Needs review"
    assert summary.latest_records == summary.current_flagged_records == summary.historical_flagged_records == ()
    assert summary.chronology_unknown_records == (malformed, missing)
    assert "unknown chronology" in summary.status_reason


def test_records_are_sorted_newest_first():
    oldest = _record(1, name="LDL", date="2024-01-01")
    newest = _record(2, name="HDL", date="2026-01-01T10:00:00Z")
    middle = _record(3, name="CRP", date="2025-01-01")

    summary = summarize_body_part_health([oldest, newest, middle])

    assert summary.latest_records == (newest, middle, oldest)
    assert summary.latest_relevant_date == "2026-01-01T10:00:00Z"


def test_record_counts_by_type_are_correct():
    summary = summarize_body_part_health(
        [_record(1), _record(2, name="HDL"), _record(3, name="Visit", record_type="appointment")]
    )

    assert summary.record_counts_by_type == {"appointment": 1, "lab": 2}


def test_summary_language_is_non_diagnostic():
    reason = summarize_body_part_health([_record(flag="critical")]).status_reason.casefold()

    assert "source-flagged" in reason
    assert not {"healthy", "unhealthy", "diagnosis", "treatment"} & set(reason.split())


def test_summary_does_not_mutate_input():
    records = [_record(1, flag="high"), _record(2, date=None)]
    before = deepcopy(records)

    summarize_body_part_health(records)

    assert records == before
