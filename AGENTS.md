# AGENTS.md

> **Read this first if you are an AI coding agent.** This file is the canonical handoff document across AI sessions, tools, and teammates. It tells you what the project is, what's locked, what's pending, how to operate, and — critically — **how to write your work log so the next agent (or human) can pick up where you left off without re-asking everything.**
>
> Project: **Bulwark**. **SIH 2026, Problem Statement SIH26117.**

---

## 1. What is this project?

A self-hosted, air-gapped, agentic AI workbench for confidential work. One machine, multiple open-weight models auto-selected per task, real local tools (OCR, code sandbox, RAG, document generation), zero external network egress — provably, live, in front of judges. Detailed scope: `README.md`, `docs/project-context.md`.

**Priority order (always):**
1. Reliable SIH demonstration
2. Strong implementation quality
3. Local/offline operation
4. Demonstrable zero external egress
5. Simplicity and debuggability
6. Reasonable extensibility after SIH

**Explicitly not building:** multi-user auth/RBAC, multi-tenant deployment, microservices/K8s/cloud, enterprise air-gap distribution tooling, general-purpose agent framework dependency. If a task seems to require any of these, **stop and flag** — don't silently deviate.

---

## 2. What is your role here?

You are implementing Bulwark (or part of it) under the locked architecture. You:

- Read context, then make focused, testable changes.
- Never silently change a locked architectural decision — flag and ask.
- Maintain the feature's `logs/<feature>.md` for **every** feature/workstream you touch (rules below).
- Run tests and lint before committing.
- Commit on a branch, never on `main`.
- Inspect your own diff before pushing.

---

## 3. Before you start ANY work

In this order:

1. **Read this file completely.** (You're doing it.)
2. **Read `docs/project-context.md`.** It is the project's orientation doc and the file to hand to a new AI session.
3. **Read the relevant detailed doc** for your task area (the file map is in `docs/README.md` and `README.md`). Don't skim — agents that skip this and then "hallucinate" capability names or event types are the most common source of bugs.
4. **Inspect the repository.** Don't trust that the docs match the code; the project is mid-implementation and the code is the source of truth where it exists.
5. **Check `logs/<feature>.md`** (and the other files under `logs/`) for prior work on the same area — they may already have solved (or made) the issue you're looking at.
6. **Identify dependencies and existing implementation** before writing anything new.

If a task seems to require breaking a locked rule in §6 below, **stop and ask the user** before proceeding.

---

## 4. The work log — `logs/<feature>.md`

**This is the single most important rule in this file.** Every AI session that writes code must produce and maintain the feature/workstream work log under `logs/`. It is what makes handoff between sessions, tools, and humans painless.

### 4.1 Purpose

A persistent, **append-only** log written by AI agents, **for AI agents** (and for humans debugging later). It is tracked in Git and is permanent project history — it stays in `main` after the feature branch is merged and deleted. When a new session opens the project, the feature's `logs/<feature>.md` is the first thing it reads after this file — so the next agent doesn't have to re-ask what was done, why, what worked, what didn't, and where to look.

### 4.2 Which file, where

- **Filename:** `logs/<feature>.md` — one log per feature/workstream, named for the workstream (e.g. `logs/feature-orchestrator.md`, `logs/feature-rag.md`, `logs/feature-ocr.md`). Pick the name when the workstream is created and keep it stable across the branches that contribute to it.
- **Location:** the tracked `logs/` directory at the repository root. Never inside `docs/` (that's for design docs), never inside the code tree.
- **Tracked and permanent.** The log is committed normally and stays in `main` — it is project history, preserved after the feature branch is merged and deleted. It is **not** removed before merge.
- **One log per feature/workstream.** If you move to a different workstream, you stop appending to the previous log and start using that workstream's log.
- **Owned by the feature/workstream owner.** Do not modify another feature's log. If your work affects another workstream, record it in *your* log and tell that owner.
- If the log doesn't exist for your feature yet, **create it** on your first commit.

### 4.3 Format

The full canonical format:

```markdown
# logs/<feature>.md

> Feature / workstream: `<feature>`  (branches: `feature/<name>`, …)
> Started: YYYY-MM-DD by <model/tool>
> Status: in-progress | paused | completed | abandoned

## Goal
What this branch is trying to achieve. One short paragraph. Reference the docs section it implements against.

## Plan
The implementation plan as you understood it on starting — phases, files you expect to touch, validation steps.

## Entries
Chronological, newest at the bottom. Each entry is a fenced block:

### Entry N — YYYY-MM-DD HH:MM — <short title>
**What changed:** (files + line refs like `backend/main.py:42`, brief diff summary)
**Why:** (rationale, link to docs/ADRs)
**How to verify:** (commands, tests, manual steps)
**Open issues / known gaps:** (things deferred, things you flagged for the user)
**Decisions made:** (anything non-obvious the next agent should not relitigate)
**Supersedes / references:** (prior entries this builds on or corrects; never delete them — add a new entry that points here)

---

### Entry N+1 — ...

## Open questions for the user
Anything you flagged but didn't get a call on — these stay here until the user answers and you turn them into a normal entry.

## Links
- PR: <url when created>
- Related branches / logs: ...
- Doc references: docs/agent.md, docs/capabilities.md, ...
```

### 4.4 When to add an entry

Add an entry after **any meaningful unit of work**, specifically:

- A `TASKS.md` phase completes or starts.
- A bug is fixed (especially a non-obvious one).
- A non-obvious decision is made (even tiny — "I used `httpx` instead of `requests` because…").
- A wrong assumption you had is corrected (add the entry that explains what you learned, **do not edit the earlier wrong entry**).
- A user instruction changes the scope.
- You pause work and want a clean handoff point.
- You finish the branch (final entry: status → `completed` or `abandoned`).

**Skip trivial one-line fixes** — a typo or whitespace cleanup doesn't need its own entry. Bundle small touches into the next meaningful entry.

### 4.5 The append-only rule (hard requirement)

- **Never edit or delete a previous entry**, even if it's wrong, stale, or superseded by a later decision.
- If something needs correcting, **add a new entry that references the old one** (use the "Supersedes / references" line) and explain the correction. The old entry stays — it documents what you actually believed and acted on, which is itself useful debugging context.
- This is what makes the log trustworthy. A log that quietly rewrites itself is no better than no log.

### 4.6 Specificity bar (hard requirement)

Write entries specific enough that a reader with **zero conversation context** could act on the file without follow-up questions. Concretely:

- Bad:  *"fixed the agent loop"*
- Good: *"Entry 4 — corrected Orchestrator termination: was terminating on `action: respond` even when `content` was empty, leading to silent 'empty answer' Jobs. Now requires non-empty `content`. Tests added in `backend/tests/test_orchestrator.py::test_terminate_on_empty_content`."*

- Bad:  *"updated config"*
- Good: *"Entry 7 — added `model_runtime.connect_timeout_seconds: 5` to `config/app.yaml` after Ollama cold-start took 60s+ on the M4 Pro and was hanging the health check. Default remains unset for non-health paths."*

Use file paths with line numbers (`backend/main.py:42`), test names, exact config keys, exact error messages. Future-you and the next agent will thank present-you.

### 4.7 What to do on starting a new session on the same feature

1. Open the feature's `logs/<feature>.md`.
2. Skim the "Goal" and "Plan" at the top.
3. Read the most recent 3–5 entries.
4. Read "Open questions for the user" — anything there is still pending.
5. Check the diff between the last entry's commit and `HEAD` to make sure the log and the code agree.
6. Continue work. New entries go at the bottom of "Entries".

### 4.8 What to do when you finish a branch

Add a final entry:

```
### Entry N — YYYY-MM-DD HH:MM — branch complete
**Status:** completed | abandoned
**Summary:** (1–3 sentences: what shipped, what's left)
**Final test status:** (paste relevant `pytest`/lint output tail)
**Reviewer notes:** (anything a reviewer should know before merging)
```

Update the front-matter `Status:` line at the top of the file to match. Leave the log file in place — it is committed with the branch and stays in `main` after the branch is merged and deleted. Never delete it, and never rewrite earlier entries.

---

## 5. Operating procedure (for every task)

Mirror of `docs/project-context.md` §"AI Coding Agent Operating Procedure" — restated here so you don't need to chase it.

1. Read this file (`AGENTS.md`) completely.
2. Read `docs/project-context.md`.
3. Inspect the repository (don't trust docs over code).
4. Read the relevant detailed doc for your task (`docs/README.md` file map).
5. Read the feature's `logs/<feature>.md` if one exists.
6. Identify dependencies and existing implementation.
7. Do **not** silently change architectural decisions — flag and ask instead.
8. Implement the smallest coherent change that solves the problem.
9. Run relevant tests/checks (`docs/testing.md` says which category applies).
10. Inspect your own diff (`git diff`).
11. **Append an entry to the feature's `logs/<feature>.md`.** (See §4.)
12. Commit on a branch, never `main`. (See §7.)
13. Push the branch.
14. Report what changed, what was tested, any remaining issues.

---

## 6. Locked rules — do not change without explicit user approval

From `docs/project-context.md` and `docs/architecture.md`. If a task seems to require breaking one, **stop and flag it explicitly** rather than silently deviating.

1. **The Orchestrator has no execution rights.** It proposes; it never executes directly. The only path from Orchestrator output to an effect in the world is `Policy → Job Manager → Executor`, and that path is structural.
2. **The Policy layer is fully deterministic.** Never model-based judgment.
3. **Capabilities declare resource types, never model names.** The Resource/Model Configuration Registry (`config/resources.yaml`) is the only place model names live.
4. **OCR is one capability with internal tiered escalation.** The Orchestrator never sees separate OCR/vision steps.
5. **RAG retrieval is always explicit.** The Orchestrator must propose `search_knowledge_base`; there is no auto-retrieve-on-every-turn path.
6. **Artifact generation is deterministic.** The model produces structured data; application code renders the file. The model never controls formatting.
7. **The Job trace is a filtered view over the Audit event stream.** Never a second, parallel log.
8. **The Sandbox capability contract is identical on macOS and Windows.** No OS-specific application logic.
9. **Zero-egress is enforced in six layers** (app / capability / model runtime / sandbox / OS / monitoring) — never by one mechanism alone.
10. **`network_access: false` is an invariant.** Never true. Don't add a config knob to flip it.
11. **Capabilities only accept and emit shapes declared in `docs/capabilities.md`.** Don't invent fields.
12. **Audit events follow `docs/audit.md`.** Don't invent event types.
13. **The data model follows `docs/data-model.md`.** Don't invent tables or fields without updating that file first.

If you need to break one of these, write a proposed ADR-style entry in your branch log explaining the conflict, the proposed change, and the trade-off — then ask the user for an explicit go/no-go before coding.

---

## 7. Git workflow

From `docs/git-workflow.md`. Short version:

- **Never commit directly to `main`.** No exceptions. Not "for a quick fix", not "for a config tweak", not "for a docs typo". Branch.
- Branch names: `feature/<short-desc>` or `fix/<short-desc>`. The feature's permanent log is `logs/<feature>.md` (see `docs/git-workflow.md`).
- One logical change per commit. Message must be readable without opening the diff.
- Before committing: `git status`, `git diff`, run the tests that apply to your change.
- Before pushing: re-check `git status` and `git diff`, confirm you're on the right branch.
- Push branch → open PR. Don't merge your own PRs unless the team explicitly says so.

AIs specifically: `update main → branch → implement → test → review diff → commit → push → PR`. This is identical to the procedure in `docs/project-context.md` §11 and points at `docs/git-workflow.md` for mechanics.

---

## 8. Tech stack — short version

Full inventory + locked choices: `README.md` §"Tech stack" and `docs/models.md`.

- Backend: FastAPI + Uvicorn, Python 3.11+, hand-rolled agent loop (no framework).
- Frontend: React + Vite + Tailwind.
- Model runtime: Ollama (`reasoning`/`code_generation`/`vision`/`embedding` resource types — never reference a model name in app code).
- OCR: PaddleOCR PP-OCRv6 with internal escalation to the `vision` resource.
- Vector store: Chroma.
- Sandbox: Docker Desktop, `--network none`, identical on macOS and Windows.
- DB: SQLite. Artifact rendering: python-docx, openpyxl. Event streaming: SSE.

Capability contracts are in `docs/capabilities.md` — that's the canonical list. The Orchestrator's proposal format (`{action: invoke_capability|respond, ...}`) is in `docs/agent.md`.

---

## 9. Verification — how to know your work is right

- Does it match the contract in the relevant `docs/` file (API shape, capability schema, event type, data-model field)? If you had to guess a name or shape, stop — check `docs/decisions.md` and the relevant contract file before inventing one.
- Does it preserve every rule in §6 above?
- Did you add or update an Audit event for anything meaningfully new that happens?
- Did you run the relevant test category from `docs/testing.md`?
- Did you write / update the relevant test for new behavior?
- Did you append an entry to `logs/<feature>.md`?

If any answer is "no" or "I'm not sure", don't commit yet.

---

## 10. When to ask the user vs. decide yourself

**Decide yourself** (and log the decision):
- Variable naming, file organization within an established module.
- Choice between two equivalent library functions.
- Test phrasing, comment wording.
- Anything fully covered by an existing `docs/` contract.

**Ask the user** (and write the question into "Open questions for the user" in your log):
- Anything that touches a locked rule in §6.
- New capability, new event type, new DB table or field.
- New dependency not already in `requirements.txt` / `package.json`.
- Deviation from a documented contract for any reason.
- "Should I…?" questions where the answer changes user-visible behavior.

Default to asking over guessing. A clarifying question that takes 30 seconds is cheaper than a wrong implementation that takes 30 minutes to undo.

---

## 11. Quick links

- `README.md` — project overview, architecture diagram, tech stack, quickstart
- `docs/project-context.md` — orientation (read first, every session)
- `docs/architecture.md` — locked system design
- `docs/decisions.md` — ADRs (don't relitigate)
- `docs/agent.md` — Orchestrator implementation spec
- `docs/capabilities.md` — every capability contract
- `docs/api.md` — HTTP API contract
- `docs/data-model.md` — SQLite schema
- `docs/audit.md` — event types
- `docs/security.md` — zero-egress, trust boundaries
- `docs/implementation-plan.md` — 21 build stages
- `docs/testing.md` — test categories, Orchestrator benchmark, M4 Pro memory test
- `docs/git-workflow.md` — branching, commits, PRs
- `docs/demo.md` — the four SIH demo workflows
- `docs/AI-CONTEXT.md` — consolidated single-file context (for upload to external AIs / PPT prep)
- `logs/<feature>.md` files — permanent, tracked development log per feature/workstream (prior work, decisions, debugging history)

---

## 12. TL;DR for a hurried agent

1. Read `docs/project-context.md`.
2. Read the feature's `logs/<feature>.md` if it exists.
3. Don't break a rule in §6.
4. Implement the smallest coherent change.
5. Test it.
6. Diff it.
7. **Append an entry to `logs/<feature>.md`** with what changed, why, how to verify, and any open issues.
8. Commit on a branch. Push. Open PR.

If you do only one thing from this file, do #7. The log is what makes this project survivable across sessions.
