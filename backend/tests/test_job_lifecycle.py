"""
Integration tests for Job lifecycle.

Tests the complete job lifecycle from creation through completion via the API.
"""

import asyncio
import time
import json
import tempfile
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app
from backend.config import settings
from backend.repositories import jobs as jobs_repo, conversations as conversations_repo
from backend.repositories.db import get_connection
from backend.domain.audit.events import get_events_for_job
import scripts.init_db as init_db


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
def client(temp_db):
    """Create a test client with patched database."""
    # Patch all repository connections to use temp DB
    original_jobs_conn = jobs_repo.get_connection
    original_conv_conn = conversations_repo.get_connection
    original_audit_conn = get_connection  # from audit_events

    # Need to patch the db module's get_connection for audit events
    import backend.repositories.db as db_module
    original_db_conn = db_module.get_connection

    jobs_repo.get_connection = lambda: get_connection(temp_db)
    conversations_repo.get_connection = lambda: get_connection(temp_db)
    db_module.get_connection = lambda: get_connection(temp_db)

    # Also need to patch audit events repo
    import backend.repositories.audit_events as audit_events_repo
    original_audit_events_conn = audit_events_repo.get_connection
    audit_events_repo.get_connection = lambda: get_connection(temp_db)

    with TestClient(app) as test_client:
        yield test_client

    jobs_repo.get_connection = original_jobs_conn
    conversations_repo.get_connection = original_conv_conn
    db_module.get_connection = original_db_conn
    audit_events_repo.get_connection = original_audit_events_conn


def test_create_job_returns_201_and_creates_row(client, temp_db):
    """POST /api/v1/jobs -> 201 with documented body; jobs row exists; job_created event persisted."""
    conv_id = conversations_repo.create_conversation()

    response = client.post(
        "/api/v1/jobs",
        json={
            "conversation_id": conv_id,
            "message": "Test message",
            "document_ids": [],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "created"
    assert "created_at" in data

    job_id = data["job_id"]
    job = jobs_repo.get_job(job_id)
    assert job is not None
    # Job may already be running/completed due to TestClient running background tasks synchronously
    assert job["status"] in ("created", "running", "completed")
    # If completed, verify it completed successfully
    if job["status"] == "completed":
        assert job["final_message"] is not None
        assert job["error_code"] is None
    assert job["input_message"] == "Test message"
    assert job["conversation_id"] == conv_id

    events = asyncio.run(get_events_for_job(job_id))
    job_created_events = [e for e in events if e["event_type"] == "job_created"]
    assert len(job_created_events) == 1
    assert job_created_events[0]["payload"]["conversation_id"] == conv_id
    assert job_created_events[0]["payload"]["input_message"] == "Test message"


def test_job_completes_with_final_message(client, temp_db):
    """After background run: GET /jobs/{id} -> status: completed, final_message set, artifact_ids: [], error: null."""
    conv_id = conversations_repo.create_conversation()

    response = client.post(
        "/api/v1/jobs",
        json={
            "conversation_id": conv_id,
            "message": "Test message",
            "document_ids": [],
        },
    )

    job_id = response.json()["job_id"]

    max_wait = 10.0
    poll_interval = 0.1
    waited = 0.0
    while waited < max_wait:
        job = jobs_repo.get_job(job_id)
        if job and job["status"] == "completed":
            break
        time.sleep(poll_interval)
        waited += poll_interval

    job = jobs_repo.get_job(job_id)
    assert job is not None
    assert job["status"] == "completed"
    assert job["final_message"] is not None
    assert "Echo: Test message" in job["final_message"]
    assert job["error_code"] is None
    assert job["error_message"] is None

    response = client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["final_message"] is not None
    assert data["artifact_ids"] == []
    assert data["error"] is None


def test_job_step_created_orchestrator_reasoning(client, temp_db):
    """A job_steps row exists: kind: orchestrator_reasoning, status: succeeded; no capability_executions row."""
    conv_id = conversations_repo.create_conversation()

    response = client.post(
        "/api/v1/jobs",
        json={
            "conversation_id": conv_id,
            "message": "Test message",
            "document_ids": [],
        },
    )

    job_id = response.json()["job_id"]

    max_wait = 10.0
    poll_interval = 0.1
    waited = 0.0
    while waited < max_wait:
        job = jobs_repo.get_job(job_id)
        if job and job["status"] == "completed":
            break
        time.sleep(poll_interval)
        waited += poll_interval

    steps = jobs_repo.list_job_steps(job_id)
    assert len(steps) == 1
    step = steps[0]
    assert step["kind"] == "orchestrator_reasoning"
    assert step["status"] == "succeeded"
    assert step["capability_name"] is None

    cap_execs = jobs_repo.list_capability_executions_by_job_step(step["job_step_id"])
    assert len(cap_execs) == 0


def test_orchestrator_message_row_created(client, temp_db):
    """A messages row exists: role: orchestrator, job_id set."""
    conv_id = conversations_repo.create_conversation()

    response = client.post(
        "/api/v1/jobs",
        json={
            "conversation_id": conv_id,
            "message": "Test message",
            "document_ids": [],
        },
    )

    job_id = response.json()["job_id"]

    max_wait = 10.0
    poll_interval = 0.1
    waited = 0.0
    while waited < max_wait:
        job = jobs_repo.get_job(job_id)
        if job and job["status"] == "completed":
            break
        time.sleep(poll_interval)
        waited += poll_interval

    messages = conversations_repo.list_messages(conv_id)
    orchestrator_messages = [m for m in messages if m["role"] == "orchestrator"]
    assert len(orchestrator_messages) == 1
    assert orchestrator_messages[0]["job_id"] == job_id
    assert "Echo: Test message" in orchestrator_messages[0]["content"]


def test_trace_returns_ordered_events(client, temp_db):
    """GET /jobs/{id}/trace -> events in timestamp order, including job_created and job_completed."""
    conv_id = conversations_repo.create_conversation()

    response = client.post(
        "/api/v1/jobs",
        json={
            "conversation_id": conv_id,
            "message": "Test message",
            "document_ids": [],
        },
    )

    job_id = response.json()["job_id"]

    max_wait = 10.0
    poll_interval = 0.1
    waited = 0.0
    while waited < max_wait:
        job = jobs_repo.get_job(job_id)
        if job and job["status"] == "completed":
            break
        time.sleep(poll_interval)
        waited += poll_interval

    response = client.get(f"/api/v1/jobs/{job_id}/trace")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert "events" in data
    events = data["events"]
    assert len(events) >= 2

    event_types = [e["event_type"] for e in events]
    assert "job_created" in event_types
    assert "job_completed" in event_types

    timestamps = [e["timestamp"] for e in events]
    assert timestamps == sorted(timestamps)


def test_sse_streams_and_closes_on_job_completed(client, temp_db):
    """GET /jobs/{id}/events streams events and closes after job_completed."""
    conv_id = conversations_repo.create_conversation()

    response = client.post(
        "/api/v1/jobs",
        json={
            "conversation_id": conv_id,
            "message": "Test message",
            "document_ids": [],
        },
    )

    job_id = response.json()["job_id"]

    max_wait = 10.0
    poll_interval = 0.1
    waited = 0.0
    while waited < max_wait:
        job = jobs_repo.get_job(job_id)
        if job and job["status"] == "completed":
            break
        time.sleep(poll_interval)
        waited += poll_interval

    # Use replay=true to get historical events since job already completed
    with client.stream("GET", f"/api/v1/jobs/{job_id}/events?replay=true") as sse_response:
        assert sse_response.status_code == 200
        events_received = []
        for line in sse_response.iter_lines():
            if line.startswith("data: "):
                event_data = json.loads(line[6:])
                events_received.append(event_data)
                if event_data["event_type"] == "job_completed":
                    break

        event_types = [e["event_type"] for e in events_received]
        assert "job_completed" in event_types
        assert "job_created" in event_types


def test_unknown_job_returns_404(client, temp_db):
    """GET /jobs/{unknown} -> 404 with error envelope."""
    unknown_id = "00000000-0000-0000-0000-000000000000"

    response = client.get(f"/api/v1/jobs/{unknown_id}")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "error" in data["detail"]
    assert data["detail"]["error"]["code"] == "not_found"
    assert "message" in data["detail"]["error"]

    response = client.get(f"/api/v1/jobs/{unknown_id}/trace")
    assert response.status_code == 404

    response = client.get(f"/api/v1/jobs/{unknown_id}/events")
    assert response.status_code == 404


def test_invalid_conversation_returns_404(client, temp_db):
    """POST /jobs with unknown conversation_id -> 404."""
    unknown_conv = "00000000-0000-0000-0000-000000000000"

    response = client.post(
        "/api/v1/jobs",
        json={
            "conversation_id": unknown_conv,
            "message": "Test message",
            "document_ids": [],
        },
    )

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "error" in data["detail"]
    assert data["detail"]["error"]["code"] == "not_found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])