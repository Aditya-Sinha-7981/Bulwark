"""
Unit tests for audit_events repository.
"""

import tempfile
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.repositories import audit_events, jobs, conversations
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

    original_audit_conn = audit_events.get_connection
    original_jobs_conn = jobs.get_connection
    original_conv_conn = conversations.get_connection

    audit_events.get_connection = lambda: get_connection(db_path)
    jobs.get_connection = lambda: get_connection(db_path)
    conversations.get_connection = lambda: get_connection(db_path)

    yield db_path

    audit_events.get_connection = original_audit_conn
    jobs.get_connection = original_jobs_conn
    conversations.get_connection = original_conv_conn
    if db_path.exists():
        db_path.unlink()


def test_insert_event(temp_db):
    """Test inserting an audit event."""
    event_id = audit_events.insert_event(
        job_id=None,
        event_type="network_check",
        component="monitoring",
        payload=json.dumps({"external_connections_detected": False})
    )
    assert event_id is not None


def test_insert_event_with_job(temp_db):
    """Test inserting audit event with job_id."""
    conv_id = conversations.create_conversation()
    job_id = jobs.create_job(conv_id, "Input")

    event_id = audit_events.insert_event(
        job_id=job_id,
        event_type="job_created",
        component="api",
        payload=json.dumps({"conversation_id": conv_id, "input_message": "Input"})
    )
    assert event_id is not None


def test_insert_event_invalid_job(temp_db):
    """Test inserting event with invalid job_id raises error."""
    with pytest.raises(ConstraintError):
        audit_events.insert_event(
            job_id=new_id(),
            event_type="test",
            component="test",
            payload="{}"
        )


def test_get_event(temp_db):
    """Test getting an event."""
    event_id = audit_events.insert_event(
        job_id=None,
        event_type="test_event",
        component="test_component",
        payload=json.dumps({"key": "value"})
    )
    event = audit_events.get_event(event_id)
    assert event is not None
    assert event["event_id"] == event_id
    assert event["event_type"] == "test_event"
    assert event["component"] == "test_component"
    assert event["payload"] == '{"key": "value"}'


def test_get_nonexistent_event(temp_db):
    """Test getting non-existent event returns None."""
    event = audit_events.get_event(new_id())
    assert event is None


def test_query_by_job_id(temp_db):
    """Test querying events by job_id."""
    conv_id = conversations.create_conversation()
    job_id = jobs.create_job(conv_id, "Input")

    audit_events.insert_event(job_id, "job_created", "api", "{}")
    audit_events.insert_event(job_id, "orchestrator_step", "orchestrator", "{}")
    audit_events.insert_event(job_id, "job_completed", "job_manager", "{}")

    events = audit_events.query_by_job_id(job_id)
    assert len(events) == 3

    # Should be ordered by timestamp
    for i in range(len(events) - 1):
        assert events[i]["timestamp"] <= events[i + 1]["timestamp"]


def test_query_by_event_type(temp_db):
    """Test querying events by event_type."""
    audit_events.insert_event(None, "network_check", "monitor", "{}")
    audit_events.insert_event(None, "network_check", "monitor", "{}")
    audit_events.insert_event(None, "error", "api", "{}")

    network_events = audit_events.query_by_event_type("network_check")
    assert len(network_events) == 2

    error_events = audit_events.query_by_event_type("error")
    assert len(error_events) == 1


def test_query_by_job_id_pagination(temp_db):
    """Test pagination for job events."""
    conv_id = conversations.create_conversation()
    job_id = jobs.create_job(conv_id, "Input")

    for i in range(5):
        audit_events.insert_event(job_id, f"event_{i}", "test", "{}")

    page1 = audit_events.query_by_job_id(job_id, limit=2, offset=0)
    page2 = audit_events.query_by_job_id(job_id, limit=2, offset=2)
    page3 = audit_events.query_by_job_id(job_id, limit=2, offset=4)

    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1


def test_count_events_by_job(temp_db):
    """Test counting events for a job."""
    conv_id = conversations.create_conversation()
    job_id = jobs.create_job(conv_id, "Input")

    assert audit_events.count_events_by_job(job_id) == 0

    audit_events.insert_event(job_id, "e1", "c", "{}")
    assert audit_events.count_events_by_job(job_id) == 1

    audit_events.insert_event(job_id, "e2", "c", "{}")
    assert audit_events.count_events_by_job(job_id) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])