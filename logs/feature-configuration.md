# logs/feature-configuration.md

> Feature / workstream: `configuration`  (branches: `feature/configuration`)
> Started: 2026-09-05 by Claude Sonnet 5 (Claude Code)
> Status: completed

## Goal

Implement Task 2 (`tasks/2-configuration-loading.md`, implementation-plan.md
Stage 2): populate the four `config/*.yaml` files with the exact contents
from `docs/configuration.md`, load and validate them into typed Pydantic
models at backend startup, and expose one frozen `settings` object with
typed accessors so no module in `backend/` hardcodes a path, port, model
name, timeout, or policy limit. This is Aditya's ownership chain
(`members/aditya.md`) step 2 of 8, directly following Task 1.a
(`logs/feature-backend-bootstrap.md`).

## Plan

1. Populate `config/resources.yaml`, `config/capabilities.yaml`,
   `config/policy.yaml`, `config/app.yaml` verbatim from `docs/configuration.md`.
2. Typed models in `backend/models/schemas.py`: one Pydantic model per file
   (`ResourcesFile`, `CapabilitiesFile`, `PolicyFile`, `AppFile`), plus a
   flattened `AppConfig` for the exposed `settings.app` surface.
3. Rewrite `backend/config.py`: `yaml.safe_load` each file, deep-merge an
   optional `config/<name>.local.yaml`, validate, expose frozen `settings`.
4. `backend/utils/paths.py`: scoped path helpers under `settings.app.paths`.
5. Rewire `backend/main.py` off the Task 1.a stub constants.
6. `backend/tests/test_config.py` + `scripts/check_no_hardcoded_models.py`.

## Entries

### Entry 1 — 2026-09-05 00:00 — Configuration loader implemented and verified

**What changed:**

- `config/resources.yaml`, `config/capabilities.yaml`, `config/policy.yaml`,
  `config/app.yaml` — populated with the exact contents from
  `docs/configuration.md` (previously 0-byte placeholders).
- `backend/models/schemas.py` (new content; file existed empty) — `StrictModel`
  base (`extra="forbid", frozen=True`); `ResourceEntry`/`ResourcesConfig`/`ResourcesFile`
  with `ResourcesConfig.for_type(resource_type)`; per-capability models
  (`ExtractDocumentConfig`, `SearchKnowledgeBaseConfig`, `GenerateCodeConfig`,
  `ExecuteCodeConfig`, `CreateDocxConfig`, `CreateXlsxConfig`) composed into
  `CapabilitiesConfig`/`CapabilitiesFile`; `PolicyConfig` (raises via
  `field_validator` if `network_access_allowed` is `True`) /`PolicyFile`;
  `AppSection`/`PathsSection`/`OcrEscalationThresholds`/`OcrSection`/
  `OllamaSection` (rejects a non-loopback `base_url` host via
  `urllib.parse.urlparse` + allowlist `{"localhost", "127.0.0.1"}`)/`AppFile`;
  and `AppConfig` — a **flattened** model (`host`, `port`, `cors_origins`,
  `paths`, `ocr`, `ollama`) built by the loader from `AppFile`, since the task
  spec requires both `settings.app.host` and `settings.app.paths.db` on the
  same object, but the YAML nests `host`/`port`/`cors_origins` under a
  sibling `app:` key — flattening avoids `settings.app.app.host`.
- `backend/config.py` (rewritten; was the Task 1.a stub) — `_load_yaml`,
  `_deep_merge` (mappings merge recursively, lists replace — locked
  semantics, task §7 Requirement 3), `_load_and_validate` (per-file: load
  base, warn on unrecognized top-level keys via stderr, merge
  `config/<name>.local.yaml` if present, validate, `SystemExit(1)` with a
  file-naming message on any failure), `Settings` (frozen via `__slots__` +
  overridden `__setattr__`), `load_settings()`, module-level `settings =
  load_settings()`. `REPO_ROOT`/`CONFIG_DIR` module constants (previously
  `REPO_ROOT`/`DATA_ROOT`/`DATA_SUBDIRS`/`HOST`/`PORT`/`CORS_ALLOW_ORIGINS`
  — all removed, replaced by `settings.app.*`).
- `backend/utils/paths.py` (new content; file existed empty) —
  `_resolve_root` (relative `config/app.yaml` paths → absolute under
  `REPO_ROOT`), module constants (`DATA_ROOT`, `UPLOADS_ROOT`,
  `EXTRACTION_ROOT`, `ARTIFACTS_ROOT`, `SANDBOX_ROOT`, `TMP_ROOT`, `DB_FILE`,
  `CHROMA_ROOT`), `_reject_unsafe` (rejects an absolute path component or a
  `..` segment), `uploads_path`, `extraction_path`, `artifacts_path`,
  `sandbox_dir`, `db_path`, `chroma_dir`, `tmp_dir`, and
  `all_managed_dirs()` — the startup directory-creation list (replaces the
  Task 1.a `DATA_SUBDIRS` constant).
- `backend/main.py:7-9,29-34` — imports `settings` instead of
  `CORS_ALLOW_ORIGINS`/`DATA_SUBDIRS`; `create_data_directories()` iterates
  `all_managed_dirs()`; CORS middleware reads `settings.app.cors_origins`;
  added `if __name__ == "__main__": uvicorn.run(app, host=settings.app.host,
  port=settings.app.port)` so `settings.app.host`/`.port` are actually
  consumed somewhere (previously unused — uvicorn was always invoked via the
  CLI in Task 1.a's verification).
- `backend/tests/test_config.py` (new) — 11 tests: all-four-load +
  documented-value assertions, frozen-settings check, three local-override
  merge tests (`network_access_allowed: true` → `SystemExit`; `port`
  override wins; `cors_origins` override **replaces** rather than
  concatenates — verified as an exact-list equality, not a superset check),
  missing-file / malformed-YAML / wrong-type-value → `SystemExit`,
  non-loopback `ollama.base_url` → `SystemExit`, path-helper composition
  under configured roots, path-helper rejection of an absolute/`..` input.
  Uses a `local_override` fixture that copies the tracked files into
  `tmp_path` and monkeypatches `config.CONFIG_DIR` so tests never touch the
  real `config/` directory.
- `scripts/check_no_hardcoded_models.py` (new) — loads model identifiers
  from `config/resources.yaml`, greps every `backend/**/*.py` line for each
  string, exits 1 and prints `file:line: found '<model>'` for the diff-
  named files listed at `docs/configuration.md`'s three model names
  (`qwen3.5:9b`, `qwen2.5-coder:7b`, `qwen3-embedding:0.6b`); exits 0
  otherwise. `ALLOWED_FILES` exempts `backend/config.py` (the only place
  model names may legitimately appear per ADR-08) and
  `backend/tests/test_config.py` (asserts the loader surfaces the
  documented values — a reference, not a hardcoded dependency).

**Why:** Implements `tasks/2-configuration-loading.md` exactly — this is
Task 2 of Aditya's owned chain (1.a → 2 → 10 → 15 → 17 → 18 → 19 → 20,
`members/aditya.md`), directly dependent on Task 1.a's `config.py` stub
(`logs/feature-backend-bootstrap.md` Entry 1) and required before Tasks
6/7/8/9/13/14 can consume a stable `settings` surface.

**How to verify:**

```bash
cd backend && source .venv/bin/activate
pytest tests/ -v                                     # 13 passed (2 from test_health.py, 11 new)
cd .. && backend/.venv/bin/python scripts/check_no_hardcoded_models.py   # exit 0
grep -rnE 'qwen[0-9]' backend/ --include='*.py'       # only backend/tests/test_config.py (see decision below)

cd backend
uvicorn main:app --host 127.0.0.1 --port 8000 &
curl http://127.0.0.1:8000/api/v1/health              # {"status":"ok",...}
kill %1

mv ../config/resources.yaml ../config/resources.yaml.bak
python -c "import config"                              # SystemExit; stderr: "fatal: config file not found: .../config/resources.yaml"
mv ../config/resources.yaml.bak ../config/resources.yaml

cat > ../config/resources.local.yaml <<'EOF'
resources:
  reasoning:
    model: test-model:1b
EOF
python -c "import config; print(config.settings.resources.for_type('reasoning').model)"  # test-model:1b
rm ../config/resources.local.yaml
```

All of the above were run and passed during this session.

**Open issues / known gaps:**

- The task's manual-verification step 4 literally reads `grep -rnE
  'qwen[0-9]' backend/ --include='*.py'` returns nothing outside
  `config.py`. In practice `backend/tests/test_config.py` also asserts the
  documented model-name values (to prove the loader surfaces them
  correctly) — a config-loader test has to assert against *some* real
  value. `scripts/check_no_hardcoded_models.py` explicitly allowlists this
  file for the same reason it allowlists `config.py`, so the automated
  check (the mechanism the acceptance criteria actually gate on) passes
  clean. Flagging this literal-vs-intent gap rather than silently
  reinterpreting the manual step.
- `backend/config.py`'s per-file loader prints unknown-top-level-key
  warnings to stderr (no audit/event pipeline exists yet — Task 3/12 own
  that). Per the task's "Error Handling" §7: "warn... surfaced as a
  startup log line via the eventual audit path / stderr for now" — stderr
  is the documented interim behavior, not a shortcut.
- `PathsSection` (and `AppConfig.paths`) store the raw relative strings
  from `config/app.yaml` (e.g. `"./data/uploads"`) unresolved —
  `backend/utils/paths.py` does the `REPO_ROOT`-relative resolution.
  Anything reading `settings.app.paths.uploads` directly (rather than
  through the `paths.py` helpers) gets a relative string, not an absolute
  path. Flagging since `docs/configuration.md` doesn't state which layer
  resolves this; the task's Requirement 4 makes `paths.py` responsible, so
  that's where I put it.

**Decisions made:**

- `settings.app` is **not** the raw `AppFile` (which would nest as
  `settings.app.app.host`) — it's a separate flattened `AppConfig` model the
  loader builds from `AppFile.app` + `AppFile.paths/ocr/ollama`. This
  satisfies the task's explicit examples (`settings.app` supplies
  `host`/`port`/`cors_origins`; `settings.app.paths.db` is the SQLite path)
  without inventing new config keys — `AppFile` still validates the YAML's
  actual on-disk shape one-to-one.
- `Settings` is frozen via `__slots__` + an overridden `__setattr__` that
  raises `AttributeError`, rather than a Pydantic model — it holds instances
  of four different Pydantic models as opaque attributes, not a
  YAML-shaped record itself, so a plain frozen container was simpler than
  wrapping it in another `BaseModel`.
- Local-override merge test fixture monkeypatches `config.CONFIG_DIR` to a
  `tmp_path` copy of the tracked files rather than writing real
  `config/*.local.yaml` files into the repo during tests — avoids any risk
  of a leftover local-override file surviving a failed test run and
  silently changing a later `import config` in the same test session or
  a developer's real environment.
- Added `if __name__ == "__main__": uvicorn.run(...)` to `main.py` using
  `settings.app.host`/`.port` — not in the original Task 1.a file. Task 2's
  acceptance criteria require `main.py` to read host/port from `settings`,
  but nothing in Task 1.a's implementation actually consumed those two
  values (uvicorn was always launched via CLI flags in that task's
  verification). Adding the block is the smallest change that makes
  `settings.app.host`/`.port` real, live-consumed configuration rather than
  dead accessors — the CLI-launch path (`uvicorn main:app --host ... --port
  ...`) still works unchanged and remains how the documented verification
  steps run it.

**Supersedes / references:** None — first entry for this workstream.
Builds directly on `logs/feature-backend-bootstrap.md` Entry 1 (Task 1.a),
which left the `config.py` stub and the `# TODO(Task 2)` marker this branch
resolves.

---

## Open questions for the user

None outstanding — both "Open Questions" in `tasks/2-configuration-loading.md`
§11 were already marked resolved in the task file itself (list-replace
merge semantics; Ollama connection settings as a config key) and this
implementation follows both resolutions as specified.

## Links

- PR: not yet opened (commit/push explicitly deferred to the human developer
  per `AGENTS.md` §7 — this session did not run `git add`/`commit`/`push`)
- Related branches / logs: `feature/configuration`;
  `logs/feature-backend-bootstrap.md` (Task 1.a, direct predecessor)
- Doc references: `tasks/2-configuration-loading.md`, `docs/configuration.md`,
  `docs/models.md`, `docs/backend.md`, `docs/decisions.md` (ADR-08),
  `docs/git-workflow.md`, `docs/security.md`, `AGENTS.md`, `members/aditya.md`

## Published `settings` surface (for Tasks 6/7/8/9/13/14)

```python
from config import settings

settings.resources.for_type("reasoning" | "code_generation" | "vision" | "embedding")
    .model / .runtime / .context_window / .keep_alive

settings.capabilities.extract_document / .search_knowledge_base / .generate_code
    / .execute_code / .create_docx / .create_xlsx
    .enabled / .timeout_seconds / (capability-specific fields per docs/configuration.md)

settings.policy.network_access_allowed / .max_job_steps / .malformed_output_free_retries

settings.app.host / .port / .cors_origins
settings.app.paths.data_root / .uploads / .extraction / .artifacts / .sandbox / .tmp / .db / .chroma
settings.app.ocr.escalation_thresholds.mean_confidence_below / .completeness_below
    / .handwriting_detected / .layout_complexity_flag
settings.app.ollama.base_url / .request_timeout_seconds
```

Path helpers (`from utils.paths import ...`) resolve everything above under
`REPO_ROOT`: `uploads_path(document_id, ext)`, `extraction_path(document_id)`,
`artifacts_path(artifact_id, ext)`, `sandbox_dir(execution_id)`, `db_path()`,
`chroma_dir()`, `tmp_dir()`, `all_managed_dirs()`.
