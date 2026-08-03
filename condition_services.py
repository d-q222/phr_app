from __future__ import annotations

from pathlib import Path

import db
import services
from condition_config import get_condition_record_mapping, normalize_condition_name

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
