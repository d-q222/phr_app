"""Tests for the trend-chart wiring at the `app.py` record pages, and the strict lab-value parser.

The chart assertions here deliberately do **not** count `vega_lite_chart` elements. `st.line_chart` --
the code these sites used before -- renders as a `vega_lite_chart` too, so a count-based assertion
passes against the unchanged app and proves nothing. These assert on the rendered spec instead: the
new chart is a layered spec carrying `color`/`shape` encodings bound to `flag`.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app  # noqa: E402
import body_map_summary  # noqa: E402
import condition_charts  # noqa: E402
import db  # noqa: E402
import services  # noqa: E402
import validation  # noqa: E402
from body_map_services import NormalizedBodyRecord  # noqa: E402
from models import APPOINTMENT_STATUSES, LAB_FLAGS, MEDICATION_STATUSES  # noqa: E402


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    path = tmp_path / "trends.db"
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db(path)
    return path


def _person(app_db, name="Fictional Person"):
    return services.create_person({"name": name}, db_path=app_db)


def _lab(app_db, person_id, **overrides):
    data = {
        "test_name": "TSH",
        "result_value": "5.6",
        "numeric_value": 5.6,
        "unit": "mIU/L",
        "flag": "High",
        "lab_date": "2026-01-05",
    }
    return services.create_item("lab_results", person_id, data | overrides, db_path=app_db)


def _wearable(app_db, person_id, **overrides):
    data = {"metric_type": "Weight", "value": 232.0, "unit": "lb", "timestamp": "2026-01-05"}
    return services.create_item("wearable_records", person_id, data | overrides, db_path=app_db)


def _run_page(page, **session):
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = page
    for key, value in session.items():
        test_app.session_state[key] = value
    test_app.run(timeout=60)
    return test_app


def _chart_specs(test_app):
    """Rendered Vega-Lite specs. `.spec` is a JSON string, so it is parsed here rather than compared raw."""

    return [json.loads(chart.spec) for chart in test_app.get("vega_lite_chart")]


def _binds_flag(layer):
    # `tooltip` and friends are lists rather than dicts, so never assume a mapping here.
    encoding = layer.get("encoding", {})
    return any(
        isinstance(encoding.get(channel), dict) and encoding[channel].get("field") == "flag"
        for channel in ("color", "shape")
    )


def _flag_encoded_specs(test_app):
    """Specs whose layers bind colour or shape to the stored flag -- what `st.line_chart` cannot do."""

    return [spec for spec in _chart_specs(test_app) if any(_binds_flag(layer) for layer in spec.get("layer", []))]


# --- the app.py record pages ----------------------------------------------------------------------


def test_lab_trend_chart_encodes_the_stored_flag(app_db):
    """Catches the lab page silently discarding `flag`, which `st.line_chart` did for every reading."""
    person_id = _person(app_db)
    _lab(app_db, person_id, lab_date="2026-01-05", numeric_value=8.4, flag="High")
    _lab(app_db, person_id, lab_date="2026-04-05", numeric_value=3.1, flag="Normal")

    test_app = _run_page("Labs")

    assert not test_app.exception
    assert _flag_encoded_specs(test_app), "the lab trend chart is not encoding the source flag"


def test_wearable_summary_still_renders_when_no_wearable_row_is_chartable(app_db):
    """Catches gating the whole wearable block on `frame.empty` instead of on `rows`.

    `validate_wearable` only requires a timestamp to be present, not parseable, so this row is
    storable but unchartable -- and the summary describes it regardless.
    """
    person_id = _person(app_db)
    _wearable(app_db, person_id, timestamp="not a date")

    test_app = _run_page("Wearables")

    assert not test_app.exception
    assert not _chart_specs(test_app), "an unchartable row should produce no trend chart"
    # "Latest Timestamp" belongs to `services.wearable_summary` alone -- the raw record table beside
    # it has a plain "Timestamp" -- so this distinguishes the summary from the record listing.
    rendered = [list(frame.value.columns) for frame in test_app.get("dataframe")]
    assert any("Latest Timestamp" in columns for columns in rendered), (
        f"the wearable summary disappeared with the chart; rendered tables were {rendered}"
    )


def test_lab_trend_frame_carries_unit_through_from_the_record_page(app_db):
    """The app page must hand `trend_frame` the unit column the mixed-unit split depends on.

    The split itself is already covered by
    `test_condition_charts.py::test_the_trend_line_does_not_join_readings_stored_in_different_units`;
    this covers only that this call site supplies what that split needs.
    """
    person_id = _person(app_db)
    _lab(app_db, person_id, unit="mIU/L")
    rows = services.filter_labs(person_id, db_path=app_db)

    frame = condition_charts.trend_frame({"lab_results": rows})

    assert frame["unit"].tolist() == ["mIU/L"]


def test_lab_trend_excludes_records_without_a_parseable_date_or_numeric_value(app_db):
    """Successor to the deleted `numeric_trends` no-fabrication test.

    Rows are written through `db` directly because the UI validators reject both of these.
    """
    person_id = _person(app_db)
    _lab(app_db, person_id, test_name="Chartable", numeric_value=4.2)
    db.create_record(
        "lab_results",
        {"person_id": person_id, "test_name": "No number", "result_value": "Positive", "lab_date": "2026-02-01"},
        db_path=app_db,
    )
    db.create_record(
        "lab_results",
        {"person_id": person_id, "test_name": "Bad date", "numeric_value": 3.0, "lab_date": "not a date"},
        db_path=app_db,
    )
    rows = services.filter_labs(person_id, db_path=app_db)

    frame = condition_charts.trend_frame({"lab_results": rows})

    assert sorted(frame["record"].unique()) == ["Chartable"]


def test_a_zero_numeric_value_is_charted_rather_than_treated_as_absent(app_db):
    """`0` is falsy; a truthiness check anywhere in this path would drop a real reading."""
    person_id = _person(app_db)
    _lab(app_db, person_id, test_name="Zeroed", numeric_value=0.0, result_value="0")
    rows = services.filter_labs(person_id, db_path=app_db)

    frame = condition_charts.trend_frame({"lab_results": rows})

    assert frame["value"].tolist() == [0.0]


def test_labs_missing_a_numeric_value_are_explained_rather_than_silently_dropped(app_db):
    person_id = _person(app_db)
    _lab(app_db, person_id, test_name="Chartable", numeric_value=4.2)
    db.create_record(
        "lab_results",
        {"person_id": person_id, "test_name": "Positive", "result_value": "Positive", "lab_date": "2026-02-01"},
        db_path=app_db,
    )

    test_app = _run_page("Labs")

    assert not test_app.exception
    assert any("Numeric Result" in caption.value for caption in test_app.caption)


def test_the_lab_page_says_so_when_labs_exist_but_none_are_chartable(app_db):
    """Previously this branch rendered nothing at all -- no chart and no explanation."""
    person_id = _person(app_db)
    db.create_record(
        "lab_results",
        {"person_id": person_id, "test_name": "Strep", "result_value": "Positive", "lab_date": "2026-02-01"},
        db_path=app_db,
    )

    test_app = _run_page("Labs")

    assert not test_app.exception
    assert not _chart_specs(test_app)
    assert any("No dated numeric records" in info.value for info in test_app.info)


def test_a_filled_numeric_value_survives_a_round_trip_through_storage(app_db):
    """The number the UI derives must be readable back, since the edit form defaults from the row."""
    person_id = _person(app_db)
    payload = app.clean_payload(
        "lab_results",
        {"test_name": "TSH", "result_value": "5.6", "numeric_value": "", "lab_date": "2026-01-05", "flag": "Normal"},
    )
    services.create_item("lab_results", person_id, payload, db_path=app_db)

    stored = services.filter_labs(person_id, db_path=app_db)[0]

    assert stored["numeric_value"] == 5.6
    assert stored["result_value"] == "5.6", "the written result must survive alongside the parsed number"


def test_lab_trend_chart_is_profile_scoped(app_db):
    """Profile B has no labs at all, so absence of any chart is the correct assertion here."""
    person_a = _person(app_db, "Person A")
    _person(app_db, "Person B")
    _lab(app_db, person_a, numeric_value=8.4, flag="High")

    test_app = _run_page("Labs")
    assert not test_app.exception
    charts_for_a = len(_chart_specs(test_app))

    # The sidebar selector stores the display label, not the id (app.py:868-877).
    person_b = next(person for person in services.list_people(db_path=app_db) if person["name"] == "Person B")
    test_app_b = _run_page("Labs", selected_profile=app.profile_selection_label(person_b, app_db))

    assert not test_app_b.exception
    assert charts_for_a >= 1
    assert not _chart_specs(test_app_b), "profile B has no labs but rendered a trend chart"


# --- the strict lab-value parser -------------------------------------------------------------------

PARSES = ["5.6", "5", "-2.3", "  5.6  ", "0", ".5", "5.", "+7", "0.0"]
REJECTED = [
    "<0.01", ">1000", "<=5", ">=5",           # censored / limit-of-detection
    "5.6-7.2", "5.6/7.2",                       # ranges
    "nan", "inf", "-inf", "infinity", "Infinity", "NaN",
    "5.6 mg/dL", "5.6%", "5.6mg",              # value carrying a unit
    "1,234.5", "5,6",                           # separator-ambiguous
    "５.６", "٥.٦", "１２３",                      # non-ASCII digits `float` accepts
    "1_0", "1_000.5",                           # underscore digit separators `float` accepts
    "Positive", "Not detected", "Negative", "", "   ", "--5", "5..6", "+-5",
]


@pytest.mark.parametrize("text", PARSES)
def test_strict_parse_accepts_plain_finite_decimals(text):
    assert validation.parse_plain_decimal(text) == float(text.strip())


@pytest.mark.parametrize("text", REJECTED)
def test_strict_parse_rejects_everything_that_is_not_a_plain_decimal(text):
    """A bare `try: float(...)` passes several of these -- notably the non-ASCII and underscore rows."""
    assert validation.parse_plain_decimal(text) is None


def test_censored_lab_values_never_become_numbers():
    """Storing 0.01 for "<0.01" would assert a precision the lab explicitly refused to give."""
    for censored in ("<0.01", ">1000", "< 0.01", "> 1000", "<0.01 mg/dL"):
        assert validation.parse_plain_decimal(censored) is None


def test_no_string_carrying_a_comparison_operator_parses_in_any_position():
    """Absence of the bug, not presence of the fix: every operator, anywhere in the string."""
    for operator in ("<", ">", "=", "~", "≤", "≥"):
        for candidate in (f"{operator}5.6", f"5.6{operator}", f"5{operator}6"):
            assert validation.parse_plain_decimal(candidate) is None, candidate


def test_ui_path_fills_numeric_value_from_a_numeric_result_value():
    cleaned = app.clean_payload("lab_results", {"result_value": "5.6", "numeric_value": ""})

    assert cleaned["numeric_value"] == 5.6


def test_ui_path_leaves_numeric_value_empty_for_a_written_result():
    cleaned = app.clean_payload("lab_results", {"result_value": "Positive", "numeric_value": ""})

    assert cleaned["numeric_value"] is None


def test_an_existing_numeric_value_is_never_overwritten():
    """A deliberate entry wins over the free-text field, even when the two disagree."""
    cleaned = app.clean_payload("lab_results", {"result_value": "5.6", "numeric_value": "9.9"})

    assert cleaned["numeric_value"] == 9.9


def test_a_stored_zero_is_not_treated_as_a_missing_numeric_value():
    """`0` is falsy; a truthiness check here would overwrite a real reading from the text field."""
    cleaned = app.clean_payload("lab_results", {"result_value": "5.6", "numeric_value": "0"})

    assert cleaned["numeric_value"] == 0.0


def test_csv_import_fills_numeric_value_from_a_numeric_result_value(app_db):
    import io

    import imports_exports

    person_id = _person(app_db)
    csv = "test_name,result_value,numeric_value,unit,flag,lab_date\nTSH,5.6,,mIU/L,Normal,2026-01-05\n"

    result = imports_exports.import_labs_csv(io.StringIO(csv), person_id, db_path=app_db)

    assert result["imported"] == 1
    assert services.filter_labs(person_id, db_path=app_db)[0]["numeric_value"] == 5.6


def test_csv_import_leaves_a_written_result_unparsed(app_db):
    import io

    import imports_exports

    person_id = _person(app_db)
    csv = "test_name,result_value,numeric_value,unit,flag,lab_date\nStrep,Positive,,,Abnormal,2026-01-05\n"

    result = imports_exports.import_labs_csv(io.StringIO(csv), person_id, db_path=app_db)

    assert result["imported"] == 1
    assert services.filter_labs(person_id, db_path=app_db)[0]["numeric_value"] is None


# --- edge cases that actually bite ------------------------------------------------------------------


def test_a_written_zero_fills_the_numeric_field_rather_than_reading_as_absent():
    """"0" is a real result. A truthiness check in the parser path would discard it."""
    cleaned = app.clean_payload("lab_results", {"result_value": "0", "numeric_value": ""})

    assert cleaned["numeric_value"] == 0.0


def test_same_day_readings_have_a_deterministic_order(app_db):
    """`services.list_items` returns rows id-descending, so date alone would invert first and latest."""
    person_id = _person(app_db)
    first = _lab(app_db, person_id, lab_date="2026-01-05", numeric_value=1.0, flag="High")
    second = _lab(app_db, person_id, lab_date="2026-01-05", numeric_value=2.0, flag="Low")
    rows = services.filter_labs(person_id, db_path=app_db)

    frame = condition_charts.trend_frame({"lab_results": rows})

    assert frame["row_id"].tolist() == sorted([first, second])
    assert frame["flag"].tolist() == ["High", "Low"]


def test_a_tz_aware_and_a_tz_naive_reading_can_share_one_series(app_db):
    """Mixing the two raised "Cannot compare tz-naive and tz-aware timestamps" before `_coerce_point`.

    The offset is dropped without shifting the clock, so a reading keeps the calendar day it records.
    """
    person_id = _person(app_db)
    _wearable(app_db, person_id, timestamp="2026-01-05")
    _wearable(app_db, person_id, timestamp="2026-01-06T08:00:00Z")
    rows = services.list_items("wearable_records", person_id, db_path=app_db)

    frame = condition_charts.trend_frame({"wearable_records": rows})

    assert [stamp.isoformat() for stamp in frame["date"]] == ["2026-01-05T00:00:00", "2026-01-06T08:00:00"]


def test_symptom_severity_renders_at_both_scale_boundaries():
    entries = [
        {"entry_date": "2026-01-05", "severity": 1, "title": "Mild"},
        {"entry_date": "2026-01-06", "severity": 10, "title": "Severe"},
    ]

    frame = condition_charts.severity_frame(entries)

    assert frame["severity"].tolist() == [1, 10]


def test_a_lab_page_with_no_labs_at_all_renders_no_trend_and_no_empty_state(app_db):
    """The record table above already says the page is empty; a second message would just be noise."""
    _person(app_db)

    test_app = _run_page("Labs")

    assert not test_app.exception
    assert not _chart_specs(test_app)
    assert not any("No dated numeric records" in info.value for info in test_app.info)


def test_one_series_name_shared_by_two_tables_draws_a_separate_path_per_table(app_db):
    """A clinic-measured weight and a wearable-estimated weight are two instruments, not one series.

    Both readings were always plotted; what changed is that no single line now joins them, so the
    chart stops implying the two measurements are continuous with each other.
    """
    person_id = _person(app_db)
    _lab(app_db, person_id, test_name="Weight", numeric_value=180.0, unit="lb", lab_date="2026-01-05")
    _wearable(app_db, person_id, metric_type="Weight", value=182.0, unit="lb", timestamp="2026-01-06")

    frame = condition_charts.trend_frame(
        {
            "lab_results": services.filter_labs(person_id, db_path=app_db),
            "wearable_records": services.list_items("wearable_records", person_id, db_path=app_db),
        }
    )
    detail = condition_charts.build_trend_chart(frame).to_dict()["layer"][0]["encoding"]["detail"]

    assert set(frame["table"]) == {"lab_results", "wearable_records"}
    assert [field["field"] for field in detail] == ["record", "unit", "table"]
    assert frame["value"].tolist() == [180.0, 182.0], "both readings must still be plotted"


# --- absence of the bug, not presence of the fix ---------------------------------------------------


def test_only_allowlisted_tables_can_reach_a_flag_encoding():
    """Holds for a sixth record table added later, which a medication-only test would not.

    Every table the body map normalizes is offered to `trend_frame`; only those in the allowlist may
    contribute rows, so no other table's `status` column can reach a clinical-severity legend.
    """
    import body_map_services

    rows_by_table = {
        "lab_results": [{"lab_date": "2026-01-05", "numeric_value": 5.6, "test_name": "TSH", "unit": "x", "flag": "High"}],
        "wearable_records": [{"timestamp": "2026-01-05", "value": 180.0, "metric_type": "Weight", "unit": "lb"}],
        "medications": [{"start_date": "2026-01-05", "dose": "500", "name": "Metformin", "status": "Unknown"}],
        "appointments": [{"appointment_date": "2026-01-05", "title": "Review", "status": "Completed"}],
        "health_entries": [{"entry_date": "2026-01-05", "severity": 7, "title": "Headache"}],
    }
    assert set(rows_by_table) == set(body_map_services._RECORD_ADAPTERS), (
        "a record table was added without deciding whether it may reach the trend chart"
    )

    frame = condition_charts.trend_frame(rows_by_table)

    assert set(frame["table"]) <= set(condition_charts._NUMERIC_FIELDS)
    assert "medications" not in set(frame["table"])


def test_the_flag_vocabulary_still_matches_the_lab_flag_list():
    """`FLAG_ORDER` and `LAB_FLAGS` agree today by coincidence of two separately-maintained lists.

    If they drift, the colour scale silently degrades to Vega defaults with no error anywhere.
    """
    assert condition_charts.FLAG_ORDER == LAB_FLAGS


def test_workflow_status_vocabularies_cannot_be_mistaken_for_clinical_flags():
    """Fails loudly if someone adds e.g. "Low" to `MEDICATION_STATUSES`.

    `medications.status` and `appointments.status` land in the same `NormalizedBodyRecord.status_flag`
    field as `lab_results.flag`. They cannot reach a chart today because `_NUMERIC_FIELDS` excludes
    those tables -- but `body_map_summary._flag` reads that field too, and is safe only because no
    workflow token collides with its abnormal set.
    """
    base = NormalizedBodyRecord(
        record_id=1, person_id=1, source_table="medications", record_type="medication",
        name="X", display_name="X", date="2026-01-05", value=None, unit=None,
        status_flag=None, reference_range=None, body_parts=("heart",), body_systems=("cardiovascular",),
        relevance_type="medication", relationship_strength="primary", mapping_source="stored",
        mapping_confidence="high", summary_text=None, raw_record={},
    )
    misread = {
        token
        for token in set(MEDICATION_STATUSES) | set(APPOINTMENT_STATUSES)
        if body_map_summary._flag(replace(base, status_flag=token))[0] is not None
    }

    assert not misread, f"workflow status {sorted(misread)} is being read as a clinical flag"
