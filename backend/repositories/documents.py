"""
Repository for Document entities.

Handles CRUD operations for uploaded input documents.
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


def create_document(
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: str,
) -> str:
    """
    Create a new document record.

    Args:
        filename: Original filename.
        content_type: MIME content type.
        size_bytes: File size in bytes.
        storage_path: Relative path under data/uploads/.

    Returns:
        The new document_id.
    """
    document_id = new_id()
    now = _now_iso()

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO documents (
                document_id, filename, content_type, size_bytes,
                storage_path, uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (document_id, filename, content_type, size_bytes, storage_path, now),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to create document: {e}") from e
    finally:
        conn.close()

    return document_id


def get_document(document_id: str) -> Optional[dict]:
    """
    Get a document by ID.

    Args:
        document_id: The document UUID.

    Returns:
        Document dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM documents WHERE document_id = ?",
            (document_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_documents(limit: int = 100, offset: int = 0) -> List[dict]:
    """
    List documents, ordered by uploaded_at descending.

    Args:
        limit: Maximum number of documents to return.
        offset: Number of documents to skip.

    Returns:
        List of document dicts ordered by uploaded_at descending.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM documents
            ORDER BY uploaded_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


import sqlite3