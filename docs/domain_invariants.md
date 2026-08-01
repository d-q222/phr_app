# PHR Domain Invariants

**Status:** authoritative. **Last verified against the repository:** 2026-08-01 (commit `2e8261e`, 159 tests passing).

This is the single file the full-stack migration is graded against. It consolidates invariants
previously scattered across `PHR_LEARNING_PROTOCOL_2026-07-28.md` ("PHR invariants"),
`PHR_PROJECT_INSTRUCTIONS_OPTIMIZED_2026-07-28.md` ("PHR invariants"), and `AGENTS.md` §4–5.
Where those disagree in wording, this file controls; where this file is silent, they still apply.

Each invariant below states **what must hold**, **why**, **how it is enforced today**, **which test
proves it**, and **what is not yet enforced**. An invariant with no enforcing test is an aspiration,
not an invariant — those are listed explicitly in §8.

A migrated component is only accepted when the invariants in this file hold in the *new* stack.
Preserving an invariant is not optional work that can be deferred to a later slice.

---

## 1. Person isolation

**One person's data must never appear in another person's view, summary, analytics, AI context,
retrieval result, export, or processing path.** Every operation is scoped to the selected or
authorized person. Never fall back to an implicit "first profile" when a patient reference is
unresolved — fail instead.

*Why:* this is the product. A family health record that can leak one member's data into another's
view has no privacy claim to make, and the failure is invisible to the user it harms.

### Enforced today

| Path | Mechanism | Location |
|---|---|---|
| Reads | `WHERE person_id = ?` appended when `person_id` is not None | `db.list_records`, db.py:197-199 |
| Creates | `person_id` force-set, overriding caller input | `services.create_item`, services.py:47-50 |
| Updates | ownership checked on the caller's connection before the write | `db._assert_owned` + `db.update_record` |
| Deletes | same | `db._assert_owned` + `db.delete_record` |
| Service API | `person_id` and `record_id` are **keyword-only** on `services.update_item`/`delete_item` — they are adjacent ints, so a silent swap would be an isolation failure rather than a visible error | services.py |
| Body map | reads exclusively through `services.list_items`, never `db` directly | `body_map_services.get_records_for_body_part`, body_map_services.py:176 |
| AI context | packet assembled per person | `ai_chat._patient_context_packet`, `insights.collect_health_context` |
| Demo/real separation | the effective tenant key is the pair `(active_db_path(), person_id)`; demo mode swaps the whole database file | `app.active_db_path`, `security._db_scope` |
| Locked profiles | health data masked in labels, tables, and banners | `app.profile_selection_label`, `app.display_safe_people` |

`db.RecordNotFound` deliberately does **not** distinguish "record does not exist" from "record is not
yours." Distinguishing them would let a caller probe for the existence of another profile's records.
This maps onto a single 404 in the future HTTP API — never a 403.

### Proven by

- `tests/test_basic.py:307` `test_update_item_rejects_a_record_owned_by_another_profile`
- `tests/test_basic.py:325` `test_delete_item_rejects_a_record_owned_by_another_profile`
- `tests/test_basic.py:372` `test_person_scoped_write_guard_covers_every_child_table` — all seven person-scoped tables
- `tests/test_basic.py:358` `test_person_and_record_ids_are_keyword_only_on_scoped_writes` — pins the API shape
- `tests/test_basic.py:452` `test_selected_json_backup_excludes_other_profiles`
- `tests/test_basic.py:750` `test_ai_chat_context_is_scoped_to_selected_person`
- `tests/test_basic.py:467` `test_demo_database_loads_sample_data_without_touching_real_profiles`
- `tests/test_basic.py:412` `test_profile_unlock_state_is_scoped_by_database`
- `tests/test_body_map_services.py:28` `test_retrieval_returns_only_selected_person_records`
- `tests/test_body_map_services.py:40` `test_every_record_adapter_applies_person_filter`
- `tests/test_body_map_ui.py:133` `test_profile_change_clears_stale_body_state`
- `tests/test_body_map_ui.py:343` `test_service_error_does_not_display_stale_profile_data`

Per `tests/AGENTS.md`: any profile-scoped feature must create **at least two profiles** and assert the
non-selected profile is absent from results, exports, summaries, and AI context.

### Deliberate, documented exceptions

These cross profiles on purpose. Each must stay explicit at the call site — never a silent default.

| Exception | Why | Guard |
|---|---|---|
| `db.list_records(person_id=None)` | returns all rows; `db.export_all_tables` depends on it | callers must pass `person_id=None` explicitly |
| `db.update_record` / `delete_record` with `person_id=None` | `people` has no `person_id` column; needed by `services.update_person`/`delete_person` | scoping a non-person-scoped table raises `ValueError` (tests/test_basic.py:398) |
| `fhir.export_bundle(person_id=None)` | whole-record-set export for interoperability | UI offers "All profiles" only when **no** profile is locked — app.py:1310-1320 |
| `imports_exports.import_json_backup` / `import_fhir_bundle` | restore operates on the whole database | not reachable per-profile; treat as an administrative operation |

**Migration requirement:** each exception must be re-justified in the new stack. An unscoped repository
method reachable from an HTTP route is a vulnerability regardless of its history here.

---

## 2. Provenance and integrity

**Preserve original values and source information. Never silently alter, merge, normalize,
reinterpret, or overwrite records.** Derived values and AI suggestions must be labeled, reviewable,
and reversible. Imports retain raw data, source, and provenance.

*Why:* a health record whose history can change underneath the user is not a record. Provenance is
also what makes an eventual provider-facing export defensible.

### Enforced today

- Validation rejects rather than coerces: `validation.py` validators return `list[str]` of messages and
  never mutate input.
- CSV import is row-atomic — invalid rows are reported in `{"imported": n, "skipped": [...]}`, never
  partially written (`imports_exports.import_labs_csv`, `import_wearables_csv`).
- Backup restore re-validates every row through `BACKUP_VALIDATORS` before writing.
- Restore uses `INSERT ... ON CONFLICT(id) DO UPDATE` (db.py) — **not** `INSERT OR REPLACE`, which would
  delete and recreate parent rows and orphan children.
- Body-map normalization never mutates the source record; stored mappings take precedence over defaults
  without rewriting them.
- `PRAGMA foreign_keys = ON` on every connection (`db.get_connection`).

### Proven by

- `tests/test_basic.py:218` `test_json_restore_upserts_existing_records_without_deleting_children`
- `tests/test_basic.py:240` `test_json_restore_rejects_malformed_backup_shapes`
- `tests/test_basic.py:645` `test_json_restore_rejects_semantically_invalid_rows`
- `tests/test_basic.py:104` `test_display_dataframe_keeps_unparseable_dates_unchanged`
- `tests/test_basic.py:575` `test_fhir_import_skips_bad_patient_references_and_missing_required_fields`
- `tests/test_body_map_services.py:73` `test_stored_mapping_takes_precedence_without_mutating_source`
- `tests/test_body_map_summary.py:181` `test_summary_does_not_mutate_input`

---

## 3. Truth labeling

**Clinician-diagnosed conditions, user-reported concerns, system-detected patterns, and AI-generated
explanations must remain distinct.** Never present a concern, wearable anomaly, statistical signal, or
AI inference as a diagnosis.

*Why:* collapsing these categories is how a wellness app becomes an unregulated diagnostic device, and
how a user comes to believe something about their health that no clinician ever said.

### Enforced today

- Abnormality is only asserted when the **source record** carries an abnormal flag or reference range —
  never inferred from a raw value.
- Historical source-flagged records stay visible even when a newer record is unflagged; current status
  may prefer the latest record, but history is not hidden.
- Mapping uncertainty is preserved rather than resolved (e.g. multi-system markers stay multi-system).

### Proven by

- `tests/test_body_map_summary.py:139` `test_raw_values_do_not_create_abnormal_flags`
- `tests/test_body_map_summary.py:66` `test_newer_unflagged_record_preserves_old_flag_as_historical`
- `tests/test_body_map_summary.py:82` `test_uncertain_mappings_return_mapping_uncertain`
- `tests/test_body_map_summary.py:90` `test_mixed_mapping_confidence_keeps_reliable_status_and_surfaces_uncertainty`
- `tests/test_body_map_config.py:195` `test_ast_mapping_preserves_multisystem_uncertainty`
- `tests/test_body_map_ui.py:321` `test_numeric_trends_exclude_nonnumeric_and_undated_values_without_fabrication`

---

## 4. Medical safety

**AI and rule output must remain explanatory and non-diagnostic.** Do not diagnose, prescribe,
recommend starting/stopping/changing medication or supplements, estimate prognosis, or suggest that
urgent symptoms can be managed at home. Preserve the medical disclaimer and urgent-care escalation.

Prefer cautious phrasing: "source-flagged," "may be worth discussing," "records show."

### Enforced today

- `insights.AI_SAFETY_INSTRUCTIONS`, `DISCLAIMER`, `URGENT_WARNING`, and `RED_FLAG_TERMS` gate the AI path.
- `insights.detect_possible_urgent_flags` runs before AI involvement.
- **Any new AI output path must have a rule-based or safe failure mode** and enforce the same
  constraints as `insights.py` and `ai_chat.py`.

### Proven by

- `tests/test_basic.py:665` `test_ai_insight_prompt_requires_safe_unobtrusive_suggestions`
- `tests/test_body_map_summary.py:174` `test_summary_language_is_non_diagnostic`

---

## 5. Privacy and external processing

**Never send health data to an external model automatically.** Show the data scope, remove unnecessary
identifiers, send the minimum necessary context, and never silently fall back from local to external
processing. Clearly distinguish local *storage* from local *inference* — "local-first" must not be
allowed to read as "never leaves the device."

### Enforced today

- No automatic external send; explicit user acknowledgement precedes any AI call.
- Context is minimized and byte-budgeted before transmission: `insights.compact_context_for_ai`,
  `ai_chat._fit_packet_to_budget`, with per-section row caps and field allowlists
  (`insights.AI_CONTEXT_LIMITS` / `AI_CONTEXT_FIELDS`).
- Chat history is not persisted to disk.
- Secrets are never read from or written to source control; the optional Zhipu key lives in Streamlit
  secrets, an env var, or the macOS Keychain (`ai_config.get_zhipu_api_key` precedence order).
- Tests never make real provider calls — the `urllib` boundary is mocked.

### Proven by

- `tests/test_basic.py:750` `test_ai_chat_context_is_scoped_to_selected_person`
- `tests/test_basic.py:790` `test_ai_chat_context_is_byte_limited`
- `tests/test_basic.py:66` `test_zhipu_api_key_prefers_streamlit_secret_then_env_then_keychain`
- `tests/test_basic.py:821` `test_ai_chat_api_key_prefers_streamlit_secret_then_env`

---

## 6. Deterministic fallback

**Rule-based behavior must continue when AI is unavailable.** The app is never dependent on an external
model to show a user their own records.

### Enforced today

`insights.generate_rule_based_insights` performs no network I/O. Provider failures are typed
(`ZhipuAPIError`, `ZhipuRetryableError`, `AIChatError` and subclasses) and degrade to rule-based output
or a clear message rather than an empty screen.

### Proven by

- `tests/test_basic.py:702` `test_ai_insight_retries_next_model_on_429`
- `tests/test_basic.py:726` `test_ai_insight_retries_next_model_on_timeout`
- `tests/test_basic.py:867` `test_ai_chat_handles_rate_limit`
- `tests/test_basic.py:920` `test_ai_chat_maps_auth_and_invalid_responses`
- `tests/test_basic.py:887` `test_ai_chat_falls_back_when_primary_model_has_no_resource_package`
- `tests/test_body_map_services.py:192` `test_database_error_is_not_reported_as_no_data` — a failure must not be rendered as "no data," which would read as clinically meaningful

---

## 7. Data handling and experimentation

- Treat `data/phr.db` as private user data. Never inspect, modify, delete, copy, or commit it unless
  explicitly asked and necessary.
- Tests use temporary database paths and fictional data only.
- Use parameterized SQL values and the existing table/column allowlists (`db.TABLE_COLUMNS`).
- **Experimental work must not mutate the real database without a migration and rollback plan.**
- Schema changes must be idempotent for existing databases and ship with regression tests.
- Do not commit secrets, local databases, exported backups, or real health data.

---

## 8. Not yet enforced — required properties of the target system

These are stated as invariants in the project documents but have **no enforcing mechanism today**.
They are requirements on the migration, not descriptions of current behavior. Listing them honestly
is the point: an unenforced invariant that reads as enforced is worse than no invariant.

| Property | Current reality | Owed by |
|---|---|---|
| Real authentication | none — anyone with the running app sees every unprotected profile. Profile passwords are a **local convenience lock**, explicitly not production authorization | slice 4 |
| Server-side authorization | unlock state is a per-browser `st.session_state` boolean with no expiry (`security.py`) | slice 4 |
| Encryption at rest | none | deferred, trigger recorded in `migration_map.md` |
| Audit logs | none — "critical operations are testable and auditable" is currently only half true | deferred |
| Consent tracking | none | deferred |
| Schema migration + rollback | **none.** `schema.sql` is all `CREATE TABLE IF NOT EXISTS`, so an added column silently no-ops on an existing `data/phr.db` and appears only in fresh databases. Tests pass because they build fresh databases. This makes the "idempotent schema changes" rule above unverifiable today | ADR-0003 / slice 3 |
| Role-based permissions, secure provider sharing | none | post-migration |

Known code-level issue, tracked in `current_system.md`: `fhir.py:73` uses `datetime.utcnow()`, which is
deprecated and scheduled for removal.

---

## 9. Changing this file

Adding, weakening, or removing an invariant is a **Critical** change under
`PHR_LEARNING_PROTOCOL_2026-07-28.md:138`: it requires design and threat assumptions, accept/reject
criteria, failure and isolation tests, a rollback path, full diff review, and documented residual risk.

An invariant is only "enforced" once a test fails when it is violated. When adding one, write the
failing test first and confirm it fails for the intended reason before making it pass.
