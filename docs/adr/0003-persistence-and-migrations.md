# ADR-0003 — Persistence layer and schema migrations

- **Status:** Accepted
- **Date raised / decided:** 2026-08-01
- **Decider:** Daniel
- **Change class:** Architectural, with Critical implications (record-altering migration)
- **Blocks:** the walking skeleton (migration step 3). This is the last open blocker.
- **Depends on:** ADR-0004 (local-first) — which constrains but does not settle this

## Context

Three sub-decisions are entangled here and are separated deliberately below, because they have different
answers and different reversibility:

- **3a.** Migration tooling — how the schema evolves.
- **3b.** Database engine — SQLite now, or Postgres from day one.
- **3c.** Access layer — SQLAlchemy ORM, SQLAlchemy Core, or neither.

### The problem that forces this now

`schema.sql` is entirely `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`. **Any column added
to an existing `data/phr.db` silently does nothing.** It appears only in fresh databases — and every
test passes, because tests build fresh databases. Today the app has no way to evolve a schema against
data a user already has.

ADR-0004 makes this harder rather than easier. A hosted product runs one migration against one server.
Local-first means N users hold N private database files at N different schema versions, and the app must
migrate each one correctly, offline, at startup, without losing data that exists nowhere else.

Schema knowledge is also currently triplicated across `schema.sql`, `db.TABLE_COLUMNS`, and
`app.FIELD_CONFIGS`, hand-synced with nothing enforcing agreement (`docs/current_system.md` §4).

---

## 3a. Migration tooling

### Option A1 — Alembic

Versioned, ordered, reversible migrations with the version recorded inside each database. Autogenerates
candidate migrations by diffing model definitions. Dialect-aware, so the same migration set can target
SQLite and Postgres.

Sharp edges, stated up front so they do not ambush execution:

- **SQLite requires batch mode.** SQLite's `ALTER TABLE` cannot drop columns or alter types; Alembic
  emulates this by recreating the table via `op.batch_alter_table(...)`. Plain `op.alter_column(...)`
  works on Postgres and fails on SQLite — a trap that only fires in one direction.
- **Existing databases need stamping.** Any `data/phr.db` already in use carries no Alembic version. This
  needs an initial migration representing today's schema plus an `alembic stamp` path for pre-existing files.
- **Local-first inverts the workflow.** Alembic assumes migrate-at-deploy against one server. Here it must
  run programmatically at app startup against the user's file. That works, but the failure handling is
  ours to own: back up the file before migrating, and define behavior when a migration fails partway on a
  user's machine with no operator present.
- **Autogenerate is a draft.** It misses server defaults and some constraint changes. Every generated
  migration needs reading.

### Option A2 — Hand-rolled runner over `PRAGMA user_version`

SQLite has a built-in schema-version integer. A runner that reads it, applies ordered SQL scripts, and
bumps it is roughly 100 lines with zero dependencies. For a small local-first SQLite app this is a
legitimate engineering choice, not a hack — and it makes the startup-migration and backup-first logic
explicit rather than adapted from a server-shaped tool.

Its cost is that it is **SQLite-only**. If 3b ever chooses Postgres, it is thrown away and rewritten.

### Note

Alembic depends on SQLAlchemy — "Alembic without SQLAlchemy" is not an available combination. Alembic
with SQLAlchemy *Core only* (or with raw SQL inside migration scripts) is.

---

## 3b. Database engine — the substantive decision

### The reasoning that must not carry this decision

"SQLite is slow and cannot scale" is the common formulation and it is imprecise. For this workload SQLite
is typically **faster** than Postgres: no network round trip, no IPC, the data is in-process. The real
constraints are different:

- **One writer at a time.** WAL mode allows concurrent readers plus a single writer. Fine for a family
  app; fatal at thousands of concurrent users.
- **It is a file, not a server.** Multiple backend processes or machines cannot share it over a network.
  *This* is the scaling wall, not speed.
- **No roles, no row-level security, no replication.**

Under ADR-0004 (local-first, single-family), **none of these constraints currently bind.**

### Option B1 — SQLite now, Postgres-compatible, trigger recorded

Ship on SQLite. Use Alembic and an access layer that avoids Postgres-only types (JSONB, arrays,
`RETURNING`-heavy patterns) so the engine stays swappable. Record an explicit trigger for revisiting:
first multi-tenant user, or observed concurrent-write contention.

- **For:** matches the deployment model actually chosen; no server dependency in any slice; zero
  infrastructure for a user running the app on their laptop; keeps the decision cheap to reverse.
- **Against:** loses dev/prod parity if the product later goes hosted. SQLite's dynamic typing accepts
  rows Postgres would reject, its `ALTER TABLE` is limited, and it enforces constraints more loosely — so
  a class of bugs surfaces at deploy rather than in development. Portability is only real if the
  Postgres-only-types discipline is actually maintained, which requires ongoing attention.

### Option B2 — Postgres from day one

Run Postgres (Docker in development) from the walking skeleton onward.

- **For:** full dev/prod parity; strict typing and constraint enforcement catch data bugs early; no
  migration surprise later; row-level security available if multi-tenancy ever arrives.
- **Against:** contradicts ADR-0004 unless local-first is reframed as "embedded DB plus sync," which is a
  separate and substantial project. Adds a server dependency to every subsequent slice and to any
  contributor's setup. For a single-family local app it is infrastructure with no current user benefit.

---

## 3c. Access layer

### Option C1 — SQLAlchemy ORM

Declarative models as the single source of schema truth, which collapses today's triplication and lets
Alembic autogenerate from real definitions. Declared relationships move the delete-children guarantee
into the database — the schema currently has **no `ON DELETE CASCADE`**, and `services.delete_person`
enforces it in Python. Typed models feed FastAPI response schemas directly.

Cost: a real learning curve (2.0-style is a shift), and ORMs hide query cost until it bites.

### Option C2 — SQLAlchemy Core

Dialect portability and safe query construction without ORM indirection. Retires the hand-rolled query
builder at `db.py:200-225`, where table and column names are f-string-interpolated into SQL and defended
by an allowlist — code that works today but is the most likely place for a future injection bug.

Cost: no declared relationships, no autogenerate from models, so schema truth still lives in more than
one place.

### Option C3 — Keep the current hand-rolled layer

`db.py` is 343 lines and works. Cost: the f-string query builder stays, portability is manual, and
schema triplication persists.

---

---

## Appendix — cost of being wrong, in each direction

Requested before ruling on 3b. Grounded in `schema.sql` as it exists, not in general argument.

### The relevant property of the current schema

**Every date and timestamp is `TEXT`**: `date_of_birth`, `lab_date NOT NULL`, `entry_date NOT NULL`,
`appointment_date NOT NULL`, `due_date NOT NULL`, `timestamp NOT NULL`, `created_at`, `updated_at`.
In SQLite, `TEXT` accepts `"2026-13-45"`, `"sometime last year"`, or `""`. A Postgres `DATE` column
rejects all three at insert.

**SQLite's declared types are advisory.** `severity INTEGER` will store `"very bad"`; `numeric_value REAL`
will store `"abc"`; there is not a single `CHECK` constraint in the file, so the controlled vocabularies in
`models.py` (`MEDICATION_STATUSES`, `LAB_FLAGS`, …) are enforced only in Python.

This is not hypothetical. The app **already tolerates malformed stored data by design**, and has tests
proving it: `test_invalid_reminder_dates_are_skipped_in_due_calculations`,
`test_display_dataframe_keeps_unparseable_dates_unchanged`, and
`test_malformed_wearable_values_do_not_crash_summaries`. Those tests exist because such rows occur.
So a future Postgres migration will encounter them.

### If you choose SQLite and later need Postgres

| Cost | Size | Notes |
|---|---|---|
| Engine swap | **Small — days** | With SQLAlchemy ORM + Alembic already chosen, this is largely a connection URL and column-type refinement, provided JSONB/arrays/PG-only types were avoided |
| Consolidating N user databases into one server, with tenancy and `person_id` remapping across 7 child tables | **Large** | **But unavoidable in either branch** — see below |
| Cleaning data SQLite accepted and Postgres rejects | **Real, and risky** | Unparseable dates, non-numeric numerics, out-of-vocabulary statuses. Risky because it is health data: you cannot silently coerce it without violating the provenance invariant (`domain_invariants.md` §2) |

**The load-bearing observation:** the consolidation cost is paid in *both* branches. Going local-first →
hosted means moving users' data onto a server regardless of which engine ran locally. Postgres-from-day-one
avoids that cost only if you **never ship local-first at all** — in which case ADR-0004 has been abandoned,
not implemented.

So B2's "parity" benefit reduces to exactly one thing: avoiding the dirty-data cleanup. That is a genuine
benefit, and it is the only one.

### If you choose Postgres and stay local-first

Nothing breaks. The cost is paid continuously instead of at a moment.

| Cost | Size | Notes |
|---|---|---|
| **Distribution** | **Blocking** | A family member running this on their laptop would need Postgres. That means bundling/embedding a server or shipping Docker to non-technical users. This does not merely add work — it obstructs shipping the local-first product at all |
| Backup/restore regression | Moderate | Today backup is "copy a file" plus a JSON export the user can read. With Postgres it becomes `pg_dump` — a user-facing feature made worse |
| Contributor setup | Small | Everyone needs Docker running to run the suite |
| Offline and emergency-card story | Moderate | The signed offline card (ADR-0004) is simplest when there is no server in the picture |

Reverting is again a small engine swap — but you would have spent the intervening time unable to ship the
thing that differentiates the product.

### The mitigation that captures most of B2's benefit at near-zero cost

The dirty-data risk is B1's only real exposure, and it does not require a server to address:

1. **Run the test suite against both engines in CI.** SQLAlchemy makes this cheap — parameterize the
   connection URL and run `pytest` twice. Type and constraint divergence then surfaces at commit time
   rather than at migration time, while production still ships SQLite.
2. **Use real column types in the ORM models** — `Date`, `DateTime`, `Numeric` — instead of carrying the
   current `TEXT`-for-everything shape forward into the new layer.
3. **Add `CHECK` constraints** for the `models.py` vocabularies, so the database enforces what is presently
   Python-only.

Together these buy Postgres-grade strictness on SQLite. They also improve the system whether or not
Postgres ever arrives, which is the mark of a good hedge.

### Summary

- B1's worst case is a **concentrated, one-time, partly-unavoidable** cost, arriving at a trigger you
  choose, and largely mitigable in advance.
- B2's worst case is a **continuous** cost that obstructs shipping the product ADR-0004 just committed to.

---

## Decision

**3a — Migration tooling: Alembic.** Decided 2026-08-01. Chosen over the `PRAGMA user_version` runner
because it survives the engine question; the runner is SQLite-only and would be discarded if 3b ever
moved. The sharp edges above (batch mode, stamping existing files, startup-migration with backup-first
failure handling) are accepted and must be handled explicitly during slice 3.

**3c — Access layer: SQLAlchemy ORM.** Decided 2026-08-01. Chosen for the single-source-of-truth property
that collapses the current triplication across `schema.sql`, `db.TABLE_COLUMNS`, and `app.FIELD_CONFIGS`,
and for declared relationships that move the delete-children guarantee out of Python and into the database
(no `ON DELETE CASCADE` exists today). Accepted cost: learning curve, and vigilance about query cost in the
body-map and analytics read paths.

**3b — Database engine: SQLite now, Postgres-compatible, with three mitigations and a recorded
trigger.** Decided 2026-08-01 after the cost analysis above.

Rationale, in the order it actually decided the question: consolidating N local databases onto a server is
unavoidable in *either* branch, so Postgres-from-day-one's only genuine benefit is avoiding dirty-data
cleanup — and that benefit is purchasable without a server. Against it stands a continuous cost that
obstructs shipping the local-first product ADR-0004 commits to.

**Required mitigations, landing with the walking skeleton (slice 3), not deferred:**

1. **Dual-engine CI.** Run the suite against SQLite *and* Postgres by parameterizing the connection URL.
   Type and constraint divergence then surfaces at commit time instead of at migration time, while
   production ships SQLite.
2. **Real column types in the ORM models** — `Date`, `DateTime`, `Numeric`. Do **not** carry the current
   `TEXT`-for-every-date shape into the new layer.
3. **`CHECK` constraints** for the `models.py` controlled vocabularies (`MEDICATION_STATUSES`, `LAB_FLAGS`,
   `REMINDER_STATUSES`, `APPOINTMENT_STATUSES`, `WEARABLE_METRIC_TYPES`), which the database does not
   enforce today at all.

These were chosen to land with slice 3 because the models are being written then anyway, and because
divergence that never accumulates costs nothing to fix.

**Switch trigger:** first multi-tenant user, or observed concurrent-write contention. Revisit this ADR at
that point, not before.

**Constraint this imposes on all subsequent slices:** no Postgres-only types (JSONB, arrays,
`RETURNING`-heavy patterns). Portability is only real if this discipline is maintained; dual-engine CI is
what makes the discipline self-enforcing rather than aspirational.

### Migrating existing data

One consequence needs care during slice 3. Existing `data/phr.db` files hold rows that the new typed
columns will reject — unparseable dates and non-numeric numerics that the current app tolerates by design.
Those rows must be surfaced for user review, **not silently coerced or dropped**: `docs/domain_invariants.md`
§2 forbids silently altering or reinterpreting records. The initial migration therefore needs a quarantine
or report path, not just a type change.

Recommended framing for the ruling, in dependency order:

1. **3b first** — it determines whether 3a's cheap option is even viable.
2. **3a follows** — if 3b is SQLite-only forever, A2 is genuinely on the table; if Postgres is reachable,
   A1 is the only sane choice.
3. **3c last** — the least consequential and the easiest to change later.

## Consequences to record once decided

- Whichever combination is chosen, the **first migration must represent today's schema** and there must
  be a stamping path for existing `data/phr.db` files.
- Backup-before-migrate at app startup is required under ADR-0004 regardless of tooling.
- The chosen layer must express the person-scoping contract established in `2e8261e`: scoped update and
  delete predicated on `person_id`, with a not-found result that does not distinguish "missing" from
  "not yours" (`docs/domain_invariants.md` §1).

## What would falsify whichever is chosen

- **If B1:** discovering that hosted deployment is required sooner than expected, and that SQLite-isms
  (dynamic typing, loose constraints) have masked data-quality bugs that Postgres would have caught.
- **If B2:** the product staying genuinely single-family local, making the server dependency pure
  overhead carried through every slice for a benefit never realized.
- **If A2:** any move toward Postgres, which discards it entirely.
- **If C1:** query-cost problems from ORM indirection in the body-map or analytics read paths, which are
  the most query-heavy parts of the system.
