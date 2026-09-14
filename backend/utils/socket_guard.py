"""
Zero-egress socket guard — Layer 6 (backstop), tasks/18-security-zero-egress.md §7 Req 6.

This is the *last-resort* layer. It is not the primary enforcement mechanism —
that is layers 1-5 (no non-loopback HTTP client in application code, the
Policy engine's network_access invariant, the Model Runtime's loopback-only
base URL, the sandbox's `--network none`, and the OS firewall). This module
exists so that if every other layer somehow failed — a bug, a future
dependency that opens a raw socket — the backend process itself still cannot
complete a connection to a non-loopback address.

Mechanism: monkeypatch `socket.socket.connect` (and `connect_ex`) at process
startup so any `connect()` call to a non-loopback address raises immediately,
before the OS-level TCP handshake begins. Loopback (127.0.0.0/8, ::1) always
passes through unmodified — Ollama, SQLite/Chroma (local files, not
sockets), and the browser's own requests to the backend are all unaffected.

docs/security.md layer 6: "a deliberately last line of defense, not the
mechanism you'd point to first."
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any

from backend.domain.audit.events import emit

_installed = False
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex


class EgressBlockedError(OSError):
    """Raised when the backend process attempts a non-loopback connection."""


def _extract_host(address: Any) -> str | None:
    """Pull the host out of a connect() address argument.

    AF_INET: (host, port). AF_INET6: (host, port, flowinfo, scopeid).
    AF_UNIX and other families pass a str/bytes path, not a network
    address — never egress, always allowed through untouched.
    """
    if isinstance(address, tuple) and len(address) >= 1:
        return address[0]
    return None


def _is_loopback(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
        return ip.is_loopback
    except ValueError:
        # Not a literal IP (e.g. a hostname). "localhost" is the only
        # hostname the codebase uses (config/app.yaml ollama.base_url) and
        # resolves to loopback on every supported platform; anything else
        # is treated as non-loopback and blocked, fail-closed.
        return host == "localhost"


def _emit_blocked(host: str, port: Any) -> None:
    import asyncio

    async def _do_emit() -> None:
        await emit(
            event_type="error",
            component="socket_guard",
            payload={
                "component": "socket_guard",
                "message": f"blocked non-loopback connect() attempt to {host}:{port}",
                "context": {"host": host, "port": port},
            },
            job_id=None,
        )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_do_emit())
    except RuntimeError:
        # No running event loop (e.g. guard tripped outside a request/async
        # context) — the block itself still happens; only the audit event
        # is best-effort here.
        pass


def _guarded_connect(self: socket.socket, address: Any):
    host = _extract_host(address)
    if host is not None and not _is_loopback(host):
        port = address[1] if len(address) > 1 else None
        _emit_blocked(host, port)
        raise EgressBlockedError(
            f"socket_guard: blocked non-loopback connect() to {host}:{port} "
            "(zero-egress backstop — docs/security.md layer 6)"
        )
    return _original_connect(self, address)


def _guarded_connect_ex(self: socket.socket, address: Any):
    host = _extract_host(address)
    if host is not None and not _is_loopback(host):
        port = address[1] if len(address) > 1 else None
        _emit_blocked(host, port)
        raise EgressBlockedError(
            f"socket_guard: blocked non-loopback connect() to {host}:{port} "
            "(zero-egress backstop — docs/security.md layer 6)"
        )
    return _original_connect_ex(self, address)


def install() -> None:
    """Install the guard. Idempotent — safe to call more than once."""
    global _installed
    if _installed:
        return
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    _installed = True


def uninstall() -> None:
    """Restore the original socket methods. Idempotent. Test-only."""
    global _installed
    if not _installed:
        return
    socket.socket.connect = _original_connect
    socket.socket.connect_ex = _original_connect_ex
    _installed = False


def is_installed() -> bool:
    return _installed
