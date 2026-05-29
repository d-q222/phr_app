# Local-First Family Personal Health Record

A private local-first Personal Health Record (PHR) prototype for organizing family health information in Streamlit with a SQLite database.

## Local Prototype Warning

This app is intended for local personal use during MVP development. It is not a public health platform and does not include production security, encryption at rest, cloud sync, audit logs, OAuth, role-based access, or HIPAA deployment infrastructure.

The local SQLite database can contain sensitive health information. Keep the project folder and exported backups protected on your device.

## Medical Disclaimer

This application is for personal organization and education only. It is not a medical device, does not diagnose disease, does not replace professional medical care, and should not be used for emergencies. For urgent symptoms or medical emergencies, seek emergency care or call emergency services.

## Features

- Multiple family profiles.
- Optional lightweight per-profile passwords.
- Local SQLite storage.
- CRUD pages for allergies, medications, labs, health timeline entries, appointments, reminders, and wearable records.
- Profile-specific dashboard.
- Filters for dates, body system, body part, medication status, lab flag, reminder status, and keyword search where useful.
- CSV import for labs and wearable records.
- JSON backup export and restore.
- FHIR R4 and R5 Bundle export/import for EHR interoperability.
- Markdown provider summary and emergency snapshot downloads.
- Rule-based Health Insights report with safety language.
- Optional Zhipu AI safety-checked insights only when a Zhipu AI API key is configured and the user clicks the AI button.

## Installation

Python 3.11+ is the intended target. The app uses only Streamlit, SQLite, pandas, pytest, and optional python-dotenv.

```bash
cd phr_app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run The App

```bash
streamlit run app.py
```

The app initializes `data/phr.db` automatically from `schema.sql`.

## Run Tests

```bash
pytest
```

## Profile Passwords

Profile passwords are optional and local-only. Passwords are hashed with `hashlib.pbkdf2_hmac` and a random salt. Plain-text passwords are never stored.

Unlock state is stored only in Streamlit `session_state`. If a profile is locked, health-data pages show only the unlock screen. There is no password recovery in this MVP; a forgotten password requires direct local database reset.

## Lab CSV Import Format

Required columns:

```csv
test_name,result_value,numeric_value,unit,reference_low,reference_high,flag,lab_date,notes
Hemoglobin A1c,5.6,5.6,%,4.0,5.6,Normal,2026-04-28,
```

`test_name` and `lab_date` are required. `flag` must be one of `Normal`, `High`, `Low`, `Abnormal`, `Critical`, or `Unknown`.

## Wearable CSV Import Format

Required columns:

```csv
metric_type,value,unit,timestamp,source
Steps,7500,steps,2026-04-28,Manual
```

`metric_type`, numeric `value`, and `timestamp` are required.

## JSON Backup

Use the Import/Export page to download a full JSON backup of all MVP tables. Restore can insert records into the current database or clear existing records first.

## FHIR Interoperability

Use the Import/Export page to export or import HL7 FHIR JSON Bundles. The app supports R4 and R5 Bundle export/import while keeping the local SQLite schema unchanged.

Current mappings:

- `people` -> `Patient`
- `allergies` -> `AllergyIntolerance`
- `medications` -> `MedicationStatement`
- `lab_results`, `health_entries`, and `wearable_records` -> `Observation`
- `appointments` -> `Appointment`
- `reminders` -> `Task`

Exports include human-readable text fields where local records do not have clinical terminology codes. Some EHRs may require additional implementation-guide profiles, OAuth/SMART authorization, or coded vocabularies before accepting imported data.

## Provider Summary And Emergency Snapshot

The Provider Summary page generates a Markdown summary with optional date range and include/exclude controls for labs, timeline entries, and wearables.

The Emergency Snapshot page generates a concise Markdown snapshot with allergies, active medications, key notes, and recent abnormal labs.

## Health Insights

Health Insights is a structured report generator, not a chatbot. Rule-based reports require no API key and include:

- Active medication count.
- Overdue reminder count.
- Abnormal or critical labs.
- Missing lab reference ranges.
- Common body systems in health entries.
- Recent symptom entries.
- Average steps and sleep when available.
- Weight change when available.
- Upcoming appointments.
- Missing data areas.

Every report includes:

```text
This report is for organization and education only. It is not a diagnosis or medical advice. Please discuss important findings, symptoms, medication questions, or abnormal results with a qualified healthcare professional.
```

If records contain red-flag terms such as chest pain, stroke symptoms, severe shortness of breath, severe allergic reaction, suicidal thoughts, severe bleeding, fainting, or loss of consciousness, the report adds urgent-care warning language.

## Optional Zhipu AI BigModel API Key

AI safety-checked insights are optional. Configure:

```bash
export ZAI_API_KEY="your-key"
export AI_PROVIDER="zhipu"
export ZHIPU_MODEL="glm-4.5-flash"
export ZHIPU_FALLBACK_MODELS="glm-4.7-flash"
export ZHIPU_MAX_TOKENS="220"
export ZHIPU_CONTEXT_BYTE_LIMIT="1200"
```

The default model is the free low-power text model `glm-4.5-flash`, with `glm-4.7-flash` configured as a fallback. You can override either with `ZHIPU_MODEL` and `ZHIPU_FALLBACK_MODELS`, but larger models may use more quota.

On macOS, you can also enter the key in the app under Settings. The app stores it in macOS Keychain under the `phr_app.zhipu_ai` service instead of writing it into the project folder. The Settings page also includes a `Test BigModel API key` button that sends a tiny request to confirm the key and selected model work.

Health data is not sent automatically. The AI request runs only after clicking `Generate AI safety-checked insights`.

The AI request sends a compact insight packet instead of the full local health database. By default it caps that packet at 1200 serialized bytes and includes only a small number of active medications, allergies, recent abnormal labs, recent symptoms, trend summaries, open reminders, upcoming appointments, and rule-based findings.

For AI safety-checked insights, the app asks BigModel for possible patterns, potential issues, safe low-risk actions, clinician questions, and a safety note. It explicitly blocks diagnosis, prescription advice, medication or supplement changes, urgent-symptom home management, restrictive diets, intense exercise, invasive actions, or anything that could delay urgent care.

The app sets `temperature=0.2`, disables model thinking, and defaults to `glm-4.5-flash`. If BigModel returns HTTP 429 for the primary model, the app automatically retries the configured fallback models before showing the rule-based report.

If the AI report is unavailable, the app shows a Streamlit warning and falls back to the rule-based report. Zhipu business error `1113` is treated as an account balance/quota problem and is not retried.

## Current Limitations

- Local prototype only.
- No production authentication.
- No encryption at rest.
- No audit logs.
- No cloud sync.
- No role-based family permissions.
- No provider sharing links.
- No PDF export.
- No FHIR or SMART-on-FHIR implementation.
- No live Apple Health, Fitbit, Garmin, Google Fit, or EHR integration.
- Not intended for emergencies, diagnosis, prescriptions, or treatment decisions.

## Future Roadmap

TODO areas for later production work:

- Stronger authentication.
- Encryption at rest.
- Audit logging.
- Role-based family sharing permissions.
- Secure provider sharing.
- Consent tracking.
- FHIR/SMART integration.
- PDF export.
- Mobile interface.
