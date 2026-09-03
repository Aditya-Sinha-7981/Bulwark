# Bulwark — Documentation

**SIH 2026, Problem Statement SIH26117** — a sovereign, on-premise, agentic multimodal AI workbench for confidential industrial/organizational work.

> Project: **Bulwark**.

## Start here

| Reader | Read first |
|---|---|
| Human new to the project | `../README.md` at the repo root (overview, architecture, tech stack, quickstart), then `project-context.md` below. |
| **AI coding agent** | **`../AGENTS.md` at the repo root** (operating procedure, locked rules, work-log convention). Then `project-context.md`. Then the relevant detailed file for your task. |
| Reviewer / judge / PPT prep | `../AI-CONTEXT.md` — single-file consolidated context covering architecture, stack, requirements, demo flows, ADRs, and implementation plan. |

## Reading order for a human or AI picking up the project cold

1. `project-context.md` — start here, always.
2. `requirements.md` — what SIH26117 actually requires of us.
3. `architecture.md` — the locked system design.
4. `decisions.md` — why it's built this way, so you don't relitigate settled choices.
5. Everything else, as needed for the task at hand.

## File map

| File | Covers |
|---|---|
| `project-context.md` | Orientation for humans and AI agents — read first |
| `requirements.md` | SIH requirements, scope, acceptance criteria |
| `architecture.md` | System architecture, components, data flow |
| `decisions.md` | Architecture/Technology Decision Records |
| `api.md` | Backend API contract |
| `data-model.md` | Persistent data model (SQLite schema) |
| `capabilities.md` | Every agent capability, as a contract |
| `agent.md` | Orchestrator implementation spec |
| `models.md` | Model stack, resource registry, lifecycle manager |
| `rag.md` | Retrieval pipeline |
| `document-processing.md` | OCR/vision extraction pipeline |
| `sandbox.md` | Docker code-execution sandbox |
| `security.md` | Sovereignty, zero-egress, trust boundaries |
| `audit.md` | Audit/Event subsystem (single source of truth) |
| `artifacts.md` | Deterministic DOCX/XLSX generation |
| `backend.md` | FastAPI backend structure |
| `frontend.md` | React frontend structure |
| `configuration.md` | Config files, no secrets in SIH runtime |
| `deployment.md` | Install and run, macOS + Windows |
| `testing.md` | Test strategy, failure injection |
| `demo.md` | The four SIH showcase workflows, exactly |
| `git-workflow.md` | Branching, commits, PRs |
| `implementation-plan.md` | Build order, MVP vs. post-MVP |
| `AI-CONTEXT.md` | Consolidated single-file context (for upload to external AIs / PPT prep) |

## For AI coding agents — the work-log rule

Every AI session that writes code on a branch must produce and maintain a `{branch_name}-log.md` at the **repo root** (not inside `docs/`). The rule, format, append-only discipline, and specificity bar are defined in `../AGENTS.md` §4. Short version: append, don't edit; be specific enough that the next agent can act without re-asking; reference prior entries when correcting yourself; one log per branch.

## Status

Phase 1 (architecture) and Phase 2 (technology/model selection) are **locked**. Phase 3 (this documentation set) is **complete**. **Implementation has not started** — see `implementation-plan.md` for the 21-stage build order. The Orchestrator model benchmark referenced in `models.md` and `testing.md` is a validation activity against an already-selected default (`qwen3.5:9b`) — it does not block starting implementation because the Resource/Model Configuration Registry makes model swap a config edit, not a rewrite.
