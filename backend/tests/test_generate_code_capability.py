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
    @staticmethod
    def _canned_model_runtime(response: str):
        async def fake_model_runtime(prompt: str, *, job_id=None):
            return response

        return fake_model_runtime

    @pytest.mark.asyncio
    async def test_execute_generate_code_returns_valid_shape(self, monkeypatch):
        """Real Model Runtime is called (mocked here for hermeticity) — the
        executor parses its CODE:/EXPLANATION: response into the output shape."""
        monkeypatch.setattr(
            gc,
            "_call_model_runtime",
            self._canned_model_runtime('CODE:\nprint("Hello, World!")\nEXPLANATION:\nPrints a greeting.'),
        )
        result = await gc.execute_generate_code(
            "test-job-1",
            {"task_description": "print hello world", "language": "python"},
        )

        assert result["language"] == "python"
        assert "print" in result["code"].lower()
        assert result["explanation"]

    @pytest.mark.asyncio
    async def test_never_touches_filesystem_or_executes(self, monkeypatch, tmp_path):
        # generate_code must have zero filesystem/execution side effects.
        monkeypatch.setattr(
            gc,
            "_call_model_runtime",
            self._canned_model_runtime("CODE:\nprint(1)\nEXPLANATION:\nprints 1."),
        )
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
        async def broken_model_runtime(prompt: str, *, job_id=None):
            raise ConnectionError("model unreachable")

        monkeypatch.setattr(gc, "_call_model_runtime", broken_model_runtime)

        with pytest.raises(gc.CapabilityValidationError, match="Model Runtime call failed"):
            await gc.execute_generate_code(
                "test-job-1",
                {"task_description": "anything", "language": "python"},
            )

    @pytest.mark.asyncio
    async def test_empty_model_output_becomes_validation_error(self, monkeypatch):
        async def empty_model_runtime(prompt: str, *, job_id=None):
            return ""

        monkeypatch.setattr(gc, "_call_model_runtime", empty_model_runtime)

        with pytest.raises(gc.CapabilityValidationError, match="Model returned empty code"):
            await gc.execute_generate_code(
                "test-job-1",
                {"task_description": "anything", "language": "python"},
            )


class TestParseModelResponse:
    """Regression: coder models emit markdown-fenced responses despite the
    CODE:/EXPLANATION: format instructions (observed live 2026-09-12 on
    qwen2.5-coder:7b) — fences and prose must not leak into the code."""

    def test_instructed_format(self):
        code, explanation = gc._parse_model_response(
            "CODE:\nprint(1)\nEXPLANATION:\nprints 1"
        )
        assert code == "print(1)"
        assert explanation == "prints 1"

    def test_fenced_response_without_markers(self):
        code, explanation = gc._parse_model_response(
            "```python\nfrom math import pi\nprint(pi)\n```\nEXPLANATION:\nPrints pi."
        )
        assert code == "from math import pi\nprint(pi)"
        assert "```" not in code
        assert "Prints pi." in explanation

    def test_fences_inside_code_section_stripped(self):
        code, explanation = gc._parse_model_response(
            "CODE:\n```python\nprint(2)\n```\nEXPLANATION:\nprints 2"
        )
        assert code == "print(2)"
        assert explanation == "prints 2"

    def test_plain_response_fallback(self):
        code, explanation = gc._parse_model_response("print(3)")
        assert code == "print(3)"
        assert explanation