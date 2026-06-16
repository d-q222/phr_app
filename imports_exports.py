from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pandas as pd

import db
import fhir
import services
from validation import (
    is_blank,
    normalize_optional_number,
    validate_allergy,
    validate_appointment,
    validate_health_entry,
    validate_lab,
    validate_medication,
    validate_person,
    validate_reminder,
    validate_wearable,
)


BACKUP_VALIDATORS = {
    "people": validate_person,
    "allergies": validate_allergy,
    "medications": validate_medication,
    "lab_results": validate_lab,
    "health_entries": validate_health_entry,
    "appointments": validate_appointment,
    "reminders": validate_reminder,
    "wearable_records": validate_wearable,
}


SYSTEM_COLUMNS = {"id", "person_id", "created_at", "updated_at"}


def import_labs_csv(file_obj, person_id: int, db_path: Path | str = db.DB_PATH) -> dict:
    frame = pd.read_csv(file_obj)
    imported = 0
    skipped = []
    for index, row in frame.fillna("").iterrows():
        data = {
            "test_name": row.get("test_name", ""),
            "result_value": row.get("result_value", ""),
            "numeric_value": row.get("numeric_value", ""),
            "unit": row.get("unit", ""),
            "reference_low": row.get("reference_low", ""),
            "reference_high": row.get("reference_high", ""),
            "flag": row.get("flag", "Unknown") or "Unknown",
            "lab_date": row.get("lab_date", ""),
            "notes": row.get("notes", ""),
        }
        errors = validate_lab(data)
        if errors:
            skipped.append({"row": int(index) + 2, "errors": errors})
            continue
        data["numeric_value"] = normalize_optional_number(data["numeric_value"])
        data["reference_low"] = normalize_optional_number(data["reference_low"])
        data["reference_high"] = normalize_optional_number(data["reference_high"])
        services.create_item("lab_results", person_id, data, db_path=db_path)
        imported += 1
    return {"imported": imported, "skipped": skipped}


def import_wearables_csv(file_obj, person_id: int, db_path: Path | str = db.DB_PATH) -> dict:
    frame = pd.read_csv(file_obj)
    imported = 0
    skipped = []
    for index, row in frame.fillna("").iterrows():
        data = {
            "metric_type": row.get("metric_type", ""),
            "value": row.get("value", ""),
            "unit": row.get("unit", ""),
            "timestamp": row.get("timestamp", ""),
            "source": row.get("source", ""),
        }
        errors = validate_wearable(data)
        if errors:
            skipped.append({"row": int(index) + 2, "errors": errors})
            continue
        data["value"] = float(data["value"])
        services.create_item("wearable_records", person_id, data, db_path=db_path)
        imported += 1
    return {"imported": imported, "skipped": skipped}


def _person_scoped_tables(person_id: int, db_path: Path | str = db.DB_PATH) -> dict:
    person = services.get_person(person_id, db_path=db_path)
    tables = {table: [] for table in db.TABLES}
    if not person:
        return tables
    tables["people"] = [person]
    for table in db.TABLES:
        if table == "people":
            continue
        tables[table] = services.list_items(table, person_id, order_by="id", descending=False, db_path=db_path)
    return tables


def export_json_backup(db_path: Path | str = db.DB_PATH, person_id: int | None = None) -> str:
    tables = _person_scoped_tables(person_id, db_path=db_path) if person_id is not None else db.export_all_tables(db_path=db_path)
    return json.dumps({"version": 1, "tables": tables}, indent=2)


def _validate_backup_tables(tables: dict) -> dict:
    validated = {}
    for table, rows in tables.items():
        if table not in db.TABLES:
            validated[table] = rows
            continue
        if not isinstance(rows, list):
            raise ValueError(f"Backup table '{table}' must be a list of records.")
        validated_rows = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"Backup table '{table}' contains a non-object record.")
            values = {key: value for key, value in row.items() if key in {"id", *db.TABLE_COLUMNS[table]}}
            data = {key: value for key, value in values.items() if key not in SYSTEM_COLUMNS}
            errors = BACKUP_VALIDATORS[table](data)
            if errors:
                raise ValueError(f"Backup table '{table}' row {index} is invalid: {'; '.join(errors)}")
            if table == "lab_results":
                for key in ("numeric_value", "reference_low", "reference_high"):
                    if key in values and not is_blank(values[key]):
                        values[key] = normalize_optional_number(values[key])
            elif table == "wearable_records" and "value" in values and not is_blank(values["value"]):
                values["value"] = float(values["value"])
            elif table == "health_entries" and "severity" in values and not is_blank(values["severity"]):
                values["severity"] = int(values["severity"])
            validated_rows.append(values)
        validated[table] = validated_rows
    return validated


def import_json_backup(payload_text: str, clear_existing: bool = False, db_path: Path | str = db.DB_PATH) -> None:
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise ValueError("Backup JSON must be an object.")
    tables = payload.get("tables", payload)
    if not isinstance(tables, dict):
        raise ValueError("Backup JSON 'tables' must be an object.")
    tables = _validate_backup_tables(tables)
    db.import_all_tables(tables, clear_existing=clear_existing, db_path=db_path)


def export_fhir_bundle(version: str = "R4", person_id: int | None = None, db_path: Path | str = db.DB_PATH) -> str:
    return fhir.export_bundle(version, person_id=person_id, db_path=db_path)


def import_fhir_bundle(payload_text: str, clear_existing: bool = False, db_path: Path | str = db.DB_PATH) -> dict:
    return fhir.import_bundle(payload_text, clear_existing=clear_existing, db_path=db_path)


def provider_summary_markdown(person_id: int, **kwargs) -> str:
    return services.generate_provider_summary(person_id, **kwargs)


def emergency_snapshot_markdown(person_id: int, **kwargs) -> str:
    return services.generate_emergency_snapshot(person_id, **kwargs)


def sample_labs_csv() -> str:
    frame = pd.DataFrame(
        [
            {
                "test_name": "Hemoglobin A1c",
                "result_value": "5.6",
                "numeric_value": 5.6,
                "unit": "%",
                "reference_low": 4.0,
                "reference_high": 5.6,
                "flag": "Normal",
                "lab_date": "2026-04-28",
                "notes": "",
            }
        ]
    )
    output = StringIO()
    frame.to_csv(output, index=False)
    return output.getvalue()


def sample_wearables_csv() -> str:
    frame = pd.DataFrame(
        [{"metric_type": "Steps", "value": 7500, "unit": "steps", "timestamp": "2026-04-28", "source": "Manual"}]
    )
    output = StringIO()
    frame.to_csv(output, index=False)
    return output.getvalue()
