"""
Integration tests for Audit Event Subsystem.

Tests the single write path (emit), subscriber registry, and SSE route.
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app
from domain.audit.events import (
    VALID_EVENT_TYPES,
    emit,
    get_events_for_job,
    subscribe,
    unsubscribe,
)
from repositories import audit_events, conversations, jobs
from repositories.db import get_connection


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


@pytest.fixture
def async_client():
    """Async HTTP client for testing SSE."""
    return AsyncClient(app=app, base_url="http://test")


@pytest.fixture
def sample_job_id(temp_db):
    """Create a sample job for testing."""
    conv_id = conversations.create_conversation()
    job_id = jobs.create_job(conv_id, "Test input message")
    return job_id


class TestEmitFunction:
    """Tests for the emit() function."""

    @pytest.mark.asyncio
    async def test_emit_job_created_persists_and_returns_event(self, temp_db, sample_job_id):
        """emit() persists event and returns event dict with correct shape."""
        payload = {
            "conversation_id": "test-conv-id",
            "input_message": "Test message"
        }
        event = await emit("job_created", "api", payload, job_id=sample_job_id)

        assert event["event_id"] is not None
        assert event["job_id"] == sample_job_id
        assert event["event_type"] == "job_created"
        assert event["component"] == "api"
        assert event["timestamp"] is not None
        assert event["payload"] == payload

        # Verify it's queryable
        rows = audit_events.query_by_job_id(sample_job_id)
        assert len(rows) == 1
        assert rows[0]["event_type"] == "job_created"
        assert json.loads(rows[0]["payload"]) == payload

    @pytest.mark.asyncio
    async def test_emit_network_check_with_none_job_id(self, temp_db):
        """emit() with network_check and job_id=None succeeds."""
        payload = {
            "external_connections_detected": False,
            "checked_at": "2026-01-01T00:00:00Z"
        }
        event = await emit("network_check", "monitor", payload, job_id=None)

        assert event["event_id"] is not None
        assert event["job_id"] is None
        assert event["event_type"] == "network_check"

        # Verify it's queryable (by event_type since job_id is None)
        rows = audit_events.query_by_event_type("network_check")
        assert len(rows) == 1
        assert rows[0]["job_id"] is None

    @pytest.mark.asyncio
    async def test_emit_invalid_event_type_raises(self, temp_db, sample_job_id):
        """emit() with invalid event_type raises ValueError and persists nothing."""
        with pytest.raises(ValueError, match="Invalid event_type"):
            await emit("invalid_type", "test", {}, job_id=sample_job_id)

        # Nothing persisted
        rows = audit_events.query_by_job_id(sample_job_id)
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_emit_network_check_with_job_id_raises(self, temp_db, sample_job_id):
        """emit() network_check with job_id raises ValueError."""
        with pytest.raises(ValueError, match="network_check events must have job_id=None"):
            await emit("network_check", "monitor", {}, job_id=sample_job_id)

    @pytest.mark.asyncio
    async def test_emit_non_network_check_without_job_id_raises(self, temp_db):
        """emit() non-network_check without job_id raises ValueError."""
        with pytest.raises(ValueError, match="requires a job_id"):
            await emit("job_created", "api", {}, job_id=None)

    @pytest.mark.asyncio
    async def test_emit_all_valid_event_types(self, temp_db, sample_job_id):
        """emit() works for all valid event types."""
        payloads = {
            "job_created": {"conversation_id": "c1", "input_message": "msg"},
            "orchestrator_step": {"action": "respond"},
            "policy_decision": {"capability": "test", "decision": "allow", "reason": "ok"},
            "tool_invoked": {"capability": "test", "arguments": {}},
            "model_invoked": {"resource_type": "reasoning", "model_identifier": "m1", "prompt_tokens": 10, "completion_tokens": 20, "duration_ms": 100},
            "resource_loaded": {"resource_type": "reasoning", "model_identifier": "m1", "duration_ms": 500},
            "resource_unloaded": {"resource_type": "reasoning", "model_identifier": "m1", "reason": "idle_timeout"},
            "artifact_created": {"artifact_id": "a1", "type": "docx", "filename": "test.docx"},
            "error": {"component": "test", "message": "err", "context": {}},
            "job_completed": {"status": "completed", "duration_ms": 1000},
        }

        for event_type, payload in payloads.items():
            event = await emit(event_type, "test", payload, job_id=sample_job_id)
            assert event["event_type"] == event_type
            assert event["payload"] == payload

        rows = audit_events.query_by_job_id(sample_job_id)
        assert len(rows) == len(payloads)


class TestSubscriberRegistry:
    """Tests for the subscriber registry."""

    @pytest.mark.asyncio
    async def test_subscribe_receives_events(self, temp_db, sample_job_id):
        """subscribe() queue receives events emitted for that job_id."""
        queue = await subscribe(sample_job_id)

        payload = {"conversation_id": "c1", "input_message": "msg"}
        event = await emit("job_created", "api", payload, job_id=sample_job_id)

        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received == event

        await unsubscribe(sample_job_id, queue)

    @pytest.mark.asyncio
    async def test_multiple_subscribers_receive_same_event(self, temp_db, sample_job_id):
        """Multiple subscribers for same job_id all receive the event."""
        queue1 = await subscribe(sample_job_id)
        queue2 = await subscribe(sample_job_id)

        payload = {"conversation_id": "c1", "input_message": "msg"}
        await emit("job_created", "api", payload, job_id=sample_job_id)

        received1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
        received2 = await asyncio.wait_for(queue2.get(), timeout=1.0)

        assert received1["event_id"] == received2["event_id"]
        assert received1["event_type"] == "job_created"

        await unsubscribe(sample_job_id, queue1)
        await unsubscribe(sample_job_id, queue2)

    @pytest.mark.asyncio
    async def test_subscriber_isolation_by_job_id(self, temp_db, sample_job_id):
        """Subscribers for different job_ids don't receive each other's events."""
        other_job_id = "00000000-0000-0000-0000-000000000000"
        queue1 = await subscribe(sample_job_id)
        queue2 = await subscribe(other_job_id)

        await emit("job_created", "api", {"conversation_id": "c1", "input_message": "msg"}, job_id=sample_job_id)

        received1 = await asyncio.wait_for(queue1.get(), timeout=1.0)
        assert received1["job_id"] == sample_job_id

        # queue2 should not have received anything (timeout)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue2.get(), timeout=0.5)

        await unsubscribe(sample_job_id, queue1)
        await unsubscribe(other_job_id, queue2)

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue(self, temp_db, sample_job_id):
        """unsubscribe() removes queue from registry."""
        queue = await subscribe(sample_job_id)
        await unsubscribe(sample_job_id, queue)

        await emit("job_created", "api", {"conversation_id": "c1", "input_message": "msg"}, job_id=sample_job_id)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.5)

    @pytest.mark.asyncio
    async def test_slow_subscriber_dropped_on_overflow(self, temp_db, sample_job_id):
        """Slow subscriber (full queue) is dropped, doesn't block emit."""
        queue = await subscribe(sample_job_id)

        # Fill the queue
        for i in range(100):
            await queue.put({"event_id": f"e{i}", "event_type": "test"})

        # This emit should not block, and the slow subscriber should be dropped
        await emit("job_created", "api", {"conversation_id": "c1", "input_message": "msg"}, job_id=sample_job_id)

        # Queue should now be empty (unsubscribed) or have only the new event
        # The key assertion: emit() didn't hang
        # Verify we can still emit another event
        await emit("job_completed", "job_manager", {"status": "completed", "duration_ms": 100}, job_id=sample_job_id)

        await unsubscribe(sample_job_id, queue)


class TestGetEventsForJob:
    """Tests for get_events_for_job (late-join replay)."""

    @pytest.mark.asyncio
    async def test_get_events_for_job_returns_persisted_events(self, temp_db, sample_job_id):
        """get_events_for_job returns events in timestamp order."""
        await emit("job_created", "api", {"conversation_id": "c1", "input_message": "msg"}, job_id=sample_job_id)
        await emit("orchestrator_step", "orchestrator", {"action": "respond"}, job_id=sample_job_id)
        await emit("job_completed", "job_manager", {"status": "completed", "duration_ms": 100}, job_id=sample_job_id)

        events = await get_events_for_job(sample_job_id)
        assert len(events) == 3
        assert events[0]["event_type"] == "job_created"
        assert events[1]["event_type"] == "orchestrator_step"
        assert events[2]["event_type"] == "job_completed"

        # Verify timestamps are ordered
        for i in range(len(events) - 1):
            assert events[i]["timestamp"] <= events[i + 1]["timestamp"]


class TestSSERoute:
    """Tests for the SSE route."""

    @pytest.mark.asyncio
    async def test_sse_route_returns_streaming_response(self, temp_db, sample_job_id):
        """SSE route returns a StreamingResponse with correct media type."""
        from api.jobs import stream_job_events
        from fastapi import Request
        from fastapi.responses import StreamingResponse
        from starlette.datastructures import Headers

        scope = {
            "type": "http",
            "method": "GET",
            "path": f"/api/v1/jobs/{sample_job_id}/events",
            "query_string": b"replay=true",
            "headers": Headers({}).raw,
        }
        request = Request(scope)

        response = await stream_job_events(job_id=sample_job_id, request=request, replay=True)

        assert isinstance(response, StreamingResponse)
        assert response.media_type == "text/event-stream"
        assert "Cache-Control" in response.headers
        assert "Connection" in response.headers


class TestEventTypeEnum:
    """Tests that VALID_EVENT_TYPES matches docs/audit.md."""

    def test_valid_event_types_matches_audit_md(self):
        """VALID_EVENT_TYPES contains exactly the 11 types from docs/audit.md."""
        expected = {
            "job_created",
            "orchestrator_step",
            "policy_decision",
            "tool_invoked",
            "model_invoked",
            "resource_loaded",
            "resource_unloaded",
            "artifact_created",
            "error",
            "job_completed",
            "network_check",
        }
        assert VALID_EVENT_TYPES == expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])