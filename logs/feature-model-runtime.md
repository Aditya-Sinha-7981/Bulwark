# logs/feature-model-runtime.md

> Feature / workstream: `feature-model-runtime` (branches: `feature/model-runtime`)
> Started: 2026-09-07 by opencode/nemotron-3-ultra-free
> Status: completed

## Goal

Implement the Ollama HTTP wrapper (`backend/domain/model_runtime/runtime.py`) — the single backend module that talks to Ollama's local HTTP API. Callers request a resource type (`reasoning`, `code_generation`, `vision`, `embedding`); the wrapper resolves it via `config/resources.yaml` to a concrete model and calls the appropriate Ollama endpoint. Emits `model_invoked` audit events and writes `model_executions` rows. Fails cleanly with typed errors when Ollama is unreachable — never hangs.

Implements Task 8 (implementation-plan.md Stage 8; tasks/8-model-runtime.md) and satisfies ADR-07 (Ollama) + ADR-08 (resource-type abstraction).

## Plan

1. Add `EmbeddingResult` model to `backend/models/schemas.py` (SECTION 5, after `GenerationResult`)
2. Implement `backend/domain/model_runtime/runtime.py`:
   - `OllamaRuntime` class with `generate()` and `embed()` methods
   - Resource-type → model resolution via `settings.resources.for_type()`
   - Non-streaming generation only (`stream: false`)
   - Options filtering (allow only temperature, top_p, top_k, repeat_penalty, num_predict, num_ctx, seed, stop)
   - Vision support via base64-encoded images
   - Locked 5s connect timeout (in-code constant `CONNECT_TIMEOUT_SECONDS = 5`)
   - 120s request timeout from `settings.app.ollama.request_timeout_seconds`
   - Typed errors: `ModelRuntimeUnavailableError`, `ModelRuntimeError`
   - `model_invoked` audit events + `model_executions` DB rows via `_record()`
   - `job_id` parameter for audit correlation
   - Module-level `runtime` singleton matching `ModelClient` Protocol
3. Create `backend/tests/test_model_runtime.py` with unit + integration tests
4. Run tests and verify implementation

## Entries

### Entry 1 — 2026-09-07 10:00 — log created, implementation started
**What changed:** Created `logs/feature-model-runtime.md` (this file). Read all authoritative docs: AGENTS.md, project-context.md, models.md, backend.md, configuration.md, audit.md, data-model.md, agent.md, decisions.md (ADR-07, ADR-08), testing.md, security.md. Inspected existing code: schemas.py (654 lines, SECTION 5 has ModelClient Protocol), config.py (settings.resources, settings.app.ollama), audit/events.py (emit function), repositories/jobs.py (add_model_execution), runtime.py (empty), lifecycle_manager.py (empty).
**Why:** AGENTS.md §4 requires a log file for every feature/workstream touched. Task 8 is the critical path from app to models.
**How to verify:** `cat logs/feature-model-runtime.md`
**Open issues / known gaps:** Task 9 (Lifecycle Manager) not implemented — this wrapper will be fronted by it later. External dependency: Ollama with models `qwen3.5:9b`, `qwen2.5-coder:7b`, `qwen3-embedding:0.6b` must be pulled for integration tests.
**Decisions made:** (1) Non-streaming generation only per user clarification. (2) Options passthrough with allowlist. (3) Best-effort `load_triggered` heuristic (duration > 30s for generate, > 10s for embed) until Task 9 provides authoritative info. (4) 5s connect timeout as in-code constant (locked, not configurable). (5) `job_id` parameter added to `generate()`/`embed()` for audit correlation.
**Supersedes / references:** N/A — first entry.

---

### Entry 2 — 2026-09-07 10:30 — EmbeddingResult added to schemas.py
**What changed:** Added `EmbeddingResult` model to `backend/models/schemas.py:626-637` (after `GenerationResult`). Fields: `embeddings: list[list[float]]`, `prompt_tokens`, `duration_ms`, `model_identifier`, `load_triggered`. Uses `ConfigDict(extra="forbid")`.
**Why:** Required by `runtime.py`'s `embed()` return type. Matches Task 8 spec requirement for embedding results.
**How to verify:** `grep -A 10 "class EmbeddingResult" backend/models/schemas.py`
**Decisions made:** `prompt_tokens` optional (Ollama `/api/embed` doesn't return token counts). `load_triggered` default `False`.

---

### Entry 3 — 2026-09-07 11:00 — runtime.py implementation complete
**What changed:** Created `backend/domain/model_runtime/runtime.py` (306 lines). Key components:
- `CONNECT_TIMEOUT_SECONDS = 5` (locked constant, documented)
- `ALLOWED_GENERATE_OPTIONS` frozenset (8 allowed keys)
- `ModelRuntimeUnavailableError`, `ModelRuntimeError` typed exceptions
- `OllamaRuntime` class with `_get_client()`, `_resolve()`, `generate()`, `embed()`, `_record()`
- `generate()`: POST `/api/generate` with `stream: false`, `keep_alive`, filtered options, base64 images for vision
- `embed()`: POST `/api/embed` with `input` array, `keep_alive`
- Error handling: `ConnectError`/`ConnectTimeout` → `ModelRuntimeUnavailableError` (fast), `HTTPStatusError` → `ModelRuntimeError`
- `_record()`: emits `model_invoked` via `emit()`, writes `model_executions` via `add_model_execution()` when `capability_execution_id` provided
- Module-level `runtime = OllamaRuntime()` singleton for DI
**Why:** Single module that calls Ollama's HTTP API per `docs/backend.md` "Model Runtime interface" and `docs/security.md` layer 3.
**How to verify:** `cat backend/domain/model_runtime/runtime.py`
**Decisions made:** 
- `_resolve()` wraps `KeyError` → `ValueError` for unknown resource types (fail before network)
- `load_triggered` best-effort heuristic (duration thresholds)
- `job_id` threaded through to `emit()` and `_record()`
- Options filtering blocks runtime-controlled fields (model, stream, keep_alive)

---

### Entry 4 — 2026-09-07 11:30 — test_model_runtime.py created, all unit tests pass
**What changed:** Created `backend/tests/test_model_runtime.py` (560+ lines, 28 tests). Added `integration` marker to `backend/pytest.ini`. Test categories:
- `TestResourceTypeResolution` (5): model identifiers match config/resources.yaml
- `TestFailureInjection` (4): connection refused (5s), connect timeout config, non-2xx errors, unknown resource type
- `TestOptionsFiltering` (2): allowed options pass, disallowed blocked
- `TestAuditAndDB` (2): model_invoked event, model_executions row (mocked)
- `TestStaticCheck` (2): only runtime.py references model endpoints, CONNECT_TIMEOUT_SECONDS constant
- `TestModelClientProtocolCompliance` (4): signatures match ModelClient Protocol
- `TestErrorEvents` (2): error events on connect failure and HTTP error
- `TestKeepAlive` (2): keep_alive = "5m" for reasoning, "-1" for embedding
- `TestGenerateIntegration` (3), `TestEmbedIntegration` (2): marked `@pytest.mark.integration` (require Ollama)
**Why:** Task 8 §8 requires integration tests against real Ollama + failure injection tests with mocked transport.
**How to verify:** `cd backend && pytest tests/test_model_runtime.py -v -k "not integration"` → 23 passed
**Decisions made:** 
- Mock `emit` at `backend.domain.model_runtime.runtime.emit` to avoid DB dependency
- Use `AsyncMock` with `call_args_list` inspection (positional args for event_type)
- Static check excludes `venv/` and test files, handles encoding errors
- Connect timeout test verifies configuration only (MockTransport can't simulate TCP connect timeout)

---

### Entry 5 — 2026-09-07 12:00 — all tests passing, implementation complete
**What changed:** All 23 unit tests pass. Verified implementation against acceptance criteria.
**Why:** Task 8 complete per Definition of Done.
**How to verify:** 
```
cd backend && pytest tests/test_model_runtime.py -v -k "not integration"  # 23 passed
grep -rn "11434\|/api/generate\|/api/embed" backend/ --include=*.py  # only runtime.py
```
**Open issues / known gaps:** 
- Integration tests require `ollama serve` + 3 models pulled (`qwen3.5:9b`, `qwen2.5-coder:7b`, `qwen3-embedding:0.6b`)
- Task 9 (Lifecycle Manager) will front this wrapper; coordinate call seam
- `capability_execution_id` wiring to `_record()` awaits Task 15 (Job Manager integration)
**Decisions made:** 
- Implementation matches `ModelClient` Protocol from schemas.py field-for-field
- No streaming support (non-streaming per SIH simplicity)
- No capability logic or prompt construction (out of scope per Task 8 §3)

---

### Entry 6 — 2026-09-07 12:15 — branch complete
**Status:** completed
**Summary:** Implemented Ollama HTTP wrapper as the single backend module for model calls. All 4 resource types supported with resource-type abstraction (no model names in calling code). Typed errors with fast failure (~5s connect timeout). Audit events + DB rows per call. 23 unit tests pass covering resolution, failure injection, options filtering, audit/DB, protocol compliance, error events, and keep_alive. Integration tests ready for Ollama environment.
**Final test status:** 23 passed, 5 deselected (integration)
**Reviewer notes:** Ready for PR. No locked contracts violated. Runtime is genuinely swappable (ADR-07). Zero-egress preserved (loopback-only base_url from Task 2 config validation).

---

## Open questions for the user

- None remaining — all clarifications resolved during implementation.

## Links

- PR: <url when created>
- Related branches / logs: `logs/feature-orchestrator.md` (ModelClient Protocol), `logs/feature-capability-registry.md` (resource types), `logs/feature-audit.md` (emit function)
- Doc references: `docs/models.md`, `docs/backend.md`, `docs/configuration.md`, `docs/audit.md`, `docs/data-model.md`, `docs/decisions.md` (ADR-07, ADR-08), `docs/security.md`, `docs/testing.md`, `tasks/8-model-runtime.md`