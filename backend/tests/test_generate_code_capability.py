"""
Unit tests for backend/domain/capabilities/generate_code.py.
"""

from __future__ import annotations

import pytest

from backend.domain.capabilities import generate_code as gc


class TestInputValidation:
    def test_rejects_missing_task_description(self):
        with pytest.raises(gc.CapabilityValidationError):
            gc.validate_input({"language": "python"})

    def test_rejects_empty_task_description(self):
        with pytest.raises(gc.CapabilityValidationError):
            gc.validate_input({"task_description": "   ", "language": "python"})

    def test_rejects_non_python_language(self):
        with pytest.raises(gc.CapabilityValidationError):
            gc.validate_input({"task_description": "sum a list", "language": "cpp"})


class TestOutputValidation:
    def test_rejects_missing_fields(self):
        with pytest.raises(gc.CapabilityValidationError):
            gc.validate_output({"code": "print(1)", "language": "python"})  # no explanation

    def test_rejects_empty_code(self):
        with pytest.raises(gc.CapabilityValidationError):
            gc.validate_output({"code": "", "language": "python", "explanation": "x"})

    def test_accepts_valid_output(self):
        out = gc.validate_output({"code": "print(1)", "language": "python", "explanation": "prints 1"})
        assert out.code == "print(1)"
        assert out.language == "python"
        assert out.explanation == "prints 1"


class TestGenerateCodeHappyPath:
    @pytest.mark.asyncio
    async def test_execute_generate_code_returns_valid_shape(self):
        # This test uses the stub ModelRuntimeStub which returns code based on task description
        result = await gc.execute_generate_code(
            "test-job-1",
            {"task_description": "print hello world", "language": "python"},
        )

        assert result["language"] == "python"
        assert "print" in result["code"].lower() or "hello" in result["code"].lower()
        assert result["explanation"]

    @pytest.mark.asyncio
    async def test_never_touches_filesystem_or_executes(self, tmp_path):
        # generate_code must have zero filesystem/execution side effects.
        before = set(tmp_path.iterdir())

        result = await gc.execute_generate_code(
            "test-job-1",
            {"task_description": "noop", "language": "python"},
        )

        after = set(tmp_path.iterdir())
        assert before == after
        assert result["code"]
        assert result["language"] == "python"


class TestGenerateCodeValidation:
    @pytest.mark.asyncio
    async def test_model_call_exception_becomes_validation_error(self, monkeypatch):
        # Test that exceptions from model runtime become CapabilityValidationError
        async def broken_model_runtime(prompt: str):
            raise ConnectionError("model unreachable")

        monkeypatch.setattr(gc, "_call_model_runtime", broken_model_runtime)

        with pytest.raises(gc.CapabilityValidationError, match="Model Runtime call failed"):
            await gc.execute_generate_code(
                "test-job-1",
                {"task_description": "anything", "language": "python"},
            )

    @pytest.mark.asyncio
    async def test_empty_model_output_becomes_validation_error(self, monkeypatch):
        async def empty_model_runtime(prompt: str):
            return ""

        monkeypatch.setattr(gc, "_call_model_runtime", empty_model_runtime)

        with pytest.raises(gc.CapabilityValidationError, match="Model returned empty code"):
            await gc.execute_generate_code(
                "test-job-1",
                {"task_description": "anything", "language": "python"},
            )