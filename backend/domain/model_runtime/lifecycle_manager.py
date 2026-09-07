"""
Resource/Model Lifecycle Manager

Sits behind the Model Runtime. Owns loading, keep-alive, unloading, and
memory-pressure eviction of the model backing each resource type.
Maintains the live ResourceState table. Every lifecycle transition emits
an audit event (resource_loaded / resource_unloaded).

Per docs/models.md, docs/architecture.md, ADR-09.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import httpx
import psutil

from backend.config import settings
from backend.domain.audit.events import emit
from backend.domain.model_runtime.runtime import (
    OllamaRuntime,
    ModelRuntimeError,
    ModelRuntimeUnavailableError,
)
from backend.repositories.resource_state import (
    get_resource_state,
    list_resource_states,
    set_resource_status,
    upsert_resource_state,
)


# =============================================================================
# Module Constants (locked design — no config keys)
# =============================================================================

# Static approximate footprint table for admission control (GB)
# Keys match resource types from config/resources.yaml.
# These are approximations for admission control, not exact physical measurements.
# Task 20's M4 Pro memory test may adjust these constants empirically.
RESOURCE_FOOTPRINT_GB = {
    "embedding": 1.5,
    "reasoning": 6.6,      # qwen3.5:9b (shared with vision)
    "vision": 6.6,         # same model as reasoning
    "code_generation": 5.0,
}

# Locked admission floor: minimum available memory that must remain after load (GB)
# This is NOT configurable — it is a hard floor for admission control.
HEADROOM_FLOOR_GB = 2

# Resource type categories for eviction policy
NON_REASONING_TYPES = {"code_generation", "embedding", "vision"}
REASONING_TYPE = "reasoning"
VALID_RESOURCE_TYPES = frozenset(RESOURCE_FOOTPRINT_GB.keys())

# Conversion
_GB = 1024 ** 3


# =============================================================================
# Public Types
# =============================================================================


@dataclass(frozen=True)
class ModelHandle:
    """Handle returned by acquire() — everything an Executor needs to call the model."""
    resource_type: str
    model_identifier: str
    runtime: str = "ollama"
    base_url: str = ""
    load_triggered: bool = False


class ModelLoadError(Exception):
    """Raised when model load fails (timeout, Ollama down, bad model, OOM)."""
    def __init__(self, resource_type: str, model_identifier: str, message: str):
        self.resource_type = resource_type
        self.model_identifier = model_identifier
        super().__init__(f"Failed to load {resource_type} ({model_identifier}): {message}")


class UnknownResourceTypeError(ValueError):
    """Raised when an invalid resource_type is requested."""
    pass


# =============================================================================
# Internal State
# =============================================================================

# Per-resource-type locks to serialize concurrent loads
# Pre-create locks for all known resource types to avoid race conditions
_load_locks: dict[str, asyncio.Lock] = {rt: asyncio.Lock() for rt in VALID_RESOURCE_TYPES}

# Module-level runtime instance for testability (can be replaced with mock)
_runtime_instance: OllamaRuntime | None = None


def _get_runtime() -> OllamaRuntime:
    """Get or create the runtime instance (for testability)."""
    global _runtime_instance
    if _runtime_instance is None:
        _runtime_instance = OllamaRuntime()
    return _runtime_instance


def _set_runtime_for_testing(runtime: OllamaRuntime | None) -> None:
    """Replace the runtime instance for testing."""
    global _runtime_instance
    _runtime_instance = runtime


def _get_lock(resource_type: str) -> asyncio.Lock:
    """Get the lock for a resource type."""
    return _load_locks[resource_type]


# =============================================================================
# Helpers
# =============================================================================


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _validate_resource_type(resource_type: str) -> None:
    """Validate resource_type is known."""
    if resource_type not in VALID_RESOURCE_TYPES:
        raise UnknownResourceTypeError(
            f"Unknown resource type '{resource_type}'; expected one of {sorted(VALID_RESOURCE_TYPES)}"
        )


def _resolve_resource_config(resource_type: str):
    """Resolve resource_type to its config entry (model, keep_alive, etc.)."""
    return settings.resources.for_type(resource_type)


async def _ensure_resource_state_row(resource_type: str, model_identifier: str) -> dict:
    """Ensure ResourceState row exists; create with unloaded status if missing."""
    state = get_resource_state(resource_type)
    if state is None:
        upsert_resource_state(
            resource_type=resource_type,
            model_identifier=model_identifier,
            status="unloaded",
            loaded_at=None,
            last_used_at=None,
        )
        return get_resource_state(resource_type)
    return state


async def _check_idle_unload(resource_type: str, model_identifier: str, runtime: OllamaRuntime) -> bool:
    """
    Lazy idle-unload reconciliation.
    Checks if model is still loaded in Ollama via /api/ps.
    Returns True if model is still loaded, False if it was idle-unloaded.
    """
    try:
        client = httpx.AsyncClient(
            base_url=settings.app.ollama.base_url,
            timeout=httpx.Timeout(connect=5, read=10, write=10, pool=10),
        )
        try:
            resp = await client.get("/api/ps")
            resp.raise_for_status()
            data = resp.json()
            # Check if our model is in the loaded models list
            for model_info in data.get("models", []):
                if model_info.get("name") == model_identifier:
                    return True
            # Model not found in loaded models — it was idle-unloaded
            return False
        finally:
            await client.aclose()
    except Exception:
        # If we can't check, assume it's still loaded (conservative)
        return True


async def _unload_model(resource_type: str, model_identifier: str, reason: str, job_id: Optional[str] = None) -> None:
    """
    Unload a model by sending keep_alive=0 to Ollama.
    Updates ResourceState and emits resource_unloaded audit event.
    """
    try:
        client = httpx.AsyncClient(
            base_url=settings.app.ollama.base_url,
            timeout=httpx.Timeout(connect=5, read=10, write=10, pool=10),
        )
        try:
            # Send unload request (keep_alive=0 means immediate unload)
            await client.post("/api/generate", json={
                "model": model_identifier,
                "prompt": "",
                "stream": False,
                "keep_alive": 0,
            })
        finally:
            await client.aclose()
    except Exception:
        # Even if unload request fails, we update state and emit event
        # The model may already be unloaded by Ollama
        pass

    set_resource_status(resource_type, "unloaded", loaded_at=None, last_used_at=None)

    await emit(
        "resource_unloaded",
        "lifecycle_manager",
        {
            "resource_type": resource_type,
            "model_identifier": model_identifier,
            "reason": reason,
        },
        job_id=job_id,
    )


async def _evict_lru_non_reasoning(required_available_bytes: int, job_id: Optional[str] = None) -> None:
    """
    Evict least-recently-used non-reasoning resources until available memory >= required.
    If only reasoning remains and still insufficient, evict reasoning as last resort.
    """
    while True:
        available = psutil.virtual_memory().available
        if available >= required_available_bytes:
            return

        # Get currently loaded resources
        loaded = list_resource_states()
        loaded = [r for r in loaded if r["status"] == "loaded"]

        # Try to evict non-reasoning first (LRU by last_used_at)
        non_reasoning = [r for r in loaded if r["resource_type"] in NON_REASONING_TYPES]
        non_reasoning.sort(key=lambda r: r["last_used_at"] or "")

        evicted = False
        for r in non_reasoning:
            await _unload_model(r["resource_type"], r["model_identifier"], "evicted", job_id)
            evicted = True
            # Check if we have enough now
            if psutil.virtual_memory().available >= required_available_bytes:
                return

        # If we evicted something, loop will re-check available memory
        if evicted:
            continue

        # No non-reasoning left to evict — check if reasoning is loaded
        reasoning_loaded = [r for r in loaded if r["resource_type"] == REASONING_TYPE]
        if reasoning_loaded:
            r = reasoning_loaded[0]
            await _unload_model(r["resource_type"], r["model_identifier"], "evicted", job_id)
            # Loop will re-check
            continue

        # Nothing left to evict — we'll attempt the load anyway and let it fail
        return


async def _load_resource(
    resource_type: str,
    model_identifier: str,
    keep_alive: str | int,
    job_id: Optional[str] = None,
) -> ModelHandle:
    """
    Load a resource by triggering Ollama to load it with the configured keep_alive.
    Uses a minimal prompt to trigger the load.
    """
    start = time.perf_counter()

    # Use the runtime module to trigger the load
    runtime = _get_runtime()

    try:
        # Minimal prompt to trigger load — the actual prompt doesn't matter
        # We use generate for reasoning/code_generation/vision, embed for embedding
        if resource_type == "embedding":
            await runtime.embed(resource_type, "warmup", job_id=job_id)
        else:
            await runtime.generate(resource_type, " ", job_id=job_id)
    except (ModelRuntimeError, ModelRuntimeUnavailableError) as e:
        # Load failed — set status to unloaded and emit error
        set_resource_status(resource_type, "unloaded", loaded_at=None, last_used_at=None)
        await emit(
            "error",
            "lifecycle_manager",
            {
                "component": "lifecycle_manager",
                "message": str(e),
                "context": {"resource_type": resource_type, "model_identifier": model_identifier},
            },
            job_id=job_id,
        )
        raise ModelLoadError(resource_type, model_identifier, str(e)) from e

    duration_ms = int((time.perf_counter() - start) * 1000)

    # Success — update state
    now = _now_iso()
    set_resource_status(resource_type, "loaded", loaded_at=now, last_used_at=now)

    # Emit resource_loaded audit event
    await emit(
        "resource_loaded",
        "lifecycle_manager",
        {
            "resource_type": resource_type,
            "model_identifier": model_identifier,
            "duration_ms": duration_ms,
        },
        job_id=job_id,
    )

    return ModelHandle(
        resource_type=resource_type,
        model_identifier=model_identifier,
        runtime="ollama",
        base_url=settings.app.ollama.base_url,
        load_triggered=True,
    )


# =============================================================================
# Public API
# =============================================================================


async def acquire(resource_type: str, job_id: Optional[str] = None) -> ModelHandle:
    """
    Acquire a model handle for the given resource type.

    This is the main public entry point for Capability Executors.
    It handles:
    - Resolving resource_type to configured model
    - Serving already-loaded models (with lazy idle-unload check)
    - Memory-pressure admission and eviction
    - Loading new models with keep_alive
    - Failure recovery

    Args:
        resource_type: One of "reasoning", "code_generation", "vision", "embedding"
        job_id: Optional job ID for audit correlation

    Returns:
        ModelHandle with resource_type, model_identifier, runtime, base_url, load_triggered

    Raises:
        UnknownResourceTypeError: If resource_type is not recognized
        ModelLoadError: If model fails to load (Ollama down, timeout, OOM, bad model)
    """
    _validate_resource_type(resource_type)

    entry = _resolve_resource_config(resource_type)
    model_identifier = entry.model
    keep_alive = entry.keep_alive

    # Ensure ResourceState row exists
    await _ensure_resource_state_row(resource_type, model_identifier)

    # Serialize loads per resource type
    async with _get_lock(resource_type):
        state = get_resource_state(resource_type)

        # Case 1: Already loaded — check for idle unload (skip for embedding with keep_alive=-1)
        if state["status"] == "loaded":
            # Embedding has keep_alive=-1 (always resident), skip idle check
            if keep_alive == -1 or keep_alive == "-1":
                now = _now_iso()
                set_resource_status(resource_type, "loaded", last_used_at=now)
                return ModelHandle(
                    resource_type=resource_type,
                    model_identifier=model_identifier,
                    runtime="ollama",
                    base_url=settings.app.ollama.base_url,
                    load_triggered=False,
                )

            # Lazy reconciliation: check if Ollama still has the model loaded
            runtime = _get_runtime()
            still_loaded = await _check_idle_unload(resource_type, model_identifier, runtime)

            if not still_loaded:
                # Idle-unloaded — treat as unloaded and proceed to reload
                set_resource_status(resource_type, "unloaded", loaded_at=None, last_used_at=None)
                await emit(
                    "resource_unloaded",
                    "lifecycle_manager",
                    {
                        "resource_type": resource_type,
                        "model_identifier": model_identifier,
                        "reason": "idle_timeout",
                    },
                    job_id=job_id,
                )
            else:
                # Still loaded — update last_used_at and return
                now = _now_iso()
                set_resource_status(resource_type, "loaded", last_used_at=now)
                return ModelHandle(
                    resource_type=resource_type,
                    model_identifier=model_identifier,
                    runtime="ollama",
                    base_url=settings.app.ollama.base_url,
                    load_triggered=False,
                )

        # Case 2: Loading — wait for the other load to complete
        if state["status"] == "loading":
            # The lock ensures we wait here until the other coroutine finishes
            # After it releases the lock, state will be either loaded or unloaded
            state = get_resource_state(resource_type)
            if state["status"] == "loaded":
                now = _now_iso()
                set_resource_status(resource_type, "loaded", last_used_at=now)
                return ModelHandle(
                    resource_type=resource_type,
                    model_identifier=model_identifier,
                    runtime="ollama",
                    base_url=settings.app.ollama.base_url,
                    load_triggered=False,
                )
            # If it failed, we'll fall through to load again

        # Case 3: Unloaded — need to load
        # Set loading status
        set_resource_status(resource_type, "loading")

        # Memory admission check with eviction
        footprint_gb = RESOURCE_FOOTPRINT_GB[resource_type]
        required_bytes = int((footprint_gb + HEADROOM_FLOOR_GB) * _GB)
        await _evict_lru_non_reasoning(required_bytes, job_id)

        # Load the resource
        return await _load_resource(resource_type, model_identifier, keep_alive, job_id)


# =============================================================================
# Cleanup (for testing)
# =============================================================================


def _reset_locks() -> None:
    """Reset internal locks (for test isolation)."""
    global _load_locks
    _load_locks = {rt: asyncio.Lock() for rt in VALID_RESOURCE_TYPES}


def _reset_runtime_for_testing() -> None:
    """Reset runtime instance for test isolation."""
    global _runtime_instance
    _runtime_instance = None