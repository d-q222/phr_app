from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "phr.db"
SCHEMA_PATH = APP_DIR / "schema.sql"

TABLES = [
    "people",
    "allergies",
    "medications",
    "lab_results",
    "health_entries",
    "appointments",
    "reminders",
    "wearable_records",
]

TABLE_COLUMNS = {
    "people": [
        "name",
        "date_of_birth",
        "sex",
        "relationship",
        "emergency_contact",
        "notes",
        "profile_password_enabled",
        "profile_password_hash",
        "profile_password_hint",
        "created_at",
        "updated_at",
    ],
    "allergies": ["person_id", "allergen", "reaction", "severity", "notes", "created_at", "updated_at"],
    "medications": [
        "person_id",
        "name",
        "dose",
        "frequency",
        "start_date",
        "end_date",
        "status",
        "reason",
        "notes",
        "created_at",
        "updated_at",
    ],
    "lab_results": [
        "person_id",
        "test_name",
        "result_value",
        "numeric_value",
        "unit",
        "reference_low",
        "reference_high",
        "flag",
        "lab_date",
        "notes",
        "created_at",
        "updated_at",
    ],
    "health_entries": [
        "person_id",
        "entry_date",
        "title",
        "body_system",
        "body_part",
        "severity",
        "note",
        "created_at",
        "updated_at",
    ],
    "appointments": [
        "person_id",
        "appointment_date",
        "title",
        "provider",
        "location",
        "status",
        "notes",
        "created_at",
        "updated_at",
    ],
    "reminders": ["person_id", "reminder_type", "title", "due_date", "status", "notes", "created_at", "updated_at"],
    "wearable_records": ["person_id", "metric_type", "value", "unit", "timestamp", "source", "created_at"],
}


def get_connection(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Return a SQLite connection with foreign key enforcement enabled."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: Path | str = DB_PATH) -> Path:
    """Create the local SQLite database and all MVP tables if needed."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with get_connection(db_path) as connection:
        connection.executescript(schema)

    return db_path


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def create_record(table: str, data: dict, db_path: Path | str = DB_PATH) -> int:
    if table not in TABLE_COLUMNS:
        raise ValueError(f"Unknown table: {table}")
    values = {key: value for key, value in data.items() if key in TABLE_COLUMNS[table]}
    stamp = now_iso()
    if "created_at" in TABLE_COLUMNS[table]:
        values.setdefault("created_at", stamp)
    if "updated_at" in TABLE_COLUMNS[table]:
        values.setdefault("updated_at", stamp)
    columns = list(values)
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    sql = f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})"
    with get_connection(db_path) as connection:
        cursor = connection.execute(sql, [values[column] for column in columns])
        return int(cursor.lastrowid)


def update_record(table: str, record_id: int, data: dict, db_path: Path | str = DB_PATH) -> None:
    if table not in TABLE_COLUMNS:
        raise ValueError(f"Unknown table: {table}")
    values = {key: value for key, value in data.items() if key in TABLE_COLUMNS[table]}
    if "updated_at" in TABLE_COLUMNS[table]:
        values["updated_at"] = now_iso()
    if not values:
        return
    assignments = ", ".join(f"{column} = ?" for column in values)
    sql = f"UPDATE {table} SET {assignments} WHERE id = ?"
    with get_connection(db_path) as connection:
        connection.execute(sql, [*values.values(), record_id])


def delete_record(table: str, record_id: int, db_path: Path | str = DB_PATH) -> None:
    if table not in TABLE_COLUMNS:
        raise ValueError(f"Unknown table: {table}")
    with get_connection(db_path) as connection:
        connection.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))


def delete_records_for_person(person_id: int, db_path: Path | str = DB_PATH) -> None:
    """Delete all child records for a profile in one transaction."""
    with get_connection(db_path) as connection:
        for table in reversed(TABLES):
            if table == "people":
                continue
            connection.execute(f"DELETE FROM {table} WHERE person_id = ?", (person_id,))


def get_record(table: str, record_id: int, db_path: Path | str = DB_PATH) -> dict | None:
    if table not in TABLE_COLUMNS:
        raise ValueError(f"Unknown table: {table}")
    with get_connection(db_path) as connection:
        row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    return row_to_dict(row)


def list_records(
    table: str,
    person_id: int | None = None,
    filters: dict | None = None,
    order_by: str = "id",
    descending: bool = True,
    limit: int | None = None,
    db_path: Path | str = DB_PATH,
) -> list[dict]:
    if table not in TABLE_COLUMNS:
        raise ValueError(f"Unknown table: {table}")
    allowed_columns = {"id", *TABLE_COLUMNS[table]}
    if order_by not in allowed_columns:
        raise ValueError(f"Unsupported order_by column: {order_by}")

    where = []
    params = []
    if person_id is not None and "person_id" in allowed_columns:
        where.append("person_id = ?")
        params.append(person_id)
    for key, value in (filters or {}).items():
        if value in (None, ""):
            continue
        if key.endswith("__like"):
            column = key.removesuffix("__like")
            if column not in allowed_columns:
                raise ValueError(f"Unsupported filter column: {column}")
            where.append(f"{column} LIKE ?")
            params.append(f"%{value}%")
        elif key.endswith("__gte"):
            column = key.removesuffix("__gte")
            if column not in allowed_columns:
                raise ValueError(f"Unsupported filter column: {column}")
            where.append(f"{column} >= ?")
            params.append(value)
        elif key.endswith("__lte"):
            column = key.removesuffix("__lte")
            if column not in allowed_columns:
                raise ValueError(f"Unsupported filter column: {column}")
            where.append(f"{column} <= ?")
            params.append(value)
        else:
            if key not in allowed_columns:
                raise ValueError(f"Unsupported filter column: {key}")
            where.append(f"{key} = ?")
            params.append(value)

    direction = "DESC" if descending else "ASC"
    sql = f"SELECT * FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order_by} {direction}"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    with get_connection(db_path) as connection:
        rows = connection.execute(sql, params).fetchall()
    return rows_to_dicts(rows)


def list_people(db_path: Path | str = DB_PATH) -> list[dict]:
    return list_records("people", order_by="name", descending=False, db_path=db_path)


def create_person(data: dict, db_path: Path | str = DB_PATH) -> int:
    return create_record("people", data, db_path=db_path)


def export_all_tables(db_path: Path | str = DB_PATH) -> dict:
    return {table: list_records(table, order_by="id", descending=False, db_path=db_path) for table in TABLES}


def _import_row_sql(table: str, values: dict) -> tuple[str, list]:
    columns = list(values)
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    params = [values[column] for column in columns]

    if "id" not in values:
        return f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})", params

    update_columns = [column for column in columns if column != "id"]
    if not update_columns:
        return f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) ON CONFLICT(id) DO NOTHING", params

    assignments = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    sql = (
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {assignments}"
    )
    return sql, params


def import_all_tables(payload: dict, clear_existing: bool = False, db_path: Path | str = DB_PATH) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Backup payload tables must be a JSON object.")

    with get_connection(db_path) as connection:
        if clear_existing:
            for table in reversed(TABLES):
                connection.execute(f"DELETE FROM {table}")
        for table in TABLES:
            rows = payload.get(table, [])
            if not isinstance(rows, list):
                raise ValueError(f"Backup table '{table}' must be a list of records.")
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError(f"Backup table '{table}' contains a non-object record.")
                values = {key: value for key, value in row.items() if key in {"id", *TABLE_COLUMNS[table]}}
                if not values:
                    continue
                sql, params = _import_row_sql(table, values)
                connection.execute(sql, params)
