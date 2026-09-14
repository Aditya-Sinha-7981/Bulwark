"""
Zero-egress enforcement tests — tasks/18-security-zero-egress.md §8.

Covers layer 1 (static check), layer 4 (promoted from test_sandbox.py),
layer 6 (socket guard backstop), the production network monitor, and the
retroactive audit report script.

Layers 2 (Policy invariant) and 3 (Model Runtime loopback) are asserted in
test_security.py, per the task's own file split.
"""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHECK_SCRIPT = REPO_ROOT / "scripts" / "check_no_egress.py"


# --- Layer 1: static check --------------------------------------------------

def _run_check_script() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_check_no_egress_passes_on_current_tree():
    result = _run_check_script()
    assert result.returncode == 0, result.stderr


def test_check_no_egress_fails_on_planted_violation(tmp_path):
    """A deliberately-planted non-loopback HTTP call outside runtime.py must
    make the check fail. Planted under backend/domain/ (a real subpackage,
    not backend/tests/, which the scanner intentionally excludes), then
    removed regardless of outcome."""
    planted = REPO_ROOT / "backend" / "domain" / "_egress_plant_for_test.py"
    planted.write_text("import httpx\n\ndef bad():\n    httpx.get('https://example.com')\n")
    try:
        result = _run_check_script()
        assert result.returncode != 0
        assert "_egress_plant_for_test.py" in result.stdout + result.stderr
    finally:
        planted.unlink()


# --- Layer 4: sandbox network denial (promoted from test_sandbox.py) -------
# Re-imported rather than duplicated so there is exactly one implementation
# of the check; this module is where Task 18 documents it as part of the
# zero-egress suite (docs/testing.md "Zero-egress tests").

from backend.tests.test_sandbox import (  # noqa: E402
    DOCKER_AVAILABLE,
    IMAGE_BUILT,
    TestNetworkDenial as _Layer4NetworkDenial,
)


@pytest.fixture
def sandbox_root(tmp_path: Path) -> Path:
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


@pytest.mark.skipif(
    not (DOCKER_AVAILABLE and IMAGE_BUILT),
    reason="Docker daemon and/or bulwark-sandbox:latest image not available.",
)
class TestLayer4SandboxNetworkDenial(_Layer4NetworkDenial):
    """Layer 4 promoted into the zero-egress suite — see test_sandbox.py for
    the canonical implementation this inherits. (Re-declares the
    `sandbox_root` fixture locally: pytest fixtures defined in another test
    module are not visible across modules without a shared conftest entry,
    and test_sandbox.py's fixture is intentionally file-local.)"""


# --- Layer 6: socket guard backstop -----------------------------------------

from backend.utils import socket_guard  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_guard_state():
    """Every test in this module starts and ends with the guard uninstalled,
    regardless of what the socket-guard tests themselves do."""
    socket_guard.uninstall()
    yield
    socket_guard.uninstall()


class TestSocketGuard:
    def test_not_installed_by_default_in_tests(self):
        assert socket_guard.is_installed() is False

    def test_install_is_idempotent(self):
        socket_guard.install()
        socket_guard.install()
        assert socket_guard.is_installed() is True

    def test_loopback_connect_still_works(self):
        """The guard must never block loopback — start a real listener on
        127.0.0.1 and confirm connect() to it succeeds with the guard on."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        socket_guard.install()
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2)
            client.connect(("127.0.0.1", port))
            client.close()
        finally:
            server.close()

    def test_non_loopback_connect_is_blocked(self):
        socket_guard.install()
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2)
        with pytest.raises(socket_guard.EgressBlockedError):
            client.connect(("93.184.216.34", 80))  # example.com's IP — never dialed
        client.close()

    def test_non_loopback_connect_ex_is_blocked(self):
        socket_guard.install()
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(2)
        with pytest.raises(socket_guard.EgressBlockedError):
            client.connect_ex(("93.184.216.34", 80))
        client.close()

    def test_uninstall_restores_original_behavior(self):
        socket_guard.install()
        socket_guard.uninstall()
        assert socket_guard.is_installed() is False
        assert socket.socket.connect is socket_guard._original_connect


# --- Network monitor (production loop) --------------------------------------

from backend.domain.monitoring import network_monitor  # noqa: E402


class TestNetworkMonitor:
    def test_check_once_emits_network_check_with_null_job_id(self, isolated_db):
        result = asyncio.run(network_monitor._check_once())
        assert result["checked_at"] is not None
        assert isinstance(result["external_connections_detected"], bool)

        import sqlite3

        conn = sqlite3.connect(str(isolated_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT job_id, event_type, payload FROM audit_events WHERE event_type = 'network_check'"
        ).fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0]["job_id"] is None
        payload = json.loads(rows[0]["payload"])
        assert "external_connections_detected" in payload
        assert "checked_at" in payload

    def test_get_status_reflects_latest_check(self, isolated_db):
        asyncio.run(network_monitor._check_once())
        status = network_monitor.get_status()
        assert set(status) == {"external_connections_detected", "checked_at", "monitoring_since"}


# --- Retroactive audit report -----------------------------------------------

from scripts.audit_egress_report import build_report, format_report  # noqa: E402


class TestAuditEgressReport:
    def _event(self, event_type, payload, job_id=None, component="test"):
        return {
            "event_id": "e",
            "job_id": job_id,
            "event_type": event_type,
            "component": component,
            "timestamp": "2026-09-14T00:00:00+00:00",
            "payload": json.dumps(payload),
        }

    def test_zero_external_connections_across_invocations(self):
        events = [
            self._event("model_invoked", {"resource_type": "reasoning"}),
            self._event("tool_invoked", {"capability": "search_knowledge_base", "arguments": {}}),
            self._event("network_check", {"external_connections_detected": False, "checked_at": "t"}),
            self._event("network_check", {"external_connections_detected": False, "checked_at": "t2"}),
        ]
        report = build_report(events)
        assert report["clean"] is True
        assert report["invocation_count"] == 2
        text = format_report(report)
        assert "0 external connections across 2 model/tool invocations" in text

    def test_flags_external_connection_detected(self):
        events = [
            self._event("model_invoked", {"resource_type": "reasoning"}),
            self._event("network_check", {"external_connections_detected": True, "checked_at": "t"}),
        ]
        report = build_report(events)
        assert report["clean"] is False
        assert "EGRESS DETECTED" in format_report(report)

    def test_flags_socket_guard_block(self):
        events = [
            self._event("model_invoked", {"resource_type": "reasoning"}),
            self._event(
                "error",
                {"component": "socket_guard", "message": "blocked", "context": {}},
                component="socket_guard",
            ),
        ]
        report = build_report(events)
        assert report["clean"] is False
