"""
Unit tests for jobs repository.
"""

import tempfile
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.repositories import jobs, conversations
from backend.repositories.db import get_connection, ConstraintError
from backend.utils.ids import new_id
import scripts.init_db as init_db


def create_temp_db():
    """Create a temporary database and return its path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Run init script against temp DB
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


def test_create_job(temp_db):
    """Test creating a job."""
    # Patch connections
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Test input message")
        assert job_id is not None
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_create_job_invalid_status(temp_db):
    """Test creating job with invalid status."""
    original_jobs_conn = jobs.get_connection
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = new_id()
        with pytest.raises(ConstraintError):
            jobs.create_job(conv_id, "Input", status="invalid")
    finally:
        jobs.get_connection = original_jobs_conn


def test_get_job(temp_db):
    """Test getting a job."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Test input")
        job = jobs.get_job(job_id)
        assert job is not None
        assert job["job_id"] == job_id
        assert job["conversation_id"] == conv_id
        assert job["status"] == "created"
        assert job["input_message"] == "Test input"
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_get_nonexistent_job(temp_db):
    """Test getting non-existent job returns None."""
    original_jobs_conn = jobs.get_connection
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        job = jobs.get_job(new_id())
        assert job is None
    finally:
        jobs.get_connection = original_jobs_conn


def test_update_job(temp_db):
    """Test updating job fields."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        jobs.update_job(job_id, status="running")
        job = jobs.get_job(job_id)
        assert job["status"] == "running"

        jobs.update_job(job_id, status="completed", final_message="Done", completed_at="2024-01-01T00:00:00")
        job = jobs.get_job(job_id)
        assert job["status"] == "completed"
        assert job["final_message"] == "Done"
        assert job["completed_at"] == "2024-01-01T00:00:00"
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_update_job_invalid_status(temp_db):
    """Test updating job with invalid status."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        with pytest.raises(ConstraintError):
            jobs.update_job(job_id, status="invalid")
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_list_jobs_by_status(temp_db):
    """Test listing jobs by status."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job1 = jobs.create_job(conv_id, "Input 1", status="created")
        job2 = jobs.create_job(conv_id, "Input 2", status="running")
        job3 = jobs.create_job(conv_id, "Input 3", status="created")

        created_jobs = jobs.list_jobs_by_status("created")
        assert len(created_jobs) == 2

        running_jobs = jobs.list_jobs_by_status("running")
        assert len(running_jobs) == 1
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_list_jobs_by_conversation(temp_db):
    """Test listing jobs by conversation."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        conv_id2 = conversations.create_conversation()
        jobs.create_job(conv_id, "Input 1")
        jobs.create_job(conv_id, "Input 2")
        jobs.create_job(conv_id2, "Input 3")

        conv_jobs = jobs.list_jobs_by_conversation(conv_id)
        assert len(conv_jobs) == 2
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


# JobStep tests

def test_add_job_step(temp_db):
    """Test adding a job step."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        step_id = jobs.add_job_step(job_id, 1, "orchestrator_reasoning", '{"prompt": "test"}')
        assert step_id is not None

        step = jobs.get_job_step(step_id)
        assert step is not None
        assert step["job_id"] == job_id
        assert step["sequence"] == 1
        assert step["kind"] == "orchestrator_reasoning"
        assert step["status"] == "pending"
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_add_job_step_invalid_kind(temp_db):
    """Test adding job step with invalid kind."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        with pytest.raises(ConstraintError):
            jobs.add_job_step(job_id, 1, "invalid_kind", '{}')
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_add_job_step_invalid_status(temp_db):
    """Test adding job step with invalid status."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        with pytest.raises(ConstraintError):
            jobs.add_job_step(job_id, 1, "orchestrator_reasoning", '{}', status="invalid")
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_add_job_step_capability_invocation_requires_name(temp_db):
    """Test capability_invocation requires capability_name."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        with pytest.raises(ConstraintError):
            jobs.add_job_step(job_id, 1, "capability_invocation", '{}')
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_list_job_steps_ordered_by_sequence(temp_db):
    """Test job steps ordered by sequence."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        jobs.add_job_step(job_id, 3, "orchestrator_reasoning", '{}')
        jobs.add_job_step(job_id, 1, "orchestrator_reasoning", '{}')
        jobs.add_job_step(job_id, 2, "capability_invocation", '{}', capability_name="test")

        steps = jobs.list_job_steps(job_id)
        assert len(steps) == 3
        assert steps[0]["sequence"] == 1
        assert steps[1]["sequence"] == 2
        assert steps[2]["sequence"] == 3
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_update_job_step(temp_db):
    """Test updating job step."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        step_id = jobs.add_job_step(job_id, 1, "orchestrator_reasoning", '{}')

        jobs.update_job_step(step_id, status="running", started_at="2024-01-01T00:00:00")
        step = jobs.get_job_step(step_id)
        assert step["status"] == "running"
        assert step["started_at"] == "2024-01-01T00:00:00"
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_add_capability_execution(temp_db):
    """Test adding capability execution."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        step_id = jobs.add_job_step(job_id, 1, "capability_invocation", '{}', capability_name="test_cap")

        cap_exec_id = jobs.add_capability_execution(
            step_id, "test_cap", "allow", resource_type="reasoning"
        )
        assert cap_exec_id is not None

        cap_exec = jobs.get_capability_execution(cap_exec_id)
        assert cap_exec is not None
        assert cap_exec["job_step_id"] == step_id
        assert cap_exec["capability_name"] == "test_cap"
        assert cap_exec["policy_decision"] == "allow"
        assert cap_exec["resource_type"] == "reasoning"
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_add_capability_execution_deny_requires_reason(temp_db):
    """Test deny decision requires reason."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        step_id = jobs.add_job_step(job_id, 1, "capability_invocation", '{}', capability_name="test")

        with pytest.raises(ConstraintError):
            jobs.add_capability_execution(step_id, "test", "deny")
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


def test_add_model_execution(temp_db):
    """Test adding model execution."""
    original_conv_conn = conversations.get_connection
    original_jobs_conn = jobs.get_connection
    conversations.get_connection = lambda: get_connection(temp_db)
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        step_id = jobs.add_job_step(job_id, 1, "capability_invocation", '{}', capability_name="test")
        cap_exec_id = jobs.add_capability_execution(step_id, "test", "allow", resource_type="reasoning")

        model_exec_id = jobs.add_model_execution(
            cap_exec_id, "reasoning", "qwen3.5:9b", "ollama",
            prompt_tokens=100, completion_tokens=50, duration_ms=1000, load_triggered=True
        )
        assert model_exec_id is not None

        model_exec = jobs.get_model_execution(model_exec_id)
        assert model_exec is not None
        assert model_exec["capability_execution_id"] == cap_exec_id
        assert model_exec["model_identifier"] == "qwen3.5:9b"
        assert model_exec["load_triggered"] == 1
    finally:
        conversations.get_connection = original_conv_conn
        jobs.get_connection = original_jobs_conn


if __name__ == "__main__":
    pytest.main([__file__, "-v"])