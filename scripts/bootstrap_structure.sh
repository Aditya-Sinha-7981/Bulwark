#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/bootstrap_structure.sh
#
# One-time repository skeleton bootstrap for Bulwark.
#
# Creates the directory layout and EMPTY placeholder files described by:
#   - README.md               "Repository layout"
#   - docs/backend.md          "Proposed project structure"
#   - docs/frontend.md         "Page/layout structure"
#   - docs/configuration.md    config/*.yaml inventory
#
# Rules this script follows:
#   - Idempotent. Safe to re-run. `mkdir -p` for directories; existing files are
#     never overwritten or truncated (only missing files are created).
#   - Writes NO implementation code, NO capability logic, NO config values.
#     Every file it creates is a zero-byte placeholder for a later workstream.
#   - Does NOT pre-create per-feature logs (logs/<feature>.md) — those are
#     created per-workstream on first commit, per AGENTS.md §4.2.
#   - Sandbox image build context is ./sandbox (per README.md Quickstart and
#     docs/deployment.md step 6: `docker build -t bulwark-sandbox:latest ./sandbox`).
#     ./docker is created empty because README.md's layout lists it.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

created=0
skipped=0

mkdir_p() {
  mkdir -p "$1"
}

# Create an empty placeholder file only if it does not already exist.
touch_new() {
  local path="$1"
  mkdir -p "$(dirname "$path")"
  if [ -e "$path" ]; then
    printf '  =   %s\n' "$path"
    skipped=$((skipped + 1))
  else
    : > "$path"
    printf '  +   %s\n' "$path"
    created=$((created + 1))
  fi
}

echo "Bulwark repo skeleton bootstrap"
echo "repo root: $REPO_ROOT"
echo

# ── backend/ (docs/backend.md) ──────────────────────────────────────────────
echo "backend/"
touch_new backend/main.py
touch_new backend/config.py
touch_new backend/requirements.txt
touch_new backend/.env.example

touch_new backend/api/conversations.py
touch_new backend/api/jobs.py
touch_new backend/api/documents.py
touch_new backend/api/artifacts.py
touch_new backend/api/knowledge_base.py
touch_new backend/api/health.py

touch_new backend/domain/orchestrator/agent.py
touch_new backend/domain/orchestrator/prompt_builder.py
touch_new backend/domain/orchestrator/proposal_parser.py

touch_new backend/domain/policy/engine.py

touch_new backend/domain/job_manager/manager.py

touch_new backend/domain/capabilities/registry.py
touch_new backend/domain/capabilities/extract_document.py
touch_new backend/domain/capabilities/search_knowledge_base.py
touch_new backend/domain/capabilities/generate_code.py
touch_new backend/domain/capabilities/execute_code.py
touch_new backend/domain/capabilities/create_docx.py
touch_new backend/domain/capabilities/create_xlsx.py

touch_new backend/domain/model_runtime/runtime.py
touch_new backend/domain/model_runtime/lifecycle_manager.py

touch_new backend/domain/rag/ingestion.py
touch_new backend/domain/rag/retrieval.py

touch_new backend/domain/document_processing/ocr.py
touch_new backend/domain/document_processing/vision_escalation.py
touch_new backend/domain/document_processing/pipeline.py

touch_new backend/domain/sandbox/docker_executor.py

touch_new backend/domain/artifacts/docx_renderer.py
touch_new backend/domain/artifacts/xlsx_renderer.py

touch_new backend/domain/audit/events.py

touch_new backend/repositories/conversations.py
touch_new backend/repositories/jobs.py
touch_new backend/repositories/documents.py
touch_new backend/repositories/artifacts.py
touch_new backend/repositories/audit_events.py
touch_new backend/repositories/knowledge_base.py

touch_new backend/models/schemas.py

touch_new backend/utils/ids.py
touch_new backend/utils/paths.py
echo

# ── frontend/ (docs/frontend.md) ────────────────────────────────────────────
echo "frontend/"
touch_new frontend/package.json
touch_new frontend/vite.config.js

touch_new frontend/src/App.jsx
touch_new frontend/src/main.jsx

touch_new frontend/src/pages/Workbench.jsx

touch_new frontend/src/components/ChatPanel.jsx
touch_new frontend/src/components/JobTracePanel.jsx
touch_new frontend/src/components/CapabilityActivity.jsx
touch_new frontend/src/components/ArtifactPanel.jsx
touch_new frontend/src/components/RagEvidencePanel.jsx
touch_new frontend/src/components/SovereigntyIndicator.jsx
touch_new frontend/src/components/UploadButton.jsx
touch_new frontend/src/components/ErrorBanner.jsx

touch_new frontend/src/hooks/useJobEvents.js
touch_new frontend/src/hooks/useApi.js

touch_new frontend/src/services/api.js
echo

# ── config/ (docs/configuration.md) — empty; values filled by a later pass ──
echo "config/"
touch_new config/resources.yaml
touch_new config/capabilities.yaml
touch_new config/policy.yaml
touch_new config/app.yaml
echo

# ── docker/ — empty; README.md's layout lists it. Sandbox image lives in ./sandbox.
echo "docker/"
touch_new docker/.gitkeep
echo

# ── sandbox/ — build context for `docker build -t bulwark-sandbox:latest ./sandbox`
echo "sandbox/"
touch_new sandbox/Dockerfile
echo

# ── data/ — gitignored (/data/ in .gitignore). .gitkeep marks each subdir
#    locally; these are auto-created on first backend startup (docs/deployment.md).
echo "data/  (gitignored — .gitkeep files are local-only unless force-added)"
touch_new data/uploads/.gitkeep
touch_new data/extraction/.gitkeep
touch_new data/artifacts/.gitkeep
touch_new data/sandbox/.gitkeep
touch_new data/tmp/.gitkeep
touch_new data/db/.gitkeep
touch_new data/chroma/.gitkeep
echo

# ── logs/ — tracked. One .gitkeep only. Per-feature logs are NOT pre-created
#    (AGENTS.md §4.2: created per-workstream on first commit).
echo "logs/"
touch_new logs/.gitkeep
echo

# ── tasks/ — gitignored (/tasks/ in .gitignore). Directory only; stays empty.
echo "tasks/"
mkdir_p tasks
printf '  dir %s\n' "tasks/"
echo

echo "done.  created: $created   already-present: $skipped"
