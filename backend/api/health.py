"""
Health endpoint (docs/api.md `GET /api/v1/health`, Task 15 Requirement 3).

Real probes: the backend process (always `ok` if this handler runs), the
SQLite database (connect + `SELECT 1`), the Ollama runtime (TCP reachability
on the configured loopback address — a liveness check, not a model call, so
`domain/model_runtime/runtime.py` stays the only module that speaks Ollama's
HTTP API), and the Docker daemon (`docker version` returns a server version).

`health` never returns `503` — it *is* the mechanism for reporting
per-dependency degradation, via the `ok | unavailable` values in its `200`
body (Task 15 Requirement 7). `docs/api.md` shows only `status: "ok"`.
"""
from __future__ import annotations

import socket
import subprocess
from urllib.parse import urlparse

from fastapi import APIRouter

from backend.config import settings
from backend.repositories.db import get_connection

router = APIRouter()

_SOCKET_TIMEOUT_SECONDS = 1.5
_DOCKER_TIMEOUT_SECONDS = 5.0  # `docker version` on Docker Desktop can take a few seconds


def _probe_database() -> bool:
    try:
        conn = get_connection()
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return True
    except Exception:
        return False


def _probe_ollama() -> bool:
    parsed = urlparse(settings.app.ollama.base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=_SOCKET_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _probe_docker() -> bool:
    try:
        result = subprocess.run(
            ["docker", "version", "-f", "{{.Server.Version}}"],
            capture_output=True,
            timeout=_DOCKER_TIMEOUT_SECONDS,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() != b""
    except (OSError, subprocess.SubprocessError):
        return False


@router.get("/health")
def get_health() -> dict:
    return {
        "status": "ok",
        "backend": "ok",
        "database": "ok" if _probe_database() else "unavailable",
        "model_runtime": "ok" if _probe_ollama() else "unavailable",
        "docker": "ok" if _probe_docker() else "unavailable",
    }
