from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, timedelta

import ai_config
import db
import services


DISCLAIMER = (
    "This report is for organization and education only. It is not a diagnosis or medical advice. "
    "Please discuss important findings, symptoms, medication questions, or abnormal results with a qualified healthcare professional."
)

URGENT_WARNING = (
    "Some symptoms may require urgent medical attention. If these symptoms are current, severe, or worsening, "
    "seek emergency care or call emergency services."
)

AI_SAFETY_INSTRUCTIONS = (
    "You are helping organize a personal health record. Provide cautious, non-diagnostic insights only. "
    "Identify possible issues to discuss with a qualified clinician and suggest safe, unobtrusive next steps such as "
    "tracking symptoms, confirming records, preparing questions, hydration, rest, sleep hygiene, gentle activity when already safe, "
    "and scheduling routine follow-up. Do not diagnose conditions, estimate prognosis, prescribe treatments, recommend medication "
    "or supplement changes, recommend stopping or starting medication, interpret emergencies as manageable at home, suggest restrictive diets, "
    "intense exercise, invasive actions, or anything that could delay urgent care. If red-flag symptoms appear, advise urgent professional care."
)

RED_FLAG_TERMS = [
    "chest pain",
    "stroke symptoms",
    "severe shortness of breath",
    "severe allergic reaction",
    "suicidal thoughts",
    "severe bleeding",
    "fainting",
    "loss of consciousness",
]

AI_CONTEXT_LIMITS = {
    "active_medications": 3,
    "allergies": 3,
    "recent_abnormal_labs": 3,
    "recent_symptoms": 3,
    "upcoming_appointments": 1,
    "open_reminders": 2,
    "rule_based_findings": 4,
}

AI_CONTEXT_FIELDS = {
    "person": ["name", "date_of_birth", "sex", "relationship", "notes"],
    "medications": ["name", "dose", "frequency", "status", "reason", "notes"],
    "allergies": ["allergen", "reaction", "severity", "notes"],
    "labs": ["test_name", "result_value", "numeric_value", "unit", "reference_low", "reference_high", "flag", "lab_date", "notes"],
    "health_entries": ["entry_date", "title", "body_system", "body_part", "severity", "note"],
    "appointments": ["appointment_date", "title", "provider", "status", "notes"],
    "reminders": ["reminder_type", "title", "due_date", "status", "notes"],
    "wearables": ["metric_type", "value", "unit", "timestamp", "source"],
}


class ZhipuAPIError(Exception):
    def __init__(self, http_status: int | None, provider_code: str | None, detail: str):
        super().__init__(detail)
        self.http_status = http_status
        self.provider_code = provider_code
        self.detail = detail


class ZhipuRetryableError(Exception):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def collect_health_context(
    person_id: int,
    date_range: tuple | None,
    include_medications: bool = True,
    include_allergies: bool = True,
    include_labs: bool = True,
    include_health_entries: bool = True,
    include_appointments: bool = True,
    include_reminders: bool = True,
    include_wearables: bool = True,
    db_path=db.DB_PATH,
) -> dict:
    start_date, end_date = date_range if date_range else (None, None)
    context = {"person": services.get_person(person_id, db_path=db_path), "date_range": date_range}
    if include_medications:
        context["medications"] = services.list_items("medications", person_id, order_by="name", descending=False, db_path=db_path)
    if include_allergies:
        context["allergies"] = services.list_items("allergies", person_id, order_by="allergen", descending=False, db_path=db_path)
    if include_labs:
        context["labs"] = services.filter_labs(person_id, start_date, end_date, db_path=db_path)
    if include_health_entries:
        context["health_entries"] = services.filter_health_entries(person_id, start_date, end_date, db_path=db_path)
    if include_appointments:
        context["appointments"] = services.upcoming_appointments(person_id, db_path=db_path)
    if include_reminders:
        context["reminders"] = services.list_items("reminders", person_id, order_by="due_date", descending=False, db_path=db_path)
    if include_wearables:
        filters = {}
        if start_date:
            filters["timestamp__gte"] = start_date
        if end_date:
            filters["timestamp__lte"] = end_date
        context["wearables"] = services.list_items("wearable_records", person_id, filters, "timestamp", True, db_path=db_path)
    return context


def detect_possible_urgent_flags(context: dict) -> list[str]:
    text_parts = []
    for collection_name in ["health_entries", "labs", "appointments", "reminders"]:
        for row in context.get(collection_name, []):
            text_parts.extend(str(value).lower() for value in row.values() if value is not None)
    haystack = " ".join(text_parts)
    return [term for term in RED_FLAG_TERMS if term in haystack]


def _average_metric(context: dict, metric_type: str) -> float | None:
    values = [_safe_float(row.get("value")) for row in context.get("wearables", []) if row.get("metric_type") == metric_type]
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 2) if values else None


def _weight_change(context: dict) -> float | None:
    weights = [row for row in context.get("wearables", []) if row.get("metric_type") == "Weight" and _safe_float(row.get("value")) is not None]
    if len(weights) < 2:
        return None
    weights = sorted(weights, key=lambda row: row.get("timestamp") or "")
    return round(_safe_float(weights[-1].get("value")) - _safe_float(weights[0].get("value")), 2)


def _safe_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _truncate_text(value, limit: int = 80):
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}..."


def _compact_row(row: dict, fields: list[str]) -> dict:
    compacted = {}
    for field in fields:
        value = row.get(field)
        if value is not None and value != "":
            compacted[field] = _truncate_text(value)
    return compacted


def _json_size(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _fit_packet_to_budget(packet: dict, byte_limit: int) -> dict:
    fitted = json.loads(json.dumps(packet))
    if _json_size(fitted) <= byte_limit:
        return fitted

    for section in ("recent_symptoms", "open_reminders", "upcoming_appointments", "allergies", "active_medications", "recent_abnormal_labs"):
        while len(fitted.get(section, [])) > 1 and _json_size(fitted) > byte_limit:
            fitted[section].pop()

    for section in ("rule_based_findings",):
        while len(fitted.get(section, [])) > 2 and _json_size(fitted) > byte_limit:
            fitted[section].pop()

    if _json_size(fitted) <= byte_limit:
        return fitted

    for section in ("recent_symptoms", "open_reminders", "upcoming_appointments", "allergies", "active_medications", "recent_abnormal_labs"):
        for row in fitted.get(section, []):
            for key, value in list(row.items()):
                if isinstance(value, str) and len(value) > 40:
                    row[key] = f"{value[:40]}..."
        if _json_size(fitted) <= byte_limit:
            return fitted

    if _json_size(fitted) > byte_limit:
        fitted.pop("trend_summary", None)
    if _json_size(fitted) > byte_limit:
        fitted.pop("record_counts", None)
    if _json_size(fitted) > byte_limit:
        for section in ("recent_symptoms", "open_reminders", "upcoming_appointments", "allergies", "active_medications", "recent_abnormal_labs"):
            fitted[section] = fitted.get(section, [])[:1]
    return fitted


def compact_context_for_ai(context: dict) -> dict:
    medications = context.get("medications", [])
    allergies = context.get("allergies", [])
    labs = context.get("labs", [])
    entries = context.get("health_entries", [])
    appointments = context.get("appointments", [])
    reminders = context.get("reminders", [])

    active_medications = [row for row in medications if row.get("status") == "Active"]
    abnormal_labs = [row for row in labs if row.get("flag") in {"High", "Low", "Abnormal", "Critical"}]
    recent_cutoff = (date.today() - timedelta(days=30)).isoformat()
    recent_symptoms = [row for row in entries if row.get("entry_date", "") >= recent_cutoff]
    today = date.today().isoformat()
    open_reminders = [row for row in reminders if row.get("status") not in {"Completed", "Dismissed"}]

    active_medications = sorted(active_medications, key=lambda row: row.get("name") or "")
    abnormal_labs = sorted(abnormal_labs, key=lambda row: row.get("lab_date") or "", reverse=True)
    recent_symptoms = sorted(recent_symptoms, key=lambda row: row.get("entry_date") or "", reverse=True)
    appointments = sorted(appointments, key=lambda row: row.get("appointment_date") or "")
    open_reminders = sorted(open_reminders, key=lambda row: row.get("due_date") or "")

    avg_steps = _average_metric(context, "Steps")
    avg_sleep = _average_metric(context, "Sleep")
    weight_delta = _weight_change(context)
    body_counts = Counter(row.get("body_system") or "Unspecified" for row in entries)

    trend_summary = {}
    if avg_steps is not None:
        trend_summary["steps"] = f"Average recorded steps: {avg_steps}"
    if avg_sleep is not None:
        trend_summary["sleep"] = f"Average recorded sleep: {avg_sleep}"
    if weight_delta is not None:
        trend_summary["weight"] = f"Weight changed by {weight_delta} over selected records"
    if body_counts:
        system, count = body_counts.most_common(1)[0]
        trend_summary["symptoms"] = f"Most frequently recorded body system: {system} ({count} entries)"

    rule_based_findings = []
    if abnormal_labs:
        rule_based_findings.append(f"{len(abnormal_labs)} lab result(s) are marked high, low, abnormal, or critical.")
    overdue = [row for row in open_reminders if row.get("due_date", "") < today]
    if overdue:
        rule_based_findings.append(f"{len(overdue)} reminder(s) are overdue.")
    if detect_possible_urgent_flags(context):
        rule_based_findings.append("Record text contains possible urgent red-flag terms.")
    if not active_medications:
        rule_based_findings.append("No active medications are recorded in the selected context.")
    if not labs:
        rule_based_findings.append("No lab records are included in the selected context.")

    person = context.get("person") or {}
    packet = {
        "person_context": _compact_row(person, ["sex", "relationship"]),
        "date_range": context.get("date_range"),
        "record_counts": {
            "medications": len(medications),
            "allergies": len(allergies),
            "labs": len(labs),
            "health_entries": len(entries),
            "appointments": len(appointments),
            "reminders": len(reminders),
            "wearables": len(context.get("wearables", [])),
        },
        "active_medications": [
            _compact_row(row, ["name", "dose", "frequency"])
            for row in active_medications[: AI_CONTEXT_LIMITS["active_medications"]]
        ],
        "allergies": [
            _compact_row(row, ["allergen", "reaction", "severity"])
            for row in allergies[: AI_CONTEXT_LIMITS["allergies"]]
        ],
        "recent_abnormal_labs": [
            _compact_row(row, ["test_name", "result_value", "numeric_value", "unit", "reference_low", "reference_high", "flag", "lab_date"])
            for row in abnormal_labs[: AI_CONTEXT_LIMITS["recent_abnormal_labs"]]
        ],
        "recent_symptoms": [
            _compact_row(row, ["entry_date", "title", "body_system", "severity"])
            for row in recent_symptoms[: AI_CONTEXT_LIMITS["recent_symptoms"]]
        ],
        "upcoming_appointments": [
            _compact_row(row, ["appointment_date", "title", "status"])
            for row in appointments[: AI_CONTEXT_LIMITS["upcoming_appointments"]]
        ],
        "open_reminders": [
            _compact_row(row, ["reminder_type", "title", "due_date", "status"])
            for row in open_reminders[: AI_CONTEXT_LIMITS["open_reminders"]]
        ],
        "trend_summary": trend_summary,
        "rule_based_findings": rule_based_findings[: AI_CONTEXT_LIMITS["rule_based_findings"]],
    }
    return _fit_packet_to_budget(packet, ai_config.ZHIPU_CONTEXT_BYTE_LIMIT)


def _parse_http_error(exc: urllib.error.HTTPError) -> tuple[str | None, str]:
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    if not body:
        return None, str(exc)
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            error = parsed.get("error") or parsed
            if isinstance(error, dict):
                message = error.get("message") or error.get("msg") or body
                code = error.get("code")
                detail = f"{exc} ({code}: {message})" if code else f"{exc} ({message})"
                return str(code) if code else None, detail
    except json.JSONDecodeError:
        pass
    return None, f"{exc} ({body[:500]})"


def _call_zhipu_chat_completion(request: urllib.request.Request) -> dict:
    last_error = None
    for delay in (0, 3, 8):
        if delay:
            time.sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            provider_code, detail = _parse_http_error(exc)
            last_error = ZhipuAPIError(exc.code, provider_code, detail)
            if exc.code != 429 or provider_code == "1113":
                raise last_error
        except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(exc).lower():
                last_error = ZhipuRetryableError(str(exc))
                continue
            raise
    raise last_error


def _build_zhipu_request(api_key: str, model: str, messages: list[dict], max_tokens: int, temperature: float) -> urllib.request.Request:
    return urllib.request.Request(
        ai_config.ZHIPU_API_URL,
        data=json.dumps(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "thinking": {"type": "disabled"},
            }
        ).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )


def _call_zhipu_with_model_fallback(
    api_key: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
) -> tuple[dict, str]:
    last_error = None
    for model in ai_config.zhipu_model_candidates():
        request = _build_zhipu_request(api_key, model, messages, max_tokens, temperature)
        try:
            return _call_zhipu_chat_completion(request), model
        except ZhipuAPIError as exc:
            last_error = exc
            if exc.http_status != 429:
                raise
        except ZhipuRetryableError as exc:
            last_error = exc
    raise last_error


def validate_zhipu_connection() -> tuple[bool, str, str | None]:
    if ai_config.AI_PROVIDER != "zhipu":
        return False, f"AI provider is set to '{ai_config.AI_PROVIDER}', not 'zhipu'.", None
    api_key = ai_config.get_zhipu_api_key()
    if not api_key:
        return False, "No Zhipu AI API key is configured.", None

    messages = [{"role": "user", "content": "Reply with OK."}]
    try:
        payload, model = _call_zhipu_with_model_fallback(api_key, messages, 8, 0)
        text = payload["choices"][0]["message"]["content"].strip()
    except ZhipuAPIError as exc:
        return False, "BigModel rejected the API key or model request.", exc.detail
    except ZhipuRetryableError as exc:
        return False, "BigModel timed out after retries.", exc.detail
    except Exception as exc:
        return False, "Could not reach the BigModel API.", str(exc)
    if not text:
        return False, "BigModel returned an empty response.", None
    return True, f"BigModel API key works with model {model}.", None


def generate_rule_based_insights(context: dict, focus_area: str | None = None) -> str:
    medications = context.get("medications", [])
    reminders = context.get("reminders", [])
    labs = context.get("labs", [])
    entries = context.get("health_entries", [])
    appointments = context.get("appointments", [])
    wearables = context.get("wearables", [])

    active_med_count = len([m for m in medications if m.get("status") == "Active"])
    today = date.today().isoformat()
    overdue = [r for r in reminders if r.get("due_date", "") < today and r.get("status") not in {"Completed", "Dismissed"}]
    abnormal = [l for l in labs if l.get("flag") in {"High", "Low", "Abnormal", "Critical"}]
    missing_ranges = [l for l in labs if l.get("reference_low") is None or l.get("reference_high") is None]
    body_counts = Counter(e.get("body_system") or "Unspecified" for e in entries)
    recent_cutoff = (date.today() - timedelta(days=30)).isoformat()
    recent_symptoms = [e for e in entries if e.get("entry_date", "") >= recent_cutoff]
    avg_steps = _average_metric(context, "Steps")
    avg_sleep = _average_metric(context, "Sleep")
    weight_delta = _weight_change(context)
    red_flags = detect_possible_urgent_flags(context)

    missing_data = []
    for label, rows in [
        ("medications", medications),
        ("allergies", context.get("allergies", [])),
        ("labs", labs),
        ("health timeline", entries),
        ("appointments", appointments),
        ("reminders", reminders),
        ("wearables", wearables),
    ]:
        if not rows:
            missing_data.append(label)

    trends = []
    if body_counts:
        system, count = body_counts.most_common(1)[0]
        trends.append(f"The most frequently recorded body system is {system} ({count} entries).")
    if avg_steps is not None:
        trends.append(f"Average recorded steps: {avg_steps}.")
    if avg_sleep is not None:
        trends.append(f"Average recorded sleep: {avg_sleep}.")
    if weight_delta is not None:
        trends.append(f"Weight changed by {weight_delta} over the selected records.")
    if abnormal:
        trends.append(f"{len(abnormal)} lab result(s) are marked high, low, abnormal, or critical.")

    followups = []
    followups += [f"Review overdue reminder: {r['title']} due {r['due_date']}." for r in overdue]
    followups += [f"Prepare for appointment: {a['title']} on {a['appointment_date']}." for a in appointments[:5]]
    if missing_ranges:
        followups.append(f"Add reference ranges for {len(missing_ranges)} lab result(s) where available.")

    questions = []
    if abnormal:
        questions.append("Which abnormal lab results need follow-up, repeat testing, or monitoring?")
    if active_med_count:
        questions.append("Are all active medications, doses, and frequencies still current?")
    if recent_symptoms:
        questions.append("Do recent symptoms suggest anything that should be tracked more closely before the next visit?")
    if not questions:
        questions.append("What health information would be most useful to track before the next appointment?")

    safety_notes = [DISCLAIMER]
    if red_flags:
        safety_notes.insert(0, URGENT_WARNING)

    sections = {
        "1. Overall Summary": [
            f"Focus area: {focus_area or 'General overview'}.",
            f"Active medications: {active_med_count}.",
            f"Overdue reminders: {len(overdue)}.",
            f"Upcoming appointments: {len(appointments)}.",
        ],
        "2. Notable Trends": trends or ["No strong trends were detected from the selected records."],
        "3. Possible Areas for Improvement": [
            "Keep medication status and dates current.",
            "Add notes to symptom entries when context may help a provider.",
            "Record units and reference ranges for lab results when available.",
        ],
        "4. Suggested Questions for Doctor": questions,
        "5. Data Gaps": [f"Missing or sparse areas: {', '.join(missing_data)}."] if missing_data else ["Selected data areas have at least one record."],
        "6. Follow-Up Items": followups or ["No overdue reminders or immediate follow-up items were detected."],
        "7. Safety Notes": safety_notes,
    }

    lines = ["# Health Insights Report", ""]
    for heading, items in sections.items():
        lines.extend([f"## {heading}", *[f"- {item}" for item in items], ""])
    return "\n".join(lines).strip()


def generate_ai_insight_report(context: dict, focus_area: str | None = None) -> str:
    result = generate_ai_insight_result(context, focus_area)
    return result["report"]


def build_ai_insight_prompt(context: dict, focus_area: str | None = None) -> str:
    prompt = {
        "task": (
            "Return concise markdown titled 'AI Safety-Checked Insights'. Include: "
            "1) possible patterns or issues noticed, 2) safe low-risk actions the patient can take, "
            "3) questions or records to bring to a clinician, and 4) safety note. "
            "Keep suggestions practical and unobtrusive."
        ),
        "focus": focus_area or "General overview",
        "safety_rules": [
            "Do not diagnose or name a condition as certain.",
            "Do not prescribe, stop, start, or change medications or supplements.",
            "Do not suggest urgent symptoms can be handled at home.",
            "Do not recommend restrictive diets, intense exercise, or invasive actions.",
            "Use language such as 'may be worth discussing' and 'consider tracking'.",
            "Prefer recordkeeping, clinician follow-up, gentle routines, and preparation questions.",
        ],
        "data": compact_context_for_ai(context),
    }
    return json.dumps(prompt, ensure_ascii=False, separators=(",", ":"))


def generate_ai_insight_result(context: dict, focus_area: str | None = None) -> dict:
    if ai_config.AI_PROVIDER == "none":
        return {
            "report": generate_rule_based_insights(context, focus_area),
            "used_fallback": True,
            "warning": "AI safety-checked insights are disabled by AI_PROVIDER=none. Showing rule-based report instead.",
        }
    if ai_config.AI_PROVIDER != "zhipu":
        return {
            "report": generate_rule_based_insights(context, focus_area),
            "used_fallback": True,
            "warning": f"AI provider '{ai_config.AI_PROVIDER}' is not implemented. Showing rule-based report instead.",
        }

    api_key = ai_config.get_zhipu_api_key()
    if not api_key:
        return {
            "report": generate_rule_based_insights(context, focus_area),
            "used_fallback": True,
            "warning": "AI safety-checked insights unavailable because no Zhipu AI API key is configured. Showing rule-based report instead.",
        }

    prompt_text = build_ai_insight_prompt(context, focus_area)
    messages = [
        {"role": "system", "content": AI_SAFETY_INSTRUCTIONS},
        {"role": "user", "content": prompt_text},
    ]
    try:
        payload, model = _call_zhipu_with_model_fallback(api_key, messages, ai_config.ZHIPU_MAX_TOKENS, 0.2)
        text = payload["choices"][0]["message"]["content"].strip()
    except ZhipuAPIError as exc:
        rule_based_report = generate_rule_based_insights(context, focus_area)
        if exc.provider_code == "1113":
            warning = "AI safety-checked insights unavailable because the Zhipu account has insufficient balance or no usable resource package. Showing rule-based report instead."
        elif exc.http_status == 429:
            warning = "AI safety-checked insights unavailable because Zhipu returned HTTP 429 after retries. The key may be rate-limited, out of quota, or unable to access the selected model. Showing rule-based report instead."
        else:
            warning = "AI safety-checked insights unavailable because Zhipu returned an error. Showing rule-based report instead."
        return {
            "report": rule_based_report,
            "used_fallback": True,
            "warning": warning,
            "provider_details": exc.detail,
        }
    except ZhipuRetryableError as exc:
        return {
            "report": generate_rule_based_insights(context, focus_area),
            "used_fallback": True,
            "warning": "AI safety-checked insights unavailable because BigModel timed out after retries. Showing rule-based report instead.",
            "provider_details": exc.detail,
        }
    except Exception as exc:
        return {
            "report": generate_rule_based_insights(context, focus_area),
            "used_fallback": True,
            "warning": "AI safety-checked insights unavailable because the provider request failed. Showing rule-based report instead.",
            "provider_details": str(exc),
        }
    if DISCLAIMER not in text:
        text = f"{text}\n\n{DISCLAIMER}"
    warning = None
    if model != ai_config.ZHIPU_MODEL:
        warning = f"BigModel was busy for {ai_config.ZHIPU_MODEL}, so the app used fallback model {model}."
    return {"report": text, "used_fallback": False, "warning": warning}
