# logs/feature-job-system.md

> Feature / workstream: `job-system`  (branches: `feature/job-system`, …)
> Started: 2026-09-05 by nemotron-3-ultra-free
> Status: completed

## Goal
Implement the Job/JobStep lifecycle and the Job HTTP API: create a Job, transition it `created → running → (completed | failed)`, record steps, and expose `POST /api/v1/jobs`, `GET /api/v1/jobs/{id}`, `GET /api/v1/jobs/{id}/trace`, and complete the `GET /api/v1/jobs/{id}/events` SSE route. Drive the loop with a **stub Orchestrator that always responds directly** — no Policy, no capabilities, no real Orchestrator yet.

## Plan
1. Create `backend/domain/job_manager/manager.py` with `create_job()`, `stub_orchestrator()`, and `run_job()` driver loop
2. Implement the four job endpoints in `backend/api/jobs.py` (POST /jobs, GET /jobs/{id}, GET /jobs/{id}/trace, GET /jobs/{id}/events)
3. Add any missing repository helpers in `backend/repositories/jobs.py` and `backend/repositories/conversations.py`
4. Create integration tests in `backend/tests/test_job_lifecycle.py`
5. Run tests and verify manually

## Entries

### Entry 1 — 2026-09-05 10:00 — Starting Task 5 implementation
**What created:** Created this development log file
**Why:** Per AGENTS.md §4, every feature/workstream must have a persistent append-only log
**How to verify:** Log file exists at `logs/feature-job-system.md`
**Open issues / known gaps:** None yet
**Decisions made:** Following the plan as approved by user
**Supersedes / references:** Task spec at `tasks/5-job-system-lifecycle.md`

### Entry 2 — 2026-09-05 11:30 — Implemented Job Manager and API routes
**What changed:**
- Created `backend/domain/job_manager/manager.py` with:
  - `create_job(conversation_id, input_message, document_ids)` - creates job, emits job_created
  - `stub_orchestrator(context)` - returns direct answer `{"action": "respond", "content": "Echo: ..."}`
  - `run_job(job_id)` - driver loop: created→running→completed, records job_steps, emits job_completed
  - `ensure_conversation_exists()` - validation helper
- Updated `backend/api/jobs.py` with full implementations:
  - `POST /api/v1/jobs` - creates job, kicks off background task
  - `GET /api/v1/jobs/{job_id}` - returns job state with exact API shape
  - `GET /api/v1/jobs/{job_id}/trace` - filtered audit_events query
  - `GET /api/v1/jobs/{job_id}/events` - SSE with replay and proper terminal event handling
- Created `backend/tests/test_job_lifecycle.py` with 8 integration tests

**Why:** Implement Job lifecycle per Task 5 spec
**How to verify:** All 8 tests pass; 102/103 backend tests pass (1 pre-existing failure in test_config.py unrelated)
**Open issues / known gaps:** None
**Decisions made:**
- Job status transitions to "completed" immediately on successful respond (fixes test timing)
- SSE endpoint closes stream after job_completed/error even with replay=true
- Error responses use FastAPI's default envelope with `detail` wrapper
**Supersedes / references:** Entry 1

### Entry 3 — 2026-09-05 12:00 — Task 5 complete
**Status:** completed
**Summary:** All acceptance criteria met:
- Job creation via POST /api/v1/jobs returns 201 with correct shape
- Job lifecycle: created → running → completed (failed on error)
- Direct answer produces one orchestrator_reasoning JobStep, no CapabilityExecution, sets final_message + orchestrator Message row
- GET /jobs/{id} returns exact api.md shape with artifact_ids: [], error: null
- GET /jobs/{id}/trace is ordered audit_events query (no separate store)
- GET /jobs/{id}/events SSE streams and closes on job_completed
- job_created and job_completed emitted via single write path (emit)
- Unknown job_id returns 404 with error envelope
- Clean seam for Task 15: stub_orchestrator clearly marked, loop structure supports future Policy/dispatch
- All 8 integration tests pass

**Final test status:** 8/8 job_lifecycle tests passed; 102/103 backend tests passed (1 pre-existing failure in test_config.py::test_path_helpers_reject_absolute_input)

**Reviewer notes:** 
- The stub Orchestrator in manager.py is clearly commented for Task 10/15 replacement
- SSE endpoint handles replay=true with terminal events correctly
- Error format matches FastAPI's default (wrapped in `detail`)
- No locked contracts violated (AGENTS.md §6)