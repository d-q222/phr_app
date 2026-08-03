# PR #3 Independent Audit — Findings Ledger and Post-Merge Audit Driver

Recorded 2026-08-01 from the independent security/correctness audit of PR #3
(branch `migration/slice-1-code`, audit base HEAD `9b8d52c`). This file is the
single source of truth for what remains open from that audit. Delete an entry
only after its fix and regression test are confirmed on `main`; delete this
file when empty.

**Post-merge follow-up audit completed 2026-08-02** against merged `main`
(`63e2295`, PRs #1–#9 all landed). Results:

- Every `FIXED-HERE` regression test named in the original ledger exists in
  `tests/test_basic.py` and passes. `./scripts/verify.sh` is green
  (ruff + compileall + 206 tests).
- M1 closed: all five profile/password call sites route through
  `apply_record_change` — password remove `app.py:919`, password save `:936`,
  profile create `:1025`, profile delete `:1072`, profile update `:1080`.
- M2 closed: both restore `except` tuples include `db.DatabaseBusyError`
  (`app.py:1384`, `:1414`) and both CSV imports are wrapped
  (`app.py:1341-1343`, `:1347-1349`).
- L24 closed for the original instance and the test-suite class: the root
  `conftest.py` guard anchored to `db.DATA_DIR` (`conftest.py:22-37`) landed,
  and `db.py` late-binds `db_path` via `db._resolve_db_path` (`db.py:107-119`).
  Independent PR review (2026-08-02) then found one straggler the audit
  missed — tracked as L24b below.
- L22 closed: the only remaining `delete_records_for_person` reference in
  `docs/CODEBASE_SWEEP.md` is the intentionally-historical changelog line
  (`:434`); the `get_connection` walkthrough line now covers busy handling
  (`:61`).
- L23 closed: `docs/current_system.md`, `docs/target_architecture.md`,
  `docs/migration_map.md`, `docs/domain_invariants.md`, and `docs/adr/` now
  exist (slice-1 merge). The one still-unrealized reference,
  `docs/architecture/<subsystem>.md`, is annotated planned-not-yet-created in
  `PHR_LEARNING_PROTOCOL_2026-07-28.md`, per this row's prescribed remedy.
- **L2 and L3 did not land on any merged branch.** Both were reclassified OPEN
  by mutation spot-check (details in their rows below).
- An independent read-only review of this PR (fresh reviewer thread,
  2026-08-02) re-verified every citation in this file against the working
  tree. Its two confirmed corrections are folded in: the L24b straggler and
  the narrowed L10 evidence wording.
- All fully-closed rows were deleted per the procedure; git history preserves
  them. L15/L17/L19 were narrowed to their residuals — the primary fixes were
  verified (response-body caps, README wording, `init_db` busy mapping with the
  boot-time catch at `app.py:1489-1492`).

All entries in the table below are `OPEN` work items. The two decision rows
(L17/L19 residuals) were ruled on 2026-08-02 and moved to "Ruled 2026-08-02";
L21 was raised to Medium by the same ruling.

## Open findings

| ID | Finding | Evidence (2026-08-02 post-merge audit) | Required fix / test |
|----|---------|----------------------------------------|---------------------|
| M2b | FHIR restore with clear-existing commits the clear, then inserts per row — a mid-import failure of any kind leaves a cleared DB with partial rows. Same per-row pattern in CSV lab/wearable imports: a mid-import busy leaves rows 1..k-1 committed, and a naive retry duplicates them (the CSV busy message warns about this) | `fhir.py:86` commits the clear in its own transaction, then inserts each resource in a separate transaction (`fhir.py:95`, `:118`); CSV per-row inserts at `imports_exports.py:64`, `:87`. Contrast: the JSON backup restore is already atomic — clear + upserts inside one `_write_connection` (`db.py:362-381`) — and is the natural template for the fix | Run FHIR restore and each CSV import in one `_write_connection` transaction (or staged with rollback); verify with a forced mid-import failure test. Touches destructive DB behavior — warrants `privacy_safety_reviewer`-grade review when picked up |
| L21 (raised Low → **Medium**, maintainer ruling 2026-08-02) | Import/Export destructive-write arming state (uploaders, clear/confirm checkboxes) is not person/db-scoped: a labs CSV staged under Alice stays armed after switching to Bob, and a FHIR clear-restore staged in **demo mode stays armed when switching back to the real database**. Raised to Medium: cross-profile writes breach the §4 isolation invariant, and the demo→real armed-restore path compounds with M2b (a mid-restore failure leaves the cleared real DB with partial rows) | CSV uploaders have no key (`app.py:1338`, `:1344`); FHIR widgets use static keys (`:1375-1377`); JSON restore widgets keyless or static `confirm_backup_restore` (`:1405-1407`). Session state is keyed only by these strings, so nothing resets on a profile or demo/real switch (structural verification; the demo→real sequence has not been driven end-to-end in an AppTest) | Key with `record_page_scope`-style person+db prefixes + AppTest `test_import_export_confirmations_and_uploads_reset_on_profile_or_database_switch`. Schedule together with M2b |
| L2 | Empty-payload ownership path (`id = id` no-op UPDATE, `db.py:219`) has no regression test | Mutation check: inserting `if not values: return` before the UPDATE in `db.update_record` left all 206 tests green. No test in `tests/` updates a record with `data={}` or a filtered-to-empty payload. Reclassified from OTHER-BRANCH — the claimed test never landed | Test that updates a foreign-owned and a missing `wearable_records` row with `data={}` and a filtered-to-empty payload expecting `RecordNotFound`, and that an owner's empty update succeeds unchanged |
| L3 | Suite cannot detect a reintroduced SELECT-then-mutate TOCTOU in scoped mutations | Mutation check: replacing the single scoped UPDATE in `db.update_record` with SELECT-then-unscoped-UPDATE left all 206 tests green — the shape is invisible to single-threaded behavior tests. Not covered by L2's branch (which itself never landed) | `Connection.set_trace_callback` test asserting scoped mutations are a single UPDATE/DELETE whose WHERE contains both `id = ?` and `person_id = ?`, with no SELECT |
| L10 | Insights retry-loop deadline/sleep-cap/3-attempt bound has no deterministic test | The insights loop has only real-time tests (`test_insight_urlopen_timeout_stops_without_retry_or_sleep`, `test_insight_1113_makes_exactly_one_request_without_retry_or_sleep`). `test_ai_chat_fallbacks_share_one_monotonic_deadline` (`tests/test_basic.py:1523`) fakes `monotonic` for the ai_chat deadline, but nothing drives the insights retry/sleep loop with a clock whose `sleep` advances it | Fake clock whose `sleep` advances `monotonic`; eligible-429 mock; assert request counts, non-increasing timeouts ≤ 30, sleeps `[3, 8]`, no request after deadline |
| L24b | `insights.collect_health_context` still freezes `db_path=db.DB_PATH` in its signature (`insights.py:95`) — evaluated at import time, so a later repoint of `db.DB_PATH` is ignored and an argument-less call reads the real DB path. Found by independent PR review 2026-08-02; the only frozen default left repo-wide, in the very function whose call site caused the original L24 CI failure | App callers pass `db_path` explicitly and the `conftest.py` DATA_DIR guard fails any test that trips it, so today this is a footgun rather than a live leak. It escaped because `test_omitted_db_path_resolves_at_call_time_not_import_time` (`tests/test_basic.py:1827`) proves the property only through `db.init_db` + three `services` functions | One-line fix: default to `None` (callees late-bind `None` via `db._resolve_db_path`); extend the late-binding regression test to sweep every public function with a `db_path` parameter |
| L15-residual | Error-body reads are uncapped: `exc.read()` in both `_parse_http_error` helpers (success-body caps landed and are verified) | `ai_chat.py:307`, `insights.py:301` read without a limit; success paths cap at `ai_chat.py:398`, `insights.py:336` via `ai_config.ZHIPU_RESPONSE_BYTE_LIMIT` | Cap error-body reads the same way, with tests mirroring the oversized-response-body pair |

## Ruled 2026-08-02 (maintainer)

- **L17-residual — ACCEPTED.** No true total-deadline cap on AI calls; urllib
  timeouts remain per-socket-operation, and the README documents exactly that
  (`README.md:174`, `:188`), so acceptance costs nothing. Worst case today is a
  hung interactive request the user can abandon. Revisit trigger: any
  unattended AI call path (scheduled insights, a server-side API) — a
  drip-feeding provider could then hold a request open with nobody watching.
- **L19-residual — DEFERRED (accepted for now).** Read paths (`db.get_record`
  `db.py:260`, `db.list_records` `:268`) keep raising raw `OperationalError`
  under a held lock; busy mapping stays write-scoped as the README documents.
  Rationale: lock contention needs a second concurrent connection, which is
  rare for one local user. Revisit trigger: anything that adds a second
  process or session touching the DB — most concretely the planned FastAPI
  backend (`docs/adr/0001-backend-fastapi.md`) — or any user-visible read-time
  traceback. The fix stays cheap when wanted: route both readers through the
  same busy mapping writes use.

## Pre-existing residuals tracked elsewhere (not re-listed above)

- Medical post-validation of AI provider output — Open P1 in `AGENTS.md` / `docs/CODEBASE_SWEEP.md`.
- Locked-profile authorization at reusable context/export boundaries — Open P1, same locations.

## Next audit pass

When any row above is fixed: confirm the fix and its regression test on `main`
(re-run the relevant mutation check for L2/L3), then delete the row. Delete
this file when no rows remain.
