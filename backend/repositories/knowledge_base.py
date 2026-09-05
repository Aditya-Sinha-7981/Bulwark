"""
Repository for KnowledgeBaseDocument entities.

Handles CRUD operations for knowledge base documents.
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


def create_kb_document(
    title: str,
    storage_path: str,
    category: Optional[str] = None,
    status: str = "ingesting",
    chunk_count: int = 0,
) -> str:
    """
    Create a new knowledge base document record.

    Args:
        title: Document title.
        storage_path: Relative path under data/uploads/ (source).
        category: Optional category.
        status: Initial status ('ingesting', 'ready', 'failed').
        chunk_count: Initial chunk count.

    Returns:
        The new kb_document_id.

    Raises:
        ConstraintError: If status is invalid.
    """
    valid_statuses = ("ingesting", "ready", "failed")
    if status not in valid_statuses:
        raise ConstraintError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    kb_document_id = new_id()

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO knowledge_base_documents (
                kb_document_id, title, category, status,
                storage_path, chunk_count, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (kb_document_id, title, category, status, storage_path, chunk_count, None),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to create KB document: {e}") from e
    finally:
        conn.close()

    return kb_document_id


def get_kb_document(kb_document_id: str) -> Optional[dict]:
    """
    Get a knowledge base document by ID.

    Args:
        kb_document_id: The KB document UUID.

    Returns:
        KB document dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM knowledge_base_documents WHERE kb_document_id = ?",
            (kb_document_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def update_kb_document(
    kb_document_id: str,
    status: Optional[str] = None,
    chunk_count: Optional[int] = None,
    ingested_at: Optional[str] = None,
) -> bool:
    """
    Update knowledge base document fields.

    Args:
        kb_document_id: The KB document UUID.
        status: New status ('ingesting', 'ready', 'failed').
        chunk_count: New chunk count.
        ingested_at: Ingestion completion timestamp.

    Returns:
        True if updated, False if not found.

    Raises:
        ConstraintError: If status is invalid.
    """
    if status is not None:
        valid_statuses = ("ingesting", "ready", "failed")
        if status not in valid_statuses:
            raise ConstraintError(f"Invalid status: {status}. Must be one of {valid_statuses}")

    updates = []
    params = []

    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if chunk_count is not None:
        updates.append("chunk_count = ?")
        params.append(chunk_count)
    if ingested_at is not None:
        updates.append("ingested_at = ?")
        params.append(ingested_at)

    if not updates:
        return False

    params.append(kb_document_id)

    conn = get_connection()
    try:
        cursor = conn.execute(
            f"UPDATE knowledge_base_documents SET {', '.join(updates)} WHERE kb_document_id = ?",
            params,
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_kb_documents(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[dict]:
    """
    List knowledge base documents, optionally filtered by status.

    Args:
        status: Optional status filter.
        limit: Maximum number of documents to return.
        offset: Number of documents to skip.

    Returns:
        List of KB document dicts ordered by kb_document_id.
    """
    conn = get_connection()
    try:
        if status is not None:
            cursor = conn.execute(
                """
                SELECT * FROM knowledge_base_documents
                WHERE status = ?
                ORDER BY kb_document_id
                LIMIT ? OFFSET ?
                """,
                (status, limit, offset),
            )
        else:
            cursor = conn.execute(
                """
                SELECT * FROM knowledge_base_documents
                ORDER BY kb_document_id
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def delete_kb_document(kb_document_id: str) -> bool:
    """
    Delete a knowledge base document.

    Args:
        kb_document_id: The KB document UUID.

    Returns:
        True if deleted, False if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM knowledge_base_documents WHERE kb_document_id = ?",
            (kb_document_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


import sqlite3