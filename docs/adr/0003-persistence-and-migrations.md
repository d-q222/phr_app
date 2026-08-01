# ADR-0003 — Persistence layer and schema migrations

- **Status:** **PROPOSED — awaiting Daniel's ruling.** Do not treat as decided.
- **Date raised:** 2026-08-01
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

## Decision

**Not yet made.** This ADR is written to be ruled on, not to record a conclusion.

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
