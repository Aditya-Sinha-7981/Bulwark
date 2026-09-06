"""
Tests for Task 14.a — DOCX artifact renderer and create_docx capability.

Covers, per docs/testing.md "Artifact tests" and "Failure injection":
- schema validation (valid input renders; invalid input is rejected
  before any file is written)
- atomic-write behavior (no partial file survives a mid-render failure)
- malformed-payload rejection (extra fields, wrong types, bad date format)
- Artifact-row persistence tying back to the correct job_id
"""
from __future__ import annotations

import tempfile
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend.domain.artifacts.docx_renderer import DocxRenderError, render_docx
from backend.domain.capabilities.create_docx import (
    CapabilityValidationError,
    execute_create_docx,
    validate_input,
    validate_output,
)
from backend.repositories import artifacts as artifacts_repo
from backend.repositories.db import get_connection
from backend.utils.ids import new_id
import scripts.init_db as init_db

VALID_PAYLOAD = {
    "title": "Q3 Inspection Findings",
    "sections": [
        {"heading": "Summary", "body": "No critical defects found."},
        {"heading": "Recommendations", "body": "Schedule follow-up in 90 days."},
    ],
    "metadata": {"prepared_by": "J. Rao", "date": "2026-09-06T00:00:00+00:00"},
}


def create_temp_db():
    """Create a temporary database and return its path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    original_get_db_path = init_db.get_db_path
    init_db.get_db_path = lambda: db_path
    init_db.main()
    init_db.get_db_path = original_get_db_path

    return db_path


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    db_path = create_temp_db()
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def temp_artifacts_root(tmp_path, monkeypatch):
    """Point the renderer at a throwaway directory instead of the real data/artifacts/."""
    fake_root = tmp_path / "artifacts"
    fake_root.mkdir()

    # Patch the paths module - both ARTIFACTS_ROOT and artifacts_path
    import backend.utils.paths as paths_module
    monkeypatch.setattr(paths_module, "ARTIFACTS_ROOT", fake_root)
    monkeypatch.setattr(paths_module, "artifacts_path", lambda artifact_id, ext: fake_root / f"{artifact_id}{ext}")
    return fake_root


@pytest.fixture
def patched_repos(temp_db):
    """Patch repository connections to use temp DB."""
    original_artifacts_conn = artifacts_repo.get_connection
    original_db_conn = get_connection

    artifacts_repo.get_connection = lambda: get_connection(temp_db)

    import backend.repositories.db as db_module
    original_db_conn_module = db_module.get_connection
    db_module.get_connection = lambda: get_connection(temp_db)

    yield temp_db

    artifacts_repo.get_connection = original_artifacts_conn
    db_module.get_connection = original_db_conn_module


# ---------------------------------------------------------------------------
# validate_input
# ---------------------------------------------------------------------------


def test_validate_input_accepts_valid_payload():
    result = validate_input(VALID_PAYLOAD)
    assert result == VALID_PAYLOAD


def test_validate_input_rejects_missing_title():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "title"}
    with pytest.raises(CapabilityValidationError, match="title"):
        validate_input(payload)


def test_validate_input_rejects_empty_title():
    payload = {**VALID_PAYLOAD, "title": "   "}
    with pytest.raises(CapabilityValidationError, match="title"):
        validate_input(payload)


def test_validate_input_rejects_extra_top_level_field():
    payload = {**VALID_PAYLOAD, "unexpected_field": "should not be here"}
    with pytest.raises(CapabilityValidationError, match="unexpected field"):
        validate_input(payload)


def test_validate_input_rejects_empty_sections():
    payload = {**VALID_PAYLOAD, "sections": []}
    with pytest.raises(CapabilityValidationError, match="sections"):
        validate_input(payload)


def test_validate_input_rejects_section_missing_heading():
    payload = {**VALID_PAYLOAD, "sections": [{"body": "no heading here"}]}
    with pytest.raises(CapabilityValidationError, match="heading"):
        validate_input(payload)


def test_validate_input_rejects_extra_field_in_section():
    payload = {
        **VALID_PAYLOAD,
        "sections": [{"heading": "H", "body": "B", "extra": "nope"}],
    }
    with pytest.raises(CapabilityValidationError, match="unexpected field"):
        validate_input(payload)


def test_validate_input_rejects_missing_metadata():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "metadata"}
    with pytest.raises(CapabilityValidationError, match="metadata"):
        validate_input(payload)


def test_validate_input_rejects_non_iso8601_date():
    payload = {
        **VALID_PAYLOAD,
        "metadata": {"prepared_by": "J. Rao", "date": "not-a-date"},
    }
    with pytest.raises(CapabilityValidationError, match="ISO-8601"):
        validate_input(payload)


def test_validate_input_rejects_empty_prepared_by():
    payload = {
        **VALID_PAYLOAD,
        "metadata": {"prepared_by": "", "date": "2026-09-06T00:00:00+00:00"},
    }
    with pytest.raises(CapabilityValidationError, match="prepared_by"):
        validate_input(payload)


# ---------------------------------------------------------------------------
# validate_output
# ---------------------------------------------------------------------------


def test_validate_output_accepts_valid_shape():
    result = validate_output({"artifact_id": "abc-123", "filename": "Report.docx"})
    assert result["artifact_id"] == "abc-123"


def test_validate_output_rejects_missing_filename():
    with pytest.raises(CapabilityValidationError, match="filename"):
        validate_output({"artifact_id": "abc-123"})


def test_validate_output_rejects_extra_field():
    with pytest.raises(CapabilityValidationError, match="unexpected"):
        validate_output({"artifact_id": "a", "filename": "f.docx", "extra": 1})


# ---------------------------------------------------------------------------
# render_docx — atomic write + Artifact persistence
# ---------------------------------------------------------------------------


def test_render_docx_writes_file_and_creates_artifact_row(temp_artifacts_root, patched_repos):
    with patch(
        "backend.domain.artifacts.docx_renderer.create_artifact"
    ) as mock_create_artifact:
        mock_create_artifact.return_value = "generated-artifact-id"

        result = render_docx(
            artifact_id="test-artifact-id",
            job_id="test-job-id",
            payload=VALID_PAYLOAD,
        )

    assert result["artifact_id"] == "test-artifact-id"
    assert result["filename"].endswith(".docx")

    written_file = temp_artifacts_root / "test-artifact-id.docx"
    assert written_file.exists()
    assert written_file.stat().st_size > 0

    mock_create_artifact.assert_called_once()
    call_kwargs = mock_create_artifact.call_args.kwargs
    assert call_kwargs["job_id"] == "test-job-id"
    assert call_kwargs["type"] == "docx"


def test_render_docx_removes_orphan_file_if_artifact_row_fails(temp_artifacts_root, patched_repos):
    with patch(
        "backend.domain.artifacts.docx_renderer.create_artifact",
        side_effect=RuntimeError("db unavailable"),
    ):
        with pytest.raises(DocxRenderError, match="Artifact row"):
            render_docx(
                artifact_id="orphan-test-id",
                job_id="test-job-id",
                payload=VALID_PAYLOAD,
            )

    # No file should survive a failed Artifact-row insert (artifacts.md
    # "Failure handling": never a file with no corresponding row).
    assert not (temp_artifacts_root / "orphan-test-id.docx").exists()
    # No leftover temp file either.
    assert list(temp_artifacts_root.glob("*.tmp")) == []


def test_render_docx_leaves_no_temp_file_on_python_docx_failure(temp_artifacts_root, patched_repos):
    with patch(
        "backend.domain.artifacts.docx_renderer._build_document",
        side_effect=RuntimeError("simulated python-docx crash"),
    ):
        with pytest.raises(DocxRenderError, match="render/write"):
            render_docx(
                artifact_id="crash-test-id",
                job_id="test-job-id",
                payload=VALID_PAYLOAD,
            )

    assert list(temp_artifacts_root.iterdir()) == []


# ---------------------------------------------------------------------------
# execute_create_docx — full capability path, including audit emission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_create_docx_emits_artifact_created_event(temp_artifacts_root, patched_repos):
    with patch(
        "backend.domain.capabilities.create_docx.emit", new_callable=AsyncMock
    ) as mock_emit, patch(
        "backend.domain.artifacts.docx_renderer.create_artifact"
    ) as mock_create_artifact:
        mock_create_artifact.return_value = "generated-id"

        result = await execute_create_docx(job_id="job-1", arguments=VALID_PAYLOAD)

        mock_emit.assert_awaited_once()
        call_args = mock_emit.call_args
        assert call_args.args[0] == "artifact_created"
        assert call_args.kwargs["job_id"] == "job-1"

    assert result["filename"].endswith(".docx")


@pytest.mark.asyncio
async def test_execute_create_docx_never_renders_on_invalid_input(temp_artifacts_root, patched_repos):
    invalid_payload = {"title": ""}  # missing sections/metadata entirely

    with patch(
        "backend.domain.artifacts.docx_renderer.create_artifact"
    ) as mock_create_artifact:
        with pytest.raises(CapabilityValidationError):
            await execute_create_docx(job_id="job-1", arguments=invalid_payload)

        mock_create_artifact.assert_not_called()

    # No stray files from a payload that never should have reached the renderer.
    assert list(temp_artifacts_root.iterdir()) == []


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_artifact_metadata_404(temp_artifacts_root, temp_db, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    import backend.repositories.db as db_module

    # Patch all repository connections to use temp DB
    import backend.repositories.jobs as jobs_repo
    import backend.repositories.conversations as conversations_repo
    import backend.repositories.audit_events as audit_events_repo
    import backend.repositories.artifacts as artifacts_repo

    monkeypatch.setattr(jobs_repo, "get_connection", lambda: get_connection(temp_db))
    monkeypatch.setattr(conversations_repo, "get_connection", lambda: get_connection(temp_db))
    monkeypatch.setattr(db_module, "get_connection", lambda: get_connection(temp_db))
    monkeypatch.setattr(audit_events_repo, "get_connection", lambda: get_connection(temp_db))
    monkeypatch.setattr(artifacts_repo, "get_connection", lambda: get_connection(temp_db))

    with TestClient(app) as client:
        response = client.get("/api/v1/artifacts/nonexistent-id")
        assert response.status_code == 404
        # Check error envelope matches docs/api.md - FastAPI wraps HTTPException.detail
        data = response.json()
        assert "detail" in data
        error = data["detail"]
        assert "error" in error
        assert error["error"]["code"] == "not_found"
        assert "message" in error["error"]
        assert "details" in error["error"]


# Need to import patch for tests that use it
from unittest.mock import patch, AsyncMock