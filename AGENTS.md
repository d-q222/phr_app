# Codex Repository Instructions — Local-First Family PHR

## 1. Product boundary

This repository is a local-first Streamlit personal health record prototype backed by SQLite.
It organizes family health information; it is not a production health platform, medical device,
diagnostic system, emergency service, or HIPAA-ready deployment.

Preserve these boundaries in code, UI text, documentation, tests, and AI prompts.

## 2. Read only the context needed

Before changing code, read:

1. `README.md` for product behavior and operating instructions.
2. `docs/CODEBASE_SWEEP.md` for the current architecture, known risks, and prior fixes.
3. The directly affected source files and tests.
4. `docs/body_map_prd.md` only for body-map work.
5. `docs/body_map_implementation_notes.md` only when continuing body-map implementation.

Do not load the entire body-map PRD for unrelated tasks. Do not repeatedly rescan the whole
repository after the relevant execution path has been identified.

## 3. Architecture and ownership

Keep responsibilities separated:

- `app.py`: Streamlit entrypoint, navigation, page composition, and UI integration.
- `db.py`: low-level SQLite connections, allowlisted CRUD, transactions, schema initialization,
  backup primitives, and database-path handling.
- `services.py`: profile-scoped business queries, summaries, filtering, and application services.
- `validation.py`: input normalization and validation before persistence.
- `models.py`: shared controlled option lists and simple domain constants.
- `security.py`: local profile-password hashing and session unlock state.
- `imports_exports.py`: CSV and JSON backup import/export orchestration.
- `fhir.py`: local-record/FHIR conversion and validation boundaries.
- `insights.py`: rule-based and AI-assisted health insight generation with safety constraints.
- `ai_chat.py`: selected-profile AI chat context, provider calls, errors, and Streamlit chat UI.
- `ai_config.py`: AI provider configuration, model candidates, token/context limits, and secrets.

For the body-map feature, prefer these focused modules unless the codebase has already evolved:

- `body_map_config.py`: canonical body parts, systems, relevance types, and deterministic mappings.
- `body_map_services.py`: profile-scoped retrieval and normalized body-area records.
- `body_map_summary.py`: conservative current/historical status logic.
- `body_map_ui.py`: Streamlit body-map rendering and interaction.
- `body_map_ai.py`: body-map-specific AI prompts and provider integration.
- `assets/body_map_front.svg`: replaceable selector asset only; no medical mapping logic.

Do not turn `app.py` into the implementation home for new business logic.

## 4. Non-negotiable data invariants

### Profile isolation

- Every health-data read, write, summary, export, AI context, and body-map query must be scoped to
  the selected `person_id` unless the feature explicitly and safely supports an all-profile view.
- Never use an implicit first profile or fallback profile when a patient reference is unresolved.
- Preserve database-path scoping so demo/session databases cannot share state with the real DB.
- Locked profiles must not leak health data through tables, exports, summaries, settings, AI context,
  cached/session state, error messages, or helper functions.

### Persistence

- Use parameterized SQL values and existing table/column allowlists.
- Preserve `PRAGMA foreign_keys = ON`.
- Do not use SQLite `INSERT OR REPLACE` for parent rows; it can delete and recreate records.
- Treat `data/phr.db` as private user data. Never inspect, modify, delete, copy, or commit it unless the
  user explicitly asks and the action is necessary.
- Tests must use temporary database paths and fictional data.
- Schema changes must be idempotent for existing databases and accompanied by regression tests.
- Do not add a dependency or persistent table when deterministic service-layer logic is sufficient.

### Secrets and external services

- Never read or print `.streamlit/secrets.toml`, API keys, tokens, Keychain values, or secret-bearing
  environment variables.
- Do not commit secrets, local databases, exported backups, or real health data.
- Do not make real AI-provider calls in tests. Mock `urllib`/provider boundaries.
- Preserve explicit user acknowledgement before selected health context is sent to an AI provider.
- Send only the minimum selected-profile context required for the requested operation.

## 5. Medical-safety invariants

- Do not diagnose, prescribe, recommend starting/stopping/changing medication or supplements,
  estimate prognosis, or suggest that urgent symptoms can be managed at home.
- Do not infer that a raw lab value is abnormal unless the source record provides an abnormal flag or
  an existing, explicitly approved deterministic rule supplies that interpretation.
- Prefer cautious language such as “source-flagged,” “may be worth discussing,” and “records show.”
- Preserve historical source-flagged records; do not hide them because a newer record is unflagged.
- Current status may prefer the latest record, but historical context must remain visible.
- Retain the existing medical disclaimer and urgent-care escalation behavior.
- Any new AI output path must have a rule-based or safe failure mode and must enforce the same safety
  constraints as `insights.py` and `ai_chat.py`.

## 6. Work process

For any non-trivial task:

1. Restate the concrete acceptance criteria internally.
2. Inspect the smallest relevant execution path.
3. Check existing tests and local conventions before designing new abstractions.
4. Produce a short implementation plan when multiple files or a schema are affected.
5. Implement the smallest coherent change.
6. Run focused tests first.
7. Run the full verification script once the change is stable.
8. Review the final diff for profile leakage, data loss, medical overclaiming, and unnecessary scope.
9. Update documentation only where behavior, setup, schema, or a PRD implementation log changed.

Do not ask the user for information that can be determined from the repository. Do not perform broad
cleanup, unrelated refactors, dependency upgrades, or formatting churn while implementing a feature.

## 7. Delegation and model-routing policy

The main agent owns requirement interpretation, architecture, cross-module changes, integration,
security decisions, schema strategy, and final verification.

Delegate only work that is bounded, independently verifiable, and cheaper than carrying its raw output
in the main context.

Use project agents as follows:

- `explorer`: read-only symbol/file lookup, execution-path tracing, and concise repository maps.
- `test_runner`: run existing checks and summarize failures by root cause; never edit source.
- `mechanical_editor`: exact repetitive transformations with explicit files and acceptance criteria.
- `implementer`: a bounded module or function whose interface and tests are already defined.
- `reviewer`: independent correctness/regression review of a meaningful completed diff.
- `privacy_safety_reviewer`: only for changes touching profile isolation, exports, security, AI health
  context, medical summaries, FHIR patient attachment, or destructive database behavior.

Delegation limits:

- Prefer zero subagents for small tasks.
- Prefer one explorer or one test runner for ordinary tasks.
- Use at most three subagents unless work is genuinely independent.
- Do not parallelize tightly coupled writes.
- Do not let subagents spawn subagents.
- Do not delegate the same question to multiple agents merely to create a “council.”
- Require concise findings, file paths/symbols, and unresolved uncertainties; do not return raw logs.
- The main agent must inspect material diffs and verify all consequential worker conclusions.

## 8. Token and tool efficiency

- Use deterministic tools before model reasoning: `rg`, `find`, Python/pytest, SQLite test fixtures,
  formatters, and static checks.
- Search for symbols and call sites before opening entire large files.
- Read targeted line ranges after search results identify relevant code.
- Reuse facts already established in the current task.
- Run the narrowest relevant test during iteration; do not run the full suite after every edit.
- Summarize test failures; do not paste complete logs unless the exact log is needed to diagnose.
- Do not generate boilerplate that an existing helper or local pattern already covers.
- Do not add an orchestration framework to this application merely to coordinate coding work.

## 9. Coding standards

- Target Python 3.11+.
- Preserve `from __future__ import annotations` in modules that already use it.
- Follow existing plain-function/module style; do not introduce classes or frameworks without a clear
  need.
- Add type hints to new public/service functions where practical.
- Add short docstrings to important service functions, especially body-map functions. State inputs,
  outputs, touched record types/tables, and assumptions.
- Keep pure transformation and summary logic separate from Streamlit rendering.
- Keep provider/network calls behind narrow functions that can be mocked.
- Validate at import/UI boundaries before persistence.
- Preserve stable ordering and explicit tie-breakers for “latest” calculations.
- Prefer clear code over compressed clever code.

## 10. Testing policy

Primary full check:

```bash
./scripts/verify.sh
```

Equivalent fallback:

```bash
.venv/bin/python -m pytest -q
```

During iteration, run focused tests, for example:

```bash
.venv/bin/python -m pytest -q tests/test_basic.py -k "profile or export"
```

Requirements:

- Add a regression test for every bug fix.
- Add service/pure-function tests for new behavior before relying on UI-only testing.
- Test selected-profile isolation and a second profile for any profile-scoped feature.
- Test locked-profile behavior for exports, settings, or AI-context changes.
- Test malformed, missing, duplicate, and unknown data where relevant.
- Mock all AI/network calls and avoid real sleeping in retry tests.
- For schema changes, test new database initialization and compatibility with an existing database.
- Do not weaken existing assertions to make a change pass.

If the full test suite cannot run because an expected file or dependency is absent, run all available
checks and report the exact limitation.

## 11. Body-map-specific rules

For body-map tasks, follow `docs/body_map_prd.md` and implement one numbered part at a time unless the
user explicitly requests otherwise.

Mandatory rules:

- Organ-first UI; body systems are internal mapping concepts.
- Use canonical IDs from the PRD.
- Store mappings in code/service logic, not in the SVG.
- Retrieval must be profile-scoped and normalize records across available record types.
- Use source flags; do not independently diagnose from raw values.
- Use only conservative status labels defined by the PRD unless a documented requirement changes.
- Keep old flagged records visible and separate current from historical context.
- Treat the SVG as replaceable.
- Update `docs/body_map_implementation_notes.md` after each completed part.
- Do not create `part1.py`, `part2.py`, or other process-named source files.

## 12. Documentation and completion report

Update `README.md` when setup, environment variables, supported behavior, safety boundaries, or user
operations change. Update `docs/CODEBASE_SWEEP.md` only for meaningful architecture/audit changes, not
for every small edit.

At completion, report:

1. What changed.
2. Files changed.
3. Tests/checks run and their results.
4. Assumptions or limitations.
5. Any migration or manual verification required.

Do not claim tests passed unless they were actually run successfully.
