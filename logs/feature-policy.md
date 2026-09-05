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