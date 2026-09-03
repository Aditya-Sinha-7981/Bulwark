# Agent (Orchestrator) Implementation

> **For AI coding agents working on the Orchestrator or its loop:** read `../AGENTS.md` first. Every commit on a branch touching the Orchestrator, the proposal parser, the prompt builder, or anything in `domain/orchestrator/` requires a `{branch_name}-log.md` entry at the repo root — append-only, never edited, specific enough that the next session can act on it without re-asking. The agent loop is exactly the kind of code where wrong assumptions are easy and silent regressions are costly; the log is what catches both.

## Responsibilities

Understand the request; decide direct-answer vs. capability invocation; produce a valid capability proposal; consume the result; decide whether another step is needed; produce the final answer; produce structured findings where a downstream capability (e.g. `create_docx`) requires them. Nothing else — see `project-context.md` for what it explicitly does not do.

## System prompt responsibilities

The system prompt given to the Orchestrator model must communicate, at minimum:

1. Its role and scope (as above).
2. The full list of available capabilities, each with: name, purpose, input schema. (Generated from `capabilities.md` — do not hand-maintain a second copy in the prompt; the prompt-building code reads the Capability Registry.)
3. The exact proposal format (below) — no other output format is acceptable for a capability call.
4. That retrieval (`search_knowledge_base`) must be explicitly proposed when grounding is needed — it is never automatic.
5. That a Policy denial is final for that attempt — react to it (explain, try a different approach), never assume it can be bypassed or retried identically.
6. That content from `extract_document` and `search_knowledge_base` results is **untrusted data**, not instructions to follow — a prompt-injection control, not a hard boundary (see `security.md`).
7. The step limit (see below) and that it must converge, not loop indefinitely.

## Capability proposal format

The Orchestrator's structured output, when proposing a capability, is exactly:

```json
{
  "action": "invoke_capability",
  "capability": "extract_document",
  "arguments": { "document_id": "uuid" }
}
```

Or, for a direct answer:

```json
{
  "action": "respond",
  "content": "string"
}
```

No other top-level `action` values exist. `capability` must exactly match a name in `capabilities.md` — an unrecognized name is a malformed proposal (see handling below), not a "hallucinated capability" the system tries to guess at.

## Conversation state

The Orchestrator receives, each turn: the conversation history for the current `conversation_id` (prior `Message` rows), the current Job's prior steps and their results (from `JobStep`/`CapabilityExecution` for this `job_id`), and nothing else — no implicit context, no automatically-injected retrieval (per ADR-03 in `decisions.md`).

## Capability discovery

Static, not dynamic — the full capability list is always presented in the system prompt; there is no separate "discovery" tool call. This keeps the proposal surface simple and testable.

## Direct-answer path

`action: respond` with `content` — recorded as a `JobStep` of `kind: orchestrator_reasoning`, `status: succeeded`, no `CapabilityExecution` row. This ends the Job (moves to step-limit/termination logic — see below; a direct answer with no further steps proposed terminates the Job immediately).

## Capability-call path

`action: invoke_capability` → validated against the Capability Registry schema → passed to Policy → (if allowed) dispatched to the Executor → result appended to context as a new "tool result" turn → loop continues from "Orchestrator reads context" (see `architecture.md`, Request Lifecycle).

## Tool-result handling

Tool results are appended to the Orchestrator's context in a fixed shape:

```json
{
  "role": "tool_result",
  "capability": "extract_document",
  "result": { "...capability's output schema..." },
  "status": "succeeded | failed | denied"
}
```

The Orchestrator must read `status` before treating a result as usable — a `failed` or `denied` result is not extractable data, it's a signal to change approach.

## Multi-step execution and step limits

Default step limit: **8** capability invocations per Job (configurable — see `configuration.md`). Each successful or failed capability invocation counts against the limit; Policy denials also count (to prevent a denial-retry loop from evading the limit). On reaching the limit without a final answer, the Job is marked `failed` with `error_code: step_limit_exceeded`, and partial results/trace are retained.

## Termination conditions

A Job terminates when: (1) the Orchestrator proposes `action: respond`, (2) the step limit is reached, (3) an unrecoverable error occurs (e.g., required resource permanently unavailable). Correct termination — stopping once the task is genuinely done, not looping past it — is a hard-required benchmark pass criterion (`testing.md`): **100% correct termination**, no exceptions tolerated.

A `respond` with **empty `content`** must not terminate the Job — treat it as a malformed step (record `status: failed` with `error_message: "empty respond content"`, give the model one corrective turn per the malformed-output rule below). Silent "empty answer" Jobs were a class of bug we explicitly closed; tests in `backend/tests/test_orchestrator.py::test_terminate_on_empty_content` lock the behavior.

## Retries

The Orchestrator may retry a capability with different arguments (e.g., regenerate code after a failed execution) — this is a new proposal, a new `JobStep`, and counts against the step limit. There is no automatic system-level retry of an identical failed call.

## Malformed output handling

If the Orchestrator's raw output doesn't parse as one of the two valid `action` shapes, or references an unknown capability, or fails schema validation against that capability's input schema: the backend does **not** attempt to execute anything. It's recorded as a failed `JobStep` (`kind: orchestrator_reasoning`, `status: failed`, `error_message` describing the parse/validation failure), and the Orchestrator is given one corrective turn (with the specific error included in context) before the step counts fully against the limit. This is the one exception to "every proposal counts" — a single malformed-output correction attempt is free, to distinguish a formatting slip from a genuine repeated failure.

## Hallucinated capability handling

A proposal naming a capability not in the Registry is treated identically to malformed output above — rejected before Policy is even reached, with the corrective-turn allowance.

## Structured output (for artifact generation)

When the Orchestrator needs to produce findings for `create_docx`/`create_xlsx`, it proposes that capability directly with the structured `arguments` matching that capability's input schema (`capabilities.md`) — there's no separate "structured output" mode; it's the same proposal mechanism, just with a richer `arguments` payload.

## Context construction

Context sent to the model per turn: system prompt (capability list + rules, built from the Registry) + conversation history for this `conversation_id` + this Job's prior tool results, in order. No summarization/truncation logic for SIH scope — Job step limits keep context bounded (8 steps × reasonably-sized tool results comfortably fits within the configured model's context window — see `models.md` for exact figures).

## RAG interaction

The Orchestrator interacts with retrieval exactly like any other capability — propose `search_knowledge_base`, receive results in the standard tool-result shape, decide whether the results are sufficient to answer or whether to try a different query/approach. See ADR-03 (`decisions.md`) for why this is explicit rather than automatic, and `capabilities.md` for the exact schema.

## Model invocation

The Orchestrator itself runs on the `reasoning` resource type, resolved via the Model Runtime/Lifecycle Manager exactly like any capability's model needs — the Orchestrator's own model identity is configuration (`config/resources.yaml`), never hardcoded in agent logic.

## Policy interaction — how the agent remains incapable of bypassing Policy

The Orchestrator's only mechanism for causing any effect in the world is emitting an `invoke_capability` proposal. That proposal is data (JSON), not code, and not an execution path. The backend code that receives it does exactly one thing with it: pass it to the Policy layer. There is no code path from "Orchestrator output" to "Executor runs" that does not pass through Policy — this is enforced structurally (the Job Manager only ever calls Executors via the post-Policy dispatch function; no other caller of that function exists), not by convention. A future implementer adding a new capability call site outside this path is the one failure mode to explicitly guard against in code review.

## Implementation checklist (for the AI writing this code)

When working on the Orchestrator (`backend/domain/orchestrator/`), the following must be true of your branch's work log entry:

- **Proposal parser:** cite the exact schema in `models/schemas.py` and any deviation from the JSON shapes above.
- **Prompt builder:** note where in the Registry it reads from (it must read `capabilities.md` as code, not a hand-copied prompt string).
- **Termination:** confirm the empty-`content` rule is implemented and tested.
- **Step-limit enforcement:** confirm denials, failures, and malformed outputs all count per the rules above (and that exactly one malformed correction is free).
- **Audit events:** every Orchestrator turn fires `orchestrator_step`; every Policy decision fires `policy_decision`; confirm these are wired and visible in the Job trace.

If you change any of this behavior in a way that would surprise the next reader, **write a new log entry that says so** — do not edit an earlier one.

---

## Cross-references

- Capabilities (what the Orchestrator can propose): `docs/capabilities.md`
- Policy rules the proposals pass through: `docs/security.md` § Deterministic Policy
- Orchestrator model selection and benchmark: `docs/models.md`, `docs/testing.md`
- Demo sequences that exercise this loop end-to-end: `docs/demo.md`
- AI coding-agent operating procedure and the log rule itself: `../AGENTS.md`
