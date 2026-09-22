# logs/feature-integration.md

> Feature / workstream: `integration` (Task 17 — full frontend/backend integration, plus post-merge UI/fixes work)  (branches: `feature/integration` — squash-merged to `main` 2026-09-13, commit `8b3ee6a`, deleted; `fix/kb-upload-ui` — current, branched from `main` 2026-09-13)
> Started: 2026-09-12 by Claude (GLM) under Aditya's direction
> Status: in-progress

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

### Entry 2 — 2026-09-13 06:20 — Documents listing, answer surfacing, RAG evidence binding, layout fix; manual C→A→B→D pass

**What changed:**

*Documents listing (Open Question from Entry 1, resolved — user approved adding the contract endpoint, confirmed they own Task 15):*
- `backend/api/documents.py` — added `GET /api/v1/documents` (list, `limit`/`offset` query params, reuses the existing `list_documents()` repo function which was already implemented but never exposed). `docs/api.md` updated with the new endpoint contract.
- `backend/tests/test_document_processing.py` — 3 new tests (`test_list_documents_includes_uploaded`, `test_list_documents_respects_limit`, `test_list_documents_rejects_invalid_limit`). All pass.
- `frontend/src/services/api.js` — added `listDocuments()`.
- `frontend/src/components/DocumentPicker.jsx` (new) — a "Browse" button next to "Attach file" in `ChatPanel` that lists previously uploaded documents and lets the user re-attach one without re-uploading. Wired into `ChatPanel.jsx`.

*Answer surfacing (Open Question from Entry 1, resolved — user chose "assistant chat bubble"):*
- Root-caused via live browser testing, not guessed: `Workbench.jsx`'s own `conversationId` state was **never updated** when `ChatPanel` created a new conversation internally — `ChatPanel` had no callback to report it back up. So when `Workbench` switched from its empty-state layout to the active chat+trace layout (on job creation), the *new* `ChatPanel` instance mounted with `conversationId=null` and never fetched history at all. Fixed by adding `onConversationCreated` prop/callback (`ChatPanel.jsx:16,105`, `Workbench.jsx` `handleConversationCreated`).
- Second, independent bug found the same way: the `job={jobData}` prop needed for the completion-triggered refetch was added to the **empty-state** `<ChatPanel>` usage in `Workbench.jsx` but never to the **active-layout** one — the one actually rendered once a Job exists. Confirmed via a temporary `console.log` in the effect (`job` was `undefined` on every render). Fixed: `Workbench.jsx` line ~376 now passes `job={jobData}` on both usages.
- Third bug: even with both of the above fixed, a race exists — the backend flips the Job row to `status: "completed"` *before* appending the orchestrator's message to the conversation (`backend/domain/job_manager/manager.py`, two sequential DB calls, no transaction). A poll landing in that gap sees "completed" with the answer not yet persisted. Fixed defensively, frontend-only: `ChatPanel.jsx`'s completion effect now fires an immediate refetch *and* a second one 1.5s later (`setTimeout`), closing the window without depending on backend ordering.
- All three confirmed fixed live: ran two full conversational turns end-to-end through the browser; both the user's message and the orchestrator's final answer rendered correctly as chat bubbles both times.

*RAG evidence panel binding (was a known open item — turned out to be a missing audit event, not a wiring bug):*
- `RagEvidencePanel.jsx` was scanning `tool_invoked` events for `result.results[]`, but per `docs/audit.md`, `tool_invoked`'s payload is `{capability, arguments}` only — it never carries the result. Verified in code: `backend/domain/audit/events.py:42` and `backend/domain/job_manager/manager.py`'s actual emit call both confirm this; the real result is only ever written to `job_steps.output_payload`, never audited.
- **User approved (after being asked, since this needed a new event type — AGENTS.md §6 rule 12/13)** adding a new `tool_result` audit event, mirroring `tool_invoked`, fired right after a successful capability dispatch: `backend/domain/job_manager/manager.py` (after the existing `update_job_step` success block), payload `{capability, result}`. Registered in `backend/domain/audit/events.py` (`VALID_EVENT_TYPES`, `_REQUIRED_PAYLOAD_KEYS`). Documented in `docs/audit.md`, `docs/api.md`, `docs/AI-CONTEXT.md`, `docs/api-manual-testing-guide.md`, `docs/frontend.md`.
- `RagEvidencePanel.jsx` now scans `tool_result` instead; also fixed a field-name bug while there — it read `result.document_id` but `search_knowledge_base`'s actual output schema (`docs/capabilities.md`) uses `kb_document_id`.
- `CapabilityActivity.jsx` — added a dedicated `tool_result` render case (capability name, exit-code badge when present e.g. for `execute_code`, collapsible JSON output) rather than falling through to the generic/unknown-event renderer, for trace legibility.
- `JobTracePanel.jsx` — refactored to accept `events`/`status`/`error`/`reconnect` as props instead of calling `useJobEvents` itself, so `Workbench.jsx` can lift the one SSE subscription and hand the same event list to both `JobTracePanel` and `RagEvidencePanel` (previously `RagEvidencePanel` was hardcoded to `events={[]}` — see Entry 1's "Open issues").
- `backend/tests/test_audit_events.py` — updated `test_emit_all_valid_event_types` and `test_valid_event_types_matches_audit_md` (now expects 12 types) for the new event type.
- Verified live: Workflow C's RAG Evidence panel populated with 4 real SOP-001 chunks, correct scores, correct doc IDs, after asking a covered question.

*Content-Disposition (Open item — verified correct, not a bug):*
- `backend/api/artifacts.py`'s `FileResponse(..., filename=...)` already sets `Content-Disposition: attachment; filename="..."` correctly via Starlette. Added a regression assertion to `backend/tests/test_e2e_workflow.py` (`test_e2e_create_docx_over_http_no_stub`) locking this in, since Requirement 7 called it out as unverified.

*Layout bug found live in the browser (not previously known):*
- `Workbench.jsx`'s active layout (`flex flex-col gap-6 xl:flex-row`) had no bounded height — both columns stretch to match each other via flex default `align-items: stretch`, and the trace column grows unbounded with trace content. Once a job produced enough trace events (~15+, completely normal for Workflow A/B), the chat column stretched to match, pushing the composer input hundreds of pixels below the fold — reachable only by scrolling through a large empty gap. Fixed: the row is now `xl:h-[calc(100vh-220px)]`, both columns `xl:h-full`, right column additionally `xl:overflow-y-auto` — each panel now scrolls independently within a viewport-bounded row. Confirmed visually before/after.

**How to verify:** `cd backend && source .venv/bin/activate && python -m pytest backend/tests/ -q` (525 passed, 1 known environmental flake — see Entry 1); `cd frontend && npm test -- --run` (14/14) and `npm run build` (clean). Manual: reproduced all three ChatPanel bugs live, confirmed fixed live, in a real browser session (not curl).

**Manual browser pass — C → A → B, D observed throughout (`docs/demo.md` order):**

- **Workflow C — PASS.** Asked "What is the maximum allowable vibration velocity before a cooling water pump must be removed from service immediately?" — trace showed explicit `orchestrator_step: invoke_capability` → `policy_decision: allow` → `tool_invoked: search_knowledge_base` → `tool_result` with 4 real SOP-001 chunks, RAG Evidence panel populated correctly, final answer ("11.0 mm/s RMS... 24 hours...") correctly grounded and citing SOP-001. A same-conversation follow-up ("what about the seal leakage class...") correctly answered from a fresh, distinct retrieval (Class III, 30 days) without confusing it with the prior turn's Class II reference. Did not get to case C2 (uncovered question) this pass — recommend Task 19 include it.
- **Workflow A — PARTIAL, one blocking finding.** Uploaded `test-assets/documents/inspection-report-clean.png`, asked for an approval note. `extract_document` succeeded (OCR, confidence 0.997, no vision escalation needed for the clean asset — expected). But the Orchestrator then went **straight to `create_docx`, skipping `search_knowledge_base` entirely** — confirmed via the job's full trace (`tool_invoked` sequence was `extract_document` → `create_docx`, no `search_knowledge_base` in between). This fails `docs/demo.md` Workflow A's explicit success criterion: "Correct capability sequencing (extraction → retrieval → generation, **not skipped or reordered**)." The produced DOCX itself was schema-valid and downloadable (`Pump_Inspection_Approval_Note_CWP_204A.docx`, 36.4 KB, correct `Content-Disposition`) — this is an Orchestrator decision-making gap (it judged the extracted text sufficient on its own), not an integration/glue bug. **Routed as a blocking finding** to the Orchestrator owner (Task 9) — not fixed here (`backend/domain/orchestrator/*` is outside Task 17's allowed files, and the fix is prompt/behavior, not wiring). Did not get to the degraded-asset/vision-escalation case this pass — recommend Task 19 cover both the retrieval-skip regression and vision escalation.
- **Workflow B — PASS** (two runs: a plain case and `test-assets/prompts/coding-test-prompts.md` case B3, the "good correction-loop case"). Both times: `generate_code` and `execute_code` appeared as distinct, separately-audited trace steps; model swap `qwen3.5:9b` (reasoning) → `qwen2.5-coder:7b` (code_generation) → back to `qwen3.5:9b` clearly visible via `model_invoked` events; `execute_code`'s `tool_result` rendered with a legible exit-code badge; both runs succeeded on the first attempt (`.strip('C')` before `float()`, avoiding B3's anticipated bug) so **the correction-loop path itself was not naturally exercised** — the mechanism is architecturally present (tool_result carries `exit_code`/`stderr`, Orchestrator can act on it) but not observed live. Recommend Task 19 retry B3 across multiple runs, or use a prompt more reliably provoking a first-attempt bug.
- **Workflow D — PASS, throughout.** `SovereigntyIndicator` (in `StatusBar`, always rendered via `AppShell`) stayed visible and updating (`checked_at` advancing every ~2s) continuously through all of the above, including during Workflow B's sandbox execution — verified by checking its timestamp at multiple points during a live job run.

**Open issues / known gaps:**
- Workflow A's retrieval-skip (above) — blocking finding routed to Task 9 (Orchestrator).
- Workflow B's correction loop — not naturally observed this pass; not blocking (the plumbing is verified), but Task 19 should specifically capture it.
- Case C2 (honest "no grounding"), and Workflow A's degraded-asset/vision-escalation case — not run this pass; recommend Task 19.
- See Entry 3 for two more significant findings from this same session (Orchestrator `malformed`-output frequency, and a Resource Lifecycle Manager wiring gap) discovered while investigating a performance report from the user.

**Decisions made:**
- `tool_result` added as a new audit event type (user-approved contract change, since the user confirmed they also own Task 15) — this is the only event/contract change made in this task; every other fix is glue per Task 17's charter.
- Race-condition fix for the completion-message gap is intentionally frontend-only (retry timer) rather than reordering the two backend DB calls, to stay inside `backend/api/*`/`frontend/src/*` — flagged as an option for whoever next touches `job_manager.py` to do properly (emit `job_completed`/update status *after* the message append, or wrap both in one transaction).

**Supersedes / references:** Builds on Entry 1's "Open issues" (answer not surfaced, RAG panel not bound, Content-Disposition unverified) — all three closed here.

---

### Entry 3 — 2026-09-13 06:35 — Performance investigation (user-reported): memory pressure, `think` mode, and a Resource Lifecycle Manager wiring gap

**Context:** Mid-session the user reported extreme turn latency (single Orchestrator turns up to 276s / one full Workflow B job taking ~21 minutes) and asked for root-cause investigation before continuing — explicitly out of Task 17's normal scope (`docs/testing.md`/Task 20 owns performance benchmarking) but directed by the user, so investigated and (with explicit approval per finding) fixed where the fix was small, well-understood, and low-risk.

**What was found and changed:**

1. **Memory pressure (environmental, not fixed — flagged for Task 20/demo-day prep).** System has 24GB unified memory (M4 Pro). Mid-session, 3 Ollama models were resident simultaneously (`qwen3.5:9b` 9.1GB + `qwen2.5-coder:7b` 6.3GB + `qwen3-embedding:0.6b` 1.4GB ≈ 16.8GB), alongside a heavy browser session, VS Code, and this CLI. `memory_pressure` showed 733K swap-ins / 1.3M swap-outs and 97M pages decompressed — sustained thrashing, which directly degrades Metal/GPU inference on unified-memory Apple Silicon. Ollama's server process had actually died by the time this was checked (no process at all) — almost certainly resource-starved. No code fix (this is machine/environment, not app code); recommend for the actual demo machine: close unrelated heavy apps beforehand, and for Task 20 to consider tightening `config/resources.yaml`'s `keep_alive` so concurrent models don't stack up across a session that touches multiple resource types.

2. **`think` mode — root cause of most of the latency, fixed.** Benchmarked directly against Ollama: the identical prompt with Ollama's default (`qwen3.5:9b`'s hidden "thinking" pass) took 27.4s / 636 completion tokens; with `"think": false`, 3.6s / 10 tokens, **byte-identical final answer**. This single option explains the majority of the multi-minute turns observed all session (5414-completion-token reasoning turns, etc.). **Fixed:** `backend/domain/model_runtime/runtime.py`'s `generate()` now sends `"think": False` in every Ollama `/api/generate` payload (reasoning/code_generation/vision — one central change covers all three). User explicitly approved after being walked through what `think` mode is and why the Orchestrator's narrow per-turn decision doesn't need it. Verified live post-fix: a full job (cold model load included) completed end-to-end in 12.8s, vs multi-minute turns beforehand.
   - **Caveat for whoever revisits this:** only benchmarked on a trivial prompt; not A/B-tested against the harder multi-step orchestration decisions in this app specifically. If Task 19's repeat-validation shows a correctness regression on complex Workflow A/C reasoning, this is the first place to look.

3. **Resource/Model Lifecycle Manager was fully implemented but never invoked — fixed.** While investigating "model-swap visibility" for Workflow B (Requirement 5), found that `resource_loaded`/`resource_unloaded` had **never fired once**, anywhere, in the entire session — confirmed by querying `audit_events` directly (zero rows of either type ever) and `resource_state` (only 2 of 4 resource types have rows at all, both showing a placeholder `2024-01-01T00:00:00` seed timestamp despite real, repeated usage). Root cause: `backend/domain/orchestrator/agent.py:69` (via `job_manager.py`'s `_JobBoundModelClient`) and `backend/domain/capabilities/generate_code.py:118` and `backend/domain/document_processing/vision_escalation.py:43` all call `model_runtime.generate()` **directly** — `backend/domain/model_runtime/lifecycle_manager.py`'s `acquire()` (the only place that emits these two event types, and that owns memory-pressure admission/eviction) is dead code on the real request path; it's only exercised by its own unit tests (`test_lifecycle_manager.py`).
   - **User approved fixing this** (a subsystem file outside Task 17's allowed list, `backend/domain/*`) given its direct relevance to a Task 17 acceptance criterion. Fixed at all three real call sites — each now calls `await acquire(resource_type, job_id=...)` immediately before the existing `model_runtime.generate(...)` call, guarded so it only runs on the real runtime path (test fakes, whose `generate()` signature has no `job_id` param, are unaffected — verified: full suite still 501 passed / 1 known flake, same as before).
   - Verified live via a direct API-level job (not through the browser, for speed): trace now shows `resource_loaded {resource_type: reasoning, model_identifier: qwen3.5:9b, duration_ms: 3797}` on a cold load, immediately followed by the real `model_invoked` for the same turn.

4. **Health-check "flood" the user separately reported — investigated, confirmed already fixed, no new bug.** A fresh, unbuffered, single-tab measurement against a clean backend showed a steady ~1 request/2s (matching `SovereigntyIndicator`'s documented 2s poll interval) — not a flood. This exact class of bug (`useApi` effect re-running every render) was already found and fixed in this workstream's baseline (Entry 1, commit `6f79ccc`) before this session started; what the user saw was almost certainly this session's own long-lived, many-times-hot-reloaded browser tab hitting their freshly-restarted backend, read through un-timestamped terminal scrollback. No code change made.

**How to verify:**
- `think`/lifecycle fixes: `curl -s -X POST http://127.0.0.1:8000/api/v1/jobs -d '{"conversation_id":"<id>","message":"...","document_ids":[]}'`, poll `GET /jobs/{id}`, then `GET /jobs/{id}/trace` — expect a `resource_loaded` event on first use of a resource type per process lifetime, and turn durations in the single-digit-to-low-teens seconds for simple prompts (was 12–276s per turn before).
- Backend suite: `python -m pytest backend/tests/ -q` — 501 passed, 1 known environmental flake (unchanged from before these fixes).
- Memory pressure: `memory_pressure`, `vm_stat`, `ollama ps` — no code-level check; environmental only.

**Decisions made:**
- Fixed items 2 and 3 despite being outside Task 17's `backend/api/*`/`frontend/src/*` charter, with explicit user approval each time (user directed the investigation and owns the affected subsystems). Item 1 (memory pressure) is left as a flagged environmental risk, not a code change — there is nothing in this app's code to fix for it beyond item 2/3's mitigating effect of using less compute per call.
- Did not attempt to fix the Orchestrator's `malformed`-output frequency (several turns this session produced non-JSON output requiring a free corrective retry) — this is Orchestrator/prompt-engineering territory (Task 9), and the `think: false` fix may have already substantially improved it (shorter generations reduce the chance of losing the JSON format mid-ramble) but this wasn't isolated/re-tested after the fix. Flagging for Task 9 / Task 19's repeat validation to re-assess malformed-rate post-`think:false`.

**Supersedes / references:** Discovered while manually verifying Entry 2's Workflow B pass (Requirement 5's "confirm a resource_loaded entry is visible" criterion).

---

### Entry 4 — 2026-09-13 08:10 — Conversation history (list + resume) and "New chat"

**What changed:** User asked, now that turns are fast, to add "conversation history and all that" on this same branch.

- `backend/repositories/conversations.py` — added `list_conversations(limit, offset)`, ordered by `updated_at DESC` (most recently active first), same pattern as the existing `list_documents()`.
- `backend/api/conversations.py` — added `GET /api/v1/conversations` (list). No `title` field exists on Conversation (`docs/data-model.md`), so each entry carries a `preview` derived from its first message at read time instead — same non-invasive approach as the documents list (Entry 2), no data-model change. `docs/api.md` updated.
- `backend/tests/test_api_conversations.py` — 3 new tests (`test_list_conversations_most_recent_first`, `test_list_conversations_preview_from_first_message`, `test_list_conversations_respects_limit`). All pass; full suite 504 passed / 1 known flake (up from 501 — matches the 3 new tests).
- `frontend/src/services/api.js` — added `listConversations()`.
- `frontend/src/components/ConversationHistory.jsx` (new) — a "History" dropdown (same UI pattern as `DocumentPicker.jsx`) listing past conversations with preview text, timestamp, message count; clicking one resumes it.
- `frontend/src/pages/Workbench.jsx` — added a "New chat" button and the `ConversationHistory` picker to the top bar (both hidden in `simMode`, since there's no backend to list from). `handleSelectConversation` sets `conversationId` and clears `activeJobId`/`jobData`, which naturally drops to the existing empty-state composer layout — `ChatPanel` there already loads and displays full history for whatever `conversationId` it's given, so no new "history view" mode was needed. `handleNewConversation` resets all three to null.
  - **Bug caught before it shipped:** switching conversations while already in the empty-state view doesn't change React's rendered branch, so `ChatPanel`'s internal `conversationId` state (only read from its prop on first mount, per Entry 2's earlier finding) would never update — same class of staleness bug as Entry 2, different trigger. Fixed by keying both `<ChatPanel>` usages with `key={conversationId ?? 'new'}`, forcing a clean remount (and correctly-initialized internal state) on every conversation switch.

**How to verify:** `python -m pytest backend/tests/test_api_conversations.py -q` (7 passed); `npm test -- --run` (14/14) and `npm run build` (clean). Manual: opened History, resumed a real past conversation (from Entry 1's original bug report, still in the DB — "Hey" / "Can you tell me pump specifications?"), full history rendered correctly; sent a new message in it ("What is 5 times 6?") — correctly continued the *same* conversation (same `conversation_id` in a new Job) rather than starting fresh, answer rendered correctly ("5 times 6 is 30."), job completed in ~15s. "New chat" verified to reset cleanly back to the empty composer.

**Decisions made:** No `title` field added to the data model — `preview` is computed at read time from the first message, avoiding a schema change for a cosmetic label.

---

### Entry 5 — 2026-09-13 08:15 — UI polish pass: attachment-note chip, sovereignty indicator dark-theme + overflow fix

**What changed:** user asked for a basic UI pass now that turns are fast enough to actually click through the app quickly.

- **Attachment note leaking raw UUIDs into chat bubbles.** `backend/domain/job_manager/manager.py:236` embeds `"[Attached document(s): document_id=<uuid>]"` directly into the *persisted* message content — necessary, since that's the only channel the Orchestrator has to learn which document to pass into `extract_document`'s arguments (there's no separate `document_ids` column on Message). But rendering that raw string verbatim in the chat bubble (visible in every Workflow A screenshot this session) is a display problem, not a backend one. `ChatPanel.jsx` now splits it out client-side (`splitAttachmentNote()`) and renders a small "📎 <id-prefix>" chip below the bubble instead of a paragraph of raw UUIDs — the backend/stored content is untouched, this is purely how it's displayed.
- **`SovereigntyIndicator` — light-mode colors inside a dark app shell, and overflowing its container.** It hardcoded Tailwind light-mode classes (`bg-emerald-50`, `text-emerald-800`, etc.) never adjusted for `AppShell`'s dark shell, and rendered as a full padded card (checked_at / monitoring_since / disclaimer each on their own line) inside `StatusBar`'s `h-9` footer — it visibly overflowed downward past the footer, off the bottom of the viewport in some screenshots this session. Redesigned as a single-line badge using the app's actual dark-theme tokens (`text-ok`/`text-danger`/`border-line` etc., matching every other component in the codebase) that fits the footer; `monitoring_since` and the disclaimer are still in the DOM (`sr-only` + a hover `title` tooltip) rather than dropped, so nothing observable by the existing test suite changed.
  - **Caught and fixed before it shipped:** the initial edit for the `checked_at` separator wrote the literal 6-character string `·` into JSX text (not a JS string context, so the escape never gets interpreted) — rendered as literal backslash-u-zero-zero-b-seven on screen instead of "·". Fixed by wrapping it as a JS string expression `{"·"}`. Caught by actually looking at the rendered page, not just the test suite (the tests only check `toHaveTextContent` substrings, which don't catch a wrong-but-present character).

**How to verify:** `npm test -- --run` (14/14, `SovereigntyIndicator.test.jsx`'s 8 tests unchanged/still passing — confirms `data-testid`/`data-variant`/text-content contracts held through the restyle) and `npm run build` (clean). Manual: uploaded a document, sent a message, confirmed the bubble shows clean text + a chip (not raw UUIDs); confirmed the sovereignty badge renders as a compact single-line item matching the dark shell, no overflow, correct separator character.

**Decisions made:** Left the backend's stored message content as-is (raw attachment note intact) rather than adding a `document_ids` column to Message to carry attachments out-of-band — that's a data-model change (`docs/data-model.md`, AGENTS.md §6 rule 13) out of a UI-polish pass's scope; the display-layer split accomplishes the same visible result without touching the schema.

**Supersedes / references:** The raw attachment-note text and the sovereignty-panel overflow were both visible in every screenshot from Entries 2–4's manual verification passes but not flagged as findings at the time (out of scope until this explicit UI-polish ask).

---

### Entry 6 — 2026-09-13 19:55 — Documents and Created (Artifacts) pages; sidebar nav; found test suite is writing into the real database

**Context:** user, driving live against the running dev stack, asked two things: (1) confirmed the inline "Browse" documents picker in ChatPanel was misleading — it showed the same global list regardless of which chat you're in (documents were never conversation-scoped in the data model to begin with), so it didn't belong inside a per-chat composer. (2) Asked for dedicated pages for "documents uploaded" and "documents created" reachable from the sidebar, rather than folding everything into an inline sidebar list (an intermediate design this entry supersedes within the same session — see below).

**What changed:**

- **Removed** `DocumentPicker.jsx` and its use in `ChatPanel.jsx` (the "Browse" button) — deleted, no longer used anywhere.
- **New: `GET /api/v1/artifacts`** (list, most recent first) — `backend/repositories/artifacts.py` (`list_artifacts()`), `backend/api/artifacts.py`. No global list existed before, only `list_artifacts_by_job`. `docs/api.md` updated. Regression-tested by extending `test_e2e_workflow.py`'s existing `create_docx` test to also assert the artifact shows up in the list, most-recent-first.
- **New pages:** `frontend/src/pages/Documents.jsx` (all uploaded documents, `GET /api/v1/documents`, polls every 10s) and a rewritten `frontend/src/pages/Artifacts.jsx` (all generated artifacts, `GET /api/v1/artifacts`, same polling pattern, each row links straight to the download endpoint) — the old `Artifacts.jsx` was a static Task 16.a mockup with a hardcoded "0 files" badge and no real data fetching; this replaces it with a real one.
- **Real client-side page switching, added to `App.jsx`:** `page`/`setPage` local state, no router library added (kept off `package.json` — a new dependency needs sign-off per `AGENTS.md` §10, and three flat pages don't need one). `AppShell`'s `onNavigate` prop, previously a no-op stub (`() => {}`), now actually switches pages. `Sidebar.jsx`'s `NAV_ITEMS` gained `Documents` and `Created` alongside `Workbench`; `Header.jsx`'s `PAGE_META` gained a `documents` entry (`artifacts`'s title changed from "Artifacts" to "Created" to match the sidebar label).
- `docs/frontend.md` updated: the page/layout tree, a new "Documents page" / "Created (Artifacts) page" / "Conversation history" section, and the stale "single-page app for SIH" framing corrected to describe the actual (still router-library-free) three-page structure.
- **Intermediate design, built then superseded within this same entry:** first attempt was an inline "Documents" list embedded directly in `Sidebar.jsx` (a `DocumentsSidebar.jsx` component, `max-h-48` scrollable panel below the nav). User redirected mid-build: full pages, sidebar as navigation only. That component and its Sidebar wiring were removed before committing; mentioned here only so a reader diffing this entry's commits isn't confused by why `Sidebar.jsx` has churn beyond the final nav-items change.
- `App.test.jsx`: the `listDocuments`/`listArtifacts`/`listConversations` mocks were missing from the shared `vi.mock('../services/api.js')` factory (added as each new component started fetching on mount and broke the suite) — this is a recurring pattern this session (documents, conversations, now artifacts) worth remembering: **any new page/component that fetches on mount needs its API function added to this mock**, or every test using `<App />` fails opaquely with "No export is defined on the mock." Renamed the stale `describe('Navigation removed - Workbench only')` block and added a test that actually navigates to both new pages.

**How to verify:** `npm test -- --run` (15/15) and `npm run build` (clean). `python -m pytest backend/tests/ -q -k "not integration"` (504 passed, 1 known flake, unchanged). Manual: confirmed live against the user's own running dev stack — sidebar shows Workbench/Documents/Created, composer no longer has a "Browse" button, Documents page renders the real (if currently polluted, see below) document list, Created page cleanly shows an HTTP 404 error banner (not a crash) since the backend hadn't been restarted yet to pick up the new endpoint — confirms the error-handling path works, not just the happy path.

**Found while verifying — not fixed, needs a decision:** the live Documents page showed **100 files**, almost entirely test-fixture junk (`bad.pdf`, `slow.png`, `corrupt.png`, many duplicate `test.png`/`test.pdf`, all uploaded in one batch). `backend/tests/test_document_processing.py` (and likely others using the same `client = TestClient(app)` pattern instead of an isolated-DB fixture like `bulwark_client`/`isolated_db`) writes directly into the **real** `data/db/app.db` and `data/uploads/` — every `pytest` run during this session's development polluted the user's actual document list. This is now visibly a problem now that a real page surfaces it. Flagged for the user to decide: clean up the junk rows now, and/or fix the test isolation (route document-upload tests through an isolated DB fixture) so it stops recurring — not done yet, pending the user's go-ahead since it touches the test suite's fixture architecture, not just this task's glue files.

**Decisions made:** No router library added — `page` state in `App.jsx` is sufficient for three flat pages and avoids a new dependency. Documents/Artifacts pages are view-only (no attach-to-chat action from either page) — attaching a document to a message still only happens via a fresh upload in the Workbench composer, since wiring a cross-page "attach this to my active chat" action would require lifting state above `AppShell`, out of proportion for what was asked.

---

### Entry 7 — 2026-09-13 20:00 — Real-database cleanup, test isolation fix, and filters on Documents/Created

**What changed:**

*Real-database cleanup (Entry 6's flagged finding, user said do it now):*
- Queried `data/db/app.db` directly: **721** rows in `documents`, of which only **3** were ever referenced by a real Job (`WHERE EXISTS (SELECT 1 FROM messages WHERE content LIKE '%' || document_id || '%')` — the attachment-note pattern is the only channel a document reaches a real Job, so "never referenced" reliably means "never used," not "used but not yet"). The other 718 were recognizable pytest fixtures (`test.png` ×166, `test.pdf` ×61, `corrupt.png` ×55, `clean.png`/`degraded.png`/`handwritten.png`/etc. ×25 each, `bad.pdf`/`slow.png`/`large.png`/`one_artifact.pdf`/`artifact_test.png` ×30 each) going back to **2026-09-11** — this predates this session, so the pollution wasn't new today, just newly visible once a real page (Entry 6) surfaced the list.
- Deleted the 718 junk rows and their on-disk files under `data/uploads/` (258 removed; 460 were already-overwritten duplicates sharing a bare, non-UUID storage path like `clean.png` — a second sign these were test fixtures, since real uploads always get a UUID-prefixed path per `backend/api/documents.py`). Also swept 82 further orphaned `.md`/`.txt` files in `data/uploads/` with **no** matching row in either `documents` or `knowledge_base_documents` — likely stray KB-ingestion temp files from other unisolated test runs. `data/uploads/` went from 344 files / 2.6MB to 4 files (3 real uploads + `.gitkeep`).
- **Checked and confirmed untouched:** `artifacts` (3 rows, matched 3 real files on disk — already clean, no test pollution there) and `knowledge_base_documents` (4 SOPs, `status: ready`, unaffected — a different table entirely; user asked mid-cleanup whether the SOPs were still there, confirmed live).

*Root cause fixed — `backend/tests/test_document_processing.py` was the sole polluter:*
- It built its own `client = TestClient(app)` at module scope and imported `create_document`/`get_document` from the **bare** `repositories.documents` path rather than `backend.repositories.documents` — this file's own sys.path setup (`_BACKEND_DIR` and `_REPO_ROOT` both inserted) makes those two import paths resolve to **separate `sys.modules` entries** for the same file, so `conftest.py`'s `isolated_db` fixture (which only patches `backend.repositories.*`, per its own `_REPO_MODULES` list) never touched this file's real DB calls, whether via the bare-imported `create_document()` (~17 call sites) or via `client.post("/api/v1/documents", ...)` (13 call sites, all in `TestUploadEndpoint` plus one more). Its own `temp_db` fixture was a **literal no-op** (`pass`) with a docstring reading "uses the real database initialized at project root... D:\HACKATHON\Bulwark\data\db\app.db" — a leftover from a different machine/session, not hiding what it did.
- Fixed: import switched to `backend.repositories.documents` (matching `isolated_db`'s patch target); `temp_db` now `return isolated_db` (a real fixture, not a no-op) — this alone fixed all ~17 direct-repository-call tests with zero change to their bodies, since they already declared `temp_db` as a parameter; added a new `client` fixture depending on `temp_db` (ensuring the patch is active before any request), and added `client` as an explicit parameter to the 12 test methods that previously read it off the module global.
- Verified with a before/after document count around a full run of this file (53 tests) and the full suite (505 tests): **3 before, 3 after**, both times. Full suite otherwise unchanged (504 passed, the one pre-existing `test_executor_error_is_failed_tool_result_not_crash` flake, same as every prior entry).
- Other files using `TestClient(app)` were checked and are fine as-is: `test_api_health.py`/`test_health.py` only hit read-only `GET /health`; `test_artifacts_docx.py`/`test_job_lifecycle.py`/`test_e2e_workflow.py`/`test_rag_ingestion.py` all already have their own working isolation (`temp_db`/`patched_repos`, or depend on `isolated_db` directly) — `test_document_processing.py` was the only one actually leaking into the real database.

*A second, related isolation gap — caught live, not from reading the code first:* fixing the DB rows didn't stop real file *bytes* from landing in `data/uploads/` — `backend/api/documents.py` (and separately `backend/domain/capabilities/extract_document.py`, imported by this test file under a **third** bare module spelling, `domain.capabilities.extract_document`) each hold their own `from backend.utils.paths import UPLOADS_ROOT` binding, copied by value at import time — patching the source module doesn't reach them. Confirmed by running the full suite once after the DB fix alone: `data/uploads/` went from 4 files to 34. The `client` fixture now also monkeypatches `UPLOADS_ROOT`/`uploads_path` on all three module references (`backend.api.documents`, `backend.domain.capabilities.extract_document`, and the bare `domain.capabilities.extract_document`) to a per-test `tmp_path`. Verified stable at 4 files through both a single-file run and the full suite.

*Filters, added to both Documents and Created pages (user asked directly):*
- Both pages fetch up to 100 rows already (no new API params needed) and now filter client-side: a filename search box plus type pills (Documents: All/PNG/JPEG/PDF against `content_type`; Created: All/DOCX/XLSX/PPTX against `type`). Badge now reads "N of M files" to show filtering is active. A distinct empty state ("No documents/artifacts match your filters") when a filter yields zero rows, separate from the "nothing uploaded/generated at all yet" empty state.

**How to verify:** `python -m pytest backend/tests/ -q -k "not integration"` (504 passed, 1 known flake); `python -m pytest backend/tests/test_document_processing.py -q` (53 passed) with a document-count check before/after (both 3). `npm test -- --run` (15/15) and `npm run build` (clean). Manual: confirmed live — Documents page shows exactly the 3 real `inspection-report-clean.png` uploads; Created page shows exactly the 3 real generated DOCX files; JPEG filter on Documents correctly shows the "no match" empty state (all 3 real docs are PNG); type pills and search work on both pages.

**Decisions made:** Kept all 3 `inspection-report-clean.png` rows rather than de-duplicating to one — each was a genuinely separate real upload tied to a distinct real Job at a distinct time, not a duplicate to collapse. Did not add a bare-module-path guard to `conftest.py`'s `_REPO_MODULES` (e.g. also listing `repositories.documents` alongside `backend.repositories.documents`) — the more correct fix is for test files to import consistently via the `backend.`-prefixed path the app itself uses, which is what was done here; a conftest-level guard would paper over the next file that makes the same mistake instead of matching the app's actual import convention.

**Supersedes / references:** Resolves Entry 6's "Found while verifying — not fixed, needs a decision" item and its corresponding "Open questions" entry (removed below, answered).

---

### Entry 8 — 2026-09-13 20:20 — Knowledge Base page

**What changed:** user asked, after checking the new Documents page, where their 4 ingested SOPs were — they aren't there, and hadn't been surfaced anywhere in the UI (Entry 1/6 both flagged this as an open gap; this closes it). `frontend/src/pages/KnowledgeBase.jsx` (new) — `GET /api/v1/knowledge-base` (already existed, no backend change needed), same table+filter pattern as Documents/Created (search by title, status pills All/Ready/Ingesting/Failed). Wired into `Sidebar.jsx` (fourth nav item), `Header.jsx` (`PAGE_META.knowledge` title corrected from stale "Knowledge" to "Knowledge Base" to match), and `App.jsx`. Deleted the old unused `pages/Knowledge.jsx` Task 16.a mockup — it was dead code with the same near-identical name as the new real page, which would've been a confusing pair to leave both sitting in the tree (unlike `Jobs.jsx`/`Audit.jsx`/`Settings.jsx`, left alone — no living counterpart to be confused with).

**How to verify:** `npm test -- --run` (15/15, including a new sidebar-navigation assertion for the Knowledge Base page) and `npm run build` (clean). Manual: confirmed live — all 4 SOPs shown (`SOP-001` through `SOP-004`, all `status: ready`, correct chunk counts 4/3/3/4 matching what `GET /api/v1/knowledge-base` returns directly).

**Decisions made:** View-only, same as Documents/Created — no ingest-from-UI or delete-from-UI action added, even though `ingestKnowledgeDocument`/`deleteKnowledgeDocument` already exist in `services/api.js`; only a viewer was asked for.

---

### Entry 9 — 2026-09-13 20:35 — Branch `fix/kb-upload-ui`; KB ingest UI; full regression sweep found and fixed 2 real bugs

**Context:** `feature/integration` was squash-merged to `main` (commit `8b3ee6a`) and deleted, outside this session's visibility — discovered when `git branch -vv` showed only `main`, now containing every commit from Entries 1–8. New branch `fix/kb-upload-ui` created from `main` per the user's request ("name it appropriately for fixes"). First ask on it: "how would one upload documents for RAG/knowledge base" — Entry 8 had left the Knowledge Base page view-only; this makes it answerable via the UI itself rather than just an API description.

**What changed:**

*KB ingestion UI:* `frontend/src/pages/KnowledgeBase.jsx` — an "Ingest document" button (top-right, matching the page's action-button convention), hidden file input accepting `.txt/.md/.markdown/.pdf` (`backend/api/knowledge_base.py ALLOWED_EXTENSIONS`), no title/category prompt (backend already defaults title to the filename stem). On success, refetches the list immediately rather than waiting for the next 10s poll. No backend change — `POST /api/v1/knowledge-base/documents` already existed and was already wired in `services/api.js` (`ingestKnowledgeDocument`), just never used anywhere in the UI.

*User then asked for a full regression sweep ("go through the codebase again, test APIs and stuff, check for bugs from the new code"):* backend suite (505 passed / 1 known flake), frontend suite (15/15), production build (clean), then live-tested every list/ingest/delete endpoint touched this session via curl (`documents`, `conversations`, `artifacts`, `knowledge-base` — list + the new ingest + delete), and a full click-through of Workbench/Documents/Created/Knowledge Base with console-error monitoring. Found and fixed two real, previously-undetected bugs:

1. **`UploadButton.jsx`'s file-input ref was `useState(null)`, not `useRef(null)`.** Flagged as a "known cosmetic gap" all the way back in Entry 1 but never actually fixed. It happened to work (arrays are objects, so React's `ref.current = node` assignment silently landed on the array), but fired an "Unexpected ref object provided" console error on every single render of any page that mounts `ChatPanel` — i.e. the Workbench, essentially always. Fixed: `useRef`. Verified the warning is gone after a hard reload, and that upload still works via a real click-triggered file input, not just the automated test bypass.
2. **Conversation history preview leaked the raw attachment note.** `GET /api/v1/conversations`' `preview` field (Entry 4) is computed from the first message's raw stored content, which for a message with an attached document includes `backend/domain/job_manager/manager.py`'s `"[Attached document(s): document_id=<uuid>]"` note (Entry 5 only stripped this for the chat-bubble *display*, not this separate server-computed field) — so the History dropdown showed raw UUIDs for any conversation that started with an attachment. Fixed: `backend/api/conversations.py` strips the same note pattern before truncating for `preview` (mirrors `ChatPanel.jsx`'s `ATTACHMENT_NOTE_RE`) — the *stored* message content, and what the Orchestrator reads, is untouched; only this derived, read-time field changed. New test: uploads a real document, drives a job with it attached, asserts the list `preview` has no note/UUID while `GET /conversations/{id}`'s full message content still does.

**How to verify:** `python -m pytest backend/tests/ -q -k "not integration"` (505 passed, 1 known flake — same as every prior entry); `python -m pytest backend/tests/test_api_conversations.py -q` (8 passed, including the new attachment-stripping test); `npm test -- --run` (15/15) and `npm run build` (clean). Manual: ingested a real test document through the live UI (not just curl) and confirmed it appeared `ready` without a page reload; confirmed the "Unexpected ref" console error is gone after the `UploadButton` fix; confirmed the History dropdown preview is clean for an attachment-note conversation after the `conversations.py` fix. Test artifacts created during this verification (one extra document upload, two KB test ingests) were cleaned up afterward — real DB back to the expected state: 3 documents, 3 artifacts, 4 KB documents.

**Decisions made:** Kept KB ingestion UI minimal (no title/category form) rather than adding a small modal for the two optional metadata fields — the backend's filename-stem default was judged sufficient for a first cut; can be added later if titles need to differ from filenames often in practice.

**Supersedes / references:** Fixes the `UploadButton.jsx` gap noted as "known" (not actioned) in Entry 1. Extends Entry 5's attachment-note display fix to the read-time `preview` field Entry 4 introduced.

---

### Entry 10 — 2026-09-22 12:40 — Pre-demo real-database cleanup (chats/documents/artifacts), no code changes

**Context:** user is about to showcase the project and asked to clear out prior chats/documents from the real `data/db/app.db` for a clean demo start, without breaking anything. Same class of task as Entry 7 (which fixed the *cause* of test pollution); this entry is a second, later cleanup of real usage data that accumulated from actual manual demo/dev sessions since Entry 7 (not test pollution — `test_document_processing.py`'s isolation fix from Entry 7 held; confirmed by a full `pytest` run before and after this cleanup showing the real DB unchanged, see below).

**What changed:**
- Backed up `data/db/app.db`, `data/chroma/`, `data/uploads/`, `data/artifacts/` to `backups/pre-cleanup-20260922-124004/` before touching anything (same convention as the two prior `backups/pre-cleanup-*` folders from 2026-09-14/15).
- `DELETE FROM conversations` (11 rows) — cascades per `scripts/init_db.py`'s `ON DELETE CASCADE` FKs to `messages` (20), `jobs` (12), `job_steps` (35), `capability_executions` (13), `model_executions` (0), the one `artifacts` row, and all job-linked `audit_events` (161 of 9,238 rows: `job_created`/`job_completed`/`orchestrator_step`/`policy_decision`/`tool_invoked`/`tool_result`/`resource_loaded`/`resource_unloaded`/`artifact_created`/some `model_invoked`/`error`).
- `DELETE FROM documents` (5 rows, all the same `inspection-report-clean.png` re-uploaded across test/demo runs) — this table has **no FK to jobs** (confirmed against `scripts/init_db.py`), so it doesn't cascade from anything; deleted explicitly, then removed the 5 corresponding files from `data/uploads/`.
- Removed the 1 orphaned `data/artifacts/*.docx` file left behind after its row cascaded away (cascade drops the DB row, not the on-disk file).
- Removed 2 stray `.md` files in `data/uploads/` (`655ad353...`, `c7d15fe5...`) that matched no row in either `documents` or `knowledge_base_documents` — old orphaned upload temp files, not referenced by anything live.
- User explicitly asked, mid-task, to also clear the `network_check` audit rows (9,077 of 9,238 — the zero-egress monitor's own periodic log, `job_id IS NULL` so it doesn't cascade with anything else) since it "doesn't matter too much" — `DELETE FROM audit_events WHERE event_type = 'network_check'`. `VACUUM`ed afterward; `data/db/app.db` went from ~1.4MB-ish range down to 136K.
- **Explicitly did not touch:** `knowledge_base_documents` (7 SOP rows, all `status: ready`) or `data/chroma/` (vector store, one collection dir `d8f3cfd2-9e8e-4bac-b110-af948a6817ff` matching those KB docs) — user was explicit ("do not delete any RAG documents and such"). Also left `resource_state` (4 rows, model load/unload runtime state) alone — it's model-runtime state, not chat history.

**How to verify:** `python3 -m pytest backend/tests/ -q -k "not integration"` → 526 passed, 11 skipped, 16 deselected (unchanged pass count from the last known-good baseline, confirms Entry 7's isolation fix is still holding and this run didn't repollute the real DB — checked row counts before and after the test run, still `conversations=0, documents=0, artifacts=0, knowledge_base_documents=7`). `python3 -c "from backend.main import app"` imports cleanly (11 routes). Final row counts: `conversations/messages/jobs/job_steps/documents/artifacts/capability_executions/model_executions = 0`; `audit_events = 20` (16 `model_invoked` + 4 `error`, both pre-existing job-independent entries that don't reference the deleted jobs); `knowledge_base_documents = 7` (all 7 SOPs present, `status: ready`, unchanged); `data/chroma/` untouched; `data/uploads/` now holds exactly the 3 `.md` files backing the 3 KB docs whose storage path lives there (`91f8821e...`, `97e29400...`, `5cab8cbc...`) plus `.gitkeep`; `data/artifacts/` back to just `.gitkeep`.

**Open issues / known gaps:** none — this was a pure data reset, no code touched, no schema touched.

**Decisions made:** Left the 16 `model_invoked` and 4 `error` audit rows in place even though their originating jobs are gone — deleting them wasn't asked for and they don't reference anything that would dangle (no FK violation, `job_id` on those rows was already NULL or pointed at conversations/jobs deleted in the same transaction and is not enforced as NOT NULL). Used `DELETE` + explicit file removal rather than dropping/recreating tables — keeps the schema (and any app connections' cached statements) untouched, matches Entry 7's approach.

**Supersedes / references:** Same pattern as Entry 7's "Real-database cleanup," applied a second time to real (non-test) accumulated demo data rather than test pollution.

---

## Open questions for the user

All original questions in this section were answered during the 2026-09-13 session (see Entry 2: documents listing, answer surfacing, test approach; Entry 7: real-database cleanup and test isolation). None currently outstanding from this workstream — see Entries 2 and 3 for items still routed to other tasks (Workflow A's retrieval-skip, Workflow B's correction loop, `think:false` regression risk).

Carried forward, still open:
- **Workflow A's retrieval-skip** (Entry 2) — routed to Task 9 (Orchestrator), not answerable by the project lead alone; needs the Orchestrator owner's prompt/behavior fix, then a re-run.
- **Workflow B's correction loop** (Entry 2) — not naturally observed; is a dedicated Task 19 repeat-validation run (or a more failure-prone demo asset) the right way to capture it, or is this task's "the plumbing is verified" sufficient to call Requirement 5 done?
- **`think: false` regression risk** (Entry 3) — only benchmarked on a trivial prompt. Should Task 19's repeat validation specifically compare answer quality on Workflow A/C's harder reasoning cases with thinking on vs off before this is considered fully safe?

## Links

- PR: (pending — baseline currently riding on stacked branch `fix/useapi-request-flood`)
- Related branches / logs: `fix/useapi-request-flood` (stacked: CORS + useApi flood + trace dedupe + test plan), all owning-feature logs referenced in Entry 1
- Doc references: `tasks/17-frontend-backend-integration.md`, `docs/demo.md`, `docs/deployment.md`, `docs/api.md`, `docs/frontend.md`, `docs/audit.md`, `docs/configuration.md`, `test-assets/full-stack-test-plan.md`
