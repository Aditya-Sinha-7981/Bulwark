"""
Unit tests for knowledge_base repository.
"""

import tempfile
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.repositories import knowledge_base
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

    original_get_connection = knowledge_base.get_connection
    knowledge_base.get_connection = lambda: get_connection(db_path)

    yield db_path

    knowledge_base.get_connection = original_get_connection
    if db_path.exists():
        db_path.unlink()


def test_create_kb_document(temp_db):
    """Test creating a KB document."""
    kb_id = knowledge_base.create_kb_document(
        title="Test Document",
        storage_path="uploads/test.pdf"
    )
    assert kb_id is not None


def test_create_kb_document_with_category(temp_db):
    """Test creating KB document with category."""
    kb_id = knowledge_base.create_kb_document(
        title="Test Document",
        storage_path="uploads/test.pdf",
        category="SOPs"
    )
    kb = knowledge_base.get_kb_document(kb_id)
    assert kb["category"] == "SOPs"


def test_create_kb_document_invalid_status(temp_db):
    """Test creating KB document with invalid status."""
    with pytest.raises(ConstraintError):
        knowledge_base.create_kb_document(
            title="Test",
            storage_path="uploads/test.pdf",
            status="invalid"
        )


def test_get_kb_document(temp_db):
    """Test getting a KB document."""
    kb_id = knowledge_base.create_kb_document(
        title="Test Document",
        storage_path="uploads/test.pdf"
    )
    kb = knowledge_base.get_kb_document(kb_id)
    assert kb is not None
    assert kb["kb_document_id"] == kb_id
    assert kb["title"] == "Test Document"
    assert kb["storage_path"] == "uploads/test.pdf"
    assert kb["status"] == "ingesting"
    assert kb["chunk_count"] == 0


def test_get_nonexistent_kb_document(temp_db):
    """Test getting non-existent KB document returns None."""
    kb = knowledge_base.get_kb_document(new_id())
    assert kb is None


def test_update_kb_document(temp_db):
    """Test updating KB document."""
    kb_id = knowledge_base.create_kb_document(
        title="Test Document",
        storage_path="uploads/test.pdf"
    )

    knowledge_base.update_kb_document(
        kb_id,
        status="ready",
        chunk_count=10,
        ingested_at="2024-01-01T00:00:00"
    )
    kb = knowledge_base.get_kb_document(kb_id)
    assert kb["status"] == "ready"
    assert kb["chunk_count"] == 10
    assert kb["ingested_at"] == "2024-01-01T00:00:00"


def test_update_kb_document_invalid_status(temp_db):
    """Test updating KB document with invalid status."""
    kb_id = knowledge_base.create_kb_document("Test", "path")
    with pytest.raises(ConstraintError):
        knowledge_base.update_kb_document(kb_id, status="invalid")


def test_list_kb_documents(temp_db):
    """Test listing KB documents."""
    knowledge_base.create_kb_document("Doc 1", "path1", category="A", status="ready")
    knowledge_base.create_kb_document("Doc 2", "path2", category="B", status="ingesting")
    knowledge_base.create_kb_document("Doc 3", "path3", category="A", status="failed")

    all_docs = knowledge_base.list_kb_documents()
    assert len(all_docs) == 3

    ready_docs = knowledge_base.list_kb_documents(status="ready")
    assert len(ready_docs) == 1
    assert ready_docs[0]["title"] == "Doc 1"


def test_list_kb_documents_pagination(temp_db):
    """Test KB document pagination."""
    for i in range(5):
        knowledge_base.create_kb_document(f"Doc {i}", f"path{i}")

    page1 = knowledge_base.list_kb_documents(limit=2, offset=0)
    page2 = knowledge_base.list_kb_documents(limit=2, offset=2)
    page3 = knowledge_base.list_kb_documents(limit=2, offset=4)

    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1


def test_delete_kb_document(temp_db):
    """Test deleting a KB document."""
    kb_id = knowledge_base.create_kb_document("Test", "path")
    assert knowledge_base.delete_kb_document(kb_id) is True
    assert knowledge_base.get_kb_document(kb_id) is None
    assert knowledge_base.delete_kb_document(kb_id) is False  # Already deleted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])