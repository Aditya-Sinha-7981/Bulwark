"""
create_xlsx capability executor.

Implements the contract defined in docs/capabilities.md.
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
    """Invalid input or output shape.

    Caller (Job Manager) converts this into a failed CapabilityExecution
    result — the Orchestrator can correct its arguments and retry (a new
    proposal, counts against the step limit per agent.md). Never rendered:
    validation happens before render_xlsx() is called.
    """


def validate_input(arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate `arguments` against docs/capabilities.md#create_xlsx exactly.

    Schema: {title: string, sheets: [{name: string, headers: [string], rows: [[cell, ...]]}]}.
    No extra top-level or nested fields are permitted (AGENTS.md §6 rule 11) —
    reject rather than silently ignore, since an ignored extra field is exactly
    the kind of silent contract drift the rule exists to prevent.

    Duplicate sheet names are rejected as invalid (failed result, no file) —
    never silently renamed or de-duplicated. Per task spec §7 Error Handling.
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

    seen_sheet_names: set[str] = set()

    for i, sheet in enumerate(sheets):
        if not isinstance(sheet, dict):
            raise CapabilityValidationError(f"sheets[{i}] must be an object")

        allowed_sheet = {"name", "headers", "rows"}
        extra_sheet = set(sheet.keys()) - allowed_sheet
        if extra_sheet:
            raise CapabilityValidationError(
                f"sheets[{i}] has unexpected field(s): {sorted(extra_sheet)}"
            )

        name = sheet.get("name")
        if not isinstance(name, str) or not name.strip():
            raise CapabilityValidationError(
                f"sheets[{i}].name is required and must be a non-empty string"
            )

        # Reject duplicate sheet names
        if name in seen_sheet_names:
            raise CapabilityValidationError(
                f"sheets[{i}].name '{name}' is a duplicate; sheet names must be unique"
            )
        seen_sheet_names.add(name)

        headers = sheet.get("headers")
        if not isinstance(headers, list) or len(headers) == 0:
            raise CapabilityValidationError(
                f"sheets[{i}].headers is required and must be a non-empty list"
            )
        for j, header in enumerate(headers):
            if not isinstance(header, str):
                raise CapabilityValidationError(
                    f"sheets[{i}].headers[{j}] must be a string"
                )

        rows = sheet.get("rows")
        if not isinstance(rows, list):
            raise CapabilityValidationError(
                f"sheets[{i}].rows is required and must be a list"
            )
        for j, row in enumerate(rows):
            if not isinstance(row, list):
                raise CapabilityValidationError(
                    f"sheets[{i}].rows[{j}] must be a list"
                )

    return arguments


def validate_output(result: dict[str, Any]) -> dict[str, Any]:
    """Validate the {artifact_id, filename} output shape."""
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

    Args:
        job_id: the Job this invocation belongs to (threaded into the
            Artifact row and the artifact_created event's job_id).
        arguments: raw arguments from the Orchestrator's invoke_capability
            proposal — validated here before anything is rendered.

    Returns:
        {"artifact_id": str, "filename": str}.

    Raises:
        CapabilityValidationError: invalid input or output shape. Raised
            before render_xlsx() runs for input errors — no file is ever
            written for an invalid payload (docs/artifacts.md "Validation").
        XlsxRenderError: rendering or Artifact-row persistence failure,
            propagated from xlsx_renderer.render_xlsx.
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