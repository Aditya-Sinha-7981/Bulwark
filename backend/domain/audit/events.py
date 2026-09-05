"""
Audit Event Subsystem - Single Write Path

Implements the single write path for audit events: one function that both inserts
an audit_events row and pushes the same event object to any open SSE subscriptions
for that job_id. Per docs/audit.md and AGENTS.md §6 rule 7.

Event types are constrained to the enum in docs/audit.md.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from backend.repositories.audit_events import insert_event, query_by_job_id
from backend.utils.ids import new_id


logger = logging.getLogger(__name__)


VALID_EVENT_TYPES = frozenset({
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
})

_REQUIRED_PAYLOAD_KEYS: Dict[str, frozenset[str]] = {
    "job_created": frozenset({"conversation_id", "input_message"}),
    "orchestrator_step": frozenset({"action"}),
    "policy_decision": frozenset({"capability", "decision", "reason"}),
    "tool_invoked": frozenset({"capability", "arguments"}),
    "model_invoked": frozenset({"resource_type", "model_identifier", "prompt_tokens", "completion_tokens", "duration_ms"}),
    "resource_loaded": frozenset({"resource_type", "model_identifier", "duration_ms"}),
    "resource_unloaded": frozenset({"resource_type", "model_identifier", "reason"}),
    "artifact_created": frozenset({"artifact_id", "type", "filename"}),
    "error": frozenset({"component", "message", "context"}),
    "job_completed": frozenset({"status", "duration_ms"}),
    "network_check": frozenset({"external_connections_detected", "checked_at"}),
}


_subscribers: Dict[str, Set[asyncio.Queue]] = {}
_subscribers_lock = asyncio.Lock()
_MAX_QUEUE_SIZE = 100


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _validate_event_type(event_type: str) -> None:
    """Validate event_type is in the allowed enum."""
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"Invalid event_type '{event_type}'. Must be one of: {sorted(VALID_EVENT_TYPES)}"
        )


def _validate_payload(event_type: str, payload: Dict[str, Any]) -> None:
    """Validate payload has required keys for the event type (minimal check)."""
    required = _REQUIRED_PAYLOAD_KEYS.get(event_type)
    if required is not None:
        missing = required - set(payload.keys())
        if missing:
            logger.warning(
                "Payload for event_type '%s' missing recommended keys: %s",
                event_type,
                sorted(missing),
            )


def _validate_job_id(event_type: str, job_id: Optional[str]) -> None:
    """Validate job_id is None only for network_check events."""
    if event_type == "network_check":
        if job_id is not None:
            raise ValueError("network_check events must have job_id=None")
    else:
        if job_id is None:
            raise ValueError(f"Event type '{event_type}' requires a job_id")


async def subscribe(job_id: str) -> asyncio.Queue:
    """
    Subscribe to audit events for a job_id.

    Returns an asyncio.Queue that will receive event dicts.
    Queue is bounded; if full, the subscriber will be dropped.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=_MAX_QUEUE_SIZE)
    async with _subscribers_lock:
        if job_id not in _subscribers:
            _subscribers[job_id] = set()
        _subscribers[job_id].add(queue)
    return queue


async def unsubscribe(job_id: str, queue: asyncio.Queue) -> None:
    """Unsubscribe a queue from job_id events."""
    async with _subscribers_lock:
        if job_id in _subscribers:
            _subscribers[job_id].discard(queue)
            if not _subscribers[job_id]:
                del _subscribers[job_id]


async def _push_to_subscribers(job_id: Optional[str], event: Dict[str, Any]) -> None:
    """Push event to all subscribers for job_id. Drop slow subscribers."""
    if job_id is None:
        return

    async with _subscribers_lock:
        queues = _subscribers.get(job_id, set()).copy()

    for queue in queues:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Dropping slow subscriber for job_id=%s (queue full)", job_id)
            await unsubscribe(job_id, queue)


async def emit(
    event_type: str,
    component: str,
    payload: Dict[str, Any],
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Emit an audit event: persist to DB and push to SSE subscribers.

    This is the single write path for audit events. The insert and push
    happen in the same call so they cannot drift (AGENTS.md §6 rule 7).

    Args:
        event_type: Event type from docs/audit.md enum.
        component: Component that emitted the event (e.g., "api", "orchestrator").
        payload: Event payload dict (will be JSON serialized).
        job_id: Job UUID, or None for job-independent events (only network_check).

    Returns:
        The event dict that was persisted and pushed.

    Raises:
        ValueError: If event_type is invalid or job_id constraint violated.
        ConstraintError: If job_id references non-existent job (from repository).
    """
    _validate_event_type(event_type)
    _validate_job_id(event_type, job_id)
    _validate_payload(event_type, payload)

    event_id = new_id()
    timestamp = _now_iso()
    payload_json = json.dumps(payload, separators=(",", ":"))

    insert_event(
        job_id=job_id,
        event_type=event_type,
        component=component,
        payload=payload_json,
        timestamp=timestamp,
    )

    event = {
        "event_id": event_id,
        "job_id": job_id,
        "event_type": event_type,
        "component": component,
        "timestamp": timestamp,
        "payload": payload,
    }

    await _push_to_subscribers(job_id, event)

    return event


async def get_events_for_job(job_id: str, limit: int = 1000, offset: int = 0) -> list[Dict[str, Any]]:
    """Get persisted events for a job_id (for late-join replay)."""
    rows = query_by_job_id(job_id, limit=limit, offset=offset)
    events = []
    for row in rows:
        events.append({
            "event_id": row["event_id"],
            "job_id": row["job_id"],
            "event_type": row["event_type"],
            "component": row["component"],
            "timestamp": row["timestamp"],
            "payload": json.loads(row["payload"]),
        })
    return events