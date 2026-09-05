"""
Unit tests for conversations repository.
"""

import tempfile
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.repositories import conversations, jobs
from backend.repositories.db import get_connection, ConstraintError
from backend.utils.ids import new_id


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    # Run init script against temp DB
    import scripts.init_db as init_db
    original_get_db_path = init_db.get_db_path
    init_db.get_db_path = lambda: db_path
    init_db.main()
    init_db.get_db_path = original_get_db_path

    # Patch the connection function
    original_get_connection = conversations.get_connection
    conversations.get_connection = lambda: get_connection(db_path)

    yield db_path

    # Cleanup
    conversations.get_connection = original_get_connection
    if db_path.exists():
        db_path.unlink()


def test_create_conversation(temp_db):
    """Test creating a conversation."""
    conv_id = conversations.create_conversation()
    assert conv_id is not None
    assert len(conv_id) == 36  # UUID length


def test_get_conversation(temp_db):
    """Test getting a conversation."""
    conv_id = conversations.create_conversation()
    conv = conversations.get_conversation(conv_id)
    assert conv is not None
    assert conv["conversation_id"] == conv_id
    assert "created_at" in conv
    assert "updated_at" in conv


def test_get_nonexistent_conversation(temp_db):
    """Test getting a non-existent conversation returns None."""
    conv = conversations.get_conversation(new_id())
    assert conv is None


def test_append_message(temp_db):
    """Test appending a message."""
    conv_id = conversations.create_conversation()
    msg_id = conversations.append_message(conv_id, "user", "Hello, world!")
    assert msg_id is not None

    msg = conversations.get_message(msg_id)
    assert msg is not None
    assert msg["conversation_id"] == conv_id
    assert msg["role"] == "user"
    assert msg["content"] == "Hello, world!"
    assert msg["job_id"] is None


def test_append_message_with_job_id(temp_db):
    """Test appending an orchestrator message with job_id."""
    from backend.repositories import jobs
    original_jobs_conn = jobs.get_connection
    jobs.get_connection = lambda: get_connection(temp_db)
    try:
        conv_id = conversations.create_conversation()
        job_id = jobs.create_job(conv_id, "Input")
        msg_id = conversations.append_message(conv_id, "orchestrator", "Response", job_id=job_id)

        msg = conversations.get_message(msg_id)
        assert msg["role"] == "orchestrator"
        assert msg["job_id"] == job_id
    finally:
        jobs.get_connection = original_jobs_conn


def test_append_message_invalid_role(temp_db):
    """Test appending message with invalid role raises error."""
    conv_id = conversations.create_conversation()
    with pytest.raises(ConstraintError):
        conversations.append_message(conv_id, "invalid", "content")


def test_append_message_nonexistent_conversation(temp_db):
    """Test appending to non-existent conversation raises error."""
    with pytest.raises(ConstraintError):
        conversations.append_message(new_id(), "user", "content")


def test_list_messages(temp_db):
    """Test listing messages in order."""
    conv_id = conversations.create_conversation()
    conversations.append_message(conv_id, "user", "First")
    conversations.append_message(conv_id, "orchestrator", "Second")
    conversations.append_message(conv_id, "user", "Third")

    messages = conversations.list_messages(conv_id)
    assert len(messages) == 3
    assert messages[0]["content"] == "First"
    assert messages[1]["content"] == "Second"
    assert messages[2]["content"] == "Third"

    # Check ordering by created_at
    for i in range(len(messages) - 1):
        assert messages[i]["created_at"] <= messages[i + 1]["created_at"]


def test_list_messages_pagination(temp_db):
    """Test message pagination."""
    conv_id = conversations.create_conversation()
    for i in range(5):
        conversations.append_message(conv_id, "user", f"Message {i}")

    page1 = conversations.list_messages(conv_id, limit=2, offset=0)
    page2 = conversations.list_messages(conv_id, limit=2, offset=2)
    page3 = conversations.list_messages(conv_id, limit=2, offset=4)

    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1
    assert page1[0]["content"] == "Message 0"
    assert page2[0]["content"] == "Message 2"
    assert page3[0]["content"] == "Message 4"


def test_count_messages(temp_db):
    """Test counting messages."""
    conv_id = conversations.create_conversation()
    assert conversations.count_messages(conv_id) == 0

    conversations.append_message(conv_id, "user", "One")
    assert conversations.count_messages(conv_id) == 1

    conversations.append_message(conv_id, "user", "Two")
    assert conversations.count_messages(conv_id) == 2


def test_update_conversation_timestamp(temp_db):
    """Test updating conversation timestamp."""
    conv_id = conversations.create_conversation()
    conv = conversations.get_conversation(conv_id)
    original_updated = conv["updated_at"]

    # Small delay to ensure timestamp changes
    import time
    time.sleep(0.01)

    conversations.update_conversation_timestamp(conv_id)
    conv = conversations.get_conversation(conv_id)
    assert conv["updated_at"] != original_updated


if __name__ == "__main__":
    pytest.main([__file__, "-v"])