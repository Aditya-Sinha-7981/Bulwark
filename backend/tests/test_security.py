"""
Zero-egress security tests — layers 2 and 3, tasks/18-security-zero-egress.md §8.

Layer 2: every Registry capability declares network_access: false; the
Policy engine denies any deviation. Layer 3: the Model Runtime resolves only
to loopback; no external URL/API key in config/*.yaml.

These assertions cross-reference and re-confirm invariants Task 6 (Policy)
and Task 8 (Model Runtime) already established at unit-test level
(backend/tests/test_policy_engine.py, backend/tests/test_config.py) — this
module is the Task 18 "still holds, all together, as a security gate" check.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest
import yaml

from backend.domain.capabilities.registry import CapabilityRegistry
from backend.domain.policy.engine import evaluate
from backend.config import settings

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = REPO_ROOT / "config"

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _real_capabilities_config() -> dict:
    with (CONFIG_DIR / "capabilities.yaml").open() as fh:
        return yaml.safe_load(fh)


def _real_policy_config() -> dict:
    with (CONFIG_DIR / "policy.yaml").open() as fh:
        return yaml.safe_load(fh)


# --- Layer 2: capability registry invariant ---------------------------------

class TestLayer2RegistryInvariant:
    def test_every_registered_capability_declares_network_access_false(self):
        registry = CapabilityRegistry(_real_capabilities_config())
        for entry in registry.all():
            assert entry.network_access is False, (
                f"capability '{entry.name}' must declare network_access: false"
            )

    def test_policy_denies_fixture_capability_with_network_access_true(self):
        registry_entry = {
            "name": "hypothetical_capability",
            "permissions": [],
            "network_access": True,  # VIOLATION — no such real capability exists
            "filesystem_scope": [],
        }
        capabilities_config = {
            "capabilities": {"hypothetical_capability": {"enabled": True, "timeout_seconds": 10}}
        }
        decision = evaluate(
            "hypothetical_capability",
            {},
            registry_entry,
            capabilities_config,
            _real_policy_config(),
        )
        assert decision["policy_decision"] == "deny"
        assert decision["rule"] == "network_access_invariant"

    def test_policy_denies_when_config_network_access_allowed_true(self):
        registry_entry = {
            "name": "search_knowledge_base",
            "permissions": ["read_chroma_index"],
            "network_access": False,
            "filesystem_scope": [],
        }
        capabilities_config = _real_capabilities_config()
        tampered_policy = {"policy": {**_real_policy_config()["policy"], "network_access_allowed": True}}

        decision = evaluate(
            "search_knowledge_base",
            {},
            registry_entry,
            capabilities_config,
            tampered_policy,
        )
        assert decision["policy_decision"] == "deny"
        assert decision["rule"] == "network_access_invariant"

    def test_no_config_knob_sets_network_access_allowed_true(self):
        """config/policy.yaml itself, as committed, must have the invariant
        set to false — this is the actual deployed config, not a fixture."""
        policy = _real_policy_config()
        assert policy["policy"]["network_access_allowed"] is False


# --- Layer 3: model runtime loopback-only -----------------------------------

class TestLayer3ModelRuntimeLoopback:
    def test_settings_ollama_base_url_is_loopback(self):
        host = urlparse(settings.app.ollama.base_url).hostname
        assert host in LOOPBACK_HOSTS, (
            f"ollama.base_url resolves to non-loopback host '{host}'"
        )

    def test_no_external_url_or_api_key_in_config_yaml_files(self):
        """Grep every config/*.yaml for anything that looks like an external
        HTTP(S) endpoint or an API-key-shaped field. Loopback URLs are fine
        (config/app.yaml's ollama.base_url, frontend cors_origins)."""
        suspicious_url_hosts = []
        api_key_lines = []

        for path in CONFIG_DIR.glob("*.yaml"):
            with path.open() as fh:
                data = yaml.safe_load(fh) or {}
            text = path.read_text()

            for lineno, line in enumerate(text.splitlines(), start=1):
                lowered = line.lower()
                if "api_key" in lowered or "apikey" in lowered or "api-key" in lowered:
                    api_key_lines.append(f"{path.name}:{lineno}: {line.strip()}")

            for url in _extract_urls(data):
                host = urlparse(url).hostname
                if host not in LOOPBACK_HOSTS:
                    suspicious_url_hosts.append(f"{path.name}: {url} (host={host})")

        assert not api_key_lines, f"API-key-shaped config found: {api_key_lines}"
        assert not suspicious_url_hosts, f"non-loopback URL found in config: {suspicious_url_hosts}"


def _extract_urls(node) -> list[str]:
    urls = []
    if isinstance(node, str):
        if node.startswith("http://") or node.startswith("https://"):
            urls.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            urls.extend(_extract_urls(v))
    elif isinstance(node, list):
        for v in node:
            urls.extend(_extract_urls(v))
    return urls
