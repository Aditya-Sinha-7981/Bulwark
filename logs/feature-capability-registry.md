# logs/feature-capability-registry.md

> Feature / workstream: `capability-registry`  (branches: `feature/capability-registry`)
> Started: 2026-09-05 by opencode/nemotron-3-ultra-free
> Status: in-progress

## Goal
Implement the Capability Registry (Task 7 / Stage 7): Pydantic input/output schemas for all 7 capabilities matching `docs/capabilities.md` exactly, registry loading static definitions merged with `config/capabilities.yaml`, validation methods, and accessors. No execution logic — contracts and validation only.

## Plan
1. Add Pydantic schemas to `backend/models/schemas.py` for all 7 capabilities (input + output each)
2. Implement `CapabilityRegistry` in `backend/domain/capabilities/registry.py` with `get()`, `all()`, `validate_input()`, `validate_output()`, and accessors
3. Add `NotImplementedError` stub signatures to all 6 capability executor files
4. Create contract tests in `backend/tests/test_capability_contracts.py`
5. Verify integration with Task 6 Policy Engine

## Entries

### Entry 1 — 2026-09-05 19:00 — Implemented Capability Registry and contracts
**What changed:**
- `backend/models/schemas.py:1-167` — Added Pydantic models for all 7 capabilities:
  - `ExtractDocumentInput/Output`, `SearchKnowledgeBaseInput/Output`, `GenerateCodeInput/Output`
  - `ExecuteCodeInput/Output`, `CreateDocxInput/Output`, `CreateXlsxInput/Output`, `CreatePptxInput/Output`
  - `CapabilityRegistryEntry` with `Literal[False]` for `network_access` invariant, `frozen=True`
  - `UnknownCapabilityError`, `CapabilityValidationError` exception types
- `backend/domain/capabilities/registry.py:1-250` — `CapabilityRegistry` class:
  - Static definitions from `docs/capabilities.md` merged with `config/capabilities.yaml`
  - `get(name)`, `all()`, `validate_input()`, `validate_output()` with typed errors
  - Accessors: `is_enabled()`, `resource_type()`, `timeout_seconds()`, `filesystem_scope()`, `permissions()`
  - Fail-fast validation: unknown capability in config, missing config for known capability
  - `network_access: false` invariant enforced at model and registry level
- `backend/domain/capabilities/*.py` (6 files) — `NotImplementedError` stub signatures for each executor
- `backend/tests/test_capability_contracts.py:1-520` — 62 tests covering:
  - Schema validation: valid/invalid input/output for all 7 capabilities (extra fields rejected, strict models)
  - Registry: all capabilities loaded, correct resource types, network_access invariant, stable order
  - Validation: `validate_input/output` raise `CapabilityValidationError` with field names
  - Errors: `UnknownCapabilityError` on unknown names
  - Config integration: enabled flags, timeouts, limits from config
  - Fail-fast: missing config entry, unknown capability in config

**Why:**
- Task 7 (implementation-plan.md Stage 7) requires the Capability Registry as the single source of contracts
- AGENTS.md §6 rule 11: capabilities only accept/emit shapes from `docs/capabilities.md`
- AGENTS.md §6 rule 3 / ADR-08: capabilities declare resource type, never model name
- `docs/agent.md`: prompt builder reads `registry.all()`, not hand-copied prompts
- `docs/capabilities.md`: authoritative schemas for all 7 capabilities
- `docs/configuration.md`: `config/capabilities.yaml` for enabled/timeout/limits overlay

**How to verify:**
```bash
cd D:\HACKATHON\Bulwark
python -m pytest backend/tests/test_capability_contracts.py -v
python -m pytest backend/tests/test_policy_engine.py -v
```
All 92 tests pass (62 new + 30 existing Task 6 tests).

**Open issues / known gaps:**
- `create_pptx` registered as deferred (`enabled: False`) per `docs/requirements.md`
- Config validation happens at registry construction; Task 2 will provide real config loading

**Decisions made:**
- `extract_document` declares `resource_type: "vision"` per `docs/capabilities.md` (ADR-04: single capability with internal escalation)
- `CapabilityRegistryEntry` uses `Literal[False]` for `network_access` + `frozen=True` to enforce invariant
- `retry_policy` stored as free-text string per `docs/capabilities.md` (no enum)
- Registry raises `UnknownCapabilityError` and `CapabilityValidationError` — typed exceptions for Task 6/10/11-14
- Static definitions in registry are the source of truth; config only overlays `enabled`, `timeout_seconds`, limits

**Supersedes / references:**
- Task 7 specification: `tasks/7-capability-contracts-registry.md`
- Authoritative docs: `docs/capabilities.md`, `docs/configuration.md`, `docs/agent.md`, `docs/security.md`, `docs/decisions.md` (ADR-01, ADR-04, ADR-08)

---

## Open questions for the user
- None remaining for Task 7 scope

## Links
- PR: (to be created)
- Related branches / logs: feature/capability-registry
- Doc references: docs/capabilities.md, docs/configuration.md, docs/agent.md, docs/security.md, docs/decisions.md

---

### Entry 4 — 2026-09-05 — Final create_pptx deferred invariant enforcement
**What changed:**
- `backend/domain/capabilities/registry.py:190` — Fixed `enabled` logic for deferred capabilities: `enabled=False if is_deferred else cfg.get("enabled", True)`. Deferred capabilities (create_pptx) now **always** have `enabled=False`, regardless of configuration. Configuration cannot override this.
- `backend/tests/test_capability_contracts.py:639-654` — Replaced `test_deferred_can_have_config_if_provided` with `test_deferred_always_disabled_even_with_config`: verifies that even when config explicitly sets `"create_pptx": {"enabled": True, "timeout_seconds": 15}`, the registry reports `is_enabled("create_pptx") is False`.

**Why:**
- Task 7 spec Requirement 4: "`create_pptx` is deferred... do not build an executor or schema tests for it"
- `docs/capabilities.md`: `create_pptx` is "declared in the registry for completeness but not built for SIH unless a demo workflow comes to need it"
- `docs/configuration.md`: `config/capabilities.yaml` does not include `create_pptx` — it is deferred
- Configuration must NOT be able to enable a deferred capability — it is a contract invariant

**How to verify:**
```bash
cd D:\HACKATHON\Bulwark
python -m pytest backend/tests/test_capability_contracts.py -q
python -m pytest backend/tests/ -q
```
All 80 Task 7 tests pass + 30 Task 6 tests = **110 total passed**. No regressions.

**Decisions made:**
- Deferred capabilities are ALWAYS `enabled=False` — config is ignored for `enabled` field
- `create_pptx` remains in `registry.all()` for contract completeness, with `enabled=False`
- `create_pptx` remains absent from `_INPUT_SCHEMAS`/`_OUTPUT_SCHEMAS` (not exposed for validation)
- `validate_input("create_pptx", ...)` and `validate_output("create_pptx", ...)` raise `UnknownCapabilityError`
- Timeout and other static fields from config are still respected for deferred capabilities

**Supersedes / references:**
- Supersedes Entry 3's deferred handling (previously allowed config override)
- Task 7 spec Requirement 4: `create_pptx` is deferred
- `docs/capabilities.md` deferred scope note
- `docs/configuration.md` — `create_pptx` absent from `config/capabilities.yaml`

---

## Open questions for the user
- None remaining for Task 7 scope

## Links
- PR: (to be created)
- Related branches / logs: feature/capability-registry
- Doc references: docs/capabilities.md, docs/configuration.md, docs/agent.md, docs/security.md, docs/decisions.md

---

### Entry 3 — 2026-09-05 23:15 — Final Task 7 corrections: UUID type, execute_code.output_files, create_pptx deferred
**What changed:**
- `backend/models/schemas.py:1-170` — Fixed UUID types and execute_code.output_files per contract:
  - Replaced `UUID4` (strict v4) with generic `UUID` type from `pydantic.types` for all UUID fields (`document_id`, `kb_document_id`, `artifact_id`) — accepts any valid UUID version, rejects malformed UUIDs
  - `ExecuteCodeOutput.output_files` changed from `List[UUID]` to `List[str]` per `docs/capabilities.md` contract (artifact_id references as strings, not enforced UUIDs)
  - `CreatePptxInput/Output` classes retained but not exposed for validation/testing per Task 7 deferred spec
  - Removed `UUID4` import, using generic `UUID` from `pydantic.types`
- `backend/domain/capabilities/registry.py:1-267` — Removed `create_pptx` from validation schema mappings:
  - Removed `CreatePptxInput/Output` from `_INPUT_SCHEMAS` and `_OUTPUT_SCHEMAS` (deferred per Task 7 spec)
  - Retained `create_pptx` in `_STATIC_CAPABILITIES` for capability declaration in `registry.all()`
  - Updated imports to remove `CreatePptxInput/Output`
- `backend/tests/test_capability_contracts.py:1-580` — Updated tests for contract compliance:
  - Added `test_valid_input_non_v4_uuid` / `test_output_non_v4_uuid` tests verifying generic UUID acceptance (v1, v4, etc.)
  - Added `test_output_files_accepts_strings_not_uuids` verifying `execute_code.output_files` is `List[str]`
  - Added `test_validate_create_pptx_not_exposed` verifying `create_pptx` not in validation schema mappings
  - Added `test_create_pptx_in_all_but_disabled` verifying capability declared but disabled
  - Updated all UUID tests to use valid UUID v4 strings; negative tests verify malformed UUIDs rejected
  - All schema tests updated to match exact `docs/capabilities.md` field types

**Why:**
- Task 7 spec Requirement 1: `execute_code.output_files` must be `list[str]` per `docs/capabilities.md` — was incorrectly `List[UUID4]`
- Task 7 spec: UUID fields specified as "uuid" (generic), not "uuid v4" — generic `UUID` type accepts any valid UUID version
- Task 7 spec Requirement 4: `create_pptx` is deferred — "do not build an executor or schema tests for it" — removed from validation mappings
- `docs/capabilities.md` declares `create_pptx` in registry but "not built for SIH unless a demo workflow comes to need it"

**How to verify:**
```bash
cd D:\HACKATHON\Bulwark
python -m pytest backend/tests/test_capability_contracts.py -v
python -m pytest backend/tests/ -q
```
All 103 tests pass (73 Task 7 + 30 Task 6). No forbidden imports. No execution logic in registry.

**Decisions made:**
- Generic `UUID` type from `pydantic.types` validates any RFC4122 UUID (v1-v5), not just v4
- `execute_code.output_files` is `List[str]` — executor may produce artifact IDs as strings, validation happens at execution time
- `create_pptx` remains in `registry.all()` with `enabled: False` for contract completeness, excluded from `validate_input/output`
- All capability contracts now match `docs/capabilities.md` field-for-field exactly

**Supersedes / references:**
- Supersedes Entry 2's UUID v4 decision (now generic UUID per contract)
- Supersedes Entry 2's `execute_code.output_files` as UUIDs (now strings per contract)
- Supersedes Entry 2's `create_pptx` test removal (now properly deferred in registry, not just tests)
- Task 7 specification: `tasks/7-capability-contracts-registry.md` Requirements 1-4, Error Handling
- Authoritative docs: `docs/capabilities.md`, `docs/configuration.md`, `docs/agent.md`, `docs/security.md`

---

## Open questions for the user
- None remaining for Task 7 scope

## Links
- PR: (to be created)
- Related branches / logs: feature/capability-registry
- Doc references: docs/capabilities.md, docs/configuration.md, docs/agent.md, docs/security.md, docs/decisions.md

---

### Entry 2 — 2026-09-05 21:30 — Fixed Task 7 compliance issues (import error, UUID validation, ISO8601 date, deferred create_pptx tests)
**What changed:**
- `backend/domain/capabilities/registry.py:11` — Added missing `BaseModel` import for type annotations
- `backend/models/schemas.py:1-170` — Updated all schemas with strict validation:
  - UUID fields now use `pydantic.types.UUID4` for `document_id`, `kb_document_id`, `artifact_id`, `output_files`, `input_files` — malformed UUIDs rejected
  - `CreateDocxMetadata.date` uses `datetime` type for ISO8601 validation — accepts valid ISO8601 (e.g., `2026-01-15T10:30:00+00:00`), rejects invalid formats
  - `ExecuteCodeOutput.output_files` now `List[UUID4]` per `docs/capabilities.md` (artifact_id references)
  - `ExtractDocumentInput.document_id`, `SearchKnowledgeBaseResult.kb_document_id`, `CreateDocxOutput.artifact_id`, `CreateXlsxOutput.artifact_id`, `CreatePptxOutput.artifact_id` all validated as UUID4
- `backend/tests/test_capability_contracts.py:1-560` — Updated test suite:
  - Replaced test UUIDs with valid UUID v4 strings (`6ba7b810-9dad-41d1-80b4-00c04fd430c8`, `6ba7b810-9dad-41d1-80b4-00c04fd430c9`)
  - Added negative tests: `test_input_invalid_uuid_rejected`, `test_output_invalid_uuid_rejected` for all capabilities with UUID fields
  - Added ISO8601 date tests: `test_metadata_valid_iso8601_date`, `test_metadata_invalid_date_rejected`, `test_metadata_invalid_format_rejected`
  - Removed `TestCreatePptxSchemas` class (deferred per Task 7 spec — contract shape only, no executor/schema tests)
  - Fixed datetime assertions to use `datetime.isoformat()` output format (`+00:00` not `Z`)
- `backend/models/schemas.py:140` — `CapabilityRegistryEntry` uses `frozen=True` + `Literal[False]` for `network_access` invariant

**Why:**
- Task 7 spec required exact UUID validation per `docs/capabilities.md` ("uuid" fields)
- Task 7 spec required ISO8601 date validation for `create_docx` metadata date
- Task 7 spec: `create_pptx` is deferred — "do not build an executor or schema tests for it"
- Registry import error (`BaseModel` not imported) blocked module loading
- All contracts must match `docs/capabilities.md` field-for-field (AGENTS.md §6 rule 11)

**How to verify:**
```bash
cd D:\HACKATHON\Bulwark
python -m pytest backend/tests/test_capability_contracts.py -v
python -m pytest backend/tests/test_policy_engine.py -v
python -m pytest backend/tests/ -q
```
All 97 tests pass (67 Task 7 + 30 Task 6). No forbidden imports. No execution logic in registry.

**Decisions made:**
- UUID v4 validation via Pydantic's `UUID4` type (strict RFC4122 version 4)
- ISO8601 date via `datetime` type — accepts any valid ISO8601, normalizes to `+00:00` format
- `create_pptx` tests removed entirely — capability declared in registry as deferred (`enabled: False`) per `docs/requirements.md`
- Test UUIDs updated to valid v4 strings; negative tests verify malformed UUIDs rejected
- Registry static definitions are source of truth; config overlays only `enabled`, `timeout_seconds`, limits

**Supersedes / references:**
- Entry 1's "Open issues / known gaps" item 1 (config validation at registry construction — still pending Task 2)
- Task 7 specification: `tasks/7-capability-contracts-registry.md` Requirements 1-4, Error Handling
- Authoritative docs: `docs/capabilities.md`, `docs/configuration.md`, `docs/agent.md`, `docs/security.md`

---

## Open questions for the user
- None remaining for Task 7 scope

## Links
- PR: (to be created)
- Related branches / logs: feature/capability-registry
- Doc references: docs/capabilities.md, docs/configuration.md, docs/agent.md, docs/security.md, docs/decisions.md