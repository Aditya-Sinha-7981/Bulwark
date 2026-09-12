# logs/feature-job-system.md

> Feature / workstream: `job-system`  (branches: `feature/job-system`, `fix/job-attachment-message-enrichment`, …)
> Started: 2026-09-05 by nemotron-3-ultra-free
> Status: in-progress (Task 5 complete; attachment-note fix on `fix/job-attachment-message-enrichment` pending commit)

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

---

### Entry 4 — 2026-09-12 11:09 — document_ids now reach the Orchestrator via an attachment note on the user message (branch `fix/job-attachment-message-enrichment`)

**What changed:**
- `backend/domain/job_manager/manager.py` — `create_job()` (`manager.py:~200-243`): when `document_ids` is non-empty, the stored user message content becomes `"{input_message}\n\n[Attached document(s): document_id=<uuid>, ...]"`; with no ids, the message is stored exactly as before. Docstring rewritten — the old one claimed the Orchestrator "asks for their contents via extract_document", which was impossible because the ids were silently dropped (the parameter was accepted and never used). Job row and `job_created` audit payload keep the raw `input_message` (no `docs/audit.md`/`docs/data-model.md` changes — Option A, user-approved over a Job-table column).
- `backend/tests/test_job_lifecycle.py` — added `test_create_job_with_document_ids_enriches_user_message` (ids present in conversation history, raw message in Job row and event) and `test_create_job_without_document_ids_keeps_message_unmodified` (no note when empty).

**Why:** Found live during the manual test pass (Phase 4, job `85e5b5c4`, 2026-09-12): Workflow A's `POST /jobs` carried the correct `document_ids`, but the Orchestrator responded "I require the specific document_id… Please provide the document_id" and terminated without invoking anything. Root cause: `manager.create_job(conversation_id, input_message, document_ids)` accepted `document_ids` and never persisted or forwarded them — `jobs_repo.create_job()` is called without them, the Job table has no `document_ids` column (`docs/data-model.md:30-40`), `OrchestratorContext` has no attachment field, and the only channel into the Orchestrator's prompt is conversation history. Meanwhile `docs/demo.md:14` requires the Orchestrator to propose `extract_document` *with* the uploaded `document_id`, and `execute_code` resolves `input_files` from proposal arguments — so capabilities were designed to receive ids from the Orchestrator, but nothing ever delivered them. User approved Option A (enrich the stored user message) over Option B (Job column + `OrchestratorContext` field + prompt-builder block, which would require updating `docs/data-model.md` first per AGENTS.md §6.13); Option A can be upgraded to B later without behavioral change.

**How to verify:**
- `backend/.venv/bin/python -m pytest backend/tests/test_job_lifecycle.py -q` → 10 passed.
- Full non-integration suite → 495 passed; only failure is the pre-existing environmental `test_job_manager_dispatch.py::test_executor_error_is_failed_tool_result_not_crash` (documented in `logs/feature-orchestrator.md` Entry 4 / `logs/feature-model-runtime.md` Entry 7).
- Live: upload a document, `POST /jobs` with `document_ids: ["<id>"]`, check Get Job Trace — the Orchestrator should now propose `extract_document` with that id instead of asking for it.

**Open issues / known gaps:**
- The attachment note is visible in conversation history (Get Conversation shows it) — accepted trade-off of Option A.
- Option B (Job column + context field) remains the structural cleanup candidate post-SIH; if done, `docs/data-model.md` must be updated first.

**Decisions made:**
- Enrich the message row, not the Job row / `job_created` payload — audit event contract (`docs/audit.md` `job_created` payload keys) and Job schema stay untouched.
- Note format is deterministic: `[Attached document(s): document_id=<id>, ...]` on its own line after a blank line — the Orchestrator can copy ids into `extract_document`/`execute_code` arguments verbatim.

**Supersedes / references:** Corrects the misleading docstring introduced with Task 5's `create_job` (Entry 2); no behavioral entry contradicted.

---

## Links

- Related branches / logs: `fix/model-runtime-num-ctx-and-timeout` (prior three fixes, committed), `logs/feature-orchestrator.md` (identical-proposal guard), `logs/feature-rag.md`, `logs/feature-model-runtime.md`
- Doc references: `docs/demo.md`, `docs/agent.md`, `docs/api.md`, `docs/data-model.md`, `docs/capabilities.md`