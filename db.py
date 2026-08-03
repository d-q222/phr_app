from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "phr.db"
SCHEMA_PATH = APP_DIR / "schema.sql"
DATABASE_BUSY_TIMEOUT_MS = 1_000


class RecordNotFound(LookupError):
    """A record id does not exist, or does not belong to the requesting person.

    The two cases are deliberately indistinguishable: telling a caller that a record
    exists but belongs to someone else would leak the existence of another profile's
    data. This maps onto a single 404 in the future HTTP API.
    """


class DatabaseBusyError(RuntimeError):
    """SQLite could not acquire its write lock within the bounded wait."""

TABLES = [
    "people",
    "allergies",
    "medications",
    "lab_results",
    "health_entries",
    "appointments",
    "reminders",
    "wearable_records",
    "conditions",
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
    "conditions": ["person_id", "condition_name", "source", "noted_date", "notes", "created_at", "updated_at"],
}


def _resolve_db_path(db_path: Path | str | None) -> Path | str:
    """Resolve an omitted database path to ``DB_PATH`` at call time.

    ``DB_PATH`` must be read here rather than captured as a default argument.
    Default arguments are evaluated once when this module is imported, so a
    ``db_path=DB_PATH`` default freezes the real database into the function
    object and makes ``monkeypatch.setattr(db, "DB_PATH", ...)`` a silent no-op.

    Every public helper in this module forwards ``db_path`` untouched, so a
    ``None`` sentinel travels down and resolves exactly once -- here, at the two
    places that actually touch the filesystem.
    """
    return DB_PATH if db_path is None else db_path


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Return a SQLite connection with foreign keys and a bounded native lock wait."""
    connection = sqlite3.connect(_resolve_db_path(db_path), timeout=DATABASE_BUSY_TIMEOUT_MS / 1_000)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {DATABASE_BUSY_TIMEOUT_MS}")
    return connection


@contextmanager
def _write_connection(db_path: Path | str | None):
    """Use SQLite's one-shot busy wait and map only busy/locked failures."""
    try:
        with get_connection(db_path) as connection:
            yield connection
    except sqlite3.OperationalError as exc:
        error_code = (getattr(exc, "sqlite_errorcode", 0) or 0) & 0xFF
        if error_code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            raise DatabaseBusyError(
                "The health record database is busy. Wait a moment and try again."
            ) from exc
        raise


def init_db(db_path: Path | str | None = None) -> Path:
    """Create the local SQLite database and all MVP tables if needed."""
    db_path = Path(_resolve_db_path(db_path))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with _write_connection(db_path) as connection:
        connection.executescript(schema)

    return db_path


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def create_record(table: str, data: dict, db_path: Path | str | None = None) -> int:
    if table not in TABLE_COLUMNS:
        raise ValueError(f"Unknown table: {table}")
    if "person_id" in TABLE_COLUMNS[table]:
        if data.get("person_id") is None:
            raise ValueError(f"person_id is required for table {table}")
    elif "person_id" in data:
        raise ValueError(f"Table {table} is not person-scoped; omit person_id")
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
    with _write_connection(db_path) as connection:
        cursor = connection.execute(sql, [values[column] for column in columns])
        return int(cursor.lastrowid)


def _mutation_scope(table: str, person_id: int | None) -> tuple[str, list[int]]:
    person_scoped = "person_id" in TABLE_COLUMNS[table]
    if person_scoped and person_id is None:
        raise ValueError(f"person_id is required for table {table}")
    if not person_scoped and person_id is not None:
        raise ValueError(f"Table {table} is not person-scoped; omit person_id")
    return ("id = ? AND person_id = ?", [person_id]) if person_scoped else ("id = ?", [])


def update_record(
    table: str,
    record_id: int,
    data: dict,
    db_path: Path | str | None = None,
    *,
    person_id: int | None = None,
) -> None:
    """Update one record, requiring scope for person-owned tables."""
    if table not in TABLE_COLUMNS:
        raise ValueError(f"Unknown table: {table}")
    if "person_id" in data:
        raise ValueError("person_id cannot be changed by an ordinary update")
    where, scope_params = _mutation_scope(table, person_id)
    values = {key: value for key, value in data.items() if key in TABLE_COLUMNS[table]}
    if "updated_at" in TABLE_COLUMNS[table]:
        values["updated_at"] = now_iso()
    assignments = ", ".join(f"{column} = ?" for column in values) or "id = id"
    with _write_connection(db_path) as connection:
        cursor = connection.execute(
            f"UPDATE {table} SET {assignments} WHERE {where}",
            [*values.values(), record_id, *scope_params],
        )
        if cursor.rowcount != 1:
            raise RecordNotFound(f"No {table} record {record_id} for the requested scope")


def delete_record(
    table: str,
    record_id: int,
    db_path: Path | str | None = None,
    *,
    person_id: int | None = None,
) -> None:
    """Delete one record, requiring scope for person-owned tables."""
    if table not in TABLE_COLUMNS:
        raise ValueError(f"Unknown table: {table}")
    where, scope_params = _mutation_scope(table, person_id)
    with _write_connection(db_path) as connection:
        cursor = connection.execute(
            f"DELETE FROM {table} WHERE {where}", (record_id, *scope_params)
        )
        if cursor.rowcount != 1:
            raise RecordNotFound(f"No {table} record {record_id} for the requested scope")


def delete_person(person_id: int, db_path: Path | str | None = None) -> None:
    """Delete one profile and all child rows atomically."""
    with _write_connection(db_path) as connection:
        for table in reversed(TABLES):
            if table == "people":
                continue
            connection.execute(f"DELETE FROM {table} WHERE person_id = ?", (person_id,))
        cursor = connection.execute("DELETE FROM people WHERE id = ?", (person_id,))
        if cursor.rowcount != 1:
            raise RecordNotFound(f"No people record {person_id}")


def get_record(table: str, record_id: int, db_path: Path | str | None = None) -> dict | None:
    if table not in TABLE_COLUMNS:
        raise ValueError(f"Unknown table: {table}")
    with get_connection(db_path) as connection:
        row = connection.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
    return row_to_dict(row)


def list_records(  # noqa: C901
    table: str,
    person_id: int | None = None,
    filters: dict | None = None,
    order_by: str = "id",
    descending: bool = True,
    limit: int | None = None,
    db_path: Path | str | None = None,
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


def list_people(db_path: Path | str | None = None) -> list[dict]:
    return list_records("people", order_by="name", descending=False, db_path=db_path)


def create_person(data: dict, db_path: Path | str | None = None) -> int:
    return create_record("people", data, db_path=db_path)


def export_all_tables(db_path: Path | str | None = None) -> dict:
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


def import_all_tables(payload: dict, clear_existing: bool = False, db_path: Path | str | None = None) -> None:
    if not isinstance(payload, dict):
        raise ValueError("Backup payload tables must be a JSON object.")

    with _write_connection(db_path) as connection:
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
