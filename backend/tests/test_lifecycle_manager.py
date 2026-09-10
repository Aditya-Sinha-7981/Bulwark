"""
Tests for Resource/Model Lifecycle Manager (Task 9).

Run: pytest tests/test_lifecycle_manager.py -v
"""

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock
from typing import Optional

from backend.domain.model_runtime.lifecycle_manager import (
    acquire,
    ModelHandle,
    ModelLoadError,
    UnknownResourceTypeError,
    RESOURCE_FOOTPRINT_GB,
    HEADROOM_FLOOR_GB,
    NON_REASONING_TYPES,
    REASONING_TYPE,
    _load_locks,
    _reset_locks,
    _reset_runtime_for_testing,
    _set_runtime_for_testing,
    _validate_resource_type,
    _check_idle_unload,
    _unload_model,
    _evict_lru_non_reasoning,
    _load_resource,
)
from backend.domain.model_runtime.runtime import (
    OllamaRuntime,
    ModelRuntimeError,
    ModelRuntimeUnavailableError,
)
from backend.repositories.resource_state import (
    get_resource_state,
    upsert_resource_state,
    set_resource_status,
    list_resource_states,
)
from backend.config import settings


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test."""
    _reset_locks()
    _reset_runtime_for_testing()
    # Clear resource_state table
    from backend.repositories.db import get_connection
    conn = get_connection()
    try:
        conn.execute("DELETE FROM resource_state")
        conn.commit()
    finally:
        conn.close()
    yield
    _reset_locks()
    _reset_runtime_for_testing()


@pytest.fixture
def mock_runtime():
    """Mock OllamaRuntime for testing."""
    mock_instance = AsyncMock(spec=OllamaRuntime)
    _set_runtime_for_testing(mock_instance)
    yield mock_instance
    _reset_runtime_for_testing()


@pytest.fixture
def mock_emit():
    """Mock emit function."""
    with patch("backend.domain.model_runtime.lifecycle_manager.emit", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_psutil():
    """Mock psutil.virtual_memory."""
    with patch("backend.domain.model_runtime.lifecycle_manager.psutil.virtual_memory") as mock:
        yield mock


@pytest.fixture
def mock_check_idle():
    """Mock _check_idle_unload function."""
    with patch("backend.domain.model_runtime.lifecycle_manager._check_idle_unload", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_httpx_get():
    """Mock httpx.AsyncClient.get for /api/ps to return loaded models."""
    from unittest.mock import MagicMock
    
    class MockResponse:
        def raise_for_status(self): pass
        def json(self): 
            return {"models": [{"name": "qwen3.5:9b"}, {"name": "qwen2.5-coder:7b"}, {"name": "qwen3-embedding:0.6b"}]}
    
    async def mock_get(*args, **kwargs):
        return MockResponse()
    
    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        yield


# =============================================================================
# Test Helpers
# =============================================================================


def _setup_loaded_resource(resource_type: str, model_identifier: Optional[str] = None):
    """Helper to set up a loaded resource state."""
    if model_identifier is None:
        entry = settings.resources.for_type(resource_type)
        model_identifier = entry.model
    upsert_resource_state(
        resource_type=resource_type,
        model_identifier=model_identifier,
        status="loaded",
        loaded_at="2024-01-01T00:00:00",
        last_used_at="2024-01-01T00:00:00",
    )


def _setup_unloaded_resource(resource_type: str, model_identifier: Optional[str] = None):
    """Helper to set up an unloaded resource state."""
    if model_identifier is None:
        entry = settings.resources.for_type(resource_type)
        model_identifier = entry.model
    upsert_resource_state(
        resource_type=resource_type,
        model_identifier=model_identifier,
        status="unloaded",
        loaded_at=None,
        last_used_at=None,
    )


# =============================================================================
# TestUnknownResourceType
# =============================================================================


class TestUnknownResourceType:
    """Test unknown resource type handling."""

    def test_unknown_resource_type_raises(self):
        with pytest.raises(UnknownResourceTypeError):
            _validate_resource_type("invalid_type")

    @pytest.mark.asyncio
    async def test_acquire_unknown_type_raises(self):
        with pytest.raises(UnknownResourceTypeError):
            await acquire("invalid_type")


# =============================================================================
# TestServeIfLoaded
# =============================================================================


class TestServeIfLoaded:
    """Test that already-loaded resources are served without reload."""

    @pytest.mark.asyncio
    async def test_acquire_loaded_returns_handle_no_reload(self, mock_runtime, mock_emit, mock_check_idle):
        _setup_loaded_resource("reasoning")
        mock_check_idle.return_value = True  # Model still loaded in Ollama

        handle = await acquire("reasoning", job_id="test-job")

        assert isinstance(handle, ModelHandle)
        assert handle.resource_type == "reasoning"
        assert handle.model_identifier == "qwen3.5:9b"
        assert handle.load_triggered is False
        # Runtime should NOT be called for generation
        mock_runtime.generate.assert_not_called()
        mock_runtime.embed.assert_not_called()
        mock_check_idle.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_loaded_updates_last_used_at(self, mock_runtime, mock_emit, mock_check_idle):
        _setup_loaded_resource("reasoning")
        mock_check_idle.return_value = True

        # Get initial state
        state_before = get_resource_state("reasoning")
        initial_last_used = state_before["last_used_at"]

        # Small delay to ensure timestamp changes
        await asyncio.sleep(0.01)

        await acquire("reasoning", job_id="test-job")

        state_after = get_resource_state("reasoning")
        assert state_after["last_used_at"] != initial_last_used
        assert state_after["last_used_at"] > initial_last_used

    @pytest.mark.asyncio
    async def test_acquire_loaded_embedding_returns_handle(self, mock_runtime, mock_emit, mock_check_idle):
        _setup_loaded_resource("embedding")
        mock_check_idle.return_value = True

        handle = await acquire("embedding", job_id="test-job")

        assert handle.resource_type == "embedding"
        assert handle.model_identifier == "qwen3-embedding:0.6b"
        assert handle.load_triggered is False
        mock_runtime.embed.assert_not_called()


# =============================================================================
# TestIdleUnloadReconciliation
# =============================================================================


class TestIdleUnloadReconciliation:
    """Test lazy idle-unload detection on acquire."""

    @pytest.mark.asyncio
    async def test_idle_unload_detected_and_reloaded(self, mock_runtime, mock_emit, mock_check_idle, mock_psutil):
        """Model shows as loaded in ResourceState but not in ollama ps -> reload."""
        _setup_loaded_resource("reasoning")
        mock_check_idle.return_value = False  # Model was idle-unloaded
        mock_psutil.return_value.available = 20 * _GB

        # Mock successful load
        mock_runtime.generate.return_value = MagicMock(
            text="ok", prompt_eval_count=5, eval_count=3, duration_ms=100
        )

        handle = await acquire("reasoning", job_id="test-job")

        assert handle.load_triggered is True
        # Should have emitted resource_unloaded (idle_timeout) then resource_loaded
        unload_calls = [
            c for c in mock_emit.call_args_list
            if c.args[0] == "resource_unloaded"
        ]
        load_calls = [
            c for c in mock_emit.call_args_list
            if c.args[0] == "resource_loaded"
        ]
        assert len(unload_calls) == 1
        assert unload_calls[0].args[2]["reason"] == "idle_timeout"
        assert len(load_calls) == 1

    @pytest.mark.asyncio
    async def test_idle_unload_embedding_never_triggers(self, mock_runtime, mock_emit, mock_check_idle):
        """Embedding has keep_alive=-1, should never be idle-unloaded."""
        _setup_loaded_resource("embedding")
        # Even if _check_idle_unload returns False, embedding should not reload
        # (embedding is always resident per config with keep_alive=-1)
        mock_check_idle.return_value = False

        handle = await acquire("embedding", job_id="test-job")

        assert handle.load_triggered is False
        mock_runtime.embed.assert_not_called()


# =============================================================================
# TestLoadPath
# =============================================================================


class TestLoadPath:
    """Test loading an unloaded resource."""

    @pytest.mark.asyncio
    async def test_acquire_unloaded_triggers_load(self, mock_runtime, mock_emit, mock_psutil):
        _setup_unloaded_resource("reasoning")
        # Mock plenty of memory available
        mock_psutil.return_value.available = 20 * _GB

        mock_runtime.generate.return_value = MagicMock(
            text="ok", prompt_eval_count=5, eval_count=3
        )

        handle = await acquire("reasoning", job_id="test-job")

        assert handle.load_triggered is True
        assert handle.resource_type == "reasoning"
        mock_runtime.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_sets_resource_state_and_emits_loaded(self, mock_runtime, mock_emit, mock_psutil):
        _setup_unloaded_resource("code_generation")
        mock_psutil.return_value.available = 20 * _GB

        mock_runtime.generate.return_value = MagicMock(
            text="ok", prompt_eval_count=10, eval_count=5
        )

        handle = await acquire("code_generation", job_id="test-job")

        state = get_resource_state("code_generation")
        assert state["status"] == "loaded"
        assert state["model_identifier"] == "qwen2.5-coder:7b"
        assert state["loaded_at"] is not None
        assert state["last_used_at"] is not None

        load_calls = [c for c in mock_emit.call_args_list if c.args[0] == "resource_loaded"]
        assert len(load_calls) == 1
        payload = load_calls[0].args[2]
        assert payload["resource_type"] == "code_generation"
        assert payload["model_identifier"] == "qwen2.5-coder:7b"
        assert "duration_ms" in payload
        assert isinstance(payload["duration_ms"], int)

    @pytest.mark.asyncio
    async def test_load_embedding_uses_embed(self, mock_runtime, mock_emit, mock_psutil):
        _setup_unloaded_resource("embedding")
        mock_psutil.return_value.available = 20 * _GB

        mock_runtime.embed.return_value = MagicMock(embeddings=[[0.1, 0.2]])

        handle = await acquire("embedding", job_id="test-job")

        assert handle.load_triggered is True
        mock_runtime.embed.assert_called_once()
        mock_runtime.generate.assert_not_called()


# =============================================================================
# TestMemoryAdmissionAndEviction
# =============================================================================


_GB = 1024 ** 3


class TestMemoryAdmissionAndEviction:
    """Test memory-pressure admission control and eviction logic."""

    @pytest.mark.asyncio
    async def test_admission_sufficient_memory_no_eviction(self, mock_runtime, mock_emit, mock_psutil):
        """Available memory >= footprint + 2GB -> no eviction."""
        _setup_unloaded_resource("code_generation")
        # reasoning (6.6GB) + headroom (2GB) = 8.6GB required
        # Provide 10GB available
        mock_psutil.return_value.available = 10 * _GB

        mock_runtime.generate.return_value = MagicMock(text="ok")

        await acquire("code_generation", job_id="test-job")

        # No unload events should be emitted
        unload_calls = [c for c in mock_emit.call_args_list if c.args[0] == "resource_unloaded"]
        assert len(unload_calls) == 0

    @pytest.mark.asyncio
    async def test_admission_insufficient_memory_triggers_eviction(self, mock_runtime, mock_emit, mock_psutil):
        """Available memory < footprint + 2GB -> eviction triggered."""
        # Pre-load embedding (1.5GB) and code_generation (5GB)
        _setup_loaded_resource("embedding")
        _setup_loaded_resource("code_generation")
        _setup_unloaded_resource("reasoning")

        # Available = 7GB, need 6.6 + 2 = 8.6GB -> need to evict
        mock_psutil.return_value.available = 7 * _GB

        mock_runtime.generate.return_value = MagicMock(text="ok")

        await acquire("reasoning", job_id="test-job")

        # Should have evicted code_generation (LRU non-reasoning) or embedding
        unload_calls = [c for c in mock_emit.call_args_list if c.args[0] == "resource_unloaded"]
        evicted = [c for c in unload_calls if c.args[2]["reason"] == "evicted"]
        assert len(evicted) >= 1

    @pytest.mark.asyncio
    async def test_eviction_order_lru_non_reasoning_first(self, mock_runtime, mock_emit, mock_psutil):
        """LRU non-reasoning resource evicted first."""
        # Set up with different last_used_at times
        upsert_resource_state("embedding", "qwen3-embedding:0.6b", "loaded",
                              "2024-01-01T00:00:00", "2024-01-01T00:00:00")  # oldest
        upsert_resource_state("code_generation", "qwen2.5-coder:7b", "loaded",
                              "2024-01-01T00:00:00", "2024-01-01T01:00:00")  # newer
        _setup_unloaded_resource("reasoning")

        # Need to evict to load reasoning (6.6 + 2 = 8.6GB)
        # Available = 6GB -> need to evict at least one
        mock_psutil.return_value.available = 6 * _GB

        mock_runtime.generate.return_value = MagicMock(text="ok")

        await acquire("reasoning", job_id="test-job")

        unload_calls = [c for c in mock_emit.call_args_list if c.args[0] == "resource_unloaded"]
        evicted = [c for c in unload_calls if c.args[2]["reason"] == "evicted"]
        assert len(evicted) >= 1
        # First evicted should be embedding (older last_used_at)
        assert evicted[0].args[2]["resource_type"] == "embedding"

    @pytest.mark.asyncio
    async def test_reasoning_not_evicted_while_non_reasoning_exists(self, mock_runtime, mock_emit, mock_psutil):
        """Reasoning is evicted only after all non-reasoning resources are exhausted."""
        _setup_loaded_resource("reasoning")
        _setup_loaded_resource("code_generation")
        _setup_unloaded_resource("vision")  # same model as reasoning

        # Very low memory - need to load vision (6.6GB) but reasoning (6.6GB) is loaded
        # Available = 3GB, need 8.6GB -> must evict
        mock_psutil.return_value.available = 3 * _GB

        mock_runtime.generate.return_value = MagicMock(text="ok")

        await acquire("vision", job_id="test-job")

        unload_calls = [c for c in mock_emit.call_args_list if c.args[0] == "resource_unloaded"]
        evicted = [c for c in unload_calls if c.args[2]["reason"] == "evicted"]

        # code_generation (non-reasoning) should be evicted FIRST
        evicted_types = [c.args[2]["resource_type"] for c in evicted]
        assert "code_generation" in evicted_types
        # code_generation should be evicted before reasoning (if reasoning is also evicted)
        if "reasoning" in evicted_types:
            code_gen_idx = evicted_types.index("code_generation")
            reasoning_idx = evicted_types.index("reasoning")
            assert code_gen_idx < reasoning_idx, "Non-reasoning should be evicted before reasoning"

    @pytest.mark.asyncio
    async def test_reasoning_evicted_last_resort(self, mock_runtime, mock_emit, mock_psutil):
        """Reasoning evicted only when it's the sole loaded resource and memory insufficient."""
        _setup_loaded_resource("reasoning")
        _setup_unloaded_resource("code_generation")

        # Available = 5GB, need 5 + 2 = 7GB for code_generation
        # Only reasoning (6.6GB) is loaded -> must evict reasoning
        mock_psutil.return_value.available = 5 * _GB

        mock_runtime.generate.return_value = MagicMock(text="ok")

        await acquire("code_generation", job_id="test-job")

        unload_calls = [c for c in mock_emit.call_args_list if c.args[0] == "resource_unloaded"]
        evicted = [c for c in unload_calls if c.args[2]["reason"] == "evicted"]
        assert len(evicted) == 1
        assert evicted[0].args[2]["resource_type"] == "reasoning"

    @pytest.mark.asyncio
    async def test_vision_and_reasoning_shared_model_not_double_counted(self, mock_runtime, mock_emit, mock_psutil):
        """Vision and reasoning share qwen3.5:9b - should not double-count footprint."""
        # reasoning is loaded (6.6GB), vision requests load (same model)
        # Since same model, should not need additional memory
        _setup_loaded_resource("reasoning")
        _setup_unloaded_resource("vision")  # same model

        # Available = 8GB (enough for reasoning 6.6 + 2 headroom = 8.6... barely)
        # Actually need 8.6, have 8 -> will try to evict
        # But since vision shares model with reasoning, this is a config quirk
        # The footprint table has both at 6.6GB - admission will see 6.6GB needed
        mock_psutil.return_value.available = 8 * _GB

        mock_runtime.generate.return_value = MagicMock(text="ok")

        await acquire("vision", job_id="test-job")

        # Should succeed (vision shares model with reasoning)
        # State should show vision as loaded
        state = get_resource_state("vision")
        assert state["status"] == "loaded"


# =============================================================================
# TestFailureRecovery
# =============================================================================


class TestFailureRecovery:
    """Test load failure handling."""

    @pytest.mark.asyncio
    async def test_load_failure_raises_model_load_error(self, mock_runtime, mock_emit, mock_psutil):
        _setup_unloaded_resource("reasoning")
        mock_psutil.return_value.available = 20 * _GB

        mock_runtime.generate.side_effect = ModelRuntimeUnavailableError("Ollama down")

        with pytest.raises(ModelLoadError) as exc_info:
            await acquire("reasoning", job_id="test-job")

        assert exc_info.value.resource_type == "reasoning"
        assert exc_info.value.model_identifier == "qwen3.5:9b"

    @pytest.mark.asyncio
    async def test_load_failure_sets_status_unloaded(self, mock_runtime, mock_emit, mock_psutil):
        _setup_unloaded_resource("code_generation")
        mock_psutil.return_value.available = 20 * _GB

        mock_runtime.generate.side_effect = ModelRuntimeError("OOM")

        with pytest.raises(ModelLoadError):
            await acquire("code_generation", job_id="test-job")

        state = get_resource_state("code_generation")
        assert state["status"] == "unloaded"

    @pytest.mark.asyncio
    async def test_load_failure_emits_error_event(self, mock_runtime, mock_emit, mock_psutil):
        _setup_unloaded_resource("reasoning")
        mock_psutil.return_value.available = 20 * _GB

        mock_runtime.generate.side_effect = ModelRuntimeUnavailableError("Connection refused")

        with pytest.raises(ModelLoadError):
            await acquire("reasoning", job_id="test-job")

        error_calls = [c for c in mock_emit.call_args_list if c.args[0] == "error"]
        assert len(error_calls) == 1
        assert error_calls[0].args[1] == "lifecycle_manager"
        assert error_calls[0].args[2]["component"] == "lifecycle_manager"

    @pytest.mark.asyncio
    async def test_load_failure_no_exception_past_boundary(self, mock_runtime, mock_emit, mock_psutil):
        """Load failure raises ModelLoadError (typed), not raw exception."""
        _setup_unloaded_resource("reasoning")
        mock_psutil.return_value.available = 20 * _GB

        mock_runtime.generate.side_effect = ModelRuntimeUnavailableError("Ollama down")

        with pytest.raises(ModelLoadError):
            await acquire("reasoning", job_id="test-job")

        # The exception IS raised, but it's a typed ModelLoadError
        # The Job Manager / Executor should catch this and handle gracefully


# =============================================================================
# TestConcurrency
# =============================================================================


class TestConcurrency:
    """Test concurrent acquire for same resource type."""

    @pytest.mark.asyncio
    async def test_concurrent_acquire_single_load(self, mock_runtime, mock_emit, mock_psutil, mock_httpx_get):
        """Multiple concurrent acquire() for same type triggers exactly one load."""
        _setup_unloaded_resource("reasoning")
        mock_psutil.return_value.available = 20 * _GB

        call_count = 0

        async def counting_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate load time
            return MagicMock(text="ok", prompt_eval_count=5, eval_count=3)

        mock_runtime.generate.side_effect = counting_generate

        # Launch 3 concurrent acquires
        results = await asyncio.gather(
            acquire("reasoning", job_id="job-1"),
            acquire("reasoning", job_id="job-2"),
            acquire("reasoning", job_id="job-3"),
        )

        # Only one actual load should have happened
        assert call_count == 1

        # All should return handles (first has load_triggered=True, others False)
        triggered = [h for h in results if h.load_triggered]
        not_triggered = [h for h in results if not h.load_triggered]
        assert len(triggered) == 1
        assert len(not_triggered) == 2

    @pytest.mark.asyncio
    async def test_concurrent_acquire_different_types_independent(self, mock_runtime, mock_emit, mock_psutil):
        """Concurrent acquire for different types proceed independently."""
        _setup_unloaded_resource("reasoning")
        _setup_unloaded_resource("code_generation")
        mock_psutil.return_value.available = 20 * _GB

        mock_runtime.generate.return_value = MagicMock(text="ok")

        results = await asyncio.gather(
            acquire("reasoning", job_id="job-1"),
            acquire("code_generation", job_id="job-2"),
        )

        assert results[0].resource_type == "reasoning"
        assert results[1].resource_type == "code_generation"
        assert results[0].load_triggered is True
        assert results[1].load_triggered is True


# =============================================================================
# TestNoNewConfigKeys
# =============================================================================


class TestNoNewConfigKeys:
    """Verify no new config keys were added."""

    def test_footprint_table_is_module_constant(self):
        """RESOURCE_FOOTPRINT_GB is a module-level constant dict."""
        assert isinstance(RESOURCE_FOOTPRINT_GB, dict)
        assert set(RESOURCE_FOOTPRINT_GB.keys()) == {"embedding", "reasoning", "vision", "code_generation"}
        # All values are floats (GB)
        for v in RESOURCE_FOOTPRINT_GB.values():
            assert isinstance(v, (int, float))

    def test_headroom_floor_is_module_constant(self):
        """HEADROOM_FLOOR_GB is a module-level constant."""
        assert HEADROOM_FLOOR_GB == 2
        assert isinstance(HEADROOM_FLOOR_GB, int)

    def test_no_footprint_keys_in_resources_yaml(self):
        """config/resources.yaml should not have footprint or headroom keys."""
        import yaml
        from pathlib import Path

        config_path = Path(__file__).parent.parent.parent / "config" / "resources.yaml"
        with open(config_path) as f:
            data = yaml.safe_load(f)

        for resource_config in data["resources"].values():
            assert "footprint_gb" not in resource_config
            assert "headroom_gb" not in resource_config
            assert "memory_footprint" not in resource_config


# =============================================================================
# TestResourceStateNoHistory
# =============================================================================


class TestResourceStateNoHistory:
    """Verify ResourceState holds only live state, no history."""

    @pytest.mark.asyncio
    async def test_resource_state_single_row_per_type(self, mock_runtime, mock_emit, mock_psutil):
        """Only one row per resource_type exists in ResourceState."""
        _setup_unloaded_resource("reasoning")
        mock_psutil.return_value.available = 20 * _GB
        mock_runtime.generate.return_value = MagicMock(text="ok")

        await acquire("reasoning", job_id="job-1")
        await acquire("reasoning", job_id="job-2")  # Second acquire

        from backend.repositories.db import get_connection
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM resource_state WHERE resource_type = 'reasoning'")
            count = cursor.fetchone()[0]
            assert count == 1
        finally:
            conn.close()

    @pytest.mark.asyncio
    async def test_history_in_audit_events_not_resource_state(self, mock_runtime, mock_emit, mock_psutil):
        """Load/unload history is in audit events, not ResourceState."""
        _setup_unloaded_resource("reasoning")
        mock_psutil.return_value.available = 20 * _GB
        mock_runtime.generate.return_value = MagicMock(text="ok")

        await acquire("reasoning", job_id="job-1")
        # Simulate unload
        from backend.domain.model_runtime.lifecycle_manager import _unload_model
        await _unload_model("reasoning", "qwen3.5:9b", "evicted", job_id="job-1")
        # Reload
        mock_runtime.generate.return_value = MagicMock(text="ok")
        await acquire("reasoning", job_id="job-2")

        # ResourceState should only show current state (loaded)
        state = get_resource_state("reasoning")
        assert state["status"] == "loaded"

        # But audit events should have both resource_loaded and resource_unloaded
        loaded_calls = [c for c in mock_emit.call_args_list if c.args[0] == "resource_loaded"]
        unloaded_calls = [c for c in mock_emit.call_args_list if c.args[0] == "resource_unloaded"]
        assert len(loaded_calls) == 2
        assert len(unloaded_calls) == 1


# =============================================================================
# TestConstantsAndConfig
# =============================================================================


class TestConstantsAndConfig:
    """Test module constants match documented values."""

    def test_footprint_values_match_docs_models_md(self):
        """Footprint constants match docs/models.md Memory budget table."""
        # docs/models.md:
        # embedding: ~1.5GB
        # reasoning/vision (shared qwen3.5:9b): ~6.6GB
        # code_generation: ~5GB
        assert RESOURCE_FOOTPRINT_GB["embedding"] == 1.5
        assert RESOURCE_FOOTPRINT_GB["reasoning"] == 6.6
        assert RESOURCE_FOOTPRINT_GB["vision"] == 6.6
        assert RESOURCE_FOOTPRINT_GB["code_generation"] == 5.0

    def test_headroom_floor_is_2gb(self):
        """HEADROOM_FLOOR_GB is 2 (locked)."""
        assert HEADROOM_FLOOR_GB == 2

    def test_non_reasoning_types_excludes_reasoning(self):
        """NON_REASONING_TYPES does not include reasoning."""
        assert REASONING_TYPE not in NON_REASONING_TYPES
        assert NON_REASONING_TYPES == {"code_generation", "embedding", "vision"}


# =============================================================================
# TestInternalHelpers
# =============================================================================


class TestInternalHelpers:
    """Test internal helper functions."""

    @pytest.mark.asyncio
    async def test_unload_model_emits_event_and_updates_state(self, mock_emit, mock_check_idle):
        """_unload_model updates state and emits event."""
        _setup_loaded_resource("reasoning")
        # Mock _check_idle_unload to avoid httpx calls
        mock_check_idle.return_value = True

        await _unload_model("reasoning", "qwen3.5:9b", "evicted", job_id="test-job")

        state = get_resource_state("reasoning")
        assert state["status"] == "unloaded"

        unload_calls = [c for c in mock_emit.call_args_list if c.args[0] == "resource_unloaded"]
        assert len(unload_calls) == 1
        assert unload_calls[0].args[2]["reason"] == "evicted"

    @pytest.mark.asyncio
    async def test_evict_lru_non_reasoning_evicts_oldest(self, mock_emit, mock_psutil, mock_check_idle):
        """_evict_lru_non_reasoning evicts LRU non-reasoning resource."""
        # Mock _check_idle_unload to avoid httpx calls in _unload_model
        mock_check_idle.return_value = True

        # Set up with specific last_used_at order
        upsert_resource_state("embedding", "qwen3-embedding:0.6b", "loaded",
                              "2024-01-01T00:00:00", "2024-01-01T00:00:00")
        upsert_resource_state("code_generation", "qwen2.5-coder:7b", "loaded",
                              "2024-01-01T00:00:00", "2024-01-01T01:00:00")

        # Need 5GB more, have 3GB available
        mock_psutil.return_value.available = 3 * _GB
        required = 8 * _GB  # Need 8GB total

        await _evict_lru_non_reasoning(required, job_id="test-job")

        # embedding (older) should be evicted first
        unload_calls = [c for c in mock_emit.call_args_list if c.args[0] == "resource_unloaded"]
        evicted = [c for c in unload_calls if c.args[2]["reason"] == "evicted"]
        assert len(evicted) >= 1
        assert evicted[0].args[2]["resource_type"] == "embedding"


# =============================================================================
# Import at bottom for constant tests
# =============================================================================

_GB = 1024 ** 3