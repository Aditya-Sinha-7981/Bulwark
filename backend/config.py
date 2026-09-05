"""Centralised configuration loader (Task 2, implementation-plan.md Stage 2).

Loads `config/resources.yaml`, `config/capabilities.yaml`, `config/policy.yaml`,
and `config/app.yaml` once at import time, deep-merges an optional
per-machine `config/<name>.local.yaml` over each, validates the result into
the typed models in `backend/models/schemas.py`, and exposes a single frozen
`settings` object (`settings.resources`, `settings.capabilities`,
`settings.policy`, `settings.app`).

Every value that used to be a hardcoded constant in the Task 1.a stub
(host, port, CORS origins, data directories) now comes from `settings`.
See `docs/configuration.md` for the authoritative file contents.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any

import yaml
from pydantic import ValidationError

from backend.models.schemas import (
    AppConfig,
    AppFile,
    CapabilitiesFile,
    PolicyFile,
    ResourcesFile,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


def _fail(message: str) -> None:
    print(f"fatal: {message}", file=sys.stderr)
    raise SystemExit(1)


def _load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        _fail(f"config file not found: {path}")
    try:
        with path.open("r") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        _fail(f"malformed YAML in {path}: {exc}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        _fail(f"config file {path} must contain a YAML mapping at the top level")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge for mappings only; a list in `override` replaces the base list.

    Locked semantics (tasks/2-configuration-loading.md §7 Requirement 3): a
    key present in both files whose value is a mapping merges recursively.
    A key whose value is a list (e.g. `app.cors_origins`) is replaced
    entirely by the local file's list — never concatenated. A teammate
    adding a local CORS override must repeat the full list, not append one
    entry.
    """
    merged = dict(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _local_path_for(filename: str) -> pathlib.Path:
    stem = filename.rsplit(".yaml", 1)[0]
    return CONFIG_DIR / f"{stem}.local.yaml"


def _load_and_validate(filename: str, model: type, expected_keys: set[str]):
    base_path = CONFIG_DIR / filename
    data = _load_yaml(base_path)

    unknown = set(data.keys()) - expected_keys
    if unknown:
        print(
            f"warning: {base_path} has unrecognized top-level key(s) {sorted(unknown)}; "
            "ignoring is not intentional support, this is a structural-drift warning",
            file=sys.stderr,
        )

    local_path = _local_path_for(filename)
    if local_path.exists():
        local_data = _load_yaml(local_path)
        local_unknown = set(local_data.keys()) - expected_keys
        if local_unknown:
            print(
                f"warning: {local_path} has unrecognized top-level key(s) {sorted(local_unknown)}",
                file=sys.stderr,
            )
        data = _deep_merge(data, local_data)

    try:
        return model.model_validate(data)
    except ValidationError as exc:
        _fail(f"config validation failed for {base_path} (merged with {local_path.name} if present):\n{exc}")


class Settings:
    """Frozen, process-wide configuration surface. Construct via `load_settings()`."""

    __slots__ = ("resources", "capabilities", "policy", "app")

    def __init__(self, resources, capabilities, policy, app: AppConfig) -> None:
        object.__setattr__(self, "resources", resources)
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "policy", policy)
        object.__setattr__(self, "app", app)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"Settings is frozen; cannot set '{name}'")


def load_settings() -> Settings:
    resources_file: ResourcesFile = _load_and_validate(
        "resources.yaml", ResourcesFile, {"resources"}
    )
    capabilities_file: CapabilitiesFile = _load_and_validate(
        "capabilities.yaml", CapabilitiesFile, {"capabilities"}
    )
    policy_file: PolicyFile = _load_and_validate("policy.yaml", PolicyFile, {"policy"})
    app_file: AppFile = _load_and_validate(
        "app.yaml", AppFile, {"app", "paths", "ocr", "ollama"}
    )

    app_config = AppConfig(
        host=app_file.app.host,
        port=app_file.app.port,
        cors_origins=app_file.app.cors_origins,
        paths=app_file.paths,
        ocr=app_file.ocr,
        ollama=app_file.ollama,
    )

    return Settings(
        resources=resources_file.resources,
        capabilities=capabilities_file.capabilities,
        policy=policy_file.policy,
        app=app_config,
    )


settings = load_settings()
