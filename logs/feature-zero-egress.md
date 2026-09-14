# logs/feature-zero-egress.md

> Feature / workstream: `zero-egress` (Task 18 — security / zero-egress validation)
> Branch: `feature/zero-egress`, branched from `fix/kb-upload-ui` (itself branched from `main`) 2026-09-14
> Started: 2026-09-14 by Aditya's direction
> Status: in-progress — layers 1, 2, 3, 4, 6, 7, 8 implemented and tested; layer 5 authored but not executed; the offline validation run (§7 Req 9) not yet performed

## Goal

Per `tasks/18-security-zero-egress.md`: bring all six zero-egress enforcement layers fully into place, prove they hold (live + retroactive), and run the full offline validation across all four demo workflows. This log records what was implemented, tested, and — since some of this task's steps are physically disruptive to the reference machine's own networking or require sudo/Administrator rights — what was deliberately **not** run autonomously and needs to happen with Aditya present.

## Entry 1 — 2026-09-14 — Layers 1, 2, 3, 4, 6, 7, 8 implemented; test suites passing

**What was already in place before this task** (discovered during the codebase read, not built here):

- **Layer 2** (Policy invariant): `backend/domain/policy/engine.py::_check_network_access_invariant` already denies unconditionally on `network_access != false` or `network_access_allowed: true`; `backend/domain/capabilities/registry.py` already raises at construction time if any static capability declares `network_access` other than `false`.
- **Layer 3** (Model Runtime loopback): `config/app.yaml` `ollama.base_url` is already `http://localhost:11434` with an explicit "loopback only" comment; `backend/domain/model_runtime/runtime.py` never reads a configurable host from anywhere else.
- **Layer 4** (sandbox): `backend/domain/sandbox/docker_executor.py` already runs with `--network none`; `backend/tests/test_sandbox.py::TestNetworkDenial` already proves an outbound call fails under it (Task 13).
- **Layer 7** (monitor): `backend/domain/monitoring/network_monitor.py` was already a complete continuous `asyncio` background loop — not just a scaffold as Task 15's docstring suggested — emitting `network_check` events (`job_id: null`) on a 5s interval and backing `GET /api/v1/network-status`. Already wired into `backend/main.py`'s lifespan (`network_monitor.start()` / `.stop()`).

**What this entry built:**

1. **Layer 1 — `scripts/check_no_egress.py`.** Static scan of `backend/` for `httpx`/`requests`/`urllib`/`http.client`/`aiohttp`/raw `socket.connect((...))` usage outside `backend/domain/model_runtime/runtime.py`, plus a check that `config/app.yaml`'s `ollama.base_url` resolves to a loopback host. One legitimate exception found and allowlisted: `backend/api/health.py`'s `socket.create_connection(...)` — a TCP reachability probe for the health endpoint (not model traffic), whose host/port are read from the same `ollama.base_url` the script's own layer-3 check verifies is loopback-locked. Passes clean on the current tree.

2. **Layer 5 — firewall scripts.** `scripts/configure_firewall_macos.sh` (`pf`/`pfctl` anchor, not Application Firewall/`socketfilterfw`) and `scripts/configure_firewall_windows.ps1` (`New-NetFirewallRule` outbound Block, relying on Windows' built-in loopback exemption). Both are idempotent, both have a read-only `--verify`/`-Verify` mode, both refuse to run their configure mode without elevated privileges. **Not executed in configure mode** — see "What was deliberately not done" below. `--verify` mode was smoke-tested (see Entry 1 continued).

3. **Layer 6 — `backend/utils/socket_guard.py`.** Monkeypatches `socket.socket.connect`/`connect_ex` at process startup to reject any non-loopback `connect()` from the backend process, emitting an `error` audit event (`component: socket_guard`) on a block. Wired into `backend/main.py`'s lifespan, installed before `network_monitor.start()` so no code path in the process can open a socket before the guard is live. Loopback (127.0.0.0/8, `::1`, and the literal hostname `localhost`) always passes through unmodified.

4. **Layer 8 — `scripts/audit_egress_report.py`.** Retroactive proof CLI (no new API endpoint, no new event type — locked finalisation decision, Task 18 §11). Queries `audit_events` directly (optionally filtered by `--since` / `--job-id`), counts `model_invoked`/`tool_invoked` events, and reports `"0 external connections across N model/tool invocations"` unless a `network_check` event flagged `external_connections_detected: true` or a `socket_guard` block was recorded — either of which is treated as a real finding (exit code 1), not just a reporting failure.

**Tests added:**

- `backend/tests/test_zero_egress.py` (14 tests): layer 1 (passes on current tree; a deliberately-planted `httpx.get(...)` outside `runtime.py` makes it fail, then is removed); layer 4 (promotes `test_sandbox.py::TestNetworkDenial` into this suite via inheritance — ran for real against the actual Docker daemon and `bulwark-sandbox:latest` image, both available in this environment); layer 6 (loopback always passes even with the guard installed against a real listening socket; non-loopback `connect()`/`connect_ex()` both raise `EgressBlockedError`; install/uninstall idempotency); the production monitor (a real `_check_once()` emits exactly one `network_check` row with `job_id IS NULL`, correct payload keys; `get_status()` shape); the audit report (`build_report`/`format_report` against fixture event lists — clean case, an `external_connections_detected: true` case, and a `socket_guard` block case).
- `backend/tests/test_security.py` (6 tests): every real registered capability declares `network_access: false`; the Policy engine denies a fixture capability with `network_access: true` and denies when `policy.yaml`'s `network_access_allowed` is tampered to `true`; the *actual committed* `config/policy.yaml` has the invariant at `false`; `settings.app.ollama.base_url` resolves to loopback; a grep of every `config/*.yaml` for API-key-shaped keys or non-loopback URLs finds none.

**How to verify:**

```bash
python scripts/check_no_egress.py
cd backend && PYTHONPATH=.. .venv/bin/python -m pytest tests/test_zero_egress.py tests/test_security.py -v
```

Result: `check_no_egress.py` exits 0; both test files pass in full — 14/14 and 6/6.

Full backend suite (`pytest tests/ -q`): **545 passed, 5 failed, 1 skipped**. The 5 failures are all in `test_model_runtime.py`'s `TestGenerateIntegration`/`TestEmbedIntegration` classes and require a live Ollama; Ollama was stopped at the start of this session per Aditya's own request in the prior turn, and restarting it was out of scope for this task. Confirmed pre-existing/unrelated: none of the 5 touch any file this task changed, and `TestStaticCheck::test_only_runtime_imports_httpx_for_model` (Task 8's own static-check test) initially broke when `socket_guard.py`'s docstring happened to mention the string `"11434"` — fixed by rewording the comment; unrelated to the Ollama-down failures.

**`--verify` mode smoke test (macOS, no sudo, no state change):**

```
$ bash scripts/configure_firewall_macos.sh --verify
Verifying outbound-block-except-loopback for backend port 8000...
  [warn] loopback (Ollama :11434) not reachable — Ollama may not be running; this is not a firewall failure
  [FAIL] outbound to a public host succeeded — the firewall rule is not active or not effective
exit: 1
```

This is the **expected** result — the pf anchor was never loaded (configure mode was not run), so outbound traffic correctly still succeeds and `--verify` correctly reports FAIL. It confirms the verify logic itself works (it can tell blocked from unblocked); it is not evidence the firewall is configured.

## What was deliberately not done, and why

Per the operating rules for this session (confirm before hard-to-reverse or system-affecting actions), the following §7/§9 items were **not** performed autonomously:

- **Firewall configure mode** (`scripts/configure_firewall_macos.sh` with no flags, requires `sudo`; `configure_firewall_windows.ps1`, requires Administrator). This edits real OS packet-filter / firewall state on the machine. The task file itself calls the exact anchor/rule syntax an implementation detail that "must be authored and hand-verified on the actual M4 Pro and an actual Windows machine" — not something to apply blind. **Needs Aditya to run this once, deliberately, on the actual reference machine(s), well before demo day**, then re-run `--verify` to confirm it stuck.
- **The 13-step offline validation procedure** (§7 Requirement 9): step 6 is "disconnect external networking" — this would cut off Aditya's own internet on his machine. That is not a git/code action and not something to do without him present and aware. **This is the single largest remaining gap against Task 18's acceptance criteria** and needs to be run with Aditya at the machine: verify local models/OCR weights/sandbox image/deps are all already present → configure + verify the firewall (previous bullet) → disconnect networking → start Ollama/backend/frontend → run one pass of each of the four workflows through the real UI → confirm `GET /api/v1/network-status` stays clean and `scripts/audit_egress_report.py` reports "0 external connections" → reconnect.
- Windows-side layer 4/5 validation — no Windows host available in this environment (`docs/project-context.md` already notes Windows is secondary hardware); the Windows script is authored to the same locked mechanism as macOS but has not been syntax-checked (no `pwsh` available here) or run anywhere.

## Acceptance checklist (tasks/18-security-zero-egress.md §9)

- [x] Layer 1: `scripts/check_no_egress.py` passes; verified in-suite.
- [x] Layer 2: every Registry capability declares `network_access: false`; Policy denies deviation; no knob exists.
- [x] Layer 3: Model Runtime resolves only to loopback; no external endpoint/API key in `config/*.yaml`.
- [x] Layer 4: outbound call inside the sandbox fails under `--network none` (tested on macOS with the real Docker daemon; Windows not available).
- [~] Layer 5: scripts exist, are idempotent, have a verify mode, are documented as one-time/never-live — **not yet executed on the reference machine(s)**.
- [x] Layer 6: socket guard rejects non-loopback `connect()`, allows loopback, wired at startup, documented as last-resort.
- [x] `network_monitor` runs continuously, emits `network_check` independent of Jobs, backs `GET /api/v1/network-status`.
- [x] `scripts/audit_egress_report.py` produces the retroactive "0 external connections across N invocations" report.
- [ ] **Offline validation procedure (all 13 steps) — not yet run.** Needs Aditya present (disconnects real networking).
- [ ] `docs/deployment.md` "SIH demo preparation checklist" — not yet completed (depends on the offline run above).
- [x] `docs/testing.md` "Security tests" and "Zero-egress tests" pass (20/20 across the two new test files).
- [x] No enterprise air-gap tooling built; no layer presented as sufficient alone; firewall not adjusted live.
- [ ] `git diff` reviewed; branch pushed; PR prepared — pending final review pass.

## Open items for Aditya

1. Run `scripts/configure_firewall_macos.sh` (sudo) on the actual M4 Pro once, then `--verify` to confirm.
2. Pick a time to actually disconnect networking and run the 13-step procedure (§7 Req 9) end-to-end — I can drive the workflow runs and read `scripts/audit_egress_report.py`'s output live if you're there for the network toggle and firewall step.
3. If a Windows machine becomes available, run `configure_firewall_windows.ps1` and repeat the sandbox network-denial check there.
