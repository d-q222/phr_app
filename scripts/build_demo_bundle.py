"""Build the Devon Marsh demo FHIR Bundle.

Run from the repository root::

    .venv/bin/python scripts/build_demo_bundle.py

Writes ``demo_data/devon_marsh_fhir_bundle.json``. The person is fictional; nothing here is real
patient data.

Why a generator rather than a hand-written file
-----------------------------------------------
The Bundle carries roughly 1,200 resources across 24 months. That is far past what anyone can keep
internally consistent by hand, and hand-editing is exactly how a lab's ``flag`` stops matching its
own value -- the defect class that required a whole remediation pass on the previous demo dataset.
Here the flag is *computed* from the value against that row's own reference range
(:func:`_flag_for`), so it cannot drift, and every record name is taken from
``condition_config.CONDITION_RECORD_MAPPINGS`` so the condition links cannot silently miss.

Determinism
-----------
Output is byte-identical on every run. Dates derive from the fixed :data:`ARC_START`; the only
variation comes from :data:`SEED` through an explicit ``random.Random`` instance, never the
module-level ``random`` functions, which share global state with whatever else is running.

What this deliberately does not do
----------------------------------
No value here is chosen to look abnormal, and no record asserts that a medication helped. Values
trend because a demo needs visible movement; the reference ranges are the source's own, and every
interpretation shown in the app comes from the stored flag rather than from anything computed at
render time.
"""

from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "demo_data" / "devon_marsh_fhir_bundle.json"

ARC_START = date(2024, 8, 1)
ARC_DAYS = 730
SEED = 20260803

PATIENT_ID = "devon-marsh"
PATIENT_REFERENCE = f"Patient/{PATIENT_ID}"
RELATIONSHIP_EXTENSION_URL = "urn:phr:fhir:StructureDefinition:profile-relationship"
PROFILE_NOTES_EXTENSION_URL = "urn:phr:fhir:StructureDefinition:profile-notes"

# Nine quarterly draws spanning the arc, the cadence a panel like this is actually repeated at.
LAB_DATES = [ARC_START + timedelta(days=4 + 91 * index) for index in range(9)]
# Free T4 is checked half as often as TSH, so it takes every other draw date.
ALTERNATE_LAB_DATES = LAB_DATES[::2]


def _flag_for(value: float, low: float | None, high: float | None) -> str:
    """Derive a lab flag from a value and that row's own reference range.

    This is the source's classification being recorded, not the app forming a clinical opinion:
    the range travels with the result, and bounds are inclusive so a value sitting exactly on a
    limit reads Normal.
    """

    if low is not None and value < low:
        return "Low"
    if high is not None and value > high:
        return "High"
    return "Normal"


# (test_name, unit, reference_low, reference_high, dates, values)
LAB_SERIES = [
    # Hypothyroidism: high on diagnosis, then flat for a year and a half. The chronic anchor -- the
    # point of the demo beat is that it never resolves and is simply monitored forever.
    ("TSH", "mIU/L", 0.4, 4.0, LAB_DATES, [8.4, 5.9, 3.1, 2.6, 2.4, 2.2, 2.5, 2.3, 2.4]),
    ("Free T4", "ng/dL", 0.8, 1.8, ALTERNATE_LAB_DATES, [0.7, 1.0, 1.2, 1.3, 1.2]),
    # Gout: the drop lands between the 2025-02-03 and 2025-05-05 draws, either side of the
    # allopurinol start date below. The chart shows the timing; it does not claim a cause.
    ("Uric Acid", "mg/dL", 3.5, 7.2, LAB_DATES, [9.2, 8.8, 7.4, 6.3, 5.4, 5.1, 4.9, 5.0, 4.8]),
    # Chronic kidney disease: the one arc that gets worse. A demo where everything improves is a
    # brochure; this is what the app looks like when it has to show a decline and not interpret it.
    ("Creatinine", "mg/dL", 0.7, 1.3, LAB_DATES, [1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9]),
    ("eGFR", "mL/min/1.73m2", 60.0, 120.0, LAB_DATES, [78, 74, 70, 66, 61, 57, 52, 47, 42]),
    ("Potassium", "mmol/L", 3.5, 5.1, LAB_DATES, [4.2, 4.3, 4.4, 4.5, 4.7, 4.8, 5.0, 5.2, 5.3]),
    ("Urine Albumin-Creatinine Ratio", "mg/g", None, 30.0, LAB_DATES, [22, 28, 41, 58, 76, 95, 118, 145, 180]),
    # Asthma: a marker used in assessing asthma, not a diagnosis of it.
    ("Eosinophils", "K/uL", 0.0, 0.5, LAB_DATES, [0.62, 0.58, 0.44, 0.39, 0.41, 0.36, 0.38, 0.34, 0.35]),
    # Unmapped on purpose: it fills the Labs page without being claimed for any condition.
    ("Hemoglobin", "g/dL", 13.5, 17.5, LAB_DATES, [14.8, 14.6, 14.4, 14.2, 14.0, 13.8, 13.6, 13.4, 13.2]),
]

# (metric_type, unit, readings, start_value, end_value, jitter, device)
WEARABLE_SERIES = [
    ("Sleep", "h", 209, 5.1, 7.2, 0.6, "Sleep tracker"),
    ("Oxygen Saturation", "%", 209, 91.0, 96.0, 1.2, "Pulse oximeter"),
    ("Weight", "lb", 209, 232.0, 198.0, 1.5, "Smart scale"),
    ("Blood Pressure Systolic", "mmHg", 209, 128.0, 134.0, 6.0, "Home BP cuff"),
    ("Blood Pressure Diastolic", "mmHg", 209, 80.0, 84.0, 4.0, "Home BP cuff"),
]
PEAK_FLOW_READINGS = 105

CONDITIONS = [
    (
        "Hypothyroidism",
        "Endocrinologist",
        "2024-09-15",
        "Followed with quarterly TSH. Levothyroxine dose adjusted once, in January 2025.",
    ),
    ("Gout", "Rheumatologist", "2024-11-02", "First flare recorded November 2024."),
    (
        "Sleep Apnea",
        "Pulmonologist",
        "2025-01-05",
        "Confirmed by sleep study. Followed with overnight tracking rather than labs.",
    ),
    (
        "Chronic Kidney Disease",
        "Nephrologist",
        "2025-04-14",
        "Followed with quarterly kidney function and urine albumin testing.",
    ),
    ("Asthma", "Pulmonologist", "2024-08-12", "Followed with weekly peak flow readings."),
]

# (name, dose, frequency, start, end, fhir_status, reason)
MEDICATIONS = [
    ("Levothyroxine", "50 mcg", "Once daily", "2024-09-15", "2025-01-20", "completed", "Hypothyroidism"),
    ("Levothyroxine", "88 mcg", "Once daily", "2025-01-20", None, "active", "Hypothyroidism"),
    ("Allopurinol", "300 mg", "Once daily", "2025-02-10", None, "active", "Gout"),
    ("Colchicine", "0.6 mg", "Twice daily", "2024-11-20", "2024-12-05", "completed", "Gout flare"),
    ("Albuterol", "90 mcg", "As needed", "2024-08-12", None, "active", "Asthma"),
    ("Fluticasone", "110 mcg", "Twice daily", "2024-09-05", None, "active", "Asthma"),
    ("Cetirizine", "10 mg", "Once daily", "2024-09-05", None, "active", "Seasonal allergies"),
]

# (title, body_system, body_part, date, severity, note)
#
# `body_part` must alias to a `body_map_config` canonical part or the Body Map cannot place the
# entry. There is no "foot" part, so a gout flare is stored against Bones -- the app's
# musculoskeletal organ -- and the location it actually happened in lives in the note. Same
# principle as dropping a FHIR clinicalStatus: represent what the schema can hold, and put what it
# cannot into free text rather than forcing it into a field that means something else.
HEALTH_ENTRIES = [
    ("Fatigue", "Endocrine", "Thyroid", "2024-08-20", 6, "Tired through the afternoons."),
    ("Fatigue", "Endocrine", "Thyroid", "2024-10-12", 5, "Still tired, less than August."),
    ("Fatigue", "Endocrine", "Thyroid", "2024-12-05", 3, "Noticeably better."),
    ("Gout flare", "Musculoskeletal", "Bones", "2024-11-02", 8, "Left foot, first metatarsal joint."),
    ("Gout flare", "Musculoskeletal", "Bones", "2025-01-18", 7, "Right foot."),
    ("Gout flare", "Musculoskeletal", "Bones", "2025-04-22", 5, "Left foot, milder and shorter."),
    ("Gout flare", "Musculoskeletal", "Bones", "2025-09-14", 3, "Left foot, resolved in two days."),
    ("Daytime sleepiness", "General", "General / Whole Body", "2025-01-05", 6, "Fell asleep reading."),
    ("Daytime sleepiness", "General", "General / Whole Body", "2025-03-20", 5, "Afternoons hardest."),
    ("Daytime sleepiness", "General", "General / Whole Body", "2025-07-11", 3, "Less frequent."),
    ("Asthma symptoms", "Respiratory", "Lungs", "2024-09-18", 5, "Wheeze after mowing."),
    ("Asthma symptoms", "Respiratory", "Lungs", "2024-12-02", 4, "Cough in cold air."),
    ("Asthma symptoms", "Respiratory", "Lungs", "2025-03-14", 7, "Heavy pollen week."),
    ("Asthma symptoms", "Respiratory", "Lungs", "2025-05-08", 6, "Tight chest on waking."),
    ("Asthma symptoms", "Respiratory", "Lungs", "2025-09-22", 5, "Wheeze after yard work."),
    ("Asthma symptoms", "Respiratory", "Lungs", "2025-12-09", 4, "Cough in cold air."),
    ("Asthma symptoms", "Respiratory", "Lungs", "2026-03-17", 6, "Pollen again."),
    ("Asthma symptoms", "Respiratory", "Lungs", "2026-05-12", 5, "Settled with the inhaler."),
    ("Ankle swelling", "Renal/Urinary", "Kidneys", "2025-05-19", 3, "Both ankles by evening."),
    ("Ankle swelling", "Renal/Urinary", "Kidneys", "2025-11-24", 4, "Noticeable after a long day."),
    ("Ankle swelling", "Renal/Urinary", "Kidneys", "2026-06-08", 5, "Socks leaving marks."),
]

# (allergen, reaction, fhir_severity)
ALLERGIES = [
    ("Penicillin", "Hives and facial swelling", "severe"),
    ("Peanuts", "Lip swelling", "moderate"),
    ("Grass pollen", "Sneezing and itchy eyes", "mild"),
]

# (date, description, provider, location, fhir_status)
APPOINTMENTS = [
    ("2024-08-12", "Annual physical", "Primary Care", "Riverbend Family Practice", "fulfilled"),
    ("2024-09-15", "Thyroid follow-up", "Endocrinologist", "Riverbend Endocrinology", "fulfilled"),
    ("2024-11-08", "Gout assessment", "Rheumatologist", "Riverbend Rheumatology", "fulfilled"),
    ("2025-01-05", "Sleep study review", "Pulmonologist", "Riverbend Sleep Center", "fulfilled"),
    ("2025-01-20", "Thyroid dose review", "Endocrinologist", "Riverbend Endocrinology", "fulfilled"),
    ("2025-02-10", "Gout follow-up", "Rheumatologist", "Riverbend Rheumatology", "fulfilled"),
    ("2025-04-14", "Kidney function review", "Nephrologist", "Riverbend Nephrology", "fulfilled"),
    ("2025-06-02", "Nutrition consult", "Registered Dietitian", "Riverbend Nutrition", "noshow"),
    ("2025-08-11", "Annual physical", "Primary Care", "Riverbend Family Practice", "fulfilled"),
    ("2025-10-06", "Kidney function review", "Nephrologist", "Riverbend Nephrology", "fulfilled"),
    ("2026-01-12", "Asthma review", "Pulmonologist", "Riverbend Pulmonology", "fulfilled"),
    ("2026-03-09", "Kidney function review", "Nephrologist", "Riverbend Nephrology", "fulfilled"),
    ("2026-05-18", "Nutrition consult", "Registered Dietitian", "Riverbend Nutrition", "cancelled"),
    ("2026-07-20", "Thyroid follow-up", "Endocrinologist", "Riverbend Endocrinology", "pending"),
    ("2026-10-05", "Annual physical", "Primary Care", "Riverbend Family Practice", "booked"),
    ("2027-01-11", "Kidney function review", "Nephrologist", "Riverbend Nephrology", "booked"),
]

# (reminder_type, title, due_date, fhir_status)
#
# The app derives "Overdue" from a past due date plus a status that is not Completed or Dismissed,
# so a past-dated `requested` Task is what makes the dashboard's overdue tile non-zero. FHIR has no
# status that maps to Overdue directly.
REMINDERS = [
    ("Lab", "Quarterly kidney panel", "2026-07-25", "requested"),
    ("Medication", "Refill allopurinol", "2026-07-30", "requested"),
    ("Appointment", "Book asthma review", "2026-11-14", "requested"),
    ("Lab", "Next TSH draw", "2026-11-02", "requested"),
    ("Appointment", "Annual physical", "2026-10-05", "requested"),
    ("Lab", "Quarterly kidney panel", "2026-03-09", "completed"),
    ("Medication", "Refill levothyroxine", "2026-05-01", "completed"),
    ("Lab", "Next TSH draw", "2026-05-04", "completed"),
    ("Appointment", "Nutrition consult", "2026-05-18", "cancelled"),
    ("Medication", "Refill inhaler", "2027-01-20", "requested"),
]

PROFILE_NOTES = (
    "Records span August 2024 to August 2026. Five conditions are tracked: hypothyroidism, gout, "
    "sleep apnea, chronic kidney disease, and asthma. Quarterly lab panels, weekly to twice-weekly "
    "wearable readings, and specialist follow-ups across endocrinology, rheumatology, nephrology, "
    "and pulmonology."
)


def _codeable(text: str) -> dict:
    return {"text": text}


def _entry(resource: dict) -> dict:
    return {"fullUrl": f"urn:uuid:{resource['id']}", "resource": resource}


def _iso(day: date) -> str:
    return day.isoformat()


def _patient_resource() -> dict:
    return {
        "resourceType": "Patient",
        "id": PATIENT_ID,
        "name": [{"text": "Devon Marsh"}],
        "gender": "male",
        "birthDate": "1970-08-02",
        "contact": [{"name": {"text": "Renata Marsh (sister)"}}],
        "extension": [
            {"url": RELATIONSHIP_EXTENSION_URL, "valueString": "Self"},
            {"url": PROFILE_NOTES_EXTENSION_URL, "valueString": PROFILE_NOTES},
        ],
    }


def _condition_resources() -> list[dict]:
    resources = []
    for index, (name, source, noted, note) in enumerate(CONDITIONS):
        resources.append(
            {
                "resourceType": "Condition",
                "id": f"condition-{index}",
                "subject": {"reference": PATIENT_REFERENCE},
                "code": _codeable(name),
                "recordedDate": noted,
                # Matches models.CONDITION_SOURCES exactly. Anything else imports blank rather than
                # inventing a provider category, which is the behaviour the importer is built for.
                "recorder": {"display": source},
                "note": [{"text": note}],
            }
        )
    return resources


def _lab_resources() -> list[dict]:
    resources = []
    index = 0
    for test_name, unit, low, high, dates, values in LAB_SERIES:
        for day, value in zip(dates, values, strict=True):
            reference_range = {}
            if low is not None:
                reference_range["low"] = {"value": low, "unit": unit}
            if high is not None:
                reference_range["high"] = {"value": high, "unit": unit}
            resources.append(
                {
                    "resourceType": "Observation",
                    "id": f"lab-{index}",
                    "status": "final",
                    "category": [_codeable("Laboratory")],
                    "subject": {"reference": PATIENT_REFERENCE},
                    "code": _codeable(test_name),
                    "effectiveDateTime": _iso(day),
                    "valueQuantity": {"value": value, "unit": unit},
                    "referenceRange": [reference_range] if reference_range else [],
                    "interpretation": [_codeable(_flag_for(value, low, high))],
                }
            )
            index += 1
    return resources


def _wearable_resource(index: int, metric: str, unit: str, day: date, value: float, device: str) -> dict:
    return {
        "resourceType": "Observation",
        "id": f"wear-{index}",
        "status": "final",
        # Routed by this category text. The resource id must also avoid the substrings "lab" and
        # "wearable", which fhir._observation_from_resource falls back to when a category is absent.
        "category": [_codeable("Wearable")],
        "subject": {"reference": PATIENT_REFERENCE},
        "code": _codeable(metric),
        "effectiveDateTime": _iso(day),
        "valueQuantity": {"value": value, "unit": unit},
        "device": {"display": device},
    }


def _reading_date(index: int, count: int) -> date:
    return ARC_START + timedelta(days=round(index * ARC_DAYS / (count - 1)))


def _wearable_resources(rng: random.Random) -> list[dict]:
    resources = []
    index = 0
    for metric, unit, count, start_value, end_value, jitter, device in WEARABLE_SERIES:
        for step in range(count):
            day = _reading_date(step, count)
            drift = start_value + (end_value - start_value) * step / (count - 1)
            value = round(drift + rng.uniform(-jitter, jitter), 1)
            resources.append(_wearable_resource(index, metric, unit, day, value, device))
            index += 1
    for step in range(PEAK_FLOW_READINGS):
        day = _reading_date(step, PEAK_FLOW_READINGS)
        # Two seasonal dips a year -- a deep one in late spring and a shallower one in winter --
        # so the variability chart has something a single trend line would flatten away.
        angle = 2 * math.pi * (day.timetuple().tm_yday - 115) / 365.25
        seasonal = -45 * math.cos(angle) - 18 * math.cos(2 * angle)
        value = round(455 + seasonal + rng.uniform(-12, 12), 1)
        resources.append(_wearable_resource(index, "Peak Flow", "L/min", day, value, "Peak flow meter"))
        index += 1
    return resources


def _health_entry_resources() -> list[dict]:
    resources = []
    for index, (title, system, part, day, severity, note) in enumerate(HEALTH_ENTRIES):
        resources.append(
            {
                "resourceType": "Observation",
                # Neither "lab" nor "wearable" appears in this id, and no body-system name contains
                # them either, so these route to health_entries by falling through both checks.
                "id": f"entry-{index}",
                "status": "final",
                "category": [_codeable(system)],
                "subject": {"reference": PATIENT_REFERENCE},
                "code": _codeable(title),
                "effectiveDateTime": day,
                "bodySite": _codeable(part),
                "component": [{"code": _codeable("Severity"), "valueInteger": severity}],
                "valueString": note,
            }
        )
    return resources


def _medication_resources() -> list[dict]:
    resources = []
    for index, (name, dose, frequency, start, end, status, reason) in enumerate(MEDICATIONS):
        period = {"start": start}
        if end:
            period["end"] = end
        resources.append(
            {
                "resourceType": "MedicationStatement",
                "id": f"med-{index}",
                "status": status,
                "subject": {"reference": PATIENT_REFERENCE},
                "medicationCodeableConcept": _codeable(name),
                "effectivePeriod": period,
                "reasonCode": [_codeable(reason)],
                "extension": [
                    {"url": "urn:phr:fhir:StructureDefinition:medication-dose", "valueString": dose},
                    {"url": "urn:phr:fhir:StructureDefinition:medication-frequency", "valueString": frequency},
                ],
            }
        )
    return resources


def _allergy_resources() -> list[dict]:
    resources = []
    for index, (allergen, reaction, severity) in enumerate(ALLERGIES):
        resources.append(
            {
                "resourceType": "AllergyIntolerance",
                "id": f"allergy-{index}",
                "patient": {"reference": PATIENT_REFERENCE},
                "code": _codeable(allergen),
                "reaction": [
                    {
                        "description": reaction,
                        "severity": severity,
                        "manifestation": [_codeable(reaction)],
                    }
                ],
            }
        )
    return resources


def _appointment_resources() -> list[dict]:
    resources = []
    for index, (day, description, provider, location, status) in enumerate(APPOINTMENTS):
        resources.append(
            {
                "resourceType": "Appointment",
                "id": f"appt-{index}",
                "status": status,
                "description": description,
                "requestedPeriod": [{"start": f"{day}T09:00:00"}],
                "supportingInformation": [{"display": location}],
                "participant": [
                    {"actor": {"reference": PATIENT_REFERENCE}},
                    {"actor": {"display": provider}},
                ],
            }
        )
    return resources


def _task_resources() -> list[dict]:
    resources = []
    for index, (reminder_type, title, due, status) in enumerate(REMINDERS):
        resources.append(
            {
                "resourceType": "Task",
                "id": f"task-{index}",
                "status": status,
                "intent": "plan",
                "description": title,
                "for": {"reference": PATIENT_REFERENCE},
                "code": _codeable(reminder_type),
                "executionPeriod": {"end": due},
            }
        )
    return resources


def build_bundle() -> tuple[dict, dict[str, int]]:
    """Return the Bundle and the per-table row counts a clean import should produce.

    The counts are the contract the routing test asserts against. An Observation that lands in the
    wrong table still imports cleanly and leaves ``skipped`` empty, so counts are the only thing
    that catches a misroute.
    """

    rng = random.Random(SEED)
    labs = _lab_resources()
    wearables = _wearable_resources(rng)
    entries = _health_entry_resources()
    medications = _medication_resources()
    allergies = _allergy_resources()
    appointments = _appointment_resources()
    tasks = _task_resources()
    conditions = _condition_resources()

    resources = [_patient_resource(), *conditions, *labs, *wearables, *entries, *medications, *allergies, *appointments, *tasks]
    bundle = {
        "resourceType": "Bundle",
        "id": "devon-marsh-demo",
        "type": "collection",
        "entry": [_entry(resource) for resource in resources],
    }
    counts = {
        "people": 1,
        "conditions": len(conditions),
        "lab_results": len(labs),
        "wearable_records": len(wearables),
        "health_entries": len(entries),
        "medications": len(medications),
        "allergies": len(allergies),
        "appointments": len(appointments),
        "reminders": len(tasks),
    }
    return bundle, counts


def main() -> None:
    bundle, counts = build_bundle()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    total = sum(counts.values())
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} -- {total} records across {len(counts)} tables")
    for table, count in counts.items():
        print(f"  {table:<20} {count}")


if __name__ == "__main__":
    main()
