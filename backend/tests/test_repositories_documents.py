"""
Unit tests for documents repository.
"""

import tempfile
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.repositories import documents
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

    original_get_connection = documents.get_connection
    documents.get_connection = lambda: get_connection(db_path)

    yield db_path

    documents.get_connection = original_get_connection
    if db_path.exists():
        db_path.unlink()


def test_create_document(temp_db):
    """Test creating a document."""
    doc_id = documents.create_document(
        filename="test.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_path="uploads/test.pdf"
    )
    assert doc_id is not None


def test_get_document(temp_db):
    """Test getting a document."""
    doc_id = documents.create_document(
        filename="test.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_path="uploads/test.pdf"
    )
    doc = documents.get_document(doc_id)
    assert doc is not None
    assert doc["document_id"] == doc_id
    assert doc["filename"] == "test.pdf"
    assert doc["content_type"] == "application/pdf"
    assert doc["size_bytes"] == 1024
    assert doc["storage_path"] == "uploads/test.pdf"


def test_get_nonexistent_document(temp_db):
    """Test getting non-existent document returns None."""
    doc = documents.get_document(new_id())
    assert doc is None


def test_list_documents(temp_db):
    """Test listing documents."""
    for i in range(3):
        documents.create_document(
            filename=f"doc{i}.pdf",
            content_type="application/pdf",
            size_bytes=1024 * (i + 1),
            storage_path=f"uploads/doc{i}.pdf"
        )

    docs = documents.list_documents()
    assert len(docs) == 3

    # Should be ordered by uploaded_at descending (newest first)
    for i in range(len(docs) - 1):
        assert docs[i]["uploaded_at"] >= docs[i + 1]["uploaded_at"]


def test_list_documents_pagination(temp_db):
    """Test document pagination."""
    for i in range(5):
        documents.create_document(
            filename=f"doc{i}.pdf",
            content_type="application/pdf",
            size_bytes=1024,
            storage_path=f"uploads/doc{i}.pdf"
        )

    page1 = documents.list_documents(limit=2, offset=0)
    page2 = documents.list_documents(limit=2, offset=2)
    page3 = documents.list_documents(limit=2, offset=4)

    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])