from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import db
import services
from body_map_config import (
    BODY_PARTS,
    BODY_SYSTEMS,
    BodyPartId,
    BodySystemId,
    MappingConfidence,
    RelationshipStrength,
    RelevanceType,
    get_default_record_mapping,
    normalize_record_name,
)


@dataclass(frozen=True)
class NormalizedBodyRecord:
    """One source record normalized for body-map retrieval without medical interpretation."""

    record_id: int
    person_id: int
    source_table: str
    record_type: str
    name: str
    display_name: str
    date: str | None
    value: Any | None
    unit: str | None
    status_flag: str | None
    reference_range: str | None
    body_parts: tuple[BodyPartId, ...]
    body_systems: tuple[BodySystemId, ...]
    relevance_type: RelevanceType
    relationship_strength: RelationshipStrength
    mapping_source: str
    mapping_confidence: MappingConfidence
    summary_text: str | None
    raw_record: dict[str, Any]


_RECORD_ADAPTERS = {
    "lab_results": ("lab", "test_name", "lab_date", "result_value", "unit", "flag", "notes"),
    "medications": ("medication", "name", "start_date", "dose", None, "status", "reason"),
    "health_entries": ("health_entry", "title", "entry_date", "severity", None, None, "note"),
    "appointments": ("appointment", "title", "appointment_date", None, None, "status", "notes"),
    "wearable_records": ("wearable", "metric_type", "timestamp", "value", "unit", None, None),
}

_STORED_RELEVANCE_TYPES: dict[str, RelevanceType] = {
    "lab_results": "organ_function_marker",
    "medications": "medication",
    "health_entries": "symptom",
    "appointments": "appointment_or_note",
    "wearable_records": "wearable_metric",
}

_SYSTEM_ALIASES = {
    normalize_record_name(system_id): system_id for system_id in BODY_SYSTEMS
} | {
    normalize_record_name(system.display_name): system_id for system_id, system in BODY_SYSTEMS.items()
} | {
    "general": "general_preventive",
    "gastrointestinal": "gastrointestinal_hepatobiliary",
    "endocrine": "endocrine_metabolic",
    "renal urinary": "renal_urinary",
    "immune allergy": "immune_lymphatic",
}

_PART_ALIASES = {
    normalize_record_name(part_id): part_id for part_id in BODY_PARTS
} | {
    normalize_record_name(part.display_name): part_id for part_id, part in BODY_PARTS.items()
}


def _stored_ids(value: object, aliases: dict[str, str]) -> tuple[str, ...]:
    if not isinstance(value, str):
        return ()
    result = []
    for item in value.replace(";", ",").replace("|", ",").split(","):
        canonical = aliases.get(normalize_record_name(item))
        if canonical and canonical not in result:
            result.append(canonical)
    return tuple(result)


def _stored_mapping(record: dict[str, Any]) -> tuple[tuple[BodyPartId, ...], tuple[BodySystemId, ...]] | None:
    parts = list(_stored_ids(record.get("body_part"), _PART_ALIASES))
    systems = list(_stored_ids(record.get("body_system"), _SYSTEM_ALIASES))
    if not parts and not systems:
        return None

    explicitly_stored_systems = tuple(systems)
    for part_id in tuple(parts):
        for system_id in BODY_PARTS[part_id].primary_systems:
            if system_id not in systems:
                systems.append(system_id)
    for part_id, part in BODY_PARTS.items():
        if any(system_id in part.primary_systems for system_id in explicitly_stored_systems) and part_id not in parts:
            parts.append(part_id)
    return tuple(parts), tuple(systems)


def _reference_range(record: dict[str, Any]) -> str | None:
    low, high = record.get("reference_low"), record.get("reference_high")
    if low is None and high is None:
        return None
    return f"{'' if low is None else low}\u2013{'' if high is None else high}"


def _normalize_record(
    table: str,
    record: dict[str, Any],
    body_part_id: BodyPartId,
) -> NormalizedBodyRecord | None:
    record_type, name_field, date_field, value_field, unit_field, flag_field, summary_field = _RECORD_ADAPTERS[table]
    name = str(record.get(name_field) or "")
    stored = _stored_mapping(record)
    if stored:
        body_parts, body_systems = stored
        relevance_type = _STORED_RELEVANCE_TYPES[table]
        confidence: MappingConfidence = "high"
        strength: RelationshipStrength = "primary"
        mapping_source = "stored"
    else:
        mapping = get_default_record_mapping(name)
        if mapping is None:
            return None
        body_parts = tuple(relationship.id for relationship in mapping.body_parts)
        body_systems = tuple(relationship.id for relationship in mapping.body_systems)
        if body_part_id not in body_parts:
            return None
        relevance_type = mapping.relevance_type
        confidence = mapping.confidence
        strength = next(
            relationship.relationship_strength
            for relationship in mapping.body_parts
            if relationship.id == body_part_id
        )
        mapping_source = "curated_default"

    if body_part_id not in body_parts:
        return None
    value = record.get(value_field) if value_field else None
    if table == "lab_results" and value in (None, ""):
        value = record.get("numeric_value")
    return NormalizedBodyRecord(
        record_id=int(record["id"]),
        person_id=int(record["person_id"]),
        source_table=table,
        record_type=record_type,
        name=name,
        display_name=name,
        date=str(record[date_field]) if record.get(date_field) not in (None, "") else None,
        value=value,
        unit=str(record[unit_field]) if unit_field and record.get(unit_field) not in (None, "") else None,
        status_flag=str(record[flag_field]) if flag_field and record.get(flag_field) not in (None, "") else None,
        reference_range=_reference_range(record) if table == "lab_results" else None,
        body_parts=body_parts,
        body_systems=body_systems,
        relevance_type=relevance_type,
        relationship_strength=strength,
        mapping_source=mapping_source,
        mapping_confidence=confidence,
        summary_text=str(record[summary_field]) if summary_field and record.get(summary_field) not in (None, "") else None,
        raw_record=dict(record),
    )


def get_records_for_body_part(
    person_id: int | str,
    body_part_id: str,
    db_path: Path | str | None = None,
) -> list[NormalizedBodyRecord]:
    """Return records from the five health-record tables relevant to one body part and person.

    Exact stored health-entry mappings override curated name defaults. Every source query is scoped
    to ``person_id``; unknown records are excluded and source records are not modified.
    """
    db_path = db.DB_PATH if db_path is None else db_path

    if body_part_id not in BODY_PARTS:
        raise ValueError(f"Unknown body part ID: {body_part_id}")
    try:
        selected_person_id = int(person_id)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid person ID: {person_id!r}") from error

    results = []
    for table in _RECORD_ADAPTERS:
        for record in services.list_items(table, selected_person_id, db_path=db_path):
            normalized = _normalize_record(table, record, body_part_id)
            if normalized is not None:
                results.append(normalized)
    return sorted(
        results,
        key=lambda record: (record.date or "", record.source_table, record.record_id),
        reverse=True,
    )
