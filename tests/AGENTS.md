# Test-Suite Instructions

These instructions supplement the repository-root `AGENTS.md` when working inside `tests/`.

- Tests must be deterministic, local, and independent of execution order.
- Use `tmp_path` or an equivalent temporary database for all persistence tests.
- Never read or write `data/phr.db`, `.streamlit/secrets.toml`, macOS Keychain values, or real exports.
- Use fictional patient data only.
- For profile-scoped features, create at least two profiles and assert that the non-selected profile is
  absent from results, exports, summaries, and AI context.
- Mock all provider/network boundaries; do not make real Zhipu/BigModel calls.
- Patch sleep/retry behavior so tests do not actually wait.
- Assert behavior and safety boundaries, not incidental implementation details.
- Add regression tests near related coverage in `tests/test_basic.py` unless a focused new test module
  materially improves organization.
- Do not weaken existing assertions or delete coverage to make new code pass.
- Prefer focused service/pure-function tests over brittle Streamlit rendering tests.
