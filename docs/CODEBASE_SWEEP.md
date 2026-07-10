# Full Codebase Sweep

This document records a source-level sweep of the local-first Streamlit PHR app. It explains the role of each file and major code section, then lists the bugs, risks, and efficiency items reviewed during the audit.

Baseline before changes: `.venv/bin/python -m pytest -q` passed with 15 tests.

## Codebase Walkthrough

### `README.md`

The README is the product and operations guide. It describes the local-only MVP boundary, medical disclaimer, supported PHR features, setup commands, Streamlit run command, test command, profile-password behavior, CSV formats, JSON backup flow, FHIR mappings, provider/emergency exports, Health Insights behavior, optional Zhipu AI configuration, AI Chat behavior, limitations, and future roadmap.

Key intent: the app is explicitly not a production health platform and does not claim HIPAA readiness, encryption at rest, audit logging, production authentication, cloud sync, or emergency-care functionality.

### `requirements.txt`

The dependency list is intentionally small:

- `streamlit` for the web UI.
- `pandas` for display frames, charts, and CSV import/export helpers.
- `pytest` for tests.
- `python-dotenv` for optional local environment loading in AI config.

No new dependencies were added during this sweep.

### `schema.sql`

This file defines the SQLite schema initialized by `db.init_db`.

Main tables:

- `people`: family profiles and optional profile password metadata.
- `allergies`: profile-scoped allergy records.
- `medications`: profile-scoped medication records and status.
- `lab_results`: profile-scoped labs, values, units, reference ranges, flags, and dates.
- `health_entries`: profile-scoped timeline notes with body system/part and optional severity.
- `appointments`: profile-scoped appointment records.
- `reminders`: profile-scoped follow-up tasks.
- `wearable_records`: profile-scoped manual wearable metrics.

Each child table has a `person_id` foreign key. The schema does not use `ON DELETE CASCADE`, so application code must delete child records before deleting a profile.

Sweep change: added `CREATE INDEX IF NOT EXISTS` indexes for common profile/date/status/name/metric queries. This improves dashboard, filters, summaries, imports, and chart-backed reads without changing application behavior.

### `db.py`

This is the low-level persistence layer.

Constants:

- `APP_DIR`, `DATA_DIR`, `DB_PATH`, `SCHEMA_PATH` define local storage paths.
- `TABLES` defines import/export/delete order.
- `TABLE_COLUMNS` is the allowlist for each table. It prevents arbitrary column names from reaching SQL builders.

Connection and schema:

- `get_connection` opens SQLite with row dictionaries and `PRAGMA foreign_keys = ON`.
- `init_db` creates the DB parent folder and executes `schema.sql`.
- `now_iso`, `row_to_dict`, and `rows_to_dicts` are formatting helpers.

CRUD:

- `create_record`, `update_record`, `delete_record`, `get_record`, and `list_records` build SQL from allowlisted table and column names, with user values passed as parameters.
- `list_records` supports equality, `LIKE`, `>=`, `<=`, ordering, direction, and optional limits.
- `list_people` and `create_person` are table-specific conveniences.

Backup/restore:

- `export_all_tables` dumps every MVP table in stable table/id order.
- `import_all_tables` restores a backup table set.

Sweep changes:

- Added `delete_records_for_person` to delete all profile child records in one transaction instead of N+1 row deletes.
- Replaced restore-time `INSERT OR REPLACE` with real SQLite upsert semantics. This avoids deleting/reinserting parent rows, which can violate foreign keys or drop child records when restoring a backup over an existing DB.
- Added shape validation for backup table payloads so malformed JSON fails with clear `ValueError` messages.

### `models.py`

This file contains shared option lists used by validation and UI controls:

- `BODY_SYSTEMS`
- `MEDICATION_STATUSES`
- `LAB_FLAGS`
- `REMINDER_STATUSES`
- `APPOINTMENT_STATUSES`
- `WEARABLE_METRIC_TYPES`

These are the source of truth for user-facing selectbox choices and validators.

### `validation.py`

This module validates and normalizes form/import payloads before records are written.

Generic helpers:

- `is_blank`, `require`
- `valid_date`, `valid_date_order`
- `valid_number`, `normalize_optional_number`
- `valid_severity`
- `valid_choice`

Record validators:

- `validate_person`
- `validate_medication`
- `validate_allergy`
- `validate_lab`
- `validate_health_entry`
- `validate_appointment`
- `validate_reminder`
- `validate_wearable`

The validators currently enforce the local MVP schema and controlled choice lists. They do not attempt clinical validation or coded terminology validation.

### `security.py`

This module implements local-only profile protection.

Password storage:

- `hash_password` creates PBKDF2-HMAC-SHA256 hashes with random salt.
- `verify_password` parses stored hashes and compares with `hmac.compare_digest`.

Session locking:

- `_unlocked_key`, `is_profile_unlocked`, `unlock_profile`, and `lock_profile` store per-profile unlock state in Streamlit `session_state`.
- `health_data_visible` gates health-data pages based on whether password protection is enabled and whether the profile is unlocked.

This is lightweight local protection only. It is not full app authentication and does not encrypt the SQLite DB.

### `services.py`

This is the business/query layer over `db.py`.

Profile operations:

- `get_person`, `list_people`, `create_person`, `update_person`, `delete_person`.

Generic record operations:

- `create_item`, `update_item`, `delete_item`, `list_items`.

Summary/query helpers:

- `active_medications`
- `latest_labs`
- `abnormal_labs`
- `recent_health_entries`
- `upcoming_appointments`
- `overdue_reminders`
- `due_soon_reminders`
- `wearable_summary`
- `dashboard_data`

Filter helpers:

- `_date_filter`
- `filter_health_entries`
- `filter_labs`
- `medication_filters`
- `reminder_filters`

Markdown exports:

- `generate_provider_summary`
- `generate_emergency_snapshot`

Sweep changes:

- `delete_person` now uses bulk child deletion through `db.delete_records_for_person`.
- Added robust date parsing for reminder due-date calculations. Invalid imported reminder dates are skipped instead of being compared lexicographically or raising errors.

### `imports_exports.py`

This module handles interchange formats.

CSV:

- `import_labs_csv` reads lab CSV files, validates each row, normalizes numeric fields, imports valid rows, and reports skipped rows.
- `import_wearables_csv` does the same for wearable records.
- `sample_labs_csv` and `sample_wearables_csv` generate example CSV files.

JSON backup:

- `export_json_backup` wraps `db.export_all_tables`.
- `import_json_backup` parses JSON and delegates to `db.import_all_tables`.

FHIR and Markdown wrappers:

- `export_fhir_bundle`
- `import_fhir_bundle`
- `provider_summary_markdown`
- `emergency_snapshot_markdown`

Sweep change: `import_json_backup` now validates that the top-level JSON and optional `tables` key are objects before importing.

### `fhir.py`

This module maps between local records and FHIR JSON.

Public API:

- `SUPPORTED_FHIR_VERSIONS` and `FHIR_MIME_TYPE`.
- `normalize_fhir_version`.
- `export_bundle`.
- `import_bundle`.

Export mapping:

- `people` -> `Patient`
- `allergies` -> `AllergyIntolerance`
- `medications` -> `MedicationStatement`
- `lab_results`, `health_entries`, `wearable_records` -> `Observation`
- `appointments` -> `Appointment`
- `reminders` -> `Task`

Import mapping:

- `_resources_from_payload` accepts a Bundle or a single resource.
- Patient resources are imported first and indexed in `patient_map`.
- Other resources resolve the patient reference, map into a local table/payload, and are inserted via `services.create_item`.
- Unsupported or unlinked resources are reported in `skipped`.

Version-specific behavior:

- R4 and R5 medication/reason fields differ.
- R4 and R5 allergy reaction manifestation shape differs.
- Appointment notes differ between `comment` and `note`.

Known boundary: this is an interoperability MVP. It preserves useful human-readable data but does not implement SMART-on-FHIR auth, implementation-guide profiles, terminology coding, or external EHR validation.

### `ai_config.py`

This module centralizes Zhipu/BigModel configuration.

Settings:

- Defaults for insight model, fallback models, response token budget, context byte budget, API URL, and provider.
- Environment variables can override model, fallback, max tokens, context bytes, provider, and API URL.

API key lookup:

- `_get_streamlit_secret`
- `_get_keychain_password`
- `get_zhipu_api_key`
- `zhipu_key_configured`
- `store_zhipu_api_key`

Sweep change: `get_zhipu_api_key` now uses the same precedence as AI Chat: Streamlit secrets first, then environment variables, then macOS Keychain. This prevents an old Keychain value from unexpectedly overriding an explicit deployment secret or environment override.

### `insights.py`

This module builds Health Insights.

Safety constants:

- `DISCLAIMER`
- `URGENT_WARNING`
- `AI_SAFETY_INSTRUCTIONS`
- `RED_FLAG_TERMS`
- AI context limits and field allowlists.

Context collection and compaction:

- `collect_health_context` gathers selected-profile records by include flags and date range.
- `detect_possible_urgent_flags` scans selected record text for red-flag terms.
- `_average_metric`, `_weight_change`, `_compact_row`, `_fit_packet_to_budget`, and `compact_context_for_ai` build a small AI-safe packet.

Zhipu request handling:

- `ZhipuAPIError` and `ZhipuRetryableError` model provider failures.
- `_parse_http_error`, `_call_zhipu_chat_completion`, `_build_zhipu_request`, and `_call_zhipu_with_model_fallback` handle HTTP calls, 429 retry behavior, timeouts, and fallback models.
- `validate_zhipu_connection` checks the configured key/model with a tiny request.

Report generation:

- `generate_rule_based_insights` produces local-only Markdown.
- `build_ai_insight_prompt` builds a compact safety-constrained JSON prompt.
- `generate_ai_insight_result` calls AI only when enabled and configured, and otherwise returns the rule-based report with warnings.

Important safety behavior: AI output is forced to include the local medical disclaimer if the provider omits it.

### `ai_chat.py`

This module powers selected-profile AI chat.

Constants:

- Privacy notice, example questions, context size limits, default chat model/tokens/temperature, and timeout.

Errors:

- `AIChatError`, `MissingAPIKeyError`, `RateLimitError`, `NetworkAIChatError`, `InvalidAIResponseError`.

Context building:

- `chat_model_candidates` chooses chat model fallback order.
- `get_zhipu_api_key` uses Streamlit secrets, then environment variables, then the shared Keychain lookup.
- `_patient_context_packet` builds selected-profile-only context from services and insights.
- `build_patient_context` serializes that packet for tests and requests.
- `_has_health_data` blocks chat when the selected profile has no records.

Provider calls:

- `build_ai_system_prompt` defines the safety and scoping rules.
- `call_zhipu_chat` iterates candidate models.
- `_call_zhipu_chat_model` sends the request, parses errors, and validates the response shape.

Streamlit rendering:

- `_history_key` scopes chat history by DB path and person ID.
- `_render_message`, `_example_questions`, and `render_ai_chatbot` render the chat UI and keep chat history only in `session_state`.

### `app.py`

This is the Streamlit application entrypoint and router.

Configuration and navigation:

- `SAMPLE_DATA_PATH`, demo mode keys, `PAGES`, `NAV_SECTIONS`, `PAGE_EMOJIS`, action labels, descriptions, display labels, hidden columns, date columns, and CSS.
- `page_navigation` stores current page in session state.
- `page_button_label`, `action_button_label`, and `warning_label` format UI labels.

Display helpers:

- `format_label`, `display_column_label`, `format_display_date`, `format_display_datetime`, `display_dataframe`, `dataframe`.
- `apply_global_styles`, `page_header`, and `selected_profile_banner`.

Demo mode:

- `create_demo_database` loads `sample_test_data.json` into a temp DB.
- `is_demo_mode`, `active_db_path`, `start_demo_mode`, `exit_demo_mode`, `demo_mode_controls`.

Forms and profile handling:

- `show_errors`, `clean_payload`, `input_field`.
- `selected_profile_sidebar`, `unlock_screen`, `require_profile`.
- `toggle_add_form`, `close_form`, `record_label`, `profile_form`, `password_settings`, `ai_settings`.

Pages:

- `page_profiles`
- `generic_record_page`
- `page_dashboard`
- `page_provider_summary`
- `page_emergency_snapshot`
- `page_import_export`
- `page_insights`
- `page_ai_chat`

Main router:

- `main` initializes Streamlit, applies CSS, initializes the real DB, renders sidebar controls, gates password-protected health-data pages, and dispatches to the selected page.

Important behavior: Settings and Profiles are available before health-data unlock; health-data pages require `security.health_data_visible`.

### `sample_test_data.json`

This file contains fictional demo-mode profiles and related records. It is imported into a temporary session database by `create_demo_database`. It should not affect the real `data/phr.db`.

### `tests/test_basic.py`

This is an integration-oriented pytest suite.

Existing coverage includes:

- Database/schema initialization.
- AI default model settings.
- DataFrame display formatting.
- Core CRUD, active medications, latest labs, profile password checks, reminders, insights, JSON backup, and CSV import.
- Demo database isolation.
- FHIR R4/R5 export/import round trip.
- AI insight safety prompt and retry behavior.
- AI chat selected-profile scoping, API key precedence, defaults, rate-limit handling, and fallback behavior.

Sweep additions:

- Index creation checks.
- Shared AI config API-key precedence.
- JSON restore upsert over existing parent/child records.
- Malformed JSON backup shape validation.
- Invalid reminder date handling.
- Bulk profile deletion child cleanup.

### `.devcontainer/devcontainer.json`

Defines the Python 3.11 dev container image, VS Code/Codespaces defaults, install command, Streamlit post-attach command, and port `8501` forwarding.

### `.gitignore`

Ignores local secrets, env files, caches, local SQLite DB files, virtualenv, bytecode, and OS/editor artifacts.

### Local/generated files not audited as source

- `.streamlit/secrets.toml`: sensitive local secrets; intentionally not read.
- `data/phr.db`: local private SQLite data; intentionally not inspected as product source.
- `.venv/`, `.pytest_cache/`, `.git/`, `.DS_Store`, `.Rhistory`: environment/tooling artifacts.

## Prioritized Findings And Changes

### P1 - JSON restore could break foreign-key integrity

Previous behavior: `db.import_all_tables` used `INSERT OR REPLACE`. In SQLite, `REPLACE` deletes the conflicting row before inserting the new one. Restoring a backup over an existing DB with child records could violate foreign keys or remove related data.

Change: restore now uses `INSERT ... ON CONFLICT(id) DO UPDATE`, preserving parent rows and child references.

Regression: `test_json_restore_upserts_existing_records_without_deleting_children`.

### P1 - Malformed backup JSON failed unclearly

Previous behavior: non-object JSON or invalid `tables` shape could raise incidental attribute/type errors.

Change: `import_json_backup` and `db.import_all_tables` now validate top-level, table, and row shapes with clear `ValueError` messages.

Regression: `test_json_restore_rejects_malformed_backup_shapes`.

### P2 - AI API key precedence differed between Insights and Chat

Previous behavior: AI config preferred Keychain before env/secrets and preferred env before Streamlit secrets. AI Chat preferred Streamlit secrets, then env, then shared config fallback.

Change: AI config now also prefers Streamlit secrets, then env vars, then Keychain.

Regression: `test_zhipu_api_key_prefers_streamlit_secret_then_env_then_keychain`.

### P2 - Profile deletion did N+1 child deletes

Previous behavior: `services.delete_person` listed each child table and deleted records row by row.

Change: added `db.delete_records_for_person` to delete each child table by `person_id` in one transaction before deleting the profile.

Regression: `test_delete_person_removes_child_records`.

### P2 - Reminder due-date calculations were brittle for imported bad dates

Previous behavior: overdue logic compared raw values lexicographically; due-soon logic could fail on non-string/null values.

Change: reminder calculations now parse ISO dates and skip invalid due dates.

Regression: `test_invalid_reminder_dates_are_skipped_in_due_calculations`.

### P3 - Common filtered reads lacked SQLite indexes

Previous behavior: profile/date/status/name filters could scan whole tables as data grew.

Change: added `CREATE INDEX IF NOT EXISTS` indexes for profile-scoped lists, date filters, status filters, and metric/test filters.

Regression: `test_database_initializes` now verifies representative indexes.

## Follow-Up Implementation

The next sweep batch addressed the highest-value remaining risks from the original follow-up list.

### P0 - Locked profile admin bypasses

Previous behavior: Profiles and Settings rendered before the health-data unlock gate, and password settings could be reached from those admin pages.

Change: locked protected profiles are masked in profile-selection/table helpers, password settings require unlock, and unlock state is scoped by database path plus person ID so demo databases and restored databases do not collide with real profile IDs.

Regressions: `test_profile_unlock_state_is_scoped_by_database`, `test_locked_profiles_are_masked_in_display_helpers`.

### P1 - Cross-profile export leakage

Previous behavior: FHIR had an all-profile export option and JSON backup always exported every table for every profile.

Change: export UIs default to selected profile, JSON backup supports selected-profile scope, and all-profile export is unavailable while any protected profile remains locked.

Regression: `test_selected_json_backup_excludes_other_profiles`.

### P1 - FHIR import could mis-attach or fabricate data

Previous behavior: unresolved patient references could fall back to the first imported Patient, and incomplete FHIR resources could receive today's date or a zero wearable value.

Change: unresolved patient references are skipped, fallback is only used when exactly one Patient exists and a resource has no patient reference, imported resources are validated before writing, and required dates/values are no longer fabricated.

Regression: `test_fhir_import_skips_bad_patient_references_and_missing_required_fields`.

### P2 - FHIR medication and lab edge cases

Previous behavior: medication dose/frequency round trips were lossy, and latest-lab selection was unstable for duplicate same-test/same-date rows.

Change: local FHIR medication extensions preserve separate dose and frequency fields, and `latest_labs` now tie-breaks by newest record ID after lab date.

Regressions: `test_fhir_r4_and_r5_export_and_import_round_trip`, `test_latest_labs_tie_breaks_same_day_by_newer_record`.

### P2 - Restore and stored numeric robustness

Previous behavior: JSON restore validated shape but not semantic row contents, and malformed stored wearable values could crash summary/insight generation.

Change: JSON restore rows pass through existing validators and numeric coercion before import, and wearable summary/insight calculations skip non-numeric stored values.

Regressions: `test_json_restore_rejects_semantically_invalid_rows`, `test_malformed_wearable_values_do_not_crash_summaries`.

### P2 - AI config, context, and consent

Previous behavior: blank model env values could enter model candidates, AI Chat context had row limits but no serialized byte limit, and AI actions were notice-only.

Change: blank AI model candidates are ignored, AI Chat context is byte-budgeted, AI Chat and AI Insights require explicit context-sharing acknowledgement, and additional fake network tests cover auth, malformed responses, and timeout retries.

Regressions: `test_zhipu_model_candidates_ignore_blank_primary`, `test_ai_chat_context_is_byte_limited`, `test_ai_chat_maps_auth_and_invalid_responses`, `test_insight_urlopen_timeout_retries_without_real_sleep`.

## Remaining Risks And Follow-Ups

- Streamlit UI behavior is mostly tested through pure helpers and service functions, not browser-driven interaction.
- FHIR support remains intentionally lightweight and human-readable; production EHR interoperability would need implementation-guide validation, coded vocabularies, and SMART-on-FHIR flows.
- Local profile passwords do not encrypt the database and are not production authentication.
- CSV imports rely on pandas and row-level validation; very large files are not streamed.
- AI provider calls are unit-tested with fakes only; no real provider calls are made in tests.
- Existing SQLite DBs get new indexes on the next `db.init_db()` call, which happens during app startup.
