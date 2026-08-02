#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "${PHR_VERIFY_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PHR_VERIFY_PYTHON_BIN"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  PYTHON_BIN="python"
fi

printf 'Using Python: %s\n' "$PYTHON_BIN"

if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
  printf 'ERROR: Python 3.12+ is required. Recreate .venv with: python3.12 -m venv .venv\n' >&2
  exit 1
fi

# Lint gate (fatal): unused/dead code, import order, and the AGENTS.md §6.2 complexity
# signals (over-complex functions, too many args/statements). Pre-existing outliers are
# grandfathered with line-level `# noqa`; new violations fail verification.
# `set -e` above makes a non-zero ruff exit abort the script.
if ! "$PYTHON_BIN" -m ruff --version >/dev/null 2>&1; then
  printf 'ERROR: ruff is required for verification. Install with: %s -m pip install ruff\n' "$PYTHON_BIN" >&2
  exit 1
fi
"$PYTHON_BIN" -m ruff check .

# Compile project Python without descending into private/generated directories.
"$PYTHON_BIN" -m compileall -q \
  -x '(^|/)(\.venv|\.git|\.pytest_cache|data)(/|$)' \
  .

# Forward optional arguments so Codex can use focused selections:
#   ./scripts/verify.sh tests/test_basic.py -k profile
"$PYTHON_BIN" -m pytest -q "$@"
