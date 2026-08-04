"""Deterministic condition→record-name mappings. This file is a CONTRACT.

Any demo/sample data must use record names that appear here, or condition→record links silently
miss. Matching is exact after case-folding and whitespace normalization -- no fuzzy or substring
matching -- so a renamed record simply stops appearing rather than failing loudly.

Every entry asserts only that a record *type* is commonly tracked alongside a condition. It never
asserts that a particular record was created for that condition, and never that the condition is
present, current, or confirmed. A medication may be listed only where it is actually indicated for
the condition; listing one prescribed for something else would assert a treatment relationship the
app has no basis for (AGENTS.md section 5). Omitting a record type is always safe; overclaiming is
not.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType

CONDITION_RECORD_MAPPINGS: dict[str, dict[str, tuple[str, ...]]] = {
    "Hypertension": {
        # Creatinine and potassium are standard renal/electrolyte monitoring on an ACE inhibitor.
        "lab_results": ("Creatinine", "Potassium"),
        "medications": ("Lisinopril",),
        "wearable_records": ("Blood Pressure Systolic", "Blood Pressure Diastolic", "Weight"),
    },
    "High Cholesterol": {
        "lab_results": ("LDL Cholesterol",),
        "medications": ("Atorvastatin",),
        "wearable_records": ("Weight", "Steps"),
    },
    "Vitamin D Deficiency": {
        "lab_results": ("Vitamin D",),
        "medications": ("Vitamin D3",),
    },
    "Prediabetes": {
        "lab_results": ("Hemoglobin A1c",),
        "wearable_records": ("Glucose", "Weight"),
    },
    "Diabetes": {
        # No medication entry on purpose: nothing in the controlled vocabulary treats diabetes, and
        # the nearest candidates treat blood pressure and cholesterol instead.
        "lab_results": ("Hemoglobin A1c",),
        "wearable_records": ("Glucose", "Weight"),
    },
    "Hypothyroidism": {
        "lab_results": ("TSH", "Free T4"),
        "medications": ("Levothyroxine",),
        "health_entries": ("Fatigue",),
    },
    "Gout": {
        # Allopurinol is urate-lowering therapy and colchicine treats a flare; both are indicated.
        "lab_results": ("Uric Acid",),
        "medications": ("Allopurinol", "Colchicine"),
        "health_entries": ("Gout flare",),
    },
    "Sleep Apnea": {
        # No medication entry on purpose: the standard treatment is CPAP, which is a device rather
        # than a medication, and nothing in the vocabulary treats the condition itself.
        "wearable_records": ("Sleep", "Oxygen Saturation", "Weight"),
        "health_entries": ("Daytime sleepiness",),
    },
    "Chronic Kidney Disease": {
        # No medication entry on purpose: an ARB is guideline-indicated only for *albuminuric* CKD,
        # which is a clinical judgement about a particular person that this type-level table cannot
        # make. Omitting a record type is always safe; overclaiming is not.
        "lab_results": ("Creatinine", "eGFR", "Potassium", "Urine Albumin-Creatinine Ratio"),
        "wearable_records": ("Blood Pressure Systolic", "Blood Pressure Diastolic", "Weight"),
        "health_entries": ("Ankle swelling",),
    },
    "Asthma": {
        # Blood eosinophils are a standard part of assessing asthma; they are a marker, not a
        # diagnosis, which is why the mapping claims only that the test is commonly tracked.
        "lab_results": ("Eosinophils",),
        "medications": ("Albuterol", "Fluticasone"),
        "wearable_records": ("Oxygen Saturation", "Peak Flow"),
        "health_entries": ("Asthma symptoms",),
    },
}

# The one series a condition is most readily followed by, as `(table, record_name)`. Used only to
# pick which line an at-a-glance sparkline draws -- it makes no claim that this measurement defines,
# diagnoses, or monitors the condition adequately.
#
# Kept here rather than in the chart module so condition->record knowledge lives in exactly one
# file. Every entry must also appear in that condition's own mapping above, which is asserted by
# `test_every_primary_metric_is_in_its_conditions_mapping` -- otherwise a sparkline could draw a
# series the condition's own record list never shows.
CONDITION_PRIMARY_METRIC: dict[str, tuple[str, str]] = {
    "Hypertension": ("wearable_records", "Blood Pressure Systolic"),
    "High Cholesterol": ("lab_results", "LDL Cholesterol"),
    "Vitamin D Deficiency": ("lab_results", "Vitamin D"),
    "Prediabetes": ("lab_results", "Hemoglobin A1c"),
    "Diabetes": ("lab_results", "Hemoglobin A1c"),
    "Hypothyroidism": ("lab_results", "TSH"),
    "Gout": ("lab_results", "Uric Acid"),
    "Sleep Apnea": ("wearable_records", "Sleep"),
    "Chronic Kidney Disease": ("lab_results", "eGFR"),
    "Asthma": ("wearable_records", "Peak Flow"),
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


CONDITION_PRIMARY_METRIC_LOOKUP = MappingProxyType(
    {normalize_condition_name(name): value for name, value in CONDITION_PRIMARY_METRIC.items()}
)


def get_condition_primary_metric(condition_name: str) -> tuple[str, str] | None:
    """Return ``(table, record_name)`` for a condition's headline series, or None when unmapped.

    Unmapped is an ordinary outcome, not an error: a condition with no entry simply has no
    sparkline drawn for it, which is the safe direction.
    """

    return CONDITION_PRIMARY_METRIC_LOOKUP.get(normalize_condition_name(condition_name))
