# logs/feature-frontend-scaffold.md

> Feature / workstream: `frontend-scaffold`  (branches: `feature/frontend-scaffold`)
> Started: 2026-09-09 by opencode (big-pickle)
> Status: in-progress

## Goal

Implement Task 1.b — Frontend scaffold & health (implementation-plan.md Stage 1 frontend half; foundation for Stage 16). Stand up the React + Vite + Tailwind single-page app skeleton so `npm run dev` serves a minimal "Bulwark Workbench" shell on `http://localhost:5173`, renders, and confirms it can reach the backend by calling `GET /api/v1/health` once on mount through a single centralised `services/api.js`. Reference: `tasks/1b-frontend-scaffold (3).md`.

## Plan

Per task file §4 Allowed Files: implement `frontend/src/main.jsx` (createRoot mount into `#root` + import `./index.css`), `frontend/src/App.jsx` (minimal Workbench shell that calls `getHealth()` on mount and renders either the returned health status or a non-crashing "Backend unreachable" state), `frontend/src/services/api.js` (centralised `getHealth()` at `BASE_URL = http://127.0.0.1:8000`, `fetch()` only here, typed `ApiError`), and a Vitest + React Testing Library smoke test at `frontend/src/__tests__/App.test.jsx`. Add `"test": "vitest"` plus the 4 vitest/RTL devDependencies to `frontend/package.json` (updates `package-lock.json`). Existing Tailwind files (`tailwind.config.js`, `postcss.config.js`, `src/index.css`) are already correct and must remain untouched unless verification proves otherwise. Create `logs/feature-frontend-scaffold.md` (this file).

Out of scope (Task 16.a/b) and MUST NOT be touched: `pages/Workbench.jsx`, `hooks/useApi.js`, `hooks/useJobEvents.js`, `components/*`. No Vite proxy, no state-management library, no UI component library, no external CDN/fonts/analytics, no browser calls to Ollama/Chroma/Docker, no `fetch()` outside `services/api.js`. Do not implement Task 16. Do not commit/push (human-only git operations per `docs/git-workflow.md`).

Verify: `cd frontend && npm install`, `npm test`, `npm run build`; then `git diff --check`, `git status`, `git diff`; grep that `fetch(` appears only in `frontend/src/services/api.js`; confirm no external hosts and Task 16 placeholders unchanged.

## Entries

### Entry 1 — 2026-09-09 — Task 1.b frontend scaffold & health implemented, verified

**What changed:**
- `frontend/src/services/api.js` — centralised API module. `BASE_URL = 'http://127.0.0.1:8000'`; `class ApiError extends Error` carrying `.status` and `.url`; single exported `getHealth()` doing `fetch(`${BASE_URL}/api/v1/health`)`, checking `res.ok`, parsing JSON, returning the parsed health object; on non-ok throws `ApiError` with the HTTP status; on network failure the native `TypeError` propagates (caller treats both as "unreachable"). Structured as a flat function-per-endpoint module so Task 16.a can add one function per `docs/api.md` endpoint without refactor. This is the only file containing `fetch(`.
- `frontend/src/main.jsx` — imports `./index.css` and `App`, mounts `<App />` into the existing `#root` via React 18 `createRoot(...).render(...)`.
- `frontend/src/App.jsx` — intentionally minimal. Renders a "Bulwark Workbench" shell (a titled panel with Tailwind styling). Calls `getHealth()` exactly once on mount via `useEffect`. Displays the returned health status fields (status/backend/database/model_runtime/docker) on success; on rejection shows a clearly visible "Backend unreachable" state. Failure path is caught and set in state — no white screen, no uncaught promise, no render-boundary throw. Does not implement any Task 16 UI.
- `frontend/src/__tests__/App.test.jsx` — Vitest + React Testing Library smoke test, `// @vitest-environment jsdom` per-file environment, imports `@testing-library/jest-dom` for matchers. Covers `getHealth` success (App renders resolved health status) and `getHealth` rejection (App renders "Backend unreachable"). Uses `vi.mock('../../services/api')` so no real network call occurs; component-only development works without Task 1.a running.
- `frontend/package.json` — added `"test": "vitest"` script and devDependencies `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`. (`package-lock.json` updated by `npm install`.)
- `logs/feature-frontend-scaffold.md` — this file, created per `AGENTS.md` §4.

**Why:** Implements Task 1.b exactly, staying within the task file's Allowed Files list and STRICT SCOPE. Keeps `services/api.js` the single place all `fetch()` calls live (`docs/frontend.md` "API integration", security boundary in `docs/security.md` "Trust boundaries"). Base URL targets only the local backend at `127.0.0.1:8000` (`config/app.yaml` app.host/port), consistent with `docs/api.md` health contract. Uses Vitest + RTL per the task's resolved decision (§11 — vitest + react-testing-library + jsdom).

**How to verify:**
```bash
cd frontend
npm install                     # installs vitest + RTL devDeps, updates package-lock.json
npm test                        # vitest — both smoke tests pass
npm run build                   # vite build succeeds (Tailwind styles applied)
cd <repo root>
git diff --check                # no whitespace errors
git status                      # only in-scope files changed/new
git diff                        # review
```
Also: `rg -l "fetch\\(" frontend/src` should return only `services/api.js`; confirm no external hosts; confirm Task 16 placeholder files unchanged.

**Open issues / known gaps:**
- Manual integration "browser shows `status: ok` with backend running" requires Task 1.a backend up; not exercised in this headless session, but CORS is preconfigured in `config/app.yaml` (`cors_origins: ["http://localhost:5173"]`) so no Vite proxy was needed.
- Not committed/pushed — per explicit instruction (human-only git operations). Working tree on `feature/frontend-scaffold` has the implementation not yet in git history.

**Decisions made:**
- Used `feature/frontend-scaffold` (matches task file §Task Information) rather than the also-spotted remote `feature/frontend-scaffold-health` — confirmed with the user; created fresh local branch off `main` (`0b62325`, already == `origin/main`; nothing to pull).
- No Vite dev proxy: reliance on backend CORS is the task's preferred approach (`docs` + task §10 Known Risks); `config/app.yaml` already whitelists `http://localhost:5173`.
- Failure handling: treats both `ApiError` (non-2xx) and the native fetch `TypeError` (network down) as "unreachable", so a stopped Task 1.a backend yields the visible non-crashing state (task §7 Error Handling).
- `main.jsx` uses React 18 `createRoot` (current `react` ^18.3.1) rather than legacy `ReactDOM.render`.

**Supersedes / references:** None — first entry for this workstream. Mirrors structure of `logs/feature-backend-bootstrap.md` (the parallel Task 1.a log).

---

### Entry 2 — 2026-09-09 — Full Bulwark frontend UI built on the Task 1.b shell

**What changed:** Completed the complete dark enterprise frontend requested by the user (supersedes the original Task 1.b "minimal shell only" scope for UI code; Task 1.b's API-layer + test foundations remain the base). Working tree on `feature/frontend-scaffold-health` (remote branch == `origin/main` at `0b62325`).
- `frontend/tailwind.config.js` — extended design tokens: `ink/panel/surface/elevated` surfaces, `line/lineStrong` borders, `txt.{hi,mid,low,dim}`, `accent{+strong,hover,soft}`, `ok`, `warn`, `danger`, `band` (purple) + mono/sans stacks.
- `frontend/src/index.css` — `@layer base` (dark scrollbar, selection) + `@layer components`: `.card`, `.btn`/`.btn-primary/-ghost/-quiet/-danger`, `.input`, `.label`, `.mono`, `.badge-*`, `.pill`.
- `frontend/src/services/api.js` — rewritten: `request()` helper, `ApiError(status,message,url)`, `getHealth()`, `createJob(...)`, `getJob(id)`, `getJobTrace(id)`, `jobEventsUrl(id)`, `getNetworkStatus()` (integration stub). **`fetch(` still lives only here** (verified with grep: only `src/services/api.js`).
- `frontend/src/data/mockJobs.js` — `MOCK_JOBS` (12 jobs; statuses completed/running/failed/waiting), `MOCK_ACTIVITY` (6), `KB_SOURCES` (3).
- `frontend/src/components/ui/` — `Icon.jsx` (inline SVG map, ~30 icons), `Button.jsx`, `Badge.jsx`, `PageHeader.jsx`, `EmptyState.jsx`.
- `frontend/src/components/layout/` — `AppShell.jsx`, `Sidebar.jsx` (nav ids workbench/jobs/knowledge/artifacts/audit/settings, brand + `NODE • CONNECTED` card), `Header.jsx` (`LOCAL • SECURE` pill), `StatusBar.jsx` (local backend connected / zero external egress).
- `frontend/src/hooks/useHealth.js` — polls `getHealth()` on mount + every 15 s; states `checking|connected|unreachable`.
- `frontend/src/components/workbench/` — `PromptComposer.jsx` (Ctrl+Enter submit, file attach → `onAttach({name,size,type})`, KB dropdown), `QuickActions.jsx` (4 preset prompts), `DocCard.jsx`, `ArtifactCard.jsx` (Open/Download/Copy), `ExecutionSteps.jsx`, `SecurityPanel.jsx`, `TaskDetailsPanel.jsx`, `FollowUpComposer.jsx`, `TaskResult.jsx`.
- `frontend/src/pages/Workbench.jsx` — replaced the empty tracked placeholder (`ebef7cb`, 0 bytes) with empty → running → result orchestrator (6 simulated execution steps on 450 ms timers, `TaskResult` + `TaskDetailsPanel`). Commented integration point for `createJob`/`getJobTrace` once the backend exposes a conversations/create endpoint.
- `frontend/src/pages/Jobs.jsx` + `frontend/src/components/jobs/` — `JobFilters.jsx` (status tabs + search), `JobsTable.jsx`, `JobOverview.jsx` (counts), `RecentActivity.jsx`, `JobsQuickActions.jsx`, `Pagination.jsx` (page + rows-per-page). Client-side filter/search over `MOCK_JOBS` (backend has no job-list endpoint).
- `frontend/src/pages/{Knowledge,Artifacts,Audit,Settings}.jsx` — consistent shells with empty states + pipeline/contract info; Settings reads `healthState` for the Connection card. (Task 16 `useApi.js`/`useJobEvents.js`/`components/*` placeholders untouched.)
- `frontend/src/App.jsx` — rewritten as state-based nav shell (`PAGES` map, `AppShell` + `useHealth`, no router dependency). `frontend/src/main.jsx` unchanged from Entry 1.
- `frontend/src/__tests__/App.test.jsx` — rewritten to 7 tests: health success/failure, prompt submit → running → completed result (fake timers), empty-prompt guard, sidebar navigation, jobs status filter, jobs search.

**Why:** User asked for the whole Bulwark UI matching four visual references (not present in the repo — built from the textual spec). Kept zero new runtime deps (no router/state mgmt/UI lib), external fonts/C DNs untouched, `fetch()` single-location rule intact, no Vite proxy (backend CORS whitelists `http://localhost:5173`).

**How to verify:** `cd frontend && npm test` (7/7 pass), `npm run build` (clean; 64 modules, CSS 25.71 kB, JS 192.69 kB), `npm run dev` → `Invoke-WebRequest http://localhost:5173` returns HTTP 200. `git diff --check` clean.

**Open issues / known gaps:**
- Job creation + Jobs dashboard are simulated from `frontend/src/data/mockJobs.js` — the FastAPI backend has `POST /api/v1/jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/trace`, `GET /jobs/{id}/events`, but no conversations or job-list endpoints yet, so the Workbench/Jobs pages define the integration points via comments.
- Manual visual QA in a real browser (layout, overflow, fonts) still recommended; headless verification here is HTTP-200 + component tests only.
- Not committed/pushed (human-only git operations). Branch `feature/frontend-scaffold-health`; remote has no unique commits.

**Decisions made:**
- Filled the tracked-empty `pages/Workbench.jsx` placeholder — the user's build request supersedes Task 1.b's "don't touch Task 16 placeholders" instruction for this file; Task 16's `hooks/useApi.js`, `hooks/useJobEvents.js`, and other placeholder components remain untouched.
- No react-router: simple state-based nav keeps zero new runtime dependencies.
- `NODE • CONNECTED` etc. use literal `•` (U+2022) inside JS string expressions — HTML entities like `&bull;` are NOT decoded inside JS string literals (only in JSX text), which initially broke the tests (see Entry 3).

**Supersedes / references:** Extends Entry 1 (Task 1.b shell). See Entry 3 for the build/test corrections made in this pass.

---

### Entry 3 — 2026-09-09 — Build/test corrections (Tailwind theme() + JS-string entity + test selector fixes)

**What changed:**
- `frontend/src/components/layout/Sidebar.jsx` and `StatusBar.jsx` — replaced `&bull;` string literals with `•`. `{'NODE &bull; CONNECTED'}` renders the literal text `NODE &bull; CONNECTED` because JS strings do not decode HTML entities (only JSX child text does). Header's `LOCAL &bull; SECURE` written as JSX children was already correct.
- `frontend/src/components/layout/Sidebar.jsx:80` — `shadow-[0_0_8px_theme(colors.ok)]` → `theme(colors.ok.DEFAULT)` (same for `danger`). Tailwind's `theme()` resolved against a nested color object returns an object, not a string; the build warned `contains an invalid theme value and was not generated`. Now the production build is warning-free.
- `frontend/src/__tests__/App.test.jsx` — search input queried by accessible name `Search tasks` (aria-label, not the `…` placeholder); duplicate text matches (`Analyze the Q3 safety report`, `Completed`, `Summary_Report.md`, `Backend unreachable`) switched to `getAllByText(...).length > 0` since the same string renders in both the result card and `TaskDetailsPanel`.

**Why:** First test run failed 4/7, then 2/7, then 1/7 — all selector/entity mismatches, not app-logic bugs. Build warning was a genuine Tailwind config misuse.

**How to verify:** `cd frontend && npx vitest run` → 7/7 pass; `npm run build` → no warnings. `git diff --check` → clean.

**Open issues / known gaps:** None.

**Decisions made:** None beyond the fixes above.

**Supersedes / references:** Corrects pieces of Entry 2.

---

### Entry 4 — 2026-09-09 — Task 1.b re-verification pass against the current tree

**What changed:** No code changes — a non-destructive verification of Task 1.b (`tasks/1b-frontend-scaffold (3).md`) hard requirements against the current working tree (which carries Entry 1's scaffold plus Entries 2–3's full-frontend build, per the user's later explicit instruction). Checks run and results:
- **`fetch(` single-location:** grep of `frontend/src` → only `frontend/src/services/api.js` (a doc comment `:3` + the actual call `:21`). Passes `docs/frontend.md` "API integration".
- **External hosts:** grep `cdn|googleapis|fonts\.|analytics|unpkg|cloudflare` across `frontend/` → only a comment in `src/components/ui/Icon.jsx:1` ("Local inline SVG icon set — no external icon libraries or network fonts"). Zero CDN/font/analytics references.
- **Base URL:** `services/api.js:6` = `http://127.0.0.1:8000` (loopback only); `getHealth()` (`:50-52`) → `GET /api/v1/health`, returns parsed object or throws `ApiError`/network error — satisfies Requirement 3 + Error Handling (no white screen, no uncaught promise; App.jsx failure path renders the visible unreachable state).
- **Tailwind pipeline:** `tailwind.config.js` `content: ['./index.html', './src/**/*.{js,jsx}']`; `postcss.config.js` wires `tailwindcss` + `autoprefixer`; `src/index.css` imports the three `@tailwind` directives; imported by `main.jsx`.
- **Tests:** `cd frontend && npm test -- --run` → 1 file, **7/7 passed**, including the two task-mandated cases in `frontend/src/__tests__/App.test.jsx` — "renders the Workbench and a connected indicator when health succeeds" (`mockGetHealth.mockResolvedValue`) and "shows an unreachable state when health fails" (`mockRejectedValue`). The module under test is `../services/api.js` (mocked via `vi.mock`), not global `fetch` — matches task §8.
- **Build:** `npm run build` → 64 modules, clean (no warnings); dist CSS spot-check: contains generated utilities `.bg-ink`, `.text-txt-hi`, `.min-h-screen`, `.ml-auto`, `.card`, `.btn-primary` and **no** `@tailwind` directive — proves real utility generation, not passthrough.
- **Dev server:** `npm run dev -- --port 5173 --strictPort` → `Invoke-WebRequest http://localhost:5173` returned HTTP 200.
- **Backend integration check:** Task 1.a backend not running on `127.0.0.1:8000` (connection refused) — so the live "status: ok" path is not exercisable here; it is covered by the mocked-success test and requires Task 1.a up per the task's §5 dependency note. Backend-down rendering (visible unreachable state, no crash) is covered by the mocked-reject test.
- **Git:** `git status --porcelain` shows the expected frontend workstream files plus the two pre-existing unrelated items (`TASKS.md` `p# Tasks` typo, `backend/.python-version`) untouched by this session; `git diff --check` exit 0 (no whitespace errors).

**Why:** The user re-issued the Task 1.b implementation order after the full-frontend build (Entries 2–3) had expanded the tree. AGENTS.md §10 + the task's own stop-and-ask clause required surfacing the scope conflict rather than silently reverting work; the user chose "verify already-done Task 1.b". This entry records that verification.

**How to verify:** Re-run the commands above (`npm test -- --run`, `npm run build`, dev-server probe, the two greps). All green at time of writing.

**Open issues / known gaps:**
- The current tree intentionally exceeds Task 1.b's narrow file list (full app shell, `createJob`/`getJob`/`getJobTrace`/`jobEventsUrl`/`getNetworkStatus` in `services/api.js`, populated `pages/Workbench.jsx`) — this is Entries 2–3's later, explicitly-requested build, not a Task 1.b violation. `api.js` remains a plain function-per-endpoint module, so Task 16.a can still add functions with no refactor.
- Live browser visual QA and the live success-path health check still require Task 1.a running + a human with a browser (headless session verified HTTP 200 + component tests only).
- Nothing committed/pushed (human-only git). Branch: `feature/frontend-scaffold-health`.

**Decisions made:** Confirmed the verification-only approach with the user (question answered: "Verify already-done Task 1.b (Recommended)"). No files modified in this pass.

**Supersedes / references:** Builds on Entries 1–3. Task-1.b acceptance criteria §9 mapped to checks above; the only unverified live items are the two that explicitly require Task 1.a + a human browser.

---

## Open questions for the user

- None at present. Awaiting: (1) manual visual QA in a real browser against the four reference screenshots, and (2) a decision on whether Workbench job creation + the Jobs dashboard should wire to the backend once it ships a conversations/job-list endpoint (Task 16 integration). (Branch-name ambiguity resolved: using `feature/frontend-scaffold` originally; current work on `feature/frontend-scaffold-health`.)

## Links

- PR: not yet opened (commit/push + PR deferred to the human developer per `docs/git-workflow.md` §0)
- Related branches / logs: `feature/backend-bootstrap` (parallel Task 1.a)
- Doc references: `tasks/1b-frontend-scaffold (3).md`, `docs/frontend.md`, `docs/api.md`, `docs/security.md`, `docs/architecture.md`, `docs/git-workflow.md`, `AGENTS.md`, `config/app.yaml`

