# Codex Workflow for the PHR Repository

## Purpose

This document explains how to use the repository-level `AGENTS.md` and project-scoped Codex agents
without wasting high-capability model tokens on deterministic or read-heavy work.

## Recommended directory layout

```text
phr_app/
├── AGENTS.md
├── README.md
├── app.py
├── db.py
├── services.py
├── validation.py
├── security.py
├── models.py
├── imports_exports.py
├── fhir.py
├── insights.py
├── ai_chat.py
├── ai_config.py
├── schema.sql
├── requirements.txt
├── sample_test_data.json
├── .codex/
│   ├── config.toml
│   └── agents/
│       ├── explorer.toml
│       ├── test_runner.toml
│       ├── mechanical_editor.toml
│       ├── implementer.toml
│       ├── reviewer.toml
│       └── privacy_safety_reviewer.toml
├── assets/
│   └── body_map_front.svg              # created during body-map Part 4
├── docs/
│   ├── CODEBASE_SWEEP.md
│   ├── body_map_prd.md
│   ├── body_map_implementation_notes.md
│   ├── CODEX_WORKFLOW.md
│   └── CODEX_TASK_TEMPLATE.md
├── scripts/
│   └── verify.sh
├── tests/
│   ├── AGENTS.md
│   └── test_basic.py
└── data/
    └── phr.db                           # private local data; never commit or inspect casually
```

## Installation

1. Copy the package contents into the repository root, preserving hidden directories.
2. Move the existing `CODEBASE_SWEEP.md` and `body_map_prd.md` into `docs/`, or use the copies in this
   package.
3. Keep the source files in the repository root; this setup does not require a source-layout refactor.
4. Ensure `scripts/verify.sh` is executable:

   ```bash
   chmod +x scripts/verify.sh
   ```

5. Open the repository in Codex and mark the project as trusted so `.codex/config.toml` and the custom
   agents load.
6. Restart the Codex session after adding or changing `AGENTS.md` or `.codex/` configuration.

## Main-thread model choice

Do not pin one main model for every task.

- Use **GPT-5.6 Terra, medium** for ordinary, well-understood feature work and bug fixes.
- Use **GPT-5.6 Sol, medium** for ambiguous requirements, architecture, multi-module changes, schema
  strategy, difficult debugging, or polished final integration.
- Increase Sol to high only when the problem actually requires deeper trade-off analysis.
- Do not use Ultra automatically. The repository already defines narrow subagents and most tasks do
  not benefit from broad fan-out.

The project configuration caps open agent threads at four and prevents nested delegation.

## Agent routing

| Task | Agent | Model | Typical output |
|---|---|---|---|
| Locate symbols, map execution path | `explorer` | Luna low | Paths, symbols, concise data flow |
| Run focused/full checks | `test_runner` | Luna low | Root-cause-grouped failures |
| Exact rename/boilerplate/repetitive edit | `mechanical_editor` | Luna low | Narrow diff and focused check |
| Bounded module with fixed interface | `implementer` | Terra medium | Isolated implementation plus tests |
| General final diff review | `reviewer` | Terra high | Material findings only |
| Privacy/medical/data-integrity review | `privacy_safety_reviewer` | Sol high | High-assurance findings only |

Do not spawn an agent merely because one exists. A small fix is normally cheaper in one thread.

## Efficient feature workflow

1. Start a new Codex thread for one feature or bug.
2. Provide acceptance criteria using `docs/CODEX_TASK_TEMPLATE.md`.
3. Ask the main agent to use `explorer` only when the relevant path is not already known.
4. Let the main agent decide architecture and integration.
5. Delegate a module to `implementer` only after its interface is fixed.
6. Use `test_runner` for noisy logs or a stable final run; use direct shell tools for tiny checks.
7. Use `reviewer` only for meaningful diffs.
8. Add `privacy_safety_reviewer` when the change touches the high-risk surfaces named above.
9. Have the main agent resolve findings and report actual test results.

## Example prompt: ordinary bug fix

```text
Fix the reminder-date bug described below.

Acceptance criteria:
- Invalid imported dates are ignored rather than compared or crashed on.
- Valid overdue and due-soon behavior is unchanged.
- Add a regression test.
- Do not refactor unrelated reminder UI.

Use the explorer only if the relevant path is unclear. Run focused tests first and the full verification
script once at the end. Review the final diff yourself.
```

## Example prompt: high-risk export change

```text
Implement selected-profile JSON export only.

Acceptance criteria:
- No records from any other person_id are included.
- Locked profiles cannot be included through an all-profile fallback.
- Existing restore behavior remains compatible.
- Add a two-profile regression test and a locked-profile test.

Have the explorer map export and lock-gating paths. After implementation, use the reviewer and the
privacy_safety_reviewer. The main agent owns integration and final verification.
```

## Body-map implementation

Implement the PRD in separate Codex threads, one numbered part per thread:

1. Mapping foundation.
2. Profile-scoped normalized retrieval.
3. Conservative current/historical summary.
4. Streamlit/SVG UI.
5. AI explanation buttons.

At the beginning of each body-map task, direct Codex to read only:

- `AGENTS.md`
- `docs/body_map_prd.md`, focusing on the relevant part
- `docs/body_map_implementation_notes.md`
- directly affected source files/tests

At completion, require the implementation-notes entry, focused tests, full verification, and a concise
migration/manual-test report.

## What not to automate with models

Use the shell or existing tools for file discovery, exact text search, compilation, tests, and standard
formatting. Do not ask an LLM to manually inspect every file for something a deterministic command can
find. Do not have multiple agents independently scan the same codebase.
