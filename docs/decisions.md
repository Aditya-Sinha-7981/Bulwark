# Architecture & Technology Decision Records

Each entry: decision, rationale, alternatives considered, tradeoffs, status. This file exists so the team doesn't relitigate settled decisions — if you're about to reopen one of these, read the rationale first.

---

### ADR-01: Capability-driven, not classifier-driven, model selection

**Decision:** Capabilities declare a required resource type; the Orchestrator selects a capability by purpose, and the Model Runtime resolves the resource type to a model. There is no separate text-classification step to pick a model.

**Rationale:** Deterministic and demo-safe — a misclassification in front of judges looks like the system is broken, even when it isn't. Tool-based routing is unambiguous: a given capability always uses its declared resource type.

**Alternatives considered:** A small classifier model reading the request first; the Orchestrator freely choosing a model name.

**Tradeoffs:** Slightly less "adaptive" than a learned router — acceptable, since capabilities are well-defined and don't need adaptive routing.

**Status:** Locked (Phase 1).

---

### ADR-02: Deterministic Policy layer

**Decision:** The Policy layer between capability proposal and execution is a fixed, auditable ruleset — never model-based judgment.

**Rationale:** Auditability and explainability under judge questioning matter more than adaptive nuance for a hackathon-scale demo, and a rule-based gate cannot be argued with or "reasoned around" the way a model-based one could.

**Alternatives considered:** A model evaluating each proposal for safety/permission.

**Tradeoffs:** Less flexible for edge cases not anticipated by the ruleset — acceptable at SIH scope; extendable later.

**Status:** Locked (Phase 1).

---

### ADR-03: Explicit RAG, not implicit

**Decision:** Retrieval is a capability the Orchestrator must explicitly propose — never automatically run on every turn.

**Rationale:** Keeps retrieval visible as a distinct, auditable Job step (useful for both debugging and the live demo trace), and avoids retrieval noise on requests that don't need grounding.

**Alternatives considered:** Always-on implicit retrieval prepended to every turn.

**Tradeoffs:** Requires the Orchestrator to correctly judge when grounding is needed — validated in the benchmark suite (`testing.md`).

**Status:** Locked (Phase 1).

---

### ADR-04: Tiered OCR as one capability

**Decision:** Document extraction is a single capability (`extract_document`) with internal escalation logic (OCR → multi-signal quality check → vision-model escalation), not separate Orchestrator-visible steps.

**Rationale:** The escalation logic is deterministic and doesn't need agent judgment; exposing it as one capability keeps the Orchestrator's proposal surface simple and reliable.

**Alternatives considered:** Two capabilities (`extract_basic`, `escalate_to_vision`) chained by the Orchestrator itself.

**Tradeoffs:** Slightly less granular demo-trace detail inside extraction — acceptable; the internal tiering is still recorded via audit events, just not as separate Orchestrator decisions.

**Status:** Locked (Phase 1).

---

### ADR-05: Docker sandbox, identical on macOS and Windows

**Decision:** Docker Desktop, same implementation and Sandbox Capability contract, on every team machine.

**Rationale:** The team spans macOS (reference/demo machine) and Windows (development machines). Apple's `container` tool offers stronger per-execution isolation and lower idle memory on macOS specifically, but it's macOS-only — using it would mean two different sandbox implementations to build, test, and keep behaviorally identical. Team consistency and reduced demo risk outweigh the marginal isolation/memory benefit of an OS-specific implementation, per explicit project priority (SIH reliability and simplicity over theoretical strength).

**Alternatives considered:** Apple `container` on macOS + Docker Desktop on Windows (hybrid); Apple `container` everywhere (impossible — Windows has no equivalent).

**Tradeoffs:** Slightly weaker isolation boundary than a per-execution micro-VM, and Docker Desktop's idle background VM costs real memory on the 24GB reference machine (~1–2GB) that a macOS-only alternative wouldn't. Accepted, because the sandboxed code is a scoped SIH demo task, not arbitrary untrusted input.

**Status:** Locked (Phase 2).

---

### ADR-06: SQLite

**Decision:** SQLite for all persistent application data.

**Rationale:** Zero-ops, embedded, matches the single-workstation deployment target. No real multi-user concurrency need at SIH scale.

**Alternatives considered:** Postgres.

**Tradeoffs:** Not suitable for a future multi-tenant production deployment — explicitly deferred, not a concern now.

**Status:** Locked (Phase 2).

---

### ADR-07: Ollama as model runtime

**Decision:** Ollama (0.32.x line), using its native MLX backend on Apple Silicon.

**Rationale:** Ollama's MLX backend on Apple Silicon closed the historical performance gap with raw MLX-LM, while keeping Ollama's simple pull/swap/API model and its ability to run identically on the team's NVIDIA Windows machines via its CUDA backend — one integration surface for the whole team.

**Alternatives considered:** Raw MLX-LM (Mac-only, no cross-team story), llama.cpp directly (more manual setup), vLLM (CUDA-only, irrelevant to the reference hardware).

**Tradeoffs:** Slightly less low-level tuning control than calling MLX-LM directly.

**Status:** Locked (Phase 2).

---

### ADR-08: Resource/Model Configuration Registry

**Decision:** A single config file (`config/resources.yaml`) maps resource types (`reasoning`, `code_generation`, `vision`, `embedding`) to concrete model + runtime + context-window configuration. Capabilities and application code reference resource types only, never model names.

**Rationale:** Directly required by the problem statement ("new open weight models should be addable later without redesigning the system"). Changing a model is a config edit plus a model pull, not an application rewrite.

**Alternatives considered:** Hardcoding model names in capability/executor code.

**Tradeoffs:** None significant — this is a small amount of indirection for a large amount of flexibility.

**Status:** Locked (Phase 2).

---

### ADR-09: Resource/Model Lifecycle Manager

**Decision:** A dedicated component behind the Model Runtime boundary owns loading, keep-alive, unloading, and eviction of whatever backs each resource type, given the M4 Pro's constrained unified memory.

**Rationale:** 24GB unified memory cannot comfortably hold every model resident simultaneously. This component makes memory-driven model swaps a visible, audited event rather than an invisible cause of latency, and keeps that complexity out of the Orchestrator and Executors entirely.

**Alternatives considered:** No lifecycle management — assume all needed models fit; letting each Executor manage its own model loading independently.

**Tradeoffs:** Adds one more component to build — necessary given the hardware constraint.

**Status:** Locked (Phase 1, concretized Phase 2).

---

### ADR-10: Deterministic artifact generation

**Decision:** Models produce structured data only; application code (python-docx, openpyxl) deterministically renders the final file. The model never controls document formatting directly.

**Rationale:** Reliability — a model cannot produce a malformed/broken document live on stage if it never touches formatting at all.

**Alternatives considered:** Having the model generate document markup/formatting directly.

**Tradeoffs:** Less flexible output formatting than a model-driven approach — acceptable; SIH deliverables use fixed templates.

**Status:** Locked (Phase 1).

---

### ADR-11: Audit as single source of truth; Job trace as a filtered view

**Decision:** One Audit/Event table records everything. The Job's live trace (shown in the frontend) is a query over that same table filtered by `job_id` — not a separately maintained log.

**Rationale:** Avoids drift between what the live UI shows and what the audit record says happened after the fact — both the live demo proof and the retroactive compliance story come from one source.

**Alternatives considered:** Separate Job-trace logging and Audit logging systems.

**Tradeoffs:** None significant.

**Status:** Locked (Phase 1).

---

### ADR-12: Zero-egress defense in depth

**Decision:** Enforcement is layered — application code contains no external-call paths, capabilities default `network_access: false`, the Model Runtime resolves only to local resources, the sandbox runs `--network none`, the OS firewall scopes the backend process to loopback, and an application-level socket guard is a last-resort backstop, never the primary mechanism. Proof for judges is a live connection monitor, backed by real enforcement underneath it, plus the queryable Audit log as a retroactive check.

**Rationale:** A single mechanism (e.g., a Python socket monkey-patch alone) is not a defensible security claim on its own. Layering means no single failure breaks the sovereignty guarantee, and gives two independent ways (live + retroactive) to prove it under questioning.

**Alternatives considered:** Relying solely on sandbox network denial; relying solely on an application-level guard; live-configuring OS firewall rules during the demo itself (rejected — real risk of breaking the presentation's own network access if misconfigured live).

**Tradeoffs:** More setup work up front (OS firewall configuration must be done and tested well before demo day).

**Status:** Locked (Phase 2).

---

### ADR-13: Cross-platform application architecture

**Decision:** The application (Orchestrator, Policy, Job Manager, Executors, API) is written with zero OS-specific branches. Platform differences are isolated entirely to what Ollama and Docker already abstract away.

**Rationale:** Required by team composition (mixed macOS/Windows); also keeps the reference deployment on the M4 Pro fully representative of what runs on development machines.

**Alternatives considered:** Platform-specific code paths for performance tuning.

**Tradeoffs:** None significant at this scope.

**Status:** Locked (Phase 1/2).
