# PHR AI-Native Building and Learning Protocol

Governs how Daniel and AI agents build the PHR while migrating from Streamlit to a full-stack system.

## Objective

Ship working software quickly with AI-generated implementation as the default, while Daniel develops the ability to:

- choose the right problem and scope;
- design system boundaries and contracts;
- direct coding agents precisely;
- review material changes;
- verify behavior with tests and evidence;
- diagnose failures;
- protect patient isolation, provenance, privacy, and safety;
- explain the system at the architectural level needed to make decisions.

The goal is not to build the application without AI. The goal is to become an effective AI-native builder who can control, verify, and improve a complex system.

---

## Post-YC operating principle

Code generation is abundant. Manual typing is no longer the default bottleneck.

The scarce skills are:

- product judgment;
- decomposition;
- systems thinking;
- architecture;
- data modeling;
- interface and contract design;
- evaluation;
- debugging;
- security and safety reasoning;
- prioritization;
- user validation.

Use agents for implementation unless manual coding is clearly faster for a small probe, correction, or debugging experiment. Do not force manual coding to prove ownership.

Ownership means Daniel can state what the system should do, identify its important boundaries and risks, evaluate the implementation evidence, direct changes, and diagnose consequential failures.

---

## Non-negotiables

- Build small vertical slices, not large horizontal rewrites.
- Keep Streamlit working until a replacement slice is verified.
- Review every material diff before merge or commit.
- Do not require line-by-line understanding of routine boilerplate or generated code.
- Do require behavioral and architectural understanding of critical or unfamiliar logic.
- Do not add a dependency, framework, service, or abstraction without a concrete need and trade-off explanation.
- State assumptions. Do not modify unrelated files.
- Tests, observability, and necessary documentation are part of the feature.
- Running is not done. Done means verified against acceptance criteria and invariants.

---

## PHR invariants

Never violate these without explicit sign-off:

- One person's data never appears in another person's view or processing path.
- Imports retain raw data, source, and provenance.
- Existing records are never silently changed, dropped, merged, or reinterpreted.
- Clinician diagnoses, user concerns, system signals, and AI explanations remain distinct.
- AI output remains explanatory and non-diagnostic.
- External AI receives only explicitly approved, minimized data with unnecessary identifiers removed.
- Local processing is preferred for sensitive records once viable.
- There is no silent local-to-external fallback.
- Rule-based behavior continues when AI is unavailable.
- Critical operations are testable and auditable.
- Experimental work does not mutate the real database without a migration and rollback plan.

---

## Default division of labor

### Daniel owns

- product goal and user workflow;
- architecture and subsystem boundaries;
- domain model and data contracts;
- acceptance criteria;
- patient isolation and authorization rules;
- provenance, privacy, and safety policy;
- significant technology choices;
- evaluation strategy;
- final review and prioritization.

### AI agents may own execution

- scaffolding;
- routine implementation;
- CRUD and forms;
- API wiring;
- test generation;
- mechanical refactoring;
- styling;
- generated types and schemas;
- documentation drafts;
- repository searches;
- repetitive migrations following an approved pattern;
- initial debugging experiments.

### Shared responsibility

- unfamiliar algorithms;
- analytics logic;
- schema migrations;
- authentication and authorization;
- external AI routing;
- import reconciliation;
- security-sensitive code;
- major architecture changes.

Agents may generate these, but Daniel must review the design, risks, and evidence before acceptance.

---

## Change classes

### Routine

An established pattern with low blast radius, such as repetitive CRUD, styling, generated types, or a mechanical refactor.

The agent may implement directly after stating scope and assumptions.

### Architectural

A new subsystem, dependency, framework pattern, data contract, state model, or cross-cutting change.

Require a compact change brief before implementation.

### Critical

Authentication, authorization, patient isolation, provenance, consent, deletion, record-altering migration, privacy, external AI routing, secure sharing, or safety behavior.

Require:

- explicit design and threat assumptions;
- acceptance and rejection criteria;
- tests for failure and isolation;
- rollback strategy;
- full diff review;
- documented residual risk.

---

## Agent modes

### Researcher

Inspect the repository and relevant sources. Return evidence, uncertainties, and contradictions. Do not propose implementation as fact.

### Architect

Define behavior, boundaries, contracts, data flow, state ownership, alternatives, risks, acceptance criteria, and tests. Produce a decision-ready design, not a giant roadmap.

### Implementer

Execute the approved or clearly scoped change. Avoid unrelated cleanup. Report files changed, tests run, assumptions, and unresolved risk.

### Reviewer

Review the full diff and trace the call path. Check state, validation, persistence, error propagation, isolation, provenance, security, framework behavior, missing tests, and unnecessary complexity.

### Debugger

Use exact errors, logs, and reproduction steps. Rank hypotheses, run the smallest isolating experiment, fix the root cause, and add a regression test. Do not regenerate whole modules to fix a local failure.

### Evaluator

Test the feature against user-visible acceptance criteria, failure behavior, privacy and safety invariants, and product usefulness. Recommend accept, revise, or reject.

---

## Build order

1. Document current system and target architecture.
2. Establish the full-stack walking skeleton with one startup command, logging, and tests.
3. Implement patient selection and isolation.
4. Migrate one record type end to end.
5. Delegate the second record type more fully to validate that the architecture and agent instructions generalize.
6. Migrate import and validation pipelines.
7. Migrate body-map state and filtering.
8. Add deterministic trends and analytics.
9. Add AI provider abstraction and privacy-aware routing.
10. Add adaptive or condition-aware capabilities only after the foundations are stable.

The walking skeleton path is:

`browser → component → API client → route → service → repository → database → response → state → UI`

---

## Change brief for architectural or critical work

Before implementation, state:

- user-visible behavior;
- acceptance criteria;
- files and interfaces affected;
- data flow and state ownership;
- API or schema changes;
- invariants at risk;
- validation and error behavior;
- tests and observability;
- migration and rollback;
- assumptions and unresolved decisions.

Routine established work does not require a lengthy approval cycle.

---

## Verification gates

A slice is accepted when Daniel can clear the relevant gates. These are not manual-coding tests.

1. **Specify**: State the intended behavior, contracts, edge cases, and invariants.
2. **Trace**: Explain the important call path, state ownership, validation, persistence, and failure propagation.
3. **Verify**: Point to test, log, or manual evidence that the behavior and isolation rules hold.
4. **Direct**: Give an agent a precise change request and evaluate whether the resulting diff is correct.
5. **Diagnose**: Use evidence to identify the failing layer and choose an isolating experiment.

Not every routine change requires all five gates. Critical changes do.

Reconstructing the implementation from memory is not required. Writing code by hand is not required.

---

## Diff and commit checklist

- Inspect the full diff.
- List changed files and explain their role.
- Trace the behavior at the appropriate architectural level.
- Run automated tests.
- Run manual happy-path, failure-path, and person-isolation checks where applicable.
- Confirm no unapproved dependency or abstraction was introduced.
- Confirm original data and provenance are preserved.
- Check logs and error behavior.
- Remove unnecessary complexity.
- Update required documentation.
- Record residual risk.
- Commit with a behavior-focused message.

---

## Documentation

Maintain:

- `docs/current_system.md`
- `docs/target_architecture.md`
- `docs/migration_map.md`
- `docs/domain_invariants.md`
- `docs/architecture/<subsystem>.md` (planned — created per subsystem as each is
  documented; no subsystem notes exist yet)
- architecture decision records for consequential choices (in `docs/adr/`)

AI may draft documentation from repository evidence. Daniel must verify that it matches the actual system and decisions. Daniel does not need to write the first draft manually.

Each subsystem note should cover purpose, user behavior, call path, files, schemas, state ownership, invariants, validation, failure modes, tests, security and privacy, trade-offs, limitations, and safe modification guidance.

---

## Understanding tiers

- **Tier 1, must own:** architecture, patient isolation, privacy and safety boundaries, provenance, domain contracts, critical data flows, migrations, and AI routing.
- **Tier 2, must navigate and evaluate:** standard CRUD, route-service-repository patterns, frontend state, API clients, forms, and routine configuration.
- **Tier 3, agent or lookup is sufficient:** build-tool internals, generated files, dependency internals, detailed CSS, boilerplate, and rare deployment settings.

---

## Session log

Use after meaningful sessions:

```text
Slice / Change class / Agent mode:
User-visible result:
Architecture or contracts decided:
AI generated:
Files changed:
Evidence and tests:
Important call path:
Invariants checked:
What I can now direct or diagnose:
Residual risks:
Next smallest validated step:
```

---

## Time allocation

Default allocation:

- 25% product definition, architecture, and acceptance criteria;
- 50% agent implementation and iteration;
- 20% review, testing, debugging, and evaluation;
- 5% durable documentation.

Adjust by slice. Never cut safety, isolation testing, or review merely to preserve visible progress.
