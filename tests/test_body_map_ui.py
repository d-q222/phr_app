from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import app
import body_map_ui
import condition_charts
import db
import services
from body_map_config import BODY_PART_IDS
from body_map_services import NormalizedBodyRecord
from body_map_summary import summarize_body_part_health
from models import LAB_FLAGS

_render_page = body_map_ui.render_body_map_page.__wrapped__


def _raw_row(
    source_table: str,
    record_id: int,
    person_id: int,
    name: str,
    date: str | None,
    value: object,
    unit: str | None,
    flag: str | None,
) -> dict[str, object]:
    """A raw DB row shaped like the real table, so `raw_record` consumers see real column names.

    A bare ``{"id": ...}`` would make `condition_charts.trend_frame` return an empty frame, which
    silently drops the chart branch out of every test that renders the Trends tab.
    """

    base = {"id": record_id, "person_id": person_id}
    if source_table == "lab_results":
        # `result_value` and `numeric_value` both populated, as a FHIR quantity import does
        # (fhir.py:944-945). Tests that need only one of them pass `raw_record=` instead.
        return base | {
            "test_name": name,
            "lab_date": date,
            "result_value": None if value is None else str(value),
            "numeric_value": value,
            "unit": unit,
            "flag": flag,
        }
    if source_table == "wearable_records":
        return base | {"metric_type": name, "timestamp": date, "value": value, "unit": unit}
    if source_table == "medications":
        return base | {"name": name, "start_date": date, "dose": value, "status": flag}
    if source_table == "health_entries":
        return base | {"title": name, "entry_date": date, "severity": value, "note": None}
    if source_table == "appointments":
        return base | {"title": name, "appointment_date": date, "status": flag}
    raise ValueError(f"Unhandled source table in test helper: {source_table}")


def _record(
    record_id: int = 1,
    *,
    person_id: int = 1,
    record_type: str = "lab",
    source_table: str = "lab_results",
    name: str = "LDL",
    date: str | None = "2026-01-01",
    value: object = 5.0,
    unit: str | None = "mg/dL",
    # Lowercase, so *not* a `models.LAB_FLAGS` member -- every write path validates against that
    # list, so this default is a value no stored record can hold. Harmless for tests that assert on
    # frame contents, but `build_trend_chart` omits the flagged point layer when no recognized flag
    # is present: a test asserting a mark is drawn must pass a real flag.
    flag: str | None = "high",
    raw_record: dict[str, object] | None = None,
) -> NormalizedBodyRecord:
    return NormalizedBodyRecord(
        record_id=record_id,
        person_id=person_id,
        source_table=source_table,
        record_type=record_type,
        name=name,
        display_name=name,
        date=date,
        value=value,
        unit=unit,
        status_flag=flag,
        reference_range=None,
        body_parts=("heart",),
        body_systems=("cardiovascular",),
        relevance_type="risk_marker",
        relationship_strength="primary",
        mapping_source="curated_default",
        mapping_confidence="high",
        summary_text=None,
        raw_record=(
            raw_record
            if raw_record is not None
            else _raw_row(source_table, record_id, person_id, name, date, value, unit, flag)
        ),
    )


class FakeStreamlit:
    def __init__(self, selected: str | None = None):
        self.session_state = {}
        self.next_selection = None
        if selected:
            self.session_state[body_map_ui.SELECTED_STATE_KEY] = selected
        self.query_params = {}
        self.messages = []
        # Recorded, not discarded: a test asserting the chart branch was reached is the only way to
        # notice if a thin `raw_record` quietly sends every render down the `st.info` path instead.
        self.charts = []
        self.captions = []

    def info(self, message): self.messages.append(("info", message))
    def error(self, message): self.messages.append(("error", message))
    def markdown(self, *args, **kwargs): pass
    def caption(self, message="", *args, **kwargs): self.captions.append(message)
    def header(self, message): self.messages.append(("header", message))
    def subheader(self, message): self.messages.append(("subheader", message))
    def write(self, message): self.messages.append(("write", message))
    def dataframe(self, *args, **kwargs): pass
    def line_chart(self, *args, **kwargs): pass
    def altair_chart(self, chart, **kwargs): self.charts.append(chart)
    def tabs(self, labels): return [nullcontext() for _ in labels]
    def columns(self, count): return [self for _ in range(count)]
    def metric(self, label, value): self.messages.append((label, value))

    def selectbox(self, _label, options, **kwargs):
        key = kwargs.get("key")
        if _label == "Select a body part" and self.next_selection is not None:
            self.session_state[key] = self.next_selection
        return self.session_state.get(key, options[kwargs.get("index", 0)])


def test_body_map_requires_selected_profile(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(body_map_ui, "st", fake)

    _render_page(None)

    assert ("info", "Select a profile to view the body map.") in fake.messages


def test_body_map_page_runs_with_streamlit_apptest(tmp_path, monkeypatch):
    db_path = tmp_path / "body-map-app.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db(db_path)
    services.create_person({"name": "Fictional Person"}, db_path=db_path)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Body Map"

    test_app.run()
    test_app.selectbox(key=body_map_ui.SELECTED_STATE_KEY).select("heart").run()

    assert not test_app.exception
    assert any(header.value == "Heart / Cardiovascular" for header in test_app.header)
    assert any(subheader.value == "No data" for subheader in test_app.subheader)


def test_selected_profile_id_is_passed_to_retrieval_and_summary_once(monkeypatch):
    fake = FakeStreamlit("heart")
    fake.session_state[body_map_ui.PROFILE_STATE_KEY] = (str(Path("test.db").resolve()), 7)
    calls = []
    records = [_record(person_id=7)]
    monkeypatch.setattr(body_map_ui, "st", fake)
    monkeypatch.setattr(body_map_ui, "render_svg", lambda selected: "<svg/>")
    monkeypatch.setattr(
        body_map_ui,
        "get_records_for_body_part",
        lambda person_id, body_part, db_path: calls.append((person_id, body_part, db_path)) or records,
    )
    monkeypatch.setattr(
        body_map_ui,
        "summarize_body_part_health",
        lambda received: calls.append(("summary", received)) or summarize_body_part_health(received),
    )

    _render_page({"id": 7}, "test.db")

    assert calls == [(7, "heart", "test.db"), ("summary", records)]
    assert ("header", "Heart / Cardiovascular") in fake.messages
    assert ("subheader", "Needs review") in fake.messages
    assert ("write", "1 latest relevant record is source-flagged high.") in fake.messages


def test_profile_change_clears_stale_body_state():
    state = {
        body_map_ui.PROFILE_STATE_KEY: (str(Path("real.db").resolve()), 1),
        body_map_ui.SELECTED_STATE_KEY: "heart",
        body_map_ui.TREND_STATE_KEY: "LDL",
        "unrelated": True,
    }

    body_map_ui.sync_profile_state(state, 1, "demo.db")

    assert state == {
        body_map_ui.PROFILE_STATE_KEY: (str(Path("demo.db").resolve()), 1),
        "unrelated": True,
    }


def test_component_events_replace_selection_and_preserve_navigation(monkeypatch):
    fake = FakeStreamlit()
    fake.session_state["nav_page"] = "Body Map"
    component_calls = []
    retrieval_calls = []
    summary_calls = []
    rendered = []
    records = {"heart": [_record(1)], "kidneys": [_record(2)]}
    monkeypatch.setattr(body_map_ui, "st", fake)
    monkeypatch.setattr(
        body_map_ui,
        "BODY_MAP_COMPONENT",
        lambda **kwargs: component_calls.append(kwargs),
    )
    monkeypatch.setattr(
        body_map_ui,
        "get_records_for_body_part",
        lambda person_id, body_part, db_path: retrieval_calls.append((person_id, body_part, db_path))
        or records[body_part],
    )
    monkeypatch.setattr(
        body_map_ui,
        "summarize_body_part_health",
        lambda received: summary_calls.append(received) or summarize_body_part_health(received),
    )
    monkeypatch.setattr(
        body_map_ui,
        "_render_records",
        lambda received, label: rendered.append((label, received)),
    )

    _render_page({"id": 1}, "test.db")
    component_key = component_calls[-1]["key"]
    for event in (
        {"body_part": "heart", "event_id": "event-1"},
        {"body_part": "heart", "event_id": "event-2"},
        {"body_part": "kidneys", "event_id": "event-3"},
        {"body_part": "not_an_organ", "event_id": "event-4"},
    ):
        fake.session_state[component_key] = event
        component_calls[-1]["on_change"]()
        _render_page({"id": 1}, "test.db")

    assert fake.session_state[body_map_ui.SELECTED_STATE_KEY] == "kidneys"
    assert fake.session_state["nav_page"] == "Body Map"
    assert [call[1] for call in retrieval_calls] == ["heart", "heart", "kidneys", "kidneys"]
    assert summary_calls == [records[part] for part in ("heart", "heart", "kidneys", "kidneys")]
    assert [items for label, items in rendered if label == "Overview"] == summary_calls
    assert 'id="heart" class="selected-organ"' in component_calls[1]["svg"]
    assert 'id="kidneys" class="selected-organ"' in component_calls[3]["svg"]
    assert 'id="kidneys" class="selected-organ"' in component_calls[4]["svg"]
    assert all(str(Path("test.db").resolve()) in call["key"] and call["key"].endswith(":1") for call in component_calls)
    assert len({call["key"] for call in component_calls}) == 1


def test_fallback_selector_uses_the_same_validated_selection(monkeypatch):
    fake = FakeStreamlit("heart")
    fake.next_selection = "kidneys"
    fake.session_state[body_map_ui.PROFILE_STATE_KEY] = (str(Path("test.db").resolve()), 1)
    calls = []
    monkeypatch.setattr(body_map_ui, "st", fake)
    monkeypatch.setattr(body_map_ui, "BODY_MAP_COMPONENT", lambda **kwargs: None)
    monkeypatch.setattr(
        body_map_ui,
        "get_records_for_body_part",
        lambda person_id, body_part, db_path: calls.append((person_id, body_part, db_path)) or [],
    )

    _render_page({"id": 1}, "test.db")

    assert fake.session_state[body_map_ui.SELECTED_STATE_KEY] == "kidneys"
    assert calls == [(1, "kidneys", "test.db")]


def test_component_value_does_not_override_fallback_without_a_new_event(monkeypatch):
    fake = FakeStreamlit("heart")
    fake.next_selection = "kidneys"
    fake.session_state[body_map_ui.PROFILE_STATE_KEY] = (str(Path("test.db").resolve()), 1)
    calls = []
    monkeypatch.setattr(body_map_ui, "st", fake)
    monkeypatch.setattr(
        body_map_ui,
        "BODY_MAP_COMPONENT",
        lambda **kwargs: {"body_part": "heart", "event_id": "event-1"},
    )
    monkeypatch.setattr(
        body_map_ui,
        "get_records_for_body_part",
        lambda person_id, body_part, db_path: calls.append((person_id, body_part, db_path)) or [],
    )

    _render_page({"id": 1}, "test.db")

    assert fake.session_state[body_map_ui.SELECTED_STATE_KEY] == "kidneys"
    assert calls == [(1, "kidneys", "test.db")]


@pytest.mark.parametrize("event", [None, "heart", {}, {"body_part": []}, {"body_part": "unknown"}])
def test_invalid_component_event_preserves_selection(event):
    state = {body_map_ui.SELECTED_STATE_KEY: "heart", "component": event}

    body_map_ui.apply_component_selection(state, "component")

    assert state[body_map_ui.SELECTED_STATE_KEY] == "heart"


def test_component_key_changes_only_with_profile_or_database_scope(monkeypatch):
    fake = FakeStreamlit()
    keys = []
    monkeypatch.setattr(body_map_ui, "st", fake)
    monkeypatch.setattr(body_map_ui, "BODY_MAP_COMPONENT", lambda **kwargs: keys.append(kwargs["key"]))

    _render_page({"id": 1}, "real.db")
    _render_page({"id": 2}, "real.db")
    _render_page({"id": 2}, "demo.db")

    assert len(set(keys)) == 3


def test_invalid_state_is_reset():
    state = {
        body_map_ui.PROFILE_STATE_KEY: (str(Path("test.db").resolve()), 1),
        body_map_ui.SELECTED_STATE_KEY: "not_an_organ",
    }
    body_map_ui.sync_profile_state(state, 1, "test.db")
    assert body_map_ui.SELECTED_STATE_KEY not in state


def test_svg_contains_canonical_body_part_ids_and_selected_highlight():
    plain = body_map_ui.render_svg(None)
    selected = body_map_ui.render_svg("heart")

    assert all(f'id="{part_id}"' in plain for part_id in BODY_PART_IDS)
    assert 'id="heart" class="selected-organ"' in selected
    assert 'id="lungs" class="selected-organ"' not in selected
    assert ".selected-organ .body" in selected
    assert "?body_part=heart" in plain
    assert Path(body_map_ui.SVG_PATH).name == "body_map_front.svg"
    assert "body_map_front.svg" not in Path(app.__file__).read_text(encoding="utf-8")


def test_component_prevents_navigation_and_highlights_before_emitting_event():
    source = (body_map_ui.COMPONENT_PATH / "index.html").read_text(encoding="utf-8")
    assert "click.preventDefault()" in source
    assert 'classList.remove("selected-organ")' in source
    assert 'classList.add("selected-organ")' in source
    assert "body_part: bodyPart" in source
    assert "event_id:" in source


@pytest.mark.parametrize(
    ("record_type", "source_table", "category"),
    [
        ("lab", "lab_results", "Labs"),
        ("vital", "health_entries", "Vitals"),
        ("medication", "medications", "Medications"),
        ("health_entry", "health_entries", "Notes"),
        ("appointment", "appointments", "Notes"),
        ("imaging", "health_entries", "Imaging"),
        ("wearable", "wearable_records", "Wearables"),
    ],
)
def test_records_are_grouped_by_type(record_type, source_table, category):
    record = _record(record_type=record_type, source_table=source_table)
    grouped = body_map_ui.group_records([record, record])
    assert grouped[category] == [record]


def test_unknown_record_type_does_not_crash():
    assert all(not records for records in body_map_ui.group_records([_record(record_type="unknown")]).values())


def test_empty_body_part_displays_no_records_message(monkeypatch):
    fake = FakeStreamlit("heart")
    fake.session_state[body_map_ui.PROFILE_STATE_KEY] = (str(Path("test.db").resolve()), 1)
    monkeypatch.setattr(body_map_ui, "st", fake)
    monkeypatch.setattr(body_map_ui, "render_svg", lambda selected: "<svg/>")
    monkeypatch.setattr(body_map_ui, "get_records_for_body_part", lambda *args, **kwargs: [])

    _render_page({"id": 1}, "test.db")

    assert ("info", "No records found for this body area in the selected profile.") in fake.messages


def test_service_error_does_not_display_stale_profile_data(monkeypatch):
    fake = FakeStreamlit("heart")
    fake.session_state[body_map_ui.PROFILE_STATE_KEY] = (str(Path("test.db").resolve()), 1)
    monkeypatch.setattr(body_map_ui, "st", fake)
    monkeypatch.setattr(body_map_ui, "render_svg", lambda selected: "<svg/>")
    monkeypatch.setattr(body_map_ui, "get_records_for_body_part", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError()))

    _render_page({"id": 1}, "test.db")

    assert fake.messages[-1] == ("error", "Body map records could not be loaded. Please try again.")
    assert not any(message[0] == "write" for message in fake.messages)


# --- the Trends tab, now drawn by `condition_charts` ---------------------------------------------


def _render_with(records, monkeypatch, selected_trend=None):
    """Render the body-map page for one body area against a fixed record list."""
    fake = FakeStreamlit("heart")
    fake.session_state[body_map_ui.PROFILE_STATE_KEY] = (str(Path("test.db").resolve()), 1)
    if selected_trend is not None:
        fake.session_state[body_map_ui.TREND_STATE_KEY] = selected_trend
    monkeypatch.setattr(body_map_ui, "st", fake)
    monkeypatch.setattr(body_map_ui, "render_svg", lambda selected: "<svg/>")
    monkeypatch.setattr(body_map_ui, "get_records_for_body_part", lambda *args, **kwargs: records)
    _render_page({"id": 1}, "test.db")
    return fake


def test_the_trends_tab_reaches_the_chart_branch_for_a_dated_numeric_record(monkeypatch):
    """Guards the test helper as much as the page: a thin `raw_record` sends every render to `st.info`."""
    fake = _render_with([_record(1, value=5.0, date="2026-01-05")], monkeypatch)

    assert fake.charts, "the Trends tab rendered no chart for a chartable lab record"


def test_body_map_trends_exclude_medication_dose_from_the_chart(monkeypatch):
    """The reason this change exists.

    A medication's charted value is `dose` -- unvalidated free text, so "500" floats -- and its
    `status` shares the token "Unknown" with `LAB_FLAGS`. Charting it would put medication adherence
    inside a clinical-severity legend.
    """
    records = [
        _record(1, value=5.0, date="2026-01-05"),
        _record(
            2,
            record_type="medication",
            source_table="medications",
            name="Metformin",
            value="500",
            unit=None,
            flag="Unknown",
            date="2026-01-05",
        ),
    ]

    frame = condition_charts.trend_frame(body_map_ui.rows_by_source_table(records))

    assert "medications" not in set(frame["table"])
    assert "Metformin" not in set(frame["record"])


def test_body_map_trends_use_numeric_value_and_ignore_a_written_result(monkeypatch):
    """Pins the accepted semantic change: `numeric_value` is canonical, `result_value` is not parsed.

    Renders the page and captures what the chart was actually given, rather than composing
    `trend_frame(rows_by_source_table(...))` here. Composing the helpers proves the helpers agree;
    it stays green if the page is rewired to chart `NormalizedBodyRecord.value` instead, which is
    the regression this pins. `result_value` and `numeric_value` disagree deliberately, so a frame
    built from the wrong field is visible in the value itself.
    """
    written_only = _record(
        1,
        name="Written only",
        raw_record={"id": 1, "test_name": "Written only", "lab_date": "2026-01-05", "result_value": "5.4", "numeric_value": None, "unit": "x", "flag": None},
    )
    both = _record(
        2,
        name="Both",
        raw_record={"id": 2, "test_name": "Both", "lab_date": "2026-01-06", "result_value": "9.9", "numeric_value": 4.2, "unit": "x", "flag": None},
    )

    received = []
    original = condition_charts.build_trend_chart
    monkeypatch.setattr(
        condition_charts,
        "build_trend_chart",
        lambda frame, *args, **kwargs: (received.append(frame), original(frame, *args, **kwargs))[1],
    )
    _render_with([written_only, both], monkeypatch)

    assert received, "the Trends tab rendered no chart"
    assert set(received[0]["record"]) == {"Both"}, "a lab with no Numeric Result was charted anyway"
    assert received[0]["value"].tolist() == [4.2], "the chart used result_value rather than numeric_value"


def test_body_map_trends_chart_symptom_severity_separately(monkeypatch):
    """Severity keeps its own 1-10 axis rather than joining the clinical-value chart."""
    records = [
        _record(1, value=5.0, date="2026-01-05"),
        _record(2, record_type="health_entry", source_table="health_entries", name="Headache", value=7, unit=None, flag=None, date="2026-01-05"),
    ]

    fake = _render_with(records, monkeypatch)
    frame = condition_charts.trend_frame(body_map_ui.rows_by_source_table(records))

    assert "health_entries" not in set(frame["table"])
    assert ("subheader", "Symptom severity") in fake.messages
    assert len(fake.charts) == 2, "severity should render as a second chart, not merged into the trend"


def test_body_map_trend_grouping_only_yields_tables_the_chart_consumes(monkeypatch):
    records = [
        _record(1, source_table="lab_results", record_type="lab"),
        _record(2, source_table="wearable_records", record_type="wearable", name="Weight", value=180.0, unit="lb", flag=None),
        _record(3, source_table="medications", record_type="medication", name="Metformin", value="500", unit=None, flag="Active"),
    ]

    grouped = body_map_ui.rows_by_source_table(records)

    assert set(grouped) == {"lab_results", "wearable_records", "medications"}
    charted = set(condition_charts.trend_frame(grouped)["table"])
    assert charted <= set(condition_charts._NUMERIC_FIELDS)


def test_a_lab_with_no_numeric_value_is_explained_in_the_trends_tab(monkeypatch):
    records = [
        _record(1, value=5.0, date="2026-01-05"),
        _record(
            2,
            name="Written only",
            raw_record={"id": 2, "test_name": "Written only", "lab_date": "2026-01-06", "result_value": "Positive", "numeric_value": None, "unit": "x", "flag": None},
        ),
    ]

    fake = _render_with(records, monkeypatch)

    assert any("Numeric Result" in caption for caption in fake.captions)


def test_the_trends_tab_says_so_when_nothing_is_chartable(monkeypatch):
    records = [_record(1, record_type="medication", source_table="medications", name="Metformin", value="500", unit=None, flag="Active")]

    fake = _render_with(records, monkeypatch)

    assert ("info", "No dated numeric records are available for trends.") in fake.messages
    assert not fake.charts


def _admits(layer: dict, flag: str | None) -> bool:
    """Whether a chart layer's Vega filter lets a row carrying this flag through.

    Asserting that a point layer *exists* is not enough: flipping the flagged layer's predicate from
    `!==` to `===` leaves the layer in place while excluding the only datum. This evaluates the
    predicate instead, and raises on any shape it does not recognize -- a filter this helper cannot
    read must not be silently reported as admitting the row.
    """

    transforms = layer.get("transform") or []
    if not transforms:
        return True
    predicate = transforms[0].get("filter", "")
    if condition_charts.NOT_FLAGGED not in predicate:
        raise AssertionError(f"unrecognized layer filter, cannot evaluate admission: {predicate!r}")
    if "!==" in predicate:
        return flag != condition_charts.NOT_FLAGGED
    if "===" in predicate:
        return flag == condition_charts.NOT_FLAGGED
    raise AssertionError(f"unrecognized layer filter, cannot evaluate admission: {predicate!r}")


def test_a_single_reading_still_renders_a_visible_point(monkeypatch):
    """`st.line_chart` drew nothing for one row; the layered chart must actually mark it.

    Asserting that `spec["layer"]` is non-empty proves nothing: a line layer draws no path for a
    single datum, and each point layer carries a filter that can exclude the row. The reading has to
    be admitted by a point layer, so this asserts on the layer that draws a source-flagged one --
    with a flag that is really in `LAB_FLAGS`, since `build_trend_chart` omits the flagged layer
    entirely when no recognized flag is present.
    """
    records = [_record(1, value=5.0, date="2026-01-05", flag="High")]
    assert records[0].status_flag in LAB_FLAGS, "fixture flag must be one a source can actually record"

    fake = _render_with(records, monkeypatch)
    spec = fake.charts[0].to_dict()

    drawn = [
        layer
        for layer in spec["layer"]
        if layer.get("mark", {}).get("type") == "point" and _admits(layer, records[0].status_flag)
    ]
    assert drawn, f"no point layer draws the flagged reading; layers were {[m.get('mark') for m in spec['layer']]}"


def test_trends_are_not_default_and_fallback_selector_is_available():
    source = Path(body_map_ui.__file__).read_text(encoding="utf-8")
    assert source.index('"Overview"') < source.index('"Trends"')
    assert 'st.selectbox(\n        "Select a body part"' in source
    assert "st.query_params" not in source
    assert not {"diagnose", "diagnosis", "treatment"} & set(source.casefold().split())
