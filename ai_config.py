from __future__ import annotations

import os
import subprocess
import sys

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
    deduped = []
    for model in candidates:
        if model not in deduped:
            deduped.append(model)
    return deduped


def _get_streamlit_secret(name: str) -> str | None:
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
        value = _get_streamlit_secret(name)
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


def zhipu_key_configured() -> bool:
    return bool(get_zhipu_api_key())


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
