import pathlib

import pytest
import yaml
from pydantic import ValidationError

import config as config_module
from config import CONFIG_DIR, Settings, load_settings, settings
from utils import paths as paths_module


# ---------------------------------------------------------------------------
# Loaded settings, typed accessors
# ---------------------------------------------------------------------------


def test_all_four_files_load_and_validate():
    assert settings.resources.for_type("reasoning").model == "qwen3.5:9b"
    assert settings.resources.for_type("code_generation").model == "qwen2.5-coder:7b"
    assert settings.resources.for_type("vision").model == "qwen3.5:9b"
    assert settings.resources.for_type("embedding").model == "qwen3-embedding:0.6b"
    assert settings.resources.for_type("embedding").keep_alive == "-1"

    assert settings.capabilities.extract_document.max_file_size_mb == 10
    assert settings.capabilities.search_knowledge_base.default_top_k == 5
    assert settings.capabilities.execute_code.cpu_limit == 1
    assert settings.capabilities.execute_code.memory_limit_mb == 512
    assert settings.capabilities.execute_code.max_output_bytes == 65536

    assert settings.policy.network_access_allowed is False
    assert settings.policy.max_job_steps == 8
    assert settings.policy.malformed_output_free_retries == 1

    assert settings.app.host == "127.0.0.1"
    assert settings.app.port == 8000
    assert settings.app.cors_origins == ["http://localhost:5173"]
    assert settings.app.ollama.base_url == "http://localhost:11434"
    assert settings.app.ollama.request_timeout_seconds == 120


def test_settings_is_frozen():
    with pytest.raises(AttributeError):
        settings.policy = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Local override merge semantics
# ---------------------------------------------------------------------------


@pytest.fixture
def local_override(tmp_path, monkeypatch):
    """Point CONFIG_DIR at a temp dir seeded with copies of the real tracked files."""
    tmp_config = tmp_path / "config"
    tmp_config.mkdir()
    for name in ("resources.yaml", "capabilities.yaml", "policy.yaml", "app.yaml"):
        (tmp_config / name).write_text((CONFIG_DIR / name).read_text())
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_config)
    return tmp_config


def test_local_policy_override_network_access_true_raises(local_override):
    (local_override / "policy.local.yaml").write_text(
        yaml.safe_dump({"policy": {"network_access_allowed": True}})
    )
    with pytest.raises(SystemExit):
        load_settings()


def test_local_app_override_port_wins(local_override):
    (local_override / "app.local.yaml").write_text(
        yaml.safe_dump({"app": {"port": 9999}})
    )
    result = load_settings()
    assert result.app.port == 9999
    assert result.app.host == "127.0.0.1"  # untouched key still merges from base


def test_local_app_override_cors_origins_is_replaced_not_concatenated(local_override):
    (local_override / "app.local.yaml").write_text(
        yaml.safe_dump({"app": {"cors_origins": ["http://localhost:3000"]}})
    )
    result = load_settings()
    assert result.app.cors_origins == ["http://localhost:3000"]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_missing_file_fails_fast(local_override):
    (local_override / "app.yaml").unlink()
    with pytest.raises(SystemExit):
        load_settings()


def test_malformed_yaml_fails_fast(local_override):
    (local_override / "policy.yaml").write_text("policy: [this is not: a mapping")
    with pytest.raises(SystemExit):
        load_settings()


def test_wrong_type_fails_fast(local_override):
    (local_override / "policy.yaml").write_text(
        yaml.safe_dump({"policy": {"network_access_allowed": False, "max_job_steps": "eight", "malformed_output_free_retries": 1}})
    )
    with pytest.raises(SystemExit):
        load_settings()


def test_non_loopback_ollama_base_url_rejected(local_override):
    (local_override / "app.local.yaml").write_text(
        yaml.safe_dump({"ollama": {"base_url": "http://example.com:11434"}})
    )
    with pytest.raises(SystemExit):
        load_settings()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def test_path_helpers_compose_under_configured_roots():
    assert paths_module.UPLOADS_ROOT in paths_module.uploads_path("doc-1", ".pdf").parents
    assert paths_module.EXTRACTION_ROOT in paths_module.extraction_path("doc-1").parents
    assert paths_module.ARTIFACTS_ROOT in paths_module.artifacts_path("art-1", ".docx").parents
    assert paths_module.SANDBOX_ROOT in paths_module.sandbox_dir("exec-1").parents
    assert paths_module.db_path() == paths_module.DB_FILE
    assert paths_module.chroma_dir() == paths_module.CHROMA_ROOT
    assert paths_module.tmp_dir() == paths_module.TMP_ROOT


def test_path_helpers_reject_absolute_input():
    with pytest.raises(ValueError):
        paths_module.uploads_path("/etc/passwd", ".pdf")
    with pytest.raises(ValueError):
        paths_module.sandbox_dir("../../etc")
