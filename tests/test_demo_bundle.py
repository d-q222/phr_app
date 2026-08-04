"""Tests for the Devon Marsh demo FHIR Bundle and the script that builds it.

The bundle is a shipped artifact a person uploads live, so these tests check the thing on disk
rather than only the generator: a regenerated-but-not-rewritten file is exactly the drift worth
catching.
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_demo_bundle  # noqa: E402

import condition_config  # noqa: E402
import db  # noqa: E402
import fhir  # noqa: E402
import services  # noqa: E402
from condition_services import get_records_for_condition  # noqa: E402

BUNDLE_PATH = ROOT / "demo_data" / "devon_marsh_fhir_bundle.json"
# Generous by design. Measured at ~0.4s for 1,278 resources; this is a tripwire for an
# order-of-magnitude regression that would hurt a live import, not a performance target.
IMPORT_TIME_BUDGET_SECONDS = 15.0


@pytest.fixture(scope="module")
def bundle_text():
    return BUNDLE_PATH.read_text(encoding="utf-8")


@pytest.fixture
def imported(tmp_path, bundle_text):
    """Import the shipped bundle into a throwaway database and return (db_path, person_id)."""
    database = tmp_path / "phr.db"
    db.init_db(database)
    result = fhir.import_bundle(bundle_text, db_path=database)
    assert result["skipped"] == [], f"bundle did not import cleanly: {result['skipped'][:5]}"
    person_id = int(services.list_people(db_path=database)[0]["id"])
    return database, person_id, result


def test_the_committed_bundle_matches_what_the_generator_produces(bundle_text):
    """The script is the source of truth. A hand-edited bundle is drift, not a fix."""
    expected, _ = build_demo_bundle.build_bundle()

    assert json.loads(bundle_text) == expected


def test_the_generator_is_deterministic():
    """Regenerating must be a no-op, or every run shows a spurious diff and nobody reads them."""
    first, first_counts = build_demo_bundle.build_bundle()
    second, second_counts = build_demo_bundle.build_bundle()

    assert first == second
    assert first_counts == second_counts


def test_observations_route_to_the_tables_the_generator_intended(imported):
    """A misroute imports cleanly and leaves `skipped` empty, so counts are the only tripwire.

    `fhir._observation_from_resource` routes on category text *or* on "lab"/"wearable" appearing in
    the resource id. With over a thousand Observations across three destinations, one id containing
    the wrong substring would move a whole series into the wrong table with no visible error.
    """
    _, _, result = imported
    _, expected = build_demo_bundle.build_bundle()

    assert result["imported"] == expected


def test_imported_lab_flags_match_their_own_reference_ranges(imported):
    """Recompute every flag from the value and range as stored *after* import.

    Deliberately asserted against database rows rather than the bundle JSON: checking the file
    against itself is near-tautological, since the generator wrote both fields. The transform that
    could drop or mangle either one is `fhir._lab_from_observation`, and only post-import rows
    exercise it. A flag that disagrees with its own value is the defect class that required a whole
    remediation pass on the previous demo dataset.
    """
    database, person_id, _ = imported
    mismatches = []
    for row in services.list_items("lab_results", person_id, db_path=database):
        value, low, high = row["numeric_value"], row["reference_low"], row["reference_high"]
        expected = build_demo_bundle._flag_for(value, low, high)
        if row["flag"] != expected:
            mismatches.append(f"{row['test_name']} {value} (range {low}-{high}) flagged {row['flag']}, expected {expected}")

    assert mismatches == [], f"lab flags contradict their own reference ranges: {mismatches}"


def test_every_flag_value_is_actually_used(imported):
    """A demo where nothing is ever flagged cannot show the flag-history chart doing anything."""
    database, person_id, _ = imported
    flags = Counter(row["flag"] for row in services.list_items("lab_results", person_id, db_path=database))

    assert flags["Normal"] > 0
    assert flags["High"] > 0
    assert flags["Low"] > 0


def test_every_condition_resolves_to_records_for_the_imported_profile(imported):
    """Regression on the fabricated-diagnosis defect, applied to the bundle rather than the seed."""
    database, person_id, _ = imported
    conditions = services.tracked_conditions(person_id, db_path=database)

    assert len(conditions) == len(build_demo_bundle.CONDITIONS)
    for row in conditions:
        found = get_records_for_condition(person_id, row["condition_name"], db_path=database)
        assert found, f"{row['condition_name']} surfaces no records"
        # Enough points that a trend line is a line rather than a dot.
        assert sum(len(rows) for rows in found.values()) >= 4


def test_every_condition_has_a_chartable_primary_series(imported):
    """The at-a-glance sparkline panel must have a line to draw for each of Devon's conditions."""
    database, person_id, _ = imported
    for row in services.tracked_conditions(person_id, db_path=database):
        table, record_name = condition_config.get_condition_primary_metric(row["condition_name"])
        column = {"lab_results": "test_name", "wearable_records": "metric_type"}[table]
        points = [
            item
            for item in services.list_items(table, person_id, db_path=database)
            if item.get(column) == record_name
        ]
        assert len(points) >= 4, f"{row['condition_name']} primary series {record_name} has {len(points)} points"


def test_condition_sources_are_all_in_the_controlled_vocabulary(imported):
    """A source outside the vocabulary imports blank, which is indistinguishable from missing data."""
    database, person_id, _ = imported
    for row in services.tracked_conditions(person_id, db_path=database):
        assert row["source"], f"{row['condition_name']} imported without a source"


def test_the_bundle_fills_every_person_scoped_table(imported):
    """Anything empty is a page that renders its empty state for the imported profile."""
    database, person_id, _ = imported
    for table in db.TABLES:
        if table == "people":
            continue
        assert services.list_items(table, person_id, db_path=database), f"{table} is empty"


def test_the_dashboard_tiles_are_all_non_zero(imported):
    """Including the overdue tile, which needs a past-dated reminder that is not Completed."""
    database, person_id, _ = imported
    data = services.dashboard_data(person_id, db_path=database)

    assert len(data["active_medications"]) > 0
    assert len(data["allergies"]) > 0
    assert len(data["latest_labs"]) > 0
    assert len(data["overdue_reminders"]) > 0
    assert len(data["wearable_summary"]) > 0


def test_health_entries_land_on_canonical_body_map_parts(imported):
    """Body Map placement depends on `body_part` aliasing to a `body_map_config` part id.

    There is no "foot" part, so a gout flare is stored against Bones with the location in the note.
    An unrecognised string would silently place nothing, which is why this is asserted rather than
    assumed.
    """
    import body_map_services
    from body_map_config import BODY_PARTS

    database, person_id, _ = imported
    populated = {
        part_id
        for part_id in BODY_PARTS
        if body_map_services.get_records_for_body_part(person_id, part_id, db_path=database)
    }

    assert {"lungs", "kidneys", "bones", "thyroid"} <= populated


def test_importing_the_bundle_leaves_existing_profiles_untouched(tmp_path, bundle_text):
    """Importing with "clear existing records" unticked is the additive path. This is that path.

    `conditions` is in `db.TABLES`, so the clear path would wipe it -- the additive path must not.
    """
    database = tmp_path / "phr.db"
    db.init_db(database)
    existing = services.create_person({"name": "Alex Rivera", "notes": "Seeded profile."}, db_path=database)
    services.create_item("conditions", existing, {"condition_name": "Prediabetes"}, db_path=database)
    services.create_item("lab_results", existing, {"test_name": "Hemoglobin A1c", "lab_date": "2026-01-01"}, db_path=database)

    fhir.import_bundle(bundle_text, clear_existing=False, db_path=database)

    assert [row["condition_name"] for row in services.list_items("conditions", existing, db_path=database)] == ["Prediabetes"]
    assert len(services.list_items("lab_results", existing, db_path=database)) == 1
    assert services.get_person(existing, db_path=database)["notes"] == "Seeded profile."
    assert len(services.list_people(db_path=database)) == 2


def test_the_imported_profile_keeps_its_own_notes(imported):
    """The Dashboard renders this string directly, so the generic import literal is visible."""
    database, person_id, _ = imported

    assert services.get_person(person_id, db_path=database)["notes"] == build_demo_bundle.PROFILE_NOTES


def test_import_completes_fast_enough_for_a_live_demo(tmp_path, bundle_text):
    """`import_bundle` inserts one row at a time, so resource count drives wall time directly.

    If this ever fails, the fix is fewer wearable readings in the generator, not a rewrite of db.py.
    """
    database = tmp_path / "phr.db"
    db.init_db(database)

    started = time.perf_counter()
    fhir.import_bundle(bundle_text, db_path=database)
    elapsed = time.perf_counter() - started

    assert elapsed < IMPORT_TIME_BUDGET_SECONDS, f"bundle import took {elapsed:.1f}s"
