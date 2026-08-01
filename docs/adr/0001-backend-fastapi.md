# ADR-0001 — Backend framework: FastAPI

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decider:** Daniel
- **Change class:** Architectural (`PHR_LEARNING_PROTOCOL_2026-07-28.md:122-148`)
- **Supersedes:** the "Backend framework" entry under *Unresolved architecture choices*, `PHR_PROJECT_SOURCE_OF_TRUTH_2026-07-28.md:1249`

## Context

The migration objective is to move a Streamlit + SQLite prototype to a maintainable full-stack system
through verified vertical slices, preserving current behavior. Step 3 of that plan is a walking
skeleton along `browser → component → API client → route → service → repository → database`, which
cannot be scaffolded until the backend framework is chosen.

The decisive constraint is how much existing code survives. Measured at commit `2e8261e`:

| Module | Lines | Imports Streamlit? | Direct `db.*` calls |
|---|---|---|---|
| `fhir.py` | 711 | no | 1 |
| `insights.py` | 579 | no | 0 |
| `db.py` | 343 | no | — |
| `services.py` | 325 | no | 10 |
| `body_map_services.py` | 204 | no | 0 |
| `body_map_summary.py` | 196 | no | 0 |
| `imports_exports.py` | 192 | no | 2 |
| `body_map_config.py` | 393 | no | 0 |
| `validation.py` | 126 | no | 0 |
| `models.py` | 35 | no | 0 |

That is roughly **2,300 lines that are already framework-free**. `fhir.py` alone — bidirectional FHIR
R4/R5 Bundle translation with 40+ resource builders and parsers — would take weeks to reproduce and is
the substrate for the entire interoperability story (ADR-0004). `validation.py` is already shared by the
UI, CSV import, backup restore, and FHIR import, so it is stack-independent by construction.

## Options considered

**A. FastAPI (Python).** Existing service, repository, validation, FHIR, and analytics code ports by
changing signatures — principally replacing the manually threaded `db_path` parameter with injected
session scope. Native async, OpenAPI generation, and Pydantic models that can serve as both request
validation and response schemas.

**B. Django + DRF (Python).** Same reuse of pure modules, plus a mature admin, auth system, and ORM with
migrations included. Cost: Django's ORM and app structure want to own the data layer, so `db.py` and much
of `services.py` would be rewritten to Django idioms rather than ported. Heavier than a local-first
single-user app needs, and the built-in auth assumes a server-side multi-user model that ADR-0004 does
not commit to.

**C. Node/TypeScript backend.** One language across the stack, and the frontend is TypeScript regardless.
Cost: every line in the table above is discarded and rewritten, including `fhir.py`. Rejected on cost
alone; no benefit offered outweighs re-implementing FHIR translation and its round-trip tests.

**D. Keep Streamlit.** Rejected upstream — `PHR_PROJECT_SOURCE_OF_TRUTH_2026-07-28.md:1170-1179` records
the decision to move away, with body-map interaction as the concrete pressure. See ADR-0002.

## Decision

**FastAPI.**

The argument is code reuse, and it is quantified above rather than asserted. Django's additional
machinery is not free here: its strongest features (admin, session auth, ORM) are either unnecessary for
a local-first app or actively conflict with an undecided deployment model. FastAPI adds the HTTP layer
this system lacks without claiming the layers it already has.

Pydantic also gives a concrete answer to a real wart: type coercion currently lives in the UI
(`app.clean_payload`) while validation lives in `validation.py`. How those two combine is a genuine fork
and is resolved in `docs/target_architecture.md`, not here.

## Consequences

- The `db_path` parameter threaded through nearly every signature becomes injected session/connection
  scope. This is the largest mechanical change in the migration.
- `services.py` grows explicit person-scoped contracts. Already begun: `update_item`/`delete_item` take
  keyword-only `person_id` and `record_id` as of `2e8261e`.
- `security.py` is **replaced, not ported**. PBKDF2 hashing survives; `st.session_state` unlock state does
  not. See `docs/domain_invariants.md` §8.
- `db.RecordNotFound` maps to a single 404 — never a 403, which would leak record existence across profiles.
- Python version floor: the venv was upgraded 3.9.6 → 3.12.13 on 2026-08-01 specifically to unblock
  modern FastAPI/Pydantic annotations.
- Requires a persistence layer decision — deferred to ADR-0003, which is the remaining blocker on the
  walking skeleton.

## Reversibility

Moderate. The pure modules stay portable regardless of framework, so switching later means rewriting the
route layer and dependency wiring but not the domain. Lock-in grows if FastAPI-specific constructs
(`Depends`, background tasks) spread into service code — keep them at the route boundary.

## What would falsify this

- If FHIR translation, analytics, and validation turn out to need substantial rewriting anyway, the
  reuse argument — the whole basis of this decision — collapses, and option C deserves reconsideration.
- If the product moves to a server-rendered model where a separate API layer is overhead rather than
  structure (see ADR-0002's rejected option B).
