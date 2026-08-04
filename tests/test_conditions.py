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


def _sample_tables():
    return json.loads(Path(app.SAMPLE_DATA_PATH).read_text(encoding="utf-8"))["tables"]


def _record_names_from_backup(tables):
    """Record names present in the JSON-backup-shaped seed file, keyed by table."""
    return {
        table: {row.get(column) for row in tables.get(table, [])}
        for table, column in RECORD_NAME_COLUMNS.items()
    }


def test_every_seeded_condition_has_a_mapping():
    """A seeded condition with no mapping silently shows 'no records mapped' to the user."""
    for row in _sample_tables().get("conditions", []):
        name = row["condition_name"]
        assert condition_config.get_condition_record_mapping(name), f"{name} has no mapping"


def test_every_mapped_record_name_exists_in_the_sample_data():
    """Guards the cross-agent contract: a renamed record silently stops appearing.

    This is the cheapest possible tripwire for a later pass that rewrites the demo data.
    """
    from_backup = _record_names_from_backup(_sample_tables())
    missing = []
    for condition, mapping in condition_config.CONDITION_RECORD_MAPPINGS.items():
        for table, names in mapping.items():
            missing += [f"{condition}/{table}/{n}" for n in names if n not in from_backup[table]]
    assert missing == [], f"mapped names absent from sample data: {missing}"

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
