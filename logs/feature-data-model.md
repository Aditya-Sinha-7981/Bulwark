# logs/feature-data-model.md

> Feature / workstream: `data-model`  (branches: `feature/data-model`, …)
> Started: 2026-09-05 by opencode
> Status: completed

## Goal

Implement the SQLite database schema and repository layer for all entities defined in `docs/data-model.md`. This is Task 3 (Stage 3 of implementation-plan.md) — the persistence spine for jobs, audit, artifacts, knowledge base, and resource state.

## Plan

1. **Schema migration script** (`scripts/init_db.py`) — create all 11 tables + 7 indexes idempotently with `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`.
2. **Connection helper** (`backend/repositories/db.py`) — shared SQLite connection factory with `PRAGMA foreign_keys = ON`, mapping row factory, and context-managed transaction helper.
3. **Repository modules** (aggregate-oriented, 7 modules) — CRUD for every entity:
   - `conversations.py` — Conversation + Message
   - `jobs.py` — Job + JobStep + CapabilityExecution + ModelExecution
   - `documents.py` — Document
   - `artifacts.py` — Artifact
   - `audit_events.py` — AuditEvent
   - `knowledge_base.py` — KnowledgeBaseDocument
   - `resource_state.py` — ResourceState
4. **Row dataclasses** (`backend/models/schemas.py`) — typed row definitions matching `data-model.md` exactly.
5. **Unit tests** (7 test files) — CRUD round-trips, enum validation, FK integrity, ordering, pagination against real temp databases.
6. **Manual verification** — `.schema` comparison with `docs/data-model.md`.

## Entries

### Entry 1 — 2026-09-05 10:30 — Schema migration script created
**What changed:** Created `scripts/init_db.py` with idempotent `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` for all 11 tables and 7 indexes per `docs/data-model.md`.
**Why:** Task requires a runnable migration script that is safe to re-run without data loss (no migration framework for SIH scope).
**How to verify:** `python scripts/init_db.py` → inspect `data/db/app.db` with `.schema`.
**Decisions made:** Used raw `sqlite3` (no ORM), explicit CHECK constraints for all enum columns, foreign keys with `ON DELETE CASCADE/SET NULL` matching aggregate ownership.
**Supersedes / references:** None (first entry).

### Entry 2 — 2026-09-05 11:00 — Connection helper created
**What changed:** Created `backend/repositories/db.py` with `get_connection()`, `transaction()` context manager, `row_to_dict()`, and typed exceptions (`DatabaseError`, `NotFoundError`, `ConstraintError`).
**Why:** All repositories need a consistent connection with foreign keys enabled and mapping rows.
**How to verify:** Import and call `get_connection()` — returns `sqlite3.Connection` with `row_factory=sqlite3.Row` and `PRAGMA foreign_keys=ON`.
**Decisions made:** Fallback DB path `./data/db/app.db` via `backend.config.DATA_ROOT`; will switch to `settings.app.paths.db` when Task 2 merges.
**Supersedes / references:** Entry 1.

### Entry 3 — 2026-09-05 11:30 — Repository modules implemented (7 modules)
**What changed:** Fleshed out all 7 repository modules in `backend/repositories/`:
- `conversations.py`: create/get conversation, append/get/list/count messages, update timestamp
- `jobs.py`: full CRUD for Job, JobStep, CapabilityExecution, ModelExecution with status transitions
- `documents.py`: create/get/list documents
- `artifacts.py`: create/get/list-by-job artifacts
- `audit_events.py`: insert, get, query by job_id/event_type (timestamp-ordered), count
- `knowledge_base.py`: create/get/update/list/delete KB documents
- `resource_state.py`: upsert, get, list, set status/timestamps
**Why:** Aggregate-oriented structure locked in task spec — sub-entities fold into parent aggregate module.
**How to verify:** Each module's functions work against a real temp DB (tested in Entry 5).
**Decisions made:** 
- All PKs generated via `backend.utils.ids.new_id()` (UUIDv4 strings)
- All timestamps ISO-8601 UTC via `_now_iso()` helper
- Enum validation in CHECK constraints AND Python-side validation
- Constraint violations raise `ConstraintError`; not-found returns `None` consistently
- Multi-row operations wrapped in transactions (via `db.transaction()`)
**Supersedes / references:** Entries 1–2.

### Entry 4 — 2026-09-05 12:00 — Row dataclasses added
**What changed:** Created `backend/models/schemas.py` with `@dataclass` definitions for all 11 tables + enum value constants (`VALID_JOB_STATUSES`, etc.).
**Why:** Optional typed layer for consumers wanting type safety; matches `data-model.md` exactly.
**How to verify:** Import `ConversationRow`, `MessageRow`, etc. — fields match table columns 1:1.
**Decisions made:** Use plain dataclasses (not Pydantic) for zero-dependency row types; validation happens at DB level via CHECK constraints.
**Supersedes / references:** Entry 3.

### Entry 5 — 2026-09-05 12:30 — Unit tests written and passing (68 tests)
**What changed:** Created 7 test files in `backend/tests/`:
- `test_repositories_conversations.py` (11 tests)
- `test_repositories_jobs.py` (17 tests)
- `test_repositories_documents.py` (5 tests)
- `test_repositories_artifacts.py` (6 tests)
- `test_repositories_audit_events.py` (9 tests)
- `test_repositories_knowledge_base.py` (10 tests)
- `test_repositories_resource_state.py` (10 tests)
**Why:** Task requires repository CRUD tested against real temp databases per entity.
**How to verify:** `python -m pytest backend/tests/test_repositories_*.py -v` → 68 passed.
**Open issues / known gaps:** Tests use monkey-patching pattern for DB connection; could be refactored to a shared test fixture later.
**Decisions made:** Each test creates its own temp DB via `scripts.init_db.main()` with patched path; patches `get_connection` on relevant modules. Ensures complete isolation.
**Supersedes / references:** Entries 1–4.

### Entry 6 — 2026-09-05 13:00 — Manual schema verification complete
**What changed:** Ran `python scripts/init_db.py` → `sqlite3 data/db/app.db ".schema"` — confirmed all 11 tables, all columns, types, nullability, PKs, FKs, CHECK constraints, and 7 indexes match `docs/data-model.md` exactly. No extra tables/fields.
**Why:** Acceptance criteria require manual verification.
**How to verify:** Compare output above with `docs/data-model.md` tables.
**Decisions made:** Schema is frozen — any future change requires updating `docs/data-model.md` first (AGENTS.md §6 rule 13).
**Supersedes / references:** Entry 1.

## Open questions for the user

1. **Row dataclasses**: Should repositories return typed dataclass instances instead of dicts? Current implementation returns dicts; `schemas.py` is available for consumers to cast.
2. **Settings integration**: Currently uses fallback `./data/db/app.db` via `backend.config.DATA_ROOT`. Should wait for Task 2's `settings.app.paths.db` to be ready, then switch.
3. **Test fixture pattern**: Current monkey-patching works but is verbose. A shared `conftest.py` fixture could simplify future tests.

## Links

- PR: <to be created>
- Related branches / logs: `feature/data-model`
- Doc references: `docs/data-model.md`, `docs/backend.md`, `docs/audit.md`, `docs/implementation-plan.md` (Stage 3), `AGENTS.md` §6 rule 13