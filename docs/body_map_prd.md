# PRD: Interactive Body Health Map for PHR

## 1. Feature Name

**Interactive Body Health Map**

## 2. One-Sentence Summary

Add a profile-specific, organ-first interactive body map to the Streamlit PHR app so users can click a body part, see that area highlighted, and view a conservative health summary using all relevant records for the selected profile.

---

## 3. Product Context

The PHR app currently stores and displays health data, including records such as labs, medications, notes, vitals, appointments, conditions, imaging/procedures, and wearable data. Some records already have body-system labels, but this currently behaves mostly like a table label or filter.

The new feature should make the body-system idea more intuitive.

Users should not need to know whether something belongs to the cardiovascular, renal, endocrine, lymphatic, or hepatobiliary system. Instead, they should be able to click a recognizable body part such as:

- heart
- lungs
- brain
- liver
- kidneys
- stomach/intestines
- thyroid
- bones
- skin
- lymph nodes

The app should then translate that body-part selection into relevant clinical systems and show the relevant health records.

The feature should answer:

> “What does my PHR know about this part of my body?”

Not merely:

> “Show me rows tagged with this system.”

---

## 4. Core User Story

As a PHR user, I want to click a body part on a clean medical body model so that I can quickly see the relevant health information for that area without manually searching tables or knowing formal medical system names.

Example flow:

1. User selects profile: “Daniel.”
2. User opens “Body Map” page.
3. User sees a clean front-view human body infographic.
4. User clicks the heart.
5. The heart glows/highlights.
6. The app shows:
   - selected body part: Heart
   - primary system: Cardiovascular
   - current status summary
   - latest relevant records
   - source-flagged abnormalities
   - historical flags
   - tabs for labs, vitals, medications, notes, imaging, wearables, and trends
   - AI explanation buttons

---

## 5. Goals

### 5.1 Primary Goals

1. Add a large clickable body model to the PHR.
2. Use body parts/organs as the primary interaction, not medical system labels.
3. Map body parts to one or more clinical body systems internally.
4. Retrieve all relevant records for the selected body part.
5. Support multiple record types:
   - labs
   - medications
   - vitals
   - health entries / notes
   - appointments
   - conditions / diagnoses
   - imaging / procedures
   - wearable data
6. Support many-to-many mapping:
   - one record can appear under multiple body parts/systems
   - one body part can pull records from multiple systems
7. Show a conservative status summary for the selected body part.
8. Preserve old abnormal/flagged records historically.
9. Prefer latest records for current status while still showing historical flags.
10. Add AI explanation buttons using the existing Zhipu AI integration for now.
11. Keep the body model visual replaceable.
12. Keep the first version feasible in Streamlit.
13. Keep the code modular and split by responsibility.

### 5.2 Secondary Goals

1. Prepare the codebase for later manual user mapping overrides.
2. Prepare the data model for eventual full-stack migration.
3. Avoid hard-coding body-map logic into UI files.
4. Avoid hard-coding medical mapping rules into SVG/body-model files.
5. Make the feature explainable and maintainable.
6. Require Codex to document what it changed after each implementation part.

---

## 6. Non-Goals for V1

Do not implement the following in this version:

1. Do not build a true 3D anatomical model.
2. Do not migrate the app from Streamlit to a full-stack app yet.
3. Do not implement React, Three.js, or React Three Fiber.
4. Do not create a numerical health score like “Heart Health: 82%.”
5. Do not diagnose the user.
6. Do not recommend treatment.
7. Do not infer abnormality from raw values unless abnormal flags/reference ranges already exist in the source data.
8. Do not hide old abnormal records just because they are old.
9. Do not mix data across profiles.
10. Do not require users to understand formal body-system terminology.
11. Do not build a full manual mapping editor unless it is trivial and isolated.
12. Do not hard-code the medical mapping into the SVG/body-model visual asset.
13. Do not put the entire feature into one large Python file.
14. Do not create implementation-process files named `part1.py`, `part2.py`, etc.

---

## 7. Design Principles

### 7.1 Organ-first, system-second

The UI should show organs/body areas first.

Examples:

- heart
- lungs
- brain
- liver
- kidneys
- stomach/intestines
- bones
- muscles
- skin
- thyroid
- pancreas
- lymph nodes
- reproductive organs

The underlying code should map these to systems.

Example:

~~~text
Clicked body part:
heart

Primary system:
cardiovascular

Related systems:
endocrine_metabolic
renal_urinary
respiratory, only for cardiopulmonary-relevant records
~~~

### 7.2 Clinical relevance, not literal anatomy

Do not map records only by where the molecule/analyte “comes from.”

Map by clinical relevance.

Examples:

~~~text
LDL Cholesterol:
Relevant to heart/cardiovascular because it is a cardiovascular risk marker.

Creatinine:
Relevant to kidneys/renal system because it is clinically used as a kidney function marker.

A1c:
Relevant to endocrine/metabolic system, but also secondarily relevant to heart and kidneys.

CRP:
General/systemic inflammatory marker, with possible immune/cardiovascular secondary relevance.
~~~

### 7.3 Conservative status language

Use cautious language.

Acceptable:

~~~text
2 cardiovascular-related records are flagged for review.
~~~

Avoid:

~~~text
Your heart is unhealthy.
~~~

Acceptable:

~~~text
Latest kidney-related record is not source-flagged.
One historical kidney-related abnormal flag was found.
~~~

Avoid:

~~~text
Your kidneys are normal.
~~~

### 7.4 Profile isolation

Every query must filter by the selected `person_id` or equivalent profile identifier.

Never aggregate records across family members unless the user explicitly opens a family overview page. This body map is profile-specific.

### 7.5 Replaceable visual asset

The body model should be treated as a replaceable UI asset.

The app should use canonical IDs such as:

~~~text
heart
lungs
brain
liver
kidneys
stomach_intestines
bones
muscles
skin
thyroid
pancreas
lymph_nodes
reproductive_organs
general_body
~~~

The SVG or body-map asset can change later as long as it maps clickable regions to these canonical IDs.

### 7.6 One master PRD, modular code

The feature should have one master PRD file for complete context.

Recommended location:

~~~text
docs/body_map_prd.md
~~~

Do not split the PRD into five separate PRD files unless it becomes too long to manage.

However, the actual code should be split into focused source files by responsibility.

Recommended files:

~~~text
docs/
  body_map_prd.md
  body_map_implementation_notes.md

assets/
  body_map_front.svg

body_map_config.py
body_map_services.py
body_map_summary.py
body_map_ui.py
body_map_ai.py
~~~

If the project already has equivalent folders or naming conventions, Codex should adapt to the existing structure.

Do not put the whole feature into one huge file.

Do not create files like:

~~~text
part1.py
part2.py
part3.py
part4.py
part5.py
~~~

Those names mirror the implementation process, not the long-term architecture.

---

## 8. Recommended V1 Body Parts

Implement these body-part IDs first:

~~~text
heart
lungs
brain
liver
kidneys
stomach_intestines
bones
muscles
skin
thyroid
pancreas
lymph_nodes
reproductive_organs
general_body
~~~

Display names:

~~~text
heart -> Heart
lungs -> Lungs
brain -> Brain
liver -> Liver
kidneys -> Kidneys
stomach_intestines -> Stomach & Intestines
bones -> Bones
muscles -> Muscles
skin -> Skin
thyroid -> Thyroid
pancreas -> Pancreas
lymph_nodes -> Lymph Nodes
reproductive_organs -> Reproductive Organs
general_body -> General / Whole Body
~~~

---

## 9. Recommended V1 Body Systems

Implement these body-system IDs:

~~~text
cardiovascular
respiratory
neurologic
gastrointestinal_hepatobiliary
renal_urinary
endocrine_metabolic
hematologic
immune_lymphatic
musculoskeletal
dermatologic
reproductive
general_preventive
~~~

---

## 10. Recommended Relevance Types

Each mapping should include a relevance type.

Use these:

~~~text
organ_function_marker
risk_marker
injury_marker
systemic_marker
symptom
diagnosis
medication
medication_safety_marker
imaging_or_procedure
wearable_metric
appointment_or_note
cross_system_related
~~~

Examples:

~~~text
LDL Cholesterol -> risk_marker
Creatinine -> organ_function_marker
ALT -> injury_marker
Troponin -> injury_marker
CRP -> systemic_marker
Metoprolol -> medication
Liver ultrasound -> imaging_or_procedure
Chest pain note -> symptom
Resting heart rate -> wearable_metric or vital_metric
~~~

---

## 11. Status Model

The feature should not produce a numeric health score.

Use status labels.

Recommended labels:

~~~text
No data
Data available
No flagged items
Needs review
Historical flag found
Mapping uncertain
~~~

### 11.1 Status Logic

The summary should prefer latest data for current status, but preserve historical flags.

Rules:

1. If there are no mapped records:
   - show `No data`

2. If records exist but no abnormal flags/reference ranges exist:
   - show `Data available`

3. If latest relevant records contain source-provided abnormal/high/low/critical flags:
   - show `Needs review`

4. If latest relevant records are not flagged but older records were flagged:
   - show `Historical flag found`

5. If all mapped records have reliable mappings and no flags:
   - show `No flagged items`

6. If most records are AI-mapped with low confidence:
   - show `Mapping uncertain`

### 11.2 Important Historical Rule

Do not remove or hide old abnormal records.

Example:

~~~text
Old LDL result:
High, 2024

New LDL result:
Normal, 2026

Current status:
No current lipid flag based on latest available result.

Historical context:
1 prior LDL result was flagged high.
~~~

---

## 12. Visual Direction

Use a clean medical infographic style.

Visual requirements:

1. Front-view human body only for v1.
2. Clean silhouette.
3. Simplified organs.
4. Soft, readable colors.
5. Clickable organs/body areas.
6. Selected organ should glow or highlight.
7. Do not make it hyper-realistic or visually overwhelming.
8. The body map should be large and placed near the top of the page.
9. The SVG/body map should be replaceable later.

V1 should use a 2D SVG or SVG-like HTML component, not a true 3D model.

---

## 13. Technical Architecture

### 13.1 Streamlit-first

This feature is for the current Streamlit app.

Use Streamlit for:

- profile selection
- body map page
- selected body-part state
- summary cards
- record tables
- tabs
- AI explanation buttons

Use custom HTML/SVG inside Streamlit only if needed for clickable regions and highlight behavior.

### 13.2 Separation of Concerns

Do not put everything in `app.py`.

Codex should inspect the existing project structure and place code in the most appropriate files.

Preferred structure if compatible with the current project:

~~~text
models.py
db.py
services.py
validation.py
body_map_config.py
body_map_services.py
body_map_summary.py
body_map_ui.py
body_map_ai.py
app.py
~~~

If the actual project uses different file names, Codex should adapt to the existing structure instead of forcing this exact structure.

### 13.3 Source of Truth

The database and service logic should be the source of truth.

The SVG is only the visual selector.

Do not store medical mapping rules inside the SVG itself.

### 13.4 Recommended file responsibilities

Use the following responsibilities unless the existing project structure suggests better locations.

| File | Responsibility |
|---|---|
| `docs/body_map_prd.md` | Master PRD with complete feature context |
| `docs/body_map_implementation_notes.md` | Readable implementation log after each part |
| `assets/body_map_front.svg` | Replaceable 2D front-view body model |
| `body_map_config.py` | Body parts, systems, relevance types, default mappings |
| `body_map_services.py` | Body-area record retrieval and normalization |
| `body_map_summary.py` | Conservative status and summary logic |
| `body_map_ui.py` | Streamlit UI, SVG rendering, tabs, cards |
| `body_map_ai.py` | AI prompts and Zhipu explanation calls |

If some of these concepts already exist elsewhere, reuse or extend existing modules instead of duplicating functionality.

---

## 14. Documentation Requirements for Codex

Codex must document what it is doing and what it did at each part.

For every implementation part, Codex must create or update a readable documentation file.

Preferred file:

~~~text
docs/body_map_implementation_notes.md
~~~

If the project does not have a `docs/` folder, create one.

Each part must add a section with this format:

~~~markdown
## Part X — [Part Name]

### Goal
What this part was supposed to implement.

### Files Changed
- file path: short description of change

### Key Functions / Classes Added
- function_name: what it does
- class_name: what it represents

### Data Model / Schema Changes
Describe any new tables, columns, constants, config structures, or migrations.

### Assumptions
List assumptions Codex made because the existing project structure was unclear.

### How to Test Manually
Step-by-step instructions for testing this part in the app.

### Known Limitations
What this part does not handle yet.

### Next Step
Which part should be implemented next.
~~~

Codex should also add docstrings to important functions.

Every new service function should have a short docstring explaining:

1. inputs
2. outputs
3. which tables/record types it touches
4. any important assumptions

---

## 15. Implementation Plan Overview

Implement in five parts.

Do not try to build the whole feature in one pass.

1. **Part 1 — Body Mapping Foundation**
   - canonical body parts
   - body systems
   - relevance types
   - default mapping rules
   - optional schema/table support

2. **Part 2 — Body-Area Record Retrieval**
   - inspect existing tables
   - build one function that gets all records for a selected body part
   - normalize records across labs, meds, vitals, notes, appointments, imaging, wearables

3. **Part 3 — Conservative Health Summary**
   - summarize current status
   - preserve historical flags
   - separate current vs historical context
   - avoid diagnosis/advice

4. **Part 4 — Streamlit Body Map UI**
   - add body-map page/section
   - render clean clickable 2D body model
   - highlight selected organ
   - show summary and record tabs

5. **Part 5 — AI Explanation Buttons**
   - add per-record AI explanation button
   - add body-area summary explanation button
   - use existing Zhipu integration
   - enforce non-diagnostic prompt language

---

# PART 1 — Body Mapping Foundation

## Part 1 Goal

Create the foundational body-part/body-system mapping layer.

This part should not focus on UI yet. It should create the vocabulary and mapping rules that the body map will use.

## Part 1 User Value

The app needs a consistent way to understand that:

~~~text
heart -> cardiovascular
LDL -> heart/cardiovascular/risk marker
creatinine -> kidneys/renal/organ function marker
ALT -> liver/hepatobiliary/injury marker
~~~

Without this foundation, the body map would become a visual gimmick instead of a meaningful health navigation tool.

## Part 1 Requirements

### 1. Add canonical body parts

Add a canonical list or enum of body parts:

~~~text
heart
lungs
brain
liver
kidneys
stomach_intestines
bones
muscles
skin
thyroid
pancreas
lymph_nodes
reproductive_organs
general_body
~~~

### 2. Add canonical body systems

Add a canonical list or enum of body systems:

~~~text
cardiovascular
respiratory
neurologic
gastrointestinal_hepatobiliary
renal_urinary
endocrine_metabolic
hematologic
immune_lymphatic
musculoskeletal
dermatologic
reproductive
general_preventive
~~~

### 3. Add relevance types

Add relevance types:

~~~text
organ_function_marker
risk_marker
injury_marker
systemic_marker
symptom
diagnosis
medication
medication_safety_marker
imaging_or_procedure
wearable_metric
appointment_or_note
cross_system_related
~~~

### 4. Add default organ-to-system mapping

Example:

~~~python
BODY_PART_TO_SYSTEMS = {
    "heart": {
        "primary_systems": ["cardiovascular"],
        "related_systems": ["endocrine_metabolic", "renal_urinary", "respiratory"],
    },
    "lungs": {
        "primary_systems": ["respiratory"],
        "related_systems": ["cardiovascular"],
    },
    "kidneys": {
        "primary_systems": ["renal_urinary"],
        "related_systems": ["cardiovascular", "endocrine_metabolic"],
    },
}
~~~

### 5. Add default record mapping rules

Start with common mappings.

Examples:

~~~python
DEFAULT_RECORD_MAPPINGS = {
    "ldl": {
        "body_parts": ["heart"],
        "body_systems": ["cardiovascular", "endocrine_metabolic"],
        "relevance_type": "risk_marker",
        "confidence": "high",
    },
    "hdl": {
        "body_parts": ["heart"],
        "body_systems": ["cardiovascular", "endocrine_metabolic"],
        "relevance_type": "risk_marker",
        "confidence": "high",
    },
    "triglycerides": {
        "body_parts": ["heart", "liver"],
        "body_systems": ["cardiovascular", "endocrine_metabolic", "gastrointestinal_hepatobiliary"],
        "relevance_type": "risk_marker",
        "confidence": "high",
    },
    "creatinine": {
        "body_parts": ["kidneys"],
        "body_systems": ["renal_urinary"],
        "relevance_type": "organ_function_marker",
        "confidence": "high",
    },
    "egfr": {
        "body_parts": ["kidneys"],
        "body_systems": ["renal_urinary"],
        "relevance_type": "organ_function_marker",
        "confidence": "high",
    },
    "bun": {
        "body_parts": ["kidneys"],
        "body_systems": ["renal_urinary"],
        "relevance_type": "organ_function_marker",
        "confidence": "high",
    },
    "alt": {
        "body_parts": ["liver"],
        "body_systems": ["gastrointestinal_hepatobiliary"],
        "relevance_type": "injury_marker",
        "confidence": "high",
    },
    "ast": {
        "body_parts": ["liver", "muscles", "heart"],
        "body_systems": ["gastrointestinal_hepatobiliary", "musculoskeletal", "cardiovascular"],
        "relevance_type": "injury_marker",
        "confidence": "medium",
    },
    "tsh": {
        "body_parts": ["thyroid"],
        "body_systems": ["endocrine_metabolic"],
        "relevance_type": "organ_function_marker",
        "confidence": "high",
    },
    "a1c": {
        "body_parts": ["pancreas", "heart", "kidneys"],
        "body_systems": ["endocrine_metabolic", "cardiovascular", "renal_urinary"],
        "relevance_type": "risk_marker",
        "confidence": "high",
    },
    "glucose": {
        "body_parts": ["pancreas"],
        "body_systems": ["endocrine_metabolic"],
        "relevance_type": "organ_function_marker",
        "confidence": "high",
    },
    "wbc": {
        "body_parts": ["lymph_nodes"],
        "body_systems": ["immune_lymphatic", "hematologic"],
        "relevance_type": "systemic_marker",
        "confidence": "medium",
    },
    "hemoglobin": {
        "body_parts": ["general_body"],
        "body_systems": ["hematologic"],
        "relevance_type": "organ_function_marker",
        "confidence": "medium",
    },
    "crp": {
        "body_parts": ["general_body", "lymph_nodes"],
        "body_systems": ["general_preventive", "immune_lymphatic"],
        "relevance_type": "systemic_marker",
        "confidence": "medium",
    },
}
~~~

Codex may expand this list if obvious, but should not overdo it in v1.

### 6. Prepare for future user overrides

If schema changes are appropriate, add a mapping table such as:

~~~sql
CREATE TABLE IF NOT EXISTS record_body_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    source_table TEXT NOT NULL,
    record_id TEXT NOT NULL,
    body_part TEXT NOT NULL,
    body_system TEXT NOT NULL,
    relevance_type TEXT,
    relationship_strength TEXT,
    mapping_source TEXT,
    mapping_confidence TEXT,
    explanation TEXT,
    created_at TEXT,
    updated_at TEXT
);
~~~

If schema changes are too risky right now, implement mappings as service-layer logic first and document that persistent mappings are deferred.

## Part 1 Acceptance Criteria

1. Canonical body parts exist in code.
2. Canonical body systems exist in code.
3. Relevance types exist in code.
4. Default organ-to-system mappings exist.
5. Default common record mappings exist.
6. The mapping logic is not embedded in the SVG or UI.
7. Future user override support is considered in either schema or documentation.
8. Documentation is updated in `docs/body_map_implementation_notes.md`.

## Part 1 Documentation Requirement

After implementation, document:

~~~markdown
## Part 1 — Body Mapping Foundation

### Goal
### Files Changed
### Key Functions / Classes Added
### Data Model / Schema Changes
### Assumptions
### How to Test Manually
### Known Limitations
### Next Step
~~~

---

# PART 2 — Body-Area Record Retrieval

## Part 2 Goal

Create a service function that retrieves all records relevant to a selected body part for the selected profile.

## Part 2 User Value

When the user clicks the heart, the app should pull all relevant heart/cardiovascular records from every record type, not just labs.

## Part 2 Requirements

### 1. Inspect the existing project

Codex should inspect the current codebase and identify:

- current database type
- database file location
- existing tables
- existing models/classes
- existing service/query functions
- how selected profile/person is represented
- how records are currently loaded

Do not ask the user for table names. Infer them from the project.

### 2. Create a normalized record shape

Regardless of source table, return records in a normalized structure.

Recommended fields:

~~~text
record_id
person_id
source_table
record_type
name
display_name
date
value
unit
raw_value
status_flag
reference_range
body_part
body_system
relevance_type
relationship_strength
mapping_source
mapping_confidence
summary_text
raw_record
~~~

Not every field will exist for every record type. Missing fields should be `None`, empty string, or omitted consistently.

### 3. Implement core retrieval function

Add a function similar to:

~~~python
def get_records_for_body_part(person_id: str | int, body_part_id: str) -> list[dict]:
    """
    Return all records relevant to a selected body part for one profile/person.
    """
~~~

This function should:

1. Filter by `person_id`.
2. Look up systems related to the selected body part.
3. Query relevant records across available tables.
4. Apply default mapping rules.
5. Include existing body-system/body-part labels if already stored.
6. Include records with direct body-part mapping.
7. Include records with relevant body-system mapping.
8. Include cross-system records only when mapping rules justify it.
9. Return normalized records.

### 4. Include all available record types

Support whatever exists in the app among:

~~~text
lab_results
medications
health_entries
notes
vitals
appointments
conditions
diagnoses
imaging
procedures
wearable_records
~~~

Codex should adapt to actual table names.

### 5. Prevent profile leakage

Every query must filter by selected profile/person.

No function should return records from another person.

### 6. Handle unknown/unmapped records

If a record cannot be mapped:

- do not break
- mark it as unmapped or general
- do not show it under a specific organ unless there is some explicit mapping
- optionally include it under `general_body`

## Part 2 Acceptance Criteria

1. There is a single main retrieval function for body-part records.
2. The function filters by profile/person.
3. The function supports multiple record types.
4. The function returns normalized records.
5. The function supports many-to-many mapping.
6. Cross-system records appear only when mappings justify them.
7. Unknown records do not crash the app.
8. Documentation is updated.

## Part 2 Documentation Requirement

Add this section:

~~~markdown
## Part 2 — Body-Area Record Retrieval

### Goal
### Files Changed
### Key Functions / Classes Added
### Data Model / Schema Changes
### Assumptions
### How to Test Manually
### Known Limitations
### Next Step
~~~

Manual testing instructions should include:

1. Select a profile.
2. Call or trigger the function for `heart`.
3. Confirm heart/cardiovascular records appear.
4. Confirm another profile’s records do not appear.
5. Test an unmapped record.
6. Test at least one non-lab record if available.

---

# PART 3 — Conservative Health Summary

## Part 3 Goal

Create summary logic that converts the retrieved records into a conservative body-area health overview.

## Part 3 User Value

The user should not only see rows. They should immediately understand whether there are relevant records, current flags, historical flags, or insufficient data.

## Part 3 Requirements

### 1. Implement summary function

Add a function similar to:

~~~python
def summarize_body_part_health(records: list[dict]) -> dict:
    """
    Summarize records for a selected body part without diagnosing or giving treatment advice.
    """
~~~

Recommended return shape:

~~~python
{
    "status_label": "Needs review",
    "status_reason": "1 latest relevant record is source-flagged high.",
    "latest_records": [...],
    "flagged_records": [...],
    "historical_flags": [...],
    "unmapped_records": [...],
    "mapping_uncertain_records": [...],
    "record_counts_by_type": {...},
}
~~~

### 2. Separate current and historical status

The summary must distinguish:

- latest/current records
- older historical records
- latest flagged records
- older historical flags

Do not hide old abnormal records.

### 3. Use source flags only

The app currently stores mostly raw values. Some imported records may already include abnormal flags or reference ranges.

In v1:

- use existing source-provided flags when available
- do not invent abnormality from raw values
- do not use AI to decide that a raw value is abnormal
- do not create a diagnosis

### 4. Status labels

Use only these labels unless there is a strong reason to add another:

~~~text
No data
Data available
No flagged items
Needs review
Historical flag found
Mapping uncertain
~~~

### 5. Record sorting

Sort records by date, newest first, where date is available.

If dates are missing, keep those records but place them after dated records.

### 6. Key signals

For each body part, identify key signals from available records.

Example for heart:

~~~text
LDL
HDL
Triglycerides
Blood pressure
Resting heart rate
ECG
Echocardiogram
Cardiac medications
Chest pain / palpitations notes
~~~

Example for kidneys:

~~~text
Creatinine
eGFR
BUN
Urinalysis
Urine albumin/creatinine ratio
Blood pressure
Renal imaging
Renal-relevant medications
~~~

The key signals should be selected from the records that actually exist, not invented.

## Part 3 Acceptance Criteria

1. A body-part summary function exists.
2. The function uses conservative status labels.
3. The function separates latest/current status from historical flags.
4. Old abnormal records remain visible.
5. Raw values are not independently interpreted as abnormal.
6. Source flags are used when available.
7. Records are sorted newest first.
8. Documentation is updated.

## Part 3 Documentation Requirement

Add this section:

~~~markdown
## Part 3 — Conservative Health Summary

### Goal
### Files Changed
### Key Functions / Classes Added
### Data Model / Schema Changes
### Assumptions
### How to Test Manually
### Known Limitations
### Next Step
~~~

Manual testing should include:

1. Body part with no data.
2. Body part with records but no flags.
3. Body part with current source-flagged result.
4. Body part with historical flag but latest normal/unflagged result.
5. Body part with low-confidence mapping.

---

# PART 4 — Streamlit Body Map UI

## Part 4 Goal

Add the user-facing Streamlit interface for the body map.

## Part 4 User Value

The user can click a body part visually and see relevant health context without manually searching tables.

## Part 4 Requirements

### 1. Add Body Map page or section

Create a page/section called something like:

~~~text
Body Map
Interactive Body Map
Body Health Map
~~~

Use the existing app navigation style.

### 2. Use selected profile

The page must use the currently selected profile/person.

If no profile is selected, show a clear message:

~~~text
Select a profile to view the body map.
~~~

### 3. Render a large clean medical body model

Use a 2D front-view SVG or HTML/SVG component.

Visual style:

- clean medical infographic
- simplified organs
- front view only
- large body model at top
- soft colors
- selected region glows
- no hyper-realistic anatomy
- no cluttered labels

### 4. Make regions clickable

Clickable regions should correspond to canonical body-part IDs:

~~~text
heart
lungs
brain
liver
kidneys
stomach_intestines
bones
muscles
skin
thyroid
pancreas
lymph_nodes
reproductive_organs
general_body
~~~

### 5. Highlight selected region

When selected, the body part should visually highlight or glow.

Suggested CSS concept:

~~~css
.selected-organ {
  filter: drop-shadow(0 0 8px rgba(0, 150, 255, 0.8));
  stroke-width: 2.5;
}
~~~

Exact styling can vary.

### 6. Store selected body part in Streamlit state

Use Streamlit state or query params so the selected body part persists across reruns.

Suggested state key:

~~~python
st.session_state["selected_body_part"]
~~~

### 7. Show selected body-part header

Example:

~~~text
Heart / Cardiovascular
~~~

Include:

- display name
- primary system(s)
- related system(s), optionally collapsed

### 8. Show status cards

At top of the result panel, show:

- status label
- status reason
- number of relevant records
- number of current flags
- number of historical flags
- latest relevant date, if available

### 9. Show tabs

Use tabs:

~~~text
Overview
Labs
Vitals
Medications
Notes
Imaging
Wearables
Trends
~~~

Only show tabs that make sense based on available data, or show all tabs with empty states.

### 10. Trends tab

The trends tab should be optional/clicked. Do not make trends the default at-a-glance display.

If trending is already implemented elsewhere, reuse it. If not, provide a simple placeholder or only implement basic trend charts for numeric records with dates.

### 11. Empty states

For a body part with no data, show:

~~~text
No records found for this body area in the selected profile.
~~~

Do not imply the body area is healthy.

### 12. Keep SVG replaceable

Place body-map visual code/assets in a separate file or folder.

Recommended:

~~~text
assets/body_map_front.svg
body_map_ui.py
body_map_config.py
~~~

If using inline SVG, isolate it in a dedicated function/file.

Do not scatter SVG path code throughout `app.py`.

## Part 4 Acceptance Criteria

1. There is a visible Body Map page/section.
2. It uses the selected profile only.
3. A large clean 2D body model appears.
4. Body parts are clickable.
5. Selected body part highlights/glows.
6. Clicking a body part updates the records shown.
7. Status cards are visible.
8. Record tabs are visible.
9. Empty states are handled.
10. Body-map visual asset is isolated and replaceable.
11. Documentation is updated.

## Part 4 Documentation Requirement

Add this section:

~~~markdown
## Part 4 — Streamlit Body Map UI

### Goal
### Files Changed
### Key Functions / Classes Added
### Data Model / Schema Changes
### Assumptions
### How to Test Manually
### Known Limitations
### Next Step
~~~

Manual testing should include:

1. Open the Body Map page.
2. Select a profile.
3. Click heart.
4. Confirm heart highlights.
5. Confirm only that profile’s records appear.
6. Click kidneys.
7. Confirm records update.
8. Test a body part with no data.
9. Confirm the app does not crash on rerun.
10. Confirm the SVG/body visual is isolated and replaceable.

---

# PART 5 — AI Explanation Buttons

## Part 5 Goal

Add AI explanation buttons that help the user understand why a record appears under a body part or what the body-area summary means.

## Part 5 User Value

The app cannot hard-code explanations for every possible lab, medication, note, or wearable metric. AI can explain the relevance in plain language while avoiding diagnosis and treatment advice.

## Part 5 Requirements

### 1. Use existing Zhipu integration

Use the current Zhipu AI integration for v1.

Do not switch AI providers in this part.

Design the code so the provider can be swapped later.

### 2. Add per-record explanation button

For each record shown in a body-part view, provide a button such as:

~~~text
Ask AI why this appears here
~~~

When clicked, the app should send a structured prompt to AI.

Prompt template:

~~~text
Explain why this health record appears under the selected body area in my Personal Health Record.

Selected body area:
{body_part_display_name}

Selected body system(s):
{body_systems}

Record:
- Name: {record_name}
- Type: {record_type}
- Value: {value}
- Unit: {unit}
- Date: {date}
- Source flag: {status_flag}
- Current mapping: {body_part}, {body_system}, {relevance_type}
- Mapping confidence: {mapping_confidence}

Please explain:
1. Why this record is relevant to this body area.
2. Whether it is a direct organ function marker, risk marker, injury marker, systemic marker, medication-related item, symptom, imaging/procedure, wearable metric, or cross-system record.
3. What the source-provided flag means, if a source flag is present.
4. What questions the user may want to ask a clinician.

Important rules:
- Do not diagnose.
- Do not recommend treatment.
- Do not claim certainty from one data point.
- Do not say the user is healthy or unhealthy.
- Use plain language.
~~~

### 3. Add body-area summary explanation button

At the top of the body-part summary, add a button:

~~~text
Explain this body-area summary
~~~

Prompt template:

~~~text
Explain this body-area summary from my Personal Health Record.

Selected body area:
{body_part_display_name}

Selected body system(s):
{body_systems}

Summary:
- Status label: {status_label}
- Status reason: {status_reason}
- Number of relevant records: {record_count}
- Current flagged records: {current_flag_count}
- Historical flagged records: {historical_flag_count}
- Latest relevant date: {latest_date}

Representative records:
{record_list}

Please explain:
1. What this summary is saying.
2. Why these records may be relevant to this body area.
3. What current flags or historical flags mean in general.
4. What questions the user may want to ask a clinician.

Important rules:
- Do not diagnose.
- Do not recommend treatment.
- Do not claim certainty from incomplete data.
- Do not say the user is healthy or unhealthy.
- Explain that the PHR may be incomplete if data is missing.
- Use plain language.
~~~

### 4. Keep AI response separate from source data

The AI explanation should be displayed as an explanation, not stored as a diagnosis or official medical conclusion.

If saved, it should be clearly marked as AI-generated explanatory text.

### 5. Avoid cross-profile leakage

The AI prompt must include only the selected profile’s records.

Do not include family/dependent records unless that dependent profile is currently selected.

### 6. Error handling

If AI fails, show a friendly error:

~~~text
AI explanation is unavailable right now. The records and summary are still shown above.
~~~

## Part 5 Acceptance Criteria

1. Per-record AI explanation buttons exist.
2. Body-area summary explanation button exists.
3. Zhipu integration is used.
4. Prompts include selected body area and record context.
5. Prompts include safety constraints.
6. AI does not receive records from other profiles.
7. AI failure does not break the page.
8. Documentation is updated.

## Part 5 Documentation Requirement

Add this section:

~~~markdown
## Part 5 — AI Explanation Buttons

### Goal
### Files Changed
### Key Functions / Classes Added
### Data Model / Schema Changes
### Assumptions
### How to Test Manually
### Known Limitations
### Next Step
~~~

Manual testing should include:

1. Click heart.
2. Click AI explanation for one record.
3. Confirm response explains relevance without diagnosis.
4. Click body-area summary explanation.
5. Confirm response uses only selected profile data.
6. Simulate AI failure if possible.
7. Confirm the app does not crash.

---

## 16. Recommended Codex Workflow

Use one master PRD file and implement in parts.

Recommended workflow:

~~~text
1. Put this full PRD in docs/body_map_prd.md.
2. Tell Codex: "Read docs/body_map_prd.md. Implement Part 1 only. Stop after updating docs/body_map_implementation_notes.md."
3. Review the changes.
4. Then tell Codex: "Now implement Part 2 only."
5. Repeat until Part 5 is complete.
~~~

Codex should not attempt all five parts in one pass.

This reduces uncontrolled changes and makes debugging easier.

---

## 17. Final Expected User Experience

After all five parts are complete:

1. User opens the PHR.
2. User selects a profile.
3. User opens the Body Map page.
4. User sees a clean front-view anatomical infographic.
5. User clicks the heart.
6. The heart glows.
7. The app shows:

~~~text
Heart / Cardiovascular

Status:
Needs review

Why:
1 latest cardiovascular-related record is source-flagged high.
2 historical cardiovascular-related flags found.

Latest relevant records:
- LDL Cholesterol — 145 mg/dL — High — Jun 2026
- Blood Pressure — 128/82 — Jun 2026
- Resting Heart Rate — 66 bpm — Jun 2026
~~~

8. User can switch tabs:

~~~text
Overview | Labs | Vitals | Medications | Notes | Imaging | Wearables | Trends
~~~

9. User can click:

~~~text
Ask AI why this appears here
~~~

10. AI explains the relevance without diagnosing or recommending treatment.

---

## 18. Final Technical Constraints

1. This is a Streamlit feature.
2. Use a 2D body map for v1.
3. Keep body-map visuals replaceable.
4. Keep mapping logic separate from UI.
5. Use selected profile/person ID for every query.
6. Support many-to-many mapping.
7. Use source flags when available.
8. Do not infer abnormality from raw values in v1.
9. Preserve historical flags.
10. Use Zhipu AI for explanations.
11. Do not implement full-stack migration in this feature.
12. Document every part in `docs/body_map_implementation_notes.md`.
13. Keep one master PRD file for complete context.
14. Split code into focused files by responsibility.
15. Do not split code into `part1.py`, `part2.py`, etc.

---

## 19. Final Deliverables

By the end of this feature, Codex should have produced:

1. Body-part/body-system mapping config.
2. Default common record mapping rules.
3. Optional persistent mapping table or documented deferred schema plan.
4. Body-area record retrieval service.
5. Normalized record output structure.
6. Conservative body-area summary service.
7. Streamlit Body Map page or section.
8. Clickable, replaceable 2D body model.
9. Selected-region highlight/glow.
10. Record tabs by category.
11. Optional trends tab.
12. AI explanation buttons.
13. Documentation file:
   - `docs/body_map_implementation_notes.md`
14. Docstrings for important functions.
15. Manual testing notes for each part.

---

## 20. Instruction to Codex

Implement this feature in the five parts listed above.

Do not try to build the whole feature in one pass.

After each part:

1. Stop.
2. Run or describe appropriate tests.
3. Update `docs/body_map_implementation_notes.md`.
4. Summarize what changed.
5. List assumptions.
6. List known limitations.
7. State which part should be implemented next.

Prioritize:

1. clean structure
2. profile isolation
3. conservative medical wording
4. replaceable visual assets
5. modular code by responsibility
6. readable documentation

over visual complexity.
