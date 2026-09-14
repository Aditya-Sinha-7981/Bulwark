"""
Job Manager — the full request lifecycle (Task 15).

Realises `docs/architecture.md` "Request lifecycle" steps 1–8 for real: the
stub Orchestrator from Task 5 is gone; every turn now calls the real
Orchestrator loop (Task 10), every capability proposal is evaluated by the
deterministic Policy engine (Task 6) before anything runs, and allowed
proposals are dispatched to their executors (Tasks 11–14) through the single
function `_dispatch_capability`.

────────────────────────────────────────────────────────────────────────────
THE NON-BYPASS GUARANTEE (AGENTS.md §6 rule 1, docs/agent.md "Policy
interaction", Task 15 Requirement 2):

  `_dispatch_capability` is the ONLY function in the codebase that invokes a
  capability executor, and `run_job` (below) is its ONLY caller. There is no
  code path from an Orchestrator proposal to an executor that does not pass
  through `evaluate(...)` and an `allow` decision first. A future change that
  adds another executor call site breaks this guarantee — the structural
  guard test in `backend/tests/test_structural_guard.py` exists to catch it.
────────────────────────────────────────────────────────────────────────────

Dependency-injection seam: `run_job` resolves its Orchestrator model client,
Capability Registry, and Policy config lazily via `_deps`. Production uses the
real Ollama runtime + `settings`; tests call `set_test_dependencies(...)` with
a `FakeModelClient` and (optionally) a registry / config that has a capability
disabled, to exercise the deny path without a live model.
"""

from __future__ import annotations

import inspect
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.config import settings
from backend.domain.audit.events import emit
from backend.domain.capabilities.registry import CapabilityRegistry
from backend.domain.orchestrator import agent
from backend.domain.policy.engine import evaluate as policy_evaluate
from backend.models.schemas import OrchestratorContext, ToolResult
from backend.repositories import conversations as conversations_repo
from backend.repositories import jobs as jobs_repo


# --------------------------------------------------------------------------- #
# Dependency-injection seam
# --------------------------------------------------------------------------- #

_deps: Dict[str, Any] = {
    "model_client": None,      # ModelClient — None → real Ollama runtime
    "registry": None,          # CapabilityRegistry — None → built from settings
    "capabilities_config": None,  # dict for Policy — None → built from settings
    "policy_config": None,     # dict for Policy — None → built from settings
}


def set_test_dependencies(
    *,
    model_client: Any = None,
    registry: Optional[CapabilityRegistry] = None,
    capabilities_config: Optional[dict] = None,
    policy_config: Optional[dict] = None,
) -> None:
    """Inject fakes for tests. Any argument left None keeps the production default."""
    if model_client is not None:
        _deps["model_client"] = model_client
    if registry is not None:
        _deps["registry"] = registry
    if capabilities_config is not None:
        _deps["capabilities_config"] = capabilities_config
    if policy_config is not None:
        _deps["policy_config"] = policy_config


def reset_test_dependencies() -> None:
    for key in _deps:
        _deps[key] = None


def _get_model_client() -> Any:
    if _deps["model_client"] is None:
        from backend.domain.model_runtime.runtime import runtime

        _deps["model_client"] = runtime
    return _deps["model_client"]


class _JobBoundModelClient:
    """Binds `job_id` onto every model call so the Model Runtime's
    `model_invoked` / `error` audit events correlate to this Job.

    `agent.step` calls `model_client.generate(resource_type, prompt)` with no
    `job_id` (the `ModelClient` protocol does not carry one), but the real
    Ollama runtime emits audit events that *require* a `job_id`. This adapter
    closes that seam in the Job Manager without changing the Orchestrator or
    the protocol. Fakes that don't accept `job_id` are called without it.
    """

    def __init__(self, inner: Any, job_id: str) -> None:
        self._inner = inner
        self._job_id = job_id
        try:
            self._accepts_job_id = "job_id" in inspect.signature(inner.generate).parameters
        except (TypeError, ValueError):
            self._accepts_job_id = False

    async def generate(
        self,
        resource_type: str,
        prompt: str,
        *,
        images: Any = None,
        options: Any = None,
    ) -> Any:
        if self._accepts_job_id:
            # Real runtime only (test fakes don't accept job_id, per the
            # signature check above) — route through the Resource/Model
            # Lifecycle Manager first so resource_loaded/resource_unloaded
            # actually fire. Previously this called self._inner.generate()
            # (Model Runtime) directly, so the Lifecycle Manager was never
            # invoked on the real request path and those two event types
            # never appeared in any Job's trace (Task 17 integration finding,
            # logs/feature-integration.md — confirmed via 0 such events ever
            # existing in audit_events despite real model swaps happening).
            from backend.domain.model_runtime.lifecycle_manager import acquire

            await acquire(resource_type, job_id=self._job_id)
            return await self._inner.generate(
                resource_type, prompt, images=images, options=options, job_id=self._job_id
            )
        return await self._inner.generate(
            resource_type, prompt, images=images, options=options
        )


def _get_registry() -> CapabilityRegistry:
    if _deps["registry"] is None:
        from backend.domain.capabilities.registry import get_registry

        _deps["registry"] = get_registry(settings.capabilities)
    return _deps["registry"]


def _capabilities_config_for_policy() -> dict:
    """`{"capabilities": {name: {enabled, timeout_seconds, ...limits}}}` — the
    shape `policy.engine.evaluate` reads."""
    if _deps["capabilities_config"] is not None:
        return _deps["capabilities_config"]
    caps = settings.capabilities
    return {
        "capabilities": {
            "extract_document": caps.extract_document.model_dump(),
            "search_knowledge_base": caps.search_knowledge_base.model_dump(),
            "generate_code": caps.generate_code.model_dump(),
            "execute_code": caps.execute_code.model_dump(),
            "create_docx": caps.create_docx.model_dump(),
            "create_xlsx": caps.create_xlsx.model_dump(),
        }
    }


def _policy_config_for_policy() -> dict:
    """`{"policy": {network_access_allowed, max_job_steps, ...}}`."""
    if _deps["policy_config"] is not None:
        return _deps["policy_config"]
    return {"policy": settings.policy.model_dump()}


def _registry_entry_dict(registry: CapabilityRegistry, capability_name: str) -> Optional[dict]:
    """The registry-entry dict Policy needs (`network_access`, `permissions`,
    `filesystem_scope`, ...). None if the capability is unknown."""
    from backend.domain.capabilities.registry import UnknownCapabilityError

    try:
        entry = registry.get(capability_name)
    except UnknownCapabilityError:
        return None
    return {
        "name": entry.name,
        "resource_type": entry.resource_type,
        "permissions": list(entry.permissions),
        "network_access": entry.network_access,
        "filesystem_scope": list(entry.filesystem_scope),
        "timeout_seconds": entry.timeout_seconds,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str)


def _canonical_arguments(arguments: Dict[str, Any]) -> str:
    """Canonical JSON of capability arguments, for identical-proposal comparison."""
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)


# --------------------------------------------------------------------------- #
# Job creation
# --------------------------------------------------------------------------- #

async def create_job(conversation_id: str, input_message: str, document_ids: List[str]) -> str:
    """
    Create a Job (`status: created`), append the triggering user message to the
    conversation, and emit `job_created`.

    `document_ids` reference documents already uploaded via `POST /documents`.
    The Orchestrator learns them through the conversation history: when
    non-empty, the stored user message carries an attachment note listing each
    `document_id`, so the Orchestrator can propose `extract_document` with it
    (docs/demo.md Workflow A). The Job row and the `job_created` event keep
    the raw `input_message`.
    """
    job_id = jobs_repo.create_job(
        conversation_id=conversation_id,
        input_message=input_message,
        status="created",
    )

    # The user's request enters the Orchestrator's context as conversation
    # history (docs/agent.md "Conversation state") — record it as a message row.
    # Attachment references ride along on the message: the Orchestrator has no
    # other channel to learn the document_ids it must put into
    # extract_document's arguments (docs/demo.md Workflow A step 1).
    if document_ids:
        attachment_note = "[Attached document(s): " + ", ".join(
            f"document_id={d}" for d in document_ids
        ) + "]"
        message_content = f"{input_message}\n\n{attachment_note}"
    else:
        message_content = input_message

    conversations_repo.append_message(
        conversation_id=conversation_id,
        role="user",
        content=message_content,
    )

    await emit(
        event_type="job_created",
        component="api",
        payload={
            "conversation_id": conversation_id,
            "input_message": input_message,
        },
        job_id=job_id,
    )

    return job_id


def ensure_conversation_exists(conversation_id: str) -> bool:
    return conversations_repo.get_conversation(conversation_id) is not None


# --------------------------------------------------------------------------- #
# The single post-Policy dispatch seam — see module docstring
# --------------------------------------------------------------------------- #

async def _dispatch_capability(
    capability_name: str,
    job_id: str,
    arguments: dict,
    capability_execution_id: str,
    registry: CapabilityRegistry,
) -> dict:
    """
    Invoke one capability executor. THE ONLY place any executor is called.

    Called by `run_job` only after `evaluate(...)` returned `allow`. Returns
    the executor's raw result as a plain dict. Raises whatever the executor
    raises (validation or render errors, a still-unimplemented capability,
    etc.) — `run_job` converts the failure into a `status: "failed"`
    tool-result so the Job never crashes.

    NOTE (coordination — Task 11): `create_docx` / `create_xlsx` (Task 14),
    `generate_code` / `execute_code` (Task 13), and `search_knowledge_base`
    (Task 12.b) have all converged on `async def execute_x(job_id, arguments)
    -> dict` — arguments is the raw, unvalidated dict from the Orchestrator's
    proposal; each executor validates its own input/output against
    `docs/capabilities.md` internally. `extract_document` (Task 11) has not
    fully converged yet and still takes a single pre-validated pydantic model
    (so this adapter validates on its behalf until it does), but it does now
    take `job_id` as a keyword arg (Task 19 finding: vision escalation's
    `model_invoked` event was being emitted with job_id=None, invisible in
    the job's trace, because job_id previously never reached
    `execute_extract_document` at all).
    `capability_execution_id` is threaded here for `model_executions`
    correlation once these executors make real model calls.
    """
    if capability_name == "create_docx":
        from backend.domain.capabilities.create_docx import execute_create_docx

        return await execute_create_docx(job_id, arguments)

    if capability_name == "create_xlsx":
        from backend.domain.capabilities.create_xlsx import execute_create_xlsx

        return await execute_create_xlsx(job_id, arguments)

    if capability_name == "extract_document":
        from backend.domain.capabilities.extract_document import execute_extract_document

        model = registry.validate_input(capability_name, arguments)
        return _as_dict(await execute_extract_document(model, job_id=job_id))

    if capability_name == "search_knowledge_base":
        from backend.domain.capabilities.search_knowledge_base import (
            execute_search_knowledge_base,
        )

        return await execute_search_knowledge_base(job_id, arguments)

    if capability_name == "generate_code":
        from backend.domain.capabilities.generate_code import execute_generate_code

        return await execute_generate_code(job_id, arguments)

    if capability_name == "execute_code":
        from backend.domain.capabilities.execute_code import execute_execute_code

        return await execute_execute_code(job_id, arguments)

    raise ValueError(f"no dispatch entry for capability {capability_name!r}")


def _as_dict(result: Any) -> dict:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    if isinstance(result, dict):
        return result
    raise TypeError(f"executor returned non-dict result: {type(result)!r}")


async def _convert_execute_code_output_files(result: dict, job_id: str) -> dict:
    """
    Task 15 Requirement 6: turn `execute_code`'s raw `output_files` filename
    candidates into real `Artifact` rows *before* schema-validating the result.

    Only `.docx` / `.xlsx` map to a documented `Artifact.type`; any other
    extension is left un-persisted and an `error` event is emitted noting the
    file was produced but not captured (see `sandbox_output` module docstring).

    NOTE (coordination — Task 13): resolving each candidate filename to an
    absolute path needs the sandbox execution directory. `ExecuteCodeOutput`
    does not currently carry an `execution_id`; Task 13's executor must return
    enough to locate its output files (an `execution_id`, or absolute paths).
    Until then this runs only when `output_files` is non-empty — which the
    current stub never produces — so it is inert, not wrong.
    """
    candidates = result.get("output_files") or []
    if not candidates:
        return result

    from pathlib import Path

    from backend.domain.artifacts.sandbox_output import (
        SandboxOutputPersistError,
        persist_sandbox_output_as_artifact,
        supported_extension,
    )
    from backend.utils.paths import SANDBOX_ROOT

    converted: List[str] = []
    for name in candidates:
        if not supported_extension(name):
            await emit(
                "error",
                "job_manager",
                {
                    "component": "job_manager",
                    "message": (
                        f"execute_code produced output file '{name}' with no documented "
                        "Artifact.type; not persisted (Task 15 Requirement 6)"
                    ),
                    "context": {"capability": "execute_code", "filename": name},
                },
                job_id=job_id,
            )
            continue
        # Best-effort resolution under the sandbox root (see NOTE above).
        source = (SANDBOX_ROOT / name) if not Path(name).is_absolute() else Path(name)
        try:
            artifact_id = await persist_sandbox_output_as_artifact(source, job_id)
        except SandboxOutputPersistError as exc:
            await emit(
                "error",
                "job_manager",
                {
                    "component": "job_manager",
                    "message": f"failed to persist execute_code output '{name}': {exc}",
                    "context": {"capability": "execute_code", "filename": name},
                },
                job_id=job_id,
            )
            continue
        if artifact_id is not None:
            converted.append(artifact_id)

    result["output_files"] = converted
    return result


# --------------------------------------------------------------------------- #
# Driver loop
# --------------------------------------------------------------------------- #

async def run_job(job_id: str) -> None:
    """
    Drive a Job to a terminal state.

    created → running → (completed | failed). Each iteration is one Orchestrator
    turn: reason → (respond ⇒ finish) | (invoke ⇒ Policy → dispatch → tool
    result) | (malformed ⇒ one free corrective turn, then it counts). Ends on
    `respond`, the step limit, or an unrecoverable error. Emits `job_completed`
    exactly once, from `finally`.
    """
    start = time.monotonic()

    if not jobs_repo.update_job(job_id, status="running"):
        return

    job = jobs_repo.get_job(job_id)
    if not job:
        return
    conversation_id = job["conversation_id"]

    registry = _get_registry()
    model_client = _JobBoundModelClient(_get_model_client(), job_id)
    max_steps = _policy_config_for_policy()["policy"]["max_job_steps"]

    step_count = 0            # counts against the limit (agent.md "step limits")
    malformed_retry_used = False
    tool_results: List[ToolResult] = []
    malformed_error: Optional[str] = None
    sequence = 0
    # Canonical "capability:arguments" of the previous capability invocation
    # (identical-proposal guard — docs/agent.md convergence requirement).
    last_invocation_key: Optional[str] = None

    try:
        while True:
            context = OrchestratorContext(
                job_id=job_id,
                conversation_id=conversation_id,
                system_prompt="",  # agent._assemble_prompt builds it from the registry
                conversation_history=[
                    {"role": m["role"], "content": m["content"]}
                    for m in conversations_repo.list_messages(conversation_id)
                ],
                tool_results=tool_results,
                malformed_error=malformed_error,
            )

            # Orchestrator turn — emits `orchestrator_step` itself (Task 10).
            result = await agent.step(context, model_client, registry, max_steps)
            outcome = agent.classify_step(result, malformed_retry_used)

            sequence += 1

            # ---- malformed proposal ------------------------------------------------
            if result.kind == "malformed":
                step_id = jobs_repo.add_job_step(
                    job_id=job_id,
                    sequence=sequence,
                    kind="orchestrator_reasoning",
                    input_payload=_compact({"malformed_error_in": malformed_error}),
                    status="failed",
                )
                jobs_repo.update_job_step(
                    job_step_id=step_id,
                    status="failed",
                    error_message=result.error or "malformed orchestrator output",
                    completed_at=_now_iso(),
                )
                malformed_error = result.error
                if outcome.counts_against_limit:
                    step_count += 1
                else:
                    malformed_retry_used = True

                if step_count >= max_steps:
                    _fail_step_limit(job_id, max_steps)
                    break
                continue

            # ---- valid proposal --------------------------------------------------
            malformed_error = None
            proposal = result.proposal

            if proposal.action == "respond":
                step_id = jobs_repo.add_job_step(
                    job_id=job_id,
                    sequence=sequence,
                    kind="orchestrator_reasoning",
                    input_payload=_compact({"action": "respond"}),
                    status="succeeded",
                )
                jobs_repo.update_job_step(
                    job_step_id=step_id,
                    status="succeeded",
                    output_payload=_compact({"content": proposal.content}),
                    completed_at=_now_iso(),
                )
                jobs_repo.update_job(
                    job_id=job_id,
                    status="completed",
                    final_message=proposal.content,
                    completed_at=_now_iso(),
                )
                conversations_repo.append_message(
                    conversation_id=conversation_id,
                    role="orchestrator",
                    content=proposal.content,
                    job_id=job_id,
                )
                break

            # proposal.action == "invoke_capability"
            capability = proposal.capability
            arguments = proposal.arguments

            # ---- identical-proposal guard (docs/agent.md convergence) -----------
            # Re-invoking the same capability with identical arguments as the
            # immediately previous invocation cannot produce new information
            # (executors are deterministic given their inputs). Reject before
            # Policy and give one corrective turn — same mechanics as the
            # malformed-output rule: the first rejection is free, later ones
            # count against the step limit. Retries with *different* arguments
            # or interleaved different capabilities are never affected.
            invocation_key = f"{capability}:{_canonical_arguments(arguments)}"
            if last_invocation_key is not None and invocation_key == last_invocation_key:
                rejection = (
                    f"identical capability invocation rejected: '{capability}' with "
                    "identical arguments was already the previous invocation; propose "
                    "different arguments or respond with an answer"
                )
                step_id = jobs_repo.add_job_step(
                    job_id=job_id,
                    sequence=sequence,
                    kind="orchestrator_reasoning",
                    input_payload=_compact({
                        "action": "invoke_capability",
                        "capability": capability,
                        "rejected": "identical_proposal",
                    }),
                    status="failed",
                )
                jobs_repo.update_job_step(
                    job_step_id=step_id,
                    status="failed",
                    error_message=rejection,
                    completed_at=_now_iso(),
                )
                malformed_error = rejection
                if malformed_retry_used:
                    step_count += 1
                else:
                    malformed_retry_used = True

                if step_count >= max_steps:
                    _fail_step_limit(job_id, max_steps)
                    break
                continue

            # Record the reasoning turn that produced this proposal.
            jobs_repo.add_job_step(
                job_id=job_id,
                sequence=sequence,
                kind="orchestrator_reasoning",
                input_payload=_compact({"action": "invoke_capability", "capability": capability}),
                status="succeeded",
            )

            sequence += 1
            cap_step_id = jobs_repo.add_job_step(
                job_id=job_id,
                sequence=sequence,
                kind="capability_invocation",
                capability_name=capability,
                input_payload=_compact(arguments),
                status="running",
            )

            # ---- Policy (deterministic, honoured verbatim) ----------------------
            entry_dict = _registry_entry_dict(registry, capability)
            decision = policy_evaluate(
                capability,
                arguments,
                entry_dict,
                _capabilities_config_for_policy(),
                _policy_config_for_policy(),
            )
            decided = decision["policy_decision"]
            reason = decision["policy_reason"] or decided

            await emit(
                event_type="policy_decision",
                component="policy",
                payload={"capability": capability, "decision": decided, "reason": reason},
                job_id=job_id,
            )

            # Allow, deny, or executor outcome — the invocation now counts as
            # "the previous invocation" for the identical-proposal guard.
            last_invocation_key = invocation_key

            cap_exec_id = jobs_repo.add_capability_execution(
                job_step_id=cap_step_id,
                capability_name=capability,
                policy_decision=decided,
                resource_type=(entry_dict or {}).get("resource_type"),
                policy_reason=reason if decided == "deny" else None,
            )

            # Every capability invocation counts — allow, deny, or failure
            # (agent.md: denials count too, to stop a denial-retry loop).
            step_count += 1

            if decided == "deny":
                jobs_repo.update_job_step(
                    job_step_id=cap_step_id,
                    status="denied",
                    error_message=reason,
                    completed_at=_now_iso(),
                )
                tool_results.append(
                    ToolResult(
                        role="tool_result",
                        capability=capability,
                        result={"reason": reason},
                        status="denied",
                    )
                )
                if step_count >= max_steps:
                    _fail_step_limit(job_id, max_steps)
                    break
                continue

            # ---- allow → dispatch ---------------------------------------------
            await emit(
                event_type="tool_invoked",
                component="job_manager",
                payload={"capability": capability, "arguments": arguments},
                job_id=job_id,
            )

            exec_start = time.monotonic()
            try:
                raw = await _dispatch_capability(
                    capability, job_id, arguments, cap_exec_id, registry
                )
                if capability == "execute_code":
                    raw = await _convert_execute_code_output_files(raw, job_id)
                registry.validate_output(capability, raw)

                duration_ms = int((time.monotonic() - exec_start) * 1000)
                jobs_repo.update_capability_execution(cap_exec_id, duration_ms=duration_ms)
                jobs_repo.update_job_step(
                    job_step_id=cap_step_id,
                    status="succeeded",
                    output_payload=_compact(raw),
                    completed_at=_now_iso(),
                )
                # Mirrors tool_invoked so the trace carries the capability's
                # actual output (docs/audit.md), not just that it was called —
                # otherwise nothing renders RAG evidence, sandbox output, etc.
                # in the UI (Task 17 integration finding, logs/feature-integration.md).
                await emit(
                    event_type="tool_result",
                    component="job_manager",
                    payload={"capability": capability, "result": raw},
                    job_id=job_id,
                )
                tool_results.append(
                    ToolResult(
                        role="tool_result",
                        capability=capability,
                        result=raw,
                        status="succeeded",
                    )
                )
            except Exception as exc:  # executor error is a tool result, never a crash
                duration_ms = int((time.monotonic() - exec_start) * 1000)
                jobs_repo.update_capability_execution(cap_exec_id, duration_ms=duration_ms)
                message = f"{type(exc).__name__}: {exc}"
                jobs_repo.update_job_step(
                    job_step_id=cap_step_id,
                    status="failed",
                    error_message=message,
                    completed_at=_now_iso(),
                )
                await emit(
                    event_type="error",
                    component="job_manager",
                    payload={
                        "component": "job_manager",
                        "message": message,
                        "context": {"capability": capability},
                    },
                    job_id=job_id,
                )
                tool_results.append(
                    ToolResult(
                        role="tool_result",
                        capability=capability,
                        result={"error": message},
                        status="failed",
                    )
                )

            if step_count >= max_steps:
                _fail_step_limit(job_id, max_steps)
                break
            # loop

    except Exception as exc:  # truly unrecoverable — the loop itself broke
        jobs_repo.update_job(
            job_id=job_id,
            status="failed",
            error_code="unrecoverable_error",
            error_message=f"{type(exc).__name__}: {exc}",
            completed_at=_now_iso(),
        )
        try:
            await emit(
                event_type="error",
                component="job_manager",
                payload={
                    "component": "job_manager",
                    "message": f"{type(exc).__name__}: {exc}",
                    "context": {"phase": "driver_loop"},
                },
                job_id=job_id,
            )
        except Exception:
            pass

    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        final_job = jobs_repo.get_job(job_id)
        final_status = final_job["status"] if final_job else "failed"
        await emit(
            event_type="job_completed",
            component="job_manager",
            payload={"status": final_status, "duration_ms": duration_ms},
            job_id=job_id,
        )


def _fail_step_limit(job_id: str, max_steps: int) -> None:
    jobs_repo.update_job(
        job_id=job_id,
        status="failed",
        error_code="step_limit_exceeded",
        error_message=f"Step limit ({max_steps}) reached without a final answer",
        completed_at=_now_iso(),
    )
