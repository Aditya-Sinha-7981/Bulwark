"""
Zero-egress sovereignty-proof endpoint (docs/api.md `GET /api/v1/network-status`).

Thin read of the continuous `network_monitor` loop (started in app lifespan).
The monitor itself — and the six enforcement layers behind the claim — is
scaffolded here and completed in Task 18.
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.domain.monitoring import network_monitor

router = APIRouter(tags=["network"])


@router.get("/network-status")
async def get_network_status() -> dict:
    """
    Response 200:
    {
      "external_connections_detected": false,
      "checked_at": "iso8601",
      "monitoring_since": "iso8601"
    }
    """
    return network_monitor.get_status()
