# logs/feature-model-lifecycle.md

> Feature / workstream: `feature-model-lifecycle` (branches: `feature/model-lifecycle`)
> Started: 2026-09-08 by opencode/nemotron-3-ultra-free
> Status: completed

## Goal

Implement the Resource/Model Lifecycle Manager (Task 9, implementation-plan.md Stage 9) — the component behind the Model Runtime that owns loading, keep-alive, unloading, and memory-pressure eviction of models backing each resource type, maintaining the live `ResourceState` table. Every lifecycle transition emits an audit event (`resource_loaded` / `resource_unloaded`).

Implements ADR-09 (Resource/Model Lifecycle Manager) and the locked design from `docs/models.md` "Memory budget (M4 Pro, 24GB unified memory)" and "Eviction under memory pressure".

## Plan

1. Define module constants: static footprint table (RESOURCE_FOOTPRINT_GB), locked 2GB headroom floor (HEADROOM_FLOOR_GB), eviction categories (NON_REASONING_TYPES)
2. Implement `acquire(resource_type, job_id)` public API with per-resource-type locking
3. Implement serve-if-loaded path with lazy idle-unload reconciliation (check Ollama `/api/ps`)
4. Implement load path with memory admission check and LRU eviction
5. Implement `_unload_model` via Ollama `keep_alive=0`
6. Implement failure recovery with typed `ModelLoadError` and `error` audit event
7. Create unit tests with mocked `psutil` and `httpx` for all acceptance criteria
8. Add `psutil` to requirements.txt

## Entries

### Entry 1 — 2026-09-08 14:00 — log created, implementation started
**What changed:** Created `logs/feature-model-lifecycle.md`. Read all authoritative docs: AGENTS.md, models.md, data-model.md, audit.md, backend.md, architecture.md, decisions.md (ADR-09), configuration.md, testing.md. Inspected existing code: runtime.py (Task 8), resource_state.py (Task 3), audit/events.py (Task 4), config.py (Task 2), schemas.py.
**Why:** AGENTS.md §4 requires a log file for every feature/workstream. Task 9 is SIH-critical for making 24GB M4 Pro viable.
**How to verify:** `cat logs/feature-model-lifecycle.md`
**Decisions made:** 
- Idle-unload detection: lazy reconciliation on `acquire()` (check Ollama `/api/ps`)
- Failure handling: raise typed `ModelLoadError` (Executor catches, emits error event, returns failed result)
- Call seam: Lifecycle Manager fronts Runtime (Executors call `acquire()`, then use `ModelHandle` to call model)
- ModelHandle shape: resource_type, model_identifier, runtime, base_url, load_triggered
**Supersedes / references:** N/A

---

### Entry 2 — 2026-09-08 15:30 — lifecycle_manager.py implementation complete
**What changed:** Created `backend/domain/model_runtime/lifecycle_manager.py` (464 lines). Key components:
- Module constants: RESOURCE_FOOTPRINT_GB (embedding:1.5, reasoning:6.6, vision:6.6, code_generation:5.0 GB), HEADROOM_FLOOR_GB=2, NON_REASONING_TYPES
- Public types: ModelHandle, ModelLoadError, UnknownResourceTypeError
- Internal: per-resource-type asyncio.Lock, module-level runtime instance for testability
- Helpers: _check_idle_unload (GET /api/ps), _unload_model (POST keep_alive=0), _evict_lru_non_reasoning (LRU non-reasoning first, reasoning last), _load_resource (triggers load via runtime.generate/embed)
- Public API: acquire() with serve-if-loaded, idle-unload check, memory admission, eviction, load, failure recovery
- Test utilities: _reset_locks, _reset_runtime_for_testing, _set_runtime_for_testing, _get_runtime
**Why:** Implements the complete locked design from docs/models.md and ADR-09.
**How to verify:** `cat backend/domain/model_runtime/lifecycle_manager.py`
**Decisions made:**
- Pre-create locks for all resource types to avoid race conditions
- Embedding (keep_alive=-1) skips idle-unload check entirely
- Footprint table keys on resource type, not model name (handles reasoning/vision sharing qwen3.5:9b)
- Eviction refreshes psutil.available after each unload
**Supersedes / references:** Entry 1

---

### Entry 3 — 2026-09-08 16:00 — test_lifecycle_manager.py created
**What changed:** Created `backend/tests/test_lifecycle_manager.py` (767 lines, 32 tests). Test categories:
- TestUnknownResourceType (2): validation and acquire raise
- TestServeIfLoaded (3): loaded resource served without reload, last_used_at advances, embedding handled
- TestIdleUnloadReconciliation (2): idle-unload detected/reloaded, embedding never triggers
- TestLoadPath (3): unloaded triggers load, ResourceState + resource_loaded + duration_ms, embedding uses embed
- TestMemoryAdmissionAndEviction (6): sufficient memory no eviction, insufficient triggers eviction, LRU order, reasoning not evicted while non-reasoning exists, reasoning last resort, shared model not double-counted
- TestFailureRecovery (4): ModelLoadError raised, status=unloaded, error event emitted, typed exception
- TestConcurrency (2): 3 concurrent acquires = 1 load, different types independent
- TestNoNewConfigKeys (3): footprint table is constant, headroom floor is constant, no keys in resources.yaml
- TestResourceStateNoHistory (2): single row per type, history in audit events
- TestConstantsAndConfig (3): values match docs/models.md
- TestInternalHelpers (2): _unload_model emits event, _evict_lru_non_reasoning evicts oldest
**Why:** Task 9 §8 requires unit tests with mocked memory-pressure signals.
**How to verify:** `cd C:\z\Bulwark && python -m pytest backend/tests/test_lifecycle_manager.py -v`
**Decisions made:**
- Mock httpx.AsyncClient.get for /api/ps to return loaded models (avoids false idle-unload in tests)
- Mock psutil.virtual_memory().available for admission control tests
- Mock OllamaRuntime via _set_runtime_for_testing for load/failure tests
**Supersedes / references:** Entry 2

---

### Entry 4 — 2026-09-08 16:30 — psutil added, all tests passing
**What changed:** Added `psutil` to `backend/requirements.txt`. Fixed concurrency test by mocking httpx /api/ps to return loaded models (prevented false idle-unload causing repeated loads). All 32 tests pass.
**Why:** psutil required for `psutil.virtual_memory().available` in admission control. httpx mock needed for _check_idle_unload.
**How to verify:** `cd C:\z\Bulwark && python -m pytest backend/tests/test_lifecycle_manager.py -v` → 32 passed
**Decisions made:** Test fixture `mock_httpx_get` auto-mocks httpx AsyncClient.get for all tests needing idle-unload check.
**Supersedes / references:** Entry 3

---

### Entry 5 — 2026-09-08 17:00 — branch complete
**Status:** completed
**Summary:** Implemented Resource/Model Lifecycle Manager per Task 9 spec. All acceptance criteria met: serve-if-loaded, load with admission/eviction, LRU non-reasoning first/reasoning last, 2GB floor + footprint table as module constants, idle-unload reconciliation, typed failure recovery, concurrency control, audit events for all transitions, no history in ResourceState. 32 unit tests pass with mocked memory signals.
**Final test status:** 32 passed in 8.56s
**Reviewer notes:** Ready for PR. No locked contracts violated. Zero-egress preserved (Ollama loopback only). Implementation matches ADR-09 and docs/models.md locked design.

---

## Open questions for the user

- None remaining — all clarifications resolved during implementation.

## Links

- PR: <url when created>
- Related branches / logs: `logs/feature-model-runtime.md` (Task 8 runtime.py), `logs/feature-data-model.md` (ResourceState), `logs/feature-audit.md` (emit function)
- Doc references: `docs/models.md`, `docs/data-model.md`, `docs/audit.md`, `docs/backend.md`, `docs/architecture.md`, `docs/decisions.md` (ADR-09), `docs/configuration.md`, `docs/testing.md`, `tasks/9-model-lifecycle-manager.md`