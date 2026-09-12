"""generate_code capability executor (Task 13).

Implements the contract defined in docs/capabilities.md#generate_code.
Validates input, calls Model Runtime `code_generation` resource,
shapes output, validates output. No filesystem, no network, no execution.
"""

from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.domain.capabilities.registry import get_registry
import re

from backend.domain.model_runtime.runtime import runtime as model_runtime
from backend.models.schemas import GenerateCodeInput, GenerateCodeOutput

_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


class CapabilityValidationError(Exception):
    """Invalid input or output shape for generate_code capability."""


def _build_generation_prompt(task_description: str) -> str:
    """Build the prompt for the code_generation model."""
    return f"""You are a code generation assistant. Produce a Python script that solves the described task.

Task: {task_description}

Requirements:
- Output only the Python code and a brief explanation
- Do not include any markdown formatting, comments about the task, or conversational text
- The code must be self-contained and runnable with Python standard library only
- No external dependencies, no network calls, no file I/O outside /workspace/output
- Print the result to stdout

Format your response as:
CODE:
<your python code here>
EXPLANATION:
<your brief explanation here>"""


def _extract_fenced_code(code: str) -> str:
    """Strip markdown fences the model may embed inside its code output."""
    if "```" not in code:
        return code.strip()
    blocks = _FENCE_RE.findall(code)
    if blocks:
        return "\n\n".join(block.strip() for block in blocks)
    # Unbalanced fences — drop the markers themselves
    return code.replace("```python", "").replace("```py", "").replace("```", "").strip()


def _parse_model_response(response_text: str) -> tuple[str, str]:
    """Parse the model response into code and explanation.

    Handles the instructed CODE:/EXPLANATION: format, and markdown-fenced
    responses — coder models frequently emit ```python blocks despite the
    format instructions (observed live 2026-09-12 on qwen2.5-coder:7b).
    """
    code = ""
    explanation = ""

    lines = response_text.strip().split("\n")
    in_code = False
    in_explanation = False
    code_lines = []
    explanation_lines = []

    for line in lines:
        if line.strip() == "CODE:":
            in_code = True
            in_explanation = False
            continue
        elif line.strip() == "EXPLANATION:":
            in_code = False
            in_explanation = True
            continue

        if in_code:
            code_lines.append(line)
        elif in_explanation:
            explanation_lines.append(line)

    code = _extract_fenced_code("\n".join(code_lines))
    explanation = "\n".join(explanation_lines).strip()

    # Fallback: no CODE: marker — take fenced block(s) as code, surrounding
    # prose as explanation
    if not code:
        fenced = _FENCE_RE.findall(response_text)
        if fenced:
            code = "\n\n".join(block.strip() for block in fenced)
            prose = _FENCE_RE.sub("", response_text).strip()
            prose = prose.replace("EXPLANATION:", "").strip()
            explanation = prose or "Generated code for the described task."
        else:
            code = response_text.strip()
            explanation = "Generated code for the described task."

    if not code:
        code = response_text.strip()
        explanation = "Generated code for the described task."

    return code, explanation


async def _call_model_runtime(prompt: str, job_id: str | None = None) -> str:
    """Call the Model Runtime's `code_generation` resource (real Ollama call).

    Emits `model_invoked` audit events with the job attribution
    (`docs/audit.md`), and the call resolves through the Resource/Model
    Configuration Registry — no model names here (AGENTS.md §6 rule 3).
    """
    result = await model_runtime.generate("code_generation", prompt, job_id=job_id)
    return result.text


def validate_input(arguments: dict[str, Any]) -> GenerateCodeInput:
    """Validate arguments against docs/capabilities.md#generate_code input schema."""
    registry = get_registry(settings.capabilities)
    try:
        validated = registry.validate_input("generate_code", arguments)
        # Additional validation: task_description must be non-empty
        if not validated.task_description or not validated.task_description.strip():
            raise CapabilityValidationError("task_description must be non-empty")
        return validated  # type: ignore[return-value]
    except CapabilityValidationError:
        raise
    except Exception as e:
        raise CapabilityValidationError(f"generate_code input validation failed: {e}")


def validate_output(result: dict[str, Any]) -> GenerateCodeOutput:
    """Validate result against docs/capabilities.md#generate_code output schema."""
    registry = get_registry(settings.capabilities)
    try:
        validated = registry.validate_output("generate_code", result)
        # Additional validation: code must be non-empty
        if not validated.code or not validated.code.strip():
            raise CapabilityValidationError("code must be non-empty")
        return validated  # type: ignore[return-value]
    except CapabilityValidationError:
        raise
    except Exception as e:
        raise CapabilityValidationError(f"generate_code output validation failed: {e}")


async def execute_generate_code(
    job_id: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """
    Capability executor entry point for generate_code.

    Args:
        job_id: The Job this invocation belongs to
        arguments: Raw arguments from Orchestrator's invoke_capability proposal

    Returns:
        {code: str, language: "python", explanation: str}

    Raises:
        CapabilityValidationError: Invalid input or output shape, or malformed/empty generation
    """
    # Validate input
    validated_input = validate_input(arguments)

    # Build prompt and call Model Runtime
    prompt = _build_generation_prompt(validated_input.task_description)

    try:
        model_response = await _call_model_runtime(prompt, job_id=job_id)
    except Exception as e:
        raise CapabilityValidationError(f"Model Runtime call failed: {e}")

    # Parse response
    code, explanation = _parse_model_response(model_response)

    if not code or not code.strip():
        raise CapabilityValidationError("Model returned empty code")

    # Shape output
    raw_result = {
        "code": code,
        "language": "python",
        "explanation": explanation,
    }

    # Validate output
    validated_output = validate_output(raw_result)

    return {
        "code": validated_output.code,
        "language": validated_output.language,
        "explanation": validated_output.explanation,
    }


__all__ = [
    "CapabilityValidationError",
    "validate_input",
    "validate_output",
    "execute_generate_code",
]