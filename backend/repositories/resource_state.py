"""
Repository for ResourceState entity.

Handles CRUD operations for resource state tracking (live table for model lifecycle).
"""

from datetime import datetime, timezone
from typing import List, Optional

from backend.repositories.db import (
    get_connection,
    row_to_dict,
    ConstraintError,
)


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def upsert_resource_state(
    resource_type: str,
    model_identifier: str,
    status: str = "unloaded",
    loaded_at: Optional[str] = None,
    last_used_at: Optional[str] = None,
) -> None:
    """
    Upsert a resource state row.

    Args:
        resource_type: Resource type (PK) - 'reasoning', 'code_generation', 'vision', 'embedding'.
        model_identifier: Currently configured/loaded model identifier.
        status: Resource status ('unloaded', 'loading', 'loaded').
        loaded_at: Load timestamp.
        last_used_at: Last used timestamp.

    Raises:
        ConstraintError: If status is invalid.
    """
    valid_statuses = ("unloaded", "loading", "loaded")
    if status not in valid_statuses:
        raise ConstraintError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    valid_resource_types = ("reasoning", "code_generation", "vision", "embedding")
    if resource_type not in valid_resource_types:
        raise ConstraintError(f"Invalid resource_type: {resource_type}. Must be one of {valid_resource_types}")

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO resource_state (
                resource_type, model_identifier, status, loaded_at, last_used_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(resource_type) DO UPDATE SET
                model_identifier = excluded.model_identifier,
                status = excluded.status,
                loaded_at = excluded.loaded_at,
                last_used_at = excluded.last_used_at
            """,
            (resource_type, model_identifier, status, loaded_at, last_used_at),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to upsert resource state: {e}") from e
    finally:
        conn.close()


def get_resource_state(resource_type: str) -> Optional[dict]:
    """
    Get a resource state by resource_type.

    Args:
        resource_type: The resource type (PK).

    Returns:
        Resource state dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM resource_state WHERE resource_type = ?",
            (resource_type,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_resource_states() -> List[dict]:
    """
    List all resource states.

    Returns:
        List of resource state dicts ordered by resource_type.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM resource_state ORDER BY resource_type"
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def set_resource_status(
    resource_type: str,
    status: str,
    loaded_at: Optional[str] = None,
    last_used_at: Optional[str] = None,
) -> bool:
    """
    Update resource status and timestamps.

    Args:
        resource_type: The resource type (PK).
        status: New status ('unloaded', 'loading', 'loaded').
        loaded_at: Load timestamp (optional).
        last_used_at: Last used timestamp (optional).

    Returns:
        True if updated, False if not found.

    Raises:
        ConstraintError: If status is invalid.
    """
    valid_statuses = ("unloaded", "loading", "loaded")
    if status not in valid_statuses:
        raise ConstraintError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    updates = ["status = ?"]
    params = [status]

    if loaded_at is not None:
        updates.append("loaded_at = ?")
        params.append(loaded_at)
    if last_used_at is not None:
        updates.append("last_used_at = ?")
        params.append(last_used_at)

    params.append(resource_type)

    conn = get_connection()
    try:
        cursor = conn.execute(
            f"UPDATE resource_state SET {', '.join(updates)} WHERE resource_type = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


import sqlite3