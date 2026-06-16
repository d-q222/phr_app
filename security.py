from __future__ import annotations

import base64
import hashlib
import hmac
import os
from pathlib import Path

try:
    import streamlit as st
except ImportError:  # pragma: no cover - tests can run without Streamlit imported.
    st = None


ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    salt_text = base64.b64encode(salt).decode("ascii")
    digest_text = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${ITERATIONS}${salt_text}${digest_text}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_text)
        expected = base64.b64decode(digest_text)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations_text))
    except Exception:
        return False
    return hmac.compare_digest(actual, expected)


def _db_scope(db_path: Path | str | None = None) -> str:
    if db_path is None:
        return "default"
    return hashlib.sha1(str(db_path).encode("utf-8")).hexdigest()[:12]


def _unlocked_key(person_id: int, db_path: Path | str | None = None) -> str:
    return f"profile_unlocked_{_db_scope(db_path)}_{person_id}"


def is_profile_unlocked(person_id: int, db_path: Path | str | None = None) -> bool:
    if st is None:
        return False
    return bool(st.session_state.get(_unlocked_key(person_id, db_path), False))


def unlock_profile(person_id: int, db_path: Path | str | None = None) -> None:
    if st is not None:
        st.session_state[_unlocked_key(person_id, db_path)] = True


def lock_profile(person_id: int, db_path: Path | str | None = None) -> None:
    if st is not None:
        st.session_state[_unlocked_key(person_id, db_path)] = False


def health_data_visible(person: dict | None, unlocked: bool | None = None, db_path: Path | str | None = None) -> bool:
    if not person:
        return False
    if not person.get("profile_password_enabled"):
        return True
    if unlocked is not None:
        return unlocked
    return is_profile_unlocked(int(person["id"]), db_path=db_path)
