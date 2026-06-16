from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import db
import services
from validation import (
    validate_allergy,
    validate_appointment,
    validate_health_entry,
    validate_lab,
    validate_medication,
    validate_reminder,
    validate_wearable,
    normalize_optional_number,
)


SUPPORTED_FHIR_VERSIONS = ["R4", "R5"]
FHIR_MIME_TYPE = "application/fhir+json"
DOSE_EXTENSION_URL = "urn:phr:fhir:StructureDefinition:medication-dose"
FREQUENCY_EXTENSION_URL = "urn:phr:fhir:StructureDefinition:medication-frequency"


FHIR_VALIDATORS = {
    "allergies": validate_allergy,
    "medications": validate_medication,
    "lab_results": validate_lab,
    "health_entries": validate_health_entry,
    "appointments": validate_appointment,
    "reminders": validate_reminder,
    "wearable_records": validate_wearable,
}


def normalize_fhir_version(version: str) -> str:
    normalized = version.upper()
    if normalized not in SUPPORTED_FHIR_VERSIONS:
        raise ValueError(f"FHIR version must be one of: {', '.join(SUPPORTED_FHIR_VERSIONS)}.")
    return normalized


def export_bundle(version: str = "R4", person_id: int | None = None, db_path: Path | str = db.DB_PATH) -> str:
    version = normalize_fhir_version(version)
    people = services.list_people(db_path=db_path)
    if person_id is not None:
        people = [person for person in people if int(person["id"]) == person_id]

    entries = []
    for person in people:
        entries.append(_entry(_patient_resource(person)))
        current_person_id = int(person["id"])
        for allergy in services.list_items("allergies", current_person_id, order_by="id", descending=False, db_path=db_path):
            entries.append(_entry(_allergy_resource(allergy, version)))
        for medication in services.list_items("medications", current_person_id, order_by="id", descending=False, db_path=db_path):
            entries.append(_entry(_medication_statement_resource(medication, version)))
        for lab in services.list_items("lab_results", current_person_id, order_by="id", descending=False, db_path=db_path):
            entries.append(_entry(_lab_observation_resource(lab)))
        for item in services.list_items("health_entries", current_person_id, order_by="id", descending=False, db_path=db_path):
            entries.append(_entry(_health_entry_observation_resource(item)))
        for appointment in services.list_items("appointments", current_person_id, order_by="id", descending=False, db_path=db_path):
            entries.append(_entry(_appointment_resource(appointment, version)))
        for reminder in services.list_items("reminders", current_person_id, order_by="id", descending=False, db_path=db_path):
            entries.append(_entry(_task_resource(reminder)))
        for wearable in services.list_items("wearable_records", current_person_id, order_by="id", descending=False, db_path=db_path):
            entries.append(_entry(_wearable_observation_resource(wearable)))

    bundle = {
        "resourceType": "Bundle",
        "id": "phr-export",
        "type": "collection",
        "timestamp": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "meta": {"tag": [_coding("urn:phr:fhir-version", version, f"FHIR {version}")]},
        "entry": entries,
    }
    return json.dumps(bundle, indent=2)


def import_bundle(payload_text: str, clear_existing: bool = False, db_path: Path | str = db.DB_PATH) -> dict:
    payload = json.loads(payload_text)
    resources = _resources_from_payload(payload)
    if clear_existing:
        db.import_all_tables({table: [] for table in db.TABLES}, clear_existing=True, db_path=db_path)

    imported = {table: 0 for table in db.TABLES}
    skipped = []
    patient_map: dict[str, int] = {}

    for resource in resources:
        if resource.get("resourceType") != "Patient":
            continue
        person_id = services.create_person(_person_from_patient(resource), db_path=db_path)
        imported["people"] += 1
        for key in _reference_keys(resource):
            patient_map[key] = person_id

    imported_patient_ids = list(dict.fromkeys(patient_map.values()))
    fallback_person_id = imported_patient_ids[0] if len(imported_patient_ids) == 1 else None
    for resource in resources:
        resource_type = resource.get("resourceType")
        if resource_type == "Patient":
            continue
        person_id = _resolve_patient_id(resource, patient_map, fallback_person_id)
        if person_id is None:
            skipped.append({"resourceType": resource_type or "Unknown", "id": resource.get("id"), "reason": "No matching Patient resource."})
            continue
        table, data = _local_record_from_resource(resource)
        if not table:
            skipped.append({"resourceType": resource_type or "Unknown", "id": resource.get("id"), "reason": "Unsupported FHIR resource."})
            continue
        errors = FHIR_VALIDATORS[table](data)
        if errors:
            skipped.append({"resourceType": resource_type or "Unknown", "id": resource.get("id"), "reason": "; ".join(errors)})
            continue
        services.create_item(table, person_id, data, db_path=db_path)
        imported[table] += 1

    return {"imported": imported, "skipped": skipped}


def _entry(resource: dict) -> dict:
    return {"fullUrl": f"urn:uuid:{resource['resourceType'].lower()}-{resource['id']}", "resource": resource}


def _id(prefix: str, row: dict) -> str:
    return f"{prefix}-{row['id']}"


def _patient_ref(person_id: int) -> dict:
    return {"reference": f"Patient/person-{person_id}"}


def _coding(system: str, code: str, display: str | None = None) -> dict:
    coding = {"system": system, "code": code}
    if display:
        coding["display"] = display
    return coding


def _codeable_text(text: str | None, coding: dict | None = None) -> dict:
    concept: dict = {}
    if coding:
        concept["coding"] = [coding]
    if text:
        concept["text"] = str(text)
    return concept


def _note(text: str | None) -> list[dict]:
    return [{"text": str(text)}] if text else []


def _patient_resource(person: dict) -> dict:
    resource = {
        "resourceType": "Patient",
        "id": _id("person", person),
        "identifier": [{"system": "urn:phr:ids:person", "value": str(person["id"])}],
        "name": [{"text": person["name"]}],
    }
    gender = _gender_to_fhir(person.get("sex"))
    if gender:
        resource["gender"] = gender
    if person.get("date_of_birth"):
        resource["birthDate"] = person["date_of_birth"]
    if person.get("emergency_contact"):
        resource["contact"] = [{"name": {"text": person["emergency_contact"]}}]
    if person.get("relationship"):
        resource["extension"] = [
            {
                "url": "urn:phr:fhir:StructureDefinition:profile-relationship",
                "valueString": person["relationship"],
            }
        ]
    return resource


def _allergy_resource(allergy: dict, version: str) -> dict:
    reaction = {
        "description": allergy.get("reaction") or "",
        "severity": _severity_to_fhir(allergy.get("severity")),
    }
    if allergy.get("reaction"):
        if version == "R5":
            reaction["manifestation"] = [{"concept": _codeable_text(allergy["reaction"])}]
        else:
            reaction["manifestation"] = [_codeable_text(allergy["reaction"])]
    resource = {
        "resourceType": "AllergyIntolerance",
        "id": _id("allergy", allergy),
        "clinicalStatus": _codeable_text("Active", _coding("http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "active", "Active")),
        "code": _codeable_text(allergy.get("allergen")),
        "patient": _patient_ref(int(allergy["person_id"])),
        "reaction": [reaction],
        "note": _note(allergy.get("notes")),
    }
    return _strip_empty(resource)


def _medication_statement_resource(medication: dict, version: str) -> dict:
    extensions = []
    if medication.get("dose"):
        extensions.append({"url": DOSE_EXTENSION_URL, "valueString": str(medication["dose"])})
    if medication.get("frequency"):
        extensions.append({"url": FREQUENCY_EXTENSION_URL, "valueString": str(medication["frequency"])})
    resource = {
        "resourceType": "MedicationStatement",
        "id": _id("medication", medication),
        "status": _medication_status_to_fhir(medication.get("status"), version),
        "subject": _patient_ref(int(medication["person_id"])),
        "effectivePeriod": _period(medication.get("start_date"), medication.get("end_date")),
        "dosage": [{"text": " ".join(part for part in [medication.get("dose"), medication.get("frequency")] if part)}],
        "note": _note(medication.get("notes")),
        "extension": extensions,
    }
    if version == "R5":
        resource["medication"] = {"concept": _codeable_text(medication.get("name"))}
        if medication.get("reason"):
            resource["reason"] = [{"concept": _codeable_text(medication["reason"])}]
    else:
        resource["medicationCodeableConcept"] = _codeable_text(medication.get("name"))
        if medication.get("reason"):
            resource["reasonCode"] = [_codeable_text(medication["reason"])]
    return _strip_empty(resource)


def _lab_observation_resource(lab: dict) -> dict:
    resource = {
        "resourceType": "Observation",
        "id": _id("lab", lab),
        "status": "final",
        "category": [_codeable_text("Laboratory", _coding("http://terminology.hl7.org/CodeSystem/observation-category", "laboratory", "Laboratory"))],
        "code": _codeable_text(lab.get("test_name")),
        "subject": _patient_ref(int(lab["person_id"])),
        "effectiveDateTime": lab.get("lab_date"),
        "interpretation": [_codeable_text(lab["flag"])] if lab.get("flag") else [],
        "referenceRange": [_reference_range(lab.get("reference_low"), lab.get("reference_high"), lab.get("unit"))],
        "note": _note(lab.get("notes")),
    }
    if lab.get("numeric_value") is not None:
        resource["valueQuantity"] = _quantity(lab["numeric_value"], lab.get("unit"))
    elif lab.get("result_value"):
        resource["valueString"] = str(lab["result_value"])
    return _strip_empty(resource)


def _health_entry_observation_resource(item: dict) -> dict:
    resource = {
        "resourceType": "Observation",
        "id": _id("health-entry", item),
        "status": "final",
        "category": [_codeable_text("Survey", _coding("http://terminology.hl7.org/CodeSystem/observation-category", "survey", "Survey"))],
        "code": _codeable_text(item.get("title")),
        "subject": _patient_ref(int(item["person_id"])),
        "effectiveDateTime": item.get("entry_date"),
        "bodySite": _codeable_text(item.get("body_part")),
        "valueString": item.get("note"),
        "component": [{"code": _codeable_text("Severity 1-10"), "valueInteger": int(item["severity"])}] if item.get("severity") is not None else [],
    }
    if item.get("body_system"):
        resource["category"].append(_codeable_text(item["body_system"]))
    return _strip_empty(resource)


def _wearable_observation_resource(wearable: dict) -> dict:
    return _strip_empty(
        {
            "resourceType": "Observation",
            "id": _id("wearable", wearable),
            "status": "final",
            "category": [_codeable_text("Wearable")],
            "code": _codeable_text(wearable.get("metric_type")),
            "subject": _patient_ref(int(wearable["person_id"])),
            "effectiveDateTime": wearable.get("timestamp"),
            "valueQuantity": _quantity(wearable.get("value"), wearable.get("unit")),
            "device": {"display": wearable.get("source")} if wearable.get("source") else None,
        }
    )


def _appointment_resource(appointment: dict, version: str) -> dict:
    resource = {
        "resourceType": "Appointment",
        "id": _id("appointment", appointment),
        "status": _appointment_status_to_fhir(appointment.get("status")),
        "description": appointment.get("title"),
        "requestedPeriod": [{"start": appointment.get("appointment_date")}],
        "participant": [{"actor": _patient_ref(int(appointment["person_id"])), "status": "accepted"}],
    }
    if appointment.get("notes"):
        if version == "R5":
            resource["note"] = _note(appointment["notes"])
        else:
            resource["comment"] = appointment["notes"]
    if appointment.get("provider"):
        resource["participant"].append({"actor": {"display": appointment["provider"]}, "status": "accepted"})
    if appointment.get("location"):
        resource["supportingInformation"] = [{"display": appointment["location"]}]
    return _strip_empty(resource)


def _task_resource(reminder: dict) -> dict:
    return _strip_empty(
        {
            "resourceType": "Task",
            "id": _id("reminder", reminder),
            "status": _task_status_to_fhir(reminder.get("status")),
            "intent": "plan",
            "code": _codeable_text(reminder.get("reminder_type")),
            "description": reminder.get("title"),
            "for": _patient_ref(int(reminder["person_id"])),
            "executionPeriod": {"end": reminder.get("due_date")},
            "note": _note(reminder.get("notes")),
        }
    )


def _quantity(value, unit: str | None) -> dict:
    quantity = {"value": float(value)}
    if unit:
        quantity["unit"] = unit
    return quantity


def _reference_range(low, high, unit: str | None) -> dict:
    result = {}
    if low is not None:
        result["low"] = _quantity(low, unit)
    if high is not None:
        result["high"] = _quantity(high, unit)
    return result


def _period(start: str | None, end: str | None) -> dict:
    period = {}
    if start:
        period["start"] = start
    if end:
        period["end"] = end
    return period


def _gender_to_fhir(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"male", "female", "other", "unknown"}:
        return normalized
    return "unknown"


def _gender_from_fhir(value: str | None) -> str | None:
    if not value:
        return None
    return {"male": "Male", "female": "Female", "other": "Other", "unknown": "Unknown"}.get(value.lower(), value)


def _severity_to_fhir(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"mild", "moderate", "severe"}:
        return normalized
    return None


def _medication_status_to_fhir(value: str | None, version: str) -> str:
    normalized = (value or "Active").strip().lower()
    if version == "R5":
        return "recorded"
    return {
        "active": "active",
        "paused": "on-hold",
        "completed": "completed",
        "stopped": "stopped",
        "unknown": "unknown",
    }.get(normalized, "unknown")


def _medication_status_from_fhir(value: str | None, effective_period: dict | None = None) -> str:
    normalized = (value or "unknown").lower()
    mapped = {
        "active": "Active",
        "on-hold": "Paused",
        "completed": "Completed",
        "stopped": "Stopped",
        "unknown": "Unknown",
        "not-taken": "Stopped",
        "recorded": "Active",
        "draft": "Unknown",
    }.get(normalized, "Unknown")
    if normalized == "recorded" and effective_period and effective_period.get("end"):
        return "Completed"
    return mapped


def _appointment_status_to_fhir(value: str | None) -> str:
    normalized = (value or "Scheduled").strip().lower()
    return {
        "scheduled": "booked",
        "completed": "fulfilled",
        "canceled": "cancelled",
        "missed": "noshow",
        "needs follow-up": "pending",
        "needs-follow-up": "pending",
    }.get(normalized, "booked")


def _appointment_status_from_fhir(value: str | None) -> str:
    return {
        "booked": "Scheduled",
        "fulfilled": "Completed",
        "cancelled": "Canceled",
        "noshow": "Missed",
        "pending": "Needs Follow-Up",
    }.get((value or "").lower(), "Scheduled")


def _task_status_to_fhir(value: str | None) -> str:
    normalized = (value or "Upcoming").strip().lower()
    return {
        "upcoming": "requested",
        "overdue": "requested",
        "completed": "completed",
        "dismissed": "cancelled",
    }.get(normalized, "requested")


def _task_status_from_fhir(value: str | None) -> str:
    return {
        "requested": "Upcoming",
        "accepted": "Upcoming",
        "ready": "Upcoming",
        "in-progress": "Upcoming",
        "completed": "Completed",
        "cancelled": "Dismissed",
        "entered-in-error": "Dismissed",
    }.get((value or "").lower(), "Upcoming")


def _resources_from_payload(payload: dict) -> list[dict]:
    if payload.get("resourceType") == "Bundle":
        resources = []
        for entry in payload.get("entry", []):
            if not entry.get("resource"):
                continue
            resource = dict(entry["resource"])
            if entry.get("fullUrl"):
                resource["_fullUrl"] = entry["fullUrl"]
            resources.append(resource)
        return resources
    if payload.get("resourceType"):
        return [payload]
    raise ValueError("FHIR import must be a Bundle or a single FHIR resource.")


def _reference_keys(resource: dict) -> set[str]:
    resource_type = resource.get("resourceType")
    resource_id = resource.get("id")
    keys = set()
    if resource.get("_fullUrl"):
        keys.add(resource["_fullUrl"])
    if resource_id:
        keys.add(resource_id)
        keys.add(f"{resource_type}/{resource_id}")
    for identifier in resource.get("identifier", []):
        if identifier.get("value"):
            keys.add(str(identifier["value"]))
    return keys


def _resolve_patient_id(resource: dict, patient_map: dict[str, int], fallback_person_id: int | None) -> int | None:
    reference = _patient_reference_value(resource)
    if reference and reference in patient_map:
        return patient_map[reference]
    if reference and reference.split("/")[-1] in patient_map:
        return patient_map[reference.split("/")[-1]]
    if reference:
        return None
    return fallback_person_id


def _patient_reference_value(resource: dict) -> str | None:
    if resource.get("patient", {}).get("reference"):
        return resource["patient"]["reference"]
    if resource.get("subject", {}).get("reference"):
        return resource["subject"]["reference"]
    if resource.get("for", {}).get("reference"):
        return resource["for"]["reference"]
    for participant in resource.get("participant", []):
        reference = participant.get("actor", {}).get("reference")
        if reference:
            return reference
    return None


def _person_from_patient(resource: dict) -> dict:
    name = None
    if resource.get("name"):
        first_name = resource["name"][0]
        name = first_name.get("text") or " ".join(first_name.get("given", []) + ([first_name.get("family")] if first_name.get("family") else []))
    contact = resource.get("contact", [{}])[0].get("name", {}).get("text") if resource.get("contact") else None
    relationship = None
    for extension in resource.get("extension", []):
        if extension.get("url", "").endswith("profile-relationship"):
            relationship = extension.get("valueString")
    return {
        "name": name or f"FHIR Patient {resource.get('id') or ''}".strip(),
        "date_of_birth": resource.get("birthDate"),
        "sex": _gender_from_fhir(resource.get("gender")),
        "relationship": relationship,
        "emergency_contact": contact,
        "notes": "Imported from FHIR.",
    }


def _local_record_from_resource(resource: dict) -> tuple[str | None, dict]:
    resource_type = resource.get("resourceType")
    if resource_type == "AllergyIntolerance":
        return "allergies", _allergy_from_resource(resource)
    if resource_type == "MedicationStatement":
        return "medications", _medication_from_resource(resource)
    if resource_type == "Observation":
        return _observation_from_resource(resource)
    if resource_type == "Appointment":
        return "appointments", _appointment_from_resource(resource)
    if resource_type == "Task":
        return "reminders", _task_from_resource(resource)
    return None, {}


def _allergy_from_resource(resource: dict) -> dict:
    reaction = resource.get("reaction", [{}])[0] if resource.get("reaction") else {}
    manifestation = reaction.get("manifestation", [{}])[0] if reaction.get("manifestation") else {}
    reaction_text = reaction.get("description") or _text_from_codeable_reference(manifestation)
    return {
        "allergen": _text_from_codeable(resource.get("code")) or "Unknown allergen",
        "reaction": reaction_text,
        "severity": (reaction.get("severity") or "").title() or None,
        "notes": _notes_text(resource.get("note")),
    }


def _medication_from_resource(resource: dict) -> dict:
    effective = resource.get("effectivePeriod") or {}
    medication = resource.get("medicationCodeableConcept") or resource.get("medication", {}).get("concept")
    reason = None
    if resource.get("reasonCode"):
        reason = _text_from_codeable(resource["reasonCode"][0])
    elif resource.get("reason"):
        reason = _text_from_codeable_reference(resource["reason"][0])
    dosage = resource.get("dosage", [{}])[0].get("text") if resource.get("dosage") else None
    dose = _extension_value(resource, DOSE_EXTENSION_URL) or dosage
    frequency = _extension_value(resource, FREQUENCY_EXTENSION_URL)
    return {
        "name": _text_from_codeable(medication) or "Unknown medication",
        "dose": dose,
        "frequency": frequency,
        "start_date": effective.get("start"),
        "end_date": effective.get("end"),
        "status": _medication_status_from_fhir(resource.get("status"), effective),
        "reason": reason,
        "notes": _notes_text(resource.get("note")),
    }


def _observation_from_resource(resource: dict) -> tuple[str, dict]:
    category = " ".join(_text_from_codeable(item) or "" for item in resource.get("category", []))
    category_lower = category.lower()
    if "laboratory" in category_lower or "lab" in resource.get("id", "").lower():
        return "lab_results", _lab_from_observation(resource)
    if "wearable" in category_lower or "wearable" in resource.get("id", "").lower():
        return "wearable_records", _wearable_from_observation(resource)
    return "health_entries", _health_entry_from_observation(resource)


def _lab_from_observation(resource: dict) -> dict:
    quantity = resource.get("valueQuantity") or {}
    reference = resource.get("referenceRange", [{}])[0] if resource.get("referenceRange") else {}
    low = reference.get("low", {}).get("value")
    high = reference.get("high", {}).get("value")
    return {
        "test_name": _text_from_codeable(resource.get("code")) or "Unknown test",
        "result_value": resource.get("valueString") or (str(quantity.get("value")) if quantity.get("value") is not None else None),
        "numeric_value": normalize_optional_number(quantity.get("value")) if quantity.get("value") is not None else None,
        "unit": quantity.get("unit"),
        "reference_low": normalize_optional_number(low) if low is not None else None,
        "reference_high": normalize_optional_number(high) if high is not None else None,
        "flag": (_text_from_codeable(resource.get("interpretation", [{}])[0]) if resource.get("interpretation") else None) or "Unknown",
        "lab_date": _date_part(resource.get("effectiveDateTime")),
        "notes": _notes_text(resource.get("note")),
    }


def _wearable_from_observation(resource: dict) -> dict:
    quantity = resource.get("valueQuantity") or {}
    return {
        "metric_type": _text_from_codeable(resource.get("code")) or "Other",
        "value": quantity.get("value"),
        "unit": quantity.get("unit"),
        "timestamp": _date_part(resource.get("effectiveDateTime")),
        "source": resource.get("device", {}).get("display"),
    }


def _health_entry_from_observation(resource: dict) -> dict:
    severity = None
    for component in resource.get("component", []):
        if "severity" in (_text_from_codeable(component.get("code")) or "").lower():
            severity = component.get("valueInteger")
    categories = [_text_from_codeable(item) for item in resource.get("category", [])]
    body_system = next((item for item in categories if item and item != "Survey"), None)
    return {
        "entry_date": _date_part(resource.get("effectiveDateTime")),
        "title": _text_from_codeable(resource.get("code")) or "FHIR observation",
        "body_system": body_system,
        "body_part": _text_from_codeable(resource.get("bodySite")),
        "severity": severity,
        "note": resource.get("valueString") or _notes_text(resource.get("note")),
    }


def _appointment_from_resource(resource: dict) -> dict:
    requested_period = resource.get("requestedPeriod", [{}])[0] if resource.get("requestedPeriod") else {}
    provider = None
    for participant in resource.get("participant", []):
        actor = participant.get("actor", {})
        if not actor.get("reference", "").startswith("Patient/") and actor.get("display"):
            provider = actor["display"]
    return {
        "appointment_date": _date_part(requested_period.get("start")),
        "title": resource.get("description") or "FHIR appointment",
        "provider": provider,
        "location": resource.get("supportingInformation", [{}])[0].get("display") if resource.get("supportingInformation") else None,
        "status": _appointment_status_from_fhir(resource.get("status")),
        "notes": resource.get("comment") or _notes_text(resource.get("note")),
    }


def _task_from_resource(resource: dict) -> dict:
    period = resource.get("executionPeriod") or {}
    return {
        "reminder_type": _text_from_codeable(resource.get("code")) or "FHIR Task",
        "title": resource.get("description") or "FHIR task",
        "due_date": _date_part(period.get("end") or period.get("start")),
        "status": _task_status_from_fhir(resource.get("status")),
        "notes": _notes_text(resource.get("note")),
    }


def _text_from_codeable(value: dict | None) -> str | None:
    if not value:
        return None
    if value.get("text"):
        return value["text"]
    for coding in value.get("coding", []):
        if coding.get("display"):
            return coding["display"]
        if coding.get("code"):
            return coding["code"]
    return None


def _text_from_codeable_reference(value: dict | None) -> str | None:
    if not value:
        return None
    if value.get("concept"):
        return _text_from_codeable(value["concept"])
    if value.get("display"):
        return value["display"]
    if value.get("text"):
        return value["text"]
    return _text_from_codeable(value)


def _notes_text(notes: list[dict] | None) -> str | None:
    if not notes:
        return None
    values = [note.get("text") for note in notes if note.get("text")]
    return "\n".join(values) if values else None


def _extension_value(resource: dict, url: str) -> str | None:
    for extension in resource.get("extension", []):
        if extension.get("url") == url and extension.get("valueString"):
            return str(extension["valueString"])
    return None


def _date_part(value: str | None) -> str | None:
    if not value:
        return None
    return value[:10]


def _strip_empty(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            stripped = _strip_empty(item)
            if stripped not in (None, "", [], {}):
                result[key] = stripped
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            stripped = _strip_empty(item)
            if stripped not in (None, "", [], {}):
                result.append(stripped)
        return result
    return value
