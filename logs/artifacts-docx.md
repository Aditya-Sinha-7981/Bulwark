---
feature: artifacts-docx
branch: feature/artifacts-docx
started: 2026-09-06
status: completed
---

## Goal

Implement Task 14.a: deterministically render a Word document (.docx) from
structured findings data, per `docs/artifacts.md` "Templates" (DOCX) and
`docs/capabilities.md#create_docx`. This is the first artifact-producing
capability in the system and the first consumer of `backend/api/artifacts.py`
— Task 14.b (xlsx) is expected to reuse the routes and atomic-write pattern
established here rather than duplicating them.

## Plan

1. Confirm the `create_docx` input/output schema against `docs/capabilities.md`
   and the `Artifact` row shape against `docs/data-model.md` (both are
   authoritative — do not invent fields, per `AGENTS.md` §6 rules 11/13).
2. Implement `backend/domain/artifacts/docx_renderer.py` — the fixed
   template, atomic write to `data/artifacts/`, Artifact-row persistence.
3. Implement `backend/domain/capabilities/create_docx.py` — input/output
   validation matching the schema exactly, calling the renderer, emitting
   `artifact_created`.
4. Implement `backend/api/artifacts.py` — `GET /api/v1/artifacts/{id}` and
   `.../download`.
5. Register the router in `backend/main.py`.
6. Write `backend/tests/test_artifacts_docx.py` covering schema validation,
   atomic-write behavior, and Artifact-row persistence per `docs/testing.md`
   "Artifact tests" / "Failure injection".
7. Run tests, review diff, propose commit message. Hand off for human
   commit/push/PR per `AGENTS.md` §7 — this session does not run `git add`,
   `git commit`, `git push`, or any PR operation.

## Entries

### 2026-09-06 — Initial implementation (renderer, capability, API routes, tests)

Implemented against the real, confirmed contracts:
- `docs/capabilities.md#create_docx`: input
  `{title, sections: [{heading, body}], metadata: {prepared_by, date}}`,
  output `{artifact_id, filename}`.
- `docs/data-model.md#Artifact`: `artifact_id, job_id, type, filename,
  storage_path, size_bytes, created_at`.
- Real repository/audit signatures confirmed by reading the actual source
  (not assumed from docs alone): `repositories/artifacts.py`'s
  `create_artifact(job_id, type, filename, storage_path, size_bytes) ->
  artifact_id`, and `domain/audit/events.py`'s `async def emit(event_type,
  component, payload, job_id=None)`.

**Design decisions:**
- Atomic write: render to a temp file inside `ARTIFACTS_ROOT` via
  `tempfile.mkstemp`, then `os.replace()` into the final `{artifact_id}.docx`
  path only on full success. On any failure, the temp file is removed and no
  Artifact row is created. If the Artifact-row insert itself fails *after*
  the file is already in place, the orphaned file is deleted so a file
  never exists on disk without a corresponding row — matches
  `docs/artifacts.md` "Failure handling" exactly.
- `storage_path` is stored as just `{artifact_id}.docx` (relative to
  `ARTIFACTS_ROOT`). `docs/data-model.md` says "relative path under
  `data/artifacts/`" without specifying the exact relative root — this is
  my reading of it. **Needs confirmation from whoever reviews this PR**,
  since Task 14.b should follow the same convention for consistency.
- `create_docx.py`'s `validate_input`/`validate_output` reject any field not
  explicitly in the schema (rather than silently ignoring extras), per
  `AGENTS.md` §6 rule 11 ("don't invent fields") — read as "don't silently
  accept them either."

**Known gaps / explicitly flagged for follow-up before merge:**
- `backend/api/artifacts.py`'s 404 error envelope shape
  (`{"error": {"message": ...}}`) is a placeholder — `docs/api.md` was not
  available when this was written. Must be confirmed/corrected against the
  real `docs/api.md` before merge.
- Router registration in `backend/main.py` has not been done — `main.py`'s
  content was not available when this was written. A follow-up entry will
  cover this once it's wired in.
- `backend/tests/test_artifacts_docx.py` was written without a reference
  test file from this repo to confirm house fixture/mocking conventions.
  The fixture style (`isolated_artifacts_root` via `monkeypatch`) is a
  reasonable default, not a confirmed match to team convention — check
  against an existing test file (e.g. `test_documents.py`) and adjust if
  needed.
- Noted but not fixed (out of scope for this task's allowed files):
  `backend/repositories/artifacts.py` has `import sqlite3` at the bottom of
  the file, after it's already referenced in an `except sqlite3.IntegrityError`
  clause above. Works today because Python resolves names at call time, but
  worth moving to the top of the file in a future pass.
- This entire implementation was built and reviewed outside the team's
  actual repository (in an isolated sandbox), per explicit instruction, to
  avoid any collision with concurrent work happening in the real repo via a
  separate agent session. **Nothing here has been committed, pushed, or
  merged.** A human must copy these files into the real repo, resolve the
  gaps above, run the real test suite, and perform the actual
  `git add`/`commit`/`push`/PR sequence.

### 2026-09-06 — Integration & verification (opencode session)

**What changed:**
1. **`backend/api/artifacts.py`** — Fixed 404 error envelope to match `docs/api.md` exactly:
   - Changed from `{"error": {"message": ...}}` to `{"error": {"code": "not_found", "message": ..., "details": {}}}` per `docs/api.md` "Error format" section.

2. **`backend/main.py`** — Registered the artifacts router:
   - Added `from api.artifacts import router as artifacts_router`
   - Added `app.include_router(artifacts_router, prefix="/api/v1")`

3. **`backend/tests/test_artifacts_docx.py`** — Adjusted test fixtures to match repo conventions:
   - Added `create_temp_db()` helper and `temp_db` fixture matching `test_repositories_documents.py` pattern
   - Added `patched_repos` fixture that patches repository `get_connection` to use temp DB (matching `test_job_lifecycle.py` pattern)
   - `isolated_artifacts_root` fixture now patches `backend.utils.paths.ARTIFACTS_ROOT` and `artifacts_path` via `monkeypatch` (matching how `test_job_lifecycle.py` patches DB connections)
   - Added `patched_repos` fixture that patches `artifacts_repo.get_connection` and `db_module.get_connection` to use temp DB
   - Added API endpoint test for 404 error envelope verification
   - Added missing imports (`patch`, `AsyncMock`)

4. **Verification** — Ran full test suite:
   - All new artifact tests pass (18 tests in `test_artifacts_docx.py`)
   - All existing backend tests still pass (no regressions)
   - Error envelope matches `docs/api.md` spec exactly

**Decisions made:**
- Confirmed `storage_path` convention: stored as just `{artifact_id}.docx` (filename only) — this is what `artifacts_path()` returns and what `create_artifact` expects per `repositories/artifacts.py` docstring "Relative path under data/artifacts/". This is the simplest consistent convention.
- Error envelope now matches `docs/api.md` exactly: `{"error": {"code": "not_found", "message": "...", "details": {}}}` for 404s.
- Test fixtures follow the repo's established pattern of patching `get_connection` on repository modules and `backend.repositories.db` module.

**Remaining known gaps (from original log, carried forward):**
- `backend/repositories/artifacts.py` has `import sqlite3` at the bottom of the file (after use in `except sqlite3.IntegrityError`). Works but should be moved to top in a future cleanup pass.
- This implementation was integrated into the real repo from an isolated sandbox. Human must run `git add`/`commit`/`push`/PR.

## Open questions

- Confirm `storage_path`'s exact relative-root convention against team practice or `docs/data-model.md` clarification.
- Confirm `docs/api.md`'s real error envelope shape. (Now resolved — matches exactly)
- Confirm `backend/main.py`'s router-registration pattern before wiring in `api/artifacts.py`. (Now resolved — registered)

## Links

- Task spec: `tasks/14a-docx-renderer.md`
- Schema: `docs/capabilities.md#create_docx`, `docs/data-model.md#Artifact`
- Rendering contract: `docs/artifacts.md`
- Related, expected to follow this work: Task 14.b (`tasks/14b-xlsx-renderer.md`)