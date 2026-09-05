# logs/feature-backend-bootstrap.md

> Feature / workstream: `backend-bootstrap`  (branches: `feature/backend-bootstrap`)
> Started: 2026-09-04 by Claude Sonnet 5 (Claude Code)
> Status: in-progress

## Goal

Stand up the runnable FastAPI backend skeleton per `tasks/1a-backend-bootstrap.md` (implementation-plan.md Stage 1): `uvicorn main:app` boots on loopback, `GET /api/v1/health` returns the documented shape, seven `data/` subdirectories are created idempotently on startup, and `sandbox/Dockerfile` builds. No functional features — this is Aditya's ownership chain (`members/aditya.md`) step 1 of 8, and the base everything else (config, DB, orchestrator, policy) mounts onto.

## Plan

Implement exactly the files listed in `tasks/1a-backend-bootstrap.md` §4 (Allowed Files): `backend/main.py`, `backend/config.py` (minimal stub), `backend/requirements.txt`, `backend/api/health.py`, `backend/utils/ids.py`, `sandbox/Dockerfile` (skeleton), `backend/tests/test_health.py`. Verify via pytest + manual curl/docker-build per §8. Do not touch anything outside scope (no config YAML parsing, no DB, no orchestrator/policy/capability logic, no auth).

## Entries

### Entry 1 — 2026-09-04 14:00 — Backend bootstrap implemented and verified

**What changed:**
- `backend/utils/ids.py` — `new_id()` returns `str(uuid.uuid4())`.
- `backend/config.py` — minimal stub: `HOST`, `PORT`, `REPO_ROOT`/`DATA_ROOT` path constants, `DATA_SUBDIRS` list (7 dirs), `CORS_ALLOW_ORIGINS = ["http://localhost:5173"]`. Docstring + `# TODO(Task 2)` marker per task file §12 handoff note.
- `backend/api/health.py` — `APIRouter`, `GET /health`, returns exactly `{status, backend, database, model_runtime, docker}` with `status`/`backend` = `"ok"` and the other three as static placeholders (`"ok"`/`"unavailable"`) per `docs/api.md`.
- `backend/main.py` — `FastAPI` app with `lifespan` context manager (not the deprecated `@app.on_event("startup")` — FastAPI in this env warns it's deprecated; switched to `contextlib.asynccontextmanager` lifespan, same idempotent `mkdir(parents=True, exist_ok=True)` behavior, fails fast with `SystemExit(1)` + stderr message on `OSError`). CORS restricted to `http://localhost:5173`. Health router mounted at `/api/v1`.
- `backend/requirements.txt` — `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `pyyaml`, `httpx`, `python-multipart`, dev `pytest`/`pytest-asyncio`. No capability-specific libs.
- `sandbox/Dockerfile` — `python:3.11-slim` base, `WORKDIR /workspace`, no package installs, no network tools.
- `backend/tests/test_health.py` — asserts 200, exact 5-key set, `status`/`backend` == `"ok"`, other three values within documented allowed sets.
- `backend/pytest.ini` — **new file, not in the task's Allowed Files list.** Added `[pytest]\npythonpath = .` because `tests/test_health.py` does `from main import app`, and `main.py` does `from api.health import router` / `from config import ...` — both require `backend/` itself on `sys.path`. Without this, `cd backend && pytest tests/test_health.py` (the exact command documented in the task file §8) fails with `ModuleNotFoundError: No module named 'main'` under pytest's default rootless import mode. This is a minimal, standard pytest config addition, not application logic — flagging per AGENTS.md §3/§10 rather than silently expanding scope.

**Why:** Implements `tasks/1a-backend-bootstrap.md` exactly; this is Task 1.a of Aditya's owned chain (1.a → 2 → 10 → 15 → 17 → 18 → 19 → 20) per `members/aditya.md`, and has no task dependencies, so it's the correct starting point given no prior implementation existed (backend/, config/, sandbox/Dockerfile were all 0-byte placeholders, logs/ was empty, no relevant branch existed).

**How to verify:**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/test_health.py -v            # 2 passed
uvicorn main:app --host 127.0.0.1 --port 8000 &
curl http://127.0.0.1:8000/api/v1/health  # {"status":"ok","backend":"ok","database":"ok","model_runtime":"unavailable","docker":"unavailable"}
ls ../data                                 # artifacts chroma db extraction sandbox tmp uploads
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/v1/nope  # 404
docker build -t bulwark-sandbox:latest ./../sandbox   # succeeds (from repo root: ./sandbox)
```
All of the above were run and passed during this session. Restart was also verified idempotent (second `uvicorn` run with dirs already present did not error).

**Open issues / known gaps:**
- `backend/.venv/` was created locally for verification — **not committed** (should be gitignored; confirm `backend/.venv` or `.venv` is in `.gitignore` before pushing, add if missing).
- Per task scope, `database`/`model_runtime`/`docker` health fields are static placeholders — Task 15 wires real probes.
- `backend/config.py` is intentionally a stub; Task 2 owns replacing it with a validated YAML-backed `settings` object.
- This session did not commit, push, or open a PR per explicit user instruction — working tree on `feature/backend-bootstrap` has the implementation but is not yet in git history beyond the branch checkout. Next step for whoever picks this up: review `git diff`, commit, push, open PR per `docs/git-workflow.md`.

**Decisions made:**
- Used FastAPI's `lifespan` context-manager pattern instead of `@app.on_event("startup")` (deprecated in the installed FastAPI version) for directory creation — functionally identical, avoids a deprecation warning in test output. Not a scope deviation, same file (`main.py`), same behavior.
- Added `backend/pytest.ini` (see "What changed" above) — flagged as an out-of-list-but-necessary file rather than silently working around it (e.g. via `sys.path` hacks inside the test file, which would be worse).

**Supersedes / references:** None — first entry for this workstream.

---

## Open questions for the user

- Confirm `backend/pytest.ini` addition (see Entry 1) is acceptable, or specify a preferred alternative (e.g. a `conftest.py` `sys.path` insert, or an installable package layout) if the project lead wants strict adherence to the task file's Allowed Files list.
- Confirm `.venv`/`backend/.venv` is excluded via `.gitignore` before this branch is committed (not verified in this session since no commit was made).

## Links

- PR: not yet opened (commit/push explicitly deferred to the user this session)
- Related branches / logs: `feature/backend-bootstrap`
- Doc references: `tasks/1a-backend-bootstrap.md`, `docs/api.md`, `docs/deployment.md`, `docs/sandbox.md`, `docs/backend.md`, `AGENTS.md`, `members/aditya.md`
