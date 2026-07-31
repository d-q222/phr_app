from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import app
import body_map_ui
import db
import services
from body_map_config import BODY_PART_IDS
from body_map_services import NormalizedBodyRecord
from body_map_summary import summarize_body_part_health

_render_page = body_map_ui.render_body_map_page.__wrapped__


def _record(
    record_id: int = 1,
    *,
    person_id: int = 1,
    record_type: str = "lab",
    source_table: str = "lab_results",
    date: str | None = "2026-01-01",
    value: object = 5.0,
    flag: str | None = "high",
) -> NormalizedBodyRecord:
    return NormalizedBodyRecord(
        record_id=record_id,
        person_id=person_id,
        source_table=source_table,
        record_type=record_type,
        name="LDL",
        display_name="LDL",
        date=date,
        value=value,
        unit="mg/dL",
        status_flag=flag,
        reference_range=None,
        body_parts=("heart",),
        body_systems=("cardiovascular",),
        relevance_type="risk_marker",
        relationship_strength="primary",
        mapping_source="curated_default",
        mapping_confidence="high",
        summary_text=None,
        raw_record={"id": record_id},
    )


class FakeStreamlit:
    def __init__(self, selected: str | None = None):
        self.session_state = {}
        self.next_selection = None
        if selected:
            self.session_state[body_map_ui.SELECTED_STATE_KEY] = selected
        self.query_params = {}
        self.messages = []

    def info(self, message): self.messages.append(("info", message))
    def error(self, message): self.messages.append(("error", message))
    def markdown(self, *args, **kwargs): pass
    def caption(self, *args, **kwargs): pass
    def header(self, message): self.messages.append(("header", message))
    def subheader(self, message): self.messages.append(("subheader", message))
    def write(self, message): self.messages.append(("write", message))
    def dataframe(self, *args, **kwargs): pass
    def line_chart(self, *args, **kwargs): pass
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


def test_numeric_trends_exclude_nonnumeric_and_undated_values_without_fabrication():
    valid = _record(1, value="4.5")
    trend = body_map_ui.numeric_trends(
        [valid, _record(2, value="not numeric"), _record(3, date=None, value=7), _record(4, value=float("nan"))]
    )

    assert trend["value"].tolist() == [4.5]
    assert trend["record"].tolist() == [valid.display_name]


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


def test_trends_are_not_default_and_fallback_selector_is_available():
    source = Path(body_map_ui.__file__).read_text(encoding="utf-8")
    assert source.index('"Overview"') < source.index('"Trends"')
    assert 'st.selectbox(\n        "Select a body part"' in source
    assert "st.query_params" not in source
    assert not {"diagnose", "diagnosis", "treatment"} & set(source.casefold().split())
