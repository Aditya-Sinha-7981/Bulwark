# Deployment (Local, macOS + Windows)

## Scope

Single-workstation local deployment only — no server/cloud deployment target exists for this project (`requirements.md`, deferred scope).

## Prerequisites (both platforms)

- Python 3.11+
- Node.js 20+
- Docker Desktop (latest stable)
- Ollama (latest stable, 0.32.x line or newer)
- Git

## macOS-specific (reference/demo machine)

- Confirm macOS version supports the intended Ollama MLX backend (recent macOS releases on Apple Silicon — verify against Ollama's current release notes if a specific minimum isn't already known).
- No Apple `container` dependency — Docker Desktop only (ADR-05).

## Windows-specific (development machines)

- Docker Desktop with WSL2 backend enabled.
- Ollama's Windows build, using its CUDA backend where an NVIDIA GPU is present (team's 6GB-VRAM-class laptops — see `project-context.md` for team hardware).

## First-time provisioning (requires internet — the only phase that does)

1. Clone the repository.
2. `cd backend && pip install -r requirements.txt`
3. `cd frontend && npm install`
4. Install and start Ollama; pull every model in `config/resources.yaml`:
   ```
   ollama pull qwen3.5:9b
   ollama pull qwen2.5-coder:7b
   ollama pull qwen3-embedding:0.6b
   ```
5. Install PaddleOCR and its model weights (`pip install paddleocr`, first-run weight download).
6. Build the sandbox image once: `docker build -t aegis-sandbox:latest ./sandbox`
7. Initialize the SQLite database (schema migration script, run once).
8. Configure the OS firewall rule scoping the backend process to loopback (`security.md`) — a one-time setup step, documented per-platform in the repository's setup script, never done live.

## Startup

```
# terminal 1
ollama serve

# terminal 2
cd backend && uvicorn main:app --host 127.0.0.1 --port 8000

# terminal 3
cd frontend && npm run dev
```

Docker Desktop must be running (its own background process) before any `execute_code` capability call.

## Shutdown

Stop the three processes above (Ctrl+C); Docker Desktop can remain running or be quit independently — no special shutdown sequence required, since Jobs/Artifacts/Audit events are all persisted to SQLite as they occur, not buffered in memory.

## Health checks

`GET /api/v1/health` (`api.md`) — checks backend, database, Ollama reachability, Docker reachability. Run this after startup, before beginning any demo or dev session, to catch a missing prerequisite early.

## Directories

See `config/app.yaml`'s `paths` section (`configuration.md`) for the canonical layout: `data/uploads/`, `data/extraction/`, `data/artifacts/`, `data/sandbox/`, `data/tmp/`, `data/db/`, `data/chroma/`. All created automatically on first startup if missing.

## Logs

Application logs to stdout (captured by the terminal running `uvicorn`) — no separate log file infrastructure for SIH scope. Everything of actual audit/debugging value is in the `audit_events` table (`audit.md`), which is the primary place to look when something needs investigating, not the stdout log.

## Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| `GET /api/v1/health` shows `model_runtime: unavailable` | Ollama not running | `ollama serve` in a terminal |
| `execute_code` fails immediately | Docker Desktop not running | Start Docker Desktop, retry |
| Model load is very slow | First load of a large model, or memory pressure | Check `resource_loaded` audit events for duration; check memory pressure per `models.md`'s budget |
| Retrieval always returns empty | Knowledge base not yet seeded | Check `GET /api/v1/knowledge-base` for `ready` documents |

## Offline operation

After the provisioning steps above, disconnect from the network entirely and re-run the full startup sequence plus a representative request through each of the four demo workflows (`demo.md`). This is an explicit, required validation step before SIH itself — not an assumption that offline operation works because the architecture says it should.

## SIH demo preparation checklist

- [ ] All models pulled and verified loadable (`ollama list`)
- [ ] Sandbox image built and a test `execute_code` run verified
- [ ] Knowledge base seeded with synthetic SOP documents, `ready` status confirmed
- [ ] OS firewall rule configured and tested (with WiFi on, confirm no external calls occur; then with WiFi off, confirm the app still runs)
- [ ] Full offline run of all four demo workflows completed successfully
- [ ] `GET /api/v1/network-status` confirmed showing zero external connections throughout a full demo run
