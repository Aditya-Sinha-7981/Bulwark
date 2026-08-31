# Models & Resource Configuration

## Locked model stack

| Role | Resource type | Model | Runtime | Context window | Quantization |
|---|---|---|---|---|---|
| Orchestrator/reasoning | `reasoning` | `qwen3.5:9b` (default; benchmark validation in progress vs. `gpt-oss:20b`, see `testing.md`) | Ollama | 128,000 (as configured) | Q4_K_M |
| Coding | `code_generation` | `qwen2.5-coder:7b` | Ollama | 32,768 | Q4_K_M |
| Vision (fallback only) | `vision` | `qwen3.5:9b` (same model as reasoning) | Ollama | 256,000 | Q4_K_M |
| Embedding | `embedding` | `qwen3-embedding:0.6b` | Ollama | n/a | default |

**Note:** reasoning and vision share the same underlying model (`qwen3.5:9b`) in the current configuration — one loaded instance can serve both resource types, which is a memory-efficiency property of this specific configuration, not an architectural requirement. If the reasoning model is later changed to something without vision capability, `vision` resolves independently per its own registry entry.

## Resource/Model Configuration Registry

`config/resources.yaml` — the single file that maps resource types to concrete configuration:

```yaml
resources:
  reasoning:
    model: qwen3.5:9b
    runtime: ollama
    context_window: 128000
    keep_alive: "5m"

  code_generation:
    model: qwen2.5-coder:7b
    runtime: ollama
    context_window: 32768
    keep_alive: "5m"

  vision:
    model: qwen3.5:9b
    runtime: ollama
    context_window: 256000
    keep_alive: "5m"

  embedding:
    model: qwen3-embedding:0.6b
    runtime: ollama
    keep_alive: "-1"   # always resident
```

Application code never references a model name — only a resource type (`resources.reasoning`, etc.). Changing `reasoning.model` from `qwen3.5:9b` to another Ollama-compatible model, once that model is pulled locally, requires **no changes** to the Orchestrator, Executors, capabilities, API, frontend, or RAG code — this is a hard implementation requirement, not an aspiration (see ADR-08, `decisions.md`).

## Model Runtime

Ollama, resolved via its local HTTP API (`http://localhost:11434` by default). The Model Runtime module in the backend is the only code that talks to this API directly — Executors call the Model Runtime module, never Ollama's API directly, keeping the runtime genuinely swappable if it's ever replaced.

## Resource/Model Lifecycle Manager

Sits behind the Model Runtime. Responsibilities:

- **Resolving a request:** given a `resource_type`, look up its configured model in the Registry; if already loaded, serve it; if not, trigger a load.
- **Loading:** calls Ollama to load the model, with the configured `keep_alive`. Fires a `resource_loaded` audit event on completion, including load duration.
- **Keep-alive:** each resource type's `keep_alive` (above) controls how long an idle model stays resident before Ollama unloads it automatically. `embedding` is always resident (`-1`) since RAG needs it on essentially every retrieval call; `reasoning`, `code_generation`, and `vision` use a 5-minute idle window by default.
- **Eviction under memory pressure:** if a load is requested and the Lifecycle Manager detects insufficient headroom (see memory budget below), it proactively unloads the least-recently-used *non-reasoning* resource before attempting the new load. The `reasoning` resource is evicted last, only if no other option exists — it's the resource in near-continuous use across a Job.
- **Failure recovery:** a load failure (timeout, Ollama unavailable) is returned to the calling Executor as a failed result, `error` audit event fired — never a silent hang. The Job continues with that step marked failed; it is not a fatal Job-level crash.
- **Audit events:** `resource_loaded`, `resource_unloaded` for every lifecycle transition, always including `resource_type`, `model_identifier`, and duration where applicable.

## Memory budget (M4 Pro, 24GB unified memory)

| Component | Approx. footprint |
|---|---|
| macOS + realistic background usage (browser, editor, etc.) | ~3–4GB |
| Backend + frontend dev server | ~0.5–1GB |
| SQLite + Chroma (demo-scale corpus) | ~0.5GB |
| Docker Desktop (idle background VM) | ~1–2GB |
| `embedding` (always resident) | ~1.5GB |
| `reasoning`/`vision` (`qwen3.5:9b`, shared) | ~6.6GB |
| `code_generation` (`qwen2.5-coder:7b`), if concurrently loaded | ~5GB |

Reasoning+embedding alone: ~9GB — comfortable. Reasoning+coding+embedding concurrently: ~14GB — comfortable, well within budget (this configuration, using `qwen3.5:9b` rather than the larger `gpt-oss:20b` candidate, specifically buys back the headroom that made concurrent-loading tight in the earlier candidate evaluation — see `testing.md` for the full comparison). This is validated empirically, not just estimated — see the memory-test procedure in `testing.md`.

## Fallbacks

| Resource | Primary | Fallback | Trigger |
|---|---|---|---|
| `reasoning` | `qwen3.5:9b` | `gpt-oss:20b` | Benchmark (`testing.md`) shows a meaningful reliability deficit on actual SIH workflows |
| `reasoning` (secondary fallback) | — | `qwen3:14b` | Both primary candidates fail thresholds |
| `code_generation` | `qwen2.5-coder:7b` | `qwen3.5:4b` (smaller footprint, more headroom) | Memory pressure under real testing |
| `vision` | `qwen3.5:9b` | `qwen2-vl:7b` | Packaging/tool-calling issues found in testing |
| `embedding` | `qwen3-embedding:0.6b` | `nomic-embed-text` | Negligible retrieval-quality difference found, memory reclaim desired |

## Usage summary by capability

See `capabilities.md` for the authoritative mapping of which capability uses which `resource_type`. This file defines *what* each resource type resolves to; `capabilities.md` defines *which capability needs which resource type*. Do not duplicate that mapping here.
