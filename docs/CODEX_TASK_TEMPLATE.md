# Codex Task Template

Copy this into a new Codex thread and remove sections that do not apply.

```text
Task:
[One concrete feature, bug, refactor, or review.]

User-visible goal:
[What should be observably different when complete?]

Acceptance criteria:
- [Objective criterion 1]
- [Objective criterion 2]
- [Required error/edge behavior]
- [Required tests]

In scope:
- [Modules, pages, or record types]

Out of scope:
- [Explicitly excluded redesigns or adjacent features]

Critical invariants:
- Preserve selected-person isolation.
- Do not inspect or modify data/phr.db.
- Do not expose secrets or make real AI-provider calls in tests.
- Preserve non-diagnostic medical-safety language.
[Add task-specific invariants.]

Delegation:
- Use explorer only if the execution path is not already clear.
- Use implementer only for a bounded component with a fixed interface.
- Use test_runner for noisy verification output.
- Use reviewer for a meaningful final diff.
- Use privacy_safety_reviewer only if this touches profile isolation, exports, security, AI health
  context, medical output, FHIR patient attachment, or destructive database behavior.

Verification:
- Run the narrowest relevant tests during implementation.
- Run ./scripts/verify.sh once after the change is stable.
- Report commands and actual results.

Completion report:
- What changed
- Files changed
- Tests/checks run
- Assumptions and limitations
- Migration or manual verification steps
```

## Body-map task addition

For a body-map part, append:

```text
Read docs/body_map_prd.md only for Part [X] and update
docs/body_map_implementation_notes.md using its required section format.
Do not implement later parts unless required to keep the current part testable.
```
