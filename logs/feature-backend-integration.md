# logs/feature-backend-integration.md

> Feature / workstream: `feature-backend-integration`  (branches: `feature/backend-integration`)
> Started: 2026-09-10 by Claude Sonnet 5 (Claude Code)
> Status: in-progress

## Goal

Task 15 (implementation-plan.md Stage 15; `tasks/15-backend-api-integration.md`):
wire the real **Job Manager → Policy → Executor** dispatch loop, replacing Task 5's
stub Orchestrator, and complete the contract-first parts of the `docs/api.md`
surface (conversations, health probes, network-status + monitor, error mapping).
Enforce structurally that no capability executor is reachable except through the
single post-Policy dispatch function.

This branch is being built **before Tasks 11 / 12.a / 12.b / 13 merge**. Those
capability executors are still stubs (`raise NotImplementedError`). The loop is
built and tested against the pieces that *are* done (Tasks 6, 7, 8, 9, 10, 14.a,
14.b); the not-yet-built executors are dispatched normally and their
`NotImplementedError` surfaces as a `status: "failed"` tool-result (the Job does
not crash) — no stub lives in production code. The `docs/api.md` acceptance
("every endpoint", "a real no-stub workflow completes") is finished in a
follow-up once Task 12 or 13 lands.

## Plan

1. Normalise imports so `uvicorn backend.main:app` runs from repo root with no
   `PYTHONPATH` hacks (`backend.` prefix everywhere).
2. `manager.py`: full driver loop + the single `_dispatch_capability` seam +
   DI seam for the model client / registry / policy config.
3. `backend/domain/artifacts/sandbox_output.py`: the `execute_code` output-file →
   Artifact conversion helper (Requirement 6), reusing Task 14.a's atomic-write
   primitive.
4. `backend/api/conversations.py`; real `backend/api/health.py` probes.
5. `backend/domain/monitoring/network_monitor.py` + `backend/api/network_status.py`;
   start the monitor in `main.py` lifespan.
6. `main.py`: router registration + domain-exception → `docs/api.md` envelope
   handlers.
7. `backend/api/jobs.py`: populate `artifact_ids` on `GET /jobs/{id}`.
8. Tests: dispatch loop, structural guard, API contract (conversations / health /
   network-status), e2e-over-HTTP with a faked model turn, integration-tier
   Workflow C skeleton.
9. Log + propose commit. **Do not commit / push / PR** (AGENTS.md §7).

## Entries

### Entry 1 — 2026-09-10 — import normalisation + full dispatch loop + contract-first API

**What changed**

*Imports (so the app runs as a package from repo root):*
- `backend/main.py` — `from api.X` / `from config` / `from utils.paths` →
  `backend.api.X` / `backend.config` / `backend.utils.paths`. Verified
  `python -m uvicorn backend.main:app` boots from the repo root with no
  `PYTHONPATH` set (previously needed both repo-root **and** `backend/` on the
  path).
- `backend/tests/test_health.py:3`, `backend/tests/test_config.py:7-9`,
  `backend/tests/test_audit_events.py:16-28` — the three remaining bare-import
  test files converted to `backend.*`. This also removes a latent split-brain
  where `test_audit_events` drove `domain.audit.events` while the app used
  `backend.domain.audit.events` (two module identities, two subscriber
  registries).
- `backend/pytest.ini` left as-is (`pythonpath = .` is now harmless).

*Job Manager — `backend/domain/job_manager/manager.py` (rewritten, ~470 lines):*
- `stub_orchestrator` / `_build_orchestrator_context` deleted.
- `run_job` is the real driver loop implementing `docs/architecture.md`
  "Request lifecycle" 2–8: build `OrchestratorContext` from the `messages`
  history + accumulated `tool_results` → `agent.step(...)` (Task 10, emits
  `orchestrator_step` itself) → `agent.classify_step(...)` for step-limit /
  malformed accounting → act on the proposal.
- **`_dispatch_capability(...)` — the ONLY function that calls any capability
  executor, and `run_job` is its ONLY caller** (AGENTS.md §6 rule 1,
  Requirement 2). Big banner comment in the module docstring. Guard test:
  `backend/tests/test_structural_guard.py`.
- `respond` (non-empty) → `orchestrator_reasoning` JobStep `succeeded`, set
  `jobs.final_message`, append `messages` row `role: orchestrator`, terminate.
- `invoke_capability` → `orchestrator_reasoning` JobStep + `capability_invocation`
  JobStep (`kind`), then `policy.engine.evaluate(...)` → emit `policy_decision`
  (`capability`/`decision`/`reason`) → `capability_executions` row
  (`policy_decision`, `policy_reason` on deny, `resource_type` from the registry
  entry). Every invocation (`allow` **or** `deny`) increments `step_count`
  (agent.md: denials count).
- `deny` → JobStep `denied`, `{role: tool_result, status: "denied",
  result: {reason}}` appended; not overridable; loop continues (Orchestrator
  reacts) unless the limit is now hit.
- `allow` → emit `tool_invoked` → `_dispatch_capability` → (for `execute_code`)
  `_convert_execute_code_output_files` → `registry.validate_output(...)` →
  JobStep `succeeded`, `update_capability_execution(duration_ms=...)`,
  `{role: tool_result, status: "succeeded", result}` appended. Any executor
  exception (incl. `NotImplementedError` from Tasks 11/12/13 stubs, render
  errors) → JobStep `failed`, `error` event, `{... status: "failed",
  result: {error}}` — the Job never crashes (docs/architecture.md "Failure
  boundaries").
- Malformed proposal → failed `orchestrator_reasoning` JobStep; one free
  corrective turn (does not count) then it counts, per `classify_step`.
- Step limit (`policy.max_job_steps`) → `jobs.status = failed`,
  `error_code: step_limit_exceeded`, partial trace kept.
- `job_completed` (`status`, `duration_ms`) emitted exactly once from `finally`.
- DI seam: `set_test_dependencies(model_client=, registry=,
  capabilities_config=, policy_config=)` / `reset_test_dependencies()`.
  Production resolves the real Ollama `runtime`, `get_registry(settings.capabilities)`,
  and `settings`. `max_job_steps` is read via `_policy_config_for_policy()` so a
  test can shorten it.
- `create_job(...)` now also appends the triggering user message as a
  `messages` row (`role: user`) — the Orchestrator's context is the conversation
  history (docs/agent.md "Conversation state"), and `OrchestratorContext` has no
  separate `job_input` field.
- **`_JobBoundModelClient`** — binds `job_id` onto every model call. `agent.step`
  calls `model_client.generate(resource_type, prompt)` with no `job_id` (the
  `ModelClient` protocol carries none), but the real `runtime.generate` emits
  `model_invoked` / `error` audit events that **require** a `job_id`
  (`_validate_job_id` in `audit/events.py`). Without this, *every* real model
  call from the Orchestrator raised
  `ValueError: Event type 'error' requires a job_id`. The adapter inspects the
  inner client's signature and only passes `job_id=` when it is accepted, so
  test fakes are unaffected. See "Decisions" and "Open questions".

*New: `backend/domain/artifacts/sandbox_output.py`* — Requirement 6.
`persist_sandbox_output_as_artifact(source_path, job_id) -> artifact_id | None`:
copies a sandbox output file into `data/artifacts/{artifact_id}.{ext}` (atomic,
same primitive as `docx_renderer.render_docx`), writes the `Artifact` row, emits
`artifact_created`. Only `.docx` / `.xlsx` map to a documented `Artifact.type`;
any other extension returns `None` and the caller emits an `error` event noting
the file was produced but not persisted (Requirement 6's flagged
`Artifact.type`-enum gap — extending the enum is a `docs/data-model.md` change
needing a project-lead call, not made here). Uses the id `create_artifact()`
actually returns (unlike the renderers — see the artifacts bug below).

*New: `backend/api/conversations.py`* — `POST /api/v1/conversations` →
`201 {conversation_id, created_at}`; `GET /api/v1/conversations/{id}` →
`{conversation_id, created_at, updated_at, messages[]}` (each message the full
`data-model.md#Message` shape), `404` envelope for unknown.

*`backend/api/health.py`* — real probes: DB (`SELECT 1`), Ollama (TCP connect to
the configured loopback host:port — a liveness check, **not** an HTTP model call,
so `runtime.py` stays the only Ollama-HTTP module), Docker (`docker version -f
{{.Server.Version}}`). `status` stays `"ok"` whenever the handler answers;
per-dependency degradation is in the individual `ok | unavailable` fields; health
never 503s (Requirement 7).

*New: `backend/domain/monitoring/network_monitor.py` + `backend/api/network_status.py`*
— Requirement 4. A single background loop (`psutil.Process().net_connections`)
classifies any non-loopback remote address as external, updates the latest
result, and emits a `network_check` audit event (`job_id` null) each poll
(5 s). `GET /api/v1/network-status` → `{external_connections_detected,
checked_at, monitoring_since}`. Started/stopped in `main.py` lifespan. **Scaffold
only** — the six enforcement layers, the firewall, the socket backstop and the
offline run are Task 18 (comments say so).

*`backend/main.py`* — registers `conversations` + `network-status` routers;
starts/stops the monitor in `lifespan`; adds exception handlers mapping
`NotFoundError → 404`, `ConstraintError → 400`, `DatabaseError → 503`
(the DB is every request's own synchronous dependency — Requirement 7) to the
`docs/api.md` envelope, at the router boundary only.

*`backend/api/jobs.py`* — `GET /api/v1/jobs/{id}` `artifact_ids` now populated
from `artifacts_repo.list_artifacts_by_job(job_id)` (was hardcoded `[]`).

*`backend/repositories/jobs.py`* — added `update_capability_execution(id,
resource_type=, duration_ms=)` (field setter on existing columns, no schema
change) and `list_capability_executions_by_job(job_id)` (read helper). Both under
§4 "May Modify If Required: repositories (query helpers only; no schema
changes)". **Flagged to Sheikh** (Task 3 owner) — see Open questions.

*`backend/api/artifacts.py`* — `/download` now resolves the file via the row's
`storage_path` instead of reconstructing `{artifact_id}.{type}`. Works around a
bug in the Task 14 renderers (see below).

*Tests added* (`backend/tests/`):
- `conftest.py` — `isolated_db` (temp schema DB patched into every repo module)
  + `bulwark_client` (TestClient with a default faked model turn).
- `test_job_manager_dispatch.py` (8) — direct answer; real `create_docx` through
  Policy (no stub, artifact row + file on disk, `duration_ms` recorded);
  Policy `deny` blocks execution (no `tool_invoked` / `artifact_created`,
  JobStep `denied`); executor `NotImplementedError` → failed tool-result, Job
  still `completed`; free malformed corrective turn; repeated malformed hits the
  step limit; invoke-loop hits the step limit at exactly `max_job_steps`.
- `test_structural_guard.py` (3) — no module outside `domain/job_manager/`
  imports/calls a capability executor; `_dispatch_capability` has exactly one
  call site.
- `test_api_conversations.py` (5), `test_api_health.py` (4, probes
  monkeypatched), `test_api_network_status.py` (4).
- `test_e2e_workflow.py` (4 non-integration + 1 `@pytest.mark.integration`
  skipped) — full HTTP → loop → Policy → dispatch → trace for `respond` and
  `create_docx` (incl. artifact download returning a real `.docx` zip);
  denial path over HTTP; `/trace` == a direct `audit_events` query; the
  integration Workflow C test skips until `BULWARK_E2E_KB_SEEDED` + Tasks 12.
- `test_job_lifecycle.py` — reworked: the pre-Task-15 assertions on the stub's
  `"Echo: ..."` output are gone; it now drives the real loop with an injected
  `FakeModelClient`.

**Why**

`docs/architecture.md` "Request lifecycle", `docs/agent.md` "Policy interaction"
/ "Tool-result handling" / "Multi-step execution and step limits", `docs/api.md`,
`docs/audit.md` (`policy_decision` / `tool_invoked` / `job_completed` /
`network_check` payloads), Task 15 Requirements 1–7 and Acceptance Criteria.

**How to verify**

```bash
python3 -m venv /tmp/bwvenv && /tmp/bwvenv/bin/pip install -r backend/requirements.txt
/tmp/bwvenv/bin/python -m pytest backend/tests/ -q -m "not integration"
# 380 passed, 1 failed (pre-existing, not this task — see below), 6 deselected

# boot the app as a package from the repo root, no PYTHONPATH:
/tmp/bwvenv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
curl -s localhost:8000/api/v1/health
curl -s -XPOST localhost:8000/api/v1/conversations
# POST /api/v1/jobs with that conversation_id + a message:
#   with Ollama DOWN  → job reaches status "failed", error_code
#     "unrecoverable_error", trace = job_created → error(model_runtime) →
#     error(job_manager) → job_completed  (graceful, no hang)
```

**Open issues / known gaps**

1. **`documents` / `knowledge_base` routers not built or registered.** They are
   coupled to Tasks 11 / 12 (which `tasks/15-...md` §11 notes "build minimal
   versions"). Building them now would collide with Shregna's branches.
   Deferred to the follow-up when those merge. `docs/api.md`'s
   `POST/GET /documents`, `POST/GET/DELETE /knowledge-base` are therefore not
   yet served.
2. **No real no-stub demo workflow yet.** Acceptance criterion 1 needs Workflow C
   (Task 12) or Workflow B (Task 13). The loop + Policy + dispatch + trace are
   fully exercised today with a faked *model turn* and the real `create_docx`
   executor; `test_e2e_workflow.py::test_workflow_c_grounded_answer_real_model`
   is written and `@pytest.mark.integration`-skipped, ready to flip on.
3. **Task 14 renderer artifact-id bug (flag to Dev).**
   `docx_renderer.render_docx` / `xlsx_renderer.render_xlsx` discard the id
   `create_artifact()` returns and report the pre-generated id they used for the
   on-disk filename. Result: the `artifact_id` the capability returns has **no
   `artifacts` row**; the row that exists has a different id, and its file is at
   `storage_path` (the pre-generated name). Mitigations here: `GET /jobs/{id}`
   exposes real row ids via `list_artifacts_by_job`; `api/artifacts.py` resolves
   downloads via `storage_path`. The renderers themselves still need fixing —
   `backend/domain/artifacts/*` is Dev's (Task 14), not in this task's allowed
   files.
4. **Pre-existing test failure, not introduced here:**
   `test_model_runtime.py::TestStaticCheck::test_only_runtime_imports_httpx_for_model`
   flags `domain/model_runtime/lifecycle_manager.py:203` — it posts to
   `/api/generate` directly instead of via `runtime.py`. Owned by Task 9
   (Sheikh). (It also flags a teammate's gitignored `backend/.venv/…`, which is
   absent on a clean checkout.) `git diff` shows this task touched neither
   `model_runtime/` nor its test. Flagged to Sheikh.
5. **Executor signature divergence (coordination — Shregna / Rehan).**
   `create_docx` / `create_xlsx` are `execute(job_id, arguments) -> dict`; the
   four stub executors take a validated pydantic input model.
   `_dispatch_capability` bridges both. Request: the real Task 11/12/13
   executors adopt `async def execute_x(job_id, arguments,
   capability_execution_id) -> dict` so the seam stays trivial and
   `model_executions` correlation is clean.
6. **`_convert_execute_code_output_files` cannot yet resolve output files to
   absolute paths** — `ExecuteCodeOutput` carries no `execution_id`. Inert until
   Task 13 (only runs when `output_files` is non-empty, which the stub never
   returns). Task 13's executor must return an `execution_id` or absolute paths.

**Decisions made**

- The user's request is recorded as a `messages` row (`role: user`) at job
  creation, not carried as a separate context field — matches
  `OrchestratorContext` (no `job_input`) and docs/agent.md "Conversation state".
- Every capability invocation increments the step counter — `allow`, `deny`, or
  executor failure — per docs/agent.md ("denials count too").
- `capability_executions` row is created **before** dispatch (so the executor /
  Model Runtime can link `model_executions` to it) and its `duration_ms` is
  written after via `update_capability_execution`. Needed a repo setter (see
  gap 1); the alternative (deferred insert) would leave the executor unable to
  correlate model calls.
- When the *Orchestrator's own* reasoning model is unreachable, the Job ends
  `failed` / `error_code: unrecoverable_error` (docs/agent.md termination
  condition 3 — "required resource permanently unavailable"). This is distinct
  from a *capability's* model call failing, which is a recoverable failed
  tool-result.
- `health` `status` stays `"ok"` whenever the handler answers; degradation is
  reported per-field (Requirement 7; `docs/api.md` only ever shows
  `status: "ok"`).
- Ollama health probe is a raw TCP connect, not an HTTP call — keeps
  `runtime.py` the only module speaking Ollama's HTTP API and avoids the
  `test_only_runtime_imports_httpx_for_model` guard.
- `_JobBoundModelClient` closes the Task 10 ↔ Task 8 `job_id` seam inside the
  Job Manager rather than editing `agent.py` or the `ModelClient` protocol
  (both nominally out of this task's scope; the protocol change would ripple to
  every fake). If Task 10 later adds `job_id` to the protocol, this adapter
  becomes a no-op and can be deleted.

**Supersedes / references**

- Supersedes the Task 5 stub loop in `logs/feature-job-system.md` (Entry for
  `manager.py` skeleton) — that stub Orchestrator and its `"Echo: ..."` path are
  removed; `test_job_lifecycle.py` reworked accordingly.
- References: `logs/feature-orchestrator.md` (agent.step / classify_step
  contract), `logs/feature-policy.md` (`evaluate` dict return),
  `logs/feature-model-runtime.md` (`runtime.generate` `job_id` param),
  `logs/artifacts-docx.md` / `logs/artifacts-xlsx.md` (renderer primitive + the
  id bug), `tasks/15-backend-api-integration.md`.

## Open questions for the user

- **Sheikh (Task 3):** OK to keep `update_capability_execution` /
  `list_capability_executions_by_job` in `repositories/jobs.py`? They are field
  setters / read helpers on existing columns, no schema change. If you'd rather
  own the exact wording, say so and I'll adjust.
- **Shregna / Rehan (Tasks 11/12/13):** please land your executors as
  `async def execute_x(job_id, arguments, capability_execution_id) -> dict`
  (see gap 5). Flag before merge if that's a problem.
- **Project lead:** `Artifact.type` enum gap for generic `execute_code` output
  files (Requirement 6) — leave as-is (only `.docx`/`.xlsx` persisted) for SIH,
  or extend `docs/data-model.md`?

## Links

- PR: <none — AI does not open PRs (AGENTS.md §7)>
- Branch: `feature/backend-integration`
- Doc references: `docs/architecture.md`, `docs/agent.md`, `docs/api.md`,
  `docs/audit.md`, `docs/data-model.md`, `docs/backend.md`, `docs/security.md`,
  `docs/decisions.md` (ADR-02, ADR-11), `tasks/15-backend-api-integration.md`
