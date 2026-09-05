"""
search_knowledge_base capability executor.

Implements the contract defined in docs/capabilities.md.
"""

from backend.models.schemas import SearchKnowledgeBaseInput, SearchKnowledgeBaseOutput


async def execute_search_knowledge_base(input_data: SearchKnowledgeBaseInput) -> SearchKnowledgeBaseOutput:
    """
    Execute the search_knowledge_base capability.

    Args:
        input_data: Validated input containing query and optional top_k.

    Returns:
        Validated output with results list.

    Raises:
        NotImplementedError: This capability is not yet implemented.
    """
    raise NotImplementedError("search_knowledge_base executor not yet implemented (Task 12.b)")