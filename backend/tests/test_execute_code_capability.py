"""
Unit tests for backend/domain/capabilities/execute_code.py -- the capability
layer sitting on top of docker_executor.py. Mocks run_in_sandbox so these run
without Docker; docker_executor.py's own behavior is covered separately in
test_docker_executor_unit.py and test_sandbox.py.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from backend.domain.capabilities import execute_code as ec
from backend.domain.sandbox.docker_executor import DockerUnavailableError, SandboxResult


def _fake_result(**overrides):
    base = dict(
        execution_id="exec-1",
        stdout="ok\n",
        stderr="",
        exit_code=0,
        timed_out=False,
        output_files=[],
    )
    base.update(overrides)
    return SandboxResult(**base)


class TestInputValidation:
    def test_rejects_missing_code(self):
        with pytest.raises(ec.CapabilityValidationError):
            ec.validate_input({"language": "python"})

    def test_rejects_empty_code(self):
        with pytest.raises(ec.CapabilityValidationError):
            ec.validate_input({"code": "   ", "language": "python"})

    def test_rejects_non_python_language(self):
        with pytest.raises(ec.CapabilityValidationError):
            ec.validate_input({"code": "print(1)", "language": "javascript"})

    def test_rejects_bad_input_files_type(self):
        with pytest.raises(ec.CapabilityValidationError):
            ec.validate_input({"code": "print(1)", "language": "python", "input_files": "not-a-list"})

    def test_accepts_valid_payload_with_defaults(self):
        result = ec.validate_input({"code": "print(1)", "language": "python"})
        assert result.code == "print(1)"
        assert result.language == "python"
        assert result.input_files == []


class TestExecuteCodeHappyPath:
    @pytest.mark.asyncio
    async def test_returns_raw_shape_not_final_schema(self, tmp_path: Path):
        with patch("backend.domain.capabilities.execute_code.run_in_sandbox", return_value=_fake_result(output_files=["out.txt"])):
            result = await ec.execute_execute_code(
                "test-job-1",
                {"code": "print(1)", "language": "python"},
            )

        assert set(result.keys()) == {"stdout", "stderr", "exit_code", "timed_out", "output_files"}
        # Locked: these must be raw filenames, not artifact_ids (Task 13 §6/§7 Req 3).
        assert result["output_files"] == ["out.txt"]
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_exit_code_returned_verbatim_no_pass_fail_translation(self, tmp_path: Path):
        with patch("backend.domain.capabilities.execute_code.run_in_sandbox", return_value=_fake_result(exit_code=17)):
            result = await ec.execute_execute_code(
                "test-job-1",
                {"code": "print(1)", "language": "python"},
            )
        assert result["exit_code"] == 17  # not coerced to True/False or 0/1


class TestExecuteCodeFailurePaths:
    @pytest.mark.asyncio
    async def test_docker_unavailable_returns_structured_failure_not_exception(self, tmp_path: Path):
        with patch("backend.domain.capabilities.execute_code.run_in_sandbox", side_effect=DockerUnavailableError("daemon down")):
            result = await ec.execute_execute_code(
                "test-job-1",
                {"code": "print(1)", "language": "python"},
            )

        # Real implementation converts exit_code=None to -1 for schema compliance (ExecuteCodeOutput.exit_code: int)
        assert result["exit_code"] == -1
        assert "docker_unavailable" in result["stderr"]
        assert result["output_files"] == []
        assert result["timed_out"] is False

    @pytest.mark.asyncio
    async def test_timeout_returns_exit_code_minus_one_not_none(self, tmp_path: Path):
        # Real docker_executor returns exit_code=None on timeout, but execute_code.py
        # converts None -> -1 before schema validation (ExecuteCodeOutput.exit_code: int)
        with patch("backend.domain.capabilities.execute_code.run_in_sandbox", return_value=_fake_result(timed_out=True, exit_code=None)):
            result = await ec.execute_execute_code(
                "test-job-1",
                {"code": "...", "language": "python"},
            )
        assert result["timed_out"] is True
        assert result["exit_code"] == -1  # converted from None for schema compliance

    @pytest.mark.asyncio
    async def test_other_execution_error_returns_structured_failure(self, tmp_path: Path):
        with patch("backend.domain.capabilities.execute_code.run_in_sandbox", side_effect=RuntimeError("unexpected error")):
            result = await ec.execute_execute_code(
                "test-job-1",
                {"code": "print(1)", "language": "python"},
            )

        assert result["exit_code"] == -1
        assert "execution_error" in result["stderr"]
        assert result["output_files"] == []
        assert result["timed_out"] is False


class TestInputFileResolution:
    @pytest.mark.asyncio
    async def test_input_files_resolved_via_uploads_path(self, tmp_path: Path, monkeypatch):
        # Create a fake uploads directory with a test file
        from backend.utils.paths import UPLOADS_ROOT
        monkeypatch.setattr("backend.utils.paths.UPLOADS_ROOT", tmp_path / "uploads")
        (tmp_path / "uploads").mkdir(parents=True)
        test_file = tmp_path / "uploads" / "doc-123.txt"
        test_file.write_text("test content")

        with patch("backend.domain.capabilities.execute_code.run_in_sandbox", return_value=_fake_result()) as mock_run:
            await ec.execute_execute_code(
                "test-job-1",
                {"code": "print(1)", "language": "python", "input_files": ["doc-123"]},
            )

        # Check that the resolved file path was passed to run_in_sandbox
        _, kwargs = mock_run.call_args
        assert "input_files" in kwargs
        assert len(kwargs["input_files"]) == 1
        assert kwargs["input_files"][0].endswith("doc-123.txt")

    @pytest.mark.asyncio
    async def test_missing_input_file_passes_doc_id_as_fallback(self, tmp_path: Path, monkeypatch):
        # When file doesn't exist, the doc_id is passed through as-is
        # (will surface as FileNotFoundError inside the sandbox)
        from backend.utils.paths import UPLOADS_ROOT
        monkeypatch.setattr("backend.utils.paths.UPLOADS_ROOT", tmp_path / "uploads")
        (tmp_path / "uploads").mkdir(parents=True)

        with patch("backend.domain.capabilities.execute_code.run_in_sandbox", return_value=_fake_result()) as mock_run:
            await ec.execute_execute_code(
                "test-job-1",
                {"code": "print(1)", "language": "python", "input_files": ["missing-doc"]},
            )

        _, kwargs = mock_run.call_args
        assert "input_files" in kwargs
        assert kwargs["input_files"] == ["missing-doc"]