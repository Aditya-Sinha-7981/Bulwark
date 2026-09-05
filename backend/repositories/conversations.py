"""
Repository for Conversation and Message entities.

Handles CRUD operations for conversations and their messages.
"""

from datetime import datetime, timezone
from typing import List, Optional

from backend.utils.ids import new_id
from backend.repositories.db import (
    get_connection,
    row_to_dict,
    NotFoundError,
    ConstraintError,
)


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


# Conversation operations

def create_conversation() -> str:
    """
    Create a new conversation.

    Returns:
        The new conversation_id.
    """
    conversation_id = new_id()
    now = _now_iso()

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO conversations (conversation_id, created_at, updated_at) VALUES (?, ?, ?)",
            (conversation_id, now, now),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to create conversation: {e}") from e
    finally:
        conn.close()

    return conversation_id


def get_conversation(conversation_id: str) -> Optional[dict]:
    """
    Get a conversation by ID.

    Args:
        conversation_id: The conversation UUID.

    Returns:
        Conversation dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def update_conversation_timestamp(conversation_id: str) -> bool:
    """
    Update the conversation's updated_at timestamp.

    Args:
        conversation_id: The conversation UUID.

    Returns:
        True if updated, False if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
            (_now_iso(), conversation_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# Message operations

def append_message(
    conversation_id: str,
    role: str,
    content: str,
    job_id: Optional[str] = None,
) -> str:
    """
    Append a message to a conversation.

    Args:
        conversation_id: The conversation UUID.
        role: Message role ('user' or 'orchestrator').
        content: Message content.
        job_id: Optional job UUID (for orchestrator messages produced by a job).

    Returns:
        The new message_id.

    Raises:
        ConstraintError: If conversation doesn't exist or role is invalid.
    """
    if role not in ("user", "orchestrator"):
        raise ConstraintError(f"Invalid role: {role}. Must be 'user' or 'orchestrator'")

    message_id = new_id()
    now = _now_iso()

    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO messages (message_id, conversation_id, role, content, job_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, conversation_id, role, content, job_id, now),
        )
        conn.commit()

        if cursor.rowcount == 0:
            raise ConstraintError(f"Conversation not found: {conversation_id}")

        # Update conversation timestamp
        update_conversation_timestamp(conversation_id)
    except sqlite3.IntegrityError as e:
        raise ConstraintError(f"Failed to append message: {e}") from e
    finally:
        conn.close()

    return message_id


def get_message(message_id: str) -> Optional[dict]:
    """
    Get a message by ID.

    Args:
        message_id: The message UUID.

    Returns:
        Message dict or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM messages WHERE message_id = ?",
            (message_id,),
        )
        row = cursor.fetchone()
        return row_to_dict(row) if row else None
    finally:
        conn.close()


def list_messages(conversation_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
    """
    List messages for a conversation, ordered by created_at.

    Args:
        conversation_id: The conversation UUID.
        limit: Maximum number of messages to return.
        offset: Number of messages to skip.

    Returns:
        List of message dicts ordered by created_at ascending.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT * FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
            """,
            (conversation_id, limit, offset),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def count_messages(conversation_id: str) -> int:
    """
    Count messages in a conversation.

    Args:
        conversation_id: The conversation UUID.

    Returns:
        Number of messages.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()


import sqlite3