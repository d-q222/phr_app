from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import app
import condition_config
import condition_ui
import db
import security
import services
from condition_services import get_records_for_condition


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "conditions.db"
    db.init_db(path)
    return path


def _person(db_path, name="Person A"):
    return services.create_person({"name": name}, db_path=db_path)


def _add(table, person_id, data, db_path):
    return services.create_item(table, person_id, data, db_path=db_path)


def _unlocked_streamlit(monkeypatch):
    """Give security a bare session so no profile reads as unlocked by accident."""
    fake_streamlit = type("FakeStreamlit", (), {"session_state": {}})()
    monkeypatch.setattr(security, "st", fake_streamlit)
    return fake_streamlit


# --- hidden_nav_pages: nav visibility is a profile-isolation surface ------------------------------


def test_condition_focus_hidden_when_no_profile_selected(db_path, monkeypatch):
    _unlocked_streamlit(monkeypatch)

    assert app.hidden_nav_pages(None, db_path) == frozenset({"Condition Focus"})


def test_condition_focus_hidden_for_profile_without_conditions(db_path, monkeypatch):
    _unlocked_streamlit(monkeypatch)
    person_id = _person(db_path)

    assert app.hidden_nav_pages({"id": person_id}, db_path) == frozenset({"Condition Focus"})


def test_condition_focus_visible_for_profile_with_a_condition(db_path, monkeypatch):
    _unlocked_streamlit(monkeypatch)
    person_id = _person(db_path)
    _add("conditions", person_id, {"condition_name": "Diabetes"}, db_path)

    assert app.hidden_nav_pages({"id": person_id}, db_path) == frozenset()


def test_locked_profile_is_never_queried_for_conditions(db_path, monkeypatch):
    """Whether a locked profile has conditions is itself health data.

    Nav visibility is observable, so the locked branch must return *before* any condition query
    runs -- not merely ignore the result. Reaching the query fails this test.
    """
    _unlocked_streamlit(monkeypatch)

    def explode(*args, **kwargs):
        raise AssertionError("tracked_conditions must not be reached for a locked profile")

    monkeypatch.setattr(services, "tracked_conditions", explode)
    locked = {"id": 1, "profile_password_enabled": 1}

    assert app.hidden_nav_pages(locked, db_path) == frozenset({"Condition Focus"})


# --- page_navigation: hidden pages must not linger in session state ------------------------------


class FakeNavStreamlit:
    """Minimal Streamlit stand-in recording which nav buttons were rendered."""

    def __init__(self):
        self.session_state = {}
        self.rendered_buttons = []
        self.sections = []
        self.rerun_called = False

    class _Container:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    class _Sidebar:
        def __init__(self, outer):
            self._outer = outer

        def container(self, **kwargs):
            return FakeNavStreamlit._Container()

    @property
    def sidebar(self):
        return FakeNavStreamlit._Sidebar(self)

    def container(self, **kwargs):
        return FakeNavStreamlit._Container()

    def caption(self, *args, **kwargs):
        pass

    def markdown(self, text, *args, **kwargs):
        self.sections.append(text)

    def button(self, label, **kwargs):
        self.rendered_buttons.append(kwargs.get("key", label))
        return False

    def rerun(self):
        self.rerun_called = True


def test_page_navigation_falls_back_and_persists_when_current_page_is_hidden(monkeypatch):
    fake = FakeNavStreamlit()
    fake.session_state["nav_page"] = "Condition Focus"
    monkeypatch.setattr(app, "st", fake)

    page = app.page_navigation(hidden_pages=frozenset({"Condition Focus"}))

    assert page == "Dashboard"
    # Not persisting the fallback would leave no nav button marked current.
    assert fake.session_state["nav_page"] == "Dashboard"
    assert "nav_page_Condition Focus" not in fake.rendered_buttons
    assert "nav_page_Dashboard" in fake.rendered_buttons


def test_page_navigation_renders_hidden_free_sections_normally(monkeypatch):
    fake = FakeNavStreamlit()
    fake.session_state["nav_page"] = "Dashboard"
    monkeypatch.setattr(app, "st", fake)

    page = app.page_navigation(hidden_pages=frozenset({"Condition Focus"}))

    assert page == "Dashboard"
    assert "nav_page_Chronic Conditions" in fake.rendered_buttons
    assert "nav_page_Body Map" in fake.rendered_buttons
    assert "nav_page_Condition Focus" not in fake.rendered_buttons


def test_page_navigation_shows_condition_focus_when_not_hidden(monkeypatch):
    fake = FakeNavStreamlit()
    monkeypatch.setattr(app, "st", fake)

    app.page_navigation(hidden_pages=frozenset())

    assert "nav_page_Condition Focus" in fake.rendered_buttons


def test_page_navigation_defaults_to_the_sidebar_container(monkeypatch):
    """A bare call must still work; the container parameter is optional by design."""
    fake = FakeNavStreamlit()
    monkeypatch.setattr(app, "st", fake)

    assert app.page_navigation() == "Dashboard"
    assert "nav_page_Dashboard" in fake.rendered_buttons


# --- condition_config: exact matching, and the mapping is a medical-safety surface ---------------


def test_condition_lookup_is_case_and_whitespace_insensitive():
    assert condition_config.get_condition_record_mapping("  diabetes  ") == (
        condition_config.get_condition_record_mapping("Diabetes")
    )
    assert condition_config.get_condition_record_mapping("HYPERTENSION") != {}


def test_unknown_condition_maps_to_nothing_without_raising():
    assert condition_config.get_condition_record_mapping("Not A Tracked Condition") == {}
    assert condition_config.get_condition_record_mapping("") == {}
    assert condition_config.get_condition_record_mapping(None) == {}


def test_matching_is_exact_not_substring():
    """'Diabetes insipidus' is a different condition and must not inherit the Diabetes mapping."""
    assert condition_config.get_condition_record_mapping("Diabetes insipidus") == {}
    assert condition_config.get_condition_record_mapping("Pre-diabetes") == {}


def test_diabetes_mapping_asserts_no_treatment_relationship():
    """Regression on AGENTS.md section 5.

    Lisinopril is a blood-pressure drug and Atorvastatin is a statin. Listing either under Diabetes
    would have the app asserting a treatment relationship it has no basis for. Labs and wearables
    only -- no diabetes medication exists in the seed data.
    """
    diabetes = condition_config.get_condition_record_mapping("Diabetes")

    assert "medications" not in diabetes
    assert set(diabetes) == {"lab_results", "wearable_records"}


# --- condition_services: profile-scoped retrieval -------------------------------------------------


def test_records_for_condition_returns_only_the_selected_profile(db_path):
    selected = _person(db_path, "Selected")
    other = _person(db_path, "Other")
    for person_id in (selected, other):
        _add("lab_results", person_id, {"test_name": "Hemoglobin A1c", "lab_date": "2026-01-01"}, db_path)

    result = get_records_for_condition(selected, "Diabetes", db_path=db_path)

    assert set(result) == {"lab_results"}
    assert [row["person_id"] for row in result["lab_results"]] == [selected]


def test_records_for_condition_ignores_unmapped_record_names(db_path):
    person_id = _person(db_path)
    _add("lab_results", person_id, {"test_name": "Hemoglobin A1c", "lab_date": "2026-01-01"}, db_path)
    _add("lab_results", person_id, {"test_name": "Troponin I", "lab_date": "2026-01-02"}, db_path)

    result = get_records_for_condition(person_id, "Diabetes", db_path=db_path)

    assert [row["test_name"] for row in result["lab_results"]] == ["Hemoglobin A1c"]


def test_records_for_unmapped_condition_is_empty_not_an_error(db_path):
    person_id = _person(db_path)
    _add("lab_results", person_id, {"test_name": "Hemoglobin A1c", "lab_date": "2026-01-01"}, db_path)

    assert get_records_for_condition(person_id, "Scurvy", db_path=db_path) == {}


def test_records_for_condition_omits_tables_with_no_matches(db_path):
    person_id = _person(db_path)
    _add("lab_results", person_id, {"test_name": "Hemoglobin A1c", "lab_date": "2026-01-01"}, db_path)

    result = get_records_for_condition(person_id, "Diabetes", db_path=db_path)

    assert "wearable_records" not in result


# --- condition_ui state hygiene: session state must not survive a profile switch -----------------


def test_profile_change_clears_stale_condition_state():
    state = {
        condition_ui.PROFILE_STATE_KEY: (str(Path("real.db").resolve()), 1),
        condition_ui.SELECTED_CONDITION_KEY: "Diabetes",
        condition_ui.TREND_STATE_KEY: "Hemoglobin A1c",
        "unrelated": True,
    }

    condition_ui.sync_profile_state(state, 2, "real.db", ["Asthma"])

    assert state == {
        condition_ui.PROFILE_STATE_KEY: (str(Path("real.db").resolve()), 2),
        "unrelated": True,
    }


def test_database_switch_clears_stale_condition_state():
    """Real -> demo is a database switch at the same profile ID and must clear too."""
    state = {
        condition_ui.PROFILE_STATE_KEY: (str(Path("real.db").resolve()), 1),
        condition_ui.SELECTED_CONDITION_KEY: "Diabetes",
    }

    condition_ui.sync_profile_state(state, 1, "demo.db", ["Diabetes"])

    assert condition_ui.SELECTED_CONDITION_KEY not in state
    assert state[condition_ui.PROFILE_STATE_KEY] == (str(Path("demo.db").resolve()), 1)


def test_selection_not_belonging_to_the_profile_is_dropped():
    """Same profile and database, but the condition was deleted meanwhile."""
    scope = (str(Path("real.db").resolve()), 1)
    state = {
        condition_ui.PROFILE_STATE_KEY: scope,
        condition_ui.SELECTED_CONDITION_KEY: "Diabetes",
    }

    condition_ui.sync_profile_state(state, 1, "real.db", ["Asthma"])

    assert condition_ui.SELECTED_CONDITION_KEY not in state


# --- end-to-end smoke over the real app, guarding the B5 sidebar change ---------------------------


def test_condition_focus_page_runs_with_streamlit_apptest(tmp_path, monkeypatch):
    app_db_path = tmp_path / "condition-app.db"
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    person_id = services.create_person({"name": "Fictional Person"}, db_path=app_db_path)
    services.create_item(
        "conditions", person_id, {"condition_name": "Diabetes", "source": "Endocrinologist"}, db_path=app_db_path
    )
    _add("lab_results", person_id, {"test_name": "Hemoglobin A1c", "lab_date": "2026-01-01"}, app_db_path)
    _add("lab_results", person_id, {"test_name": "Troponin I", "lab_date": "2026-01-02"}, app_db_path)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Condition Focus"

    test_app.run()

    assert not test_app.exception
    # The page must be reachable (not hidden and not bounced back to Dashboard) and must open on
    # content rather than an empty prompt -- this is the regression guard on the B5 sidebar change.
    assert test_app.session_state["nav_page"] == "Condition Focus"
    assert [header.value for header in test_app.header] == ["Diabetes"]
    assert [sub.value for sub in test_app.subheader] == ["Lab results", "Wearable records"]


def test_condition_focus_is_unreachable_for_a_profile_with_no_conditions(tmp_path, monkeypatch):
    """The nav entry is hidden, so a stale stored page must bounce back to the Dashboard."""
    app_db_path = tmp_path / "condition-app-empty.db"
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    services.create_person({"name": "Fictional Person"}, db_path=app_db_path)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Condition Focus"

    test_app.run()

    assert not test_app.exception
    assert test_app.session_state["nav_page"] == "Dashboard"
