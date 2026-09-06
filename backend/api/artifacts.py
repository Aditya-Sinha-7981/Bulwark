"""
Artifact metadata and download routes (Task 14.a — first artifact producer).

Implements GET /api/v1/artifacts/{artifact_id} and .../download exactly as
quoted in docs/api.md. Task 14.b reuses this router for the xlsx type;
nothing here is docx-specific except the media type fallback.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.repositories.artifacts import get_artifact
from backend.utils.paths import ARTIFACTS_ROOT

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def _not_found_envelope(message: str) -> dict:
    # Per docs/api.md "Error format":
    # {"error": {"code": "string_error_code", "message": "human-readable message", "details": {}}}
    return {"error": {"code": "not_found", "message": message, "details": {}}}


@router.get("/{artifact_id}")
async def get_artifact_metadata(artifact_id: str) -> dict:
    """Return artifact metadata. 404 with the api.md error envelope if unknown."""
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=_not_found_envelope("artifact not found"))

    return {
        "artifact_id": artifact["artifact_id"],
        "job_id": artifact["job_id"],
        "type": artifact["type"],
        "filename": artifact["filename"],
        "created_at": artifact["created_at"],
        "size_bytes": artifact["size_bytes"],
    }


@router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str) -> FileResponse:
    """Stream the artifact's bytes with Content-Disposition set to its readable filename."""
    artifact = get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=_not_found_envelope("artifact not found"))

    file_path = ARTIFACTS_ROOT / f"{artifact['artifact_id']}.{artifact['type']}"
    if not file_path.exists():
        # Should be unreachable given the atomic-write guarantee in
        # docx_renderer.py, but never serve a 200 for a missing file.
        raise HTTPException(status_code=404, detail=_not_found_envelope("artifact file missing on disk"))

    return FileResponse(
        path=file_path,
        filename=artifact["filename"],
        media_type="application/octet-stream",
    )