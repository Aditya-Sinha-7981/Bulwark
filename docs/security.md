# Security & Sovereignty

## Zero-egress — enforcement vs. proof

These are two different things and must never be conflated. A UI indicator is monitoring, not a control.

### Enforcement (what actually prevents external network access)

| Layer | Mechanism |
|---|---|
| Application | No HTTP client call to a non-localhost address exists anywhere in the codebase — verified at code review, not a runtime setting. |
| Capability | Every capability declares `network_access: false` (`capabilities.md`) — an explicit, checked invariant, not a default that could silently be overridden. |
| Model Runtime | Ollama resolved only to `localhost` — no external model endpoint is ever configured. |
| Sandbox | Docker containers run with `--network none` — kernel-enforced, not application-level (`sandbox.md`). |
| Deployment/OS | The host firewall (macOS Application Firewall / Windows Defender Firewall, per platform) is configured once during provisioning to block outbound connections from the backend process except to loopback. Configured and tested well before demo day — never adjusted live during a demo. |
| Application (backstop) | A socket-wrapper guard rejecting any non-loopback connection attempt from the backend process — the last layer, explicitly not the primary mechanism, never relied on alone. |

### Monitoring / judge-facing proof

A live, continuously-polled connection monitor (backend, `psutil`-based) feeding `network_check` audit events, surfaced in the frontend as a standing "0 external connections" panel (`GET /api/v1/network-status`, `api.md`) — independent of any single Job, running for the whole session. This is what judges see live. It is backed by the enforcement layers above, not a substitute for them.

### Retroactive proof

Every `AuditEvent` for every model/tool invocation across a session is queryable — none of them should show any non-declared network access. This gives a second, independent way to answer "prove it" beyond the live panel.

## Trust boundaries

- **Orchestrator ↔ Policy:** the Orchestrator proposes; it has zero execution authority. This boundary is structural (only one dispatch function exists, and only Policy-approved calls reach it — `agent.md`), not conventional.
- **Policy ↔ Executor:** Policy permits; Executors act only on permitted proposals.
- **Frontend ↔ Backend:** the frontend talks only to the API layer — never to models, Docker, or the filesystem directly (`frontend.md`).
- **Sandbox ↔ Host:** the sandbox is filesystem- and network-isolated from the host except its two explicit mounts (`sandbox.md`).

## Deterministic Policy

Fully rule-based (ADR-02, `decisions.md`) — never model judgment. Rules check: capability is registered and enabled, `network_access` invariant holds, filesystem access stays within the capability's declared scope, resource limits (timeout, output size) are within configured bounds. Every decision — allow or deny — is a `policy_decision` audit event, including the specific rule that produced it.

## Capability permissions

Declared per-capability in `capabilities.md` (`permissions`, `filesystem_scope`) — checked by Policy on every invocation, not assumed from the capability's identity alone.

## Filesystem restrictions

Each capability's Executor only ever touches the specific paths declared in its `filesystem_scope` — enforced by the Executor implementation itself using scoped paths (not raw user/model-supplied paths), and checked as an invariant by Policy before dispatch.

## Sandbox security

See `sandbox.md` in full — network denial, read-only filesystem except one output mount, resource limits, ephemeral per-execution containers, no runtime package installation.

## Model/runtime restrictions

Ollama bound to localhost only. No API keys, no external model endpoints anywhere in configuration. Model weights are downloaded once during provisioning and run entirely locally thereafter — see `deployment.md`.

## File validation

Uploads are checked against an allowlist of MIME types and a max size limit (`configuration.md`) at the API boundary (`api.md`, `POST /api/v1/documents`) before anything downstream ever processes them.

## Prompt-injection considerations

A malicious or adversarial scanned document could contain text designed to look like an instruction to the Orchestrator (e.g., embedded text reading "ignore previous instructions and..."). Mitigations: extracted document content is passed to the Orchestrator as tool-result *data*, not as a system-level instruction — the system prompt (`agent.md`) should explicitly state that content from `extract_document`/`search_knowledge_base` results is untrusted data, not instructions to follow. This is a prompt-engineering control, not a hard technical boundary — flagged here as a known, partially-mitigated risk rather than a solved one, appropriate for SIH scope.

## Malicious-document risks

Uploaded files are never executed and never parsed by anything beyond the intended OCR/vision pipeline (`document-processing.md`) — no code path treats an uploaded document as anything but image/text input to that specific pipeline.

## Generated-code risks

This is what the sandbox exists for (`sandbox.md`) — network-denied, resource-limited, filesystem-isolated, ephemeral execution of anything the coding capability produces, regardless of what that code attempts to do.

## Resource exhaustion

- Sandbox: CPU/memory limits and a hard timeout (`sandbox.md`).
- Model loads: bounded by the Resource/Model Lifecycle Manager's memory-aware eviction (`models.md`) — a runaway sequence of load requests cannot exceed the system's actual memory, since the Lifecycle Manager evicts before over-committing.
- Job step limit (8, default) bounds how long any single Job can run (`agent.md`).

## Secret handling

There are no external API keys or secrets in the SIH runtime — the entire model/tool stack is local (`configuration.md` states this explicitly). If any local credential is ever needed (none currently are), it would go in a `.env` file excluded from version control — documented here as the pattern to follow, not because it's currently in use.

## Dependency policy

All Python/Node dependencies, the Docker sandbox image, and all model weights are provisioned once while online and must demonstrably run afterward with networking disabled — see `deployment.md`'s offline provisioning section. No dependency is fetched at runtime.

## Offline operation

The system must run correctly with networking disabled, as a tested property, not an assumption — validation step defined in `deployment.md` and `testing.md`.

## Failure-safe behavior

Every failure mode documented across `capabilities.md`, `sandbox.md`, `document-processing.md`, and `models.md` returns a structured result to the Orchestrator rather than crashing the Job or silently succeeding with bad data. Nothing in this system fails open with respect to network access — a failure in any enforcement layer results in the operation not happening, not in it happening without the safeguard.
