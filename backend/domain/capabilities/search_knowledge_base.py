"""search_knowledge_base capability executor (Task 12.b).

Implements the contract defined in `docs/capabilities.md#search_knowledge_base`.
`validate_input` -> `domain.rag.retrieval.retrieve()` -> `validate_output`.

Called only by the Job Manager after an explicit Orchestrator
`search_knowledge_base` proposal has passed Policy (Task 15) — this module
never triggers retrieval on its own (ADR-03, `AGENTS.md` §6 rule 5).
"""

from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.domain.capabilities.registry import get_registry
from backend.domain.rag.retrieval import RetrievalError, retrieve
from backend.models.schemas import SearchKnowledgeBaseInput, SearchKnowledgeBaseOutput


class CapabilityValidationError(Exception):
    """Invalid input or output shape for the search_knowledge_base capability."""


def validate_input(arguments: dict[str, Any]) -> SearchKnowledgeBaseInput:
    """Validate arguments against docs/capabilities.md#search_knowledge_base input schema."""
    registry = get_registry(settings.capabilities)
    try:
        validated = registry.validate_input("search_knowledge_base", arguments)
        if not validated.query or not validated.query.strip():
            raise CapabilityValidationError("query must be non-empty")
        return validated  # type: ignore[return-value]
    except CapabilityValidationError:
        raise
    except Exception as e:
        raise CapabilityValidationError(f"search_knowledge_base input validation failed: {e}")


def validate_output(result: dict[str, Any]) -> SearchKnowledgeBaseOutput:
    """Validate result against docs/capabilities.md#search_knowledge_base output schema."""
    registry = get_registry(settings.capabilities)
    try:
        validated = registry.validate_output("search_knowledge_base", result)
        return validated  # type: ignore[return-value]
    except Exception as e:
        raise CapabilityValidationError(f"search_knowledge_base output validation failed: {e}")


async def execute_search_knowledge_base(
    job_id: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """
    Capability executor entry point for search_knowledge_base.

    Args:
        job_id: The Job this invocation belongs to.
        arguments: Raw arguments from the Orchestrator's invoke_capability proposal.

    Returns:
        {results: [{kb_document_id, title, chunk_text, score}, ...]} — possibly
        empty. An empty list is a successful, honest "no grounding found"
        result (docs/rag.md "Retrieval failure"), not an error.

    Raises:
        CapabilityValidationError: Invalid input or output shape.
        RetrievalError: Retrieval itself failed — embedding-model failure,
            Chroma query error, or an empty/uninitialised knowledge_base
            collection. Distinct from a genuine empty result; the caller
            (Task 15's dispatch) must surface this as status: failed, not
            results: [].
    """
    validated_input = validate_input(arguments)

    hits = await retrieve(
        query=validated_input.query,
        top_k=validated_input.top_k,
        job_id=job_id,
    )

    raw_result = {"results": hits}
    validated_output = validate_output(raw_result)

    return {
        "results": [r.model_dump(mode="json") for r in validated_output.results],
    }
