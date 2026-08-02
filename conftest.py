"""Pytest configuration and safety guards for the PHR test suite.

This file lives at the repository root for two reasons:

1. It puts the repo root on ``sys.path``, so ``import app`` / ``import db`` resolve
   under a bare ``pytest`` invocation, not only ``python -m pytest``.
2. It installs the autouse guards below, which enforce the ``tests/AGENTS.md`` rule
   that the suite must never read or write the real ``data/phr.db``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import db

# Anchored to db.py's own DATA_DIR rather than recomputed from this file's location, so the
# guard always tracks whatever the application considers the real data directory.
REAL_DATA_DIR = db.DATA_DIR.resolve()


def _is_real_data_path(database: object) -> bool:
    """Return True if ``database`` points inside the repository's real data directory."""
    if not isinstance(database, (str, Path)):
        return False
    text = str(database)
    if text == ":memory:" or text.startswith("file::memory:"):
        return False
    try:
        resolved = Path(text).resolve()
    except (OSError, ValueError):  # pragma: no cover - defensive
        return False
    try:
        resolved.relative_to(REAL_DATA_DIR)
    except ValueError:
        return False
    return True


@pytest.fixture(autouse=True)
def guard_real_database(tmp_path, monkeypatch, request):
    """Point every test at a temporary database and fail loudly on real-DB access.

    ``db.DB_PATH`` is redirected so that any helper reaching for the module-level
    default lands in ``tmp_path``. Every ``db_path`` parameter now defaults to
    ``None`` rather than to ``DB_PATH``, so this patch is actually honoured -- an
    import-time default would have frozen the real path into the function object
    and ignored it silently. Where the ``None`` resolves differs by layer: caller
    modules resolve in the function body, while ``db.py`` forwards it down to
    ``db._resolve_db_path`` at the two places that open the file.

    The ``sqlite3.connect`` wrapper is the backstop that does not depend on that
    discipline holding: it catches reads as well as writes whatever the call site's
    binding, and it names the offending test instead of surfacing one anonymous
    failure at the end of the session.
    """
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "phr.db")

    real_connect = sqlite3.connect

    def guarded_connect(database, *args, **kwargs):
        if _is_real_data_path(database):
            raise AssertionError(
                f"{request.node.nodeid} attempted to open the real database at "
                f"{database!r}. Tests must use tmp_path (see tests/AGENTS.md)."
            )
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)


@pytest.fixture(scope="session", autouse=True)
def real_data_dir_untouched():
    """Fail the session if the suite conjured a ``data/`` directory that did not exist.

    Existence is snapshotted rather than asserted outright: a real checkout legitimately
    has ``data/phr.db`` sitting there, so demanding the directory be absent would fail
    every run on a developer machine. Per-test access to it is caught by
    ``guard_real_database`` above.
    """
    existed = REAL_DATA_DIR.exists()
    yield
    if not existed and REAL_DATA_DIR.exists():
        raise AssertionError(
            f"The test suite created {REAL_DATA_DIR}. Tests must use temporary "
            "database paths (see tests/AGENTS.md)."
        )
