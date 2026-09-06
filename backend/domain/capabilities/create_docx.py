"""
create_docx capability executor (Task 14.a).

Validates input against docs/capabilities.md#create_docx exactly (no added
fields — AGENTS.md §6 rule 11), renders via domain/artifacts/docx_renderer.py,
validates output, and emits the artifact_created audit event. Called only by
the Job Manager after a Policy `allow` (docs/backend.md "Capability Executor
layer"; docs/agent.md "Policy interaction").
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.domain.artifacts.docx_renderer import DocxRenderError, render_docx
from backend.domain.audit.events import emit
from backend.utils.ids import new_id

__all__ = [
    "CapabilityValidationError",
    "validate_input",
    "validate_output",
    "execute_create_docx",
]


class CapabilityValidationError(Exception):
    """Invalid input or output shape.

    Caller (Job Manager) converts this into a failed CapabilityExecution
    result — the Orchestrator can correct its arguments and retry (a new
    proposal, counts against the step limit per agent.md). Never rendered:
    validation happens before render_docx() is called.
    """


def _validate_iso8601(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise CapabilityValidationError(f"{field_name} must be an ISO-8601 string, got: {value!r}")
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise CapabilityValidationError(f"{field_name} is not valid ISO-8601: {value!r}") from exc


def validate_input(arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate `arguments` against docs/capabilities.md#create_docx exactly.

    Schema: {title: string, sections: [{heading: string, body: string}],
    metadata: {prepared_by: string, date: iso8601}}. No extra top-level or
    nested fields are permitted (AGENTS.md §6 rule 11) — reject rather than
    silently ignore, since an ignored extra field is exactly the kind of
    silent contract drift the rule exists to prevent.
    """
    if not isinstance(arguments, dict):
        raise CapabilityValidationError("arguments must be an object")

    allowed_top = {"title", "sections", "metadata"}
    extra_top = set(arguments.keys()) - allowed_top
    if extra_top:
        raise CapabilityValidationError(f"unexpected field(s): {sorted(extra_top)}")

    title = arguments.get("title")
    if not isinstance(title, str) or not title.strip():
        raise CapabilityValidationError("'title' is required and must be a non-empty string")

    sections = arguments.get("sections")
    if not isinstance(sections, list) or len(sections) == 0:
        raise CapabilityValidationError("'sections' is required and must be a non-empty list")

    for i, section in enumerate(sections):
        if not isinstance(section, dict):
            raise CapabilityValidationError(f"sections[{i}] must be an object")
        extra_section = set(section.keys()) - {"heading", "body"}
        if extra_section:
            raise CapabilityValidationError(f"sections[{i}] has unexpected field(s): {sorted(extra_section)}")
        if not isinstance(section.get("heading"), str) or not section["heading"].strip():
            raise CapabilityValidationError(f"sections[{i}].heading is required and must be a non-empty string")
        if not isinstance(section.get("body"), str):
            raise CapabilityValidationError(f"sections[{i}].body is required and must be a string")

    metadata = arguments.get("metadata")
    if not isinstance(metadata, dict):
        raise CapabilityValidationError("'metadata' is required and must be an object")
    extra_metadata = set(metadata.keys()) - {"prepared_by", "date"}
    if extra_metadata:
        raise CapabilityValidationError(f"metadata has unexpected field(s): {sorted(extra_metadata)}")
    if not isinstance(metadata.get("prepared_by"), str) or not metadata["prepared_by"].strip():
        raise CapabilityValidationError("metadata.prepared_by is required and must be a non-empty string")
    _validate_iso8601(metadata.get("date"), "metadata.date")

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


async def execute_create_docx(job_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
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
            before render_docx() runs for input errors — no file is ever
            written for an invalid payload (docs/artifacts.md "Validation").
        DocxRenderError: rendering or Artifact-row persistence failure,
            propagated from docx_renderer.render_docx.
    """
    validated_input = validate_input(arguments)

    artifact_id = new_id()
    result = render_docx(artifact_id=artifact_id, job_id=job_id, payload=validated_input)

    validated_output = validate_output(result)

    await emit(
        "artifact_created",
        "artifact_executor",
        {
            "artifact_id": validated_output["artifact_id"],
            "type": "docx",
            "filename": validated_output["filename"],
        },
        job_id=job_id,
    )

    return validated_output