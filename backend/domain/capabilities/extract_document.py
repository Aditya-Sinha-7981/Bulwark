"""
extract_document capability executor.

Implements the contract defined in docs/capabilities.md.
"""

from backend.models.schemas import ExtractDocumentInput, ExtractDocumentOutput


async def execute_extract_document(input_data: ExtractDocumentInput) -> ExtractDocumentOutput:
    """
    Execute the extract_document capability.

    Args:
        input_data: Validated input containing document_id.

    Returns:
        Validated output with extracted_text, extraction_method, confidence, warnings.

    Raises:
        NotImplementedError: This capability is not yet implemented.
    """
    raise NotImplementedError("extract_document executor not yet implemented (Task 11)")