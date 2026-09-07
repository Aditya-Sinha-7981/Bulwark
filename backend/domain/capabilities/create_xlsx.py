"""
create_xlsx capability executor (Task 14.b).

Validates input against docs/capabilities.md#create_xlsx exactly, renders
via domain/artifacts/xlsx_renderer.py, validates output, and emits the
artifact_created audit event. Mirrors create_docx.py's structure exactly —
same validation discipline, same emit() call shape, different schema.
"""
from __future__ import annotations

from typing import Any

from backend.domain.artifacts.xlsx_renderer import XlsxRenderError, render_xlsx
from backend.domain.audit.events import emit
from backend.utils.ids import new_id

__all__ = [
    "CapabilityValidationError",
    "validate_input",
    "validate_output",
    "execute_create_xlsx",
]


class CapabilityValidationError(Exception):
    """Invalid input or output shape — see create_docx.py's identical class
    for the full rationale (mirrors it exactly for consistency)."""


def validate_input(arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate `arguments` against docs/capabilities.md#create_xlsx exactly.

    Schema: {title: string, sheets: [{name: string, headers: [string],
    rows: [[cell, ...]]}]}. No extra top-level or nested fields permitted
    (AGENTS.md §6 rule 11), same discipline as create_docx.py.

    Error handling per docs/capabilities.md#create_xlsx:
    - Duplicate sheet names: reject as invalid (no file written)
    """
    if not isinstance(arguments, dict):
        raise CapabilityValidationError("arguments must be an object")

    allowed_top = {"title", "sheets"}
    extra_top = set(arguments.keys()) - allowed_top
    if extra_top:
        raise CapabilityValidationError(f"unexpected field(s): {sorted(extra_top)}")

    title = arguments.get("title")
    if not isinstance(title, str) or not title.strip():
        raise CapabilityValidationError("'title' is required and must be a non-empty string")

    sheets = arguments.get("sheets")
    if not isinstance(sheets, list) or len(sheets) == 0:
        raise CapabilityValidationError("'sheets' is required and must be a non-empty list")

    # Check for duplicate sheet names
    sheet_names = []
    for i, sheet in enumerate(sheets):
        if not isinstance(sheet, dict):
            raise CapabilityValidationError(f"sheets[{i}] must be an object")

        extra_sheet = set(sheet.keys()) - {"name", "headers", "rows"}
        if extra_sheet:
            raise CapabilityValidationError(f"sheets[{i}] has unexpected field(s): {sorted(extra_sheet)}")

        name = sheet.get("name")
        if not isinstance(name, str) or not name.strip():
            raise CapabilityValidationError(f"sheets[{i}].name is required and must be a non-empty string")

        if name in sheet_names:
            raise CapabilityValidationError(f"duplicate sheet name: '{name}'")
        sheet_names.append(name)

        headers = sheet.get("headers")
        if not isinstance(headers, list) or len(headers) == 0:
            raise CapabilityValidationError(f"sheets[{i}].headers is required and must be a non-empty list")

        for j, header in enumerate(headers):
            if not isinstance(header, str):
                raise CapabilityValidationError(f"sheets[{i}].headers[{j}] must be a string")

        rows = sheet.get("rows")
        if not isinstance(rows, list):
            raise CapabilityValidationError(f"sheets[{i}].rows must be a list (may be empty for a headers-only sheet)")

        for j, row in enumerate(rows):
            if not isinstance(row, list):
                raise CapabilityValidationError(f"sheets[{i}].rows[{j}] must be a list")

    return arguments


def validate_output(result: dict[str, Any]) -> dict[str, Any]:
    """Identical output contract to create_docx.py: {artifact_id, filename}."""
    allowed = {"artifact_id", "filename"}
    extra = set(result.keys()) - allowed
    if extra:
        raise CapabilityValidationError(f"unexpected output field(s): {sorted(extra)}")
    if not isinstance(result.get("artifact_id"), str) or not result["artifact_id"]:
        raise CapabilityValidationError("output missing a valid 'artifact_id'")
    if not isinstance(result.get("filename"), str) or not result["filename"]:
        raise CapabilityValidationError("output missing a valid 'filename'")
    return result


async def execute_create_xlsx(job_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Capability executor entry point: validate -> render -> validate -> emit.

    Mirrors create_docx.py's execute_create_docx exactly in structure.

    Args:
        job_id: the Job this invocation belongs to.
        arguments: raw arguments from the Orchestrator's invoke_capability proposal.

    Returns:
        {"artifact_id": str, "filename": str}.

    Raises:
        CapabilityValidationError: invalid input or output shape.
        XlsxRenderError: rendering or Artifact-row persistence failure.
    """
    validated_input = validate_input(arguments)

    artifact_id = new_id()
    result = render_xlsx(artifact_id=artifact_id, job_id=job_id, payload=validated_input)

    validated_output = validate_output(result)

    await emit(
        "artifact_created",
        "artifact_executor",
        {
            "artifact_id": validated_output["artifact_id"],
            "type": "xlsx",
            "filename": validated_output["filename"],
        },
        job_id=job_id,
    )

    return validated_output