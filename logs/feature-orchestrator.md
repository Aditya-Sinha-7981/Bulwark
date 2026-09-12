# logs/feature-orchestrator.md

> Feature / workstream: `feature-orchestrator` (branches: `feature/orchestrator`, `fix/model-runtime-num-ctx-and-timeout`)
> Started: 2026-09-06 by opencode/mimo-v2.5-free
> Status: in-progress (Task 10 complete; identical-proposal loop guard on `fix/model-runtime-num-ctx-and-timeout` pending commit)

## Goal

Implement the hand-rolled Orchestrator agent loop per `docs/agent.md` and `docs/implementation-plan.md` Stage 10. Three modules: `proposal_parser.py` (parse/validate model output into proposals), `prompt_builder.py` (build system prompt from Capability Registry), `agent.py` (reasoning step function, termination logic, audit emission). The Orchestrator **proposes only** — no execution rights (AGENTS.md §6 rule 1). All outputs go through Policy → Job Manager → Executor path.

## Plan

1. Add schema models to `backend/models/schemas.py`: `Proposal`, `ParseResult`, `OrchestratorContext`, `GenerationResult`, `ModelClient` protocol, `StepOutcome`
2. Implement `proposal_parser.py`: parse raw JSON output → `ParseResult`; validate against Registry input schemas
3. Implement `prompt_builder.py`: build system prompt from `registry.all()` with all 7 `docs/agent.md` responsibilities
4. Implement `agent.py`: `step()` function with context assembly, model call (injected), parse, audit emit; `classify_step()` pure function for termination/step-limit logic
5. Implement `test_orchestrator.py`: comprehensive tests using fake ModelClient + fixture Registry
6. Run tests, verify no forbidden imports, append log entries

## Entries

### Entry 1 — 2026-09-06 13:00 — log created, implementation started
**What changed:** Created `logs/feature-orchestrator.md` (this file). Began reading all authoritative docs: AGENTS.md, project-context.md, agent.md, capabilities.md, data-model.md, audit.md. Inspected existing code: registry.py (349 lines, fully implemented), schemas.py (558 lines, Task 7 schemas), audit/events.py (202 lines), job_manager/manager.py (221 lines, stub orchestrator).
**Why:** AGENTS.md §4 requires a log file for every feature/workstream touched. Task 10 is the critical integration point for everything above Stage 7.
**How to verify:** `cat logs/feature-orchestrator.md`
**Open issues / known gaps:** Model Runtime (Task 8) not implemented — `agent.py` uses dependency injection (`ModelClient` Protocol) so tests use a fake; no adapter needed when Task 8 lands. Lifecycle Manager (Task 9) not needed directly by Orchestrator.
**Decisions made:** (1) Registry passed explicitly as function argument, never global singleton. (2) `ModelClient` Protocol for DI — field-for-field matches Task 8's real interface. (3) `classify_step()` is a pure function owned by Job Manager/Task 15, tested exhaustively here. (4) `agent.py` has zero forbidden imports — only imports from `domain/capabilities/registry.py` (read-only) and `domain/audit/events.py` (emit).
**Supersedes / references:** N/A — first entry.

---

### Entry 2 — 2026-09-06 13:30 — implementation complete, all 43 tests pass
**What changed:** Implemented all four files for Task 10:
- `backend/models/schemas.py:556-654` — added SECTION 5: `InvokeCapabilityProposal`, `RespondProposal`, `Proposal` (Union), `ParseResult`, `ToolResult`, `OrchestratorContext`, `GenerationResult`, `ModelClient` (Protocol), `StepOutcome`. Added `Protocol` to typing imports.
- `backend/domain/orchestrator/proposal_parser.py` (117 lines) — `parse_proposal(raw_output, registry) → ParseResult`. Validates JSON parsing, action field, capability names (via `registry.get()`), and arguments (via `registry.validate_input()`). Unknown capabilities → malformed per docs/agent.md (NOT hallucinated guesses). Empty respond content → malformed with error "empty respond content".
- `backend/domain/orchestrator/prompt_builder.py` (135 lines) — `build_system_prompt(registry) → str`. Reads `registry.all()` for capability names/purposes/input schemas. Includes all 7 docs/agent.md responsibilities: role/scope, capability list, proposal format, explicit retrieval rule, policy denial rule, untrusted data rule, step limit + convergence.
- `backend/domain/orchestrator/agent.py` (210 lines) — `step(context, model_client, registry) → ParseResult` (async, stateless per turn). `classify_step(result, malformed_retry_used) → StepOutcome` (pure function). step() assembles prompt from context, calls `model_client.generate("reasoning", prompt)`, parses output, emits `orchestrator_step` audit event every turn. Zero forbidden imports (verified by regex test).
- `backend/tests/test_orchestrator.py` (43 tests) — `TestPromptBuilder` (11 tests), `TestProposalParser` (12 tests), `TestTerminateOnEmptyContent` (3 tests), `TestClassifyStep` (7 tests), `TestAgentStep` (7 tests), `TestForbiddenImports` (3 tests). All 43 tests pass. Existing 80 capability contract tests also pass.

**Why:** Task 10 is the critical integration point — the only reasoning component. The Orchestrator proposes; it never executes. This implements the hand-rolled agent loop per docs/agent.md and docs/implementation-plan.md Stage 10.

**How to verify:**
```bash
cd /Users/adityasinha/Files/Codes/Hackathons/Bulwark
backend/.venv/bin/python -m pytest backend/tests/test_orchestrator.py -v  # 43 passed
backend/.venv/bin/python -m pytest backend/tests/test_capability_contracts.py -v  # 80 passed (no regressions)
```

**Open issues / known gaps:**
- Task 15 (Job Manager integration) must call `classify_step()` with its own step counter and `malformed_retry_used` flag — do NOT reimplement this logic independently.
- Task 8 (Model Runtime) is not implemented; tests use a fake `ModelClient`. When Task 8 lands, swap the fake for the real Ollama wrapper — no adapter needed since `ModelClient` Protocol matches field-for-field.
- The step limit in the prompt uses `registry._config` which may be `None` for test registries; defaults to 8. This is cosmetic — the real step-limit enforcement is in `classify_step()` + Job Manager.

**Decisions made:**
- `classify_step()` is a pure function tested exhaustively here (7 test cases covering all combinations). The Job Manager (Task 15) owns the step counter and `malformed_retry_used` flag; this function tells it what to do with them. This separation ensures step-limit logic never diverges from docs/agent.md.
- `step()` emits `orchestrator_step` with payload `{action, raw_proposal}` per docs/audit.md. For malformed output, action is "malformed" and raw_proposal contains the error.
- `OrchestratorContext.tool_results` uses `ToolResult` Pydantic model (not raw dict) to enforce the exact shape per docs/agent.md "Tool-result handling": `{role: "tool_result", capability: ..., result: {...}, status: "succeeded|failed|denied"}`.
- Prompt builder skips disabled capabilities (e.g., deferred `create_pptx`) to avoid confusing the model with unavailable tools.

**Supersedes / references:** Entry 1 (log created, implementation started).

---

### Entry 3 — 2026-09-06 14:00 — fix max_job_steps signature, remove registry._config access
**What changed:** Removed `registry._config` dependency from `prompt_builder.py`. Changed `build_system_prompt(registry)` to `build_system_prompt(registry, max_job_steps: int)`. Updated `agent.py` — `step()` now takes `max_job_steps` and passes it through to `_assemble_prompt()` which calls `build_system_prompt()`. Updated `test_orchestrator.py` — added `MAX_JOB_STEPS = 8` constant, updated all 11 prompt builder calls and all 7 step() calls. No `_config` access remains anywhere in the orchestrator module. `.ignore` confirmed untracked, excluded from this commit.
**Why:** `_config` is a private attribute of Registry (Task 7). `max_job_steps` is Policy config data (Task 6), not Capability Registry data. Reaching past public accessors creates a cross-contract coupling that would silently break if Task 7's internal representation changes. The fix removes the dependency entirely by making it an explicit parameter sourced by the caller (Task 15's Job Manager) from `settings.policy.max_job_steps`.
**How to verify:**
```bash
cd /Users/adityasinha/Files/Codes/Hackathons/Bulwark
grep "_config" backend/domain/orchestrator/prompt_builder.py  # no output
grep "_config" backend/domain/orchestrator/agent.py  # no output
backend/.venv/bin/python -m pytest backend/tests/test_orchestrator.py backend/tests/test_capability_contracts.py -v  # 123 passed
```
**Open issues / known gaps:** None — Issue 1 fully resolved.
**Decisions made:** `max_job_steps` flows as: caller (Task 15) → `step(ctx, model_client, registry, max_job_steps)` → `_assemble_prompt(ctx, registry, max_job_steps)` → `build_system_prompt(registry, max_job_steps)`. The `OrchestratorContext.system_prompt` field is retained in the schema but no longer used by `step()` — the prompt is built fresh from the Registry each turn to stay in sync with capability changes.
**Supersedes / references:** Entry 2 (this fixes the `registry._config` access identified as an open question in Entry 2).

---

### Entry 4 — 2026-09-12 10:45 — identical-proposal loop guard in the Job Manager dispatch loop (branch `fix/model-runtime-num-ctx-and-timeout`)

**What changed:**
- `backend/domain/job_manager/manager.py` — new `_canonical_arguments()` helper (canonical JSON, sort_keys) next to `_compact()` (manager.py:~191); `last_invocation_key` state in `run_job()` init; identical-proposal guard inserted after `proposal.capability`/`proposal.arguments` extraction and BEFORE the succeeded reasoning-step recording / Policy evaluation; `last_invocation_key` set right after the `policy_decision` emit (covers allow and deny).
- Guard behavior: proposal with identical `(capability, arguments)` as the immediately previous capability invocation → rejected before Policy: recorded as failed `orchestrator_reasoning` `JobStep` with `error_message: "identical capability invocation rejected: ..."` and `input_payload.rejected: "identical_proposal"`; `malformed_error` set so the corrective turn carries the message (same channel as the malformed rule); first rejection free via the existing `malformed_retry_used` flag, later ones count against the step limit; step-limit failure preserved (`_fail_step_limit`).
- `docs/agent.md` — new paragraph after the retry rule: "Identical consecutive proposals are rejected before Policy", with rationale and the B3-shape carve-out.
- `backend/tests/test_job_manager_dispatch.py` — added `test_identical_consecutive_invocation_rejected_and_job_completes` (1 tool_invoked, 1 policy_decision, failed reasoning step carries the rejection, Job completes) and `test_non_consecutive_identical_invocation_allowed` (search A→B→A: 3 dispatches, guard doesn't over-block); updated `test_invoke_loop_hits_step_limit` (still fails with `step_limit_exceeded`, but now `len(cap_steps) == 1` — rejections count, executor dispatches don't multiply).

**Why:** Observed live in job `4f3f0428` (2026-09-12, Workflow C "fire extinguisher inspection frequency" — a C2 not-covered question from the Postman collection authored for the never-ingested `api_testing/fixtures/sop-fire-safety.txt`): the Orchestrator proposed `search_knowledge_base` with byte-identical arguments 4× in a row, each identical tool result growing the prompt ~600 tokens until the (then-4096) context truncated and output went malformed, then the job died on the 120s read timeout. `docs/agent.md:81` makes convergence ("must converge, not loop indefinitely") a hard 100%-termination benchmark criterion; nothing enforced it. User approved the guard explicitly (over test-first and flag-only).

**How to verify:**
- `backend/.venv/bin/python -m pytest backend/tests/test_job_manager_dispatch.py backend/tests/test_orchestrator.py -q` — all pass except the pre-existing environmental `test_executor_error_is_failed_tool_result_not_crash` (verified failing on clean tree via `git stash`; expects uninitialised Chroma, this machine has a live seeded KB).
- Full non-integration suite: 493 passed, 9 skipped, 1 pre-existing environmental failure.

**Open issues / known gaps:**
- `malformed_retry_used` is a single per-Job flag shared by the malformed rule and this guard — an earlier malformed output consumes the one free turn, so a later first identical-rejection counts immediately. Bounded either way; noted deliberately.
- The guard is consecutive-only (not "any prior identical") — revisiting query A after query B is legal by design (context may have changed); the observed pathology is consecutive.

**Decisions made:**
- Rejection happens BEFORE Policy (no `policy_decision`/`tool_invoked` events for rejected turns — Policy stays purely per-capability deterministic; the guard is Job Manager loop logic, not policy).
- `last_invocation_key` updates on deny too — identical retry of a denied call is blocked, matching `docs/agent.md:17` ("denial is final for that attempt; never retried identically").
- No outcome carve-out: an identical retry after a FAILED invocation is also rejected (deterministic executors given identical inputs); the model must vary arguments or respond. The legitimate correction-loop shape (`generate_code → execute_code → generate_code`) is unaffected because the intervening capability breaks consecutive-identity.

**Supersedes / references:** None — new behavior on top of Entry 3's contracts; `test_invoke_loop_hits_step_limit`'s `len(cap_steps) == 3` expectation is superseded by `== 1` (documented in that test's new docstring).

---

## Handoff — contracts for not-yet-started tasks

### Task 8 (Model Runtime) — must satisfy this Protocol

`agent.py` calls `model_client.generate(...)` with this exact signature. Your `generate()` must match field-for-field:

```python
# backend/models/schemas.py — ModelClient Protocol
class ModelClient(Protocol):
    async def generate(
        self,
        resource_type: str,
        prompt: str,
        *,
        images: list[bytes] | None = None,
        options: dict | None = None,
    ) -> GenerationResult: ...

# GenerationResult fields:
#   text: str
#   prompt_tokens: Optional[int] = None
#   completion_tokens: Optional[int] = None
#   duration_ms: Optional[int] = None
#   model_identifier: Optional[str] = None
#   load_triggered: bool = False
```

The Orchestrator always calls you with `resource_type="reasoning"` — literally, never anything else, never read from config on the Orchestrator side.

### Task 15 (Job Manager / real dispatch integration) — two functions to call every turn

Do not reimplement their logic. The Job Manager owns the step counter and `malformed_retry_used` boolean (per Job).

```python
# Call this every turn — returns ParseResult (kind="proposal" or kind="malformed")
await agent.step(
    context: OrchestratorContext,
    model_client: ModelClient,
    registry: Registry,
    max_job_steps: int,           # from settings.policy.max_job_steps
) -> ParseResult

# Call this after parse_proposal — returns StepOutcome
# Apply counts_against_limit and terminal to your own step counter state
agent.classify_step(
    result: ParseResult,
    malformed_retry_used: bool,   # owned by Job Manager, per Job
) -> StepOutcome
```

Key details:
- `max_job_steps` must be sourced from `settings.policy.max_job_steps` and passed in — it is NOT read from the Capability Registry (see Entry 3; old code doing that was a bug).
- `OrchestratorContext.tool_results` must be built as `ToolResult` Pydantic objects, exact shape `{role: "tool_result", capability, result, status: "succeeded|failed|denied"}` — not raw dicts — when assembling context for the next turn.
- `classify_step` returns `counts_against_limit`, `terminal`, `terminal_reason` — apply that to your own state, don't recompute.
- Task 5's stub orchestrator (`backend/domain/job_manager/manager.py`) is what you're replacing with a real call to `agent.step()`/`classify_step()`.

## Open questions for the user
- Should `classify_step()` be exported from `agent.py` or moved to a separate `step_classifier.py` module? Currently in `agent.py` per the task spec.

## Links
- Branch: `feature/orchestrator`
- Related logs: `logs/feature-capability-registry.md`, `logs/feature-job-system.md`, `logs/feature-policy.md`
- Doc references: `docs/agent.md`, `docs/capabilities.md`, `docs/audit.md`, `docs/data-model.md`

---

### Entry 5 — 2026-09-12 12:35 — Document Deliverables Rule in the system prompt (branch `fix/model-runtime-num-ctx-and-timeout`)

**What changed:**
- `backend/domain/orchestrator/prompt_builder.py` — new "Document Deliverables Rule" section in `build_system_prompt()` (between Explicit Retrieval Rule and Policy Denial Rule): when the user requests a document deliverable (approval note, report, letter, spreadsheet, ...), the Orchestrator must propose `create_docx`/`create_xlsx` with structured arguments matching the input schema, then respond briefly (filename + summary) after the artifact succeeds; inline text only as a fallback when the document capability is denied/failed, or when the user explicitly asked for chat text.
- `backend/tests/test_orchestrator.py` — `test_prompt_includes_document_deliverables_rule` in `TestPromptBuilder` (asserts the section heading, capability names, `artifact_id`, and the fallback).

**Why:** Observed live (job `24e02e8e`, 2026-09-12, Phase 4): Workflow A executed flawlessly through `extract_document` and `search_knowledge_base`, and the final message was a high-quality, fully SOP-grounded approval note (every ground-truth finding correct: 8.3 mm/s → SOP-001 Band 3, 7-day corrective maintenance + notify Area Engineer; ~6 drops/min → Class II) — but the model answered inline and never proposed `create_docx`, so `artifact_ids: []` and no artifact existed to download. Root cause: the system prompt listed capability schemas but contained no guidance about when document deliverables must route through the artifact capabilities, and `docs/demo.md` Workflow A's expected outcome (a docx artifact) depends on that proposal. This stays within locked rule 6 (model produces structured data; application code renders the file) — the rule channels the model's output into the schema, it does not change rendering.

**How to verify:**
- `backend/.venv/bin/python -m pytest backend/tests/test_orchestrator.py -q` → 44 passed.
- Full non-integration suite → 503 passed; only failure is the pre-existing environmental dispatch test.
- Live: re-run Workflow A in a FRESH conversation → trace should now include a `create_docx` step (tool_invoked + artifact_created) and `artifact_ids[]` populated in Get Job Status; final message brief.

**Open issues / known gaps:**
- Model compliance with the new rule is probabilistic — verify on the live re-run; if the 9B still skips `create_docx`, the next lever is an example proposal block in the prompt (not done preemptively — prompt bloat has its own cost, and the current prompt already runs ~2.3K tokens).

**Decisions made:**
- Prompt-level guidance (not code-level forcing): the Orchestrator deciding *whether* a request is a document deliverable is exactly the model's job (docs/agent.md role); forcing it in code would need a classifier, which is heavier and beyond SIH scope.
- No `docs/agent.md` change: the deliverable expectation is owned by `docs/demo.md` (Workflow A) and `docs/capabilities.md` (artifact semantics); the prompt now implements it. Flagged for the demo doc owner to double-check the Workflow A narrative mentions the docx artifact.

**Supersedes / references:** Builds on Entry 4 (identical-proposal guard) — unrelated mechanism; no contradictions.

