from __future__ import annotations

import re
from datetime import date
from math import isfinite

from models import (
    APPOINTMENT_STATUSES,
    CONDITION_SOURCES,
    LAB_FLAGS,
    MEDICATION_STATUSES,
    REMINDER_STATUSES,
)


def is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def require(value: object, label: str) -> list[str]:
    return [f"{label} is required."] if is_blank(value) else []


def valid_date(value: str | None, label: str, required: bool = False) -> list[str]:
    if is_blank(value):
        return [f"{label} is required."] if required else []
    try:
        date.fromisoformat(str(value))
    except ValueError:
        return [f"{label} must be a valid YYYY-MM-DD date."]
    return []


def valid_number(value: object, label: str, required: bool = False) -> list[str]:
    if is_blank(value):
        return [f"{label} is required."] if required else []
    # `float(True)` is 1.0, so a boolean sails through the conversion below and is recorded as the
    # reading 1.0 -- a measurement no source stated. Reachable from a FHIR `valueQuantity` and from
    # a JSON backup, both of which hand raw decoded values straight to this validator.
    if isinstance(value, bool):
        return [f"{label} must be numeric."]
    try:
        float(value)
    except (TypeError, ValueError):
        return [f"{label} must be numeric."]
    return []


def normalize_optional_number(value: object) -> float | None:
    if is_blank(value):
        return None
    # Also guarded here, not only in `valid_number`: `fhir._lab_from_observation` normalizes before
    # validation ever sees the raw value, so a boolean quantity would already be 1.0 by then.
    # Returning None keeps the record and its written result while refusing to invent a reading.
    if isinstance(value, bool):
        return None
    return float(value)


# An allowlist, not a blacklist. `float()` is far more permissive than it looks: it accepts fullwidth
# digits ("５.６" -> 5.6), underscore digit separators ("1_000.5" -> 1000.5) and "Infinity" -> inf, so
# a `try: float(...)` guarded by a few rejected characters silently lets all three through.
#
# `[0-9]` rather than `\d`: `\d` matches every Unicode decimal digit, so the fullwidth case survives
# the regex too and reaches `float`, which happily converts it.
_PLAIN_DECIMAL = re.compile(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)$")


def parse_plain_decimal(value: object) -> float | None:
    """A written result as a number, but only when the whole string is an unambiguous decimal.

    Used to fill `lab_results.numeric_value` from a `result_value` the person typed as a number.
    Returns None for anything that is not purely a finite decimal, which deliberately includes:

    - censored results such as ``"<0.01"`` or ``">1000"``. Storing 0.01 would assert a precision the
      lab explicitly refused to give, which is the kind of claim AGENTS.md section 5 forbids.
    - ranges (``"5.6-7.2"``), values carrying a unit (``"5.6 mg/dL"``), and separator-ambiguous input
      (``"5,6"`` is 5.6 in some locales and 56 in others).
    - ``"nan"``/``"inf"``, which `float` accepts and which would poison every downstream comparison.
    """

    # No `None` guard: `str(None)` is "None", which the pattern rejects like any other word.
    text = str(value).strip()
    if not _PLAIN_DECIMAL.match(text):
        return None
    # Not redundant after the regex: 400 digits match it and still overflow to `inf` in `float`.
    parsed = float(text)
    return parsed if isfinite(parsed) else None


def valid_severity(value: object) -> list[str]:
    if is_blank(value):
        return []
    try:
        severity = int(value)
    except (TypeError, ValueError):
        return ["Severity must be a whole number from 1 to 10."]
    if severity < 1 or severity > 10:
        return ["Severity must be between 1 and 10."]
    return []


def valid_choice(value: str | None, allowed: list[str], label: str, allow_blank: bool = False) -> list[str]:
    if is_blank(value):
        return [] if allow_blank else [f"{label} is required."]
    return [] if value in allowed else [f"{label} must be one of: {', '.join(allowed)}."]


def valid_date_order(start_date: str | None, end_date: str | None) -> list[str]:
    if is_blank(start_date) or is_blank(end_date):
        return []
    try:
        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))
    except ValueError:
        return []
    return ["End date cannot be before start date."] if end < start else []


def validate_person(data: dict) -> list[str]:
    errors = require(data.get("name"), "Name")
    errors += valid_date(data.get("date_of_birth"), "Date of birth")
    return errors


def validate_medication(data: dict) -> list[str]:
    errors = require(data.get("name"), "Medication name")
    errors += valid_date(data.get("start_date"), "Start date")
    errors += valid_date(data.get("end_date"), "End date")
    errors += valid_date_order(data.get("start_date"), data.get("end_date"))
    errors += valid_choice(data.get("status") or "Active", MEDICATION_STATUSES, "Medication status")
    return errors


def validate_allergy(data: dict) -> list[str]:
    return require(data.get("allergen"), "Allergen")


def validate_condition(data: dict) -> list[str]:
    errors = require(data.get("condition_name"), "Condition name")
    errors += valid_choice(data.get("source"), CONDITION_SOURCES, "Source", allow_blank=True)
    errors += valid_date(data.get("noted_date"), "Noted date")
    return errors


def validate_lab(data: dict) -> list[str]:
    errors = require(data.get("test_name"), "Test name")
    errors += valid_date(data.get("lab_date"), "Lab date", required=True)
    errors += valid_number(data.get("numeric_value"), "Numeric value") if not is_blank(data.get("numeric_value")) else []
    errors += valid_number(data.get("reference_low"), "Reference low") if not is_blank(data.get("reference_low")) else []
    errors += valid_number(data.get("reference_high"), "Reference high") if not is_blank(data.get("reference_high")) else []
    errors += valid_choice(data.get("flag") or "Unknown", LAB_FLAGS, "Lab flag")
    return errors


def validate_health_entry(data: dict) -> list[str]:
    errors = require(data.get("title"), "Title")
    errors += valid_date(data.get("entry_date"), "Entry date", required=True)
    errors += valid_severity(data.get("severity"))
    return errors


def validate_appointment(data: dict) -> list[str]:
    errors = require(data.get("title"), "Title")
    errors += valid_date(data.get("appointment_date"), "Appointment date", required=True)
    errors += valid_choice(data.get("status"), APPOINTMENT_STATUSES, "Appointment status", allow_blank=True)
    return errors


def validate_reminder(data: dict) -> list[str]:
    errors = require(data.get("reminder_type"), "Reminder type")
    errors += require(data.get("title"), "Title")
    errors += valid_date(data.get("due_date"), "Due date", required=True)
    errors += valid_choice(data.get("status") or "Upcoming", REMINDER_STATUSES, "Reminder status")
    return errors


def validate_wearable(data: dict) -> list[str]:
    errors = require(data.get("metric_type"), "Metric type")
    errors += valid_number(data.get("value"), "Value", required=True)
    errors += require(data.get("timestamp"), "Timestamp")
    return errors
