"""
Agent (Orchestrator) — Hand-rolled agent loop step function.

Implements the reasoning step per docs/agent.md:
- Assembles context (system prompt + conversation history + tool results)
- Calls the reasoning model via ModelClient (dependency injection)
- Parses the model output via proposal_parser
- Emits orchestrator_step audit event every turn
- Returns ParseResult for the Job Manager to act on

The Orchestrator has NO execution rights (AGENTS.md §6 rule 1).
It proposes; the only path from its output to an effect is Policy → Job Manager → Executor.

ZERO FORBIDDEN IMPORTS:
This module MUST NOT import from:
- domain/model_runtime (Task 8 — injected via ModelClient protocol)
- domain/policy (Task 6 — read-only via StepOutcome, not imported here)
- domain/capabilities/<executor files> (Tasks 11-14)
- domain/sandbox, domain/rag, domain/artifacts, domain/document_processing

Allowed imports:
- domain/capabilities/registry.py (read-only, Task 7)
- domain/audit/events.py (emit, Task 4)
"""

import json
from typing import Any, Dict, List

from backend.domain.audit.events import emit
from backend.domain.capabilities.registry import CapabilityRegistry
from backend.domain.orchestrator.proposal_parser import parse_proposal
from backend.domain.orchestrator.prompt_builder import build_system_prompt
from backend.models.schemas import (
    GenerationResult,
    ModelClient,
    OrchestratorContext,
    ParseResult,
    StepOutcome,
)


async def step(
    context: OrchestratorContext,
    model_client: ModelClient,
    registry: CapabilityRegistry,
    max_job_steps: int,
) -> ParseResult:
    """
    Execute one Orchestrator reasoning step.

    This function is stateless per turn — it does NOT own step counters or
    malformed retry flags. The Job Manager (Task 15) owns that state and
    calls classify_step() with its own counters.

    Args:
        context: The OrchestratorContext for this turn (conversation history, tool results).
        model_client: The model client for calling the reasoning model (injected).
        registry: The Capability Registry for validating proposals.
        max_job_steps: Maximum steps per Job, sourced from settings.policy.max_job_steps.

    Returns:
        ParseResult with kind="proposal" or kind="malformed".
    """
    # 1. Assemble the full prompt for the model
    prompt = _assemble_prompt(context, registry, max_job_steps)

    # 2. Call the reasoning model
    #    Orchestrator always runs on the "reasoning" resource type per docs/agent.md
    generation_result = await model_client.generate("reasoning", prompt)

    # 3. Parse the model output
    parse_result = parse_proposal(generation_result.text, registry)

    # 4. Emit orchestrator_step audit event (every turn, per docs/audit.md)
    action = "unknown"
    raw_proposal: Dict[str, Any] = {}
    if parse_result.kind == "proposal" and parse_result.proposal is not None:
        action = parse_result.proposal.action
        raw_proposal = parse_result.proposal.model_dump()
    else:
        action = "malformed"
        raw_proposal = {"error": parse_result.error}

    await emit(
        event_type="orchestrator_step",
        component="orchestrator",
        payload={
            "action": action,
            "raw_proposal": raw_proposal,
        },
        job_id=context.job_id,
    )

    return parse_result


def classify_step(
    result: ParseResult,
    malformed_retry_used: bool,
) -> StepOutcome:
    """
    Classify a parsed step into its step-limit and termination behavior.

    This is a PURE FUNCTION — no side effects, no state. The Job Manager (Task 15)
    owns the step counter and malformed_retry_used flag; this function tells it
    what to do with them.

    Per docs/agent.md:
    - Malformed output with retry_used=False: counts_against_limit=False (free turn)
    - Malformed output with retry_used=True: counts_against_limit=True
    - Valid respond with non-empty content: terminal=True
    - Valid invoke_capability: not terminal, counts against limit
    - Denied tool results are handled by the Job Manager, not here

    Args:
        result: The ParseResult from parse_proposal().
        malformed_retry_used: Whether the Job Manager has already given one
            free corrective turn for malformed output in this Job.

    Returns:
        StepOutcome with counts_against_limit and terminal flags.
    """
    if result.kind == "malformed":
        if not malformed_retry_used:
            # One free corrective turn — does NOT count against limit
            return StepOutcome(
                counts_against_limit=False,
                terminal=False,
            )
        else:
            # Free turn already used — this counts against limit
            return StepOutcome(
                counts_against_limit=True,
                terminal=False,
            )

    # result.kind == "proposal"
    proposal = result.proposal
    if proposal is None:
        # Should not happen if kind="proposal", but defensive
        return StepOutcome(
            counts_against_limit=True,
            terminal=False,
        )

    if proposal.action == "respond":
        # respond with non-empty content terminates the Job
        return StepOutcome(
            counts_against_limit=False,
            terminal=True,
            terminal_reason=None,
        )

    if proposal.action == "invoke_capability":
        # Capability invocation counts against limit, does not terminate
        return StepOutcome(
            counts_against_limit=True,
            terminal=False,
        )

    # Unknown action — should not reach here if parser is correct
    return StepOutcome(
        counts_against_limit=True,
        terminal=False,
    )


def _assemble_prompt(
    context: OrchestratorContext,
    registry: CapabilityRegistry,
    max_job_steps: int,
) -> str:
    """
    Assemble the full prompt for the reasoning model from the context.

    Per docs/agent.md "Context construction":
    - System prompt (capability list + rules, built from the Registry)
    - Conversation history for this conversation_id
    - This Job's prior tool results, in order
    - Malformed error corrective context (if any)
    """
    parts: List[str] = []

    # System prompt (built fresh from the Registry each turn)
    parts.append(build_system_prompt(registry, max_job_steps))

    # Conversation history
    if context.conversation_history:
        parts.append("\n## Conversation History\n")
        for msg in context.conversation_history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")

    # Tool results
    if context.tool_results:
        parts.append("\n## Tool Results\n")
        for tr in context.tool_results:
            status = tr.status
            capability = tr.capability
            result = tr.result

            parts.append(f"### {capability} (status: {status})")
            if status == "succeeded":
                parts.append(f"Result: {json.dumps(result, separators=(',', ':'))}")
            elif status == "failed":
                parts.append(f"Failed: {json.dumps(result, separators=(',', ':'))}")
            elif status == "denied":
                parts.append(f"Denied: {json.dumps(result, separators=(',', ':'))}")

    # Malformed error corrective context
    if context.malformed_error:
        parts.append(f"\n## Previous Step Error\n")
        parts.append(f"Your previous output was malformed: {context.malformed_error}")
        parts.append("Please correct your output and respond with exactly one JSON object.")

    return "\n".join(parts)
