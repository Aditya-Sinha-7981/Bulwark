# logs/feature-policy.md

> Feature / workstream: `policy`  (branches: `feature/policy`)
> Started: 2026-09-05 by opencode/nemotron-3-ultra-free
> Status: in-progress

## Goal
Implement the deterministic Policy engine (Task 6 / Stage 6): pure functions that evaluate capability proposals against 5 deterministic rules, returning allow/deny with specific rule identifiers. No side effects, fully unit-testable in isolation. Implements ADR-02 (deterministic Policy layer) and requirement N5 (Policy enforcement cannot be bypassed).

## Plan
1. Create `PolicyDecision` model in `backend/models/schemas.py`
2. Implement `evaluate()` and 5 rule-checking functions in `backend/domain/policy/engine.py`
3. Create unit tests in `backend/tests/test_policy_engine.py` with allow/deny per rule
4. Run tests, verify no forbidden imports, confirm determinism

## Entries

### Entry 1 — 2026-09-05 14:30 — Implemented deterministic Policy engine
**What changed:**
- `backend/models/schemas.py:1-8` — Added `PolicyDecision` Pydantic model with `decision: Literal["allow", "deny"]`, `reason: str`, `rule: str`
- `backend/domain/policy/engine.py:1-313` — Implemented `evaluate()` orchestrating 5 rules in order (first deny wins):
  1. **Registered & enabled** (`unknown_capability`, `capability_not_enabled`) — checks registry entry exists and `config/capabilities.yaml` enabled flag
  2. **Permissions** (`missing_permission`) — validates declared permission tokens against recognized set for SIH single trust level
  3. **Network-access invariant** (`network_access_invariant`) — UNCONDITIONAL: both capability `network_access` and config `network_access_allowed` must be `false`
  4. **Filesystem scope** (`filesystem_scope_violation`) — scoped path resolution rejects traversal (`../`), absolute paths, and cross-job directory access
  5. **Resource limits** (`resource_limit_exceeded`) — validates requested timeout against configured bounds
- `backend/tests/test_policy_engine.py:1-395` — 19 unit tests covering allow/deny per rule, determinism (100 iterations), forbidden imports check, malformed arguments handling

**Why:**
- Task 6 (implementation-plan.md Stage 6) requires the deterministic Policy engine as the gate between every Orchestrator proposal and execution
- ADR-02 / AGENTS.md §6 rule 2: Policy must be fully deterministic, never model-based
- `docs/security.md` "Deterministic Policy" and `docs/capabilities.md` "Policy checks" define the 5 rules
- Engine must be pure (no DB/model/network/emit imports) so Job Manager (Task 15) can call it and emit `policy_decision` audit event

**How to verify:**
```bash
cd D:\HACKATHON\Bulwark
python -m pytest backend/tests/test_policy_engine.py -v
```
All 19 tests pass including: allow/deny per rule, network invariant unconditional denial, filesystem scope traversal/absolute path rejection, resource limit enforcement, determinism (100 identical evaluations), no forbidden imports.

**Open issues / known gaps:**
- Filesystem scope mapping uses hardcoded base paths from `config/app.yaml` — will need to read from actual config when Task 2 lands
- Resource limits only checks timeout_seconds; max_output_bytes for execute_code is validated at execution time, not in Policy (per design)
- Permissions rule validates token recognition only (no RBAC per SIH scope)

**Decisions made:**
- Rule order is fixed: registered/enabled → permissions → network invariant → filesystem → resource limits — matches `docs/security.md` summary order
- Unknown capability returns `deny` with `unknown_capability` (not exception) — aligns with `agent.md` "Hallucinated capability handling"
- Malformed arguments (non-dict) returns `deny` with `malformed_arguments` — fail closed per task requirement
- Network invariant is truly unconditional: no capability argument or config can override it — implements AGENTS.md §6 rules 9, 10
- Scoped path resolution uses `os.path` for cross-platform compatibility (Windows/macOS)

**Supersedes / references:**
- Task 6 specification: `tasks/6-policy-engine.md`
- Authoritative docs: `docs/security.md`, `docs/capabilities.md`, `docs/configuration.md`, `docs/agent.md`, `docs/decisions.md` (ADR-02)

---

## Open questions for the user
- Filesystem scope base paths currently hardcoded — confirm reading from `config/app.yaml` paths section when Task 2 merges
- Permissions rule interpretation: validate tokens only (no RBAC) — confirmed per `docs/capabilities.md` "SIH single trust level"

## Links
- PR: (to be created)
- Related branches / logs: feature/policy
- Doc references: docs/security.md, docs/capabilities.md, docs/configuration.md, docs/agent.md, docs/decisions.md (ADR-02)

---

### Entry 2 — 2026-09-05 16:45 — Fixed Task 6 compliance gaps
**What changed:**
- `backend/utils/paths.py:1-124` — NEW FILE: Created scoped filesystem path helpers (`resolve_within_scope`, `is_within_scope`, `get_base_path_for_capability`, `extract_path_from_arguments`) for cross-platform path validation against declared capability `filesystem_scope`
- `backend/domain/policy/engine.py:1-341` — Major updates to all 5 rules:
  - **Rule 3 (Network invariant)**: Added fail-closed checks for missing `policy` section and missing `network_access_allowed` in config (previously defaulted to `False`)
  - **Rule 4 (Filesystem scope)**: Replaced hardcoded scope mapping with validation against registry entry's declared `filesystem_scope`; now uses `backend.utils.paths` for path extraction and resolution; properly handles relative filenames (e.g., "file.txt") by joining with scope base path; added `app_config` parameter to read base paths from `config/app.yaml`
  - **Rule 5 (Resource limits)**: Added `max_output_bytes` validation for `execute_code` capability (fail closed if missing or invalid); added fail-closed check for missing `timeout_seconds` in any capability config; added fail-closed for missing capability config entirely
  - Updated `evaluate()` signature to accept optional `app_config` parameter
- `backend/tests/test_policy_engine.py:1-655` — Added 10 new tests:
  - `test_deny_missing_policy_section`, `test_deny_missing_network_access_allowed` (Rule 3 fail-closed)
  - `test_deny_path_outside_declared_scope`, `test_allow_path_within_declared_scope`, `test_deny_capability_with_no_filesystem_scope_but_path_in_args` (Rule 4 against declared scope)
  - `test_deny_missing_timeout_seconds_in_config`, `test_deny_missing_max_output_bytes_in_execute_code_config`, `test_deny_invalid_max_output_bytes_in_config`, `test_allow_other_capabilities_without_max_output_bytes`, `test_allow_create_docx_without_max_output_bytes` (Rule 5 fail-closed + max_output_bytes)
  - Updated `test_deny_malformed_arguments_not_dict` to assert specific `malformed_arguments` rule
  - All filesystem tests now use `valid_app_config` fixture

**Why:**
- Task 6 spec requires: "A config value missing for a rule → fail closed: `deny` with a clear `reason`, and surface the config gap (do not silently `allow`)"
- Task 6 spec requires: "Resource limits — requested/effective `timeout_seconds` and any output-size bound are within the configured values" — `max_output_bytes` for `execute_code` was missing
- Task 6 spec requires: "Filesystem scope — every path implied by `arguments` resolves within the capability's declared `filesystem_scope`" — was using hardcoded mapping instead of registry entry's declared scope
- Task 6 spec requires: "Resolve via scoped path helpers (`backend/utils/paths.py`)" — was not using the path helpers module

**How to verify:**
```bash
cd D:\HACKATHON\Bulwark
python -m pytest backend/tests/test_policy_engine.py -v
```
All 29 tests pass including: fail-closed on missing config for all rules, `max_output_bytes` validation for `execute_code`, filesystem scope validation against declared `filesystem_scope` from registry, relative filename handling, cross-platform path resolution.

**Open issues / known gaps:**
- None remaining for Task 6 scope

**Decisions made:**
- Fail-closed on missing config is implemented for: network_access_allowed, timeout_seconds, max_output_bytes, capability config section
- Filesystem scope now validates against BOTH the registry entry's `filesystem_scope` AND the base path from `app_config` (defense in depth)
- Relative filenames (no path separators) are now properly validated by joining with scope base path
- `max_output_bytes` is only required for `execute_code`; other capabilities don't need it
- `app_config` parameter is optional (defaults to None) for backward compatibility

**Supersedes / references:**
- Supersedes Entry 1's "Open issues / known gaps" items 1, 2, and 4 (all resolved)
- Task 6 specification: `tasks/6-policy-engine.md` Requirements 2 (Rules 3, 4, 5) and Error Handling
- Authoritative docs: `docs/security.md`, `docs/capabilities.md`, `docs/configuration.md`

## Open questions for the user
- None remaining for Task 6

## Links
- PR: (to be created)
- Related branches / logs: feature/policy
- Doc references: docs/security.md, docs/capabilities.md, docs/configuration.md, docs/agent.md, docs/decisions.md (ADR-02)

---

### Entry 3 — 2026-09-05 18:30 — Fixed Rule 1 fail-closed on missing enabled flag
**What changed:**
- `backend/domain/policy/engine.py:69-96` — Updated `_check_registered_and_enabled` to fail closed when `enabled` is missing from capability config:
  - `enabled: true` → passes (allow)
  - `enabled: false` → deny with `capability_not_enabled`
  - `enabled` missing → deny with `capability_not_enabled` and clear reason "Missing enabled flag in capability configuration for '{capability_name}'"
- `backend/tests/test_policy_engine.py:154-178` — Added `test_deny_missing_enabled_flag` test verifying fail-closed behavior for missing `enabled` config

**Why:**
- Task 6 spec Requirement 2 Rule 1: "Registered & enabled — the capability exists in the Registry and `config/capabilities.yaml` `<name>.enabled` is `true`. Unknown capability → `deny` (`unknown_capability`). Disabled → `deny` (`capability_not_enabled`)."
- Task 6 spec Error Handling: "A config value missing for a rule → fail closed: `deny` with a clear `reason`, and surface the config gap (do not silently `allow`)."
- The previous implementation only denied when `enabled` was explicitly `false`, silently allowing when missing — violating fail-closed principle.

**How to verify:**
```bash
cd D:\HACKATHON\Bulwark
python -m pytest backend/tests/test_policy_engine.py -q
```
All 30 tests pass including new `test_deny_missing_enabled_flag`.

**Decisions made:**
- Uses same rule identifier `capability_not_enabled` for both disabled and missing cases (consistent with "not enabled" semantics)
- No new rule identifier invented — reuses existing stable identifier
- No changes to capability arguments or fields — strictly config validation

**Supersedes / references:**
- Task 6 specification: `tasks/6-policy-engine.md` Requirement 2 Rule 1 and Error Handling
- Authoritative docs: `docs/configuration.md` (capabilities.yaml schema with `enabled: true`)
---

### Entry 4 — 2026-09-06 01:00 — Resolved merge conflicts with main branch (Tasks 1-5)

**What changed:**
- `backend/models/schemas.py` — Restored main's full schema (DB row dataclasses + config models + `PolicyDecision = str` type alias). Removed branch's minimal Pydantic `PolicyDecision` model which was incompatible with main's `CapabilityExecutionRow` expecting string `policy_decision`/`policy_reason`.
- `backend/utils/paths.py` — Restored main's `settings`-based path helpers using `pathlib.Path` and `backend.config`. Fixed import to use `from backend.config import REPO_ROOT, settings`.
- `backend/config.py` — Restored from main (was empty). Fixed import to use `from backend.models.schemas import ...`.
- `backend/domain/policy/paths.py` — NEW FILE: Policy-engine scoped path authorization helpers built on top of `backend.utils.paths` canonical roots. Contains `resolve_within_scope`, `is_within_scope`, `get_allowed_scopes_for_capability`, `extract_paths_from_arguments`.
- `backend/domain/policy/engine.py` — Updated to:
  - Import from `backend.domain.policy.paths` instead of `backend.utils.paths`
  - Return `dict` with `policy_decision`, `policy_reason`, `rule` matching `CapabilityExecutionRow` fields (not Pydantic model)
  - Use `_make_decision()` helper for consistent decision objects
  - Removed `app_config` parameter (now uses canonical paths from `backend.utils.paths` via policy paths module)
  - Filesystem scope validates against both registry entry's declared `filesystem_scope` AND canonical capability scopes from config
- `backend/tests/test_policy_engine.py` — Updated to use dict-style access (`decision["policy_decision"]`) and match new return format
- `config/*.yaml` — Restored from main (were empty on branch)

**Why:**
- Main branch completed Tasks 1-5 (config loading, data model, audit, job system) which provide the infrastructure the Policy Engine depends on
- The Policy branch (Task 6) was developed in parallel and re-implemented core types (`schemas.py`, `paths.py`) that already exist on main with different designs
- Per merge guide (`tasks/temp-docs/merge conflict Resolution.md`): Keep main's implementation as canonical; adapt branch to use it
- The Pydantic `PolicyDecision` model on branch was incompatible with main's `CapabilityExecutionRow` (expects string fields), repositories, and audit events

**How to verify:**
```bash
cd /Users/adityasinha/Files/Codes/Hackathons/Bulwark
python3 -m pytest backend/tests/test_policy_engine.py -v
```
All 30 tests pass including: allow/deny per rule, network invariant unconditional denial, filesystem scope traversal/absolute path rejection, resource limit enforcement, determinism (100 identical evaluations), no forbidden imports.

**Open issues / known gaps:**
- None for Task 6 scope — all rules implemented and tested

**Decisions made:**
- Policy engine returns dict matching `CapabilityExecutionRow` fields: `{policy_decision, policy_reason, rule}`
- Policy-specific path helpers live in `backend/domain/policy/paths.py`, built on canonical roots from `backend.utils.paths`
- No `app_config` parameter needed in `evaluate()` — uses canonical paths from config
- Filesystem scope defense-in-depth: validates against both registry entry's declared scope AND canonical capability scopes

**Supersedes / references:**
- Merge conflict resolution guide: `tasks/temp-docs/merge conflict Resolution.md`
- Task 6 specification: `tasks/6-policy-engine.md`
- Main branch Tasks 1-5: config, data model, audit, job system
