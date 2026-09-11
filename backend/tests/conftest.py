"""
Shared test fixtures (Task 15).

`isolated_db` — a fresh temp SQLite file with the full schema, wired into every
repository module's `get_connection` for the duration of a test.
`bulwark_client` — a `TestClient` over the real app on top of `isolated_db`,
with the Job Manager's model client faked (no Ollama) unless a test overrides it
via `manager.set_test_dependencies(...)`.

These are additive: existing test files keep their own local fixtures.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import scripts.init_db as init_db  # noqa: E402
from backend.repositories.db import get_connection  # noqa: E402

_REPO_MODULES = (
    "backend.repositories.db",
    "backend.repositories.jobs",
    "backend.repositories.conversations",
    "backend.repositories.artifacts",
    "backend.repositories.audit_events",
    "backend.repositories.documents",
    "backend.repositories.knowledge_base",
    "backend.repositories.resource_state",
)


@pytest.fixture
def isolated_db():
    """Fresh schema-initialised temp DB, patched into all repository modules."""
    import importlib

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    original_get_db_path = init_db.get_db_path
    init_db.get_db_path = lambda: db_path
    init_db.main()
    init_db.get_db_path = original_get_db_path

    patched = lambda *a, **k: get_connection(db_path)
    saved = {}
    for name in _REPO_MODULES:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError:
            continue
        if hasattr(mod, "get_connection"):
            saved[name] = mod.get_connection
            mod.get_connection = patched

    yield db_path

    for name, fn in saved.items():
        importlib.import_module(name).get_connection = fn
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def bulwark_client(isolated_db):
    from fastapi.testclient import TestClient

    from backend.domain.capabilities.registry import CapabilityRegistry
    from backend.domain.job_manager import manager
    from backend.models.schemas import GenerationResult

    caps_config = {
        "capabilities": {
            "extract_document": {"enabled": True, "timeout_seconds": 120, "max_file_size_mb": 10},
            "search_knowledge_base": {"enabled": True, "timeout_seconds": 10, "default_top_k": 5},
            "generate_code": {"enabled": True, "timeout_seconds": 30},
            "execute_code": {"enabled": True, "timeout_seconds": 30, "cpu_limit": 1, "memory_limit_mb": 512, "max_output_bytes": 65536},
            "create_docx": {"enabled": True, "timeout_seconds": 15},
            "create_xlsx": {"enabled": True, "timeout_seconds": 15},
        }
    }

    class _DefaultFake:
        async def generate(self, resource_type, prompt, *, images=None, options=None):
            return GenerationResult(
                text=json.dumps({"action": "respond", "content": "ok"}),
                prompt_tokens=1,
                completion_tokens=1,
                duration_ms=1,
            )

    manager.set_test_dependencies(
        model_client=_DefaultFake(),
        registry=CapabilityRegistry(caps_config),
        capabilities_config=caps_config,
    )

    from backend.main import app

    with TestClient(app) as client:
        client.caps_config = caps_config  # type: ignore[attr-defined]
        yield client

    manager.reset_test_dependencies()
