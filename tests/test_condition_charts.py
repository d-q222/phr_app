"""Tests for `condition_charts`.

Every chart here is an `alt.Chart`, i.e. a declarative spec, so these assert on `chart.to_dict()`
rather than driving a browser. That is the payoff of the module importing no Streamlit: the app's
existing `st.line_chart` call sites cannot be checked this way at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import condition_charts  # noqa: E402
import db  # noqa: E402
import services  # noqa: E402
from condition_services import get_primary_series  # noqa: E402


def _labs(rows):
    return [
        {"lab_date": date, "numeric_value": value, "test_name": name, "unit": "mIU/L", "flag": flag}
        for date, value, name, flag in rows
    ]


def _wearables(rows):
    return [
        {"timestamp": stamp, "value": value, "metric_type": name, "unit": "lb"}
        for stamp, value, name in rows
    ]


SAMPLE_LABS = _labs(
    [
        ("2025-01-05", 8.4, "TSH", "High"),
        ("2025-04-05", 3.1, "TSH", "Normal"),
        ("2025-07-05", 2.4, "TSH", "Normal"),
        ("2025-10-05", 0.2, "TSH", "Low"),
    ]
)
SAMPLE_WEARABLES = _wearables([("2025-01-05T08:00:00", 232.0, "Weight"), ("2025-06-05T08:00:00", 205.0, "Weight")])
SAMPLE_RECORDS = {"lab_results": SAMPLE_LABS, "wearable_records": SAMPLE_WEARABLES}


# --- frames ---------------------------------------------------------------------------------------


def test_trend_frame_carries_flag_and_unit_and_marks_wearables_unflagged():
    frame = condition_charts.trend_frame(SAMPLE_RECORDS)

    assert list(frame.columns) == condition_charts.TREND_COLUMNS
    assert len(frame) == 6
    labs = frame[frame["table"] == "lab_results"]
    assert set(labs["flag"]) == {"High", "Normal", "Low"}
    # The schema has no flag column on wearables. Anything other than "Not flagged" here would be
    # the app assigning a status the source never recorded.
    wearables = frame[frame["table"] == "wearable_records"]
    assert set(wearables["flag"]) == {condition_charts.NOT_FLAGGED}


def test_trend_frame_skips_unusable_rows_without_raising():
    messy = {
        "lab_results": _labs(
            [
                ("not-a-date", 1.0, "TSH", "Normal"),
                ("2025-01-05", None, "TSH", "Normal"),
                ("2025-02-05", float("inf"), "TSH", "Normal"),
                ("2025-03-05", 2.0, "TSH", "Normal"),
            ]
        )
    }

    frame = condition_charts.trend_frame(messy)

    assert len(frame) == 1


def test_trend_frame_rejects_booleans_rather_than_plotting_them_as_one():
    """`float(True)` is 1.0, so a boolean would silently become a measurement."""
    frame = condition_charts.trend_frame({"lab_results": _labs([("2025-01-05", True, "TSH", "Normal")])})

    assert frame.empty


@pytest.mark.parametrize(
    "builder, columns",
    [
        (lambda: condition_charts.trend_frame({}), condition_charts.TREND_COLUMNS),
        (lambda: condition_charts.medication_spans([], "2026-08-01"), condition_charts.MEDICATION_COLUMNS),
        (lambda: condition_charts.flag_history([]), condition_charts.FLAG_HISTORY_COLUMNS),
        (lambda: condition_charts.monthly_counts({}), condition_charts.MONTHLY_COUNT_COLUMNS),
        (lambda: condition_charts.value_ranges(pd.DataFrame(), "TSH"), condition_charts.RANGE_COLUMNS),
        (lambda: condition_charts.severity_frame([]), condition_charts.SEVERITY_COLUMNS),
        (lambda: condition_charts.first_latest(pd.DataFrame()), condition_charts.FIRST_LATEST_COLUMNS),
        (lambda: condition_charts.sparkline_frame({}), condition_charts.SPARKLINE_COLUMNS),
    ],
)
def test_every_frame_builder_returns_empty_but_typed_on_no_data(builder, columns):
    """Empty-but-typed, so a caller can filter on a column without a KeyError."""
    frame = builder()

    assert frame.empty
    assert list(frame.columns) == columns


def test_medication_spans_clamps_an_open_ended_row_and_flags_it():
    spans = condition_charts.medication_spans(
        [
            {"name": "Levothyroxine", "start_date": "2024-09-15", "end_date": "2025-01-20", "status": "Completed"},
            {"name": "Allopurinol", "start_date": "2025-02-10", "end_date": None, "status": "Active"},
        ],
        "2026-08-01",
    )

    assert list(spans["name"]) == ["Levothyroxine", "Allopurinol"]
    ongoing = spans[spans["name"] == "Allopurinol"].iloc[0]
    # Clamped for drawing, but marked so the UI never presents it as a recorded stop date.
    assert bool(ongoing["open_ended"]) is True
    assert ongoing["end"] == pd.Timestamp("2026-08-01")
    assert bool(spans[spans["name"] == "Levothyroxine"].iloc[0]["open_ended"]) is False


def test_medication_spans_skips_a_row_with_no_start_date():
    spans = condition_charts.medication_spans([{"name": "Mystery", "start_date": None}], "2026-08-01")

    assert spans.empty


def test_first_latest_reports_arithmetic_change_only():
    frame = condition_charts.trend_frame({"lab_results": SAMPLE_LABS})

    summary = condition_charts.first_latest(frame).iloc[0]

    assert summary["record"] == "TSH"
    assert summary["first_value"] == 8.4
    assert summary["latest_value"] == 0.2
    assert summary["change"] == -8.2
    assert summary["results"] == 4
    # Flags travel with the endpoints so the caller never has to infer one from a number.
    assert summary["first_flag"] == "High"
    assert summary["latest_flag"] == "Low"


def test_value_ranges_summarises_spread_within_each_period():
    rows = _wearables(
        [
            ("2025-01-04T08:00:00", 120.0, "Blood Pressure Systolic"),
            ("2025-01-20T08:00:00", 140.0, "Blood Pressure Systolic"),
            ("2025-02-04T08:00:00", 130.0, "Blood Pressure Systolic"),
        ]
    )
    frame = condition_charts.trend_frame({"wearable_records": rows})

    ranges = condition_charts.value_ranges(frame, "Blood Pressure Systolic")

    assert len(ranges) == 2
    january = ranges.iloc[0]
    assert (january["minimum"], january["maximum"], january["average"]) == (120.0, 140.0, 130.0)


def test_value_ranges_for_an_unknown_record_is_empty_not_an_error():
    frame = condition_charts.trend_frame(SAMPLE_RECORDS)

    assert condition_charts.value_ranges(frame, "Nothing Like This").empty


def test_monthly_counts_splits_by_record_type():
    counts = condition_charts.monthly_counts(SAMPLE_RECORDS)

    assert set(counts["record_type"]) == {"Lab results", "Wearable records"}
    assert counts["count"].sum() == 6


def test_severity_frame_skips_entries_with_no_severity():
    entries = condition_charts.severity_frame(
        [
            {"entry_date": "2025-01-05", "title": "Gout flare", "severity": 8, "body_part": "Bones", "note": "Left foot."},
            {"entry_date": "2025-02-05", "title": "Gout flare", "severity": None},
            {"entry_date": "2025-03-05", "title": "Gout flare", "severity": "not a number"},
        ]
    )

    assert len(entries) == 1
    assert entries.iloc[0]["severity"] == 8


# --- chart specifications --------------------------------------------------------------------------


def _colors(spec):
    """Every explicit colour range anywhere in a (possibly nested) Vega-Lite spec."""
    found = []
    if isinstance(spec, dict):
        if spec.get("scale", {}).get("range") and "domain" in spec.get("scale", {}):
            found.append((tuple(spec["scale"]["domain"]), tuple(spec["scale"]["range"])))
        for value in spec.values():
            found += _colors(value)
    elif isinstance(spec, list):
        for item in spec:
            found += _colors(item)
    return found


def test_the_flag_palette_passed_validation_and_separates_severity_not_direction():
    """High, Low and Abnormal share the warning hue on purpose.

    Six distinct hues could not be separated: purple and blue landed 1.6 deltaE apart under
    deuteranopia. Three hues carry severity, mark shape carries direction, and identity therefore
    never rests on colour alone.
    """
    assert condition_charts.FLAG_COLORS["High"] == condition_charts.FLAG_COLORS["Low"]
    assert condition_charts.FLAG_SHAPES["High"] != condition_charts.FLAG_SHAPES["Low"]
    distinct_hues = set(condition_charts.FLAG_COLORS.values()) - {condition_charts.MUTED}
    assert len(distinct_hues) == 3
    # Every flag the app can store must have both encodings, or one renders in a Vega default.
    assert set(condition_charts.FLAG_COLORS) == set(condition_charts.FLAG_SHAPES)


def test_trend_chart_binds_colour_to_an_explicit_flag_domain():
    """An explicit domain means an unexpected flag falls outside the scale instead of borrowing a hue."""
    frame = condition_charts.trend_frame(SAMPLE_RECORDS)

    spec = condition_charts.build_trend_chart(frame).to_dict()

    # The domain is the flags actually present, so the legend does not list four entries with no
    # marks beside them. Each flag keeps its own hue regardless of which others are on screen.
    expected_domain = ("Normal", "High", "Low")
    ranges = [found for domain, found in _colors(spec) if domain == expected_domain]
    # Colour and shape share the flag domain, so both scales appear.
    assert tuple(condition_charts.FLAG_COLORS[flag] for flag in expected_domain) in ranges
    assert tuple(condition_charts.FLAG_SHAPES[flag] for flag in expected_domain) in ranges


def test_flag_colours_do_not_shift_when_other_flags_are_absent():
    """Colour follows the flag, never its position in whatever subset is on screen."""
    both = condition_charts.trend_frame({"lab_results": SAMPLE_LABS})
    normal_only = condition_charts.trend_frame(
        {"lab_results": _labs([("2025-01-05", 2.4, "TSH", "Normal"), ("2025-04-05", 2.2, "TSH", "Normal")])}
    )

    assert condition_charts.present_flags(both) == ["Normal", "High", "Low"]
    assert condition_charts.present_flags(normal_only) == ["Normal"]
    # Same hue for Normal in both, even though one frame has three flags and the other has one.
    assert condition_charts.FLAG_COLORS["Normal"] == "#12805f"


def test_range_period_widens_until_readings_actually_share_a_bucket():
    """A quarterly lab has one reading a month, so a monthly band collapses onto its own mean.

    Bucketing by year instead is the difference between a chart with something to say and a
    redrawn trend line.
    """
    quarterly = condition_charts.trend_frame({"lab_results": SAMPLE_LABS})
    twice_weekly = condition_charts.trend_frame(
        {"wearable_records": _wearables([("2025-01-04T08:00:00", 120.0, "BP"), ("2025-01-20T08:00:00", 140.0, "BP")])}
    )

    assert condition_charts.choose_range_period(quarterly, "TSH") == ("Y", "year")
    assert condition_charts.choose_range_period(twice_weekly, "BP") == ("M", "month")
    # One reading in total has no spread at any bucket size, so the section shows its empty state.
    single = condition_charts.trend_frame({"lab_results": _labs([("2025-01-05", 8.4, "TSH", "High")])})
    assert condition_charts.choose_range_period(single, "TSH") is None
    assert condition_charts.series_with_a_visible_range(single) == []


def test_series_with_a_visible_range_orders_densest_first():
    """The section opens on the series with the most to show, not the alphabetically first."""
    frame = condition_charts.trend_frame(
        {
            "lab_results": SAMPLE_LABS,
            "wearable_records": _wearables(
                [(f"2025-01-{day:02d}T08:00:00", 120.0 + day, "Weight") for day in range(1, 12)]
            ),
        }
    )

    assert condition_charts.series_with_a_visible_range(frame)[0] == "Weight"


def test_trend_chart_draws_flagged_and_unflagged_records_as_different_marks():
    frame = condition_charts.trend_frame(SAMPLE_RECORDS)

    spec = condition_charts.build_trend_chart(frame).to_dict()

    fills = [layer["mark"].get("filled") for layer in spec["layer"] if isinstance(layer.get("mark"), dict)]
    assert True in fills and False in fills


def test_trend_chart_survives_a_single_point():
    """The app opens on a seed profile whose series are short. A one-point chart must not raise."""
    frame = condition_charts.trend_frame({"lab_results": _labs([("2025-01-05", 8.4, "TSH", "High")])})

    spec = condition_charts.build_trend_chart(frame).to_dict()

    assert spec["layer"]


def test_trend_with_medications_shares_one_time_axis_and_never_a_second_y_scale():
    """Two y scales on one plot would imply a relationship nothing here has established.

    Concatenated with a shared x instead: the timing lines up, and each measure keeps its own axis.
    """
    frame = condition_charts.trend_frame(SAMPLE_RECORDS)
    spans = condition_charts.medication_spans(
        [{"name": "Levothyroxine", "start_date": "2025-01-01", "end_date": None, "status": "Active"}],
        "2026-08-01",
    )

    spec = condition_charts.build_trend_with_medications(frame, spans).to_dict()

    assert "vconcat" in spec
    assert spec["resolve"]["scale"]["x"] == "shared"
    assert "y" not in spec.get("resolve", {}).get("scale", {})


def test_trend_with_medications_falls_back_to_the_bare_trend_when_none_are_recorded():
    frame = condition_charts.trend_frame(SAMPLE_RECORDS)

    spec = condition_charts.build_trend_with_medications(frame, condition_charts.medication_spans([], "2026-08-01")).to_dict()

    assert "vconcat" not in spec


def test_trend_axis_is_not_forced_to_zero():
    """Zero is not a meaningful baseline for a physiological measurement, and forcing it flattens
    every real movement into a straight line."""
    frame = condition_charts.trend_frame(SAMPLE_RECORDS)

    spec = condition_charts.build_trend_chart(frame).to_dict()

    encodings = [layer["encoding"]["y"] for layer in spec["layer"] if "y" in layer.get("encoding", {})]
    assert all(encoding["scale"]["zero"] is False for encoding in encodings)


def test_every_flag_bearing_chart_puts_the_flag_in_its_tooltip():
    """Colour alone is never the carrier: the flag is readable as text on hover too."""
    frame = condition_charts.trend_frame(SAMPLE_RECORDS)
    history = condition_charts.flag_history(SAMPLE_LABS)

    for spec in (condition_charts.build_trend_chart(frame).to_dict(), condition_charts.build_flag_strip(history).to_dict()):
        titles = [tip.get("title") for tip in _tooltips(spec)]
        assert "Source flag" in titles


def _tooltips(spec):
    found = []
    if isinstance(spec, dict):
        tooltip = spec.get("encoding", {}).get("tooltip")
        if isinstance(tooltip, list):
            found += tooltip
        for value in spec.values():
            found += _tooltips(value)
    elif isinstance(spec, list):
        for item in spec:
            found += _tooltips(item)
    return found


def test_sparklines_give_each_condition_its_own_y_scale():
    """Different measurements in different units; a shared scale flattens one against another."""
    frame = condition_charts.sparkline_frame(
        {
            "Hypothyroidism": [{"date": "2025-01-05", "value": 8.4, "record": "TSH"}, {"date": "2025-04-05", "value": 3.1, "record": "TSH"}],
            "Sleep Apnea": [{"date": "2025-01-05", "value": 5.1, "record": "Sleep"}, {"date": "2025-04-05", "value": 7.2, "record": "Sleep"}],
        }
    )

    spec = condition_charts.build_sparklines(frame).to_dict()

    assert spec["resolve"]["scale"]["y"] == "independent"
    assert spec["facet"]["field"] == "condition"


@pytest.mark.parametrize(
    "builder",
    [
        lambda: condition_charts.build_flag_strip(condition_charts.flag_history(SAMPLE_LABS)),
        lambda: condition_charts.build_density_chart(condition_charts.monthly_counts(SAMPLE_RECORDS)),
        lambda: condition_charts.build_severity_chart(
            condition_charts.severity_frame([{"entry_date": "2025-01-05", "title": "Gout flare", "severity": 8}])
        ),
    ],
)
def test_remaining_builders_produce_a_renderable_spec(builder):
    spec = builder().to_dict()

    # `.get` on both: the flag strip is layered (filled marks for stored flags, hollow for absence),
    # and subscripting "mark" raised KeyError before the `or` could reach the layer branch.
    assert spec.get("mark") or spec.get("layer")


def test_range_band_chart_layers_a_band_under_a_mean_line():
    rows = _wearables([("2025-01-04T08:00:00", 120.0, "BP"), ("2025-01-20T08:00:00", 140.0, "BP")])
    ranges = condition_charts.value_ranges(condition_charts.trend_frame({"wearable_records": rows}), "BP")

    spec = condition_charts.build_range_band_chart(ranges).to_dict()

    marks = [layer["mark"]["type"] if isinstance(layer["mark"], dict) else layer["mark"] for layer in spec["layer"]]
    assert marks == ["area", "line"]


# --- the retrieval helper the sparklines depend on ---------------------------------------------------


def test_get_primary_series_is_profile_scoped(tmp_path):
    database = tmp_path / "phr.db"
    db.init_db(database)
    mine = services.create_person({"name": "Mine"}, db_path=database)
    theirs = services.create_person({"name": "Theirs"}, db_path=database)
    for person_id, value in ((mine, 8.4), (theirs, 1.1)):
        services.create_item(
            "lab_results",
            person_id,
            {"test_name": "Hemoglobin A1c", "numeric_value": value, "lab_date": "2025-01-05"},
            db_path=database,
        )

    series = get_primary_series(mine, ["Prediabetes"], db_path=database)

    assert [point["value"] for point in series["Prediabetes"]] == [8.4]


def test_get_primary_series_omits_a_condition_with_no_matching_records(tmp_path):
    database = tmp_path / "phr.db"
    db.init_db(database)
    person_id = services.create_person({"name": "Mine"}, db_path=database)

    series = get_primary_series(person_id, ["Prediabetes", "Not A Mapped Condition"], db_path=database)

    assert series == {}


# --- regressions from the 2026-08-04 independent review ---------------------------------------


def test_a_wearable_timestamp_with_a_zone_does_not_crash_the_page():
    """`validate_wearable` only requires a timestamp to be present, so a `Z` suffix is storable.

    Mixed with a bare lab date it produced a column of tz-aware and tz-naive values, and sorting it
    raised `TypeError: Cannot compare tz-naive and tz-aware timestamps` -- taking out the whole
    Tracked Conditions page for exactly the conditions that map both a lab and a wearable, which is
    the mapping Diabetes uses.
    """
    frame = condition_charts.trend_frame(
        {
            "lab_results": _labs([("2026-01-01", 5.5, "Hemoglobin A1c", "Normal")]),
            "wearable_records": [
                {"timestamp": "2026-01-02T08:00:00Z", "value": 100.0, "metric_type": "Glucose", "unit": "mg/dL"},
                {"timestamp": "2026-01-03T08:00:00+05:00", "value": 110.0, "metric_type": "Glucose", "unit": "mg/dL"},
            ],
        }
    )

    assert len(frame) == 3
    # Offsets are converted to UTC rather than dropped, so 08:00+05:00 lands at 03:00.
    assert frame["date"].dt.tz is None
    assert str(frame["date"].iloc[2]) == "2026-01-03 03:00:00"


def test_first_and_latest_use_a_row_id_tie_breaker_not_sort_order():
    """Two readings sharing a date must resolve by row id, not by however the rows arrived.

    `services.list_items` returns rows id-*descending*, so date-only sorting showed the newer row as
    "First" and the older as "Latest", inverting both flags and the sign of `change`. AGENTS.md
    section 9 requires an explicit tie-breaker for any "latest" calculation.
    """
    newest_first = [
        {"lab_date": "2026-01-01", "numeric_value": 1.9, "test_name": "Creatinine", "unit": "mg/dL", "flag": "High", "id": 11},
        {"lab_date": "2026-01-01", "numeric_value": 1.1, "test_name": "Creatinine", "unit": "mg/dL", "flag": "Normal", "id": 10},
    ]

    summary = condition_charts.first_latest(condition_charts.trend_frame({"lab_results": newest_first}))

    row = summary.iloc[0]
    assert (row["first_value"], row["first_flag"]) == (1.1, "Normal")
    assert (row["latest_value"], row["latest_flag"]) == (1.9, "High")
    assert row["change"] == 0.8
    # Reversing the input must not change any of it.
    reversed_summary = condition_charts.first_latest(
        condition_charts.trend_frame({"lab_results": list(reversed(newest_first))})
    )
    assert reversed_summary.iloc[0]["latest_value"] == 1.9
    assert reversed_summary.iloc[0]["change"] == 0.8


def test_many_same_date_readings_stay_stable_across_runs():
    """Guards the sort itself: pandas' default quicksort scrambled ties even without the id bug."""
    rows = [
        {"lab_date": "2026-01-01", "numeric_value": float(n), "test_name": "TSH", "unit": "mIU/L", "flag": "Normal", "id": n}
        for n in range(20, 0, -1)
    ]

    summary = condition_charts.first_latest(condition_charts.trend_frame({"lab_results": rows}))

    assert summary.iloc[0]["first_value"] == 1.0
    assert summary.iloc[0]["latest_value"] == 20.0


def test_a_lab_with_no_stored_flag_is_an_absence_not_the_unknown_flag():
    """"Unknown" is a real member of `models.LAB_FLAGS`, i.e. a flag a source can actually record.

    Mapping a NULL flag onto it made a lab nobody flagged indistinguishable from one a source
    explicitly flagged Unknown, under a caption promising "the flag the source recorded".
    """
    history = condition_charts.flag_history(
        [
            {"lab_date": "2026-01-01", "test_name": "A1c", "flag": None},
            {"lab_date": "2026-02-01", "test_name": "A1c", "flag": ""},
            {"lab_date": "2026-03-01", "test_name": "A1c", "flag": "Unknown"},
        ]
    )

    assert list(history["flag"]) == [
        condition_charts.NOT_FLAGGED,
        condition_charts.NOT_FLAGGED,
        "Unknown",
    ]
    # And the strip must draw the absence hollow rather than borrow a status hue for it.
    spec = condition_charts.build_flag_strip(history).to_dict()
    assert spec.get("layer")


def test_a_medication_with_no_end_date_says_so_instead_of_showing_today():
    """The clamped end is a drawing coordinate, not a fact about the record.

    `validate_medication` accepts a blank end date at any status, so this fires for a medication
    recorded as Stopped just as readily as an active one -- and the tooltip previously presented
    today's date under "Recorded through" for both.
    """
    spans = condition_charts.medication_spans(
        [
            {"name": "Metformin", "start_date": "2025-01-01", "end_date": "", "status": "Stopped"},
            {"name": "Lisinopril", "start_date": "2025-01-01", "end_date": "2025-06-01", "status": "Completed"},
        ],
        as_of="2026-08-04",
    )

    by_name = {row["name"]: row for _, row in spans.iterrows()}
    assert by_name["Metformin"]["open_ended"] is True
    assert by_name["Metformin"]["end_label"] == "No end date recorded"
    assert by_name["Lisinopril"]["open_ended"] is False
    assert by_name["Lisinopril"]["end_label"] == "Jun 1, 2025"

    spec = condition_charts.build_medication_timeline(spans).to_dict()
    # Two layers, so a span the record establishes at both ends cannot look like one it does not.
    assert len(spec["layer"]) == 2
    titles = {tip.get("title") for layer in spec["layer"] for tip in layer["encoding"]["tooltip"]}
    assert "Recorded through" in titles
    fields = {tip.get("field") for layer in spec["layer"] for tip in layer["encoding"]["tooltip"]}
    assert "end_label" in fields and "end" not in fields


def test_an_all_unflagged_chart_emits_no_flag_legend_at_all():
    """A wearable-only series has no flag column, so advertising Critical beside it is noise."""
    frame = condition_charts.trend_frame({"wearable_records": SAMPLE_WEARABLES})

    assert condition_charts.present_flags(frame[frame["flag"] != condition_charts.NOT_FLAGGED]) == []
    spec = condition_charts.build_trend_chart(frame).to_dict()
    encodings = [layer.get("encoding", {}) for layer in spec["layer"]]
    assert not any("color" in encoding or "shape" in encoding for encoding in encodings)


def test_change_is_withheld_when_a_series_mixes_units():
    """Subtracting 93 kg from 232 lb is true of the stored numbers and clinically meaningless."""
    rows = [
        {"timestamp": "2026-01-01T08:00:00", "value": 232.0, "metric_type": "Weight", "unit": "lb"},
        {"timestamp": "2026-06-01T08:00:00", "value": 93.0, "metric_type": "Weight", "unit": "kg"},
    ]

    summary = condition_charts.first_latest(condition_charts.trend_frame({"wearable_records": rows}))

    assert summary.iloc[0]["change"] is None
    assert summary.iloc[0]["unit"] == "Mixed units"


def test_a_single_point_sparkline_still_draws_something():
    """A Vega-Lite line mark with one datum draws no path, so the panel came out empty."""
    frame = condition_charts.sparkline_frame({"Prediabetes": [{"date": "2026-01-01", "value": 5.9, "record": "A1c"}]})

    spec = condition_charts.build_sparklines(frame).to_dict()

    assert spec["spec"]["mark"]["point"]
