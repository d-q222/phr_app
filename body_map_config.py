from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping


BodyPartId = Literal[
    "heart",
    "lungs",
    "brain",
    "liver",
    "kidneys",
    "stomach_intestines",
    "bones",
    "muscles",
    "skin",
    "thyroid",
    "pancreas",
    "lymph_nodes",
    "reproductive_organs",
    "general_body",
]
BodySystemId = Literal[
    "cardiovascular",
    "respiratory",
    "neurologic",
    "gastrointestinal_hepatobiliary",
    "renal_urinary",
    "endocrine_metabolic",
    "hematologic",
    "immune_lymphatic",
    "musculoskeletal",
    "dermatologic",
    "reproductive",
    "general_preventive",
]
RelevanceType = Literal[
    "organ_function_marker",
    "risk_marker",
    "injury_marker",
    "systemic_marker",
    "symptom",
    "diagnosis",
    "medication",
    "medication_safety_marker",
    "imaging_or_procedure",
    "wearable_metric",
    "appointment_or_note",
    "cross_system_related",
]
MappingConfidence = Literal["high", "medium", "low"]
RelationshipStrength = Literal["primary", "secondary"]


BODY_PART_IDS: tuple[BodyPartId, ...] = (
    "heart",
    "lungs",
    "brain",
    "liver",
    "kidneys",
    "stomach_intestines",
    "bones",
    "muscles",
    "skin",
    "thyroid",
    "pancreas",
    "lymph_nodes",
    "reproductive_organs",
    "general_body",
)
BODY_SYSTEM_IDS: tuple[BodySystemId, ...] = (
    "cardiovascular",
    "respiratory",
    "neurologic",
    "gastrointestinal_hepatobiliary",
    "renal_urinary",
    "endocrine_metabolic",
    "hematologic",
    "immune_lymphatic",
    "musculoskeletal",
    "dermatologic",
    "reproductive",
    "general_preventive",
)
RELEVANCE_TYPE_IDS: tuple[RelevanceType, ...] = (
    "organ_function_marker",
    "risk_marker",
    "injury_marker",
    "systemic_marker",
    "symptom",
    "diagnosis",
    "medication",
    "medication_safety_marker",
    "imaging_or_procedure",
    "wearable_metric",
    "appointment_or_note",
    "cross_system_related",
)
MAPPING_CONFIDENCE_IDS: tuple[MappingConfidence, ...] = ("high", "medium", "low")
RELATIONSHIP_STRENGTH_IDS: tuple[RelationshipStrength, ...] = ("primary", "secondary")


@dataclass(frozen=True)
class BodySystemDefinition:
    """A canonical body-system ID and its display label."""

    id: BodySystemId
    display_name: str


@dataclass(frozen=True)
class BodyPartDefinition:
    """A canonical body part and its deterministic system relationships."""

    id: BodyPartId
    display_name: str
    primary_systems: tuple[BodySystemId, ...]
    related_systems: tuple[BodySystemId, ...] = ()


@dataclass(frozen=True)
class MappingRelationship:
    """A body-part or body-system target with its relationship strength."""

    id: str
    relationship_strength: RelationshipStrength


@dataclass(frozen=True)
class RecordBodyMapping:
    """A curated, non-diagnostic relationship between a record name and body areas."""

    body_parts: tuple[MappingRelationship, ...]
    body_systems: tuple[MappingRelationship, ...]
    relevance_type: RelevanceType
    confidence: MappingConfidence


@dataclass(frozen=True)
class RecordMappingDefinition:
    """A canonical lookup name, its explicit aliases, and validated mapping."""

    record_name: str
    aliases: tuple[str, ...]
    mapping: RecordBodyMapping


BODY_SYSTEMS: Mapping[BodySystemId, BodySystemDefinition] = MappingProxyType(
    {
        system.id: system
        for system in (
            BodySystemDefinition("cardiovascular", "Cardiovascular"),
            BodySystemDefinition("respiratory", "Respiratory"),
            BodySystemDefinition("neurologic", "Neurologic"),
            BodySystemDefinition("gastrointestinal_hepatobiliary", "Gastrointestinal / Hepatobiliary"),
            BodySystemDefinition("renal_urinary", "Renal / Urinary"),
            BodySystemDefinition("endocrine_metabolic", "Endocrine / Metabolic"),
            BodySystemDefinition("hematologic", "Hematologic"),
            BodySystemDefinition("immune_lymphatic", "Immune / Lymphatic"),
            BodySystemDefinition("musculoskeletal", "Musculoskeletal"),
            BodySystemDefinition("dermatologic", "Dermatologic"),
            BodySystemDefinition("reproductive", "Reproductive"),
            BodySystemDefinition("general_preventive", "General / Preventive"),
        )
    }
)

BODY_PARTS: Mapping[BodyPartId, BodyPartDefinition] = MappingProxyType(
    {
        part.id: part
        for part in (
            BodyPartDefinition("heart", "Heart", ("cardiovascular",), ("endocrine_metabolic", "renal_urinary", "respiratory")),
            BodyPartDefinition("lungs", "Lungs", ("respiratory",), ("cardiovascular",)),
            BodyPartDefinition("brain", "Brain", ("neurologic",), ("cardiovascular",)),
            BodyPartDefinition("liver", "Liver", ("gastrointestinal_hepatobiliary",), ("endocrine_metabolic",)),
            BodyPartDefinition("kidneys", "Kidneys", ("renal_urinary",), ("cardiovascular", "endocrine_metabolic")),
            BodyPartDefinition("stomach_intestines", "Stomach & Intestines", ("gastrointestinal_hepatobiliary",)),
            BodyPartDefinition("bones", "Bones", ("musculoskeletal",), ("endocrine_metabolic", "hematologic")),
            BodyPartDefinition("muscles", "Muscles", ("musculoskeletal",), ("endocrine_metabolic",)),
            BodyPartDefinition("skin", "Skin", ("dermatologic",), ("immune_lymphatic",)),
            BodyPartDefinition("thyroid", "Thyroid", ("endocrine_metabolic",)),
            BodyPartDefinition("pancreas", "Pancreas", ("endocrine_metabolic",), ("gastrointestinal_hepatobiliary",)),
            BodyPartDefinition("lymph_nodes", "Lymph Nodes", ("immune_lymphatic",), ("hematologic",)),
            BodyPartDefinition("reproductive_organs", "Reproductive Organs", ("reproductive",), ("endocrine_metabolic",)),
            BodyPartDefinition("general_body", "General / Whole Body", ("general_preventive",)),
        )
    }
)

# This explicit alias is the stable organ-to-system interface used by later body-map parts.
BODY_PART_TO_SYSTEMS: Mapping[BodyPartId, BodyPartDefinition] = BODY_PARTS


def _relationships(
    primary: tuple[str, ...], secondary: tuple[str, ...] = ()
) -> tuple[MappingRelationship, ...]:
    return tuple(MappingRelationship(item, "primary") for item in primary) + tuple(
        MappingRelationship(item, "secondary") for item in secondary
    )


_DEFAULT_MAPPING_DEFINITIONS = (
    RecordMappingDefinition(
        "ldl",
        ("LDL cholesterol",),
        RecordBodyMapping(_relationships(("heart",)), _relationships(("cardiovascular",)), "risk_marker", "high"),
    ),
    RecordMappingDefinition(
        "hdl",
        ("HDL cholesterol",),
        RecordBodyMapping(_relationships(("heart",)), _relationships(("cardiovascular",)), "risk_marker", "high"),
    ),
    RecordMappingDefinition(
        "triglycerides",
        (),
        RecordBodyMapping(
            _relationships(("heart",), ("liver",)),
            _relationships(("cardiovascular",), ("endocrine_metabolic", "gastrointestinal_hepatobiliary")),
            "risk_marker",
            "high",
        ),
    ),
    RecordMappingDefinition(
        "creatinine",
        (),
        RecordBodyMapping(_relationships(("kidneys",)), _relationships(("renal_urinary",)), "organ_function_marker", "high"),
    ),
    RecordMappingDefinition(
        "estimated glomerular filtration rate",
        ("eGFR", "estimated GFR"),
        RecordBodyMapping(_relationships(("kidneys",)), _relationships(("renal_urinary",)), "organ_function_marker", "high"),
    ),
    RecordMappingDefinition(
        "bun",
        ("blood urea nitrogen",),
        RecordBodyMapping(_relationships(("kidneys",)), _relationships(("renal_urinary",)), "organ_function_marker", "high"),
    ),
    RecordMappingDefinition(
        "alt",
        ("alanine aminotransferase",),
        RecordBodyMapping(_relationships(("liver",)), _relationships(("gastrointestinal_hepatobiliary",)), "injury_marker", "high"),
    ),
    RecordMappingDefinition(
        "ast",
        ("aspartate aminotransferase",),
        RecordBodyMapping(
            _relationships(("liver",), ("heart", "muscles")),
            _relationships(("gastrointestinal_hepatobiliary",), ("cardiovascular", "musculoskeletal")),
            "injury_marker",
            "medium",
        ),
    ),
    RecordMappingDefinition(
        "tsh",
        ("thyroid stimulating hormone",),
        RecordBodyMapping(_relationships(("thyroid",)), _relationships(("endocrine_metabolic",)), "organ_function_marker", "high"),
    ),
    RecordMappingDefinition(
        "a1c",
        ("HbA1c", "hemoglobin A1c"),
        RecordBodyMapping(
            _relationships(("pancreas",), ("heart", "kidneys")),
            _relationships(("endocrine_metabolic",), ("cardiovascular", "renal_urinary")),
            "risk_marker",
            "high",
        ),
    ),
    RecordMappingDefinition(
        "glucose",
        (),
        RecordBodyMapping(_relationships(("pancreas",)), _relationships(("endocrine_metabolic",)), "organ_function_marker", "high"),
    ),
    RecordMappingDefinition(
        "wbc",
        ("white blood cell count",),
        RecordBodyMapping(
            _relationships(("lymph_nodes",)),
            _relationships(("immune_lymphatic", "hematologic")),
            "systemic_marker",
            "medium",
        ),
    ),
    RecordMappingDefinition(
        "hemoglobin",
        (),
        RecordBodyMapping(_relationships(("general_body",)), _relationships(("hematologic",)), "organ_function_marker", "medium"),
    ),
    RecordMappingDefinition(
        "crp",
        ("C-reactive protein",),
        RecordBodyMapping(
            _relationships(("general_body",)),
            _relationships(("general_preventive",), ("immune_lymphatic",)),
            "systemic_marker",
            "medium",
        ),
    ),
)


def normalize_record_name(record_name: str) -> str:
    """Normalize case, whitespace, and ordinary punctuation without fuzzy matching."""

    if not isinstance(record_name, str):
        return ""
    return " ".join(re.sub(r"[\W_]+", " ", record_name.casefold()).split())


def validate_body_map_definitions() -> None:
    """Validate canonical body-part and body-system definitions."""

    if tuple(BODY_PARTS) != BODY_PART_IDS or tuple(BODY_SYSTEMS) != BODY_SYSTEM_IDS:
        raise ValueError("Canonical body-map definitions do not match their ID lists")
    for system in BODY_SYSTEMS.values():
        if not system.display_name.strip():
            raise ValueError(f"Body system {system.id!r} requires a display name")
    for part in BODY_PARTS.values():
        if not part.display_name.strip() or not part.primary_systems:
            raise ValueError(f"Body part {part.id!r} requires a display name and primary system")
        referenced = part.primary_systems + part.related_systems
        if len(referenced) != len(set(referenced)):
            raise ValueError(f"Body part {part.id!r} has duplicate system relationships")
        if not set(referenced).issubset(BODY_SYSTEMS):
            raise ValueError(f"Body part {part.id!r} references an unknown system")


def validate_record_mapping(mapping: RecordBodyMapping) -> None:
    """Reject empty mappings and references outside the canonical vocabulary."""

    if not mapping.body_parts or not mapping.body_systems:
        raise ValueError("Record mappings require at least one body part and body system")
    if mapping.relevance_type not in RELEVANCE_TYPE_IDS:
        raise ValueError(f"Unknown relevance type: {mapping.relevance_type}")
    if mapping.confidence not in MAPPING_CONFIDENCE_IDS:
        raise ValueError(f"Unknown mapping confidence: {mapping.confidence}")

    for label, relationships, valid_ids in (
        ("body part", mapping.body_parts, BODY_PART_IDS),
        ("body system", mapping.body_systems, BODY_SYSTEM_IDS),
    ):
        ids = [relationship.id for relationship in relationships]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Record mapping has duplicate {label} relationships")
        if not any(relationship.relationship_strength == "primary" for relationship in relationships):
            raise ValueError(f"Record mapping requires a primary {label} relationship")
        for relationship in relationships:
            if relationship.id not in valid_ids:
                raise ValueError(f"Unknown {label}: {relationship.id}")
            if relationship.relationship_strength not in RELATIONSHIP_STRENGTH_IDS:
                raise ValueError(f"Unknown relationship strength: {relationship.relationship_strength}")


def build_record_mapping_registry(
    definitions: tuple[RecordMappingDefinition, ...],
) -> tuple[Mapping[str, RecordBodyMapping], Mapping[str, str]]:
    """Validate definitions and return immutable mapping and normalized-alias registries."""

    mappings: dict[str, RecordBodyMapping] = {}
    lookup: dict[str, str] = {}
    for definition in definitions:
        key = normalize_record_name(definition.record_name)
        if not key:
            raise ValueError("Record mapping names cannot be empty")
        if key in mappings:
            raise ValueError(f"Duplicate record mapping name: {definition.record_name}")
        validate_record_mapping(definition.mapping)
        mappings[key] = definition.mapping
        for name in (definition.record_name, *definition.aliases):
            normalized = normalize_record_name(name)
            if not normalized:
                raise ValueError("Record mapping aliases cannot be empty")
            if normalized in lookup:
                raise ValueError(f"Record mapping alias collision: {name}")
            lookup[normalized] = key
    return MappingProxyType(mappings), MappingProxyType(lookup)


validate_body_map_definitions()
DEFAULT_RECORD_MAPPINGS, DEFAULT_RECORD_MAPPING_ALIASES = build_record_mapping_registry(
    _DEFAULT_MAPPING_DEFINITIONS
)


def get_default_record_mapping(record_name: str) -> RecordBodyMapping | None:
    """Return a curated default mapping or None for unknown or ambiguous names."""

    # Uppercase EGFR commonly names a gene/receptor; only explicit eGFR casing or expanded lab names map.
    if isinstance(record_name, str) and record_name.strip() == "EGFR":
        return None
    key = DEFAULT_RECORD_MAPPING_ALIASES.get(normalize_record_name(record_name))
    return DEFAULT_RECORD_MAPPINGS.get(key) if key else None
