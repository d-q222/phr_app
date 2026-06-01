from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from datetime import date, timedelta
from hashlib import sha1
from pathlib import Path

import streamlit as st

import ai_config
import db
import insights
import services


PRIVACY_NOTICE = (
    "This sends the selected patient’s relevant health context and your message to Zhipu AI. "
    "Do not include information you do not want sent to the API."
)

EXAMPLE_QUESTIONS = [
    "Summarize my recent labs.",
    "What medications am I currently taking?",
    "What should I ask my doctor?",
    "Are any reminders overdue?",
    "Make a provider visit summary.",
    "Explain this lab result in plain language.",
    "What changed recently in this profile?",
]

CHAT_CONTEXT_LIMITS = {
    "allergies": 8,
    "active_medications": 10,
    "recent_labs": 12,
    "recent_health_entries": 10,
    "appointments": 6,
    "overdue_reminders": 8,
    "upcoming_reminders": 8,
    "wearable_summary": 6,
    "rule_based_findings": 5,
}

DEFAULT_CHAT_MODEL = "glm-5.1"
DEFAULT_CHAT_MAX_TOKENS = 1200
DEFAULT_CHAT_TEMPERATURE = 0.3
CHAT_TIMEOUT_SECONDS = 45


class AIChatError(Exception):
    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class MissingAPIKeyError(AIChatError):
    pass


class RateLimitError(AIChatError):
    pass


class NetworkAIChatError(AIChatError):
    pass


class InvalidAIResponseError(AIChatError):
    pass


def _env_value(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value else None


def chat_model_candidates(model: str = DEFAULT_CHAT_MODEL) -> list[str]:
    candidates = [_env_value("ZHIPU_CHAT_MODEL") or model]
    chat_fallbacks = _env_value("ZHIPU_CHAT_FALLBACK_MODELS")
    if chat_fallbacks is not None:
        candidates.extend(item.strip() for item in chat_fallbacks.split(",") if item.strip())
    else:
        candidates.extend(ai_config.zhipu_model_candidates())

    deduped = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _streamlit_secret(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except Exception:
        return None
    return str(value).strip() if value else None


def get_zhipu_api_key() -> str | None:
    for name in ("ZAI_API_KEY", "ZHIPU_API_KEY"):
        value = _streamlit_secret(name)
        if value:
            return value
    for name in ("ZAI_API_KEY", "ZHIPU_API_KEY"):
        value = os.getenv(name)
        if value:
            return value.strip()
    return ai_config.get_zhipu_api_key()


def _truncate(value, limit: int = 180):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _compact_row(row: dict, fields: list[str], text_limit: int = 180) -> dict:
    compacted = {}
    for field in fields:
        value = _truncate(row.get(field), text_limit)
        if value is not None:
            compacted[field] = value
    return compacted


def _recent_labs(person_id: int, db_path: Path | str) -> list[dict]:
    labs = services.list_items("lab_results", person_id, order_by="lab_date", descending=True, db_path=db_path)
    abnormal = [row for row in labs if row.get("flag") in {"Critical", "Abnormal", "High", "Low"}]
    normal = [row for row in labs if row not in abnormal]
    return (abnormal + normal)[: CHAT_CONTEXT_LIMITS["recent_labs"]]


def _reminder_groups(person_id: int, db_path: Path | str) -> tuple[list[dict], list[dict]]:
    reminders = services.list_items("reminders", person_id, order_by="due_date", descending=False, db_path=db_path)
    today = date.today().isoformat()
    open_reminders = [row for row in reminders if row.get("status") not in {"Completed", "Dismissed"}]
    overdue = [row for row in open_reminders if row.get("due_date", "") < today]
    upcoming = [row for row in open_reminders if row.get("due_date", "") >= today]
    return overdue, upcoming


def _patient_context_packet(person_id: int, db_path: Path | str = db.DB_PATH) -> dict:
    person = services.get_person(person_id, db_path=db_path)
    if not person:
        return {}

    recent_cutoff = (date.today() - timedelta(days=180)).isoformat()
    recent_entries = services.list_items(
        "health_entries",
        person_id,
        {"entry_date__gte": recent_cutoff},
        order_by="entry_date",
        descending=True,
        limit=CHAT_CONTEXT_LIMITS["recent_health_entries"],
        db_path=db_path,
    )
    if not recent_entries:
        recent_entries = services.recent_health_entries(
            person_id,
            limit=CHAT_CONTEXT_LIMITS["recent_health_entries"],
            db_path=db_path,
        )

    overdue_reminders, upcoming_reminders = _reminder_groups(person_id, db_path)
    context = insights.collect_health_context(person_id, None, db_path=db_path)
    insight_packet = insights.compact_context_for_ai(context)

    packet = {
        "basic_profile": _compact_row(
            person,
            ["name", "date_of_birth", "sex", "relationship", "emergency_contact", "notes"],
            text_limit=220,
        ),
        "record_counts": {
            "allergies": len(context.get("allergies", [])),
            "medications": len(context.get("medications", [])),
            "labs": len(context.get("labs", [])),
            "health_entries": len(context.get("health_entries", [])),
            "appointments": len(context.get("appointments", [])),
            "reminders": len(context.get("reminders", [])),
            "wearables": len(context.get("wearables", [])),
        },
        "allergies": [
            _compact_row(row, ["allergen", "reaction", "severity", "notes"])
            for row in context.get("allergies", [])[: CHAT_CONTEXT_LIMITS["allergies"]]
        ],
        "active_medications": [
            _compact_row(row, ["name", "dose", "frequency", "start_date", "reason", "notes"])
            for row in services.active_medications(person_id, db_path=db_path)[: CHAT_CONTEXT_LIMITS["active_medications"]]
        ],
        "recent_labs": [
            _compact_row(
                row,
                ["test_name", "result_value", "numeric_value", "unit", "reference_low", "reference_high", "flag", "lab_date", "notes"],
            )
            for row in _recent_labs(person_id, db_path)
        ],
        "recent_health_entries": [
            _compact_row(row, ["entry_date", "title", "body_system", "body_part", "severity", "note"])
            for row in recent_entries
        ],
        "appointments": [
            _compact_row(row, ["appointment_date", "title", "provider", "location", "status", "notes"])
            for row in services.upcoming_appointments(person_id, db_path=db_path)[: CHAT_CONTEXT_LIMITS["appointments"]]
        ],
        "overdue_reminders": [
            _compact_row(row, ["reminder_type", "title", "due_date", "status", "notes"])
            for row in overdue_reminders[: CHAT_CONTEXT_LIMITS["overdue_reminders"]]
        ],
        "upcoming_reminders": [
            _compact_row(row, ["reminder_type", "title", "due_date", "status", "notes"])
            for row in upcoming_reminders[: CHAT_CONTEXT_LIMITS["upcoming_reminders"]]
        ],
        "wearable_summary": services.wearable_summary(person_id, db_path=db_path)[: CHAT_CONTEXT_LIMITS["wearable_summary"]],
        "existing_summaries_or_insights": {
            "rule_based_findings": insight_packet.get("rule_based_findings", [])[: CHAT_CONTEXT_LIMITS["rule_based_findings"]],
            "trend_summary": insight_packet.get("trend_summary", {}),
        },
    }
    return packet


def build_patient_context(person_id: int, db_path: Path | str = db.DB_PATH) -> str:
    packet = _patient_context_packet(person_id, db_path=db_path)
    return json.dumps(packet, ensure_ascii=False, indent=2, default=str)


def _has_health_data(packet: dict) -> bool:
    counts = packet.get("record_counts", {})
    return any(int(value or 0) > 0 for value in counts.values())


def build_ai_system_prompt() -> str:
    return (
        "You are an AI assistant inside a personal health record app. Help the user understand and summarize their own "
        "stored health records. You are not a doctor. Do not diagnose, prescribe, or replace medical care. You may explain "
        "terms, summarize trends, organize information, suggest clinician questions, and prepare visit summaries. Say when "
        "information is missing or uncertain. For emergencies such as chest pain, trouble breathing, stroke symptoms, severe "
        "allergic reaction, suicidal thoughts, or any urgent medical concern, tell the user to seek emergency help immediately.\n\n"
        "Use only the selected patient context supplied in the current request. Do not infer or invent records. If the selected "
        "patient context does not contain the needed data, say what is missing."
    )


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
    except json.JSONDecodeError:
        return None, f"{exc} ({body[:500]})"
    if isinstance(parsed, dict):
        error = parsed.get("error") or parsed
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message") or error.get("msg") or body
            return str(code) if code else None, f"{exc} ({code}: {message})" if code else f"{exc} ({message})"
    return None, f"{exc} ({body[:500]})"


def call_zhipu_chat(
    messages: list[dict],
    model: str = DEFAULT_CHAT_MODEL,
    temperature: float = DEFAULT_CHAT_TEMPERATURE,
    max_tokens: int = DEFAULT_CHAT_MAX_TOKENS,
) -> str:
    api_key = get_zhipu_api_key()
    if not api_key:
        raise MissingAPIKeyError("Zhipu AI API key is not configured.")

    last_error: AIChatError | None = None
    tried_models = []
    for candidate_model in chat_model_candidates(model):
        tried_models.append(candidate_model)
        try:
            return _call_zhipu_chat_model(api_key, candidate_model, messages, temperature, max_tokens)
        except RateLimitError as exc:
            last_error = exc
            continue
        except NetworkAIChatError as exc:
            last_error = exc
            continue

    if isinstance(last_error, RateLimitError):
        raise RateLimitError(
            "Zhipu AI could not complete the request with any configured chat model. "
            "Your account may not have access, quota, or a usable resource package for these models.",
            f"Tried models: {', '.join(tried_models)}\n\n{last_error.detail or last_error.message}",
        )
    if last_error:
        raise last_error
    raise AIChatError("No Zhipu chat model is configured.")


def _call_zhipu_chat_model(
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    request = urllib.request.Request(
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
    try:
        with urllib.request.urlopen(request, timeout=CHAT_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        provider_code, detail = _parse_http_error(exc)
        if exc.code == 429:
            if provider_code == "1113":
                raise RateLimitError(
                    f"Zhipu AI could not use model {model} because the account has insufficient balance or no usable resource package.",
                    detail,
                ) from exc
            raise RateLimitError(f"Zhipu AI model {model} is rate-limited or temporarily busy.", detail) from exc
        if exc.code in {401, 403}:
            raise MissingAPIKeyError("Zhipu AI rejected the API key. Check that your key is correct and has access to this model.", detail) from exc
        raise AIChatError("Zhipu AI returned an error.", detail) from exc
    except (TimeoutError, socket.timeout, urllib.error.URLError) as exc:
        raise NetworkAIChatError("Could not reach Zhipu AI. Check your network connection and try again.", str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise InvalidAIResponseError("Zhipu AI returned a response the app could not read.", str(exc)) from exc

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise InvalidAIResponseError("Zhipu AI returned an unexpected response format.", json.dumps(payload)[:1000]) from exc
    if not str(content).strip():
        raise InvalidAIResponseError("Zhipu AI returned an empty response.")
    return str(content).strip()


def _history_key(person_id: int, db_path: Path | str) -> str:
    db_scope = sha1(str(db_path).encode("utf-8")).hexdigest()[:12]
    return f"ai_chat_history_{db_scope}_{person_id}"


def _render_message(role: str, content: str) -> None:
    if hasattr(st, "chat_message"):
        with st.chat_message(role):
            st.markdown(content)
    else:
        speaker = "Assistant" if role == "assistant" else "You"
        st.markdown(f"**{speaker}:** {content}")


def _example_questions(draft_key: str) -> None:
    selection_key = f"example_question_{draft_key}"
    selected = st.pills(
        "Example questions",
        EXAMPLE_QUESTIONS,
        format_func=lambda question: f"💬 {question.rstrip('.?')}",
        key=selection_key,
        width="content",
    )
    if selected and st.session_state.get(f"{selection_key}_applied") != selected:
        st.session_state[draft_key] = selected
        st.session_state[f"{selection_key}_applied"] = selected
        st.rerun()


def render_ai_chatbot(person_id: int, db_path: Path | str = db.DB_PATH) -> None:
    person = services.get_person(person_id, db_path=db_path)
    if not person:
        st.error("No selected profile was found. Select or create a profile before using AI Chat.")
        return

    history_key = _history_key(person_id, db_path)
    draft_key = f"{history_key}_draft"
    st.session_state.setdefault(history_key, [])
    st.session_state.setdefault(draft_key, "")

    st.warning(f"⚠️ {PRIVACY_NOTICE}")
    _example_questions(draft_key)

    if st.button("🧹 Clear chat", key=f"clear_{history_key}"):
        st.session_state[history_key] = []
        st.rerun()

    packet = _patient_context_packet(person_id, db_path=db_path)
    if not _has_health_data(packet):
        st.info("No health data is available for this selected profile yet. Add records before using AI Chat.")
        return

    for message in st.session_state[history_key]:
        _render_message(message["role"], message["content"])

    prompt = (
        st.chat_input("Ask about the selected profile's health records", key=draft_key)
        if hasattr(st, "chat_input")
        else st.text_input("Ask about the selected profile's health records", key=draft_key)
    )
    if not prompt:
        return

    user_message = {"role": "user", "content": prompt}
    st.session_state[history_key].append(user_message)
    _render_message("user", prompt)

    context_text = json.dumps(packet, ensure_ascii=False, indent=2, default=str)
    messages = [{"role": "system", "content": build_ai_system_prompt()}]
    messages.extend(st.session_state[history_key][-8:-1])
    messages.append(
        {
            "role": "user",
            "content": (
                "Selected patient context from the local PHR follows. Use only this selected patient's data.\n\n"
                f"{context_text}\n\n"
                f"User question: {prompt}"
            ),
        }
    )

    try:
        with st.spinner("Asking Zhipu AI..."):
            answer = call_zhipu_chat(messages)
    except AIChatError as exc:
        st.error(exc.message)
        if exc.detail:
            with st.expander("Provider details"):
                st.code(exc.detail)
        return

    st.session_state[history_key].append({"role": "assistant", "content": answer})
    _render_message("assistant", answer)
