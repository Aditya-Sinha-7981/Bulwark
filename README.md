# Bulwark

**A sovereign, on-premise, agentic multimodal AI workbench for confidential industrial and organizational work.**

> Bulwark is built for environments where the data cannot leave the room — refineries, PSUs, defence-linked manufacturing, government offices. It runs entirely on one machine, calls real local tools (document extraction, sandboxed code execution, knowledge retrieval, document generation), auto-selects the right open-weight model per task, and proves — live, on a network monitor — that nothing ever leaves the machine.
>
> **SIH 2026, Problem Statement SIH26117.**

---

## What it does

A user submits a request — text, a scanned PDF, a handwritten note, a coding task — through a single-page React workbench. The system:

1. **Plans and reasons** — an Orchestrator (a local LLM) reads the request and decides what to do.
2. **Proposes capabilities, never executes directly** — the Orchestrator emits a structured proposal (`invoke_capability <name> <args>` or `respond <content>`).
3. **Passes through a deterministic Policy gate** — every proposal is allow/denied by rule, with the rule logged.
4. **Dispatches to Capability Executors** — OCR/vision, RAG, Docker sandbox, deterministic artifact rendering, or model-backed generation via the Model Runtime.
5. **Records everything in one Audit stream** — the live trace the user sees and the retroactive audit log a judge can query are the same data.
6. **Returns a final answer or artifact** — DOCX approval notes, executed-and-verified code, grounded chat responses, all visible in the same UI.

---

## Architecture

```
User → Frontend → API/Job Layer → Orchestrator (LLM)
                                       │ proposes
                                       ▼
                              Policy Layer (deterministic)
                                       │ allow
                                       ▼
                                Job Manager
                                       │ dispatch
                                       ▼
                          Capability Executor
                ┌──────────┬──────────┬──────────┬──────────┐
                ▼          ▼          ▼          ▼          ▼
          Model Runtime  RAG    OCR/Vision  Sandbox    Artifacts
            (Ollama)                          (Docker)    (docx/xlsx)
                │
                ▼
        Resource/Model Lifecycle Manager  →  load / keep-alive / evict

Cross-cutting: Audit/Event subsystem (single source of truth)
               Zero-egress enforcement (six layers)
```

The Orchestrator **proposes; it never executes**. The only path from "model output" to "thing happens in the world" goes through Policy → Job Manager → Executor, and that path is structural, not conventional.

Full architecture: `docs/architecture.md`. ADRs (why each piece is built this way): `docs/decisions.md`.

---

## Tech stack (locked)

| Layer | Choice |
|---|---|
| Model runtime | Ollama (0.32.x+, MLX on Apple Silicon, CUDA on Windows NVIDIA) |
| Reasoning (Orchestrator) | `qwen3.5:9b` — pending benchmark vs. `gpt-oss:20b` (`docs/testing.md`); the Registry makes swap a config edit |
| Coding | `qwen2.5-coder:7b` |
| Vision (escalation) | `qwen3.5:9b` (shared with reasoning) |
| Embedding | `qwen3-embedding:0.6b` (always resident) |
| OCR | PaddleOCR PP-OCRv6 (CPU) with internal escalation to vision LLM |
| Vector store | Chroma (embedded) |
| Agent loop | Hand-rolled Python — no framework |
| Sandbox | Docker Desktop — identical contract on macOS and Windows (ADR-05) |
| Database | SQLite |
| Backend | FastAPI + Uvicorn |
| Frontend | React + Vite + Tailwind |
| Artifact rendering | python-docx, openpyxl |
| Event streaming | Server-Sent Events (SSE) |

**Resource types, not model names.** Capabilities declare `reasoning` / `code_generation` / `vision` / `embedding`; `config/resources.yaml` resolves them to the currently configured model. Changing a model is `ollama pull` + one config edit — never a code change (ADR-08).

---

## Four SIH demo workflows

The entire SIH-critical scope. Each maps to one or more functional requirements in `docs/requirements.md`.

| | Workflow | Capabilities used | Proves |
|---|---|---|---|
| **A** | Scanned report → extract → SOP retrieval → findings → DOCX | `extract_document` → `search_knowledge_base` → `create_docx` | Multimodal input → grounded, structured, schema-valid artifact |
| **B** | Coding request → generate → sandbox execute → verify | `generate_code` → `execute_code` (loop on failure) | Model-generated code runs in an isolated, network-denied container |
| **C** | Knowledge query → explicit retrieval → grounded answer | `search_knowledge_base` → respond | Retrieval is a visible Job step, never implicit; honest "no grounding" when relevant |
| **D** | Live zero-egress proof | *(standing, not a Job)* | `GET /api/v1/network-status` continuously shows `0 external connections`, backed by six enforcement layers |

Recommended demo order: **C → A → B**, narrate **D** continuously. Full per-workflow success criteria: `docs/demo.md`.

---

## Repository layout

```
Bulwark/
├── README.md                  ← you are here
├── AGENTS.md                  ← context for AI coding agents (read this if you are one)
├── docs/                      ← the full design (locked Phase 1–3, no implementation yet)
│   ├── README.md              ← docs navigation (file map)
│   ├── project-context.md     ← read first; handed to every new AI session
│   ├── architecture.md        ← system design
│   ├── decisions.md           ← ADRs — don't relitigate these
│   ├── capabilities.md        ← capability contracts
│   ├── agent.md               ← Orchestrator spec
│   ├── api.md                 ← HTTP API contract
│   ├── data-model.md          ← SQLite schema
│   ├── audit.md               ← event types, single source of truth
│   ├── security.md            ← zero-egress, trust boundaries
│   ├── models.md              ← resource registry, lifecycle
│   ├── rag.md                 ← ingestion + retrieval
│   ├── document-processing.md ← tiered OCR
│   ├── sandbox.md             ← Docker sandbox contract
│   ├── artifacts.md           ← deterministic DOCX/XLSX
│   ├── backend.md             ← FastAPI structure
│   ├── frontend.md            ← React structure
│   ├── configuration.md       ← config/*.yaml inventory
│   ├── deployment.md          ← install + run, macOS + Windows
│   ├── testing.md             ← test strategy, Orchestrator benchmark, M4 Pro memory test
│   ├── implementation-plan.md ← 21 stages, build order
│   ├── git-workflow.md        ← branching, commits, PRs
│   ├── demo.md                ← the four SIH workflows, exactly
│   └── AI-CONTEXT.md          ← consolidated single-file context (for upload to other AIs)
└── (backend/, frontend/, config/, docker/, data/, sandbox/) ← not yet created; Stages 1–20
```

---

## Quickstart (after implementation lands)

```bash
# one-time provisioning (internet required)
git clone <repo>
cd Bulwark
cd backend && pip install -r requirements.txt && cd ..
cd frontend && npm install && cd ..
ollama serve &                      # then in another shell:
ollama pull qwen3.5:9b
ollama pull qwen2.5-coder:7b
ollama pull qwen3-embedding:0.6b
pip install paddleocr               # first-run weight download
docker build -t bulwark-sandbox:latest ./sandbox

# every session
ollama serve &                      # terminal 1
cd backend && uvicorn main:app --host 127.0.0.1 --port 8000   # terminal 2
cd frontend && npm run dev                                  # terminal 3

# verify
curl http://127.0.0.1:8000/api/v1/health
```

**Offline validation is a required step, not an assumption.** After provisioning, disconnect from the network and re-run the four demo workflows — see `docs/deployment.md`'s checklist.

Full deployment details (macOS + Windows, firewall rule, OS-level setup): `docs/deployment.md`.

---

## Sovereignty & zero-egress

Six enforcement layers, not one:

1. **Application code** — no HTTP client call to non-loopback exists anywhere; verified at code review.
2. **Capability contract** — every capability declares `network_access: false`; checked as invariant by Policy.
3. **Model Runtime** — Ollama resolved to `localhost` only.
4. **Sandbox** — `docker run --network none`, kernel-enforced.
5. **OS firewall** — backend process scoped to loopback (one-time provisioning, never live-adjusted).
6. **Application backstop** — socket-wrapper guard rejecting non-loopback attempts (last layer, never the primary).

A live `psutil`-based monitor writes `network_check` audit events and powers a standing "0 external connections" panel in the UI. Full detail: `docs/security.md`.

---

## Status

| Phase | State |
|---|---|
| Phase 1 — Architecture | **Locked** |
| Phase 2 — Tech/model selection | **Locked** (one reasoning-model benchmark pending — `qwen3.5:9b` vs. `gpt-oss:20b`) |
| Phase 3 — Documentation | **Complete** (this repo) |
| Phase 4 — Implementation | **Not started** — Stages 1–20 per `docs/implementation-plan.md` |

The Orchestrator benchmark is a validation activity against an already-selected default; it does not block implementation because the Resource/Model Configuration Registry makes swap a config edit, not a rewrite.

---

## Reading order

If you're new to this codebase:

1. `AGENTS.md` — if you're an AI session, or skip to step 2 if you're a human.
2. `docs/project-context.md` — start here, always.
3. `docs/requirements.md` — what SIH26117 actually requires.
4. `docs/architecture.md` — the locked system design.
5. `docs/decisions.md` — why it's built this way (don't relitigate).
6. Everything else, as needed for the task at hand.

If you're contributing: see `docs/git-workflow.md`. **Never commit directly to `main`.** Always branch → implement → test → review diff → commit → push → PR — and if an AI coding agent is doing the implementing, it stops after "review diff": it prepares a suggested commit message and never runs `git commit`, `git push`, or opens/merges a PR itself. The human developer performs every Git and PR mutation. See `docs/git-workflow.md` §0 and `AGENTS.md` §7 for the exact boundary.

---

## License

TBD by the team.
