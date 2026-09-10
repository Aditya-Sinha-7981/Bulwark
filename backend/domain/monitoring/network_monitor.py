"""
Zero-egress network monitor (Task 15 Requirement 4 — scaffold only).

A single backend background loop that inspects the connections owned by *this*
process with `psutil` and records whether any non-loopback (external) socket is
open. Each poll emits a `network_check` audit event (`job_id` null, per
docs/audit.md) and updates the in-memory latest result that
`GET /api/v1/network-status` returns.

Scope boundary (docs/security.md "Zero-egress — enforcement vs. proof",
Task 15 §10 / Task 18):
- This module is *proof/observability*, one of the two independent ways to
  answer "prove it" (the live panel; the other is the retroactive audit query).
- It does **not** enforce anything. The six enforcement layers, the OS firewall,
  the socket backstop, and the offline validation run are Task 18.

It stays deliberately small — one loop + the state the endpoint reads. Not a
framework, not a separate service (locked finalisation decision, Task 15 §11).
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
from datetime import datetime, timezone
from typing import Any, Optional

import psutil

from backend.domain.audit.events import emit

# Poll cadence. The endpoint only ever returns the latest result, so this is the
# resolution of the "external connections" signal, not a request path.
POLL_INTERVAL_SECONDS = 5.0

_COMPONENT = "network_monitor"

# Module state (single process, single loop).
_task: Optional[asyncio.Task] = None
_monitoring_since: Optional[str] = None
_latest: dict[str, Any] = {
    "external_connections_detected": False,
    "checked_at": None,
    "remote_addresses": [],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_external(host: Optional[str]) -> bool:
    """True if `host` is a routable non-loopback address.

    Loopback (127.0.0.0/8, ::1) is where Ollama and the frontend dev server
    live — those are sovereign-local and never count as egress.
    """
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host.split("%")[0])  # strip scope id if present
    except ValueError:
        return False
    return not (ip.is_loopback or ip.is_unspecified)


def _scan_own_connections() -> list[str]:
    """Return the sorted unique set of external remote addresses this process holds."""
    externals: set[str] = set()
    try:
        conns = psutil.Process().net_connections(kind="inet")
    except (psutil.Error, PermissionError, OSError):
        # If we cannot inspect our own sockets, report nothing found rather than
        # a false positive; Task 18's enforcement layers are the real guarantee.
        return []
    for conn in conns:
        raddr = getattr(conn, "raddr", None)
        if not raddr:
            continue
        host = raddr[0] if isinstance(raddr, tuple) else getattr(raddr, "ip", None)
        if _is_external(host):
            port = raddr[1] if isinstance(raddr, tuple) else getattr(raddr, "port", "")
            externals.add(f"{host}:{port}")
    return sorted(externals)


async def _check_once() -> dict[str, Any]:
    externals = await asyncio.to_thread(_scan_own_connections)
    checked_at = _now_iso()
    result = {
        "external_connections_detected": bool(externals),
        "checked_at": checked_at,
        "remote_addresses": externals,
    }
    _latest.update(result)

    # Single audit write path (Task 4). Never let a monitoring hiccup take down
    # the loop — a failed emit is logged by emit() itself; we swallow here.
    with contextlib.suppress(Exception):
        await emit(
            event_type="network_check",
            component=_COMPONENT,
            payload={
                "external_connections_detected": result["external_connections_detected"],
                "checked_at": checked_at,
            },
            job_id=None,
        )
    return result


async def _loop() -> None:
    while True:
        await _check_once()
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def start() -> None:
    """Start the background monitor. Idempotent; called from app lifespan."""
    global _task, _monitoring_since
    if _task is not None and not _task.done():
        return
    _monitoring_since = _now_iso()
    # One eager check so the endpoint has a real value immediately after startup.
    await _check_once()
    _task = asyncio.create_task(_loop(), name="network-monitor")


async def stop() -> None:
    """Stop the background monitor. Idempotent."""
    global _task
    if _task is None:
        return
    _task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _task
    _task = None


def get_status() -> dict[str, Any]:
    """The `GET /api/v1/network-status` body (docs/api.md)."""
    return {
        "external_connections_detected": _latest["external_connections_detected"],
        "checked_at": _latest["checked_at"] or _now_iso(),
        "monitoring_since": _monitoring_since or _now_iso(),
    }
