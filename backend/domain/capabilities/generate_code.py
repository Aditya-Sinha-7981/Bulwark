"""generate_code capability executor (Task 13).

Implements the contract defined in docs/capabilities.md#generate_code.
Validates input, calls Model Runtime `code_generation` resource,
shapes output, validates output. No filesystem, no network, no execution.

NOTE: The Model Runtime `code_generation` interface (backend/domain/model_runtime/runtime.py)
is not yet implemented (Task 8). This executor uses a stub that can be swapped
when the real Model Runtime is available. See logs/feature-sandbox.md "Open issues / known gaps".
"""

from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.domain.capabilities.registry import get_registry
from backend.models.schemas import GenerateCodeInput, GenerateCodeOutput


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


def _parse_model_response(response_text: str) -> tuple[str, str]:
    """Parse the model response into code and explanation."""
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

    code = "\n".join(code_lines).strip()
    explanation = "\n".join(explanation_lines).strip()

    # Fallback: if parsing failed, treat entire response as code
    if not code:
        code = response_text.strip()
        explanation = "Generated code for the described task."

    return code, explanation


class ModelRuntimeStub:
    """Stub for Model Runtime code_generation call — replace with real implementation from Task 8."""

    @staticmethod
    async def generate(resource_type: str, prompt: str) -> str:
        """
        Generate code using the code_generation resource.

        This is a STUB. The real implementation (Task 8) will:
        1. Resolve resource_type "code_generation" to model via Resource/Model Configuration Registry
        2. Call Ollama via Model Runtime module
        3. Return the generated text

        For now, returns a simple working example based on the task description.
        """
        if resource_type != "code_generation":
            raise ValueError(f"Expected resource_type 'code_generation', got '{resource_type}'")

        # Simple heuristic-based stub for demo/testing
        task_lower = prompt.lower()

        if "hello" in task_lower or "print" in task_lower:
            return """CODE:
print("Hello, World!")
EXPLANATION:
Prints a simple greeting to stdout."""

        if "factorial" in task_lower:
            return """CODE:
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(5)
print(f"5! = {result}")
EXPLANATION:
Computes 5! recursively and prints the result."""

        if "fibonacci" in task_lower or "fib" in task_lower:
            return """CODE:
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

for i in range(10):
    print(fibonacci(i))
EXPLANATION:
Prints the first 10 Fibonacci numbers."""

        if "sum" in task_lower and "range" in task_lower:
            return """CODE:
total = sum(range(1, 101))
print(f"Sum of 1 to 100 = {total}")
EXPLANATION:
Calculates and prints the sum of integers from 1 to 100."""

        # Default: simple calculation
        return """CODE:
result = 2 + 2
print(f"2 + 2 = {result}")
EXPLANATION:
Simple arithmetic calculation demonstrating the sandbox."""


async def _call_model_runtime(prompt: str) -> str:
    """Call the Model Runtime for code_generation. Swappable for real implementation."""
    return await ModelRuntimeStub.generate("code_generation", prompt)


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
        model_response = await _call_model_runtime(prompt)
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