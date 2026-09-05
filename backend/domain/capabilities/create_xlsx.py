"""
create_xlsx capability executor.

Implements the contract defined in docs/capabilities.md.
"""

from backend.models.schemas import CreateXlsxInput, CreateXlsxOutput


async def execute_create_xlsx(input_data: CreateXlsxInput) -> CreateXlsxOutput:
    """
    Execute the create_xlsx capability.

    Args:
        input_data: Validated input containing title and sheets.

    Returns:
        Validated output with artifact_id and filename.

    Raises:
        NotImplementedError: This capability is not yet implemented.
    """
    raise NotImplementedError("create_xlsx executor not yet implemented (Task 14.b)")