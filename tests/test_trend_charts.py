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


def test_lab_trend_frame_carries_unit_through_from_the_record_page(app_db, monkeypatch):
    """The app page must hand `build_trend_chart` the unit column the mixed-unit split depends on.

    The split itself is covered by
    `test_condition_charts.py::test_the_trend_line_does_not_join_readings_stored_in_different_units`.
    This has to prove the *page* supplies what that split needs, so it renders the real page and
    captures the frame the renderer actually received. Rebuilding the frame from `filter_labs`
    instead would pass even if `app.render_trend_chart` dropped the unit -- the failure it exists to
    catch. The rendered Vega spec is no good for this: it refers to its data by name and Streamlit
    ships the rows separately, so no unit is readable from the spec at all.
    """
    person_id = _person(app_db)
    _lab(app_db, person_id, lab_date="2026-01-05", numeric_value=5.6, unit="mIU/L")
    _lab(app_db, person_id, lab_date="2026-02-05", numeric_value=7.3, unit="pmol/L")

    received = []
    original = condition_charts.build_trend_chart
    monkeypatch.setattr(
        condition_charts,
        "build_trend_chart",
        lambda frame, *args, **kwargs: (received.append(frame), original(frame, *args, **kwargs))[1],
    )

    test_app = _run_page("Labs")

    assert not test_app.exception
    assert received, "the Labs page rendered no trend chart"
    assert sorted(received[0]["unit"]) == ["mIU/L", "pmol/L"], (
        f"the page did not carry both units into the chart: {received[0].columns.tolist()}"
    )


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


def test_csv_import_does_not_let_pandas_round_a_result_before_the_parser_sees_it(app_db):
    """The number that reaches `parse_plain_decimal` must be the one in the file.

    `pd.read_csv` infers a dtype per column, and its C parser reads "0.000000000000000001" as 0.0.
    A trace-level result would import, chart and export as zero -- a wrong reading, not a missing one.
    """
    import io

    import imports_exports

    person_id = _person(app_db)
    # Both rows numeric, so the column infers as float64. A single non-numeric row would keep it
    # text and hide the bug, which is what makes this defect depend on the rest of the file.
    csv = (
        "test_name,result_value,numeric_value,unit,flag,lab_date\n"
        "Trace,0.000000000000000001,,mg/dL,Normal,2026-01-05\n"
        "TSH,5.6,,mIU/L,Normal,2026-01-06\n"
    )

    result = imports_exports.import_labs_csv(io.StringIO(csv), person_id, db_path=app_db)

    assert result["imported"] == 2
    labs = {row["test_name"]: row for row in services.filter_labs(person_id, db_path=app_db)}
    assert labs["Trace"]["numeric_value"] == 1e-18
    # The written result is preserved verbatim too; inference rewrote this to "0.0".
    assert labs["Trace"]["result_value"] == "0.000000000000000001"
    assert labs["TSH"]["numeric_value"] == 5.6


def test_csv_import_refuses_exponent_notation_exactly_as_the_form_does(app_db):
    """Type inference made the CSV path more permissive than the UI form for the same string.

    Inference turned "1e-3" into 0.001, which then satisfied the plain-decimal allowlist that the
    form rejects. Two entry paths disagreeing about what a lab value is defeats the point of the
    allowlist.
    """
    import io

    import imports_exports

    person_id = _person(app_db)
    csv = (
        "test_name,result_value,numeric_value,unit,flag,lab_date\n"
        "Exp,1e-3,,mg/dL,Normal,2026-01-05\n"
        "TSH,5.6,,mIU/L,Normal,2026-01-06\n"
    )

    result = imports_exports.import_labs_csv(io.StringIO(csv), person_id, db_path=app_db)

    assert result["imported"] == 2
    labs = {row["test_name"]: row for row in services.filter_labs(person_id, db_path=app_db)}
    assert labs["Exp"]["numeric_value"] is None
    assert app.clean_payload("lab_results", {"result_value": "1e-3", "numeric_value": ""})["numeric_value"] is None


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


def test_only_the_selected_profile_reaches_the_body_map_trend_chart(app_db):
    """Isolation must survive the whole path, not just the query.

    `test_body_map_services.test_retrieval_returns_only_selected_person_records` pins the retrieval
    query. This pins the stage this change added: real rows for two profiles, through real retrieval,
    through `rows_by_source_table` into `trend_frame`. Every other body-map trend test monkeypatches
    `get_records_for_body_part`, so a leak introduced between retrieval and the chart -- a helper that
    re-queries unscoped, or a `raw_record` carrying the wrong row -- would not be caught by any of them.
    """
    import body_map_ui
    from body_map_services import get_records_for_body_part

    selected = _person(app_db, "Selected Person")
    other = _person(app_db, "Other Person")
    # "LDL" is a curated heart mapping, so both rows are genuinely retrievable for this body part.
    _lab(app_db, selected, test_name="LDL", numeric_value=101.0, result_value="101", unit="mg/dL")
    _lab(app_db, other, test_name="LDL", numeric_value=202.0, result_value="202", unit="mg/dL")

    records = get_records_for_body_part(selected, "heart", app_db)
    frame = condition_charts.trend_frame(body_map_ui.rows_by_source_table(records))

    assert frame["value"].tolist() == [101.0]
    assert 202.0 not in set(frame["value"]), "the other profile's reading reached the chart"


def test_csv_import_keeps_a_written_result_that_pandas_reads_as_missing(app_db):
    """"NA" and "NULL" are results a person can write; pandas treats them as absent.

    Blanking them is silent loss rather than a reported skip: `validate_lab` requires `test_name` and
    `lab_date` but returns no error for an empty `result_value`, so the row imports looking complete.
    """
    import io

    import imports_exports

    person_id = _person(app_db)
    csv = (
        "test_name,result_value,numeric_value,unit,flag,lab_date\n"
        "NotApplicable,NA,,mg/dL,Normal,2026-01-05\n"
        "NullResult,NULL,,mg/dL,Normal,2026-01-06\n"
    )

    result = imports_exports.import_labs_csv(io.StringIO(csv), person_id, db_path=app_db)

    assert result["imported"] == 2
    labs = {row["test_name"]: row for row in services.filter_labs(person_id, db_path=app_db)}
    assert labs["NotApplicable"]["result_value"] == "NA"
    assert labs["NullResult"]["result_value"] == "NULL"
    # Neither is a number, so the chart still has nothing to plot -- but the record kept what it said.
    assert labs["NotApplicable"]["numeric_value"] is None
    assert labs["NullResult"]["numeric_value"] is None


def test_csv_import_still_accepts_na_in_the_coded_and_numeric_columns(app_db):
    """`keep_default_na=False` must not turn a tolerant import into a rejecting one.

    "NA"/"NULL" in a flag, unit or numeric column is how exported CSVs spell "nothing here". Reading
    them literally makes `validate_lab` reject the row -- `valid_choice` on the flag, `valid_number`
    on the value -- so a file that used to import would come back entirely as `skipped`.
    """
    import io

    import imports_exports

    person_id = _person(app_db)
    csv = (
        "test_name,result_value,numeric_value,unit,flag,lab_date\n"
        "TSH,5.6,,mIU/L,NA,2026-01-05\n"
        "LDL,120,NA,mg/dL,NULL,2026-01-06\n"
    )

    result = imports_exports.import_labs_csv(io.StringIO(csv), person_id, db_path=app_db)

    assert result["skipped"] == []
    assert result["imported"] == 2
    labs = {row["test_name"]: row for row in services.filter_labs(person_id, db_path=app_db)}
    # Read as absent, not stored as the literal token.
    assert not labs["TSH"]["flag"]
    assert not labs["LDL"]["flag"]
    # ...while the written result keeps its own reading, and still derives a number.
    assert labs["TSH"]["result_value"] == "5.6"
    assert labs["TSH"]["numeric_value"] == 5.6
    assert labs["LDL"]["numeric_value"] == 120.0


def test_csv_na_tokens_still_cover_the_pandas_defaults():
    """`import_labs_csv` replaces pandas' NA handling, so its token set must not fall behind it.

    Every token pandas would have read as missing has to still read as missing, or a file that
    imported before this change comes back as `skipped`. Imports the private constant here rather
    than in `imports_exports`, so a pandas upgrade that moves it fails a test run instead of taking
    the app down at import time.
    """
    from pandas._libs.parsers import STR_NA_VALUES

    import imports_exports

    uncovered = {t for t in STR_NA_VALUES if t not in imports_exports._CSV_NA_TOKENS}
    extra = {t for t in imports_exports._CSV_NA_TOKENS if t not in STR_NA_VALUES}

    assert not uncovered, f"pandas reads these as missing and the lab import no longer does: {sorted(uncovered)}"
    # Both directions: a token pandas would have kept literal must not be blanked here either.
    assert not extra, f"the lab import blanks these and pandas would not: {sorted(extra)}"


@pytest.mark.parametrize("token", ["<NA>", "#NA", "-NaN", "1.#IND", "#N/A N/A", "NULL", "n/a"])
def test_every_pandas_na_token_still_imports_as_absent(app_db, token):
    """One parametrized case per token, because the set is only correct if each member behaves."""
    import io

    import imports_exports

    person_id = _person(app_db)
    csv = f"test_name,result_value,numeric_value,unit,flag,lab_date\nTSH,5.6,{token},mIU/L,,2026-01-05\n"

    result = imports_exports.import_labs_csv(io.StringIO(csv), person_id, db_path=app_db)

    assert result["skipped"] == [], f"{token!r} in a numeric column now rejects the row"
    # Absent, then derived from the written result -- not rejected, and not stored as the token.
    assert services.filter_labs(person_id, db_path=app_db)[0]["numeric_value"] == 5.6


def test_editing_an_existing_lab_does_not_backfill_its_numeric_value():
    """README: "existing records are never rewritten."

    `clean_payload` runs on the edit path too, so deriving there would mean opening a legacy lab to
    fix a typo in its notes also invented a `numeric_value` the person never entered.
    """
    payload = {"result_value": "5.6", "numeric_value": "", "notes": "corrected"}

    edited = app.clean_payload("lab_results", payload, derive_numeric_value=False)
    created = app.clean_payload("lab_results", payload)

    assert edited["numeric_value"] is None, "editing a record backfilled a value it did not have"
    assert created["numeric_value"] == 5.6, "new entries must still derive it"


@pytest.mark.parametrize("test_name", ["Na", "none", "NONE", "nA"])
def test_a_lab_named_like_an_na_token_still_imports(app_db, test_name):
    """"Na" is sodium. Case-folding the NA comparison silently deleted its test name.

    `validate_lab` requires a test name, so the blanked row was rejected outright: a sodium panel
    would not import at all. Pandas matches its missing-value tokens case-sensitively and "Na",
    "none" and "NONE" are not among them.
    """
    import io

    import imports_exports

    person_id = _person(app_db)
    csv = f"test_name,result_value,numeric_value,unit,flag,lab_date\n{test_name},140,,mmol/L,Normal,2026-01-05\n"

    result = imports_exports.import_labs_csv(io.StringIO(csv), person_id, db_path=app_db)

    assert result["skipped"] == [], f"a lab named {test_name!r} no longer imports"
    stored = services.filter_labs(person_id, db_path=app_db)[0]
    assert stored["test_name"] == test_name
    assert stored["numeric_value"] == 140.0


def test_a_boolean_numeric_cell_is_reported_rather_than_stored_as_one(app_db):
    """Deliberate behavior change, pinned so it is a decision rather than an accident.

    The merge-base importer let pandas infer `True` as a boolean and stored the lab reading `1.0`.
    That is a fabricated measurement. Reading the column as text means it now fails `valid_number`
    and the row is reported in `skipped`, which is the visible outcome rather than the silent one.
    """
    import io

    import imports_exports

    person_id = _person(app_db)
    csv = "test_name,result_value,numeric_value,unit,flag,lab_date\nX,5.6,True,mg/dL,Normal,2026-01-05\n"

    result = imports_exports.import_labs_csv(io.StringIO(csv), person_id, db_path=app_db)

    assert result["imported"] == 0
    assert len(result["skipped"]) == 1
    assert "Numeric value" in result["skipped"][0]["errors"][0]
    assert services.filter_labs(person_id, db_path=app_db) == []


def test_saving_the_edit_form_does_not_backfill_a_legacy_lab(app_db):
    """Drives the real edit form, because the call site is what has to pass the flag.

    Asserting on `clean_payload(derive_numeric_value=False)` directly proves only that the parameter
    works -- deleting the argument at the `services.update_item` call site would leave that green.
    This opens a legacy row in the Labs edit form and saves it unchanged.
    """
    person_id = _person(app_db)
    # Written through `db` directly: a row from before derivation existed, so no number was stored.
    db.create_record(
        "lab_results",
        {"person_id": person_id, "test_name": "TSH", "result_value": "5.6", "unit": "mIU/L", "lab_date": "2026-01-05"},
        db_path=app_db,
    )
    record_id = services.filter_labs(person_id, db_path=app_db)[0]["id"]

    test_app = _run_page("Labs")
    selector = next(box for box in test_app.get("selectbox") if ":edit:selection:" in (box.key or ""))
    selector.select(str(record_id)).run(timeout=60)
    save = next(button for button in test_app.get("button") if "Save changes" in (button.label or ""))
    save.click().run(timeout=60)

    assert not test_app.exception
    stored = services.filter_labs(person_id, db_path=app_db)[0]
    assert stored["numeric_value"] is None, "saving the edit form backfilled a stored record"
    assert stored["result_value"] == "5.6"


def _fill(test_app, suffix, value):
    """Set an add-form field by its key suffix; the full key carries the db path and profile id."""

    widget = next(item for item in test_app.get("text_input") if (item.key or "").endswith(f":add:{suffix}"))
    widget.set_value(value)


@pytest.mark.parametrize(
    "written, expected",
    [("5.6", 5.6), ("Positive", None), ("<0.01", None), ("0", 0.0)],
)
def test_the_add_form_derives_a_number_only_from_an_unambiguous_result(app_db, written, expected):
    """Drives the real Labs add form, because the call site is what has to derive.

    `clean_payload` is also tested directly, but that proves the helper works -- disabling
    derivation at the `services.create_item` call site would leave that green.
    """
    _person(app_db)

    test_app = _run_page("Labs")
    next(b for b in test_app.get("button") if "Add Lab" in (b.label or "")).click().run(timeout=60)
    _fill(test_app, "test_name", "TSH")
    _fill(test_app, "result_value", written)
    _fill(test_app, "lab_date", "2026-01-05")
    next(b for b in test_app.get("button") if "Add record" in (b.label or "")).click().run(timeout=60)

    assert not test_app.exception
    stored = services.filter_labs(1, db_path=app_db)
    assert len(stored) == 1, f"the add form did not store the record: {stored}"
    assert stored[0]["numeric_value"] == expected
    assert stored[0]["result_value"] == written


def test_a_fhir_boolean_quantity_does_not_become_a_lab_reading(app_db):
    """`float(True)` is 1.0. The CSV path already refuses "True"; FHIR must not disagree.

    `fhir._lab_from_observation` normalizes before validation, so the boolean was already the number
    1.0 by the time `validate_lab` saw it -- and the body map now charts `numeric_value`.
    """
    import fhir

    person_id = _person(app_db)
    observation = {
        "resourceType": "Observation",
        "category": [{"coding": [{"code": "laboratory"}]}],
        "code": {"text": "TSH"},
        "valueQuantity": {"value": True, "unit": "mIU/L"},
        "effectiveDateTime": "2026-01-05",
    }

    _table, data = fhir._local_record_from_resource(observation)

    assert data["numeric_value"] is None, "a boolean quantity was recorded as a measurement"
    # The record still keeps what the source said; only the invented number is refused.
    assert data["result_value"] == "True"
    assert services.filter_labs(person_id, db_path=app_db) == []


@pytest.mark.parametrize("field", ["test_name", "unit"])
def test_a_whitespace_padded_na_token_is_kept_verbatim(app_db, field):
    """Pandas does not strip before matching its NA tokens, so neither may this.

    Stripping first looked like harmless tolerance and blanked a value the merge-base importer kept.
    """
    import io

    import imports_exports

    person_id = _person(app_db)
    columns = {"test_name": "TSH", "result_value": "5.6", "numeric_value": "", "unit": "mIU/L",
               "flag": "Normal", "lab_date": "2026-01-05"}
    columns[field] = " NA "
    header = ",".join(columns)
    csv = f"{header}\n" + ",".join(f'"{value}"' for value in columns.values()) + "\n"

    result = imports_exports.import_labs_csv(io.StringIO(csv), person_id, db_path=app_db)

    assert result["skipped"] == []
    assert services.filter_labs(person_id, db_path=app_db)[0][field] == " NA "


def test_the_add_form_does_not_invent_a_normal_flag(app_db):
    """The app must never state a clinical assessment no source made.

    The flag select had no blank option, so `input_field` fell to index 0 and stored "Normal" for a
    result nobody flagged. `FLAG_CAPTION` tells the reader that point colour is "the flag recorded
    by the source, not an assessment by this app" -- which was untrue for every form-entered record.
    A fabricated "Normal" is the more dangerous direction: it reads as reassurance.
    """
    _person(app_db)

    test_app = _run_page("Labs")
    next(b for b in test_app.get("button") if "Add Lab" in (b.label or "")).click().run(timeout=60)
    _fill(test_app, "test_name", "TSH")
    _fill(test_app, "result_value", "5.6")
    _fill(test_app, "lab_date", "2026-01-05")
    next(b for b in test_app.get("button") if "Add record" in (b.label or "")).click().run(timeout=60)

    assert not test_app.exception
    stored = services.filter_labs(1, db_path=app_db)[0]
    assert not stored["flag"], f"the form invented the source flag {stored['flag']!r}"


def test_editing_an_unflagged_lab_does_not_stamp_it_normal(app_db):
    """The same default also rewrote an imported record: opening it to edit stored "Normal"."""
    person_id = _person(app_db)
    db.create_record(
        "lab_results",
        {"person_id": person_id, "test_name": "TSH", "result_value": "5.6", "numeric_value": 5.6,
         "unit": "mIU/L", "lab_date": "2026-01-05"},
        db_path=app_db,
    )
    record_id = services.filter_labs(person_id, db_path=app_db)[0]["id"]

    test_app = _run_page("Labs")
    selector = next(box for box in test_app.get("selectbox") if ":edit:selection:" in (box.key or ""))
    selector.select(str(record_id)).run(timeout=60)
    next(b for b in test_app.get("button") if "Save changes" in (b.label or "")).click().run(timeout=60)

    assert not test_app.exception
    assert not services.filter_labs(person_id, db_path=app_db)[0]["flag"]


def test_the_missing_number_caption_does_not_ask_for_a_number_that_does_not_exist():
    """The caption used to instruct the reader to defeat the parser's own protection.

    "Enter the number in 'Numeric Result'" applied to every uncharted lab, including `Positive` and
    `<0.01` -- so following it meant recording a precision the source explicitly withheld, which is
    the fabrication `parse_plain_decimal` exists to prevent.
    """
    caption = condition_charts.missing_numeric_value_caption(3)

    assert "where the source reported a number" in caption
    assert "<0.01" in caption, "the caption must name a censored result as having no number to chart"


def test_the_wearables_page_renders_a_chartable_series_through_the_shared_renderer(app_db, monkeypatch):
    """The positive counterpart to the unchartable-row test, which alone would stay green if the
    page were reverted to `st.line_chart` or stopped passing units."""
    person_id = _person(app_db)
    _wearable(app_db, person_id, timestamp="2026-01-05", value=232.0, unit="lb")
    _wearable(app_db, person_id, timestamp="2026-02-05", value=93.0, unit="kg")

    received = []
    original = condition_charts.build_trend_chart
    monkeypatch.setattr(
        condition_charts,
        "build_trend_chart",
        lambda frame, *args, **kwargs: (received.append(frame), original(frame, *args, **kwargs))[1],
    )

    test_app = _run_page("Wearables")

    assert not test_app.exception
    assert received, "the Wearables page did not render through the shared trend renderer"
    # The defect that motivated this change: one series in two units must not become one line.
    assert sorted(received[0]["unit"]) == ["kg", "lb"]


def test_only_the_selected_profile_reaches_the_wearables_chart(app_db, monkeypatch):
    """AGENTS.md section 10: any profile-scoped feature needs a second-profile test.

    The body-map trend path has one; the Wearables page is the other surface this change rewired,
    and its readings are as identifying as any lab.
    """
    selected = _person(app_db, "Selected Person")
    other = _person(app_db, "Other Person")
    _wearable(app_db, selected, timestamp="2026-01-05", value=180.0, unit="lb")
    _wearable(app_db, other, timestamp="2026-01-05", value=999.0, unit="lb")

    received = []
    original = condition_charts.build_trend_chart
    monkeypatch.setattr(
        condition_charts,
        "build_trend_chart",
        lambda frame, *args, **kwargs: (received.append(frame), original(frame, *args, **kwargs))[1],
    )

    # The sidebar selectbox is keyed by profile *label*, not id: setting it to "1" selects nothing
    # and the page falls back to whichever profile sorts first, which is the other one here.
    label = app.profile_selection_label(services.get_person(selected, db_path=app_db), app_db)
    test_app = _run_page("Wearables", selected_profile=label)

    assert not test_app.exception
    assert received, "the Wearables page rendered no trend chart"
    assert received[0]["value"].tolist() == [180.0]
    assert 999.0 not in set(received[0]["value"]), "the other profile's reading reached the chart"
