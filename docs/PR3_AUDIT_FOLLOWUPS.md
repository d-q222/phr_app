# PR #3 Independent Audit — Findings Ledger and Post-Merge Audit Driver

Recorded 2026-08-01 from the independent security/correctness audit of PR #3
(branch `migration/slice-1-code`, audit base HEAD `9b8d52c`). This file is the
single source of truth for what the audit found, what was fixed where, and what
the **post-merge follow-up audit** must re-verify once all in-flight branches
land. Delete entries only after the post-merge audit confirms them closed.

Status legend:

- `FIXED-HERE` — fixed on this branch, with the named regression test.
- `FIXED-ON-MAIN` — already fixed on `main`; this branch inherits it by merge.
- `OTHER-BRANCH` — being addressed on a different branch; post-merge audit must
  confirm it actually landed.
- `OPEN` — not yet addressed anywhere; needs an owner.

## Medium

| ID | Finding | Status | Location | Post-merge check |
|----|---------|--------|----------|------------------|
| M1 | Profile/password writes surfaced `DatabaseBusyError` (and theoretical `RecordNotFound`) as a raw Streamlit traceback | FIXED-HERE — all five call sites now route through `apply_record_change` | `app.py` password remove/save, profile create/delete/update | `test_profile_write_busy_shows_clean_error_with_apptest` covers the update path; confirm the other four paths manually or extend the test |
| M2 | FHIR/JSON restore and CSV imports leaked `DatabaseBusyError` as a traceback | FIXED-HERE — busy added to both restore `except` tuples; CSV imports wrapped | `app.py` `page_import_export` | No automated test: Streamlit `AppTest` cannot drive `file_uploader`. Post-merge audit: verify tuples still include `db.DatabaseBusyError`, or add a test if AppTest gains uploader support |
| M2b | FHIR restore with clear-existing commits the clear, then inserts per row — a mid-import failure of any kind leaves a cleared DB with partial rows. Same per-row pattern in CSV lab/wearable imports: a mid-import busy leaves rows 1..k-1 committed, and a naive retry duplicates them (the CSV busy message now warns about this) | OPEN (pre-existing design; busy merely added a new trigger) | `fhir.py` import path; `imports_exports.py` CSV imports | Make each restore/import one transaction (single `_write_connection`) or staged; verify with a forced mid-import failure test |

## Low — behavioral

| ID | Finding | Status | Location | Post-merge check |
|----|---------|--------|----------|------------------|
| L1 | Whitespace-only allergy severity stored verbatim instead of NULL (regression vs pre-PR behavior) | FIXED-HERE | `app.py` `clean_payload` | `test_blank_and_whitespace_severity_normalize_to_none_for_both_severity_tables` |
| L14 | Deeply nested provider JSON raised unmapped `RecursionError` past the AI boundary (success bodies AND HTTP-error bodies via both `_parse_http_error` helpers) | FIXED-HERE | `ai_chat.py` invalid-response clause; both `_parse_http_error` `json.loads` guards | `test_ai_chat_rejects_pathologically_nested_json_response`, `test_http_error_parsers_tolerate_pathologically_nested_error_bodies` |
| L15 | Unbounded `response.read()` let a misbehaving provider exhaust memory | FIXED-HERE for both response-body sites via `ai_config.ZHIPU_RESPONSE_BYTE_LIMIT` | `ai_chat.py`, `insights.py` | `test_ai_chat_rejects_oversized_response_body`, `test_insight_rejects_oversized_response_body`. Residual OPEN: error-body reads (`exc.read()` in both `_parse_http_error` helpers) are still uncapped |
| L16 | Insights 30s budget was an undocumented duplicated literal | FIXED-HERE — `INSIGHT_TIMEOUT_SECONDS` + README sentence | `insights.py`, `README.md` | Constant used at both deadline sites |
| L17 | README overstated the deadline as a hard wall-clock cap (urllib timeouts are per socket operation) | FIXED-HERE (wording) | `README.md` AI sections | Residual OPEN: a true hard cap would need a reader thread or an HTTP client with total-deadline support — decide if ever worth it |
| L18 | Empty model candidate list raised `None` (TypeError) in insights fallback | FIXED-HERE | `insights.py` `_call_zhipu_with_model_fallback` | `test_insight_empty_model_candidates_raise_config_error_not_typeerror` |
| L19 | `init_db` bypassed busy mapping; busy at app boot gave a raw traceback | FIXED-HERE — `init_db` uses `_write_connection`; boot call catches busy with `st.stop()` | `db.py`, `app.py` `main` | `test_init_db_busy_maps_to_database_busy_error`. Residual OPEN: read paths (`get_record`, `list_records`, exports) still raise raw `OperationalError` under a held lock; README scopes the guarantee to writes |
| L20 | `create_record` silently dropped `person_id` for non-person-scoped tables where update/delete raise | FIXED-HERE | `db.py` `create_record` | `test_create_record_rejects_person_id_for_unscoped_tables` |
| L21 | Import/Export destructive-write arming state (uploaders, clear/confirm checkboxes) is not person/db-scoped: a labs CSV staged under Alice stays armed after switching to Bob | OPEN (pre-existing) | `app.py` `page_import_export` widget keys | Key with `record_page_scope`-style prefixes + AppTest `test_import_export_confirmations_and_uploads_reset_on_profile_or_database_switch` |

## Low — test coverage (each proven by mutation testing: the pre-fix suite stayed green with the guard broken)

| ID | Finding | Status | Post-merge check |
|----|---------|--------|------------------|
| L2 | Empty-payload ownership path (`id = id`) had no regression test | OTHER-BRANCH | Confirm a test exists that updates a foreign-owned and a missing `wearable_records` row with `data={}` and a filtered-to-empty payload expecting `RecordNotFound`, and that an owner's empty update succeeds unchanged |
| L3 | Stale-connection test cannot detect a reintroduced SELECT-then-mutate TOCTOU (the pre-fix vulnerable code passes it) | OPEN — possibly covered with L2's branch; confirm | Needs a `Connection.set_trace_callback` test asserting scoped mutations are a single UPDATE/DELETE whose WHERE contains both `id = ?` and `person_id = ?`, with no SELECT |
| L4 | No test pinned rejection of `person_id` equal to the current owner (or `None`-valued) in update payloads | FIXED-HERE — `test_person_id_is_immutable_during_scoped_updates` now covers bob/alice/None |
| L5 | `delete_person` missing-id RecordNotFound/rollback path untested | FIXED-HERE — `test_delete_person_missing_id_raises_and_rolls_back` (orphan row proves rollback) |
| L6 | Transfer-surfaces test omitted the provider summary surface | FIXED-HERE — `generate_provider_summary` added to both surface lists |
| L7 | Empty/whitespace chat content rejection untested | FIXED-HERE — `""` and `"   "` added to `test_ai_chat_rejects_non_string_content` |
| L8 | AI accessor failure branch (KeyError/IndexError/TypeError) never executed by any test | FIXED-HERE — `test_ai_chat_rejects_malformed_response_shapes` (5 shapes) |
| L9 | Insights 1113 "not retried" promise unpinned at the urlopen level | FIXED-HERE — `test_insight_1113_makes_exactly_one_request_without_retry_or_sleep` |
| L10 | Insights retry-loop deadline/sleep-cap/3-attempt bound has no deterministic test (fake-clock harness) | OPEN | Fake clock whose `sleep` advances `monotonic`; eligible-429 mock; assert request counts, non-increasing timeouts ≤ 30, sleeps `[3, 8]`, no request after deadline |
| L11 | No negative test that non-busy `OperationalError` is NOT translated to `DatabaseBusyError` | FIXED-HERE — `test_non_busy_operational_errors_propagate_untranslated` |
| L12 | `CHILD_TABLE_SEEDS` completeness not asserted against person-scoped tables | FIXED-HERE — `test_child_table_seeds_cover_every_person_scoped_table` |
| L13 | Health-severity int assertion was satisfied by SQLite column affinity, not `clean_payload` | FIXED-HERE — pre-storage type assertions added |
| L24 | `test_person_medication_active_filter_lab_latest_password_reminder_insights_backup_and_csv` called `insights.collect_health_context` without `db_path`, so it fell back to `db.DB_PATH` and read the developer's real `data/phr.db`. It passed locally only because that file exists; CI failed with `unable to open database file`. The independent audit missed it for exactly that reason — passing locally concealed it — and it violates the AGENTS.md rule that tests use temporary database paths | CLOSED — instance fixed on main (PR #6 added `db_path=db_path`); the class is now closed too: PR #8 added the root `conftest.py` guard that fails any test opening a path under `db.DATA_DIR`, and PR #7 late-bound all 66 `db_path` defaults so none can resolve to the real `db.DB_PATH` behind a caller's back | Nothing outstanding. Both follow-ups this row asked for have landed |

## Low — documentation

| ID | Finding | Status | Post-merge check |
|----|---------|--------|------------------|
| L22 | `docs/CODEBASE_SWEEP.md` still documented removed `db.delete_records_for_person`; `get_connection` description omitted busy handling | FIXED-HERE (walkthrough lines; the historical changelog entry intentionally keeps the old name) |
| L23 | `PHR_LEARNING_PROTOCOL_2026-07-28.md:254-258` references five docs that do not exist on the branch | OPEN (pre-existing, intentionally untouched to avoid unrelated PR scope) | Annotate as planned-not-yet-created, or create stubs |

## Pre-existing residuals tracked elsewhere (not re-listed above)

- Medical post-validation of AI provider output — Open P1 in `AGENTS.md` / `docs/CODEBASE_SWEEP.md`.
- Locked-profile authorization at reusable context/export boundaries — Open P1, same locations.

## Post-merge audit procedure

After all in-flight branches merge:

1. Re-run `./scripts/verify.sh` and confirm every `FIXED-HERE` regression test above still exists and passes (grep the test names).
2. For each `OTHER-BRANCH` entry, locate the landed implementation and test; move to closed or reclassify `OPEN`.
3. For each `OPEN` entry, confirm it is still unaddressed and assign or consciously accept it.
4. Re-run the mutation spot-checks for L2/L3 (reintroduce the early-return / SELECT-then-mutate in a scratch copy; the merged suite must fail).
5. Delete closed rows; delete this file when empty.
