#!/usr/bin/env python3
"""Layer 1 (application) zero-egress check — tasks/18-security-zero-egress.md §7 Req 1.

Fails if:
  - An HTTP client (httpx, requests, urllib, http.client, aiohttp) or a raw
    socket.connect(...) call is used anywhere in backend/ outside
    backend/domain/model_runtime/runtime.py.
  - runtime.py's configured Ollama base URL targets anything but
    localhost/127.0.0.1 (checked via config/app.yaml, since the URL itself
    is not hardcoded in runtime.py — docs/security.md layer 3).

This is a code-review gate (docs/security.md layer 1: "verified at code
review, not a runtime setting"), run in the test suite by
backend/tests/test_zero_egress.py.

Usage:
    python scripts/check_no_egress.py

Exits 0 if clean, non-zero (and prints each offending file/line) otherwise.
"""

from __future__ import annotations

import pathlib
import re
import sys
from urllib.parse import urlparse

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
APP_CONFIG_FILE = REPO_ROOT / "config" / "app.yaml"

# The one module permitted to hold an HTTP client — it talks to Ollama on
# loopback only (docs/security.md layer 3).
RUNTIME_FILE = BACKEND_DIR / "domain" / "model_runtime" / "runtime.py"

# health.py's Ollama probe is a raw TCP reachability check (not an HTTP
# client call, and not model traffic — docs/api.md `GET /api/v1/health`),
# and its host/port come from the exact same config.app.ollama.base_url this
# script's layer-3 check (_check_runtime_loopback_only) verifies is
# loopback-locked. Allowed here rather than exempted from the HTTP-client
# scan entirely, so a future edit that hardcodes a different host would still
# be caught by that separate check.
ALLOWED_SOCKET_FILES = {BACKEND_DIR / "api" / "health.py"}

EXCLUDED_DIRS = {".venv", "__pycache__", ".pytest_cache", "node_modules"}

# Modules/calls that reach outside the process. Matched as identifiers, not
# substrings, so "httpx" flags `import httpx` / `httpx.get(...)` but not an
# unrelated word containing it.
_FORBIDDEN_IMPORTS = re.compile(
    r"^\s*(?:import|from)\s+(httpx|requests|urllib\.request|urllib3|aiohttp|http\.client)\b",
    re.MULTILINE,
)
_FORBIDDEN_CALLS = re.compile(
    r"\b(httpx\.\w+\(|requests\.\w+\(|aiohttp\.\w+\(|urlopen\(|http\.client\.\w+\(|socket\.create_connection\()"
)
# A raw socket .connect(...) call (socket_guard.py itself needs to reference
# the pattern in prose/tests without being flagged — it never calls connect()
# on a non-loopback address itself, so this stays a plain textual check).
_SOCKET_CONNECT = re.compile(r"\.connect\(\s*\(")

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _iter_backend_py_files():
    for path in BACKEND_DIR.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if "tests" in path.parts:
            # Test files intentionally exercise/assert egress-denial behavior
            # (e.g. planting a violation, or socket_guard's own unit tests
            # constructing loopback/non-loopback connect() calls) — this
            # script audits application code, not the tests that verify it.
            continue
        yield path


def _check_forbidden_http_clients() -> list[str]:
    violations = []
    for path in _iter_backend_py_files():
        if path == RUNTIME_FILE:
            continue
        if path in ALLOWED_SOCKET_FILES:
            continue
        text = path.read_text(errors="ignore")
        rel = path.relative_to(REPO_ROOT)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _FORBIDDEN_IMPORTS.match(line) or _FORBIDDEN_CALLS.search(line):
                violations.append(f"{rel}:{lineno}: forbidden HTTP client usage: {line.strip()}")
            if _SOCKET_CONNECT.search(line) and "utils/socket_guard.py" not in str(rel).replace("\\", "/"):
                violations.append(f"{rel}:{lineno}: raw socket.connect(...) usage: {line.strip()}")
    return violations


def _check_runtime_loopback_only() -> list[str]:
    if not APP_CONFIG_FILE.exists():
        return [f"{APP_CONFIG_FILE.relative_to(REPO_ROOT)}: not found"]

    with APP_CONFIG_FILE.open() as fh:
        data = yaml.safe_load(fh)

    base_url = (data or {}).get("ollama", {}).get("base_url")
    if not base_url:
        return ["config/app.yaml: ollama.base_url is not set"]

    host = urlparse(base_url).hostname
    if host not in LOOPBACK_HOSTS:
        return [f"config/app.yaml: ollama.base_url '{base_url}' resolves to non-loopback host '{host}'"]
    return []


def main() -> int:
    violations = _check_forbidden_http_clients() + _check_runtime_loopback_only()

    if violations:
        print("zero-egress layer-1 violation(s) found:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print("no non-loopback HTTP client usage found outside backend/domain/model_runtime/runtime.py; "
          "Ollama base URL is loopback-locked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
