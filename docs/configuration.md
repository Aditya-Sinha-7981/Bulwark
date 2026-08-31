# Configuration

## Principle

Centralized, file-based, no secrets in the SIH runtime — there are no external API keys anywhere in this system, since every model/tool is local. Configuration files live under `config/`, loaded once at backend startup (`backend.md`).

## `config/resources.yaml` — Resource/Model Configuration Registry

Authoritative content and behavior defined in `models.md`. Reproduced here for completeness of the configuration file inventory:

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
    keep_alive: "-1"
```

## `config/capabilities.yaml` — Capability configuration

Machine-readable form of `capabilities.md`'s contracts — timeouts, resource limits, per-capability toggles:

```yaml
capabilities:
  extract_document:
    enabled: true
    timeout_seconds: 120
    max_file_size_mb: 10

  search_knowledge_base:
    enabled: true
    timeout_seconds: 10
    default_top_k: 5

  generate_code:
    enabled: true
    timeout_seconds: 30

  execute_code:
    enabled: true
    timeout_seconds: 30
    cpu_limit: 1
    memory_limit_mb: 512
    max_output_bytes: 65536

  create_docx:
    enabled: true
    timeout_seconds: 15

  create_xlsx:
    enabled: true
    timeout_seconds: 15
```

## `config/policy.yaml` — Policy configuration

```yaml
policy:
  network_access_allowed: false   # invariant — never set true
  max_job_steps: 8
  malformed_output_free_retries: 1
```

## `config/app.yaml` — general application settings

```yaml
app:
  host: 127.0.0.1
  port: 8000
  cors_origins: ["http://localhost:5173"]

paths:
  data_root: ./data
  uploads: ./data/uploads
  extraction: ./data/extraction
  artifacts: ./data/artifacts
  sandbox: ./data/sandbox
  tmp: ./data/tmp
  db: ./data/db/app.db
  chroma: ./data/chroma

ocr:
  escalation_thresholds:
    mean_confidence_below: 0.75
    completeness_below: 0.6
    handwriting_detected: true
    layout_complexity_flag: true
```

## Distinguishing configuration from secrets

There are currently no secrets in this system — no API keys, no external credentials. `.env.example` exists as a documented pattern for the (currently empty) case where a local credential might someday be needed, and is explicitly excluded from version control (`.gitignore`). Do not add a cloud service credential to any `config/*.yaml` file — if a task seems to require one, stop, since it likely violates the zero-egress requirement (`security.md`) rather than needing a config entry.

## Environment-specific overrides

None required for SIH — the same `config/*.yaml` files are used on the M4 Pro reference deployment and every development machine. Ollama transparently selects its Metal or CUDA backend per machine; nothing in these files needs to differ by platform.
