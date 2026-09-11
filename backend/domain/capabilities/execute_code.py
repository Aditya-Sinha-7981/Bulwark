"""execute_code capability executor (Task 13).

Implements the contract defined in docs/capabilities.md#execute_code.
Validates input, delegates to docker_executor, returns raw result with
candidate output filenames (not artifact_ids — Task 15 owns that conversion).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from backend.config import settings
from domain.capabilities.registry import get_registry
from backend.domain.sandbox.docker_executor import DockerUnavailableError, run_in_sandbox, SandboxResult
from backend.models.schemas import ExecuteCodeInput, ExecuteCodeOutput
from backend.utils.ids import new_id
from backend.utils.paths import uploads_path


class CapabilityValidationError(Exception):
    """Invalid input or output shape for execute_code capability."""


def validate_input(arguments: dict[str, Any]) -> ExecuteCodeInput:
    """Validate arguments against docs/capabilities.md#execute_code input schema."""
    registry = get_registry(settings.capabilities)
    try:
        validated = registry.validate_input("execute_code", arguments)
        # Additional validation: code must be non-empty
        if not validated.code or not validated.code.strip():
            raise CapabilityValidationError("code must be non-empty")
        return validated  # type: ignore[return-value]
    except CapabilityValidationError:
        raise
    except Exception as e:
        raise CapabilityValidationError(f"execute_code input validation failed: {e}")


def validate_output(result: dict[str, Any]) -> ExecuteCodeOutput:
    """Validate result against docs/capabilities.md#execute_code output schema."""
    registry = get_registry(settings.capabilities)
    try:
        validated = registry.validate_output("execute_code", result)
        return validated  # type: ignore[return-value]
    except Exception as e:
        raise CapabilityValidationError(f"execute_code output validation failed: {e}")


async def execute_execute_code(
    job_id: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """
    Capability executor entry point for execute_code.

    Args:
        job_id: The Job this invocation belongs to
        arguments: Raw arguments from Orchestrator's invoke_capability proposal

    Returns:
        Raw result: {stdout, stderr, exit_code, timed_out, output_files: [<raw filename>, ...]}
        Note: output_files are candidate filenames from sandbox output dir,
              NOT artifact_ids — Task 15 converts these to Artifact records.

    Raises:
        CapabilityValidationError: Invalid input or output shape
    """
    # Validate input
    validated_input = validate_input(arguments)

    # Resolve input_files (document_ids) to actual file paths
    input_files: list[str] = []
    for doc_id in validated_input.input_files:
        # Try to find the uploaded file with common extensions
        found = False
        for ext in [".pdf", ".png", ".jpg", ".jpeg", ".txt", ".md", ""]:
            try:
                file_path = uploads_path(doc_id, ext)
                if file_path.exists():
                    input_files.append(str(file_path))
                    found = True
                    break
            except Exception:
                continue
        if not found:
            # File not found - will surface as FileNotFoundError inside the sandbox
            input_files.append(doc_id)

    # Create a temporary sandbox root for this execution
    with tempfile.TemporaryDirectory(prefix="bulwark-sbx-") as tmp_dir:
        sandbox_root = Path(tmp_dir)

        # Execute in sandbox
        try:
            sandbox_result: SandboxResult = run_in_sandbox(
                code=validated_input.code,
                input_files=input_files,
                sandbox_root=sandbox_root,
                timeout_seconds=settings.capabilities.execute_code.timeout_seconds,
                max_output_bytes=settings.capabilities.execute_code.max_output_bytes,
                cpu_limit=settings.capabilities.execute_code.cpu_limit,
                memory_limit_mb=settings.capabilities.execute_code.memory_limit_mb,
            )
        except DockerUnavailableError as e:
            # Docker unavailable - return structured failed result (never raise)
            sandbox_result = SandboxResult(
                execution_id=new_id(),
                exit_code=None,
                stdout="",
                stderr=f"docker_unavailable: {e}",
                timed_out=False,
                output_files=[],
            )
        except Exception as e:
            # Other execution errors - return structured failed result
            sandbox_result = SandboxResult(
                execution_id=new_id(),
                exit_code=-1,
                stdout="",
                stderr=f"execution_error: {e}",
                timed_out=False,
                output_files=[],
            )

        # Prepare raw result dict
        raw_result = {
            "stdout": sandbox_result.stdout,
            "stderr": sandbox_result.stderr,
            "exit_code": sandbox_result.exit_code if sandbox_result.exit_code is not None else -1,
            "timed_out": sandbox_result.timed_out,
            "output_files": sandbox_result.output_files,
        }

    # Validate output shape (output_files are raw filenames, not artifact_ids)
    # The registry's ExecuteCodeOutput schema expects List[str] for output_files,
    # which matches our raw filenames — Task 15 will swap for artifact_ids later.
    validated_output = validate_output(raw_result)

    return {
        "stdout": validated_output.stdout,
        "stderr": validated_output.stderr,
        "exit_code": validated_output.exit_code,
        "timed_out": validated_output.timed_out,
        "output_files": validated_output.output_files,
    }


__all__ = [
    "CapabilityValidationError",
    "validate_input",
    "validate_output",
    "execute_execute_code",
]