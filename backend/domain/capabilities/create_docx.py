"""
create_docx capability executor.

Implements the contract defined in docs/capabilities.md.
"""

from backend.models.schemas import CreateDocxInput, CreateDocxOutput


async def execute_create_docx(input_data: CreateDocxInput) -> CreateDocxOutput:
    """
    Execute the create_docx capability.

    Args:
        input_data: Validated input containing title, sections, and metadata.

    Returns:
        Validated output with artifact_id and filename.

    Raises:
        NotImplementedError: This capability is not yet implemented.
    """
    raise NotImplementedError("create_docx executor not yet implemented (Task 14.a)")