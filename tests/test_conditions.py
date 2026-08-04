from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import app
import condition_charts
import condition_config
import condition_ui
import db
import security
import services
from condition_services import get_records_for_condition
from display_format import format_display_date


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


# --- navigation no longer depends on profile data at all -----------------------------------------


def test_navigation_never_queries_profile_health_data(db_path, monkeypatch):
    """Nav visibility used to depend on whether a profile had conditions, which made it an
    observable side channel: the sidebar renders before main()'s lock gate, so a locked profile's
    nav could reveal that it had conditions.

    That surface is gone with the Condition Details page. This asserts the stronger property the
    removal bought -- rendering navigation issues no condition query for anyone, locked or not --
    rather than the old, weaker "the locked branch returns early".
    """
    _unlocked_streamlit(monkeypatch)

    def explode(*args, **kwargs):
        raise AssertionError("navigation must not query profile health data")

    monkeypatch.setattr(services, "tracked_conditions", explode)
    fake = FakeNavStreamlit()
    monkeypatch.setattr(app, "st", fake)

    assert app.page_navigation() == "Dashboard"


# --- page_navigation: a removed page must not linger in session state ----------------------------


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


def test_page_navigation_falls_back_from_a_page_that_no_longer_exists(monkeypatch):
    """A session carrying `nav_page = "Condition Details"` from an older build must not blank out.

    That name matches no dispatch branch now, so without this fallback the whole content area
    would render empty with no button marked current and no way back.
    """
    fake = FakeNavStreamlit()
    fake.session_state["nav_page"] = "Condition Details"
    monkeypatch.setattr(app, "st", fake)

    page = app.page_navigation()

    assert page == "Dashboard"
    # Not persisting the fallback would leave no nav button marked current.
    assert fake.session_state["nav_page"] == "Dashboard"
    assert "nav_page_Condition Details" not in fake.rendered_buttons
    assert "nav_page_Dashboard" in fake.rendered_buttons


def test_page_navigation_renders_every_page_in_every_section(monkeypatch):
    """No page is conditional any more, so every entry in NAV_SECTIONS gets a button."""
    fake = FakeNavStreamlit()
    fake.session_state["nav_page"] = "Dashboard"
    monkeypatch.setattr(app, "st", fake)

    page = app.page_navigation()

    assert page == "Dashboard"
    for section_pages in app.NAV_SECTIONS.values():
        for name in section_pages:
            assert f"nav_page_{name}" in fake.rendered_buttons
    assert "nav_page_Condition Details" not in fake.rendered_buttons


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


def _scope(db_path="real.db", person_id=1, created_at="2026-01-01T09:00:00", locked=False):
    person = None if person_id is None else {"id": person_id, "created_at": created_at}
    return condition_ui.profile_scope(person, db_path, locked)


def test_profile_change_clears_stale_condition_state():
    state = {
        condition_ui.PROFILE_STATE_KEY: _scope(person_id=1),
        condition_ui.SELECTED_CONDITION_KEY: "Hypertension",
        f"{condition_ui.SERIES_KEY_PREFIX}:Hypertension": ["Blood Pressure Systolic"],
        f"{condition_ui.RANGE_KEY_PREFIX}:Hypertension": "Blood Pressure Systolic",
        "unrelated": True,
    }
    moved = _scope(person_id=2, created_at="2026-02-02T09:00:00")

    condition_ui.sync_profile_scope(state, moved)

    assert state == {condition_ui.PROFILE_STATE_KEY: moved, "unrelated": True}


def test_database_switch_clears_stale_condition_state():
    """Real -> demo is a database switch at the same profile ID and must clear too."""
    state = {
        condition_ui.PROFILE_STATE_KEY: _scope(db_path="real.db"),
        condition_ui.SELECTED_CONDITION_KEY: "Hypertension",
    }

    condition_ui.sync_profile_scope(state, _scope(db_path="demo.db"))

    assert condition_ui.SELECTED_CONDITION_KEY not in state


def test_locking_the_current_profile_clears_condition_state():
    """Regression: locking changes neither path nor id, so lock state must be part of the scope.

    Without it, a selected condition and its chart selections stay reachable in session state for a
    profile that has just become locked.
    """
    series_key = f"{condition_ui.SERIES_KEY_PREFIX}:Hypertension"
    state = {
        condition_ui.PROFILE_STATE_KEY: _scope(locked=False),
        condition_ui.SELECTED_CONDITION_KEY: "Hypertension",
        series_key: ["Blood Pressure Systolic"],
    }

    condition_ui.sync_profile_scope(state, _scope(locked=True))

    assert condition_ui.SELECTED_CONDITION_KEY not in state
    assert series_key not in state


def test_restoring_a_different_person_at_the_same_id_clears_condition_state():
    """Regression: a clear-and-restore can put a different human at profile id 1.

    Path and id are identical afterwards, so the profile's created_at is what distinguishes them.
    """
    state = {
        condition_ui.PROFILE_STATE_KEY: _scope(person_id=1, created_at="2026-01-01T09:00:00"),
        condition_ui.SELECTED_CONDITION_KEY: "Hypertension",
    }

    condition_ui.sync_profile_scope(state, _scope(person_id=1, created_at="2025-05-05T09:00:00"))

    assert condition_ui.SELECTED_CONDITION_KEY not in state


def test_selection_not_belonging_to_the_profile_is_dropped():
    """Same profile and database, but the condition was deleted meanwhile."""
    state = {condition_ui.SELECTED_CONDITION_KEY: "Hypertension"}

    condition_ui.sync_valid_conditions(state, ["Prediabetes"])

    assert condition_ui.SELECTED_CONDITION_KEY not in state


def test_valid_selection_is_kept():
    state = {condition_ui.SELECTED_CONDITION_KEY: "Hypertension"}

    condition_ui.sync_valid_conditions(state, ["Hypertension", "Prediabetes"])

    assert state[condition_ui.SELECTED_CONDITION_KEY] == "Hypertension"


# --- end-to-end smoke over the real app, guarding the B5 sidebar change ---------------------------


def test_a_removed_page_left_in_session_state_falls_back_to_the_dashboard(tmp_path, monkeypatch):
    """End-to-end version of the stale-nav guard, through the real app rather than a test double.

    Condition Details was removed; a browser session that still has it stored must land on the
    Dashboard with content, not on a blank page.
    """
    app_db_path = tmp_path / "stale-nav.db"
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    services.create_person({"name": "Fictional Person"}, db_path=app_db_path)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Condition Details"

    test_app.run(timeout=60)

    assert not test_app.exception
    assert test_app.session_state["nav_page"] == "Dashboard"
    assert any("<h1>Dashboard</h1>" in block.value for block in test_app.markdown)


# --- the Tracked Conditions detail page ----------------------------------------------------------

DEMO_BUNDLE = Path(app.__file__).resolve().parent / "demo_data" / "devon_marsh_fhir_bundle.json"
DETAIL_SECTIONS = [
    "Measurement trends",
    "First and most recent",
    "Source-flag history",
    "Monitoring cadence",
    "Variability",
    "Recorded symptom severity",
    "All tracked conditions",
    "Linked records",
]


def _app_with_imported_demo(tmp_path, monkeypatch, name="devon.db"):
    """A database holding the shipped demo bundle, wired in as the app's real path."""
    import fhir

    app_db_path = tmp_path / name
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    fhir.import_bundle(DEMO_BUNDLE.read_text(encoding="utf-8"), db_path=app_db_path)
    return app_db_path


def test_tracked_conditions_page_renders_every_section_for_the_imported_profile(tmp_path, monkeypatch):
    _app_with_imported_demo(tmp_path, monkeypatch)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Tracked Conditions"

    test_app.run(timeout=60)

    assert not test_app.exception
    subheaders = [sub.value for sub in test_app.subheader]
    for section in DETAIL_SECTIONS:
        assert section in subheaders, f"{section} is missing from the page"
    assert len(test_app.get("metric")) == 4
    assert len(test_app.get("vega_lite_chart")) >= 5


def test_every_imported_condition_charts_without_error(tmp_path, monkeypatch):
    """Each condition is a different shape, so each is a different chance to raise.

    Sleep Apnea is the one that renders five charts rather than six: it maps no lab, because there
    is no blood test commonly tracked for it, and mapping one purely to fill the panel would be the
    fabricated-claim defect this feature exists to avoid. Its empty state says so.
    """
    _app_with_imported_demo(tmp_path, monkeypatch)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Tracked Conditions"
    test_app.run(timeout=60)

    rendered = {}
    for condition in ("Hypothyroidism", "Gout", "Sleep Apnea", "Chronic Kidney Disease", "Asthma"):
        # Set after the first run: sync_profile_scope clears the selection on the run that first
        # establishes the profile scope, which would discard a pre-seeded value.
        test_app.session_state[condition_ui.SELECTED_CONDITION_KEY] = condition
        test_app.run(timeout=60)
        assert not test_app.exception, f"{condition} raised"
        assert [header.value for header in test_app.header] == [condition]
        rendered[condition] = len(test_app.get("vega_lite_chart"))

    assert rendered["Sleep Apnea"] == 5
    assert all(count == 6 for name, count in rendered.items() if name != "Sleep Apnea"), rendered


def test_tracked_conditions_page_degrades_for_a_profile_with_thin_data(tmp_path, monkeypatch):
    """The app opens on the seed profile, so this page renders before the demo import ever happens.

    One condition, one lab result, one point. Every section must render its empty state rather than
    raising or leaving a gap.
    """
    app_db_path = tmp_path / "thin.db"
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    person_id = services.create_person({"name": "Fictional Person"}, db_path=app_db_path)
    _add("conditions", person_id, {"condition_name": "Prediabetes", "source": "Primary Care"}, app_db_path)
    _add("lab_results", person_id, {"test_name": "Hemoglobin A1c", "numeric_value": 5.8, "lab_date": "2026-01-01", "flag": "High"}, app_db_path)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Tracked Conditions"

    test_app.run(timeout=60)

    assert not test_app.exception
    assert [header.value for header in test_app.header] == ["Prediabetes"]
    subheaders = [sub.value for sub in test_app.subheader]
    for section in DETAIL_SECTIONS:
        assert section in subheaders
    # A single-point series still charts; with one reading there is no spread, so the range band
    # shows its empty state rather than a band collapsed onto its own mean.
    assert len(test_app.get("vega_lite_chart")) >= 1
    assert any("no spread to show" in message.value for message in test_app.info)


def test_tracked_conditions_page_is_reachable_and_prompts_when_no_conditions_exist(tmp_path, monkeypatch):
    """Unlike Condition Details this page is never hidden -- it is where a condition gets created."""
    app_db_path = tmp_path / "empty.db"
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    services.create_person({"name": "Fictional Person"}, db_path=app_db_path)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Tracked Conditions"

    test_app.run(timeout=60)

    assert not test_app.exception
    assert test_app.session_state["nav_page"] == "Tracked Conditions"
    assert any("Add one below" in message.value for message in test_app.info)


def test_tracked_conditions_is_always_in_the_navigation(monkeypatch):
    """Hiding it would leave a profile with no conditions no way to record its first one."""
    fake = FakeNavStreamlit()
    monkeypatch.setattr(app, "st", fake)

    app.page_navigation()

    assert "nav_page_Tracked Conditions" in fake.rendered_buttons


def test_dashboard_offers_a_button_through_to_the_detail_page(tmp_path, monkeypatch):
    """The dashboard carries the accessible slice; the detail view is one click away from it."""
    app_db_path = tmp_path / "jump.db"
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    person_id = services.create_person({"name": "Fictional Person"}, db_path=app_db_path)
    _add("conditions", person_id, {"condition_name": "Prediabetes"}, app_db_path)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Dashboard"
    test_app.run(timeout=60)

    test_app.button(key="dashboard_condition_detail").click().run(timeout=60)

    assert not test_app.exception
    assert test_app.session_state["nav_page"] == "Tracked Conditions"


def test_the_detail_button_is_offered_even_with_no_conditions_recorded(tmp_path, monkeypatch):
    """That profile needs the route most: the page it leads to is where a first condition is added."""
    app_db_path = tmp_path / "jump-empty.db"
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    services.create_person({"name": "Fictional Person"}, db_path=app_db_path)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Dashboard"
    test_app.run(timeout=60)

    test_app.button(key="dashboard_condition_detail").click().run(timeout=60)

    assert not test_app.exception
    assert test_app.session_state["nav_page"] == "Tracked Conditions"
    assert any("Add one below" in message.value for message in test_app.info)


def test_generic_record_page_still_renders_its_own_header_by_default(tmp_path, monkeypatch):
    """The new parameter must not change any of the eight pages that do not pass it."""
    app_db_path = tmp_path / "labs.db"
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    services.create_person({"name": "Fictional Person"}, db_path=app_db_path)
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Labs"

    test_app.run(timeout=60)

    assert not test_app.exception
    assert any("<h1>Labs</h1>" in block.value for block in test_app.markdown)


def test_body_map_and_emergency_snapshot_render_for_the_imported_profile(tmp_path, monkeypatch):
    """Both read record types the demo bundle fills, so both must survive an import."""
    _app_with_imported_demo(tmp_path, monkeypatch)

    for page in ("Body Map", "Emergency Snapshot"):
        test_app = AppTest.from_file(str(Path(app.__file__)))
        test_app.session_state["nav_page"] = page
        test_app.run(timeout=60)
        assert not test_app.exception, f"{page} raised"
        assert test_app.session_state["nav_page"] == page

    snapshot_person = int(services.list_people(db_path=db.DB_PATH)[0]["id"])
    snapshot = services.generate_emergency_snapshot(snapshot_person, db_path=db.DB_PATH)
    assert "## Tracked Conditions" in snapshot
    assert "Chronic Kidney Disease" in snapshot


# --- review follow-ups: state hygiene at the profile-selection site ------------------------------


def test_scope_sync_handles_no_selected_profile():
    state = {
        condition_ui.PROFILE_STATE_KEY: _scope(person_id=1),
        condition_ui.SELECTED_CONDITION_KEY: "Hypertension",
    }

    condition_ui.sync_profile_scope(state, _scope(person_id=None))

    assert condition_ui.SELECTED_CONDITION_KEY not in state


def test_scope_sync_is_idempotent_within_one_profile():
    """It runs on every rerun, so it must not wipe a live selection."""
    state = {}
    condition_ui.sync_profile_scope(state, _scope())
    state[condition_ui.SELECTED_CONDITION_KEY] = "Hypertension"

    condition_ui.sync_profile_scope(state, _scope())

    assert state[condition_ui.SELECTED_CONDITION_KEY] == "Hypertension"


def test_profile_scope_needs_no_query_and_tolerates_a_bare_profile_row():
    """Built for locked and unselected profiles, where reading conditions would itself leak."""
    assert condition_ui.profile_scope(None, "real.db", False)[1] is None
    assert condition_ui.profile_scope({"id": 3}, "real.db", True)[1] == 3


def test_switching_profiles_on_an_unrelated_page_clears_condition_state(tmp_path, monkeypatch):
    """The leak path: the Dashboard and Condition Details never render, so only main() can clear."""
    app_db_path = tmp_path / "switch.db"
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    first = services.create_person({"name": "First"}, db_path=app_db_path)
    services.create_person({"name": "Second"}, db_path=app_db_path)
    services.create_item("conditions", first, {"condition_name": "Diabetes"}, db_path=app_db_path)
    labels = [
        app.profile_selection_label(person, app_db_path)
        for person in services.list_people(db_path=app_db_path)
    ]

    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Labs"
    test_app.run()
    test_app.session_state[condition_ui.SELECTED_CONDITION_KEY] = "Diabetes"
    test_app.selectbox(key="selected_profile").select(labels[1]).run()

    assert not test_app.exception
    assert condition_ui.SELECTED_CONDITION_KEY not in test_app.session_state


# --- review follow-ups: the app must not invent data or overclaim --------------------------------


def test_noted_date_is_not_prefilled_with_today():
    """`date_text` would default a blank date to today, inventing a date the user never gave."""
    fields = dict(app.FIELD_CONFIGS["conditions"]["fields"])

    assert fields["noted_date"] == "text"


def test_a_condition_saved_without_a_date_keeps_a_blank_date(db_path):
    person_id = _person(db_path)
    record_id = _add("conditions", person_id, {"condition_name": "Asthma", "noted_date": ""}, db_path)

    row = services.tracked_conditions(person_id, db_path=db_path)[0]

    assert row["id"] == record_id
    assert not row["noted_date"]


def _user_facing_condition_text():
    """Every string that can reach the screen from the condition feature.

    `condition_charts` is included because axis titles, legend labels and tooltip titles are user
    facing too -- a chart is not exempt from the copy rules just because the words are small.
    """
    return " ".join(
        [
            app.PAGE_DESCRIPTIONS["Tracked Conditions"],
            Path(condition_ui.__file__).read_text(encoding="utf-8"),
            Path(condition_charts.__file__).read_text(encoding="utf-8"),
        ]
    ).lower()


def test_user_facing_condition_copy_makes_no_currency_or_attachment_claim():
    """Without a status column the app cannot claim a condition is ongoing, and the mapping is
    type-level, so no copy may say a specific record belongs to a condition."""
    text = _user_facing_condition_text()

    assert "ongoing" not in text
    assert "matching this condition" not in text
    assert "relevant to" not in text


def test_user_facing_condition_copy_passes_no_judgement_on_any_value():
    """Describing a trend is allowed; grading it is not.

    "decreased" is arithmetic over two stored numbers. "improved" is an opinion about whether that
    was good, which needs clinical context the app does not have. This guards the line between them
    now that charts make it much easier to cross.
    """
    text = _user_facing_condition_text()

    for word in ("improved", "improving", "worsened", "worsening", "well controlled", "well-managed", "healthy", "concerning"):
        assert word not in text, f"user-facing condition copy passes judgement with {word!r}"


# --- the demo data must not assert anything its own records contradict ---------------------------


RECORD_NAME_COLUMNS = {
    "lab_results": "test_name",
    "medications": "name",
    "wearable_records": "metric_type",
    "health_entries": "title",
}
DEMO_BUNDLE_PATH = Path(app.__file__).resolve().parent / "demo_data" / "devon_marsh_fhir_bundle.json"


def _sample_tables():
    return json.loads(Path(app.SAMPLE_DATA_PATH).read_text(encoding="utf-8"))["tables"]


def _record_names_from_backup(tables):
    """Record names present in the JSON-backup-shaped seed file, keyed by table."""
    return {
        table: {row.get(column) for row in tables.get(table, [])}
        for table, column in RECORD_NAME_COLUMNS.items()
    }


def _demo_bundle_resources():
    return [
        entry["resource"]
        for entry in json.loads(DEMO_BUNDLE_PATH.read_text(encoding="utf-8"))["entry"]
        if entry.get("resource")
    ]


def _record_names_from_bundle(resources):
    """Record names present in the FHIR-shaped demo bundle, keyed by the table each will land in.

    Mirrors `fhir._observation_from_resource`'s routing so the guard checks the table a name will
    actually occupy rather than where it looks like it belongs.
    """
    names = {table: set() for table in RECORD_NAME_COLUMNS}
    for resource in resources:
        text = (resource.get("code") or {}).get("text")
        if resource.get("resourceType") == "MedicationStatement":
            names["medications"].add((resource.get("medicationCodeableConcept") or {}).get("text"))
        elif resource.get("resourceType") == "Observation":
            category = " ".join((item.get("text") or "") for item in resource.get("category", [])).lower()
            if "laboratory" in category:
                names["lab_results"].add(text)
            elif "wearable" in category:
                names["wearable_records"].add(text)
            else:
                names["health_entries"].add(text)
    return names


def test_every_seeded_condition_has_a_mapping():
    """A seeded condition with no mapping silently shows 'no records mapped' to the user."""
    bundle_conditions = [
        (resource.get("code") or {}).get("text")
        for resource in _demo_bundle_resources()
        if resource.get("resourceType") == "Condition"
    ]
    seeded = [row["condition_name"] for row in _sample_tables().get("conditions", [])]
    for name in seeded + bundle_conditions:
        assert condition_config.get_condition_record_mapping(name), f"{name} has no mapping"


def test_every_mapped_record_name_exists_in_a_shipped_dataset():
    """Guards the cross-agent contract: a renamed record silently stops appearing.

    Widened, not weakened, when the demo bundle arrived. The seed file and the bundle are two
    shipped datasets and neither can hold every mapped name on its own -- the Riveras are
    deliberately left untouched, so the conditions only Devon Marsh carries can never appear in the
    seed file. A name is satisfied by appearing in *either*; a name in neither is still a failure
    that names the exact triple.
    """
    from_backup = _record_names_from_backup(_sample_tables())
    from_bundle = _record_names_from_bundle(_demo_bundle_resources())
    missing = []
    for condition, mapping in condition_config.CONDITION_RECORD_MAPPINGS.items():
        for table, names in mapping.items():
            present = from_backup[table] | from_bundle[table]
            missing += [f"{condition}/{table}/{n}" for n in names if n not in present]
    assert missing == [], f"mapped names absent from every shipped dataset: {missing}"


def test_demo_bundle_conditions_resolve_inside_the_bundle_itself():
    """Stricter than the union guard: Devon's own conditions must be satisfied by his own records.

    The union guard would be happy if a name Devon needs happened to exist in Alex's seed data.
    That would still leave the imported profile's page empty, which is the thing being demoed.
    """
    from_bundle = _record_names_from_bundle(_demo_bundle_resources())
    bundle_conditions = [
        (resource.get("code") or {}).get("text")
        for resource in _demo_bundle_resources()
        if resource.get("resourceType") == "Condition"
    ]
    missing = []
    for condition in bundle_conditions:
        for table, names in condition_config.get_condition_record_mapping(condition).items():
            missing += [f"{condition}/{table}/{n}" for n in names if n not in from_bundle[table]]
    assert missing == [], f"bundle conditions with no backing records in the bundle: {missing}"


def test_every_primary_metric_is_in_its_conditions_mapping():
    """A sparkline must draw a series the condition's own record list also shows.

    Without this, `CONDITION_PRIMARY_METRIC` could name a record the condition does not map, and the
    at-a-glance chart would show a line that appears nowhere else on the page.
    """
    for condition, (table, record_name) in condition_config.CONDITION_PRIMARY_METRIC.items():
        mapping = condition_config.get_condition_record_mapping(condition)
        assert record_name in mapping.get(table, ()), f"{condition} primary metric {record_name} is unmapped"


def test_every_mapped_condition_has_a_primary_metric():
    """Otherwise the all-conditions sparkline panel is silently missing a facet."""
    for condition in condition_config.CONDITION_RECORD_MAPPINGS:
        assert condition_config.get_condition_primary_metric(condition), f"{condition} has no primary metric"


def test_seeded_conditions_are_supported_by_the_profiles_own_records():
    """Regression on the fabricated-diagnosis defect.

    Every seeded condition must actually surface records for the profile it is attached to. A label
    with nothing behind it is exactly the failure this replaced.
    """
    demo_path = Path(tempfile.mkdtemp()) / "demo.db"
    app.create_demo_database(demo_path)
    for person in services.list_people(db_path=demo_path):
        person_id = int(person["id"])
        for row in services.tracked_conditions(person_id, db_path=demo_path):
            found = get_records_for_condition(person_id, row["condition_name"], db_path=demo_path)
            assert found, f"{person['name']} / {row['condition_name']} surfaces nothing"


def test_sample_data_makes_no_diabetes_claim():
    """Alex's A1c results are 5.8/5.7/5.5/5.4, the last two source-flagged Normal.

    Labelling her diabetic asserts a diagnosis her own records contradict. Prediabetes is what the
    source-flagged values support.
    """
    names = {row["condition_name"] for row in _sample_tables().get("conditions", [])}

    assert "Diabetes" not in names


# --- conditions reach the two Markdown documents, profile-scoped ---------------------------------


def test_provider_summary_includes_only_this_profiles_conditions(db_path):
    selected = _person(db_path, "Selected")
    other = _person(db_path, "Other")
    _add("conditions", selected, {"condition_name": "Hypertension", "source": "Primary Care"}, db_path)
    _add("conditions", other, {"condition_name": "Prediabetes", "source": "Cardiologist"}, db_path)

    summary = services.generate_provider_summary(selected, db_path=db_path)

    assert "## Tracked Conditions" in summary
    assert "Hypertension (reported by Primary Care)" in summary
    assert "Prediabetes" not in summary


def test_emergency_snapshot_includes_only_this_profiles_conditions(db_path):
    selected = _person(db_path, "Selected")
    other = _person(db_path, "Other")
    _add("conditions", selected, {"condition_name": "Hypertension", "source": "Primary Care"}, db_path)
    _add("conditions", other, {"condition_name": "Prediabetes"}, db_path)

    snapshot = services.generate_emergency_snapshot(selected, db_path=db_path)

    assert "## Tracked Conditions" in snapshot
    assert "Hypertension" in snapshot
    assert "Prediabetes" not in snapshot
    # Conditions belong above medications in an emergency document.
    assert snapshot.index("## Tracked Conditions") < snapshot.index("## Active Medications")


def test_summaries_report_no_conditions_without_implying_absence_of_illness(db_path):
    person_id = _person(db_path)

    summary = services.generate_provider_summary(person_id, db_path=db_path)
    snapshot = services.generate_emergency_snapshot(person_id, db_path=db_path)

    for document in (summary, snapshot):
        section = document.split("## Tracked Conditions")[1].splitlines()[1]
        assert section == "None recorded."


# --- regressions from the 2026-08-04 independent review ---------------------------------------


def test_most_recent_record_counts_every_linked_record_not_only_numeric_ones():
    """"Most recent record: None" appeared beside "Medications recorded: 1" on the same metric row.

    The date came from the trend frame, which covers only lab and wearable rows carrying a finite
    number. A condition linked solely to a medication -- or to a qualitative lab stored as text with
    a NULL `numeric_value` -- therefore contradicted the counts printed next to it.
    """
    records = {
        "medications": [{"name": "Vitamin D3", "start_date": "2026-02-01"}],
        "lab_results": [{"test_name": "Vitamin D", "lab_date": "2026-03-05", "result_value": "Insufficient"}],
    }

    latest = condition_ui._most_recent_record_date(records)

    assert latest is not None
    assert latest.date().isoformat() == "2026-03-05"


def test_most_recent_record_is_none_only_when_nothing_is_dated():
    assert condition_ui._most_recent_record_date({}) is None
    assert condition_ui._most_recent_record_date({"medications": [{"name": "No date"}]}) is None


def test_most_recent_record_handles_a_zoned_wearable_timestamp():
    """Same tz-normalisation the trend frame needs; `max()` over mixed awareness would raise."""
    records = {
        "wearable_records": [{"metric_type": "Glucose", "timestamp": "2026-01-02T08:00:00Z"}],
        "lab_results": [{"test_name": "Hemoglobin A1c", "lab_date": "2026-01-01"}],
    }

    latest = condition_ui._most_recent_record_date(records)

    assert latest.date().isoformat() == "2026-01-02"


def test_the_page_shows_a_most_recent_date_for_a_medication_only_condition(tmp_path, monkeypatch):
    """Wiring, not just the helper.

    The pure-function tests above would still pass if `_render_at_a_glance` went back to reading
    `trends["date"].max()`, which is where the visible contradiction lived: "Most recent record:
    None" printed beside "Medications recorded: 1".
    """
    app_db_path = tmp_path / "at-a-glance.db"
    monkeypatch.setattr(db, "DB_PATH", app_db_path)
    db.init_db(app_db_path)
    person_id = services.create_person({"name": "Fictional Person"}, db_path=app_db_path)
    services.create_item(
        "conditions",
        person_id,
        {"condition_name": "Vitamin D Deficiency", "source": "Primary Care"},
        db_path=app_db_path,
    )
    # Mapped for this condition, and deliberately the only linked record: a medication carries no
    # numeric value, so it never reaches the trend frame the metric used to be derived from.
    services.create_item(
        "medications", person_id, {"name": "Vitamin D3", "start_date": "2026-02-01"}, db_path=app_db_path
    )
    test_app = AppTest.from_file(str(Path(app.__file__)))
    test_app.session_state["nav_page"] = "Tracked Conditions"

    test_app.run(timeout=60)

    assert not test_app.exception
    values = [metric.value for metric in test_app.metric]
    # Expected through the same formatter the page uses: `%b` is locale-sensitive, so hard-coding
    # "Feb" would fail under a non-English LC_TIME rather than because the behaviour broke.
    assert format_display_date("2026-02-01") in values
    assert "None" not in values


def test_most_recent_record_keeps_the_calendar_day_across_a_day_crossing_offset():
    """The `Z` case above has a zero offset, so UTC conversion and wall clock agree there.

    `2026-01-01T00:30:00+14:00` is 2025-12-31 in UTC, so a UTC normalisation made the metric name a
    day the record does not -- while the cadence chart and the record table still said Jan 1.
    """
    latest = condition_ui._most_recent_record_date(
        {"wearable_records": [{"metric_type": "Glucose", "timestamp": "2026-01-01T00:30:00+14:00"}]}
    )

    assert latest.date().isoformat() == "2026-01-01"
def _bundle(*conditions):
    return json.dumps(
        {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1", "name": [{"text": "Fictional Person"}]}},
                *(
                    {
                        "resource": {
                            "resourceType": "Condition",
                            "id": f"c{index}",
                            "subject": {"reference": "Patient/p1"},
                            "code": {"text": name},
                            **({"verificationStatus": {"coding": [{"code": status}]}} if status else {}),
                        }
                    }
                    for index, (name, status) in enumerate(conditions)
                ),
            ],
        }
    )


def test_a_refuted_condition_is_not_imported_as_a_tracked_condition(db_path):
    """`refuted` means a clinician considered it and ruled it out.

    Dropping `verificationStatus` is right for active-versus-resolved -- the schema has no column for
    it and inventing one would overclaim. It inverts for a negation: importing "Cancer / refuted" as
    a tracked condition asserts a diagnosis the source explicitly excluded, and the row then appeared
    in the Emergency Snapshot.
    """
    import imports_exports

    result = imports_exports.import_fhir_bundle(
        _bundle(("Cancer", "refuted"), ("Typo Condition", "entered-in-error"), ("Asthma", "confirmed")),
        db_path=db_path,
    )

    person_id = services.list_people(db_path=db_path)[0]["id"]
    assert [row["condition_name"] for row in services.tracked_conditions(person_id, db_path=db_path)] == ["Asthma"]
    # Visible, not silent: the user can see what did not come in and why.
    reasons = {entry["reason"] for entry in result["skipped"]}
    assert any("refuted" in reason for reason in reasons)
    assert any("entered-in-error" in reason for reason in reasons)
    assert result["imported"]["conditions"] == 1


def test_a_refuted_condition_never_reaches_the_emergency_snapshot(db_path):
    """The document an emergency responder reads is the reason this matters most."""
    import imports_exports

    imports_exports.import_fhir_bundle(_bundle(("Cancer", "refuted")), db_path=db_path)
    person_id = services.list_people(db_path=db_path)[0]["id"]

    snapshot = services.generate_emergency_snapshot(person_id, db_path=db_path)

    assert "Cancer" not in snapshot


def test_a_condition_with_no_verification_status_still_imports(db_path):
    """Real bundles routinely omit it, including this repository's own demo bundle."""
    import imports_exports

    imports_exports.import_fhir_bundle(_bundle(("Hypothyroidism", None)), db_path=db_path)

    person_id = services.list_people(db_path=db_path)[0]["id"]
    assert [row["condition_name"] for row in services.tracked_conditions(person_id, db_path=db_path)] == ["Hypothyroidism"]


def test_a_condition_coded_only_by_number_is_skipped_not_named_after_its_code(db_path):
    """`_text_from_codeable` falls back to `coding[].code`, which is right for a lab and wrong here.

    Machine-generated EHR exports routinely code a Condition as SNOMED `44054006` with no text and
    no display. The shared helper turned that into a tracked condition literally named "44054006",
    shown in the condition list and the Emergency Snapshot and matching no mapping -- the same
    failure the converter's "no fallback name" rule exists to prevent, arriving by another door.
    """
    import imports_exports

    bundle = json.dumps(
        {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1", "name": [{"text": "Fictional Person"}]}},
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "c1",
                        "subject": {"reference": "Patient/p1"},
                        "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006"}]},
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "c2",
                        "subject": {"reference": "Patient/p1"},
                        "code": {"coding": [{"system": "http://snomed.info/sct", "code": "44054006", "display": "Diabetes"}]},
                    }
                },
            ],
        }
    )

    result = imports_exports.import_fhir_bundle(bundle, db_path=db_path)

    person_id = services.list_people(db_path=db_path)[0]["id"]
    # The one carrying a human-readable display still imports; only the bare code is refused.
    assert [row["condition_name"] for row in services.tracked_conditions(person_id, db_path=db_path)] == ["Diabetes"]
    assert [entry["id"] for entry in result["skipped"]] == ["c1"]
    assert "44054006" not in services.generate_emergency_snapshot(person_id, db_path=db_path)


def test_a_refused_condition_reports_the_refusal_not_the_missing_patient(db_path):
    """Precedence when a resource fails two ways at once.

    The verification-status refusal is intrinsic and terminal -- repairing the subject reference
    would not make the condition importable -- so it is the more useful reason to show.
    """
    import imports_exports

    bundle = json.dumps(
        {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1", "name": [{"text": "Fictional Person"}]}},
                {"resource": {"resourceType": "Patient", "id": "p2", "name": [{"text": "Second Person"}]}},
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "c1",
                        "subject": {"reference": "Patient/ghost"},
                        "code": {"text": "Cancer"},
                        "verificationStatus": {"coding": [{"code": "refuted"}]},
                    }
                },
            ],
        }
    )

    result = imports_exports.import_fhir_bundle(bundle, db_path=db_path)

    reason = next(entry["reason"] for entry in result["skipped"] if entry["id"] == "c1")
    assert "refuted" in reason
    assert "No matching Patient" not in reason


def test_uncertain_conditions_are_refused_along_with_the_negated_ones(db_path):
    """`provisional` and `differential` withhold the claim; storing them unqualified asserts it.

    There is no status column to carry "the source has not confirmed this", and the tracked list
    feeds the Emergency Snapshot, so an unqualified row states more than the bundle does.
    """
    import imports_exports

    result = imports_exports.import_fhir_bundle(
        _bundle(
            ("Provisional Thing", "provisional"),
            ("Differential Thing", "differential"),
            ("Unconfirmed Thing", "unconfirmed"),
            ("Asthma", "confirmed"),
        ),
        db_path=db_path,
    )

    person_id = services.list_people(db_path=db_path)[0]["id"]
    assert [row["condition_name"] for row in services.tracked_conditions(person_id, db_path=db_path)] == ["Asthma"]
    assert len(result["skipped"]) == 3


def test_no_imported_record_is_ever_named_after_a_bare_terminology_code(db_path):
    """Allergen, medication and health-entry titles reach the provider summary and the snapshot."""
    import imports_exports

    coded = {"coding": [{"system": "http://snomed.info/sct", "code": "227493005"}]}
    bundle = json.dumps(
        {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "p1", "name": [{"text": "Fictional Person"}]}},
                {"resource": {"resourceType": "AllergyIntolerance", "id": "a1", "patient": {"reference": "Patient/p1"}, "code": coded}},
                {
                    "resource": {
                        "resourceType": "MedicationStatement",
                        "id": "m1",
                        "subject": {"reference": "Patient/p1"},
                        "medicationCodeableConcept": coded,
                        "status": "active",
                    }
                },
            ],
        }
    )

    imports_exports.import_fhir_bundle(bundle, db_path=db_path)

    person_id = services.list_people(db_path=db_path)[0]["id"]
    assert [row["allergen"] for row in services.list_items("allergies", person_id, db_path=db_path)] == ["Unknown allergen"]
    assert [row["name"] for row in services.list_items("medications", person_id, db_path=db_path)] == ["Unknown medication"]
    assert "227493005" not in services.generate_emergency_snapshot(person_id, db_path=db_path)
