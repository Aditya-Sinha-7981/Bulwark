"""
Proposal Parser — Parse raw model output into validated proposals.

Parses the Orchestrator model's raw JSON output into exactly one of the two
valid proposal shapes (invoke_capability, respond) or classifies it as malformed.
Validates capability names against the Registry and arguments against input schemas.

Per docs/agent.md: unknown capability names are malformed (NOT "hallucinated
capability" guesses — rejected before Policy, same corrective-turn allowance).
"""

import json
from typing import Any, Dict

from backend.domain.capabilities.registry import CapabilityRegistry
from backend.models.schemas import (
    InvokeCapabilityProposal,
    ParseResult,
    Proposal,
    RespondProposal,
)
from backend.domain.capabilities.registry import UnknownCapabilityError


def parse_proposal(raw_output: str, registry: CapabilityRegistry) -> ParseResult:
    """
    Parse raw model output into a validated proposal or classify as malformed.

    Args:
        raw_output: The raw string output from the reasoning model.
        registry: The Capability Registry for validating capability names and arguments.

    Returns:
        ParseResult with kind="proposal" (proposal set) or kind="malformed" (error set).
    """
    # Step 1: Try JSON parsing
    try:
        parsed = json.loads(raw_output)
    except (json.JSONDecodeError, ValueError) as e:
        return ParseResult(kind="malformed", error=f"non-JSON output: {e}")

    if not isinstance(parsed, dict):
        return ParseResult(kind="malformed", error="output is not a JSON object")

    # Step 2: Check action field exists
    action = parsed.get("action")
    if action is None:
        return ParseResult(kind="malformed", error="missing required 'action' field")

    # Step 3: Dispatch on action type
    if action == "invoke_capability":
        return _parse_invoke_capability(parsed, registry)
    elif action == "respond":
        return _parse_respond(parsed)
    else:
        return ParseResult(kind="malformed", error=f"unknown action: {action!r}")


def _parse_invoke_capability(parsed: Dict[str, Any], registry: CapabilityRegistry) -> ParseResult:
    """Parse and validate an invoke_capability proposal."""
    capability = parsed.get("capability")
    arguments = parsed.get("arguments")

    if capability is None:
        return ParseResult(kind="malformed", error="invoke_capability missing 'capability' field")

    if arguments is None:
        return ParseResult(kind="malformed", error=f"invoke_capability '{capability}' missing 'arguments' field")

    if not isinstance(arguments, dict):
        return ParseResult(kind="malformed", error=f"invoke_capability '{capability}' arguments must be a JSON object")

    # Check capability name exists in Registry (unknown = malformed per docs/agent.md)
    try:
        registry.get(capability)
    except UnknownCapabilityError:
        return ParseResult(kind="malformed", error=f"unknown capability: {capability!r}")

    # Validate arguments against the capability's input schema
    try:
        registry.validate_input(capability, arguments)
    except Exception as e:
        return ParseResult(kind="malformed", error=f"invalid arguments for '{capability}': {e}")

    # Build validated proposal
    try:
        proposal = InvokeCapabilityProposal(
            action="invoke_capability",
            capability=capability,
            arguments=arguments,
        )
    except Exception as e:
        return ParseResult(kind="malformed", error=f"proposal validation failed: {e}")

    return ParseResult(kind="proposal", proposal=proposal)


def _parse_respond(parsed: Dict[str, Any]) -> ParseResult:
    """Parse and validate a respond proposal."""
    content = parsed.get("content")

    if content is None:
        return ParseResult(kind="malformed", error="respond missing 'content' field")

    if not isinstance(content, str):
        return ParseResult(kind="malformed", error="respond 'content' must be a string")

    if not content.strip():
        # Empty content is malformed per docs/agent.md — must not terminate
        return ParseResult(kind="malformed", error="empty respond content")

    try:
        proposal = RespondProposal(action="respond", content=content)
    except Exception as e:
        return ParseResult(kind="malformed", error=f"proposal validation failed: {e}")

    return ParseResult(kind="proposal", proposal=proposal)
