# ADR-0004 — Deployment model: local-first

- **Status:** Accepted
- **Date:** 2026-08-01
- **Decider:** Daniel
- **Change class:** Architectural (with Critical implications — privacy boundary)
- **Supersedes:** *"Local desktop versus hosted web deployment"* (`SoT:1251`) and informs *"Single-tenant family app versus multi-tenant platform"* (`SoT:1261`), *"Local desktop app, hosted app, or hybrid"* (`SoT:2043`)

## Context

This decision was surfaced because the *database* choice appeared to be the open question, when in fact
the database is downstream of the deployment model. Committing to a server-based database would have
silently decided deployment, tenancy, and regulatory posture as a side effect of a technical choice.

The project documents already lean one way, consistently and in load-bearing places: the repository title
is *"Local-First Family Personal Health Record"* (`SoT:2301`), with local-first positioning restated at
`SoT:52`, `SoT:989`, `SoT:1275`, and checked off at `SoT:2182`.

The stated product thesis is that **patients should own their own data and choose how it is used.**

`SoT:1332-1340` already identifies what attaches on the other branch: HIPAA applicability depends on
product relationships and data flows; the FTC Health Breach Notification Rule may apply to consumer
health apps; state consumer-health-data laws may apply.

## Options considered

**A. Local-first; sync and sharing as later, explicitly-enabled slices.** Data lives on the user's
machine by default. Nothing leaves without a deliberate action. Matches every positioning statement in
the documents and keeps the app outside HIPAA/FTC-HBNR scope for now.

**B. Hosted web app.** Accounts, server-side storage, standard SaaS distribution. Easier to demo, sell,
and support. Immediately places the project in regulatory scope, requires the security posture listed as
absent in `docs/domain_invariants.md` §8 (encryption at rest, audit logs, real authentication, consent
tracking) *before* it could responsibly hold anyone's records, and contradicts the positioning — which
would then need rewriting rather than defending.

**C. Explicitly defer.** Build stack-neutral and decide later. Rejected as a deployment decision because
"undecided" is not neutral in practice: every slice would carry a hedge, and the walking skeleton would
be designed for a product shape nobody had chosen. Deferral is retained *within* ADR-0003 for the
database engine, where it is genuinely cheap.

## Decision

**Local-first. Sync, sharing, and any hosted component are later slices, each explicitly enabled by the
user.**

The privacy claim and the interoperability architecture are the same thing. "The patient holds the record
and grants access" is simultaneously the differentiator and the technical design; hosting by default
forfeits the claim while gaining nothing that cannot be built later on top of it.

## Consequences

### Interoperability is not blocked by this — it is enabled by it

Patient-directed access assumes the patient holds a copy. That is the premise of the Cures Act
information-blocking rules and consumer-directed API guidance already cited at `SoT:1338-1339`. The
substrate exists: `fhir.py` is 711 lines of working R4/R5 Bundle export and import, and it is
storage-location agnostic.

What is genuinely hard is **not** where the bytes sit:

- **Reading from EHRs** (SMART on FHIR, US Core profiles) requires registering the app with each EHR
  vendor's developer program and increasingly with interoperability networks. This is business-development
  and compliance work. *Verify current program requirements at the time of implementation — these change.*
- **Writing back to an EHR** is much harder and frequently unsupported; most systems do not accept
  patient-generated data. Already open at `SoT:2048`.
- **Emergency access** is hard for trust reasons, not technical ones: an unconscious patient cannot
  authorize anything. Any "connected to the emergency provider" design must answer who authorizes, how
  it is revoked, and how it resists abuse.

### The emergency card is local-first-native

`services.generate_emergency_snapshot(person_id)` (services.py) and its page already exist. A signed,
offline-verifiable QR or PDF card the patient carries needs no server, no account, and no network. This
is a case where local-first is **better** than hosted, not a constraint to work around — worth treating
as evidence the positioning is a product asset.

### Engineering consequences

- **Schema migration becomes harder, not easier.** N users hold N private database files at N schema
  versions, and the app must migrate each correctly, offline, at startup, without data loss. A hosted
  product runs one migration against one server. This is the central input to ADR-0003.
- Encryption at rest and key management become *user-device* problems (see `domain_invariants.md` §8).
- Backup and restore are user-facing features, not operations tooling.
- Authentication is a local unlock, not an identity system — until sharing exists, at which point a real
  identity boundary is required for the sharing path only.
- Multi-device use is not supported until a sync slice exists. This is a real product limitation and
  should be stated to users plainly rather than implied away.

## Reversibility

High in one direction, low in the other. Local-first → hosted is a substantial but ordinary project
(server, accounts, migration of user data with consent). Hosted → local-first is much harder, because by
then the product, the security posture, and the user expectations have all been built around a server.
Choosing local-first first is the option that preserves the most future choice.

## What would falsify this

- Validated demand that depends on multi-device or family-shared real-time access, which local-first
  cannot serve without a sync slice that turns out to cost more than hosting would have.
- A provider-connected wedge where providers must *pull* from the patient. A provider-initiated pull
  requires a reachable endpoint, which forces the hybrid model — local data plus a thin, user-enabled
  relay. **This is the recorded trigger to revisit this ADR.**
- Regulatory or partnership requirements that mandate server-side custody and auditability.
