#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  PYTHON_BIN="python"
fi

printf 'Using Python: %s\n' "$PYTHON_BIN"

# Compile project Python without descending into private/generated directories.
"$PYTHON_BIN" -m compileall -q \
  -x '(^|/)(\.venv|\.git|\.pytest_cache|data)(/|$)' \
  .

# Forward optional arguments so Codex can use focused selections:
#   ./scripts/verify.sh tests/test_basic.py -k profile
"$PYTHON_BIN" -m pytest -q "$@"
