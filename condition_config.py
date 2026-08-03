"""This file is a CONTRACT.

Any demo/sample data must use record names that appear here, or condition→record
links silently miss.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType

CONDITION_RECORD_MAPPINGS: dict[str, dict[str, tuple[str, ...]]] = {
    "Diabetes": {
        "lab_results": ("Hemoglobin A1c",),
        "wearable_records": ("Glucose", "Weight"),
    },
    "Hypertension": {
        "medications": ("Lisinopril",),
        "wearable_records": ("Blood Pressure Systolic", "Blood Pressure Diastolic"),
    },
}


def normalize_condition_name(value: str) -> str:
    """Normalize case, whitespace, and ordinary punctuation without fuzzy matching."""

    if not isinstance(value, str):
        return ""
    return " ".join(re.sub(r"[\W_]+", " ", value.casefold()).split())


def build_condition_mapping_registry(
    mappings: Mapping[str, Mapping[str, tuple[str, ...]]],
) -> Mapping[str, Mapping[str, tuple[str, ...]]]:
    """Validate condition names and return an immutable normalized lookup index."""

    lookup: dict[str, Mapping[str, tuple[str, ...]]] = {}
    for condition_name, mapping in mappings.items():
        key = normalize_condition_name(condition_name)
        if not key:
            raise ValueError("Condition mapping names cannot be empty")
        if key in lookup:
            raise ValueError(f"Duplicate condition mapping name: {condition_name}")
        lookup[key] = mapping
    return MappingProxyType(lookup)


CONDITION_RECORD_MAPPING_LOOKUP = build_condition_mapping_registry(CONDITION_RECORD_MAPPINGS)


def get_condition_record_mapping(condition_name: str) -> Mapping[str, tuple[str, ...]]:
    """Return the exact normalized mapping entry, or an empty mapping when unknown."""

    return CONDITION_RECORD_MAPPING_LOOKUP.get(normalize_condition_name(condition_name), {})
