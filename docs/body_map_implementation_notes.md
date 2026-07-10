# Body Map Implementation Notes

This file is the implementation log required by `docs/body_map_prd.md`.
Append one completed section per implementation part. Record actual changes and tests; do not prefill
future parts with speculative content.

## Part X — [Part Name]

### Goal

[What this part was intended to implement.]

### Files Changed

- `path/to/file`: [short description]

### Key Functions / Classes Added

- `function_or_class`: [responsibility]

### Data Model / Schema Changes

[New tables, columns, indexes, constants, config structures, migration behavior, or “None.”]

### Assumptions

- [Assumption made from the current codebase or PRD]

### Automated Tests

- `[command]`: [result]

### How to Test Manually

1. [Step]
2. [Expected result]

### Known Limitations

- [What this part deliberately does not handle]

### Next Step

[Next PRD part or remaining work.]

## Part 1 — Body Mapping Foundation

### Goal

Create an SVG-independent vocabulary and deterministic mapping layer for later body-map retrieval,
summary, and UI work.

### Files Changed

- `body_map_config.py`: added canonical definitions, immutable mappings, lookup normalization, and
  validation.
- `tests/test_body_map_config.py`: added focused Part 1 integrity, behavior, and failure tests.
- `docs/body_map_implementation_notes.md`: recorded the completed Part 1 implementation.

### Canonical Definitions

- 14 body-part IDs and display names.
- 12 body-system IDs and display names.
- 12 relevance types.
- Confidence values: `high`, `medium`, `low`.
- Relationship strengths: `primary`, `secondary`.
- Primary and related organ-to-system relationships for every body part.

### Default Mappings Added

Curated mappings cover LDL, HDL, triglycerides, creatinine, eGFR, BUN, ALT, AST, TSH, A1c,
glucose, WBC, hemoglobin, and CRP. Each mapping identifies body parts, body systems, relevance type,
confidence, and primary/secondary relationship strength. AST, WBC, and CRP retain medium confidence
and explicit multisystem relationships rather than implying organ health from a raw result.

### Public Interfaces

- `get_default_record_mapping(record_name)`: returns an immutable `RecordBodyMapping` or `None`.
- `normalize_record_name(record_name)`: normalizes supported exact names and aliases without fuzzy
  matching.
- `validate_record_mapping(mapping)`: rejects empty or non-canonical mapping data.
- `build_record_mapping_registry(definitions)`: validates aliases and returns immutable registries.
- `BODY_PARTS`, `BODY_SYSTEMS`, `BODY_PART_TO_SYSTEMS`, and canonical ID tuples expose the vocabulary.

### Alias and Normalization Rules

Lookup is case-insensitive and ignores surrounding whitespace and ordinary punctuation, including
hyphens, slashes, and underscores. Explicit aliases cover the required expanded lab names. Unknown
names do not receive partial or fuzzy matches. Exact uppercase `EGFR` remains unmapped because it may
refer to the EGFR gene/receptor; `eGFR` and the expanded kidney-function names resolve normally.

### Data Model / Schema Changes

None. Defaults are immutable in-process configuration and do not access SQLite.

### Future Override Precedence

1. User-specific override.
2. Stored reviewed mapping.
3. Curated default mapping.
4. AI suggestion.
5. Unmapped/general fallback.

Persistent user overrides are deferred until their storage and review workflow is implemented.

### Assumptions

- Curated mappings express record relevance, not diagnoses or conclusions about organ health.
- A mapping can have multiple primary relationships when a marker is directly systemic across more
  than one system.
- Canonical body-map systems intentionally remain separate from the existing timeline display choices
  in `models.py`.

### Tests Added

- `tests/test_body_map_config.py` covers exact canonical sets, system integrity, required mappings,
  conservative multisystem confidence, aliases, normalization, ambiguity, immutability, and invalid
  definitions.

### Automated Tests

- `.venv/bin/python -m pytest -q tests/test_body_map_config.py`: 44 passed.
- `.venv/bin/python -m pytest -q tests/test_basic.py`: 31 passed.
- `./scripts/verify.sh`: compile checks passed; 75 tests passed.

### How to Test Manually

1. Import `body_map_config` in a Python shell.
2. Call `get_default_record_mapping("LDL cholesterol")` and confirm it returns the heart,
   cardiovascular, risk-marker, high-confidence mapping.
3. Call `get_default_record_mapping("unknown test")` and confirm it returns `None`.

### Known Limitations

- Part 1 maps only the required curated record names; there is no fuzzy or context-specific matching.
- There are no persistent overrides, database retrieval, summaries, SVG assets, or UI integration.
- The uppercase `EGFR` ambiguity rule is intentionally case-sensitive.

### Next Step

Part 2 — implement selected-profile, normalized body-area record retrieval using this mapping layer.

## Part 2 — Body-Area Record Retrieval

### Goal

Retrieve every existing record relevant to one canonical body part for one selected profile, with a
single normalized result per source record and no medical interpretation.

### Files Changed

- `body_map_services.py`: added profile-scoped retrieval, source adapters, stored-mapping precedence,
  canonical normalization, and deduplication by construction.
- `tests/test_body_map_services.py`: added Part 2 isolation, mapping, boundary, normalization, adapter,
  deduplication, and error regression tests.
- `docs/body_map_implementation_notes.md`: recorded the completed Part 2 implementation.

### Key Functions / Classes Added

- `NormalizedBodyRecord`: typed normalized shape shared by all retrieved source records.
- `get_records_for_body_part(person_id, body_part_id, db_path)`: queries every supported source table
  with the selected `person_id`, applies explicit or curated mappings, and returns matching records.

### Data Model / Schema Changes

None. Retrieval reuses the existing `lab_results`, `medications`, `health_entries`, `appointments`,
and `wearable_records` tables. Only `health_entries` currently stores explicit body-part/body-system
fields.

### Assumptions

- An exact, canonicalizable `health_entries.body_part` or `body_system` value is an explicit stored
  mapping and takes precedence over a conflicting curated name mapping.
- A stored system expands only to body parts for which that system is primary. Related systems do not
  pull records into an organ.
- Tables without stored body-area fields participate only when their record-name field matches a Part
  1 curated mapping exactly or through a Part 1 alias.

### Automated Tests

- `.venv/bin/python -m pytest -q tests/test_body_map_services.py tests/test_body_map_config.py`: 65
  passed.
- `./scripts/verify.sh`: compile checks passed; 96 tests passed.

### How to Test Manually

1. Initialize a temporary database and create two fictional profiles.
2. Add an LDL lab and a cardiovascular health entry for the first profile, plus similar records for
   the second profile.
3. Call `get_records_for_body_part(first_profile_id, "heart", db_path=temp_db_path)`.
4. Confirm only the first profile's heart records appear and every result has the normalized fields.
5. Add an unknown lab name and confirm it does not appear under `heart`.
6. Add a respiratory-only health entry and confirm it appears under `lungs` but not `heart`.

### Known Limitations

- There is no UI in Part 2.
- Medications, appointments, and wearables have no existing stored body-area columns, so most such
  records remain unmapped until a later explicit mapping design exists; no schema was invented here.
- Mapping uses exact canonical IDs, existing display labels, and Part 1 aliases only; there is no
  fuzzy, inferred, or AI mapping.

### Next Step

Part 3 — build conservative current and historical summaries from these normalized records.
