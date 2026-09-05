"""
Repository for Artifact entities.

Handles CRUD operations for generated output artifacts.
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


def create_artifact(
    job_id: str,
    type: str,
    filename: str,
    storage_path: str,
    size_bytes: int,
) -> str:
    """
    Create a new artifact record.

    Args:
        job_id: The job UUID that produced this artifact.
        type: Artifact type ('docx', 'xlsx', 'pptx').
        filename: Output filename.
        storage_path: Relative path under data/artifacts/.
        size_bytes: File size in bytes.

    Returns:
        The new artifact_id.

    Raises:
        ConstraintError: If job doesn't exist or type is invalid.
    """
    valid_types = ("docx", "xlsx", "pptx")
    if type not in valid_types:
        raise ConstraintError(f"Invalid type: {type}. Must be one of {valid_types}")

    artifact_id = new_id()
    now = _now_iso()

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO artifacts (
                artifact_id, job_id, type, filename,
                storage_path, size_bytes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (artifact_id, job_id, type, filename, storage_path, size_bytes, now),
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise ConstraintError(f"Job not found: {job_id}")
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to create artifact: {e}") from e
    finally:
        conn.close()

    return artifact_id


def get_artifact(artifact_id: str) -> Optional[dict]:
    """
    Get an artifact by ID.

    Args:
        artifact_id: The artifact UUID.

    Returns:
        Artifact dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM artifacts WHERE artifact_id = ?",
            (artifact_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_artifacts_by_job(job_id: str) -> List[dict]:
    """
    List artifacts for a job, ordered by created_at.

    Args:
        job_id: The job UUID.

    Returns:
        List of artifact dicts ordered by created_at ascending.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM artifacts
            WHERE job_id = ?
            ORDER BY created_at ASC
            """,
            (job_id,),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


import sqlite3