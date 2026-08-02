# ADR-0002 — Frontend framework: React + TypeScript

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decider:** Daniel
- **Change class:** Architectural
- **Supersedes:** the "Frontend framework" entry under *Unresolved architecture choices*, `PHR_PROJECT_SOURCE_OF_TRUTH_2026-07-28.md:1248`

## Context

`PHR_PROJECT_SOURCE_OF_TRUTH_2026-07-28.md:1170-1179` records the decision to move off Streamlit, naming
**body-map interaction as the concrete migration pressure** and noting that adaptive UI is intended
after the migration. §33 (line 1757) records the current symptom plainly: "Body-map navigation behavior
is constrained or broken."

The evidence for that is in the repository, not in preference:

1. **The body map is already a hand-written web component.** `components/body_map/index.html` is 31 lines
   of vanilla JS in a Streamlit custom component — the escape hatch that exists precisely because
   Streamlit could not express the interaction.
2. **Tests exist solely to fight the rerun model.** `tests/test_body_map_ui.py` carries
   `test_profile_change_clears_stale_body_state`, `test_component_key_changes_only_with_profile_or_database_scope`,
   `test_component_value_does_not_override_fallback_without_a_new_event`, and `test_invalid_state_is_reset`.
   None of these test a product behavior. They test that state survives Streamlit re-executing the script
   top-to-bottom.
3. **Tenant identity is round-tripped through a UI string.** `st.session_state["selected_profile"]` holds
   a display label — `"Alice (ID 3)"` — and the person is recovered with `names.index(selection)`. The
   identity of the patient whose records are on screen is reconstructed from formatted presentation text
   because Streamlit offered nowhere better to put it. See `docs/current_system.md` §5.

Note on a frequently-miscited constraint: `docs/body_map_prd.md:112` says "Do not implement React,
Three.js, or React Three Fiber." That sits under **"Non-Goals for V1"**, alongside "Do not migrate the
app from Streamlit to a full-stack app yet" (line 111). It scoped the body-map V1 feature. It is not a
constraint on the target stack, and it is superseded here.

## Options considered

**A. React + TypeScript.** Component-local state and explicit data flow remove the entire class of
problems the tests above exist to catch. Typed API clients pair with FastAPI's generated OpenAPI schema.
The largest ecosystem for the interactive/SVG work the body map needs, and the skill transfers.
Cost: a build toolchain, a second language, and a real client/server split where none exists today.

**B. HTMX / server-rendered templates.** Dramatically less machinery — one language, no bundler, no
client state to synchronize. Genuinely attractive for the seven CRUD pages, which are forms and tables.
Rejected because it does not solve the problem that motivated the migration: rich body-map interaction
still lands in hand-written JS, which is exactly where the pain is today. It optimizes the easy 80% and
leaves the hard 20% unchanged.

**C. Vue or Svelte.** Both technically sufficient and arguably simpler than React. Smaller ecosystems for
interactive-diagram work, and the transferable-skill argument is weaker.

## Decision

**React + TypeScript.**

To be explicit about reasoning, because this ADR will be reviewed: "many companies use React" is a real
career consideration but is *not* an architecture argument and does not justify this decision on its own.
The decision rests on (1) the body map being the stated migration pressure and already having escaped
Streamlit into hand-written JS, (2) an existing test suite whose body-map portion is substantially
devoted to working around framework behavior rather than verifying product behavior, and (3) tenant
identity currently living in a presentation string. React is chosen over Vue/Svelte partly on ecosystem
fit for interactive diagrams and partly on transferability — the tiebreaker, not the case.

## Consequences

- A build toolchain (Vite assumed) and a typed API client generated from FastAPI's OpenAPI schema.
- `app.py` (1,516 lines: routing, ~260 lines of CSS, form plumbing, presentation, demo mode) decomposes
  into components. `app.FIELD_CONFIGS` — already a declarative form/table schema — is the natural seam:
  seven of sixteen pages are rendered by one config-driven function today and should stay that way.
- The body map becomes a first-class component; `components/body_map/index.html` and the Streamlit
  component bridge are retired.
- **Person isolation must be re-established server-side.** Today two gates (`require_profile`,
  `security.health_data_visible`) are UI-level only — the service layer will happily return a locked
  profile's data if called directly. Once a browser can call the API, UI gates are decorative.
  See `docs/domain_invariants.md` §1.
- The selected profile becomes real client state backed by a server-side identifier, replacing the
  `(active_db_path(), person_id)` pair reconstructed from a label string.
- Streamlit must keep working until each replacement slice is verified (`PHR_LEARNING_PROTOCOL:49`).

## Reversibility

Low-to-moderate, and this is the more expensive of the two framework decisions to unwind. A committed
React app is not cheaply re-hosted in a server-rendered model. Mitigation: keep business logic on the
server. If the frontend stays a rendering and interaction layer with no domain rules, replacing it is
bounded work.

## What would falsify this

- If, after the walking skeleton, the seven CRUD pages account for nearly all real usage and the body map
  does not become the differentiating feature, then option B's simplicity was the better trade and this
  decision bought complexity for a feature that did not matter.
- If the product commits to a native mobile app, the shared-code calculus changes and React Native or a
  cross-platform framework should be re-evaluated. `SoT:2049` leaves "responsive web or native" open.
