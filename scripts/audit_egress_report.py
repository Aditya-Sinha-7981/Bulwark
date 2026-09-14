#!/usr/bin/env python3
"""Retroactive zero-egress proof — tasks/18-security-zero-egress.md §7 Req 8.

Answers "how do you know?" for a technically-literate judge without relying
on the live sovereignty panel: queries `audit_events` and shows that none of
the recorded `model_invoked` / `tool_invoked` events (or any other event) was
associated with a non-loopback connection, across the whole session (or a
`--since` / `--job-id` slice of it).

This is a CLI script, not an API endpoint (locked finalisation decision,
Task 18 §11) — no new event type, no schema change.

Usage:
    python scripts/audit_egress_report.py
    python scripts/audit_egress_report.py --since 2026-09-14T00:00:00+00:00
    python scripts/audit_egress_report.py --job-id <uuid>

Exit code 0 if the report shows zero external connections; 1 if any
`network_check` event or `socket_guard` block indicates otherwise (a real
finding, not just a reporting failure).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.repositories.db import get_connection  # noqa: E402

INVOCATION_EVENT_TYPES = ("model_invoked", "tool_invoked")


def _fetch(conn, since: str | None, job_id: str | None):
    clauses = []
    params: list = []
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if job_id:
        clauses.append("job_id = ?")
        params.append(job_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    rows = conn.execute(
        f"SELECT event_id, job_id, event_type, component, timestamp, payload "
        f"FROM audit_events {where} ORDER BY timestamp ASC",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def build_report(events: list[dict]) -> dict:
    invocation_count = sum(1 for e in events if e["event_type"] in INVOCATION_EVENT_TYPES)

    network_checks = [e for e in events if e["event_type"] == "network_check"]
    external_detected = []
    for e in network_checks:
        payload = json.loads(e["payload"])
        if payload.get("external_connections_detected"):
            external_detected.append(e)

    socket_guard_blocks = [
        e for e in events if e["event_type"] == "error" and e["component"] == "socket_guard"
    ]

    clean = not external_detected and not socket_guard_blocks

    return {
        "total_events": len(events),
        "invocation_count": invocation_count,
        "network_check_count": len(network_checks),
        "external_connections_detected_count": len(external_detected),
        "socket_guard_block_count": len(socket_guard_blocks),
        "clean": clean,
    }


def format_report(report: dict) -> str:
    lines = []
    if report["clean"]:
        lines.append(
            f"0 external connections across {report['invocation_count']} model/tool invocations"
        )
    else:
        lines.append(
            f"EGRESS DETECTED: {report['external_connections_detected_count']} network_check "
            f"event(s) flagged external connections; {report['socket_guard_block_count']} "
            f"socket_guard block(s) recorded — across {report['invocation_count']} "
            f"model/tool invocations"
        )
    lines.append(f"  total audit events inspected: {report['total_events']}")
    lines.append(f"  network_check events: {report['network_check_count']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default=None, help="ISO-8601 timestamp lower bound")
    parser.add_argument("--job-id", default=None, help="Restrict to a single job's events")
    args = parser.parse_args()

    conn = get_connection()
    try:
        events = _fetch(conn, args.since, args.job_id)
    finally:
        conn.close()

    report = build_report(events)
    print(format_report(report))
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
