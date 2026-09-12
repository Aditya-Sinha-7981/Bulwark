# logs/feature-sandbox.md

> Feature / workstream: `feature-sandbox`  (branches: `feature/sandbox`, …)
> Started: 2026-09-09 by nemotron-3-ultra-free
> Status: completed

## Goal
Implement the `generate_code` and `execute_code` capabilities for demo Workflow B (code generation → sandboxed execution → verification), plus the Docker sandbox image. These must stay two distinct, separately-audited Orchestrator steps — never merged into one capability or one step.

## Plan
1. Update `sandbox/Dockerfile` — minimal Python 3.11-slim base with only Python runtime + stdlib, working dir `/workspace`
2. Implement `backend/domain/sandbox/docker_executor.py` — container lifecycle per `docs/sandbox.md`: write code to `data/sandbox/{execution_id}/input/`, copy input_files, invoke Docker via subprocess with exact flags from config, enforce timeout with docker kill, capture stdout/stderr/exit_code, collect output files, cleanup in finally block
3. Implement `backend/domain/capabilities/execute_code.py` — validate input, call docker_executor, return raw result `{stdout, stderr, exit_code, timed_out, output_files: [<raw filename>, ...]}`
4. Implement `backend/domain/capabilities/generate_code.py` — validate input, call Model Runtime `code_generation` resource, shape output `{code, language, explanation}`, validate output
5. Write `backend/tests/test_sandbox.py` — all 10 required test cases
6. Build Docker image and run tests
7. Manual verification
8. Update log, propose commit message

## Entries

### Entry 1 — 2026-09-09 16:00 — Initial setup and Dockerfile update
**What changed:** Created `logs/feature-sandbox.md`, updated `sandbox/Dockerfile` to match the spec (minimal Python 3.11-slim, only runtime + stdlib)
**Why:** Starting implementation of Task 13 (code generation + sandbox execution) per the task file and docs/sandbox.md
**How to verify:** Docker build succeeds, image contains only Python runtime + stdlib
**Open issues / known gaps:** Model Runtime `code_generation` interface not yet implemented (runtime.py is empty) — will need a stub for generate_code
**Decisions made:** Following the existing capability executor pattern from create_docx.py (validate_input, validate_output, execute_* functions)
**Supersedes / references:** None

### Entry 2 — 2026-09-09 16:15 — Implemented docker_executor.py and execute_code.py
**What changed:** 
- `backend/domain/sandbox/docker_executor.py`: Full container lifecycle implementation per docs/sandbox.md — writes code to sandbox input dir, copies input_files, invokes Docker via subprocess with exact flags from config (--rm --network none --cpus --memory --read-only -v input:ro -v output:rw --workdir /workspace), enforces timeout with docker kill, captures stdout/stderr/exit_code, collects output files, cleans up in finally block
- `backend/domain/capabilities/execute_code.py`: Capability executor with validate_input, validate_output, execute_execute_code; returns raw result with candidate filenames (not artifact_ids)
**Why:** Core sandbox execution logic
**How to verify:** Unit tests pass, docker build + test execution works
**Open issues / known gaps:** Model Runtime stub in generate_code.py — needs real implementation from Task 8
**Decisions made:** Using subprocess for Docker CLI (no Docker SDK), config values from settings.capabilities.execute_code, raw filenames in output_files (Task 15 converts to artifact_ids)
**Supersedes / references:** Entry 1

### Entry 3 — 2026-09-09 16:30 — Implemented generate_code.py and test_sandbox.py
**What changed:**
- `backend/domain/capabilities/generate_code.py`: Capability executor with validate_input, validate_output, execute_generate_code; uses ModelRuntimeStub for code_generation resource call (Task 8 not yet implemented), parses CODE:/EXPLANATION: format
- `backend/tests/test_sandbox.py`: Comprehensive test suite with all 10 required test cases plus static checks
**Why:** Complete the two capabilities and test coverage per docs/testing.md "Sandbox tests"
**How to verify:** Build Docker image, run pytest tests/test_sandbox.py -v
**Open issues / known gaps:** 
- Model Runtime stub in generate_code.py — needs real implementation from Task 8
- Full timeout test requires 30s wait — marked as skip in automated suite
- Docker daemon unavailable test requires stopping Docker — marked as skip
**Decisions made:** Stub is swappable; timeout test documented for manual verification; static checks ensure no OS-specific branches and only execute_code/docker_executor touch Docker
**Supersedes / references:** Entry 2

### Entry 4 — 2026-09-09 18:00 — Reconciled pre-built files with real repo, all unit tests pass
**What changed:**
- Updated `backend/domain/sandbox/docker_executor.py` with pre-flight Docker availability check (`_check_docker_available`, `DockerUnavailableError`), `SandboxResult` dataclass, `is_docker_available()`, proper `docker kill` with container name, Windows-compatible mount parsing
- Updated `backend/domain/capabilities/execute_code.py` to use async `execute_execute_code` matching real repo pattern, added non-empty code validation, `uploads_path` resolution for input_files
- Updated `backend/domain/capabilities/generate_code.py` with non-empty task_description and code validation
- Added 4 new test files: `test_docker_executor_unit.py` (11 tests), `test_execute_code_capability.py` (10 tests), `test_generate_code_capability.py` (10 tests), `test_sandbox_static_checks.py` (3 tests)
- All 34 new unit tests pass + 274 existing tests pass (1 pre-existing failure in test_config.py unrelated to changes)
- Docker not available in this environment — integration tests in test_sandbox.py skip cleanly with clear reason
**Why:** Integrate the pre-built implementation with the actual repository's schema layer (backend/models/schemas.py), config loader (backend/config.py), paths module (backend/utils/paths.py), and capability registry
**How to verify:** `pytest backend/tests/test_docker_executor_unit.py backend/tests/test_execute_code_capability.py backend/tests/test_generate_code_capability.py backend/tests/test_sandbox_static_checks.py -v` — all 34 tests pass
**Open issues / known gaps:** 
- Docker daemon not available in this environment — `test_sandbox.py` (9 integration tests) skipped. Must be run on machine with Docker Desktop and `docker build -t bulwark-sandbox:latest ./sandbox` before Task 13 is fully verified.
- Model Runtime `code_generation` interface (`backend/domain/model_runtime/runtime.py`) is still empty (Task 8). `generate_code.py` uses a swappable `ModelRuntimeStub` — documented in log. When Task 8 is ready, bind `_call_model_runtime` to the real `model_runtime.generate("code_generation", prompt)`.
- Output-file cleanup vs Task 15 Artifact hand-off: `docker_executor.py` deletes temp dir in finally block (per sandbox.md literal step order). Task 15 will need the file bytes to create Artifacts. This architectural seam needs decision before Task 15 — flagged in Entry 1 of the pre-build log.
**Decisions made:** 
- Kept the 4 extra test files as permanent additions (they test the same modules and provide fast CI feedback without Docker)
- Stub pattern in generate_code.py is swappable — no duplicate schema definitions
- All Docker CLI flags exactly match docs/sandbox.md and config/capabilities.yaml
- No OS-specific branches anywhere in the implementation
**Supersedes / references:** Entry 3

### Entry 5 — 2026-09-09 19:30 — Updated test_execute_code_capability.py to match real implementation; confirmed exit_code: -1 convention
**What changed:**
- Rewrote `backend/tests/test_execute_code_capability.py` to match the actual async `execute_execute_code` implementation:
  - Fixed patch path to `"backend.domain.capabilities.execute_code.run_in_sandbox"`
  - Added test for timeout returning `exit_code=-1` (not `None`) — real impl converts None→-1 for schema compliance
  - Added test for other execution errors returning structured failure
  - Added proper input file resolution tests using real `uploads_path` mechanism with monkeypatched `UPLOADS_ROOT`
- Full test suite: 319 passed, 1 failed (pre-existing `test_config.py::test_path_helpers_reject_absolute_input`)
**Why:** The pre-built tests assumed the old sync interface and `exit_code: None` convention; updated to match the real integration
**How to verify:** `pytest backend/tests/ -v` — only the known pre-existing failure remains
**Open issues / known gaps:** None new
**Decisions made:** 
- **`exit_code: -1` on Docker-unavailable/timeout/error** — decided against the real `ExecuteCodeOutput` schema in `backend/models/schemas.py` which types `exit_code: int` (not `Optional[int]`). Returning `None` would fail Pydantic validation. The `-1` sentinel is the standard Unix convention for "abnormal termination without a real exit code" and is explicitly checked in tests. Documented here for traceability.
- Timeout test now asserts `exit_code == -1` (not `None`) — matches real implementation behavior where `docker_executor.py` returns `None` but `execute_code.py` converts to `-1` before schema validation.
**Supersedes / references:** Entry 4

---

### Entry 6 — 2026-09-12 12:19 — generate_code wired to the real Model Runtime; stub removed; fenced-response parsing hardened (branch `fix/model-runtime-num-ctx-and-timeout`)

**What changed:**
- `backend/domain/capabilities/generate_code.py` — `ModelRuntimeStub` deleted; `_call_model_runtime(prompt, job_id=None)` now calls the real `model_runtime.generate("code_generation", prompt, job_id=job_id)` (module-level singleton from Task 8). Resolves Open question #4 below. Module docstring's stale "not yet implemented (Task 8)" note removed. Also hardened `_parse_model_response()`: markdown code fences are stripped from the CODE: section, and a fallback path now extracts ```python fenced block(s) as code with surrounding prose as explanation — coder models emit fences despite the format instructions.
- `backend/tests/test_generate_code_capability.py` — happy-path tests now monkeypatch `_call_model_runtime` with canned responses (hermetic, was stub-dependent); fake model signatures gained `*, job_id=None`; new `TestParseModelResponse` class (4 tests: instructed format, fenced-without-markers, fences-inside-CODE:, plain fallback).

**Why:** Observed live (job `a28d1a22`, 2026-09-12, Phase 5 / Workflow B): the Orchestrator proposed `generate_code` 4× with varying args and hit malformed output 4× of ~7 steps — because the stub returned canned `2 + 2` code for a tanks-volume task (keyword fallback), the Orchestrator thrashed against a useless tool result. The trace also showed **zero `model_invoked` events for `code_generation`** — the stub never called Ollama, violating the `docs/audit.md` model_invoked contract and leaving `qwen2.5-coder:7b` unused. Sanity script against live Ollama after the fix: correct tanks script generated; the model emitted a fenced block (not the instructed CODE:/EXPLANATION: format), which the previous parser's fallback would have passed to the sandbox verbatim (`\`\`\`python` first line → guaranteed SyntaxError) — hence the parser hardening in the same change.

**How to verify:**
- `backend/.venv/bin/python -m pytest backend/tests/test_generate_code_capability.py -q` → 14 passed.
- Full non-integration suite → 507 passed; only failure remains the pre-existing environmental dispatch test.
- Live: run Workflow B (B1) in a fresh conversation → trace must now show `model_invoked` events with `resource_type: "code_generation"` / `qwen2.5-coder:7b` alongside the reasoning calls; generated code is fence-free.

**Open issues / known gaps:**
- The malformed-output frequency in the failing trace (4/8 turns non-JSON) was driven by the stub's useless tool result — expect improvement with real code results, but the 9B reasoning model's JSON discipline under long tool-result context remains a watch item (corrective-turn mechanism handles it; each malformed after the first costs a step).
- Open question #1 below still stands: Docker-backed execute_code integration tests have not been run for real (needs Docker Desktop + `bulwark-sandbox:latest` built) — that's the user's Phase 5 step.

**Decisions made:**
- Reused the module-level `runtime` singleton and passed `job_id` through — matches `vision_escalation.py`'s call pattern; audit attribution per `docs/audit.md`.
- Parser prefers the instructed CODE:/EXPLANATION: format and only falls back to fence extraction; `[]`-fence-stripping also applies when fences appear *inside* the CODE: section.

**Supersedes / references:** Resolves Open question #4 (stub wiring); follows Entry 5. The stub's docstring referenced this log's known gap — now closed.

---

### Entry 7 — 2026-09-12 12:45 — execute_code never imported at runtime: stale `domain.` import (branch `fix/model-runtime-num-ctx-and-timeout`)

**What changed:**
- `backend/domain/capabilities/execute_code.py:15` — `from domain.capabilities.registry import get_registry` → `from backend.domain.capabilities.registry import get_registry`. One-line import-layout fix; no behavioral change to the executor logic.

**Why:** Observed live (job `a6bd3285`, 2026-09-12, Phase 5 / Workflow B): `generate_code` now works (Entry 6), but the first real `execute_code` invocation failed with `ModuleNotFoundError: No module named 'domain'` — the step failed with exactly that message (the dispatch wraps exceptions as `f"{type(exc).__name__}: {exc}"`). Root cause: the executor module was written against the pre-`backend.`-package import layout and **only ever imported successfully under pytest** (`pytest.ini: pythonpath = . ..`), because the live server (repo root on sys.path) has no top-level `domain` package — so the module crashed at import on first dispatch. It has therefore never executed for real. The sandboxed code itself was verified clean via the DB (`job_steps.input_payload` — a simple stdlib classification script, no `domain` import); the container never ran. The model then honestly reported the failure instead of fabricating success — correct B4-style behavior.

**How to verify:**
- `backend/.venv/bin/python -c "import backend.domain.capabilities.execute_code"` → imports cleanly under the live layout.
- `backend/.venv/bin/python -m pytest backend/tests/test_execute_code_capability.py -q` → 12 passed.
- Full non-integration suite → 516 passed (collects the execute_code tests that previously couldn't import); only failure remains the pre-existing environmental dispatch test.
- Live: re-run Workflow B in a fresh conversation — `execute_code` should now actually start a container; expect stdout with the computed classifications (or, if Docker Desktop isn't running / image missing, an honest structured `docker_unavailable`-style failure, not an import crash).

**Open issues / known gaps:**
- Open question #1 (Docker-backed integration tests run for real) still stands — the first successful `execute_code` run in the live environment doubles as that verification.
- Worth a sweep for other stale-layout imports in live-dispatched modules — `rg "from domain\." backend -g '!tests'` found only this one (now fixed), but noting the pattern here since it survived until a real invocation.

**Decisions made:** Minimal one-line fix; no test changes needed (the test file already imports via `backend.`).

**Supersedes / references:** Follows Entry 6 — together they make Workflow B's `generate_code → execute_code` chain live for the first time.

---

## Open questions for the user
1. **Docker-backed integration tests must be run for real** on a machine with Docker Desktop running and `bulwark-sandbox:latest` built, before Task 13's acceptance criteria can be considered fully met. This build only proves the tests are written correctly and the Python logic around Docker is sound; it does not prove Docker itself behaves as expected end-to-end (real `--network none` enforcement, real `--read-only` enforcement, real timeout/kill behavior under actual container startup latency, etc.).

2. **Output-file cleanup vs. Task 15's Artifact conversion** (see Entry 1 of pre-build log in 10_feature-sandbox-log.md). Needs an explicit decision: does cleanup move to a separate, Job-Manager-triggered call, or does this module return file bytes instead of just names? This affects `docker_executor.py`'s public interface and should be decided before Task 15 starts.

3. **`exit_code: null` on timeout** — is `null`/`None` acceptable against `docs/capabilities.md#execute_code`'s output schema (which types it as an integer, `0` by convention for success), or should timeout use a specific sentinel integer? Current implementation returns `None` on timeout (honest representation — no real exit code exists). The registry's `ExecuteCodeOutput` schema has `exit_code: int` — may need adjustment.

4. **Real Model Runtime integration for `generate_code.py`** — this build uses `ModelRuntimeStub` with `_call_model_runtime` as an internal async function. When Task 8 delivers `backend/domain/model_runtime/runtime.py`, wire it to the real `generate()` method. The current stub is fully self-contained and testable.

## Links
- PR: <url when created>
- Related branches / logs: feature/sandbox
- Doc references: docs/sandbox.md, docs/capabilities.md, docs/configuration.md, docs/models.md, docs/security.md, docs/decisions.md (ADR-05), docs/demo.md (Workflow B), docs/testing.md (Sandbox tests)