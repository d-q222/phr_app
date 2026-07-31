# PHR Project Source of Truth
**Current-state inventory, complete functionality backlog, future direction, inconsistencies, gaps, and feasibility flags**

**Repository reviewed:** `d-q222/phr_app`  
**Repository state reviewed:** July 14, 2026  
**Product and development decisions updated:** July 28, 2026  
**Document purpose:** Preserve every distinct PHR functionality, behavior, architectural requirement, safety rule, and future idea discussed so far. This is an inventory, not a prioritized roadmap.

---

## 0. How to read this document

### Status labels

- **IMPLEMENTED — REPOSITORY-CONFIRMED:** Explicitly described as present in the current public repository.
- **IMPLEMENTED — PARTIAL / UX BLOCKED:** Code or data support exists, but the intended user behavior is incomplete or currently malfunctioning.
- **DECIDED — NOT YET IMPLEMENTED:** The user explicitly decided this should be built.
- **PLANNED / ACCEPTED DIRECTION:** Discussed and retained as part of the project direction, but not necessarily specified enough to implement immediately.
- **CONDITIONAL / LATER:** Retained as a future option, usually after migration or foundational work.
- **SUGGESTED — NOT CONFIRMED:** Suggested during prior discussions but not clearly accepted as a requirement.
- **REJECTED / SUPERSEDED:** Previously suggested or framed in a way the user later changed.
- **UNKNOWN:** Repository and prior discussion do not establish whether it works end to end.

### Evidence hierarchy used

Use different authorities for different questions:

- **Current implementation status:** the latest inspected repository and test evidence.
- **Product goals, priorities, and development method:** the user's latest explicit decision.

Then use:

1. This source-of-truth document.
2. The current PHR AI-native building and learning protocol.
3. Explicit decisions in prior PHR conversations.
4. Uploaded PHR development and research notes.
5. External research.
6. Assistant suggestions that were not explicitly accepted.

When sources conflict, record the conflict rather than silently reconciling it.

---

# Part I — Current App: What Exists Now

## 1. Current product definition

### IMPLEMENTED — REPOSITORY-CONFIRMED

The current application is:

- A **local-first family personal health record prototype**.
- Built with **Python and Streamlit**.
- Backed by a **local SQLite database**.
- Intended for **local personal use during MVP development**.
- Not a public production health platform.
- Not a medical device.
- Not intended for diagnosis, prescription decisions, treatment decisions, or emergency use.
- Designed to keep health data on the user’s device by default.
- Capable of optional external AI use only after a user action.

### Current technical shape

- Main Streamlit application.
- SQLite schema and persistence layer.
- Data models.
- Validation.
- Services.
- Security helpers.
- Import/export services.
- FHIR services.
- Rule-based insights.
- AI configuration and AI chat.
- Dedicated body-map configuration, services, summary, UI, and custom component code.
- Tests.
- Documentation.
- Codex/agent instructions.
- Sample data and demo mode.

### Current major files visible in the repository

- `app.py`
- `models.py`
- `db.py`
- `services.py`
- `validation.py`
- `security.py`
- `imports_exports.py`
- `fhir.py`
- `insights.py`
- `ai_config.py`
- `ai_chat.py`
- `body_map_config.py`
- `body_map_services.py`
- `body_map_summary.py`
- `body_map_ui.py`
- `components/body_map/`
- `schema.sql`
- `sample_test_data.json`
- `tests/`
- `docs/`
- `scripts/`
- `AGENTS.md`
- `.codex/`

### Current architecture warning

- `app.py` is approximately 1,500 lines.
- This is inconsistent with the earlier architectural goal of avoiding a large monolithic application file.
- The project has extracted several modules, but page routing and UI logic remain heavily centralized.

---

## 2. Family and profile management

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Multiple family profiles.
- A currently selected profile.
- Profile-specific dashboard.
- Health data scoped to the selected profile.
- Separate records for each profile.
- Demo mode with sample family data.
- Demo data stored in a temporary session database.
- Optional lightweight password per profile.
- Passwords hashed using PBKDF2-HMAC with random salt.
- Plaintext passwords are not stored.
- Unlock state stored in Streamlit session state.
- Locked profiles show an unlock screen instead of health-data pages.
- No password recovery in the current MVP.
- Forgotten passwords require direct local database reset.

### Previously decided profile behavior

- Selected-person isolation is an invariant.
- No record from one family member should appear in another person’s dashboard, body map, AI context, summary, or filter results.
- Dependents should be separate profiles, not blended into a parent’s record.
- Sex-specific body or health data should be supported where relevant.
- The interface should not assume every family member has the same permissions or relationship to the account owner.

### DECIDED — NOT YET IMPLEMENTED

- Role-based family permissions.
- Different access levels for adults, caregivers, children, and dependents.
- Consent tracking.
- Explicit sharing consent per person.
- Clear provenance for who entered or changed a record.
- More robust account-level authentication.
- Password recovery or account recovery.
- Production session management.

### Gap

The current app has **profile separation**, but not a complete **family authorization model**. A local profile password is not equivalent to account security, caregiver authorization, minor consent, or legal access control.

---

## 3. Core health record CRUD

### IMPLEMENTED — REPOSITORY-CONFIRMED

The current application has create/read/update/delete pages or flows for:

- Allergies.
- Medications.
- Lab results.
- Health timeline entries.
- Appointments.
- Reminders.
- Wearable records.
- Family profiles.

### Implemented or repository-described filters

- Date.
- Body system.
- Body part.
- Medication status.
- Lab flag.
- Reminder status.
- Keyword search where useful.
- Selected profile.

### Earlier data-model requirements retained

- Raw values should be preserved.
- Dates should be associated with records.
- Medication active/inactive status.
- Lab numeric value where available.
- Lab textual result where appropriate.
- Units.
- Reference low and high.
- Lab flag.
- Notes.
- Source/provenance.
- Body system.
- Body part or organ.
- Timeline ordering.
- Newest-to-oldest and recent-entry views.
- Overdue follow-up logic.
- Duplicate detection.
- Input validation.
- Friendly validation errors.

### UNKNOWN / NEEDS AUDIT

- Whether every CRUD page supports editing as cleanly as creating/deleting.
- Whether all records retain source provenance consistently.
- Whether duplicate prevention is applied across all record types.
- Whether data deletion has undo, confirmation, or soft-delete behavior.
- Whether medication dose, route, frequency, prescriber, indication, and adherence are fully represented.
- Whether allergies distinguish drug, food, environmental, intolerance, severity, reaction, and verification status.
- Whether appointments distinguish scheduled, completed, canceled, and no-show.
- Whether reminders have robust recurrence rules.

---

## 4. Dashboard and summary views

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Profile-specific dashboard.
- Record filters.
- Rule-based Health Insights report.
- Provider summary.
- Emergency snapshot.
- Body-map-linked summary/filtering.
- Upcoming appointment display.
- Abnormal-lab display.
- Wearable summary signals.
- Missing-data indicators.

### Current Health Insights output includes

- Active medication count.
- Overdue reminder count.
- Abnormal or critical labs.
- Missing lab reference ranges.
- Common body systems in health entries.
- Recent symptom entries.
- Average steps when available.
- Average sleep when available.
- Weight change when available.
- Upcoming appointments.
- Missing-data areas.
- Safety disclaimer.
- Red-flag urgent-care warning language when specified terms appear.

### Current red-flag language triggers include terms related to

- Chest pain.
- Stroke symptoms.
- Severe shortness of breath.
- Severe allergic reaction.
- Suicidal thoughts.
- Severe bleeding.
- Fainting.
- Loss of consciousness.

### DECIDED — NOT YET IMPLEMENTED OR NOT CONFIRMED

- A clearer longitudinal timeline that unifies records from different sources.
- Trend views that can be toggled on and off.
- Persistent non-diagnostic flags that remain visible until superseded by newer data.
- A more adaptive dashboard based on the person’s condition, concern, data, or recent events.
- More explicit separation between “record,” “trend,” “flag,” “concern,” and “insight.”
- User-configurable dashboard widgets.
- More visual analytics similar to Oura.
- Personal-baseline analysis rather than only population/reference-range comparison.
- Provider-ready summaries that explain trends and data provenance.
- Clear traceability from every summary statement back to underlying records.

---

## 5. Body map and anatomical filtering

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Dedicated body-map subsystem.
- Profile-specific body map.
- Interactive body-map component.
- Organ highlighting.
- Record filtering tied to body-map selection.
- Body system and body part configuration.
- Default organ-to-system mapping.
- Relevance types.
- Tests for at least part of the body-map configuration.
- Body-map summary and services separated from the main application.
- Existing assets folder and custom component folder.

### IMPLEMENTED — PARTIAL / UX BLOCKED

Known current blocker:

- Clicking a body region can redirect to the dashboard rather than filter in place.
- Intended behavior is to remain on the same page.
- Intended behavior is to apply the selected body part/organ filter immediately.
- Intended behavior is to visibly highlight the selected region.
- Selection and filtering should remain synchronized.
- Existing functionality should not be broken while replacing or improving the model.

### Explicitly decided visual requirements

- Clean medical infographic appearance.
- Servier-like visual style was preferred as a reference.
- Sex-neutral model.
- Front view first.
- Back view later.
- Front/back toggle later.
- Layer toggles later.
- Systems and organs as possible layers.
- One body model first rather than multiple simultaneous models.
- Simple organ shapes.
- Selected system should become more prominent.
- Organs first, then systems, was discussed as the initial hierarchy.
- A selected organ should highlight.
- A selected organ should filter relevant records.
- Cross-system relevance should be supported.
- Visual assets should be replaceable later.
- The implementation should not lock the project into one irreversible set of anatomical graphics.
- Codex should receive assets in a clear folder structure.
- The body map should preserve current filtering functionality while visuals change.

### Explicitly decided data behavior

- Default organ-to-system mappings.
- User override of mappings later or where supported.
- Unknown labs should have an AI-assisted mapping option.
- Mapping should preserve raw values.
- Body part and body system filtering should work across the complete record history by default.
- A more recent-only view may be offered where it is more useful.
- Flags associated with body parts should persist until newer data resolves or supersedes them.
- Trends toggle.
- Light, non-diagnostic flags.
- Cross-system relationships.
- Selected-person isolation.
- Sex-specific anatomy where necessary.
- No modifications to the existing database file as an implementation invariant during certain body-map phases.
- No secrets added.
- Non-diagnostic language.

### Gaps and unresolved design questions

- Anatomical ontology is not fully specified.
- “Body part,” “organ,” “system,” “region,” and “symptom location” may overlap.
- A lab may map to multiple organs/systems with different relevance strengths.
- Diagnoses, symptoms, procedures, imaging, medications, and wearables require different mapping semantics.
- The source of a mapping needs provenance: default rule, user override, imported code, or AI suggestion.
- The user needs a way to correct an incorrect map assignment.
- Front-only anatomy cannot represent all meaningful areas.
- A sex-neutral figure may not support sex-specific organs without layers or profile-aware anatomy.
- A Servier-derived asset workflow needs license and attribution review.
- In-place interaction may remain awkward in Streamlit and is one reason full-stack migration is relevant.

---

## 6. Laboratory data

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Lab CRUD.
- Lab CSV import.
- Required test name and date.
- Numeric value support.
- Text result support.
- Unit.
- Reference low.
- Reference high.
- Lab flag.
- Notes.
- Allowed lab flags:
  - Normal.
  - High.
  - Low.
  - Abnormal.
  - Critical.
  - Unknown.
- Lab date filtering.
- Abnormal-lab display.
- Missing-reference-range detection.
- FHIR export/import as Observation.
- Inclusion in provider summaries.
- Inclusion in emergency snapshot for recent abnormal labs.
- Inclusion in optional AI context in compact form.

### DECIDED — NOT YET IMPLEMENTED OR NOT CONFIRMED

- Preserve the imported raw value and original lab wording.
- Normalize units without overwriting the original.
- Later reference-range support more robust than user-entered low/high.
- Reference ranges adjusted for:
  - Lab.
  - Age.
  - Sex.
  - Pregnancy where relevant.
  - Units.
  - Collection context.
- Trend charts by analyte.
- Latest result for each test.
- Longitudinal comparison.
- Personal baseline.
- Duplicate import handling.
- Source tracking for manual, CSV, FHIR, EHR, and provider records.
- Mapping unknown lab names to standard concepts.
- AI-assisted unknown-lab mapping.
- Standard terminology support such as LOINC.
- Clinically meaningful grouping into panels.
- Recognition that “normal” reference range is not always the same as the individual’s baseline.
- Provider-ready interpretation questions without diagnosis.
- Clear distinction between a lab flag supplied by a source and a flag computed by the app.

### Gap

The current record structure supports labs, but a production longitudinal lab product requires terminology normalization, unit conversion, source-specific reference ranges, duplicate reconciliation, and provenance.

---

## 7. Medications and allergies

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Medication CRUD.
- Active medication counting.
- Medication status filtering.
- Allergy CRUD.
- Active medications in emergency snapshot.
- Allergies in emergency snapshot.
- Medication and allergy context sent to optional AI in compact form.
- FHIR mapping:
  - Medications to `MedicationStatement`.
  - Allergies to `AllergyIntolerance`.

### DECIDED / DISCUSSED FUNCTIONALITIES

- Medication reminders.
- Active medication logic based on dates/status.
- Check whether a medication is already present.
- Provider summary of medications and allergies.
- Medication questions for clinician discussion.
- No AI prescription advice.
- No AI medication changes.
- No AI supplement changes.
- No ungrounded interaction warnings presented as a diagnosis.
- Source/provenance for medication records.
- User-entered versus imported medication distinction.

### UNKNOWN / NEEDS AUDIT

- Dose.
- Dose unit.
- Route.
- Frequency.
- Start date.
- End date.
- Prescriber.
- Indication.
- As-needed status.
- Adherence.
- Refill state.
- Medication reconciliation.
- Duplicate drug normalization.
- RxNorm coding.
- Allergy reaction and severity.
- Allergy verification status.
- Intolerance versus immune-mediated allergy.
- Historical versus active allergy.

---

## 8. Timeline and health entries

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Health timeline entry CRUD.
- Date filtering.
- Body-system filtering.
- Body-part filtering.
- Keyword search.
- Recent symptom entries in rule-based insights.
- FHIR export/import as Observation.
- Inclusion in provider summary.
- Inclusion in optional AI context.

### DECIDED / DISCUSSED

- Health entries need:
  - Title.
  - Date.
  - Body system.
  - Body part.
  - Note.
  - Source.
- Newest entry.
- Recent entries.
- Entries from the last 30 days.
- Full-history view.
- Symptom check-ins.
- Structured patient-reported outcomes.
- Cross-record timeline.
- Trends toggle.
- Persistent flags until newer data resolves them.
- Structured patient-reported outcomes and symptom check-ins should become a core input, not remain only free-text notes.
- Symptoms entered by a user must not be labeled as diagnoses.
- Concern tracking should be explicit.

### Gap

A generic timeline entry is flexible but weak for analytics. Symptoms, procedures, diagnoses, imaging, encounters, patient-reported outcomes, and notes should eventually be distinct typed records or normalized events.

---

## 9. Appointments, reminders, and calendar functions

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Appointment CRUD.
- Reminder CRUD.
- Upcoming appointment display.
- Overdue reminder detection.
- Reminder status filtering.
- FHIR mapping:
  - Appointments to `Appointment`.
  - Reminders to `Task`.
- Inclusion in optional AI context.
- Inclusion in summaries where relevant.

### DECIDED / DISCUSSED

- Medication reminders.
- Appointment reminders.
- Checkup reminders.
- Due soon.
- Overdue.
- Repeat every N days.
- Recurrence.
- Calendar view.
- Daily-use workflow.
- Follow-up tracking.
- Provider-recommended follow-up tracking.
- Notification support in a production app.
- Clear completed, dismissed, snoozed, overdue, and canceled states.

### UNKNOWN / GAP

- No confirmed external calendar integration.
- No confirmed device notifications.
- No confirmed email/SMS reminders.
- No confirmed recurrence engine beyond basic stored reminders.
- No confirmed timezone strategy.
- No confirmed medication adherence logging.

---

## 10. Wearable records and analytics

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Wearable record CRUD.
- Wearable CSV import.
- Fields include:
  - Metric type.
  - Numeric value.
  - Unit.
  - Timestamp.
  - Source.
- Current supported conceptual examples include:
  - Steps.
  - Heart rate.
  - Sleep.
  - Weight.
- Average steps in insights.
- Average sleep in insights.
- Weight change in insights.
- FHIR export/import as Observation.
- Inclusion in provider summary when selected.
- Inclusion in optional AI context as compact summaries.
- No live wearable API integration.

### DECIDED PRODUCT DIRECTION

The retained product direction is:

- Build **wearable-to-PHR/EHR ingestion**.
- Perform **longitudinal personal-baseline trend detection**.
- Generate **provider-ready summaries**.
- Use wearable information as one input to a broader longitudinal health record.
- Avoid simply copying the Oura interface.
- Use AI agents to implement the analytics pipeline where efficient.
- The user must own the statistical method, assumptions, data-quality policy, tests, interpretation, and safety boundaries, but does not need to type the implementation manually.
- Keep the project educational enough that the user can specify, review, verify, direct changes to, and diagnose the ingestion and analytics system.
- Consider Oura API as a cleaner API/data option.
- Consider lower-cost devices such as Colmi for experimentation.
- Later integrate wearable work into the PHR rather than keeping it permanently separate.

### DECIDED — NOT YET IMPLEMENTED

- Live Oura API ingestion.
- Live Apple Health ingestion.
- Live Fitbit ingestion.
- Live Garmin ingestion.
- Live Google Fit / Health Connect ingestion.
- Device-specific import adapters.
- Deduplication by source identifier.
- Timestamp/value fallback deduplication.
- Unit normalization.
- Time-zone normalization.
- Data-quality scoring.
- Missing-wear detection.
- Sensor confidence/quality.
- Daily aggregation.
- Rolling averages.
- Personal baseline.
- Deviation from baseline.
- Trend detection.
- Change-point detection.
- Sleep analysis.
- Resting heart-rate analysis.
- HRV analysis.
- Activity analysis.
- Recovery/readiness-like analysis without copying proprietary scores.
- Correlations between symptoms, medications, labs, and wearables.
- Provider-ready summary of meaningful deviations.
- Explainability for each detected trend.
- Raw-data drill-down.
- Provenance of every metric.
- Imported data reconciliation.
- User control over which wearable metrics are retained or shared.

### Feasibility issue

Consumer wearable data can support wellness and longitudinal pattern detection, but it cannot reliably establish diagnosis. Device data quality, API access, missingness, proprietary algorithms, and inconsistent metric definitions must be handled explicitly.

---

## 11. Import, export, backup, and portability

### IMPLEMENTED — REPOSITORY-CONFIRMED

- CSV import for lab results.
- CSV import for wearable records.
- Full JSON backup.
- JSON restore.
- Restore into current database.
- Option to clear existing records first.
- FHIR R4 Bundle export.
- FHIR R5 Bundle export.
- FHIR R4 Bundle import.
- FHIR R5 Bundle import.
- Markdown provider-summary download.
- Markdown emergency-snapshot download.

### Current FHIR mappings

- `people` → `Patient`
- `allergies` → `AllergyIntolerance`
- `medications` → `MedicationStatement`
- `lab_results` → `Observation`
- `health_entries` → `Observation`
- `wearable_records` → `Observation`
- `appointments` → `Appointment`
- `reminders` → `Task`

### DECIDED — NOT YET IMPLEMENTED

- PDF export.
- Better human-readable provider packet.
- Secure share link.
- Time-limited share link.
- Revocable share link.
- Selective record sharing.
- Consent record attached to a share.
- Provider-connected export.
- Direct EHR ingestion.
- Direct EHR write-back only if appropriate and safe.
- Import preview before committing data.
- Duplicate/reconciliation screen.
- Import validation report.
- Source-specific adapters.
- Provenance preservation through export/import.
- Export of original and normalized values.
- Redaction controls.
- Emergency access controls.

### Gap

FHIR Bundle import/export is not equivalent to real interoperability. Production integration requires profiles, coding systems, validation, authorization, patient matching, conflict resolution, provenance, and likely organization-specific workflows.

---

## 12. FHIR, EHR, and analytics data layer

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Basic FHIR R4/R5 Bundle import/export.
- Local SQLite schema remains unchanged during FHIR conversion.
- Human-readable text is used where local records lack clinical codes.

### DECIDED CORE SEQUENCING

The retained architecture direction is:

1. **Product direction:** wearable-to-PHR/EHR ingestion, longitudinal personal-baseline trend detection, provider-ready summaries.
2. **Internal data layer:** FHIR flattening and analytics-ready transformation.
3. **Interface layer:** adaptive condition-aware interface built from tested deterministic widgets.
4. **Patient input layer:** structured patient-reported outcomes and symptom check-ins.

### DECIDED — NOT YET IMPLEMENTED

- SMART on FHIR authorization.
- Provider-connected EHR workflow.
- US Core or other implementation-guide profiles.
- Coded vocabularies.
- FHIR validation.
- OAuth.
- Patient matching.
- Provenance resources.
- Encounter-aware context.
- Normalized internal analytics schema.
- FHIR flattening into analysis tables.
- Stable canonical model independent of source.
- Mapping layer from source data to canonical concepts.
- Data lineage.
- Versioned transformations.
- Reprocessing when mappings change.
- Source conflict resolution.
- Data quality status.
- Analytics-ready longitudinal event table.
- Terminology services.
- LOINC.
- RxNorm.
- SNOMED CT where licensed/appropriate.
- UCUM units.
- Observation category handling.
- DiagnosticReport and panel relationships.
- Condition versus symptom separation.
- Procedure, encounter, imaging, immunization, and document support.
- Bulk import workflows.
- Incremental synchronization.

### Feasibility issue

FHIR is a transport and representation standard, not an analytics model. Flattening is necessary, but careless flattening can erase clinical context. The canonical model must preserve source resources, references, coding, timestamps, encounter context, and provenance.

---

## 13. Provider summary and emergency snapshot

### IMPLEMENTED — REPOSITORY-CONFIRMED

Provider Summary:

- Markdown output.
- Optional date range.
- Include/exclude controls for:
  - Labs.
  - Timeline entries.
  - Wearables.

Emergency Snapshot:

- Concise Markdown.
- Allergies.
- Active medications.
- Key notes.
- Recent abnormal labs.

### DECIDED — NOT YET IMPLEMENTED

- PDF output.
- More polished provider-ready formatting.
- Clinician-facing trend plots.
- Source citations/provenance per statement.
- Patient questions for the visit.
- Concise “what changed since last visit.”
- Baseline deviations.
- Medication changes.
- Symptom progression.
- Relevant adherence information.
- Share controls.
- Expiring provider link.
- Print-friendly emergency card.
- Offline emergency view.
- QR code only if privacy and revocation are handled.
- Selectable data scope.
- Explicit patient consent.
- Provider feedback loop.
- Clinician annotation or correction.
- Distinguish patient-entered, imported, and system-derived information.
- Avoid overwhelming providers with unfiltered wearable data.

---

## 14. Rule-based insights and safety logic

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Rule-based report works without an API key.
- Rule-based report is the fallback when AI fails.
- Safety disclaimer always included.
- Urgent warning language triggered by red-flag terms.
- Missing-data areas identified.
- Basic counts and summaries.
- No diagnosis.
- No treatment recommendations.

### Decided safety invariants

- Rule-based fallback must be preserved.
- AI provider abstraction must be preserved.
- AI must not be the only route to core functionality.
- Non-diagnostic language.
- System-detected patterns are signals, not diagnoses.
- User-entered suspected concerns are concerns, not diagnoses.
- Clinician-diagnosed conditions need provenance.
- The app should explain why something appears.
- Safety rules should be deterministic and testable.
- AI should not override structured safety rules.
- Urgent symptoms should not be managed through home-care advice that delays care.
- No prescription changes.
- No supplement changes.
- No restrictive diet prescriptions.
- No intense exercise prescriptions.
- No invasive actions.
- No output that could delay urgent care.

### DECIDED — NOT YET IMPLEMENTED

- Broader structured safety rules beyond keyword matching.
- Negation handling.
- Context handling.
- Severity and timing.
- Separate emergency guidance layer.
- Versioned safety rules.
- Audit of triggered rules.
- Rule explanation.
- False-positive/false-negative review.
- Clinically reviewed terminology.
- More robust crisis and self-harm handling.
- Localization of emergency guidance.
- Medical-device/regulatory assessment if insights become more directive.

### Gap

Keyword detection is useful as a safeguard, but medically meaningful symptom triage requires context. “No chest pain” and “family history of stroke” must not trigger the same behavior as an active emergency.

---

## 15. External AI insights

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Optional Zhipu AI provider.
- Key accepted from:
  - Streamlit secrets.
  - Environment variable.
  - macOS Keychain.
- Key is not written to the project folder when stored through the macOS setting.
- Test-key button.
- AI request occurs only after a button click.
- Health data is not sent automatically.
- Compact insight packet instead of full database.
- Default serialized context byte cap.
- Context may include a small number of:
  - Active medications.
  - Allergies.
  - Recent abnormal labs.
  - Recent symptoms.
  - Trend summaries.
  - Open reminders.
  - Upcoming appointments.
  - Rule-based findings.
- Low-temperature generation.
- Model thinking disabled for insight report.
- Primary/fallback model behavior.
- 429 fallback behavior.
- Quota/account error handling.
- Rule-based fallback if unavailable.
- Prompt safety restrictions.
- Requested output categories:
  - Possible patterns.
  - Potential issues.
  - Safe low-risk actions.
  - Questions for a clinician.
  - Safety note.

### IMPLEMENTED — REPOSITORY-CONFIRMED: AI chat

- Streamlit chat UI.
- Current-profile-only context.
- Other family profiles excluded.
- Concise selected-patient context.
- Chat history stored only in session state.
- Chat history not written to SQLite.
- Clear chat per selected profile.
- Chat model configuration.
- Fallback models.
- Current default chat setup described as GLM-5.1 with configurable alternatives.

### DECIDED FUTURE PRIVACY/AI DIRECTION

- Add a local `ollama` or Apple-silicon-friendly local provider such as MLX.
- Default to local AI whenever health records are included.
- Preserve external provider support as optional.
- Preview exactly what data will be sent before any external AI call.
- Automatically remove unnecessary identifiers:
  - Name.
  - Date of birth.
  - Address.
  - Record IDs.
  - Other irrelevant direct identifiers.
- Add local retrieval-augmented generation over:
  - Selected user’s records.
  - Trusted health references.
- Keep AI provider abstraction.
- Keep rule-based fallback.
- Use minimal necessary context.
- Log what type of data was sent, without logging sensitive content insecurely.
- Explicit opt-in for external processing.
- Distinguish local inference from external inference in the UI.
- Let the user select sources and records included in a question.
- Do not automatically send the complete record.
- Add source citations to AI responses.
- Ground clinical explanations in trusted references.
- Use AI explanations inside deterministic widgets rather than letting AI invent the interface or diagnosis.
- AI may explain why a widget or trend matters.
- AI should not determine a diagnosis label.

### REJECTED / SUPERSEDED FRAMING

- The privacy/local-AI sequence should **not** be treated as the entire default roadmap.
- It is one component of a broader PHR roadmap.
- Future planning should review unfinished work across all prior PHR discussions before prioritizing.

### Major risk

The current external AI integration sends health information to an external provider. Compact context and click-to-send reduce exposure, but they do not make the workflow appropriate for all PHI. Production use requires contracts, policy review, consent, retention understanding, de-identification strategy, and potentially regulated healthcare infrastructure.

---

## 16. Local AI and local RAG

### DECIDED — NOT YET IMPLEMENTED

- Local model provider.
- Ollama option.
- MLX-compatible option for Apple Silicon.
- Local AI as default when health records are used.
- Local embeddings.
- Local vector index or retrieval layer.
- Retrieval over selected profile only.
- Retrieval over trusted medical references.
- Source citations.
- Record-level permissions.
- Preview of retrieved context.
- User-selected source scope.
- Identifier redaction before any optional external fallback.
- No silent external fallback.
- Clear “local” versus “external” labels.
- AI-provider routing based on sensitivity and task.
- Cheap/small local model for low-risk routing or formatting.
- Larger model only where needed.
- Deterministic rules before AI.
- No raw database dump into prompts.
- Evaluation set for safety and factuality.
- Prompt/version tracking.
- Model/version tracking.
- Reproducibility where practical.

### Open feasibility questions

- Which local model can run acceptably on the user’s Mac while preserving answer quality.
- Whether RAG over personal records is necessary for every query.
- How to embed structured health data without losing temporal context.
- How to prevent one profile’s records entering another profile’s retrieval results.
- How to update or delete embeddings when a record changes.
- How to cite structured records cleanly.
- How to validate health explanations.

---

# Part II — Looking-Forward Product Goal

## 17. Long-term product concept

### PLANNED / ACCEPTED DIRECTION

The long-term application is not merely a digital filing cabinet. It is intended to become a:

- Local-first or privacy-forward personal/family health record.
- Longitudinal health data hub.
- Wearable and patient-generated data ingestion platform.
- EHR-connected record aggregator.
- Personal-baseline analytics system.
- Provider-ready summary generator.
- Condition- and concern-aware interface.
- User-correctable, provenance-preserving health organization tool.
- Non-diagnostic decision-support and education interface.
- Family health management tool.
- Structured patient-reported outcome collection system.

### Core user jobs discussed

- Keep family health records organized.
- See records by person.
- See records by date.
- See records by organ, body part, and system.
- Understand what changed.
- Find abnormal or unresolved items.
- Track symptoms.
- Track medications.
- Track reminders and appointments.
- Import labs.
- Import wearable data.
- Connect EHR data.
- Prepare for a clinician visit.
- Share a concise subset with a provider.
- Create an emergency snapshot.
- Ask questions about selected records.
- See trends against the person’s own baseline.
- Understand data provenance.
- Correct bad mappings.
- Keep sensitive data local where possible.
- Decide what is sent externally.

---

## 18. Adaptive condition- and concern-aware interface

### CONDITIONAL / LATER — AFTER FULL-STACK MIGRATION

Retained design:

- Fixed library of tested widgets.
- Deterministic, versioned display rules.
- Optional AI-generated explanations inside widgets.
- Log why each component appears.
- Prioritize trends and data relevant to a condition or concern.
- Do not let an LLM freely generate the page layout.
- Do not let the UI imply diagnosis.

### Required distinctions

1. **Clinician-diagnosed condition**
   - Sourced from a medical record or entered manually.
   - Must include provenance.
   - May be used to enable condition-specific views.

2. **User-reported concern or suspected condition**
   - Must be explicitly entered as a concern.
   - Must not be labeled as a diagnosis.
   - May be used to show relevant tracking options or education.

3. **System-detected pattern**
   - Presented as a non-diagnostic signal.
   - Must show why it was detected.
   - Must link to underlying data.
   - Must not silently become a condition.

### DECIDED — NOT YET IMPLEMENTED

- Condition-specific widget sets.
- Concern-specific widget sets.
- Versioned rule library.
- Rule priority and conflict resolution.
- “Why am I seeing this?” explanation.
- Audit log of widget selection.
- User controls to dismiss, pin, or correct widgets.
- Clinician-diagnosis provenance.
- Concern creation flow.
- System-pattern flow.
- Widget testing.
- Safe fallback generic dashboard.
- No hidden model-generated medical categorization.
- Personal relevance without diagnosis inflation.

### Gap

The project does not yet have a formal condition model, concern model, signal model, rule engine, or widget registry.

---

## 19. Structured patient-reported outcomes and symptom check-ins

### DECIDED CORE FUTURE LAYER

- Structured symptom check-ins.
- Patient-reported outcome measures.
- Repeatable questionnaires.
- Time-series symptom severity.
- Body location.
- Onset.
- Duration.
- Frequency.
- Triggers.
- Relieving factors.
- Associated symptoms.
- Functional impact.
- Free-text notes in addition to structured fields.
- Medication side-effect tracking.
- Condition-specific instruments where appropriate.
- Version and provenance of each questionnaire.
- Avoid treating a check-in as a diagnosis.
- Trend displays.
- Provider summary inclusion.
- Reminder cadence.
- User control over notification frequency.
- Link check-ins to events, medications, or interventions.
- Allow missing/unknown answers.
- Preserve original responses.

### Feasibility / governance issue

Validated clinical instruments may have licensing, scoring, and interpretation requirements. The app should not recreate or modify proprietary instruments without checking permission.

---

## 20. Personal-baseline analytics

### DECIDED PRODUCT DIRECTION

- Longitudinal personal baseline.
- Compare current values with the individual’s usual range.
- Do not rely only on population reference ranges.
- Trend detection.
- Meaningful deviation detection.
- Provider-ready summary.
- Explainable signals.
- Link every signal to source records.
- Non-diagnostic wording.
- Use personal baseline only when enough high-quality data exists.
- Show confidence or data sufficiency.
- Account for device changes.
- Account for missing data.
- Account for time of day, day of week, and season where relevant.
- Separate short-term fluctuation from sustained change.
- Avoid alert fatigue.
- Let the user dismiss or annotate a signal.
- Retain the annotation for future interpretation.
- Use deterministic statistical methods first.
- AI may explain a detected signal but should not be the sole detector.

### Candidate analytics discussed or implied

- Rolling mean.
- Rolling median.
- Standard deviation.
- Median absolute deviation.
- Percent change.
- Z-score relative to personal baseline.
- Trend slope.
- Change points.
- Sustained threshold crossings.
- Correlations.
- Lagged correlations.
- Event-aligned analysis.
- Before/after medication or behavior comparison.
- Data completeness.
- Wear-time estimation.
- Outlier handling.
- Unit normalization.

### Gap

No agreed minimum data requirements, validation set, false-alert tolerance, or clinical review process has been specified.

---

## 21. Full-stack migration

### DECIDED DIRECTION

- Move away from Streamlit.
- Streamlit is considered too limiting or primitive for the long-term product.
- Build a real full-stack application.
- Preserve the working MVP while migrating.
- Do not rewrite blindly before clarifying domain boundaries.
- Plan the migration once Streamlit limits interaction and maintainability.
- Body-map interaction is one concrete migration pressure.
- Adaptive UI is intended after the full-stack migration.

### Likely retained backend responsibilities

- Authentication.
- Authorization.
- Profile/person access.
- CRUD APIs.
- Import jobs.
- FHIR transformations.
- Analytics jobs.
- AI routing.
- Audit logs.
- Consent.
- Sharing.
- Notifications.
- Database transactions.
- Data validation.

### Likely retained frontend responsibilities

- Dashboard.
- Body map.
- Timeline.
- Forms.
- Trend charts.
- Adaptive widgets.
- Import preview.
- Share controls.
- Consent UI.
- Local/external AI preview.
- Mobile-responsive interface.

### POST-YC DEVELOPMENT MODEL — DECIDED JULY 2026

After YC Startup School, the development model changed from manual-code-first learning to AI-native building. The user's retained interpretation of the event is:

- Code generation is abundant and fast; manual typing is not the primary bottleneck.
- Systems thinking, product judgment, decomposition, architecture, evaluation, debugging, and user validation are the higher-leverage skills.
- AI agents should generate most implementation, scaffolding, tests, refactors, and documentation drafts.
- The user should own behavior, contracts, domain boundaries, data models, invariants, acceptance criteria, risks, and the decision to accept or reject a change.
- Line-by-line understanding is not required for routine boilerplate, generated code, styling, or framework internals.
- Critical and novel logic still requires behavioral and architectural understanding, test evidence, and review.
- Writing code by hand is optional and should be used only when it is the fastest way to probe behavior, clarify an algorithm, isolate a bug, or make a small correction.
- Migration remains valuable, but it should be treated as a systems, architecture, and product exercise rather than a manual coding curriculum.
- A broader prototype is technically more feasible with agents, but broader implementation does not remove the need for a narrow validated user problem or credible product wedge.

Ownership is now defined as the ability to specify, direct, review, verify, modify through agents, and diagnose the system, not the ability to reconstruct the application unaided from memory.

### DECIDED / DISCUSSED MIGRATION REQUIREMENTS

- Preserve selected-person isolation.
- Preserve current data.
- Avoid breaking the SQLite prototype before the replacement works.
- Document each implementation phase.
- Coding agents should document material plans, changes, tests, assumptions, and unresolved risks.
- Routine work that follows an established pattern may be delegated directly without forcing a separate manual implementation or lengthy approval cycle.
- Architectural and critical changes require a compact change brief and explicit evidence.
- Implement in parts.
- Maintain a complete PRD while splitting implementation into smaller files or phases.
- Keep changeable visual assets and configuration.
- Keep tests.
- Keep secrets out of source control.
- Keep non-diagnostic language.
- Preserve rule-based fallback.
- Preserve AI-provider abstraction.

### Unresolved architecture choices

- Frontend framework.
- Backend framework.
- Database for production.
- Local desktop versus hosted web deployment.
- Offline-first synchronization.
- Cloud provider.
- Authentication provider.
- Local encryption strategy.
- Key management.
- Job queue.
- Vector database.
- FHIR server or no FHIR server.
- Mobile app versus responsive web app.
- Single-tenant family app versus multi-tenant platform.
- HIPAA scope.
- Consumer app versus provider-connected product.
- Medical-device boundary.

---

# Part III — Security, Privacy, Compliance, and Trust

## 22. Current security state

### IMPLEMENTED — REPOSITORY-CONFIRMED

- Local SQLite.
- Local-first default.
- Optional profile passwords.
- PBKDF2-HMAC password hashing.
- Random salts.
- Mac Keychain storage for optional Zhipu key.
- No automatic external AI sending.
- Selected-profile-only AI context.
- Compact AI packet.
- No persisted chat history.
- Basic medical disclaimer.
- Basic urgent-warning language.

### Explicit current limitations

- No production authentication.
- No encryption at rest.
- No audit logs.
- No cloud sync.
- No role-based permissions.
- No secure provider sharing.
- No production HIPAA deployment infrastructure.
- No OAuth.
- No consent tracking.
- No live EHR authorization.

### DECIDED FUTURE REQUIREMENTS

- Strong authentication.
- Encryption at rest.
- Encryption in transit.
- Key management.
- Audit logging.
- Role-based access control.
- Consent tracking.
- Secure provider sharing.
- Revocation.
- Session security.
- Device security considerations.
- Data export controls.
- Data deletion.
- Backup encryption.
- Recovery.
- Breach-response planning.
- Minimal necessary data sharing.
- External AI preview.
- Identifier removal.
- Local AI default for records.
- Clear retention policy.
- Clear third-party processor disclosure.
- User-visible provenance.
- User-visible data lineage.
- Security tests.
- Threat model.
- No secrets in repository.
- Separate demo and real data.
- Never treat lightweight profile passwords as production security.

### Legal/regulatory topics already identified as relevant

- HIPAA applicability depends on product relationships and data flows.
- FTC Health Breach Notification Rule may apply to consumer health apps.
- State consumer-health-data laws may apply.
- HHS guidance for consumer-directed APIs is relevant.
- Cures Act and information-blocking rules are relevant to patient access.
- SMART on FHIR and US Core are relevant to provider-connected access.
- Medical-device regulation may become relevant if the app provides diagnostic or treatment recommendations.

---

## 23. Provenance and truth labeling

### DECIDED / REQUIRED

Every clinically meaningful item should eventually be labeled as one of:

- Imported from provider/EHR.
- Imported from wearable/device.
- Imported from file.
- Entered by user.
- Entered by caregiver.
- Entered by clinician.
- Derived by deterministic rule.
- Derived by statistical analysis.
- Suggested by AI.
- Corrected by user.
- Superseded by newer data.

For diagnoses and concerns:

- Clinician-diagnosed condition.
- User-reported condition.
- User concern/suspected issue.
- System-detected non-diagnostic pattern.

For mappings:

- Default mapping.
- Terminology-based mapping.
- User override.
- AI suggestion.
- Imported mapping.

For lab flags:

- Source-provided flag.
- App-computed flag.
- Unknown.

### Current gap

The current product has source fields in parts of the schema and compact AI context, but no confirmed universal provenance model or provenance UI.

---

# Part IV — Complete Functionality Backlog by Domain

## 24. Identity and access backlog

- Account creation.
- Login.
- Logout.
- Password reset.
- Multi-factor authentication.
- Passkeys.
- Device trust.
- Session expiration.
- Account owner.
- Adult family member.
- Dependent.
- Caregiver.
- Provider guest access.
- Emergency access.
- Per-record sharing.
- Per-category sharing.
- Per-date-range sharing.
- Consent grant.
- Consent revocation.
- Minor/dependent access transition.
- Access audit.
- Login audit.
- Failed-login monitoring.
- Profile switch.
- Profile lock.
- Profile recovery.
- Data ownership.
- Account deletion.
- Profile deletion.
- Export before deletion.

**Status:** Mostly future; only local profile selection and lightweight local passwords are current.

---

## 25. Record types backlog

Currently represented:

- Person.
- Allergy.
- Medication.
- Lab result.
- Health entry.
- Appointment.
- Reminder.
- Wearable record.

Discussed or necessary future record types:

- Condition/diagnosis.
- Concern.
- Symptom.
- Patient-reported outcome.
- Procedure.
- Surgery.
- Encounter/visit.
- Immunization.
- Imaging study.
- Imaging report.
- Diagnostic report.
- Vital sign.
- Device.
- Care plan.
- Goal.
- Family history.
- Social history.
- Lifestyle factor.
- Pregnancy status/history where appropriate.
- Genetics.
- Pathology.
- Clinical note/document.
- Insurance.
- Provider.
- Organization.
- Pharmacy.
- Medication order versus medication statement.
- Refill.
- Adherence event.
- Adverse event.
- Attachment.
- Consent.
- Provenance.
- Share grant.
- Alert/signal.
- User annotation.

**Status:** Most are not yet implemented.

---

## 26. Search, filtering, and navigation backlog

Current:

- Date filters.
- Body-system filter.
- Body-part filter.
- Medication status.
- Lab flag.
- Reminder status.
- Keyword search.
- Current profile.

Future:

- Source filter.
- Record-type filter.
- Provider filter.
- Facility filter.
- Condition filter.
- Concern filter.
- Signal status.
- Unresolved-only.
- New-since-last-view.
- Imported-versus-user-entered.
- Abnormal-only.
- Missing-data-only.
- Shared/not shared.
- Recent changes.
- Full-text search.
- Saved searches.
- Pinned filters.
- Filter combinations.
- Timeline zoom.
- Calendar navigation.
- Body-map navigation.
- Mobile navigation.
- Accessible keyboard navigation.

---

## 27. Data quality backlog

- Required-field validation.
- Date validation.
- Allowed-value validation.
- Impossible-value checks.
- Duplicate detection.
- Unit validation.
- Unit conversion.
- Terminology normalization.
- Source identifier retention.
- Record reconciliation.
- Conflict detection.
- Missing reference ranges.
- Missing units.
- Implausible wearable values.
- Device time drift.
- Time-zone normalization.
- Imported date ambiguity.
- Data completeness.
- Data quality score.
- Manual correction.
- Correction history.
- Version history.
- Soft delete.
- Merge records.
- Split records.
- Import report.
- Reprocess mappings.
- Preserve original raw payload.
- Provenance.

**Status:** Basic validation exists; production-grade data-quality workflows do not.

---

## 28. Visualization backlog

Current:

- Streamlit dashboard.
- Tables/lists.
- Body map.
- Basic summaries.

Future:

- Longitudinal line charts.
- Reference-range bands.
- Personal-baseline bands.
- Event annotations.
- Medication start/stop overlay.
- Symptom overlay.
- Wearable trend charts.
- Small multiples.
- Calendar heatmaps.
- Daily/weekly/monthly views.
- Body-map front/back.
- Body-map layers.
- Condition widgets.
- Concern widgets.
- Signal cards.
- “Why shown” panel.
- Source/provenance display.
- Data sufficiency.
- Confidence.
- Import preview.
- Sharing preview.
- Mobile layouts.
- Accessibility.
- Printable provider report.
- Printable emergency summary.

---

## 29. Notifications and engagement backlog

- Reminder notification.
- Appointment notification.
- Medication reminder.
- Symptom check-in reminder.
- Patient-reported outcome reminder.
- New imported record notice.
- Unresolved critical item notice.
- Share expiration notice.
- Provider summary preparation reminder.
- Notification preferences.
- Quiet hours.
- Snooze.
- Dismiss.
- Escalation.
- No alert fatigue.
- Separate informational versus urgent notices.
- Local device notifications.
- Email.
- SMS only if justified and secured.
- Calendar integration.

**Status:** Stored reminders exist; delivery channels are not confirmed.

---

## 30. Sharing and collaboration backlog

- Provider summary export.
- Emergency snapshot export.
- PDF.
- Secure link.
- Link expiration.
- Link revocation.
- Password-protected link.
- One-time access.
- Provider guest view.
- Select records.
- Select categories.
- Select date range.
- Redact identifiers.
- Consent receipt.
- Access log.
- Download log.
- Provider comments.
- User correction.
- Caregiver collaboration.
- Family role permissions.
- Emergency access.
- Share only a derivative summary versus underlying data.
- No public static URLs for PHI.

**Status:** Markdown downloads exist; secure collaboration does not.

---

## 31. AI backlog

Current:

- Rule-based insights.
- External Zhipu insight generation.
- External Zhipu chat.
- Compact context.
- Profile isolation.
- Rule fallback.
- Safety constraints.

Future:

- Local model.
- Local RAG.
- Trusted-reference retrieval.
- Record citations.
- Source citations.
- Identifier redaction.
- External-send preview.
- Explicit consent.
- Provider abstraction.
- Sensitivity-aware routing.
- Model evaluation.
- Prompt evaluation.
- Hallucination testing.
- Safety testing.
- Prompt injection protection for imported documents.
- Structured outputs.
- AI mapping suggestion.
- AI plain-language explanation.
- AI clinician-question generation.
- AI summary draft.
- No AI diagnosis.
- No AI prescription changes.
- No AI UI invention.
- No silent external fallback.
- Model/version display.
- Data-scope display.
- Delete AI session.
- Do not retain chat by default.
- Optional local history if explicitly enabled.
- Explain what was and was not included.

---

## 32. Testing and engineering backlog

Current:

- Pytest.
- Body-map configuration tests.
- Agent instructions.
- Documentation.
- Scripts.
- Sample data.

Decided/required:

- Selected-person isolation tests.
- No cross-profile leakage.
- No modification of production/local real database during tests.
- Temporary databases.
- No secrets.
- Non-diagnostic wording tests.
- Body-map mapping tests.
- Click/filter synchronization tests.
- Import validation tests.
- FHIR round-trip tests.
- Backup/restore tests.
- Permission tests.
- Consent tests.
- AI context minimization tests.
- Redaction tests.
- Rule fallback tests.
- External-provider failure tests.
- Safety-output tests.
- Migration tests.
- Schema versioning.
- Seed/demo isolation.
- Accessibility tests.
- Performance tests.
- Large wearable dataset tests.
- Data deletion tests.
- Audit-log integrity tests.
- Agent-produced diff summaries, test evidence, and documentation for material implementation steps.
- Architecture decision records for consequential framework, data-model, privacy, or security choices.
- Failure-injection and observability checks for critical workflows.
- Verification that agent-generated code matches the intended contracts and invariants.

---

# Part V — Inconsistencies and Conflicts

## 33. Streamlit prototype versus full-stack goal

- Current: Streamlit local prototype.
- Goal: Real full-stack application.
- Conflict: New complex product features added directly to Streamlit increase migration cost.
- Current symptom: Body-map navigation behavior is constrained or broken.
- Required decision: Define a freeze line for Streamlit feature work versus features that begin only in the full-stack architecture.

---

## 34. Local-first positioning versus external AI

- Current: Local-first data storage.
- Current: Optional Zhipu AI sends a compact subset externally.
- Future: Local AI should be default whenever records are included.
- Conflict: “Local-first” can be misunderstood as “never leaves device.”
- Required product behavior: Clearly label local storage separately from external processing.

---

## 35. Family PHR versus lightweight profile passwords

- Current: Multiple family profiles and optional per-profile passwords.
- Goal: Family roles, consent, and secure sharing.
- Conflict: A local profile password may create a false sense of access control.
- Required product behavior: Explicitly call it a local convenience lock, not production authorization.

---

## 36. FHIR support versus real EHR interoperability

- Current: R4/R5 Bundle import/export.
- Goal: SMART-on-FHIR provider connection.
- Conflict: Feature wording can imply broad interoperability.
- Required product behavior: Describe current support as file-level mapping, not connected EHR integration.

---

## 37. Generic Observation mapping versus clinical semantics

- Current: Labs, health entries, and wearables map to Observation.
- Problem: Generic notes, symptoms, and device metrics are not semantically interchangeable.
- Required future work: Expand typed resources and preserve source distinctions.

---

## 38. Body-part mapping versus multi-system relevance

- Current direction: Default organ-to-system mapping.
- Goal: Cross-system relevance.
- Conflict: A single mapping may be too rigid.
- Required future model: Many-to-many mappings with relevance type, weight, provenance, and override.

---

## 39. Sex-neutral body model versus sex-specific anatomy

- Visual goal: Sex-neutral default.
- Functional goal: Sex-specific support.
- Conflict: One static front image cannot represent all anatomy.
- Likely resolution: Optional profile-aware layers or separate anatomical overlays.

---

## 40. Persistent flags versus changing data

- Goal: Flags persist until newer data.
- Risk: Persistence can become stale or alarming.
- Missing specification:
  - What resolves a flag?
  - What supersedes it?
  - Can a user dismiss it?
  - Is dismissal recorded?
  - Does a clinician correction override it?
  - Does a new normal value automatically close it?

---

## 41. AI mapping unknown labs versus deterministic healthcare terminology

- Goal: “Unknown lab” AI button.
- Risk: AI can assign incorrect anatomy or terminology.
- Required constraint: AI suggestion must be reviewable, reversible, provenance-labeled, and never overwrite raw data.

---

## 42. Emergency snapshot versus emergency use disclaimer

- Current: Emergency snapshot.
- Current disclaimer: Not intended for emergencies.
- Tension: A document for emergency reference may be useful, but the app cannot be relied on as an emergency response system.
- Required wording: “Emergency information summary” rather than implying real-time emergency decision support.

---

## 43. Adaptive condition-aware interface versus non-diagnostic scope

- Goal: Condition-aware widgets.
- Safety rule: No implied diagnosis.
- Resolution already decided:
  - Diagnosed condition with provenance.
  - User concern.
  - System signal.
- Missing implementation: Formal data types and UI labels.

---

## 44. “Everything in one source of truth” versus implementation files

- Goal: One authoritative product definition.
- Engineering need: Split work into smaller implementation documents.
- Resolution:
  - One master source-of-truth document.
  - Separate phase PRDs/specifications linked back to master requirement IDs.
  - Do not duplicate requirements without references.

## 44A. Manual-code-first learning versus AI-native development

- Previous approach: Daniel manually implements first instances, reconstructs patterns, and limits generated implementation to preserve learning.
- Updated approach: AI agents generate most code while Daniel owns system design, contracts, invariants, evaluation, review, and debugging.
- Conflict: Requiring manual coding as proof of understanding slows iteration and optimizes for a skill that is no longer the main project bottleneck.
- Resolution:
  - Remove mandatory manual implementation and reconstruction gates.
  - Retain rigorous review, testing, traceability, and failure diagnosis.
  - Require deeper review for critical and unfamiliar logic, not for routine boilerplate.
  - Judge ownership by the ability to specify, direct, verify, and diagnose the system.
  - Use manual coding only when it is locally efficient or educationally necessary for a specific concept.

---

# Part VI — Gaps in Service

## 45. Health information that the current app does not fully cover

- Diagnoses/conditions as first-class records.
- Clinical documents.
- Imaging.
- Procedures.
- Immunizations.
- Encounters.
- Providers.
- Organizations.
- Family history.
- Social determinants.
- Care plans.
- Goals.
- Genetics.
- Pathology.
- Insurance.
- Pharmacy data.
- Medication reconciliation.
- Structured symptoms.
- Validated PRO instruments.
- Clinical terminology.
- Complete provenance.
- Record version history.
- Secure collaboration.
- Connected EHR access.
- Live wearable access.

---

## 46. User workflows not yet complete

- First-time onboarding.
- Import preview and reconciliation.
- Review imported data.
- Correct bad mappings.
- See what changed since last visit.
- Create a concern.
- Record a clinician-diagnosed condition with provenance.
- Respond to a system signal.
- Dismiss or resolve a flag.
- Prepare a provider visit packet with source citations.
- Share securely.
- Revoke sharing.
- See who accessed data.
- Migrate to a new device.
- Recover encrypted data.
- Delete account and records.
- Manage a dependent aging into their own account.
- Reconcile conflicting records from two providers.
- Connect and disconnect wearable/EHR sources.
- Understand why a widget appears.
- Preview external AI data.
- Choose local versus external AI.

---

## 47. Clinician-side gaps

- No clinician portal.
- No clinician identity verification.
- No structured clinician feedback.
- No correction workflow.
- No provider-specific summary preferences.
- No EHR write-back.
- No inbox integration.
- No standardized provider report.
- No evidence that provider summaries fit clinical workflow.
- No validation that wearable summaries are concise enough.
- No study of whether the body map helps provider communication.
- No liability workflow.

---

## 48. Accessibility and inclusivity gaps

- Accessibility requirements not yet specified.
- Screen-reader support unknown.
- Keyboard navigation unknown.
- Color-contrast support unknown.
- Color-independent lab flags unknown.
- Language localization not specified.
- Health literacy level controls not specified.
- Disability accommodations not specified.
- Sex and gender data model not specified.
- Preferred name/pronouns not specified.
- Pediatric and geriatric workflows not specified.
- Units/localization not specified.

---

# Part VII — Feasibility Flags

## 49. High-feasibility near-term functions

- Improve body-map click/filter behavior.
- Refactor Streamlit page structure.
- Add stronger provenance fields.
- Add import preview.
- Add duplicate detection.
- Add typed symptom entries.
- Add trend charts.
- Add PDF exports.
- Add local Ollama/MLX provider abstraction.
- Add external-send preview.
- Add identifier redaction.
- Improve rule explanations.
- Add selected-profile isolation tests.
- Add source citations in summaries.
- Improve wearable CSV processing.
- Build analytics-ready local tables.
- Add personal-baseline prototypes using deterministic statistics.

---

## 50. Medium-feasibility functions requiring design work

- Full-stack migration.
- Secure family roles.
- Consent.
- Encrypted local database.
- Secure sharing links.
- Local RAG.
- Condition-aware widgets.
- Structured PRO system.
- Oura API ingestion.
- Apple Health ingestion.
- FHIR terminology normalization.
- Provider-ready longitudinal summaries.
- Multi-source reconciliation.
- Audit logging.
- Offline-first sync.

---

## 51. High-complexity functions

- Production EHR connectivity across institutions.
- SMART-on-FHIR at scale.
- Clinical terminology mapping across all record types.
- HIPAA-ready multi-tenant deployment.
- Cross-device encrypted sync.
- Clinician collaboration integrated into workflow.
- Safe medical trend interpretation.
- Medical-device claims.
- Reliable emergency or triage functionality.
- Broad live wearable support.
- Automated diagnosis or treatment recommendation.
- General-purpose health AI with high clinical accuracy.
- Family/minor consent across jurisdictions.

---

# Part VIII — Decisions Still Needed

## 52. Product boundary decisions

- Personal project or startup product.
- Consumer-only or provider-connected.
- Local desktop app, hosted app, or hybrid.
- Single-family or multi-tenant.
- Wellness analytics or clinical decision support.
- Whether to pursue HIPAA-covered workflows.
- Whether provider sharing is a core product or export-only feature.
- Whether EHR write-back is in scope.
- Whether mobile is responsive web or native.
- Whether the app should remain primarily educational during development.

---

## 53. Data architecture decisions

- Canonical data model.
- Production database.
- Schema migration strategy.
- Raw versus normalized storage.
- FHIR resource retention.
- Analytics tables.
- Terminology service.
- Provenance model.
- Versioning.
- Audit events.
- File/attachment storage.
- Encryption.
- Sync.
- Deletion semantics.
- Deduplication semantics.
- Conflict resolution.

---

## 54. AI decisions

- Supported local model.
- Local embeddings.
- Vector store.
- Trusted reference corpus.
- External provider policy.
- PHI policy.
- De-identification policy.
- User preview design.
- AI retention.
- Logging.
- Evaluation.
- Safety review.
- Citation format.
- Model-routing rules.
- Whether AI chat remains a core feature or becomes contextual assistance.

---

## 55. Body-map decisions

- Anatomical ontology.
- Asset license.
- Front/back design.
- Sex-specific layers.
- System/organ/region hierarchy.
- Many-to-many relevance.
- Selection state.
- Deep linking.
- Mobile behavior.
- Accessibility.
- Mapping correction flow.
- Flag resolution.
- Trend overlay.
- Full-stack component technology.

---

# Part IX — Superseded and Non-Requirements

## 56. Items that should not be treated as the whole roadmap

- Manual coding or learning syntax as the primary measure of progress.
- Reconstructing agent-generated application code from memory.
- Line-by-line understanding of boilerplate, generated types, framework internals, or styling.
- The local-AI/privacy sequence alone.
- The body-map project alone.
- The 12-week Python learning course alone.
- The Streamlit implementation alone.
- The wearable analytics side project alone.
- FHIR export/import alone.
- AI chat alone.

All are components of the larger PHR direction.

---

## 57. Items that remain suggestions unless explicitly adopted

- Exact frontend framework.
- Exact backend framework.
- Exact production database.
- Exact cloud provider.
- Exact wearable device.
- Exact statistical alert thresholds.
- Exact local model.
- Exact terminology service.
- Exact mobile implementation.
- Exact commercial model.
- Exact regulatory pathway.

---

# Part X — Repository-Confirmed Current Limitations

As of the reviewed repository:

- Local prototype only.
- No production authentication.
- No encryption at rest.
- No audit logs.
- No cloud sync.
- No role-based family permissions.
- No provider sharing links.
- No PDF export.
- No SMART-on-FHIR authorization.
- No provider-connected FHIR workflow.
- No implementation-guide profile support.
- No live Apple Health integration.
- No live Fitbit integration.
- No live Garmin integration.
- No live Google Fit integration.
- No live EHR integration.
- Not for emergencies.
- Not for diagnosis.
- Not for prescriptions.
- Not for treatment decisions.

---

# Part XI — Master Functional Inventory

This section intentionally repeats functions in a flat checklist so no feature disappears inside architecture prose.

## Current or partially current

- [x] Local-first storage.
- [x] SQLite.
- [x] Streamlit.
- [x] Multiple profiles.
- [x] Profile selection.
- [x] Profile dashboard.
- [x] Optional local profile passwords.
- [x] Password hashing and salt.
- [x] Allergies CRUD.
- [x] Medications CRUD.
- [x] Labs CRUD.
- [x] Health entries CRUD.
- [x] Appointments CRUD.
- [x] Reminders CRUD.
- [x] Wearable records CRUD.
- [x] Date filters.
- [x] Body-system filters.
- [x] Body-part filters.
- [x] Medication-status filters.
- [x] Lab-flag filters.
- [x] Reminder-status filters.
- [x] Keyword search.
- [x] Body map.
- [~] In-place body-map click/filter/highlight.
- [x] Lab CSV import.
- [x] Wearable CSV import.
- [x] JSON backup.
- [x] JSON restore.
- [x] FHIR R4 Bundle import/export.
- [x] FHIR R5 Bundle import/export.
- [x] Provider Markdown summary.
- [x] Emergency Markdown snapshot.
- [x] Rule-based insights.
- [x] Safety disclaimer.
- [x] Red-flag keyword warnings.
- [x] Optional Zhipu insight generation.
- [x] Optional Zhipu chat.
- [x] Compact AI context.
- [x] Current-profile-only AI context.
- [x] Session-only chat history.
- [x] Rule-based AI fallback.
- [x] Demo mode.
- [x] Tests and documentation.

## Explicit future functions

- [ ] Full-stack migration.
- [ ] Mobile-responsive interface.
- [ ] Strong authentication.
- [ ] Encryption at rest.
- [ ] Audit logging.
- [ ] Role-based family permissions.
- [ ] Consent tracking.
- [ ] Secure provider sharing.
- [ ] Revocable sharing.
- [ ] Expiring sharing.
- [ ] PDF export.
- [ ] SMART on FHIR.
- [ ] Provider-connected EHR integration.
- [ ] FHIR implementation-guide profiles.
- [ ] Coded vocabularies.
- [ ] FHIR validation.
- [ ] Analytics-ready FHIR flattening.
- [ ] Canonical longitudinal data model.
- [ ] Provenance.
- [ ] Terminology normalization.
- [ ] Import preview.
- [ ] Duplicate reconciliation.
- [ ] Live wearable integrations.
- [ ] Oura ingestion.
- [ ] Apple Health ingestion.
- [ ] Fitbit ingestion.
- [ ] Garmin ingestion.
- [ ] Google Fit/Health Connect ingestion.
- [ ] Personal-baseline analytics.
- [ ] Trend detection.
- [ ] Provider-ready trend summaries.
- [ ] Structured symptom check-ins.
- [ ] Patient-reported outcomes.
- [ ] Condition records with provenance.
- [ ] Concern records.
- [ ] System signals.
- [ ] Adaptive deterministic widgets.
- [ ] “Why shown” logging.
- [ ] Front/back body map.
- [ ] Body-map layer toggles.
- [ ] Sex-specific anatomical support.
- [ ] Mapping correction.
- [ ] Persistent/resolvable flags.
- [ ] Trend toggle.
- [ ] Local Ollama/MLX provider.
- [ ] Local AI default for health records.
- [ ] Local RAG.
- [ ] Trusted health reference retrieval.
- [ ] External-send preview.
- [ ] Identifier removal.
- [ ] AI source citations.
- [ ] No silent external fallback.
- [ ] Model/provider transparency.
- [ ] AI evaluation.
- [ ] Safety evaluation.
- [ ] Calendar/notification delivery.
- [ ] Medication reminders.
- [ ] Appointment reminders.
- [ ] Check-in reminders.
- [ ] Data portability and encrypted backups.
- [ ] Provider feedback/correction workflow.
- [ ] Accessibility.
- [ ] Localization.

---

# Part XII — Sources Used

## Current repository

Public repository reviewed directly:

- `https://github.com/d-q222/phr_app`
- Repository title: **Local-First Family Personal Health Record**
- Current repository README and file structure reviewed July 14, 2026.

## Prior PHR conversations and retained decisions

This document includes retained requirements from prior discussions about:

- Initial Python/Streamlit PHR.
- Multi-user and family records.
- Body-system and anatomical filtering.
- Body-map PRD and implementation phases.
- Full-stack migration.
- AI provider architecture.
- Local AI/privacy.
- Wearable analytics.
- Oura/Colmi exploration.
- FHIR and EHR integration.
- Adaptive condition-aware UI.
- Structured patient-reported outcomes.
- Longitudinal personal-baseline detection.
- Provider-ready summaries.
- Safety and non-diagnostic requirements.

## Uploaded project notes

- `Python for PHR Development.txt`
- `PHR Learning Resources.txt`

The learning course contains early desired functions including people, medications, allergies, labs, health entries, body systems, dates, SQLite persistence, validation, Streamlit UI, filtering, family profiles, import/export, wearable ingestion, reminders, provider summaries, and emergency snapshots. The current repository has implemented many of those early goals.

---

# Part XIII — Maintenance Rule for This Source of Truth

For every future PHR decision:

1. Add the requirement here.
2. Give it a stable requirement ID in a future revision.
3. Mark its status.
4. Link the implementation PRD or issue.
5. Record conflicts.
6. Record whether it is user-decided, accepted direction, conditional, suggested, rejected, or superseded.
7. Do not describe a partial implementation as complete.
8. Do not describe file-level FHIR support as connected interoperability.
9. Do not describe a user concern or system pattern as a diagnosis.
10. Do not describe local storage as fully local processing when an external AI call is enabled.
11. Record material changes to the AI-native development model in both this document and the learning protocol.
12. Do not reintroduce mandatory manual coding, unaided reconstruction, or line-by-line ownership as default project requirements unless the user explicitly reverses the July 2026 decision.
