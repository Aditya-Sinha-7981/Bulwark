# Requirements

## Source

Derived from SIH26117's Background/Description/Expected Solution, and from decisions made and locked across Phase 1 and Phase 2. Nothing here is invented beyond those two sources.

## Functional requirements

| ID | Requirement | Architectural home |
|---|---|---|
| F1 | Auto-select the right model for a given task, demonstrable across ≥2 task types | Capability Registry, Model Runtime, Resource/Model Lifecycle Manager |
| F2 | Support adding a new open-weight model without redesigning the system | Resource/Model Configuration Registry |
| F3 | Plan and carry out multi-step work, not single-shot replies | Orchestrator, Job Manager |
| F4 | Call local tools: file read/write, sandboxed code execution, document search, document generation | Capability Executors |
| F5 | Handle scanned PDFs, handwritten notes, photographs via OCR/vision | Document-extraction capability, tiered OCR/vision |
| F6 | Produce real deliverables (approval notes, Word/Excel files, working verified code) | Deterministic Artifact Generator, Sandbox |
| F7 | Ground responses in the organization's own documents via local knowledge base | RAG pipeline |
| F8 | Demonstrate model auto-selection across ≥2 task types, live | Demo workflows A + B |
| F9 | Carry an agentic task end-to-end: scanned report → findings → DOCX | Demo workflow A |
| F10 | Run and verify a coding task in a sandbox | Demo workflow B |
| F11 | Demonstrate multimodal (image/scanned document) understanding | Demo workflow A (extraction tier) |
| F12 | Show, through logs or a visible monitor, that no external network calls occur | Demo workflow D, zero-egress enforcement + monitoring |

## Non-functional requirements

| ID | Requirement |
|---|---|
| N1 | Runs entirely on one machine — no cloud dependency at runtime, for any component |
| N2 | Runs on the reference hardware (M4 Pro, 24GB unified memory) with comfortable memory headroom, not just "technically fits" |
| N3 | Model swaps and multi-step agent execution stay within a demo-acceptable latency envelope |
| N4 | Every significant system action is auditable after the fact, not just visible live |
| N5 | Policy enforcement cannot be bypassed by the Orchestrator under any circumstance |
| N6 | Code execution is isolated, network-denied, resource-limited, and cleaned up after every run |
| N7 | The system operates fully offline after a one-time provisioning step |
| N8 | Model, capability, and configuration choices are swappable without application rewrites |

## Sovereignty / offline requirements

- No code path may make an external HTTP call at runtime — verified at code review, not just at runtime.
- All models, OCR weights, and embedding models are downloaded once during provisioning; the system must demonstrably run with networking disabled afterward.
- Zero-egress enforcement is layered (application, capability, model runtime, sandbox, OS/deployment, monitoring) — never a single mechanism.
- A live, visible proof of zero egress is a first-class demo requirement, not an afterthought — see `security.md` and `demo.md` (Workflow D).

## Supported workflows (SIH scope)

Exactly the four demo workflows in `demo.md` (A: report → DOCX, B: code → sandbox, C: knowledge query, D: zero-egress proof). Anything else the agent can incidentally do is not validated or demo-critical.

## Supported inputs

- Text chat requests
- Scanned document images/PDFs (inspection reports)
- Handwritten note images
- Coding requests (text)

## Supported outputs

- Chat responses (grounded, with retrieval evidence where used)
- DOCX (approval notes / findings documents)
- XLSX (where a capability produces one — not required for MVP demo workflows)
- Executed, verified code + its output
- Live Job trace / Audit view

## Hardware assumptions

Reference/guaranteed: MacBook Pro, M4 Pro, 24GB unified memory, 512GB SSD. Team development machines vary (Windows, 6GB-VRAM-class NVIDIA GPUs, integrated-graphics-only) and are not required to match the reference machine — see `models.md` for how the Resource/Model Lifecycle Manager handles this.

## MVP / SIH scope

Everything in "Functional requirements" above. Nothing beyond it is required to consider the SIH build complete.

## Deferred (explicitly out of scope for SIH)

- Multi-role auth (engineer/reviewer/admin)
- Multi-tenant/production-scale deployment
- Reranking in RAG (add only if retrieval quality disappoints in testing)
- PPTX artifact generation (kept in `artifacts.md` as a supported capability shape, but not exercised by any demo workflow)
- Cross-organization/enterprise air-gapped distribution tooling

## Acceptance criteria

A requirement is "done" when: (1) its capability/API/data contract exists in the relevant `docs/` file, (2) it's implemented per that contract, (3) it has a corresponding test per `testing.md`, (4) if it's part of a demo workflow, it passes the exact success criteria defined for that workflow in `demo.md`.

See `implementation-plan.md` for the traceability map from requirement → architecture → implementation → test → demo outcome.
