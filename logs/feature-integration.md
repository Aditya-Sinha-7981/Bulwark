# logs/feature-integration.md

> Feature / workstream: `integration` (Task 17 — full frontend/backend integration)  (branches: `feature/integration` suggested by the task file; baseline work currently riding on `fix/useapi-request-flood`)
> Started: 2026-09-12 by Claude (GLM) under Aditya's direction
> Status: in-progress (baseline recorded; Task 17 formal work not yet started)

## Goal

Per `tasks/17-frontend-backend-integration.md`: run the frontend and backend together and make all four `docs/demo.md` workflows work end-to-end **through the real browser UI** — Workflow C (grounded RAG), then A (scan → DOCX), then B (generate/execute code), with Workflow D's sovereignty panel visibly live throughout. Fix integration defects as **glue only** in `backend/api/*` and `frontend/src/*` (plus `config/app.yaml` `cors_origins` if wrong); deeper defects route to their owning tasks. Log every defect, fix, routed issue, and residual item here.

## Plan

The formal task had not been started when much of its glue scope was already fixed *en passant* during the 2026-09-12 manual API test session (the fixes are scattered across the owning features' logs). This log records that baseline (Entry 1), then tracks the remaining Task 17 work:

1. Surface the job's final answer in the UI (`final_message` currently rendered nowhere).
2. Documents listing: no list endpoint exists in the `docs/api.md` contract (`GET /documents/{id}` only) and no UI surface — needs a contract decision (route to project lead per the task's API-stability rule), then backend list endpoint + Documents panel.
3. Verify artifact download `Content-Disposition` headers.
4. Verify model-swap (`resource_loaded`/`resource_unloaded`) events render legibly in the trace UI.
5. Manual browser pass C → A → B with D live throughout, per `docs/demo.md` success criteria; record results here.
6. Acceptance checklist of the task file; targeted regression tests only where a fix warrants one.

## Entries

### Entry 1 — 2026-09-12 22:30 — Baseline: integration-scope work already completed (partly accidentally) during the 2026-09-12 test session

**What changed (with the owning feature log for each — full detail lives there):**

*Integration glue inside Task 17's allowed files, discovered and fixed while manually testing the four workflows via Postman and the browser:*

- **CORS origin gap** — `config/app.yaml` `cors_origins` allowed only `http://localhost:5173`; opening the UI via `http://127.0.0.1:5173` (a distinct browser origin, or any vite port shift) got every request silently browser-blocked. Fixed: both loopback dev origins allow-listed (`fix/cors-loopback-origins`, `d42f23b`). Detail: `logs/feature-configuration.md` Entry 2.
- **SSE terminal semantics** — both the backend stream (`backend/api/jobs.py`) and the frontend `useJobEvents` treated mid-job `error` events as terminal; only `job_completed` is terminal per `docs/audit.md`. Late joiners on jobs with recoverable tool failures got frozen traces. Fixed both sides (`dc6c86d` backend; `39a57dc` frontend). Detail: `logs/feature-job-system.md` Entry 5 + `logs/feature-frontend-scaffold.md` Entry 5.
- **Trace double-render** — `/trace` fetch + default SSE replay rendered every historical event twice; dedupe by `event_id` added, and (same day, after live confirmation in the browser) the initial trace fetch was routed through the same dedupe path. Fixed (`39a57dc` + `84b60fe`). Detail: `logs/feature-frontend-scaffold.md` Entries 5 + 6.
- **Chat message timestamps** — UI rendered `msg.timestamp`; the backend sends `created_at` → "Invalid Date" on every bubble. Fixed (`39a57dc`). Detail: `logs/feature-frontend-scaffold.md` Entry 5.
- **useApi request flood** — `useApi`'s effect re-ran on every render (rest-array identity), hammering endpoints in an unbounded loop (observed: 328 × `/health` in one backend window). Fixed with value-serialized args (`6f79ccc`). Detail: `logs/feature-frontend-scaffold.md` Entry 6.
- **Upload-boundary error surfacing** — verified through the browser/API: `.docx` → `400 INVALID_MIME_TYPE` at both boundaries; oversized → `400 FILE_TOO_LARGE`; corrupt image uploads OK then fails extraction honestly. No code change needed — behavior verified correct. Detail: `test-assets/full-stack-test-plan.md` Phase 6.

*Deeper (subsystem) fixes that were prerequisites for the workflows to run at all — routed to and fixed in their owning tasks, listed here because Task 17's browser pass depends on them:*

- KB ingestion audit crash (`model_invoked` required `job_id`) — `logs/feature-rag.md` Entry 8.
- `context_window` never enforced at Ollama + 120s read timeout — `logs/feature-model-runtime.md` Entry 7.
- Identical-proposal Orchestrator loop guard + Document Deliverables Rule — `logs/feature-orchestrator.md` Entries 4–5.
- `document_ids` dropped before reaching the Orchestrator — `logs/feature-job-system.md` Entry 4.
- PaddleOCR stack absent/mis-pinned + numpy polys crash + cold-start race — `logs/feature-ocr.md` Entries 6–8.
- `generate_code` still a canned stub; `execute_code` stale import (never loaded) — `logs/feature-sandbox.md` Entries 6–7.
- Backend resurrected mid-session: the only live uvicorn was a stale pre-fix process not listening on :8000; killed and restarted from current main.

**Also produced (test infrastructure for this task):** `test-assets/full-stack-test-plan.md` — the consolidated 10-phase API+UI test pass this workstream will execute (`logs/test-assets.md` Entry 7).

**How to verify (baseline):** backend suite 509 passed (1 known environmental flake in `test_executor_error_is_failed_tool_result_not_crash` — verified failing on a clean tree); frontend 14/14 + build green on the stacked branch `fix/useapi-request-flood` (contains CORS + flood + dedupe fixes and the test plan).

**Open issues / known gaps (the actual remaining Task 17 work):**
- **Answer not surfaced:** a completed Job's `final_message` is rendered nowhere — Workbench polls `getJob` for status only; ChatPanel loads history on mount only. The browser shows "Orchestrator: respond" in the trace but the answer text never appears (observed live in the browser, 2026-09-12, "Can you tell me pump specifications" / "Hi").
- **Documents listing:** no `GET /api/v1/documents` list endpoint in the contract; no UI surface. Needs a `docs/api.md` change decision (route to project lead) before backend/UI work.
- **Artifact `Content-Disposition`:** download works (binary .docx), header correctness not yet verified.
- **Model-swap rendering:** `resource_loaded`/`resource_unloaded` render in the capability-activity feed (`CapabilityActivity.jsx:122+`) — legibility during a live Workflow B run not yet verified.
- **No live loaded-models indicator** (flagged enhancement, needs `docs/api.md` decision — `test-assets/full-stack-test-plan.md` §Phase 10).
- Known frontend cosmetic gaps handed to the frontend owner: `ApiError.code`, attachment-note pretty-printing, dead page-level `handleError`, hardcoded `BASE_URL` (`logs/feature-frontend-scaffold.md` Entry 5).
- The browser-based C → A → B → D pass itself (the core acceptance criterion) — not yet done as a formal recorded run.

**Decisions made:**
- Baseline recorded here rather than duplicating each fix's detail — the owning feature logs are the source of truth; this log indexes them and tracks what *remains*.
- The informal fixes stay where they landed (owning features' branches/logs); Task 17's formal branch will build on main once they're merged.

**Supersedes / references:** Indexes `feature-rag.md` E8, `feature-model-runtime.md` E7, `feature-orchestrator.md` E4–5, `feature-job-system.md` E4–5, `feature-ocr.md` E6–8, `feature-sandbox.md` E6–7, `feature-frontend-scaffold.md` E5–6, `feature-configuration.md` E2, `test-assets.md` E7.

---

## Open questions for the user

- **Documents listing (blocks "see uploaded documents"):** add `GET /api/v1/documents` (list) to `docs/api.md` (contract change → your approval + Task 15 lead sign-off per the task's stability rule), then backend endpoint + a Documents panel? Or defer past Task 17?
- **Answer surfacing shape:** render `final_message` as an assistant chat bubble, a dedicated result panel, or both? (`docs/frontend.md` is the reference — needs the intended behavior confirmed.)
- The task file's Open Questions (headless e2e harness vs manual) — proposed: manual + targeted regression tests only; confirm.

## Links

- PR: (pending — baseline currently riding on stacked branch `fix/useapi-request-flood`)
- Related branches / logs: `fix/useapi-request-flood` (stacked: CORS + useApi flood + trace dedupe + test plan), all owning-feature logs referenced in Entry 1
- Doc references: `tasks/17-frontend-backend-integration.md`, `docs/demo.md`, `docs/deployment.md`, `docs/api.md`, `docs/frontend.md`, `docs/audit.md`, `docs/configuration.md`, `test-assets/full-stack-test-plan.md`
