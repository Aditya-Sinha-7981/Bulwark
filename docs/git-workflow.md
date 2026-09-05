# Git Workflow

Deliberately simple, and meant to stay that way. Six people, mixed OS / GPU / RAM (`hardware.md`), everyone leaning on AI coding agents, a lot of parallel work. Every rule below exists to stop that from turning into merge chaos, lost context, or a polluted `main`. Branch-protection, CI, and reviewer policy can be tightened later; this is the default until the team decides otherwise.

---

## 0. AI Git authority — read this first

**Git mutation is human-only.**

AI coding agents may inspect Git state and prepare commit/PR information, but they do not stage, commit, push, merge, rebase, delete a branch, or otherwise modify remote repository state. AI may propose an exact commit message and PR description; the human developer decides whether to use them and performs the actual operation.

| Action | AI coding agent | Human developer |
|---|---|---|
| `git status`, `git diff`, `git log`, `git branch`, `git show`, non-mutating `git fetch` | ✅ | ✅ |
| Create/edit repository files, including `logs/<feature>.md` | ✅ | ✅ |
| Create/check out a local feature branch (`git checkout -b feature/<name>`, never `main`) | ✅ | ✅ |
| Propose a commit message / PR title & description | ✅ | ✅ |
| `git add`, `git commit` | ❌ never | ✅ |
| `git push`, including force-push | ❌ never | ✅ |
| `git merge`, `git rebase` | ❌ never | ✅ |
| Branch deletion, local or remote | ❌ never | ✅ |
| Open, approve, or merge a Pull Request | ❌ never | ✅ |
| Any other mutation of Git history or the remote repository | ❌ never | ✅ |

Every "commit → push → PR" phrase elsewhere in this document (and in `AGENTS.md`, `README.md`, `docs/project-context.md`, `docs/AI-CONTEXT.md`) describes steps the **human developer** performs, using the AI's prepared diff, tests, log entry, and suggested commit message. None of those phrases are an instruction for an AI agent to run those commands itself — §14 below states the AI-specific rules explicitly.

---

## 1. The team Git model

Four things, four different jobs. Keep them straight and the rest follows.

```
AGENTS.md + docs/           Project rules and architectural truth.
                            Authoritative. Changes only via a deliberate PR.

tasks/<feature>-task.md     Temporary work order from the project lead.
                            Scope fence for one feature. IGNORED by Git.
                            Handed out when work is assigned; never committed.

logs/<feature>.md           Permanent development & debugging history.
                            One file per feature/workstream. TRACKED by Git.
                            Append-only. Survives feature-branch deletion.

feature/<name>              Temporary isolated implementation workspace.
                            One workstream. Deleted after its PR merges.

main                        Integrated, stable project state.
                            Never committed to directly.
```

Shorter still:

```
task   = what to do       (given to you, discarded afterwards)
log    = what was done     (kept forever, inside the repo)
branch = where you do it   (discarded after merge)
main   = the result        (kept forever)
```

---

## 2. Repository truth vs task files vs development logs

**Repository truth** — `AGENTS.md`, `README.md`, `docs/**`. Defines what Bulwark *is* and what is architecturally locked. A task file never overrides these. If a task file and the architecture docs disagree, **stop and ask the project lead** (`AGENTS.md` §6).

**Task files** — `tasks/<feature>-task.md`. Written by the project lead and handed to whoever picks up the feature. They state the goal, the allowed files/areas, what is explicitly out of scope, the contracts that must not change, the acceptance criteria, and the required tests. They are *work orders*, not history — so they are **git-ignored** (`/tasks/`) and never committed. The lead can re-send or replace a task file when work continues or is reassigned.

**Development logs** — `logs/<feature>.md`. The persistent record of how a feature was actually built: implementation decisions, non-obvious bugs and their fixes, debugging findings, test results, handoff notes. They are **tracked** and live in `main`. They outlive the feature branch. A future developer or AI agent reads the log to understand why the code looks the way it does without re-deriving it.

Why the split: a clean `main` should not carry six people's transient scope-notes, but it *should* carry the reasoning history that keeps the codebase debuggable months later.

**`.gitignore` — the rules that enforce this:**

- `/tasks/` — ignored. Task files never enter Git. Do not force-add them.
- `/logs/` — **not** ignored. Logs are tracked project history.
- Also ignored: `/data/` (runtime data), `.env` (but `.env.example` is kept), `/config/*.local.yaml` (per-machine overrides; shared `config/*.yaml` is tracked), Python/Node build & cache dirs, model weights (`*.gguf`, `*.onnx`, …), editor/OS cruft, `.claude/settings.local.json`. Every rule in `.gitignore` is commented — read it before changing it.

---

## 3. Starting new work

1. The project lead writes `tasks/<feature>-task.md` and sends it to the assigned developer.
2. The developer saves it locally at `tasks/<feature>-task.md` (create the `tasks/` directory if it isn't there — it's git-ignored, so there's nothing to commit).
3. Update local `main`:
   ```bash
   git checkout main
   git pull origin main
   ```
4. Read, in this order: `AGENTS.md`, `docs/project-context.md`, the relevant detailed `docs/` file for the area, the task file, and the feature's existing `logs/<feature>.md` if one exists.

---

## 4. Creating a feature branch

Branch names describe the **workstream**, not the person:

```
feature/<short-description>     e.g. feature/orchestrator, feature/rag, feature/ocr
fix/<short-description>         e.g. fix/sse-leak
```

```bash
git checkout main
git pull origin main
git checkout -b feature/<name>
```

One logical workstream per branch. Don't bundle "everything for person X". Keep branches short-lived. Don't touch subsystems outside the task's scope — if a real dependency forces you outside it, stop and flag the project lead rather than quietly expanding the branch.

Branch ↔ file mapping:

```
branch   feature/rag
task     tasks/feature-rag-task.md     (ignored)
log      logs/feature-rag.md           (tracked)
```

---

## 5. Using the task file

- The task file is your **scope fence**. Implement what it lists under scope / allowed files; leave what it lists as out of scope alone.
- If you want to change something outside scope, first decide which case it is:
  1. already covered by a documented contract → proceed;
  2. a necessary implementation dependency → do the minimum, note it in the log;
  3. a genuine scope or architecture change → **stop and flag the project lead.** Never do it silently.
- Do **not** commit the task file. Do **not** `git add -f` it. Do **not** move it into `docs/`.
- Implementation history goes in `logs/<feature>.md`, never in the task file.
- When the work is done you may delete your local `tasks/<feature>-task.md`, but you don't have to — Git ignores it either way, so there's no cleanup obligation.

---

## 6. Maintaining the permanent development log

**File:** `logs/<feature>.md`, one per feature/workstream. Branch `feature/rag-retrieval` → `logs/feature-rag-retrieval.md`. If the branch is one of several in a broader workstream, write to the workstream log instead (e.g. `logs/feature-rag.md`) — choose the name when the workstream is created and keep it stable.

**Create it when the workstream starts** if it doesn't exist. It's a normal tracked file — an AI agent creates or edits it directly as a file edit (not a Git operation); the human developer stages and commits it alongside the code it describes:

```bash
git add logs/feature-<name>.md
git commit -m "..."
```

**Rules:**

- **Append-only during development.** Never edit or delete an earlier entry, even if it turned out to be wrong. Add a new entry that references and corrects the old one.
- **One log per feature. Never modify another feature's log.** If your work affects another workstream, note it in *your* log and tell that workstream's owner.
- Record **meaningful** units of work: an implementation milestone, a non-obvious decision, a bug and its fix, a corrected assumption, a dependency discovered, a test failure, a scope change, a pause point, branch completion.
- **Skip the noise.** No entries for typos, formatting, or one-line renames. It's a debugging aid, not a minute-by-minute diary.
- Entry format is the canonical one in `AGENTS.md` §4.3 — `### Entry N — YYYY-MM-DD HH:MM — <title>` with **What changed / Why / How to verify / Open issues / Decisions made / Supersedes-references**. Be specific enough that a reader with zero conversation context can act on it: file paths with line numbers, exact test names, exact commands.

> This supersedes the earlier "logs live at the repo root as `{branch_name}-log.md`" convention. Logs now live under `logs/`, are tracked, and are permanent. The log **entry format** in `AGENTS.md` §4 is unchanged — only the location and lifecycle changed.

---

## 7. Working while `main` changes

*(Human developer executes the commands below — `git merge` mutates history, so an AI agent never runs it; see §0. An AI agent can flag that a merge is needed and what to expect from it, but stops there.)*

Other people merge while you're mid-branch. That's expected.

```
main ──●───────────────●   (feature/Y merged here)
        \
         ●──●──●  feature/X   ← you are here; does NOT auto-receive Y
```

Your branch does **not** automatically get feature Y. Pull it in deliberately:

```bash
git checkout main
git pull origin main

git checkout feature/x
git merge main
```

Resolve any conflicts, run the tests that apply to your change (`testing.md`), then keep working. Do this whenever you know something relevant landed on `main`.

**Do not** delete and recreate your feature branch to "get up to date". Merge `main` into it.

---

## 8. Updating a feature branch from `main` (before the PR)

*(Human developer executes `git merge`/`git push` below; see §0.)*

Right before pushing the final version and opening the PR, sync again:

```bash
git checkout main
git pull origin main

git checkout feature/x
git merge main

# resolve conflicts if any, then:
<run the relevant tests/checks>
git push origin feature/x
```

This team uses **`git merge main`**, not rebase, as the standard. Merge is predictable, keeps a truthful history, and doesn't rewrite commits other people (or their AI sessions) may already have read. Don't introduce rebase into the shared workflow.

---

## 9. Commits and testing

- One logical change per commit. The message must be readable on its own without opening the diff.
- Don't mix unrelated changes. Bad: `implement rag + refactor api + fix frontend`. Good: `Implement Chroma knowledge retrieval`, then separately `Add RAG integration tests`.
- No drive-by reformatting or "cleanup" of files outside your scope. No global renames without a coordinated reason.
- Before every commit: `git status`, `git diff`, and run the relevant test category from `testing.md`.
- Commit the log entry alongside the code it describes (`logs/<feature>.md` in the same commit or an adjacent one).

---

## 10. Push and PR

*(Human developer only, from the AI's prepared diff/tests/log entry/suggested message; see §0.)*

```bash
git push origin feature/<name>
```

Open a PR into `main`. Include:

- Summary of the change
- Files changed
- Tests performed (with output where useful)
- Screenshots if UI-affecting
- Known limitations
- Link to the task / related issue if applicable

```
main
  ↑
Pull Request
  ↑
feature/<name>
```

Don't merge your own PR unless the team has explicitly said so.

The PR contains implementation code, `docs/` changes if the task required them, and the feature's `logs/<feature>.md`. It does **not** contain a task file — those are never in Git.

---

## 11. Review and merge

*(Human developer only — an AI agent never merges a PR, including its own; see §0.)*

- The reviewer checks the diff against the task file's scope and acceptance criteria, and against the locked rules in `AGENTS.md` §6.
- The reviewer can read `logs/<feature>.md` for the reasoning behind non-obvious changes.
- Required tests pass.
- Merge into `main`.

After merge, `main` contains:

```
main
├── implementation code
├── docs/ updates (if any)
└── logs/<feature>.md        ← stays here permanently
```

---

## 12. Branch deletion

*(Human developer only — branch deletion is a prohibited AI operation regardless of local/remote; see §0.)*

Feature branches are temporary integration branches. Once the PR is merged, delete the branch:

```bash
git branch -d feature/x
git push origin --delete feature/x
```

This is safe. The implementation and `logs/feature-x.md` are already in `main`:

```
main
├── implementation
└── logs/feature-x.md
```

Deleting the branch loses nothing that matters — the permanent history was never held in the branch alone, it's in `logs/`. The task file was never in Git, so there's nothing to clean up there either.

---

## 13. Conflict handling

- Conflicts surface during `git merge main`. Resolve them on your feature branch — never by forcing your branch onto `main`.
- After resolving, re-run the relevant tests before continuing or pushing.
- Prevent most conflicts with **ownership by directory/module**: `backend/domain/orchestrator/` for the orchestrator owner, `backend/domain/rag/` for the RAG owner, `frontend/` for the frontend owner, and so on.
- Shared files — `AGENTS.md`, `README.md`, `docs/project-context.md`, `docs/architecture.md`, `.gitignore` — are edited rarely and deliberately. If two branches need the same shared-doc change, coordinate first and let one branch own it.
- Each feature owns its own `logs/<feature>.md`, so logs never conflict as long as nobody edits someone else's.
- If a conflict is genuinely architectural — two branches implementing the same thing differently — stop and have the project lead arbitrate. Don't merge a fork of the architecture.

---

## 14. AI coding-agent rules

Unchanged in spirit; restated for the task/log model. See §0 for the full AI/human Git authority table — the summary here is task-workflow-specific. An AI agent working on Bulwark must:

- **Never work directly on `main`.** Branch first, always — no exception for "a quick fix" or "a docs typo". The AI may create the local branch itself (`git checkout -b feature/<name>`); that is not a history or remote mutation.
- Read `AGENTS.md` completely at the start of every session.
- Read `docs/project-context.md` and the relevant detailed architecture/contract doc for the task area.
- Read the assigned `tasks/<feature>-task.md`.
- Read the feature's `logs/<feature>.md`, most recent entries first, before writing anything.
- Stay inside the task's scope. Use existing architecture, contracts, capability names, event types, and DB fields — don't invent them.
- Never silently change a locked architectural decision or a documented contract. Flag it and ask (`AGENTS.md` §6, §10).
- Make the smallest coherent change that satisfies the task.
- Write tests for new behavior; run the relevant test category from `testing.md`.
- **Append a meaningful entry to `logs/<feature>.md`.** Never edit past entries. Never touch another feature's log.
- Inspect `git diff` and `git status` when the work is ready, and report the results.
- **Never stage, commit, push, merge, rebase, delete a branch, or open/approve/merge a Pull Request.** Propose an exact commit message and a PR summary, then stop and hand off. The human developer runs `git add`, `git commit`, `git push`, and opens/merges the PR. Never `git add -f` a task file — that's a Git mutation like any other, and it belongs to the human (task files are git-ignored and shouldn't be force-added regardless).

Canonical per-task procedure, actors explicit:

```
update main → branch → read task + log → implement in scope → test
→ review diff → append log entry → AI proposes commit message
→ human commits → human pushes → human opens PR → human reviews/merges
```

This mirrors the AI Coding Agent Operating Procedure in `docs/project-context.md` — the steps there that say "use the project's Git workflow" point here for the mechanics.

---

## 15. Final workflow and checklist

When an AI coding agent is doing the implementation, everything through "Review git diff / git status" below is the AI's job; everything from "Focused commits" onward (commit, merge into main, branch deletion) is the human developer's job — see §0.

```
Project lead writes tasks/<feature>-task.md
        ↓  (sent to the developer out-of-band)
Developer:  git checkout main && git pull origin main
        ↓
git checkout -b feature/<name>
        ↓
Save task file at tasks/<feature>-task.md          (git-ignored)
        ↓
Create / open logs/<feature>.md                    (tracked)
        ↓
Read AGENTS.md + project-context + area doc + task + log
        ↓
Implement within scope
        ↓
Run relevant tests (testing.md)
        ↓
Append an entry to logs/<feature>.md
        ↓
git merge main   (pull in anything that landed)  →  re-test
        ↓
Review git diff / git status
        ↓
Focused commits  (code + log together)
        ↓
git push origin feature/<name>
        ↓
Open PR into main
        ↓
Review  (scope + acceptance criteria + AGENTS.md §6)
        ↓
Merge into main
        ↓
git branch -d feature/<name> && git push origin --delete feature/<name>
        ↓
main keeps: implementation + docs changes + logs/<feature>.md
tasks/<feature>-task.md was never in Git
```

**Pre-PR checklist:**

- [ ] On the feature branch, not `main`.
- [ ] Latest `main` merged in (`git merge main`), conflicts resolved.
- [ ] Relevant tests/checks pass (`testing.md`).
- [ ] `git diff` / `git status` reviewed — no out-of-scope files, no drive-by reformatting, no task file staged.
- [ ] `logs/<feature>.md` has an entry covering this work, in the `AGENTS.md` §4.3 format.
- [ ] No locked rule from `AGENTS.md` §6 touched without an approved go-ahead.
- [ ] Commits are focused; messages stand on their own.
- [ ] PR description: summary, files, tests, limitations.
