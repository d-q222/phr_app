from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pandas as pd

import db
import services
from validation import normalize_optional_number, validate_lab, validate_wearable


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


def export_json_backup(db_path: Path | str = db.DB_PATH) -> str:
    return json.dumps({"version": 1, "tables": db.export_all_tables(db_path=db_path)}, indent=2)


def import_json_backup(payload_text: str, clear_existing: bool = False, db_path: Path | str = db.DB_PATH) -> None:
    payload = json.loads(payload_text)
    tables = payload.get("tables", payload)
    db.import_all_tables(tables, clear_existing=clear_existing, db_path=db_path)


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
