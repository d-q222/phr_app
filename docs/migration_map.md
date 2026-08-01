# Migration Map

**Updated:** 2026-08-01, commit `bff5c38`. **Baseline:** 159 tests passing, Python 3.12.13.

How the Streamlit + SQLite prototype becomes the system in `docs/target_architecture.md`. The controlling
step list is `PHR_PROJECT_INSTRUCTIONS_OPTIMIZED_2026-07-28.md:19-27`.

> **Which list controls.** The instructions doc's **7-step** list governs. The protocol's 10-step "Build
> order" (`PHR_LEARNING_PROTOCOL_2026-07-28.md:179-190`) is offset by one — it has no separate audit step.
> The instructions doc ranks higher under its own *Authority and evidence* section.

---

## 1. Status

| # | Step | Status |
|---|---|---|
| 1 | Document the current system and target architecture | **Done** — 2026-08-01 |
| 2 | Audit malformed inputs, failure behavior, profile isolation | **Done** — `docs/CODEBASE_SWEEP.md` closed its P0–P3 findings; the write-path isolation gap it missed was closed in `2e8261e` |
| 3 | Establish a full-stack walking skeleton | **Next** — unblocked, all four ADRs decided |
| 4 | Migrate patient selection and isolation | Not started |
| 5 | Migrate one complete record workflow | Not started — candidate chosen, §4 |
| 6 | Generalize the pattern with increasing agent autonomy | Not started |
| 7 | Migrate imports, body-map state, deterministic analytics, AI routing | Not started |

Slice 1 also delivered two things outside the documentation scope: the Python 3.9.6 → 3.12.13 upgrade
(which unblocks FastAPI/Pydantic annotations) and the person-scoped write guard.

**Rule for every step below:** Streamlit keeps working until the replacement slice is verified
(`PHR_LEARNING_PROTOCOL:49`).

---

## 2. Module → layer mapping

| Today | Target layer | Disposition |
|---|---|---|
| `db.py` | repository | Rewritten as SQLAlchemy models + repositories |
| `services.py` | service | Ported; person-scoping made mandatory |
| `validation.py` | domain rules | Ported unchanged; Pydantic wraps it at the edge |
| `models.py` | ORM enums / `CHECK` constraints | Absorbed |
| `fhir.py` | service + routes | Ported — interop substrate, do not rewrite |
| `insights.py` | service (analytics) + provider adapter (transport) | Split |
| `ai_chat.py` | service + provider adapter + component | Split three ways |
| `ai_config.py` | provider adapter | Folded into the `LLMProvider` port |
| `imports_exports.py` | service + routes | Ported; stops reading `db.TABLES` |
| `body_map_*.py` | service + component | Services ported; UI rewritten |
| `security.py` | auth | **Replaced** — hashing survives, session model does not |
| `app.py` | routes + components | Split; `FIELD_CONFIGS` is the seam |
| `components/body_map/index.html` | React component | Retired |

---

## 3. Step 3 — walking skeleton

**Goal:** one trivial endpoint traversing the full path, with the persistence foundation correct.

1. Scaffold FastAPI + SQLAlchemy 2.0 + Alembic; React + TypeScript + Vite.
2. **ORM models with real types** — `Date`, `DateTime`, `Numeric`; `CHECK` constraints for the `models.py`
   vocabularies; `ON DELETE CASCADE` on all seven child relationships.
3. **Initial Alembic migration** representing today's schema, plus an `alembic stamp` path for existing
   `data/phr.db` files.
4. **Startup migration runner**: back up the user's file, migrate, and **surface** rows the typed columns
   reject rather than coercing them (`domain_invariants.md` §2). Define failure behavior for a migration
   that fails partway on a user's machine.
5. **Dual-engine CI** — the suite runs against SQLite and Postgres (ADR-0003).
6. Health-check endpoint through the full path; typed client generated from the OpenAPI schema.

**Sharp edges** (ADR-0003): SQLite needs `op.batch_alter_table` — plain `op.alter_column` works on Postgres
and fails on SQLite. Alembic autogenerate misses server defaults and some constraint changes; read every
generated migration.

**Acceptance:** a request travels browser → component → client → route → service → repository → SQLite and
back. Alembic upgrades a copy of a real existing database without data loss. Suite green on both engines.

---

## 4. Steps 4–5 — isolation, then one record workflow

**Step 4 first, and it is Critical class.** Until authorization is real, every endpoint added in step 5 is
an unauthenticated endpoint over health data.

- Real server-side session with expiry, replacing the non-expiring `st.session_state` boolean.
- Selected profile becomes a server-side identifier — retiring the display-label string parsed via
  `names.index()`.
- Authorization at the route layer; person-scoping enforced again at the repository layer.
- Locked-profile masking moves server-side so locked data never reaches the client.

**Step 5 candidate: Allergy.** The only entity that is all-text, dateless, chartless, filterless, and absent
from the body-map adapters — it exercises the full vertical with the least incidental complexity.

- Table: `schema.sql:16-26` (`allergen NOT NULL`, `reaction`, `severity`, `notes`)
- Driven entirely by the generic service functions with `"allergies"` as a string argument
- UI: `app.py` dispatch → `generic_record_page`; field config at `app.FIELD_CONFIGS["allergies"]`
- Validator: `validation.validate_allergy`

**Six read-only consumers that must not break:** `services.dashboard_data`,
`services.generate_provider_summary`, `services.generate_emergency_snapshot`,
`insights.collect_health_context`, `ai_chat._patient_context_packet`, `fhir._allergy_resource`.

**Do not unify** `allergies.severity` (free text — `"Moderate"`) with `health_entries.severity`
(1–10 integer).

**Acceptance:** full CRUD for allergies; `PATCH`/`DELETE`/`GET` with a foreign record id return **404**
(not 403); `validate_allergy` messages render identically; `created_at`/`updated_at` preserved and
`updated_at` bumps on edit; delete-confirm gate preserved.

---

## 5. Steps 6–7

**Step 6** generalizes the step-5 pattern across the remaining six record types with increasing agent
autonomy. These are Routine class once the pattern is proven — an agent may implement directly after
stating scope and assumptions.

**Step 7** migrates the harder subsystems, in this order:

1. **Imports/exports and FHIR** — self-contained, well-tested, high value.
2. **Deterministic analytics** (`insights.py` rule-based half) — pure, no transport.
3. **Body-map state** — the largest frontend rewrite; the payoff for choosing React.
4. **AI routing** — build the `LLMProvider` port, collapsing six duplicated functions into one adapter.
   Rule-based fallback stays mandatory.

---

## 6. Deferred decisions and their triggers

Recorded so they are deliberately open rather than silently unresolved.

| Decision | Trigger that forces it |
|---|---|
| Postgres migration | First multi-tenant user, or observed concurrent-write contention (ADR-0003) |
| Sync transport | After the skeleton is stable; a provider needing to **pull** from the patient forces a reachable endpoint and the hybrid model (ADR-0004) |
| EHR read (SMART on FHIR, US Core) | Requires per-vendor app registration — business/compliance work. Verify current program requirements at that time |
| EHR write-back | `SoT:2048`; frequently unsupported by EHRs |
| Encryption at rest, key management | Before any real user data leaves a developer machine |
| Audit logs | With step 4, or before the first sharing feature |
| Consent model | With the first sharing feature |
| Mobile: responsive vs. native | `SoT:2049`; after the web app is usable |
| HIPAA scope, single- vs. multi-tenant | Product decisions, not engineering (`SoT:2039-2050`) |

### Proposed Streamlit feature-freeze line

`SoT` §33 (line 1758) explicitly asks for one. Proposed:

- **Allowed in Streamlit:** bug fixes, safety and isolation fixes, test additions, small copy changes.
- **Not allowed in Streamlit:** new record types, new pages, new AI capabilities, body-map feature work,
  anything requiring new schema.
- **Rationale:** new complex features added to Streamlit increase migration cost (`SoT:1756`), and
  body-map work in particular would be discarded by step 7.
- **Status:** proposed here, not yet ratified. Needs Daniel's sign-off.

---

## 7. Known issues carried into the migration

| Issue | Where | Handling |
|---|---|---|
| `datetime.utcnow()` deprecated and scheduled for removal | `fhir.py:73` | Fix at the model boundary in step 3 (timezone-aware). Changes FHIR timestamp output, so it needs its own verified change |
| Redundant `socket.timeout` in an `isinstance` | `insights.py:330` | Harmless; clean up opportunistically |
| `generic_record_page` has no direct test | `app.py` | Mitigated by keyword-only `person_id`/`record_id`; superseded when the page becomes React components |
| Connections opened per call, never explicitly closed | `db.py` | Resolved by SQLAlchemy session scope |
| Schema triplication | `schema.sql` / `db.TABLE_COLUMNS` / `app.FIELD_CONFIGS` | Resolved by ORM models as single source of truth |

---

## 8. Per-slice acceptance

Every slice, from step 3 onward:

1. `./scripts/verify.sh` green — ruff is fatal, not advisory. Both engines from step 3.
2. Every invariant in `docs/domain_invariants.md` still holds, with tests cited.
3. Two-profile isolation test for anything profile-scoped (`tests/AGENTS.md`), including foreign-id
   `update`/`delete`/`get` returning 404.
4. Streamlit still works until the replacement is verified.
5. Existing behavioral tests ported, not rewritten to match new code.
6. Residual risks recorded.

Change classes (`PHR_LEARNING_PROTOCOL:122-148`): step 3 scaffolding is **Architectural**; step 4 and
anything touching isolation, auth, or record-altering migration is **Critical** (full diff review,
documented residual risk); step 6 record types are **Routine** once the pattern is proven.
