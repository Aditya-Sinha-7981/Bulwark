"""
Unit tests for artifacts repository.
"""

import tempfile
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.repositories import artifacts, jobs, conversations
from backend.repositories.db import get_connection, ConstraintError
from backend.utils.ids import new_id


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    import scripts.init_db as init_db
    original_get_db_path = init_db.get_db_path
    init_db.get_db_path = lambda: db_path
    init_db.main()
    init_db.get_db_path = original_get_db_path

    original_artifacts_conn = artifacts.get_connection
    original_jobs_conn = jobs.get_connection
    original_conv_conn = conversations.get_connection

    artifacts.get_connection = lambda: get_connection(db_path)
    jobs.get_connection = lambda: get_connection(db_path)
    conversations.get_connection = lambda: get_connection(db_path)

    yield db_path

    artifacts.get_connection = original_artifacts_conn
    jobs.get_connection = original_jobs_conn
    conversations.get_connection = original_conv_conn
    if db_path.exists():
        db_path.unlink()


def test_create_artifact(temp_db):
    """Test creating an artifact."""
    conv_id = conversations.create_conversation()
    job_id = jobs.create_job(conv_id, "Input")

    artifact_id = artifacts.create_artifact(
        job_id=job_id,
        type="docx",
        filename="output.docx",
        storage_path="artifacts/output.docx",
        size_bytes=2048
    )
    assert artifact_id is not None


def test_create_artifact_invalid_type(temp_db):
    """Test creating artifact with invalid type."""
    conv_id = conversations.create_conversation()
    job_id = jobs.create_job(conv_id, "Input")

    with pytest.raises(ConstraintError):
        artifacts.create_artifact(job_id, "invalid", "file", "path", 100)


def test_create_artifact_nonexistent_job(temp_db):
    """Test creating artifact for non-existent job."""
    with pytest.raises(ConstraintError):
        artifacts.create_artifact(new_id(), "docx", "file", "path", 100)


def test_get_artifact(temp_db):
    """Test getting an artifact."""
    conv_id = conversations.create_conversation()
    job_id = jobs.create_job(conv_id, "Input")

    artifact_id = artifacts.create_artifact(
        job_id=job_id,
        type="xlsx",
        filename="output.xlsx",
        storage_path="artifacts/output.xlsx",
        size_bytes=4096
    )
    artifact = artifacts.get_artifact(artifact_id)
    assert artifact is not None
    assert artifact["artifact_id"] == artifact_id
    assert artifact["job_id"] == job_id
    assert artifact["type"] == "xlsx"
    assert artifact["filename"] == "output.xlsx"
    assert artifact["size_bytes"] == 4096


def test_get_nonexistent_artifact(temp_db):
    """Test getting non-existent artifact returns None."""
    artifact = artifacts.get_artifact(new_id())
    assert artifact is None


def test_list_artifacts_by_job(temp_db):
    """Test listing artifacts for a job."""
    conv_id = conversations.create_conversation()
    job_id = jobs.create_job(conv_id, "Input")
    job_id2 = jobs.create_job(conv_id, "Input 2")

    artifacts.create_artifact(job_id, "docx", "a.docx", "artifacts/a.docx", 100)
    artifacts.create_artifact(job_id, "xlsx", "b.xlsx", "artifacts/b.xlsx", 200)
    artifacts.create_artifact(job_id2, "pptx", "c.pptx", "artifacts/c.pptx", 300)

    job_artifacts = artifacts.list_artifacts_by_job(job_id)
    assert len(job_artifacts) == 2

    # Ordered by created_at
    assert job_artifacts[0]["filename"] == "a.docx"
    assert job_artifacts[1]["filename"] == "b.xlsx"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])