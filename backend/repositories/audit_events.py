"""
Repository for AuditEvent entities.

Handles CRUD operations for audit events - the single source of truth.
"""

from datetime import datetime, timezone
from typing import List, Optional

from backend.utils.ids import new_id
from backend.repositories.db import (
    get_connection,
    row_to_dict,
    ConstraintError,
)


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def insert_event(
    job_id: Optional[str],
    event_type: str,
    component: str,
    payload: str,
    timestamp: Optional[str] = None,
) -> str:
    """
    Insert a new audit event.

    Args:
        job_id: Job UUID (nullable for job-independent events).
        event_type: Event type (see docs/audit.md for enum).
        component: Component that emitted the event.
        payload: JSON payload.
        timestamp: Optional timestamp (defaults to now).

    Returns:
        The new event_id.

    Raises:
        ConstraintError: If job_id references non-existent job.
    """
    event_id = new_id()
    ts = timestamp or _now_iso()

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO audit_events (
                event_id, job_id, event_type, component, timestamp, payload
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, job_id, event_type, component, ts, payload),
        )
        conn.commit()

        if cursor.rowcount == 0 and job_id is not None:
            raise ConstraintError(f"Job not found: {job_id}")
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to insert audit event: {e}") from e
    finally:
        conn.close()

    return event_id


def get_event(event_id: str) -> Optional[dict]:
    """
    Get an audit event by ID.

    Args:
        event_id: The event UUID.

    Returns:
        Audit event dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM audit_events WHERE event_id = ?",
            (event_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def query_by_job_id(job_id: str, limit: int = 1000, offset: int = 0) -> List[dict]:
    """
    Query audit events by job_id, ordered by timestamp.

    Args:
        job_id: The job UUID.
        limit: Maximum number of events to return.
        offset: Number of events to skip.

    Returns:
        List of audit event dicts ordered by timestamp ascending.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM audit_events
            WHERE job_id = ?
            ORDER BY timestamp ASC
            LIMIT ? OFFSET ?
            """,
            (job_id, limit, offset),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def query_by_event_type(event_type: str, limit: int = 1000, offset: int = 0) -> List[dict]:
    """
    Query audit events by event_type, ordered by timestamp.

    Args:
        event_type: Event type to filter by.
        limit: Maximum number of events to return.
        offset: Number of events to skip.

    Returns:
        List of audit event dicts ordered by timestamp ascending.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM audit_events
            WHERE event_type = ?
            ORDER BY timestamp ASC
            LIMIT ? OFFSET ?
            """,
            (event_type, limit, offset),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def count_events_by_job(job_id: str) -> int:
    """
    Count audit events for a job.

    Args:
        job_id: The job UUID.

    Returns:
        Number of events.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM audit_events WHERE job_id = ?",
            (job_id,),
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()


import sqlite3