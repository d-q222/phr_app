# Install This Codex Setup

Copy all contents of this package into the root of the PHR repository, preserving hidden files.

```bash
# Run from the extracted phr_codex_setup directory.
cp -R . /path/to/your/phr_app/
chmod +x /path/to/your/phr_app/scripts/verify.sh
```

Because `cp -R .` includes `.codex/`, do not use `cp -R *`, which skips hidden files.

The resulting root should contain:

```text
AGENTS.md
.codex/config.toml
.codex/agents/*.toml
docs/CODEBASE_SWEEP.md
docs/body_map_prd.md
docs/body_map_implementation_notes.md
docs/CODEX_WORKFLOW.md
docs/CODEX_TASK_TEMPLATE.md
scripts/verify.sh
tests/AGENTS.md
```

If `CODEBASE_SWEEP.md` or `body_map_prd.md` still exists at repository root after copying, remove the
duplicate root copy after confirming the version under `docs/` is correct. The source Python files stay
at repository root.

Open the repository in Codex, trust the project so project-scoped `.codex/` configuration loads, then
restart the Codex session. Use `docs/CODEX_WORKFLOW.md` for model selection and prompt examples.
