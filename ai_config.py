from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


KEYCHAIN_SERVICE = "phr_app.zhipu_ai"
KEYCHAIN_ACCOUNT = "ZAI_API_KEY"
DEFAULT_ZHIPU_MODEL = "glm-4.5-flash"
DEFAULT_ZHIPU_FALLBACK_MODELS = "glm-4.7-flash"
DEFAULT_ZHIPU_MAX_TOKENS = 220
DEFAULT_ZHIPU_CONTEXT_BYTE_LIMIT = 1200
# Cap on provider response bodies read into memory before JSON parsing; a
# misbehaving provider must not be able to exhaust memory through one response.
ZHIPU_RESPONSE_BYTE_LIMIT = 5_000_000
ZHIPU_API_URL = os.getenv(
    "ZHIPU_API_URL",
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
)
AI_PROVIDER = os.getenv("AI_PROVIDER", "zhipu").strip().lower()
ZHIPU_MODEL = os.getenv("ZHIPU_MODEL", os.getenv("ZAI_MODEL", DEFAULT_ZHIPU_MODEL)).strip()
ZHIPU_FALLBACK_MODELS = os.getenv("ZHIPU_FALLBACK_MODELS", DEFAULT_ZHIPU_FALLBACK_MODELS)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


ZHIPU_MAX_TOKENS = _env_int("ZHIPU_MAX_TOKENS", DEFAULT_ZHIPU_MAX_TOKENS)
ZHIPU_CONTEXT_BYTE_LIMIT = _env_int("ZHIPU_CONTEXT_BYTE_LIMIT", DEFAULT_ZHIPU_CONTEXT_BYTE_LIMIT)


def zhipu_model_candidates() -> list[str]:
    candidates = [ZHIPU_MODEL] if ZHIPU_MODEL else []
    candidates.extend(model.strip() for model in ZHIPU_FALLBACK_MODELS.split(",") if model.strip())
    return list(dict.fromkeys(candidates))


def streamlit_secret(name: str) -> str | None:
    """Read one Streamlit secret, returning None if secrets are unavailable or unset.

    Imports Streamlit lazily so this module stays importable outside a Streamlit process.
    """
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:
        return None
    return str(value).strip() if value else None


def _get_keychain_password() -> str | None:
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                KEYCHAIN_ACCOUNT,
                "-w",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def get_zhipu_api_key() -> str | None:
    for name in ("ZAI_API_KEY", "ZHIPU_API_KEY"):
        value = streamlit_secret(name)
        if value:
            return value.strip()
    for name in ("ZAI_API_KEY", "ZHIPU_API_KEY"):
        value = os.getenv(name)
        if value:
            return value.strip()
    keychain_value = _get_keychain_password()
    if keychain_value:
        return keychain_value
    return None


def build_zhipu_request(api_key: str, model: str, messages: list[dict], max_tokens: int, temperature: float) -> urllib.request.Request:
    """One Zhipu chat-completion request, shared by the chat and insight paths.

    Deliberately carries no timeout: the two callers allow different budgets (45s for chat, 30s for
    an insight) and apply them at `urlopen`, along with their own retry policies.
    """
    return urllib.request.Request(
        ZHIPU_API_URL,
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


def zhipu_key_configured() -> bool:
    return bool(get_zhipu_api_key())


def replay_enabled() -> bool:
    """True when demo replay mode is on, so AI surfaces serve a recorded response.

    Checks Streamlit secrets before the environment, the same precedence as
    `get_zhipu_api_key`. Hosted Streamlit has a secrets editor but no environment-variable
    field, and while Streamlit promotes top-level secrets into `os.environ`, it does so
    lazily inside its own secrets parse -- which has not necessarily run when a replay
    check fires, because these checks deliberately precede the key lookup that would
    trigger it. Reading the secret directly removes that ordering dependency.

    Resolved on every call rather than frozen into a module constant like the flags at the
    top of this module. A constant is captured at first import, which would make the flag
    unsettable from a test that imports this module before setting it -- the same
    frozen-default failure mode as the database-path default previously fixed in
    insights.py. Replay is demo-only and takes precedence over a configured API key.
    """
    value = streamlit_secret("AI_REPLAY") or os.getenv("AI_REPLAY", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def store_zhipu_api_key(api_key: str) -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "Secure local key storage is only implemented for macOS Keychain. Use ZAI_API_KEY or Streamlit secrets on this platform."
    api_key = api_key.strip()
    if not api_key:
        return False, "API key cannot be blank."
    try:
        subprocess.run(
            [
                "security",
                "add-generic-password",
                "-U",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                KEYCHAIN_ACCOUNT,
                "-w",
                api_key,
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
    except subprocess.CalledProcessError as exc:
        return False, f"Could not save API key to Keychain: {exc.stderr.strip() or exc}"
    except Exception as exc:
        return False, f"Could not save API key to Keychain: {exc}"
    return True, "Zhipu AI API key saved to macOS Keychain."
