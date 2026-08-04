from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import db
import services
from condition_config import (
    get_condition_primary_metric,
    get_condition_record_mapping,
    normalize_condition_name,
)

_RECORD_NAME_COLUMNS = {
    "lab_results": "test_name",
    "medications": "name",
    "wearable_records": "metric_type",
    "health_entries": "title",
}


def get_records_for_condition(
    person_id: int,
    condition_name: str,
    db_path: Path | str | None = None,
) -> dict[str, list[dict]]:
    """Return matched records for one profile and condition.

    Inputs are a profile ID, raw condition name, and optional database path. The output contains
    non-empty lists from mapped lab, medication, wearable, or health-entry tables. Reads are
    profile-scoped through ``services.list_items``; mapping names are exact after normalization.
    """

    db_path = db.DB_PATH if db_path is None else db_path
    mapping = get_condition_record_mapping(condition_name)
    if not mapping:
        return {}

    results: dict[str, list[dict]] = {}
    for table, record_names in mapping.items():
        normalized_names = {normalize_condition_name(name) for name in record_names}
        rows = services.list_items(table, person_id, db_path=db_path)
        filtered = [
            row
            for row in rows
            if normalize_condition_name(row.get(_RECORD_NAME_COLUMNS[table])) in normalized_names
        ]
        if filtered:
            results[table] = filtered
    return results


_PRIMARY_SERIES_FIELDS = {
    "lab_results": ("lab_date", "numeric_value"),
    "wearable_records": ("timestamp", "value"),
}


def get_primary_series(
    person_id: int,
    condition_names: Sequence[str],
    db_path: Path | str | None = None,
) -> dict[str, list[dict]]:
    """Return each condition's headline series as ``{condition: [{date, value, record}, ...]}``.

    Inputs a profile ID, the condition names on screen, and an optional database path; outputs one
    entry per condition that has both a `CONDITION_PRIMARY_METRIC` entry and matching records.
    Reads `lab_results` and `wearable_records` through profile-scoped `services.list_items`.

    Lives here rather than in `condition_charts` so that module needs no database access at all,
    which is what lets every chart be tested without a fixture.
    """

    db_path = db.DB_PATH if db_path is None else db_path
    results: dict[str, list[dict]] = {}
    cache: dict[str, list[dict]] = {}
    for condition_name in condition_names:
        primary = get_condition_primary_metric(condition_name)
        if primary is None:
            continue
        table, record_name = primary
        fields = _PRIMARY_SERIES_FIELDS.get(table)
        if fields is None:
            continue
        date_column, value_column = fields
        if table not in cache:
            cache[table] = services.list_items(table, person_id, db_path=db_path)
        wanted = normalize_condition_name(record_name)
        points = [
            {
                "date": row.get(date_column),
                "value": row.get(value_column),
                "record": record_name,
                # Carried so `sparkline_frame` can tie-break two readings sharing a date, the same
                # way `trend_frame` does. Without it the sparkline's point order is a sort accident.
                "id": row.get("id"),
            }
            for row in cache[table]
            if normalize_condition_name(row.get(_RECORD_NAME_COLUMNS[table])) == wanted
        ]
        if points:
            results[condition_name] = points
    return results
