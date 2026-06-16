from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

import db


def _parse_iso_date(value: object) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_person(person_id: int, db_path: Path | str = db.DB_PATH) -> dict | None:
    return db.get_record("people", person_id, db_path=db_path)


def list_people(db_path: Path | str = db.DB_PATH) -> list[dict]:
    return db.list_people(db_path=db_path)


def create_person(data: dict, db_path: Path | str = db.DB_PATH) -> int:
    return db.create_person(data, db_path=db_path)


def update_person(person_id: int, data: dict, db_path: Path | str = db.DB_PATH) -> None:
    db.update_record("people", person_id, data, db_path=db_path)


def delete_person(person_id: int, db_path: Path | str = db.DB_PATH) -> None:
    db.delete_records_for_person(person_id, db_path=db_path)
    db.delete_record("people", person_id, db_path=db_path)


def create_item(table: str, person_id: int, data: dict, db_path: Path | str = db.DB_PATH) -> int:
    data = dict(data)
    data["person_id"] = person_id
    return db.create_record(table, data, db_path=db_path)


def update_item(table: str, record_id: int, data: dict, db_path: Path | str = db.DB_PATH) -> None:
    db.update_record(table, record_id, data, db_path=db_path)


def delete_item(table: str, record_id: int, db_path: Path | str = db.DB_PATH) -> None:
    db.delete_record(table, record_id, db_path=db_path)


def list_items(
    table: str,
    person_id: int,
    filters: dict | None = None,
    order_by: str = "id",
    descending: bool = True,
    limit: int | None = None,
    db_path: Path | str = db.DB_PATH,
) -> list[dict]:
    return db.list_records(table, person_id, filters, order_by, descending, limit, db_path=db_path)


def active_medications(person_id: int, db_path: Path | str = db.DB_PATH) -> list[dict]:
    return list_items("medications", person_id, {"status": "Active"}, order_by="name", descending=False, db_path=db_path)


def latest_labs(person_id: int, db_path: Path | str = db.DB_PATH) -> list[dict]:
    labs = list_items("lab_results", person_id, order_by="id", descending=True, db_path=db_path)
    labs = sorted(labs, key=lambda lab: (lab.get("lab_date") or "", int(lab.get("id") or 0)), reverse=True)
    latest_by_test = {}
    for lab in labs:
        latest_by_test.setdefault(lab["test_name"].lower(), lab)
    return list(latest_by_test.values())


def abnormal_labs(person_id: int, db_path: Path | str = db.DB_PATH) -> list[dict]:
    return [
        lab
        for lab in latest_labs(person_id, db_path=db_path)
        if lab.get("flag") in {"High", "Low", "Abnormal", "Critical"}
    ]


def recent_health_entries(person_id: int, limit: int = 5, db_path: Path | str = db.DB_PATH) -> list[dict]:
    return list_items("health_entries", person_id, order_by="entry_date", descending=True, limit=limit, db_path=db_path)


def upcoming_appointments(person_id: int, db_path: Path | str = db.DB_PATH) -> list[dict]:
    return list_items(
        "appointments",
        person_id,
        {"appointment_date__gte": date.today().isoformat()},
        order_by="appointment_date",
        descending=False,
        db_path=db_path,
    )


def overdue_reminders(person_id: int, db_path: Path | str = db.DB_PATH) -> list[dict]:
    reminders = list_items("reminders", person_id, order_by="due_date", descending=False, db_path=db_path)
    today = date.today()
    result = []
    for reminder in reminders:
        if reminder.get("status") in {"Completed", "Dismissed"}:
            continue
        due_date = _parse_iso_date(reminder.get("due_date"))
        if due_date and due_date < today:
            result.append(reminder)
    return result


def due_soon_reminders(person_id: int, db_path: Path | str = db.DB_PATH) -> list[dict]:
    reminders = list_items("reminders", person_id, order_by="due_date", descending=False, db_path=db_path)
    today = date.today()
    result = []
    for reminder in reminders:
        if reminder.get("status") in {"Completed", "Dismissed"}:
            continue
        due_date = _parse_iso_date(reminder.get("due_date"))
        if not due_date:
            continue
        if 0 <= (due_date - today).days <= 7:
            result.append(reminder)
    return result


def wearable_summary(person_id: int, db_path: Path | str = db.DB_PATH) -> list[dict]:
    records = list_items("wearable_records", person_id, order_by="timestamp", descending=True, db_path=db_path)
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[record["metric_type"]].append(record)

    summaries = []
    for metric_type, values in groups.items():
        numbers = [number for number in (_safe_float(record.get("value")) for record in values) if number is not None]
        if not numbers:
            continue
        latest = values[0]
        summaries.append(
            {
                "metric_type": metric_type,
                "latest": latest["value"],
                "unit": latest.get("unit"),
                "latest_timestamp": latest["timestamp"],
                "average": round(sum(numbers) / len(numbers), 2),
                "minimum": min(numbers),
                "maximum": max(numbers),
                "count": len(numbers),
            }
        )
    return summaries


def dashboard_data(person_id: int, db_path: Path | str = db.DB_PATH) -> dict:
    return {
        "person": get_person(person_id, db_path=db_path),
        "allergies": list_items("allergies", person_id, order_by="allergen", descending=False, db_path=db_path),
        "active_medications": active_medications(person_id, db_path=db_path),
        "latest_labs": latest_labs(person_id, db_path=db_path),
        "recent_entries": recent_health_entries(person_id, db_path=db_path),
        "upcoming_appointments": upcoming_appointments(person_id, db_path=db_path),
        "overdue_reminders": overdue_reminders(person_id, db_path=db_path),
        "wearable_summary": wearable_summary(person_id, db_path=db_path),
    }


def _date_filter(field: str, start_date: str | None, end_date: str | None) -> dict:
    filters = {}
    if start_date:
        filters[f"{field}__gte"] = start_date
    if end_date:
        filters[f"{field}__lte"] = end_date
    return filters


def filter_health_entries(
    person_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    body_system: str | None = None,
    body_part: str | None = None,
    search: str | None = None,
    db_path: Path | str = db.DB_PATH,
) -> list[dict]:
    filters = _date_filter("entry_date", start_date, end_date)
    if body_system:
        filters["body_system"] = body_system
    if body_part:
        filters["body_part__like"] = body_part
    if search:
        title_matches = list_items("health_entries", person_id, {**filters, "title__like": search}, "entry_date", True, db_path=db_path)
        note_matches = list_items("health_entries", person_id, {**filters, "note__like": search}, "entry_date", True, db_path=db_path)
        seen = set()
        merged = []
        for item in title_matches + note_matches:
            if item["id"] not in seen:
                merged.append(item)
                seen.add(item["id"])
        return sorted(merged, key=lambda item: item["entry_date"], reverse=True)
    return list_items("health_entries", person_id, filters, "entry_date", True, db_path=db_path)


def filter_labs(
    person_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    test_search: str | None = None,
    flag: str | None = None,
    db_path: Path | str = db.DB_PATH,
) -> list[dict]:
    filters = _date_filter("lab_date", start_date, end_date)
    if test_search:
        filters["test_name__like"] = test_search
    if flag:
        filters["flag"] = flag
    return list_items("lab_results", person_id, filters, "lab_date", True, db_path=db_path)


def medication_filters(person_id: int, status: str | None = None, db_path: Path | str = db.DB_PATH) -> list[dict]:
    filters = {"status": status} if status else {}
    return list_items("medications", person_id, filters, "name", False, db_path=db_path)


def reminder_filters(person_id: int, status: str | None = None, db_path: Path | str = db.DB_PATH) -> list[dict]:
    filters = {"status": status} if status else {}
    return list_items("reminders", person_id, filters, "due_date", False, db_path=db_path)


def generate_provider_summary(
    person_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    include_labs: bool = True,
    include_timeline: bool = True,
    include_wearables: bool = True,
    db_path: Path | str = db.DB_PATH,
) -> str:
    person = get_person(person_id, db_path=db_path) or {}
    lines = [
        "# Provider Summary",
        "",
        "## Patient Overview",
        f"- Name: {person.get('name', '')}",
        f"- Date of birth: {person.get('date_of_birth') or ''}",
        f"- Sex: {person.get('sex') or ''}",
        f"- Relationship: {person.get('relationship') or ''}",
        "",
        "## Emergency Contact",
        person.get("emergency_contact") or "Not recorded.",
        "",
        "## Allergies",
    ]
    allergies = list_items("allergies", person_id, order_by="allergen", descending=False, db_path=db_path)
    lines += [f"- {a['allergen']} ({a.get('severity') or 'severity unknown'}): {a.get('reaction') or ''}" for a in allergies] or ["None recorded."]
    lines += ["", "## Active Medications"]
    meds = active_medications(person_id, db_path=db_path)
    lines += [f"- {m['name']} {m.get('dose') or ''} {m.get('frequency') or ''}".strip() for m in meds] or ["None recorded."]
    if include_timeline:
        lines += ["", "## Recent Health Timeline"]
        entries = filter_health_entries(person_id, start_date, end_date, db_path=db_path)[:15]
        lines += [f"- {e['entry_date']}: {e['title']} ({e.get('body_system') or 'General'})" for e in entries] or ["None recorded."]
    if include_labs:
        lines += ["", "## Recent Labs"]
        labs = filter_labs(person_id, start_date, end_date, db_path=db_path)[:20]
        lines += [f"- {l['lab_date']}: {l['test_name']} {l.get('result_value') or l.get('numeric_value') or ''} {l.get('unit') or ''} [{l.get('flag') or 'Unknown'}]".strip() for l in labs] or ["None recorded."]
    lines += ["", "## Upcoming Appointments"]
    appointments = upcoming_appointments(person_id, db_path=db_path)[:10]
    lines += [f"- {a['appointment_date']}: {a['title']} with {a.get('provider') or 'provider not recorded'}" for a in appointments] or ["None recorded."]
    lines += ["", "## Overdue / Active Follow-Up Items"]
    reminders = overdue_reminders(person_id, db_path=db_path) + due_soon_reminders(person_id, db_path=db_path)
    lines += [f"- {r['due_date']}: {r['title']} ({r['status']})" for r in reminders] or ["None recorded."]
    if include_wearables:
        lines += ["", "## Recent Wearable Summary"]
        summaries = wearable_summary(person_id, db_path=db_path)
        lines += [f"- {s['metric_type']}: latest {s['latest']} {s.get('unit') or ''}, average {s['average']}".strip() for s in summaries] or ["None recorded."]
    lines += ["", "## Patient Notes", person.get("notes") or "None recorded."]
    return "\n".join(lines)


def generate_emergency_snapshot(person_id: int, db_path: Path | str = db.DB_PATH) -> str:
    person = get_person(person_id, db_path=db_path) or {}
    allergies = list_items("allergies", person_id, order_by="allergen", descending=False, db_path=db_path)
    meds = active_medications(person_id, db_path=db_path)
    critical_labs = [lab for lab in latest_labs(person_id, db_path=db_path) if lab.get("flag") in {"Critical", "Abnormal", "High", "Low"}]
    entries = recent_health_entries(person_id, limit=5, db_path=db_path)
    lines = [
        "# Emergency Snapshot",
        "",
        f"**Name:** {person.get('name', '')}",
        f"**Date of Birth:** {person.get('date_of_birth') or ''}",
        f"**Emergency Contact:** {person.get('emergency_contact') or 'Not recorded.'}",
        "",
        "## Allergies",
    ]
    lines += [f"- {a['allergen']}: {a.get('reaction') or ''} ({a.get('severity') or 'severity unknown'})" for a in allergies] or ["None recorded."]
    lines += ["", "## Active Medications"]
    lines += [f"- {m['name']} {m.get('dose') or ''} {m.get('frequency') or ''}".strip() for m in meds] or ["None recorded."]
    lines += ["", "## Key Health Notes"]
    lines += [f"- {e['entry_date']}: {e['title']}" for e in entries] or ["None recorded."]
    lines += ["", "## Recent Critical/Abnormal Labs"]
    lines += [f"- {l['lab_date']}: {l['test_name']} {l.get('result_value') or l.get('numeric_value') or ''} {l.get('unit') or ''} [{l.get('flag')}]".strip() for l in critical_labs] or ["None recorded."]
    return "\n".join(lines)
