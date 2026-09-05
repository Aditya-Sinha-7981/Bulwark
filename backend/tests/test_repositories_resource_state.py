"""
Unit tests for resource_state repository.
"""

import tempfile
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.repositories import resource_state
from backend.repositories.db import get_connection, ConstraintError


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

    original_get_connection = resource_state.get_connection
    resource_state.get_connection = lambda: get_connection(db_path)

    yield db_path

    resource_state.get_connection = original_get_connection
    if db_path.exists():
        db_path.unlink()


def test_upsert_resource_state(temp_db):
    """Test upserting a resource state."""
    resource_state.upsert_resource_state(
        resource_type="reasoning",
        model_identifier="qwen3.5:9b",
        status="loaded"
    )
    rs = resource_state.get_resource_state("reasoning")
    assert rs is not None
    assert rs["resource_type"] == "reasoning"
    assert rs["model_identifier"] == "qwen3.5:9b"
    assert rs["status"] == "loaded"


def test_upsert_resource_state_update(temp_db):
    """Test upserting updates existing resource state."""
    resource_state.upsert_resource_state(
        resource_type="reasoning",
        model_identifier="qwen3.5:9b",
        status="unloaded"
    )

    resource_state.upsert_resource_state(
        resource_type="reasoning",
        model_identifier="qwen3.5:9b",
        status="loaded",
        loaded_at="2024-01-01T00:00:00"
    )
    rs = resource_state.get_resource_state("reasoning")
    assert rs["status"] == "loaded"
    assert rs["loaded_at"] == "2024-01-01T00:00:00"


def test_upsert_invalid_status(temp_db):
    """Test upserting with invalid status."""
    with pytest.raises(ConstraintError):
        resource_state.upsert_resource_state("reasoning", "model", "invalid")


def test_upsert_invalid_resource_type(temp_db):
    """Test upserting with invalid resource type."""
    with pytest.raises(ConstraintError):
        resource_state.upsert_resource_state("invalid", "model", "loaded")


def test_get_resource_state(temp_db):
    """Test getting a resource state."""
    resource_state.upsert_resource_state("vision", "qwen3.5:9b", "loaded")
    rs = resource_state.get_resource_state("vision")
    assert rs is not None
    assert rs["resource_type"] == "vision"


def test_get_nonexistent_resource_state(temp_db):
    """Test getting non-existent resource state returns None."""
    rs = resource_state.get_resource_state("nonexistent")
    assert rs is None


def test_list_resource_states(temp_db):
    """Test listing all resource states."""
    resource_state.upsert_resource_state("reasoning", "qwen3.5:9b", "loaded")
    resource_state.upsert_resource_state("code_generation", "qwen2.5-coder:7b", "unloaded")
    resource_state.upsert_resource_state("embedding", "qwen3-embedding:0.6b", "loading")

    all_states = resource_state.list_resource_states()
    assert len(all_states) == 3

    # Should be ordered by resource_type
    types = [s["resource_type"] for s in all_states]
    assert types == sorted(types)


def test_set_resource_status(temp_db):
    """Test updating resource status."""
    resource_state.upsert_resource_state("reasoning", "qwen3.5:9b", "unloaded")

    resource_state.set_resource_status(
        "reasoning",
        "loading",
        last_used_at="2024-01-01T00:00:00"
    )
    rs = resource_state.get_resource_state("reasoning")
    assert rs["status"] == "loading"
    assert rs["last_used_at"] == "2024-01-01T00:00:00"


def test_set_resource_status_invalid(temp_db):
    """Test setting invalid status."""
    with pytest.raises(ConstraintError):
        resource_state.set_resource_status("reasoning", "invalid")


def test_set_resource_status_nonexistent(temp_db):
    """Test setting status for non-existent resource."""
    # Should return False, not raise
    result = resource_state.set_resource_status("nonexistent", "loaded")
    assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])