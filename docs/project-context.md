# Project Context — Aegis (SIH26117)

**Read this file first. Every team member and every AI coding session reads this before touching any code.**

---

## What we're building

A self-hosted, air-gapped, agentic AI workbench for confidential industrial/organizational work — refineries, PSUs, defence-linked manufacturing, government offices. It runs entirely on one machine, uses multiple open-weight models auto-selected by task, calls real local tools (document extraction, code sandbox, knowledge retrieval, document generation), and can prove — live, on a network monitor, not just claim — that nothing ever leaves the machine.

**SIH problem statement:** SIH26117.

**Priority order, always:** (1) reliable SIH demonstration, (2) strong implementation quality, (3) local/offline operation, (4) demonstrable zero external egress, (5) simplicity and debuggability, (6) reasonable extensibility after SIH. In that order — do not sacrifice #1–5 for #6.

## What we are explicitly NOT building right now

- Multi-user auth / role-based access control (single-operator demo)
- A production-scale multi-tenant deployment
- Microservices, Kubernetes, or any cloud infrastructure
- Enterprise-grade air-gapped distribution tooling
- A general-purpose agent framework dependency

If a task seems to require any of the above, stop and flag it — don't build it.

## System summary

The user submits a request (text and/or a file) through the frontend. A **Job** is created. An **Orchestrator** (an LLM) reads the request and either answers directly or proposes a **Capability** by name. A fully deterministic **Policy layer** allows or denies the proposal. If allowed, a **Capability Executor** runs it — possibly invoking a specialist model through the **Model Runtime** boundary, possibly running deterministic code (a renderer, the retrieval index, the sandbox). Every step is recorded as an **Audit Event**; the Job's live trace, shown in the frontend, is a filtered view over that same event stream. Nothing in the system makes an external network call, ever, enforced in layers — not just claimed.

## Major architecture

```text
User → Frontend → API/Job Layer → Orchestrator → Capability Selection
  → Policy Layer (deterministic) → Job Manager → Capability Executor
     ├── Model Runtime → Resource/Model Lifecycle Manager
     ├── RAG
     ├── OCR/Vision
     ├── Sandbox (Docker)
     └── Deterministic Artifact Generation
  → Result → Job/Audit Event → Orchestrator → Final Answer/Artifact

Cross-cutting: Audit/Event System, Zero-Egress Enforcement
```

Full detail: `architecture.md`.

## Major components

| Component | Responsibility |
|---|---|
| Frontend | Chat, uploads, live Job trace, artifacts. Never touches models/tools/Docker directly. |
| API / Job Layer | Turns requests into first-class Jobs. |
| Orchestrator | The only reasoning component. Proposes; never executes. |
| Capability Registry | Declares what the system can do and what resource type each capability needs. |
| Policy Layer | Deterministic allow/deny gate between proposal and execution. Cannot be bypassed. |
| Job Manager | Tracks Job state, dispatches steps to Executors. |
| Capability Executors | Do the actual work: retrieval, extraction, code exec, artifact generation. |
| Model Runtime | Abstraction — capabilities request a resource *type*, never a model name. |
| Resource/Model Lifecycle Manager | Loads/unloads/evicts models under memory constraints. |
| Audit/Event Subsystem | Single source of truth for everything that happened. Job trace is a view over it. |

## Locked technology stack

| Layer | Choice |
|---|---|
| Model runtime | Ollama |
| Reasoning (Orchestrator) | `qwen3.5:9b` — see note below |
| Coding | `qwen2.5-coder:7b` |
| Vision | `qwen3.5:9b` (same model as reasoning) |
| Embedding | `qwen3-embedding:0.6b` |
| OCR | PaddleOCR PP-OCRv6 |
| Vector store | Chroma |
| Agent implementation | Hand-rolled Python loop (no framework) |
| Sandbox | Docker Desktop — identical on macOS and Windows |
| Database | SQLite |
| Backend | FastAPI + Uvicorn |
| Frontend | React + Vite + Tailwind |
| Artifact generation | python-docx, openpyxl |
| Event streaming | Server-Sent Events (SSE) |

**Note on the reasoning model:** `qwen3.5:9b` is the current default and is undergoing benchmark validation against `gpt-oss:20b` (procedure in `testing.md`). This does not block implementation — the Resource/Model Configuration Registry means changing this later is a config edit, not a rewrite.

## Model/resource configuration

Capabilities never reference a model name. They declare a **resource type** (`reasoning`, `code_generation`, `vision`, `embedding`); the Resource/Model Configuration Registry (`config/resources.yaml`, see `configuration.md` and `models.md`) resolves that to the currently configured model. Changing a model is a config change plus `ollama pull` — never an application code change.

## Reference hardware

**Primary/guaranteed SIH showcase machine:** MacBook Pro, Apple M4 Pro, 24GB unified memory, 512GB SSD.

Team development machines (secondary, not the demo target): Windows laptops with varying NVIDIA GPUs (6GB VRAM class) and integrated-graphics-only machines. The application architecture stays hardware-agnostic at the Model Runtime boundary; the reference *deployment* is tuned for the M4 Pro. Hardware parity across team machines is not required or expected.

## Primary SIH demo workflows

| | Flow |
|---|---|
| **A** | Scanned inspection report → extraction → SOP retrieval → structured findings → DOCX |
| **B** | Coding request → generation → Docker sandbox execution → verification |
| **C** | Local knowledge query → explicit retrieval → grounded answer |
| **D** | Live, visible proof of zero external network egress |

Full detail, including expected Orchestrator behavior at each step: `demo.md`.

## Current implementation status

Phase 1 (architecture) — **locked**. Phase 2 (technology/model selection) — **locked**, one benchmark validation pending (reasoning model). Phase 3 (this documentation set) — complete. **Implementation has not started.**

## Important architectural rules — do not change without explicit approval

- The Orchestrator has no execution rights — it proposes, it never executes directly.
- The Policy layer is fully deterministic — never model-based judgment.
- Capabilities declare resource types, never model names.
- OCR is one capability with internal tiered escalation — the Orchestrator never sees separate OCR/vision steps.
- RAG retrieval is always explicit — never automatically run on every turn.
- Artifact generation is deterministic — the model produces structured data; application code renders the file.
- The Job trace is a filtered view over the Audit event stream — never a second, parallel log.
- The Sandbox Capability contract is identical on macOS and Windows — no OS-specific application logic.
- Zero-egress is enforced in layers (app, capability, runtime, sandbox, OS, monitoring) — never by one mechanism alone.

If a task seems to require breaking one of these, **stop and flag it explicitly** rather than silently deviating.

## AI Coding Agent Operating Procedure

This procedure is generic and can be customized later. Follow it for every task:

1. Read `project-context.md` (this file).
2. Inspect the repository before modifying anything.
3. Read the relevant detailed documentation for the task (see the file map in `README.md`).
4. Identify dependencies and existing implementation.
5. Do not silently change architectural decisions — flag and ask instead.
6. Implement the smallest coherent change.
7. Run relevant tests/checks.
8. Inspect the diff.
9. Update documentation if the implementation changes a documented contract.
10. Commit the work using the project's Git workflow (`git-workflow.md`).
11. Push the branch.
12. Report what changed, what was tested, and any remaining issues.

## How to verify your work

- Does it match the contract in the relevant `docs/` file (API shape, capability schema, event type, data model field)? If you had to guess a name or shape, stop — check `decisions.md` and the relevant contract file before inventing one.
- Does it preserve every rule in "Important architectural rules" above?
- Did you add or update an Audit event for anything meaningfully new that happens?
- Did you run the relevant test category from `testing.md`?

## Git workflow summary

Update main → create a branch (`feature/<desc>` or `fix/<desc>`) → implement → test → review diff → commit → push → PR. Never commit directly to main. Full detail: `git-workflow.md`.
