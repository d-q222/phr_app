# Claude Instructions — Local-First Family PHR

`AGENTS.md` in this repository is the full instruction set. **Read it before any non-trivial
change.** This file carries only the invariants that hold even for a one-line edit, plus pointers
to the sections that own the detail.

## Product boundary

Local-first Streamlit personal health record prototype backed by SQLite. It is not a production
health platform, medical device, diagnostic system, emergency service, or HIPAA-ready deployment.
Preserve that boundary in code, UI text, documentation, tests, and AI prompts.

## Invariants that are never traded away

### Profile isolation

- Scope every health-data read, write, summary, export, AI context, and body-map query to the
  selected `person_id`, unless the feature explicitly and safely supports an all-profile view.
- Never fall back to an implicit or first profile when a patient reference is unresolved.
- Locked profiles must not leak health data through tables, exports, summaries, settings, AI
  context, cached/session state, error messages, or helper functions.
- Preserve database-path scoping so demo/session databases cannot share state with the real DB.

### Persistence

- Parameterized SQL values only; use the existing table/column allowlists.
- Preserve `PRAGMA foreign_keys = ON`.
- Never use `INSERT OR REPLACE` for parent rows — it can delete and recreate records.
- `data/phr.db` is private user data. Do not inspect, modify, delete, copy, or commit it.
- Tests use temporary database paths and fictional data.

### Secrets and external services

- Never read or print `.streamlit/secrets.toml`, API keys, tokens, or Keychain values.
- No real AI-provider calls in tests — mock at the `urllib`/provider boundary.
- Preserve explicit user acknowledgement before selected health context is sent to a provider,
  and send only the minimum context the operation requires.

### Medical safety

- Do not diagnose, prescribe, recommend starting/stopping/changing medication, estimate prognosis,
  or suggest that urgent symptoms can be managed at home.
- Do not treat a raw lab value as abnormal unless the source record carries an abnormal flag or an
  existing approved deterministic rule supplies that interpretation.
- Preserve historical source-flagged records; a newer unflagged record does not hide them.
- Retain the existing medical disclaimer and urgent-care escalation behavior.
- Any new AI output path needs a rule-based or safe failure mode with the same constraints as
  `insights.py` and `ai_chat.py`.

Open P1 safety gaps are tracked in `AGENTS.md` §5 — check it before planning related work.

## Module ownership

`app.py` Streamlit entrypoint and UI only · `db.py` SQLite connections, allowlisted CRUD, schema ·
`services.py` profile-scoped business queries · `validation.py` · `models.py` · `security.py` ·
`imports_exports.py` · `fhir.py` · `insights.py` · `ai_chat.py` · `ai_config.py` ·
`body_map_{config,services,summary,ui,ai}.py`

Do not make `app.py` the implementation home for new business logic. Full table: `AGENTS.md` §3.

## Before writing new code

Read the relevant execution path first — be lazy about the solution, never about reading. Then stop
at the first step that satisfies the requirement: (1) does it need to exist at all, (2) does the
codebase already do it, (3) does the stdlib or an installed dependency cover it, (4) is it a
one-line change, (5) minimum new code in the module that already owns that responsibility.

Do not add a class, module, config layer, dependency, table, or "future override" hook until a
second concrete caller exists. This trims scope, never correctness — safety, validation, and
profile isolation are not what gets minimized. Counterweight signals for when structure *has*
earned its place: `AGENTS.md` §6.2.

## Verification

```bash
./scripts/verify.sh
```

Fallback: `.venv/bin/python -m pytest -q`. Run focused tests during iteration, the full script once
the change is stable.

Add a regression test for every bug fix. Test selected-profile isolation against a second profile
for any profile-scoped feature. Test locked-profile behavior for exports, settings, and AI-context
changes. Never weaken an existing assertion to make a change pass. Full policy: `AGENTS.md` §10.

## Delegation

`AGENTS.md` §7 is the routing policy and applies here: the main agent owns requirement
interpretation, architecture, cross-module changes, security decisions, and final verification.
Delegate only bounded, independently verifiable work. Prefer zero subagents for small tasks, at most
three unless the work is genuinely independent, and never let subagents spawn subagents. §7 also
names which agent owns which kind of change.

## Further detail in AGENTS.md

§2 context discipline · §6 work process · §8 token and tool efficiency · §9 coding standards
