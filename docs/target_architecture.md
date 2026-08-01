# Target Architecture

**Status:** agreed direction as of 2026-08-01. All four framework ADRs are decided.

| Layer | Choice | ADR |
|---|---|---|
| Deployment | Local-first; sync and sharing are later, user-enabled slices | [0004](adr/0004-deployment-local-first.md) |
| Backend | FastAPI | [0001](adr/0001-backend-fastapi.md) |
| Frontend | React + TypeScript (Vite) | [0002](adr/0002-frontend-react-typescript.md) |
| Persistence | SQLAlchemy ORM + Alembic, SQLite now, Postgres-compatible | [0003](adr/0003-persistence-and-migrations.md) |
| Runtime | Python 3.12 | — |

Read `docs/current_system.md` for what exists today and `docs/migration_map.md` for the sequence.

---

## 1. The walking skeleton path

```
browser
  → React component
    → typed API client (generated from the OpenAPI schema)
      → FastAPI route            ← authorization boundary lives HERE
        → service                ← person-scoped contracts
          → repository           ← SQLAlchemy session
            → SQLite (Postgres-compatible)
          → response model       ← Pydantic
    → client state
  → UI
```

Every slice must traverse this whole path. A slice that stops at the service layer is not a slice.

---

## 2. Where each existing module lands

### Ported — signature changes, not rewrites

| Module | Change |
|---|---|
| `validation.py` | Ported as-is. Already pure and shared by UI, CSV import, backup restore, and FHIR import. See §4 for how it meets Pydantic. |
| `fhir.py` (711 lines) | Ported. Reads move behind the repository; `export_bundle`/`import_bundle` become route handlers. The interop substrate — do not rewrite. |
| `insights.py` — analytics half | Ported. `collect_health_context` takes a session; everything downstream already operates on a plain `context` dict and is trivially portable. |
| `body_map_config.py`, `body_map_services.py`, `body_map_summary.py` | Ported. Best-layered code in the repo; already read exclusively through the service layer. |
| `imports_exports.py` | Ported. Stops reaching into `db.TABLES`/`db.TABLE_COLUMNS` (see §6). |
| `services.py` | Ported with the person-scoping contract made explicit and mandatory. |
| `models.py` | Absorbed into ORM models and enum/`CHECK` constraints. |

### Rewritten

| Module | Becomes |
|---|---|
| `db.py` | SQLAlchemy models + repository classes. The hand-rolled f-string query builder (`db.py:200-225`) is retired. |
| `app.py` (1,516 lines) | Split: routes (FastAPI) + components (React). `FIELD_CONFIGS` is the seam — see §5. |
| `body_map_ui.py`, `components/body_map/index.html` | A first-class React component. |
| `ai_chat.py` | Split three ways: context assembly (service), transport (provider adapter), rendering (React). |

### Replaced

| Module | Why |
|---|---|
| `security.py` | PBKDF2 hashing (`hash_password`/`verify_password`) survives and is portable. The `st.session_state` unlock model does not — it is a per-browser, non-expiring boolean, and there is no application-level authentication at all. See §7. |

---

## 3. Persistence

**ORM models are the single source of schema truth**, collapsing today's triplication across `schema.sql`,
`db.TABLE_COLUMNS`, and `app.FIELD_CONFIGS`. Alembic autogenerates migrations by diffing them.

Non-negotiable properties, per ADR-0003:

- **Real column types.** `Date`, `DateTime`, `Numeric` — never carry the current `TEXT`-for-every-date shape
  forward. Every date and timestamp in `schema.sql` is `TEXT` today.
- **`CHECK` constraints** for the `models.py` vocabularies, which the database does not enforce at all today.
- **`ON DELETE CASCADE`** via declared relationships, moving the delete-children guarantee out of
  `services.delete_person` and into the database.
- **No Postgres-only types** (JSONB, arrays). Dual-engine CI makes this self-enforcing.
- **Timezone-aware timestamps.** `db.now_iso()` is naive local time today, and `fhir.py:73` still calls the
  deprecated `datetime.utcnow()`. Fix both at the model boundary.

### Repository contract — the isolation boundary

The contract established in `2e8261e` carries forward and tightens:

```python
class RecordRepository:
    def list(self, person_id: int, ...) -> list[Model]: ...
    def get(self, person_id: int, record_id: int) -> Model: ...      # raises RecordNotFound
    def create(self, person_id: int, data: Model) -> Model: ...      # person_id force-set
    def update(self, person_id: int, record_id: int, data) -> Model: ...
    def delete(self, person_id: int, record_id: int) -> None: ...
```

`person_id` is **required and first** on every method. Unscoped access is a separate, explicitly named
method (`list_all_for_export`), never a `person_id=None` default — a default is how this became a
vulnerability the first time.

`RecordNotFound` maps to **404, never 403.** Distinguishing "missing" from "not yours" lets a caller probe
for the existence of another profile's records. See `docs/domain_invariants.md` §1.

### Migrating existing databases

The startup migration must: back up the user's file first; run Alembic programmatically; and **surface**
rows the new typed columns reject rather than coercing or dropping them. The current app tolerates
unparseable dates and non-numeric numerics by design, so such rows exist. Silently fixing them violates the
provenance invariant (`domain_invariants.md` §2) — they need a quarantine or report path.

---

## 4. Validation — the resolved fork

`validation.py` returns `list[str]` and never raises, deliberately, so CSV import, backup restore, and FHIR
import can report per-row errors and skip rather than abort. Pydantic raises. These are genuinely different
contracts and the conflict must be resolved once, not per-slice.

**Decision: keep `validation.py` as the shared rule layer; wrap it at the API boundary.**

- Pydantic models own **shape and type coercion** at the HTTP edge — replacing `app.clean_payload`
  (app.py:791), which is type coercion that has been living in the UI.
- `validation.py` owns **domain rules** (severity ranges, date ordering, controlled vocabularies) and keeps
  its message-list contract.
- The route layer calls the validators and converts messages into a `422` with per-field detail.
- Batch importers keep calling `validation.py` directly and keep skipping bad rows — unchanged.

Rejected: moving all rules into Pydantic validators, which would either break batch import's
skip-and-report behavior or force duplicate rule definitions.

---

## 5. Frontend

`app.FIELD_CONFIGS` is the migration seam. Seven of sixteen pages are already rendered by one
config-driven function (`generic_record_page`); that property must survive. `FIELD_CONFIGS` becomes a
TypeScript schema driving a generic record page component, so adding a record type stays a config change.

- Typed API client generated from FastAPI's OpenAPI schema — no hand-written fetch wrappers.
- The selected profile becomes real client state backed by a **server-side identifier**, replacing today's
  display-label string parsed by `names.index()`.
- The body map becomes a first-class component. The tests that exist only to fight Streamlit's rerun model
  (`test_profile_change_clears_stale_body_state`, `test_component_key_changes_only_with_profile_or_database_scope`)
  should disappear rather than be ported — if an equivalent is still needed, the state model is wrong.
- The delete-confirm gate (`generic_record_page`) is preserved as an explicit client-side confirmation.

---

## 6. Cross-cutting cleanups

**`db_path` disappears.** Today it is threaded manually through nearly every signature in every module —
the connection and tenant concern expressed as a parameter. It becomes injected session scope via FastAPI
dependencies. This is the largest mechanical change in the migration.

Demo mode currently works by swapping the entire database file, which is why the effective tenant key is
the pair `(active_db_path(), person_id)`. In the target, demo mode is a seeded database selected at
session scope — the rest of the system never learns about it.

**Schema coupling.** `imports_exports.py` and `fhir.py` read `db.TABLES`/`db.TABLE_COLUMNS` directly. They
move to the ORM metadata or an explicit export schema.

**The AI provider port.** `ai_config.AI_PROVIDER` is read once and never branched on; key lookup, HTTP
error parsing, and model fallback are each implemented twice (`current_system.md` §9). Target: one
`LLMProvider` interface —

```python
class LLMProvider(Protocol):
    def complete(self, messages, *, model, max_tokens, temperature) -> str: ...
```

— plus the shared error taxonomy already sketched by `AIChatError` and its subclasses, collapsing six
functions into one adapter. The rule-based fallback path stays mandatory
(`domain_invariants.md` §6).

---

## 7. Authentication and authorization

The one place where "port the existing behavior" is the wrong instruction.

Today: no application authentication; per-profile passwords are a **local convenience lock**; unlock state
is a per-browser `st.session_state` boolean with no expiry; and the two gates in `main()`
(`require_profile`, `health_data_visible`) are **UI-level only** — the service layer will return a locked
profile's data if called directly.

Once a browser can call an API, UI gates are decorative. Required in the target:

- Authorization enforced at the **route** layer, with the person-scoping contract enforced again at the
  **repository** layer. Two layers, because the first is about who is asking and the second is about what
  they may touch.
- A real session with expiry, replacing the non-expiring boolean.
- Locked-profile masking applied server-side, so locked data never reaches the client — today it is masked
  in display helpers, which is the wrong side of the boundary.

Under ADR-0004 this is a **local** identity boundary, not an identity platform. It becomes a real identity
problem only when a sharing slice exists, and only for the sharing path.

---

## 8. Testing

- The 159 existing tests are the behavioral contract. Port them; do not rewrite them to match new code.
- The two-profile isolation pattern (`tests/AGENTS.md`) applies to every new endpoint, and now must cover
  `update`/`delete`/`get` with a **foreign record id** returning 404.
- **Dual-engine CI** from slice 3 (ADR-0003): the suite runs against SQLite and Postgres.
- Contract tests against the generated OpenAPI schema, so client and server cannot drift silently.
- `scripts/verify.sh` stays the gate, extended to cover the frontend.

## 9. What this architecture does not decide

Deliberately open, with triggers recorded in `docs/migration_map.md`: sync transport, encryption at rest
and key management, audit log design, consent model, EHR read/write-back, mobile (responsive vs. native),
and the Streamlit feature-freeze line requested by `SoT` §33.
