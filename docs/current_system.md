# Current System

**Verified against the repository:** 2026-08-02, commit `cb7e055`. **Suite:** 206 tests passing on Python 3.12.13.

Supersedes `docs/CODEBASE_SWEEP.md`, which remains in the repo as the historical record of the
P0–P3 audit but is stale by an entire subsystem: it predates `body_map_*`, `components/`, and
`assets/`, and cites a 15-test baseline. Read this file for current structure; read the sweep for
what was found and fixed in June 2026.

Companion documents: `docs/domain_invariants.md` (what must always hold),
`docs/target_architecture.md` (where this is going), `docs/migration_map.md` (how it gets there).

---

## 1. Purpose and user behavior

A local-first family personal health record. One user runs it on their own machine; the SQLite file
holds every family member's records. Selecting a profile in the sidebar scopes everything on screen.

Sixteen pages, grouped in four sidebar sections (`app.NAV_SECTIONS`):

- **Overview** — Dashboard, Body Map
- **Records** — Profiles, Health Timeline, Medications, Allergies, Labs, Appointments, Reminders, Wearables
- **Documents** — Provider Summary, Emergency Snapshot, Health Insights, AI Chat
- **Admin** — Import/Export, Settings

Seven of those (Health Timeline, Medications, Allergies, Labs, Appointments, Reminders, Wearables) are
rendered by a **single** function, `app.generic_record_page`, driven by the `app.FIELD_CONFIGS` table.
Adding a record type is a config change, not a new page.

Supporting capabilities: CSV import for labs and wearables, whole-database JSON backup/restore,
FHIR R4/R5 Bundle export and import, deterministic rule-based insights, optional external AI
(insights and chat), optional per-profile password locks, and a demo mode that swaps in a temporary
database seeded from `sample_test_data.json`.

**What this is not:** it is a working local prototype, not a production healthcare platform. File-level
FHIR support is not connected EHR interoperability. Profile passwords are a local convenience lock,
not authorization.

---

## 2. Files and sizes

| Module | Lines | Role | Imports Streamlit? |
|---|---|---|---|
| `app.py` | 1516 | All UI, routing, forms, presentation, demo mode | yes |
| `fhir.py` | 711 | FHIR R4/R5 Bundle export and import | no |
| `insights.py` | 579 | Deterministic analytics + safety-gated AI reports | no |
| `ai_chat.py` | 502 | AI chat page: context assembly, HTTP transport, rendering | yes |
| `body_map_config.py` | 393 | Body-part/system taxonomy and record mapping (static) | no |
| `db.py` | 343 | Repository: connections, schema init, generic CRUD | no |
| `services.py` | 325 | Service layer: person-scoped operations, derived reads | no |
| `body_map_services.py` | 204 | Normalizes records into `NormalizedBodyRecord` per body part | no |
| `body_map_summary.py` | 196 | Conservative current/historical status summarization | no |
| `imports_exports.py` | 192 | CSV / JSON-backup / FHIR facade | no |
| `body_map_ui.py` | 190 | Body-map rendering and state sync | yes |
| `ai_config.py` | 135 | Provider config and key lookup | yes |
| `validation.py` | 126 | Pure field validators | no |
| `security.py` | 72 | Password hashing + profile unlock state | yes |
| `models.py` | 35 | Controlled vocabularies only | no |

**5,519 lines of application code; 2,027 lines of tests across 5 files.** Also
`components/body_map/index.html` (31 lines of vanilla JS, a Streamlit custom component), `schema.sql`,
and `scripts/verify.sh`.

---

## 3. Call path

```
app.main()
  → db.init_db()                              # bootstrap, in app.main
  → app.selected_profile_sidebar(db_path, demo_mode)
      → services.list_people(db_path)
      → st.sidebar.selectbox(key="selected_profile")   # value is a DISPLAY LABEL string
      → returns (label, person_dict)
  → app.require_profile(person)                # UI gate
  → security.health_data_visible(person, db_path) or app.unlock_screen()   # UI gate
  → page function(person, db_path, demo_mode)
      → services.<fn>(int(person["id"]), ..., db_path=db_path)
          → db.<fn>(..., db_path=db_path)
              → sqlite3
```

Body map and AI chat branch off to `body_map_ui.render_body_map_page(person, db_path)` and
`ai_chat.render_ai_chatbot(person_id, db_path)`.

### Layering is cleaner than it looks

Direct `db.*` **calls** by module: `app.py` **3** (all bootstrap/demo-seed — `db.init_db()` at
`app.main`, and `db.init_db` + `db.import_all_tables` for demo seeding in `app.create_demo_database`),
`imports_exports.py` 2, `fhir.py` 1, and **zero** in `insights.py`, `ai_chat.py`,
`body_map_services.py`, and `body_map_ui.py`. Everything else routes through `services.*`.

The Streamlit → service boundary is therefore already well drawn. `db.py` imports no Streamlit and
holds no business logic; `services.py` imports only `db`. This is why a FastAPI backend is a
signature change rather than a rewrite for roughly 2,300 of these lines.

---

## 4. Schema and data model

`schema.sql`: eight tables. `people` plus seven child tables, each with
`person_id INTEGER NOT NULL REFERENCES people(id)` and a `(person_id, ...)` composite index.

`people`, `allergies`, `medications`, `lab_results`, `health_entries`, `appointments`, `reminders`,
`wearable_records`.

Facts that matter for migration:

- **No `ON DELETE CASCADE` anywhere.** `db.delete_person` deletes every child table then the parent
  inside a single transaction, and raises `RecordNotFound` if the parent delete matches no row — which
  rolls the children back with it. The guarantee lives in application code, not the database, so it
  does not survive anything that writes to SQLite without going through this function.
- `wearable_records` has `created_at` but **no `updated_at`**; every other table has both.
  `db.create_record`/`update_record` branch on this.
- `people` carries auth columns inline: `profile_password_enabled`, `profile_password_hash`,
  `profile_password_hint`.
- `allergies.severity` is **free text** (`"Moderate"`, `"Severe"`); `health_entries.severity` is a
  **1–10 integer**. Do not unify them.
- Timestamps are naive local time via `db.now_iso()` — no timezone.

**Schema knowledge is triplicated** and hand-synced across `schema.sql` (DDL), `db.TABLE_COLUMNS`
(the writable-column allowlist), and `app.FIELD_CONFIGS` (the form/table definition). Changing a column
means editing three places with nothing enforcing agreement.

**There is no migration mechanism.** `schema.sql` is entirely `CREATE TABLE IF NOT EXISTS` /
`CREATE INDEX IF NOT EXISTS`, so an added column silently no-ops against an existing `data/phr.db` and
appears only in fresh databases. Tests never catch this because they build fresh databases. This is the
single most consequential defect in the current system and the reason Alembic is not optional
(see ADR-0003).

### There are no entity types

`models.py` contains no classes — only controlled vocabularies (`BODY_SYSTEMS`, `MEDICATION_STATUSES`,
`LAB_FLAGS`, …). Records travel as plain `dict` from `sqlite3.Row` all the way to HTML. The only real
domain objects in the codebase are `body_map_services.NormalizedBodyRecord` (a frozen dataclass) and
`body_map_summary.BodyPartHealthSummary`.

---

## 5. State ownership

**There is no `person_id` in session state.** The tenant key is reconstructed on every rerun from a
formatted display string.

| Key | Holds | Set at |
|---|---|---|
| `selected_profile` / `demo_selected_profile` | **a display label**, e.g. `"Alice (ID 3)"` or `"Protected profile (ID 3)"` | app.py selectbox |
| `nav_page` | current page name | `app.page_navigation` |
| `demo_mode_enabled`, `demo_db_path` | demo toggle and temp DB path | `app.start_demo_mode` |
| `profile_unlocked_{sha1(db_path)[:12]}_{person_id}` | per-profile unlock bool | `security.unlock_profile` |
| `show_add_{table}_form` | add-form toggle | `generic_record_page` |
| `edit_{table}_selection_reset` / `edit_{table}_selection_{n}` | counter used to force-reset the edit selectbox, and the selected id | `generic_record_page` |
| `body_map_profile_scope`, `selected_body_part`, `body_map_trend_record` | body-map scope and selection | `body_map_ui` |
| `ai_chat_history_{person}_{db}` | chat transcript (memory only, never persisted) | `ai_chat._history_key` |

Identity is recovered by `names.index(selection)` against the label list — unambiguous only because the
label embeds the id. **The effective tenant key is the pair `(active_db_path(), person["id"])`**, because
demo mode swaps the entire database file. There is no stable current-profile identifier and no
server-side notion of a session.

This is the clearest example of Streamlit's rerun model leaking into the domain, and it is what slice 4
exists to replace.

---

## 6. Validation

`validation.py` is pure and framework-free. Every validator returns `list[str]` of human-readable
messages and **never raises** — deliberately, so CSV import, backup restore, and FHIR import can report
per-row errors and skip rather than abort.

Primitives: `is_blank`, `require`, `valid_date`, `valid_number`, `normalize_optional_number`,
`valid_severity`, `valid_choice`, `valid_date_order`.
Entity validators: `validate_person`, `validate_medication`, `validate_allergy`, `validate_lab`,
`validate_health_entry`, `validate_appointment`, `validate_reminder`, `validate_wearable`.

Reused by `imports_exports.BACKUP_VALIDATORS` and `fhir.FHIR_VALIDATORS` — already stack-independent,
and the cheapest thing in the codebase to port.

**Wart:** type coercion lives in the UI (`app.clean_payload`, `""` → `None`, float/int casts), not in
validation. The service layer therefore accepts unvalidated, uncoerced dicts. A Pydantic model would
own both halves; resolving this is a decision in `target_architecture.md`.

---

## 7. Failure modes

- **Validation failures** — surfaced as messages, never exceptions. Row-atomic for imports.
- **Isolation violations** — `db.RecordNotFound` (added 2026-08-01). Raised when a scoped write
  matches no row (`db._mutation_scope` supplies the `WHERE`); `app.apply_record_change` renders a
  clean message rather than a traceback.
- **Provider failures** — typed: `ZhipuAPIError`, `ZhipuRetryableError`, `AIChatError`,
  `MissingAPIKeyError`, `RateLimitError`, `NetworkAIChatError`, `InvalidAIResponseError`. Model fallback
  retries capacity failures (429, missing resource package) across candidates but **not** transport
  timeouts or account errors, so total AI latency stays bounded; rule-based output always remains
  available.
- **Database errors in the body map** — explicitly *not* reported as "no data," since an empty state
  reads as clinically meaningful (`test_database_error_is_not_reported_as_no_data`).
- **Malformed stored data** — unparseable dates are displayed unchanged rather than dropped;
  non-numeric wearable values do not crash summaries.

### Known code-level issues

- `fhir.export_bundle` uses `datetime.utcnow()`, deprecated and **scheduled for removal**. Surfaces as a test
  warning. Fixing it changes FHIR timestamp output (naive → timezone-aware), so it needs its own change.
- `insights._call_zhipu_chat_completion` still references `socket.timeout` inside an `isinstance` check — redundant on 3.10+
  where it aliases `TimeoutError`, harmless, `socket` still imported.
- Connections are opened per function call and never explicitly closed; `sqlite3`'s context manager
  commits/rolls back but does not close. Handles are released by GC. No transaction spans two calls.

---

## 8. Security and privacy posture

**Implemented:** local SQLite, local-first default, optional per-profile passwords (PBKDF2-HMAC-SHA256,
260k iterations, per-password random salt), Keychain storage for the optional Zhipu key, no automatic
external AI send, selected-profile-only AI context with byte budgeting, no persisted chat history,
medical disclaimer and urgent-warning language, and — as of PR #3 — person-scoped record writes.

**Not implemented:** production authentication, encryption at rest, audit logs, cloud sync, role-based
permissions, secure provider sharing, HIPAA deployment infrastructure, OAuth, consent tracking, live
EHR authorization.

`security.py` is the module that must be **replaced rather than ported**: the PBKDF2 hashing is sound
and portable, but unlock state is a per-browser, non-expiring `st.session_state` boolean, and there is
no application-level authentication at all. Anyone with the running app sees every profile that is not
individually password-protected.

See `docs/domain_invariants.md` §8 for the full list of stated-but-unenforced properties.

---

## 9. The AI layer is duplication, not abstraction

`ai_config.AI_PROVIDER` is read once (`ai_config.AI_PROVIDER`) and **never branched on**. There is no provider
interface, registry, or strategy. Three concerns are each implemented twice:

| Concern | Implementation A | Implementation B |
|---|---|---|
| API key lookup | `ai_config.get_zhipu_api_key` | `ai_chat.get_zhipu_api_key` |
| HTTP error parsing | `ai_chat._parse_http_error` | `insights._parse_http_error` |
| Request build + model fallback | `ai_chat._call_zhipu_chat_model` | `insights._build_zhipu_request` / `_call_zhipu_with_model_fallback` |

The source-of-truth requirement to "preserve AI-provider abstraction" is therefore a requirement to
**build** one, not to keep one. Target: a single `LLMProvider` port plus a shared error taxonomy,
collapsing six functions into one adapter.

---

## 10. Tests

206 tests, `scripts/verify.sh` = fatal `ruff check .` → `compileall` → `pytest -q`.

| File | Covers |
|---|---|
| `tests/test_basic.py` (973 lines) | schema init, CRUD, person isolation on reads *and writes*, profile passwords, reminders, insights, JSON backup/restore, CSV import, demo isolation, FHIR round trip, AI safety/retry/scoping |
| `tests/test_body_map_config.py` (308) | canonical ids, mapping validity, alias collisions, preserved multi-system uncertainty |
| `tests/test_body_map_services.py` (198) | profile-scoped retrieval, mapping precedence, normalization, error handling |
| `tests/test_body_map_summary.py` (187) | conservative current/historical status, flag normalization, non-diagnostic language |
| `tests/test_body_map_ui.py` (361) | Streamlit `AppTest`, component events, state reset, SVG ids |

**Coverage gap worth knowing:** `app.generic_record_page` — the function rendering seven of the sixteen
pages — has no direct test. Its service calls are covered; its wiring is not. `services.update_item`
and `delete_item` therefore take `person_id` and `record_id` as **keyword-only** parameters, so a
silent argument swap is impossible rather than merely untested
(`test_person_and_record_ids_are_keyword_only_on_scoped_writes`).

---

## 11. Trade-offs and limitations

- `db_path` is threaded manually through nearly every signature in every module — the connection/tenant
  concern is a parameter instead of injected context. This is the largest mechanical change any
  migration faces.
- Streamlit leaks into library modules: `security.py` (session state), `ai_config._get_streamlit_secret`,
  `ai_chat.py` (mixes context building, transport, and rendering), `body_map_ui.py` (rendering + state sync).
- `imports_exports.py` and `fhir.py` read `db.TABLES` / `db.TABLE_COLUMNS` directly, coupling I/O modules
  to the physical schema dict.
- `app.py` at 1,516 lines mixes routing, CSS (~260 lines), form plumbing, presentation, and demo mode.
- `generic_record_page` carries `# noqa: C901, PLR0915` — already over the complexity gate.

---

## 12. Modifying this system safely

1. Read `docs/domain_invariants.md` first. Person isolation, provenance, truth labeling, and safety are
   not negotiable without explicit sign-off.
2. Run `./scripts/verify.sh` before and after. Ruff is a **fatal** gate, not advisory.
3. For anything profile-scoped, create **two** profiles in the test and assert the non-selected profile
   is absent (`tests/AGENTS.md`).
4. Never point tests at `data/phr.db`; use `tmp_path`.
5. Adding a record type means editing `schema.sql`, `db.TABLE_COLUMNS`, **and** `app.FIELD_CONFIGS` —
   all three, or the column will silently not persist. Remember that `CREATE TABLE IF NOT EXISTS` will
   not apply the change to an existing database.
6. New AI output paths must have a rule-based or safe failure mode and enforce the same safety
   constraints as `insights.py` and `ai_chat.py`.
7. Keep `pyproject.toml`'s ruff `target-version` in sync with the venv interpreter. A target ahead of the
   runtime lets pyupgrade rewrite to syntax that cannot execute.
