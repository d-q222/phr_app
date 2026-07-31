from __future__ import annotations

import re
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import body_map_config as config  # noqa: E402

REQUIRED_BODY_PART_IDS = {
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
}
REQUIRED_BODY_SYSTEM_IDS = {
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
}
REQUIRED_RELEVANCE_TYPE_IDS = {
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
}


def _targets(mapping, attribute):
    return {
        relationship.id: relationship.relationship_strength
        for relationship in getattr(mapping, attribute)
    }


def test_body_part_ids_match_required_v1_set():
    assert set(config.BODY_PART_IDS) == REQUIRED_BODY_PART_IDS
    assert set(config.BODY_PARTS) == REQUIRED_BODY_PART_IDS


def test_body_system_ids_match_required_v1_set():
    assert set(config.BODY_SYSTEM_IDS) == REQUIRED_BODY_SYSTEM_IDS
    assert set(config.BODY_SYSTEMS) == REQUIRED_BODY_SYSTEM_IDS


def test_relevance_type_ids_match_required_v1_set():
    assert set(config.RELEVANCE_TYPE_IDS) == REQUIRED_RELEVANCE_TYPE_IDS
    assert set(config.MAPPING_CONFIDENCE_IDS) == {"high", "medium", "low"}
    assert set(config.RELATIONSHIP_STRENGTH_IDS) == {"primary", "secondary"}


def test_canonical_ids_are_unique_and_snake_case():
    for identifiers in (
        config.BODY_PART_IDS,
        config.BODY_SYSTEM_IDS,
        config.RELEVANCE_TYPE_IDS,
        config.MAPPING_CONFIDENCE_IDS,
        config.RELATIONSHIP_STRENGTH_IDS,
    ):
        assert len(identifiers) == len(set(identifiers))
        assert all(re.fullmatch(r"[a-z][a-z0-9_]*", identifier) for identifier in identifiers)
    assert all(definition.display_name.strip() for definition in config.BODY_PARTS.values())
    assert all(definition.display_name.strip() for definition in config.BODY_SYSTEMS.values())


def test_every_body_part_has_primary_system():
    for part in config.BODY_PARTS.values():
        assert part.primary_systems
        assert set(part.primary_systems + part.related_systems) <= REQUIRED_BODY_SYSTEM_IDS
        assert len(part.primary_systems) == len(set(part.primary_systems))
        assert len(part.related_systems) == len(set(part.related_systems))
        assert set(part.primary_systems).isdisjoint(part.related_systems)


def test_required_primary_body_system_relationships():
    expected = {
        "heart": "cardiovascular",
        "lungs": "respiratory",
        "brain": "neurologic",
        "liver": "gastrointestinal_hepatobiliary",
        "kidneys": "renal_urinary",
        "thyroid": "endocrine_metabolic",
        "pancreas": "endocrine_metabolic",
        "bones": "musculoskeletal",
        "muscles": "musculoskeletal",
        "skin": "dermatologic",
        "lymph_nodes": "immune_lymphatic",
        "reproductive_organs": "reproductive",
        "general_body": "general_preventive",
    }
    for body_part, body_system in expected.items():
        assert body_system in config.BODY_PART_TO_SYSTEMS[body_part].primary_systems


def test_default_mappings_reference_only_canonical_ids():
    assert len(config.DEFAULT_RECORD_MAPPINGS) == 14
    for mapping in config.DEFAULT_RECORD_MAPPINGS.values():
        assert {item.id for item in mapping.body_parts} <= REQUIRED_BODY_PART_IDS
        assert {item.id for item in mapping.body_systems} <= REQUIRED_BODY_SYSTEM_IDS


def test_default_mapping_values_are_valid():
    for mapping in config.DEFAULT_RECORD_MAPPINGS.values():
        config.validate_record_mapping(mapping)
        assert mapping.relevance_type in REQUIRED_RELEVANCE_TYPE_IDS
        assert mapping.confidence in config.MAPPING_CONFIDENCE_IDS
        assert all(
            item.relationship_strength in config.RELATIONSHIP_STRENGTH_IDS
            for item in mapping.body_parts + mapping.body_systems
        )


def test_aliases_do_not_collide():
    aliases = config.DEFAULT_RECORD_MAPPING_ALIASES
    assert len(aliases) == len(set(aliases))
    assert all(key == config.normalize_record_name(key) for key in aliases)
    assert set(aliases.values()) <= set(config.DEFAULT_RECORD_MAPPINGS)


@pytest.mark.parametrize("record_name", ["ldl", "LDL cholesterol", "hdl", "HDL cholesterol"])
def test_ldl_and_hdl_mappings(record_name):
    mapping = config.get_default_record_mapping(record_name)
    assert _targets(mapping, "body_parts") == {"heart": "primary"}
    assert _targets(mapping, "body_systems") == {"cardiovascular": "primary"}
    assert mapping.relevance_type == "risk_marker"
    assert mapping.confidence == "high"


def test_triglycerides_mapping():
    mapping = config.get_default_record_mapping("triglycerides")
    assert _targets(mapping, "body_parts") == {"heart": "primary", "liver": "secondary"}
    assert _targets(mapping, "body_systems") == {
        "cardiovascular": "primary",
        "endocrine_metabolic": "secondary",
        "gastrointestinal_hepatobiliary": "secondary",
    }
    assert mapping.relevance_type == "risk_marker"


@pytest.mark.parametrize("record_name", ["creatinine", "eGFR", "estimated GFR", "BUN"])
def test_kidney_function_mappings(record_name):
    mapping = config.get_default_record_mapping(record_name)
    assert _targets(mapping, "body_parts") == {"kidneys": "primary"}
    assert _targets(mapping, "body_systems") == {"renal_urinary": "primary"}
    assert mapping.relevance_type == "organ_function_marker"


@pytest.mark.parametrize(
    ("record_name", "body_part", "body_system", "relevance_type"),
    [
        ("ALT", "liver", "gastrointestinal_hepatobiliary", "injury_marker"),
        ("TSH", "thyroid", "endocrine_metabolic", "organ_function_marker"),
        ("glucose", "pancreas", "endocrine_metabolic", "organ_function_marker"),
        ("hemoglobin", "general_body", "hematologic", "organ_function_marker"),
    ],
)
def test_single_area_required_mappings(record_name, body_part, body_system, relevance_type):
    mapping = config.get_default_record_mapping(record_name)
    assert _targets(mapping, "body_parts") == {body_part: "primary"}
    assert _targets(mapping, "body_systems") == {body_system: "primary"}
    assert mapping.relevance_type == relevance_type


def test_ast_mapping_preserves_multisystem_uncertainty():
    mapping = config.get_default_record_mapping("AST")
    assert _targets(mapping, "body_parts") == {
        "liver": "primary",
        "heart": "secondary",
        "muscles": "secondary",
    }
    assert _targets(mapping, "body_systems") == {
        "gastrointestinal_hepatobiliary": "primary",
        "cardiovascular": "secondary",
        "musculoskeletal": "secondary",
    }
    assert mapping.relevance_type == "injury_marker"
    assert mapping.confidence == "medium"


def test_a1c_mapping():
    mapping = config.get_default_record_mapping("HbA1c")
    assert _targets(mapping, "body_parts") == {
        "pancreas": "primary",
        "heart": "secondary",
        "kidneys": "secondary",
    }
    assert _targets(mapping, "body_systems") == {
        "endocrine_metabolic": "primary",
        "cardiovascular": "secondary",
        "renal_urinary": "secondary",
    }
    assert mapping.relevance_type == "risk_marker"
    assert mapping.confidence == "high"


def test_wbc_mapping_preserves_multisystem_uncertainty():
    mapping = config.get_default_record_mapping("WBC")
    assert _targets(mapping, "body_parts") == {"lymph_nodes": "primary"}
    assert _targets(mapping, "body_systems") == {
        "immune_lymphatic": "primary",
        "hematologic": "primary",
    }
    assert mapping.relevance_type == "systemic_marker"
    assert mapping.confidence == "medium"


def test_crp_mapping_preserves_multisystem_uncertainty():
    mapping = config.get_default_record_mapping("CRP")
    assert _targets(mapping, "body_parts") == {"general_body": "primary"}
    assert _targets(mapping, "body_systems") == {
        "general_preventive": "primary",
        "immune_lymphatic": "secondary",
    }
    assert mapping.relevance_type == "systemic_marker"
    assert mapping.confidence == "medium"


@pytest.mark.parametrize(
    "record_name",
    [
        "  LDL-CHOLESTEROL ",
        "hdl/cholesterol",
        "estimated-glomerular filtration rate",
        "hemoglobin-A1c",
        "Alanine Aminotransferase",
        "aspartate_aminotransferase",
        "white-blood-cell-count",
        "C reactive protein",
    ],
)
def test_lookup_resolves_supported_aliases_and_normalization(record_name):
    assert config.get_default_record_mapping(record_name) is not None


@pytest.mark.parametrize("record_name", ["", "   ", "troponin", "LD", "random glucose note", None])
def test_lookup_returns_none_for_unknown_names(record_name):
    assert config.get_default_record_mapping(record_name) is None


def test_bare_uppercase_egfr_remains_unmapped_as_ambiguous():
    assert config.get_default_record_mapping("EGFR") is None
    assert config.get_default_record_mapping("eGFR") is not None


def test_lookup_does_not_mutate_registry():
    mapping = config.get_default_record_mapping("LDL")
    before = config.get_default_record_mapping("LDL")
    with pytest.raises(FrozenInstanceError):
        mapping.confidence = "low"
    with pytest.raises(TypeError):
        config.DEFAULT_RECORD_MAPPINGS["ldl"] = mapping
    assert config.get_default_record_mapping("LDL") == before


def test_mapping_rejects_invalid_configuration():
    valid = config.get_default_record_mapping("LDL")
    invalid_mappings = (
        replace(valid, body_parts=()),
        replace(valid, body_parts=(config.MappingRelationship("unknown", "primary"),)),
        replace(valid, body_systems=(config.MappingRelationship("unknown", "primary"),)),
        replace(valid, relevance_type="unknown"),
        replace(valid, confidence="unknown"),
        replace(valid, body_parts=(config.MappingRelationship("heart", "tertiary"),)),
    )
    for mapping in invalid_mappings:
        with pytest.raises(ValueError):
            config.validate_record_mapping(mapping)


def test_mapping_registry_rejects_alias_collisions():
    mapping = config.get_default_record_mapping("LDL")
    definitions = (
        config.RecordMappingDefinition("first", ("same-name",), mapping),
        config.RecordMappingDefinition("second", ("same name",), mapping),
    )
    with pytest.raises(ValueError, match="collision"):
        config.build_record_mapping_registry(definitions)
