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
    parse_plain_decimal,
    validate_allergy,
    validate_appointment,
    validate_condition,
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
    "conditions": validate_condition,
}


SYSTEM_COLUMNS = {"id", "person_id", "created_at", "updated_at"}


# Read as absent, the way pandas would normally read them. `import_labs_csv` turns pandas' own
# handling off wholesale, so this restores it -- which means it must cover pandas' whole default
# vocabulary, not the memorable half of it. Anything missing here is a token that used to import as
# absent and would now reach `validate_lab` literally and be rejected.
#
# Spelled out rather than imported from `pandas._libs.parsers.STR_NA_VALUES`: that name is private,
# and an import of it breaking on upgrade would take the app down at import time. Coverage is pinned
# by `test_csv_na_tokens_still_cover_the_pandas_defaults` instead, so drift fails a test run rather
# than a user's import.
#
# Matched case-sensitively, exactly as pandas matches them. Case-folding looks harmless and is not:
# "Na" is sodium. Lowercasing turned a sodium panel's test name into an empty one, and `validate_lab`
# then rejected the row for a missing test name. "None" is a pandas token; "none" and "NONE" are not.
_CSV_NA_TOKENS = {
    "",
    "#N/A",
    "#N/A N/A",
    "#NA",
    "-1.#IND",
    "-1.#QNAN",
    "-NaN",
    "-nan",
    "1.#IND",
    "1.#QNAN",
    "<NA>",
    "N/A",
    "NA",
    "NULL",
    "NaN",
    "None",
    "n/a",
    "nan",
    "null",
}

# The two free-text fields, where such a token is content rather than absence. A lab result really
# can be written "NA" -- for an assay that does not apply -- and blanking it loses what the record
# said. Every other column is coded, numeric or a date, where "NA" only ever means the exporter had
# nothing to put there.
_LITERAL_CSV_FIELDS = {"result_value", "notes"}


def _csv_cell(row, column: str) -> str:
    """One cell of a lab CSV, as text, with absence resolved per column.

    Companion to the `keep_default_na=False` read in `import_labs_csv`: that keeps every token
    literal so a written result survives, and this restores the ordinary reading everywhere a
    literal "NA" would instead make `validate_lab` reject a row that used to import.
    """

    value = row.get(column, "")
    text = "" if value is None else str(value)
    if column in _LITERAL_CSV_FIELDS:
        return text
    # Exact, with no stripping: pandas does not strip before matching either, so a quoted " NA " is
    # a two-space-padded literal to it and must stay one here. Stripping first looked like harmless
    # tolerance and instead blanked a value the merge-base importer kept.
    return "" if text in _CSV_NA_TOKENS else text


def import_labs_csv(file_obj, person_id: int, db_path: Path | str | None = None) -> dict:
    db_path = db.DB_PATH if db_path is None else db_path
    # Both arguments stop pandas rewriting a value before any validation sees it.
    #
    # `dtype=str` disables column type inference. The C parser reads "0.000000000000000001" as 0.0,
    # not 1e-18, so a result stored as a written string reached `parse_plain_decimal` already
    # destroyed and the careful allowlist below charted the rounded number. Inference is also
    # non-local: it applies per column, so one non-numeric row ("<0.01") keeps the whole column as
    # text and the same file imports at full precision.
    #
    # `keep_default_na=False` stops the other rewrite. Pandas treats "NA", "NULL", "N/A" and friends
    # as missing regardless of dtype, so `fillna("")` below blanked them -- and `validate_lab`
    # returns no error for an empty `result_value`, so the row imported with the written result
    # silently gone rather than being reported in `skipped`. `_csv_cell` then puts that reading back
    # for every column except the free-text ones, because `result_value` and `flag` want opposite
    # readings of the same token and one file-wide setting cannot serve both.
    #
    # Together these make the CSV path agree with the UI form, where the value is always a string.
    frame = pd.read_csv(file_obj, dtype=str, keep_default_na=False)
    imported = 0
    skipped = []
    with db.write_transaction(db_path) as connection:
        for index, row in frame.fillna("").iterrows():
            data = {
                "test_name": _csv_cell(row, "test_name"),
                "result_value": _csv_cell(row, "result_value"),
                "numeric_value": _csv_cell(row, "numeric_value"),
                "unit": _csv_cell(row, "unit"),
                "reference_low": _csv_cell(row, "reference_low"),
                "reference_high": _csv_cell(row, "reference_high"),
                # Absent, not "Unknown" -- that is a flag a source can actually record.
                "flag": _csv_cell(row, "flag"),
                "lab_date": _csv_cell(row, "lab_date"),
                "notes": _csv_cell(row, "notes"),
            }
            errors = validate_lab(data)
            if errors:
                skipped.append({"row": int(index) + 2, "errors": errors})
                continue
            data["numeric_value"] = normalize_optional_number(data["numeric_value"])
            if data["numeric_value"] is None:
                # A CSV carrying only a written result still charts, provided that result is
                # unambiguously a number. `is None` because a stored 0 is a real reading.
                data["numeric_value"] = parse_plain_decimal(data["result_value"])
            data["reference_low"] = normalize_optional_number(data["reference_low"])
            data["reference_high"] = normalize_optional_number(data["reference_high"])
            services.create_item(
                "lab_results", person_id, data, db_path=db_path, connection=connection
            )
            imported += 1
    return {"imported": imported, "skipped": skipped}


def import_wearables_csv(file_obj, person_id: int, db_path: Path | str | None = None) -> dict:
    db_path = db.DB_PATH if db_path is None else db_path
    frame = pd.read_csv(file_obj)
    imported = 0
    skipped = []
    with db.write_transaction(db_path) as connection:
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
            services.create_item(
                "wearable_records", person_id, data, db_path=db_path, connection=connection
            )
            imported += 1
    return {"imported": imported, "skipped": skipped}


def _person_scoped_tables(person_id: int, db_path: Path | str | None = None) -> dict:
    db_path = db.DB_PATH if db_path is None else db_path
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


def export_json_backup(db_path: Path | str | None = None, person_id: int | None = None) -> str:
    db_path = db.DB_PATH if db_path is None else db_path
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


def import_json_backup(payload_text: str, clear_existing: bool = False, db_path: Path | str | None = None) -> None:
    db_path = db.DB_PATH if db_path is None else db_path
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise ValueError("Backup JSON must be an object.")
    tables = payload.get("tables", payload)
    if not isinstance(tables, dict):
        raise ValueError("Backup JSON 'tables' must be an object.")
    tables = _validate_backup_tables(tables)
    # Already atomic: import_all_tables owns one transaction for the restore and optional clear.
    db.import_all_tables(tables, clear_existing=clear_existing, db_path=db_path)


def export_fhir_bundle(version: str = "R4", person_id: int | None = None, db_path: Path | str | None = None) -> str:
    db_path = db.DB_PATH if db_path is None else db_path
    return fhir.export_bundle(version, person_id=person_id, db_path=db_path)


def import_fhir_bundle(payload_text: str, clear_existing: bool = False, db_path: Path | str | None = None) -> dict:
    db_path = db.DB_PATH if db_path is None else db_path
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
