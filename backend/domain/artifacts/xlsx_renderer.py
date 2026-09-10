"""
XLSX artifact renderer (Task 14.b).

Deterministically renders an Excel workbook from validated structured input,
per docs/artifacts.md "Templates" (XLSX) and docs/capabilities.md#create_xlsx.
Mirrors the atomic-write and Artifact-persistence pattern established in
Task 14.a's docx_renderer.py (see logs/artifacts-docx.md) — same guarantees,
same failure handling, different rendering library (openpyxl vs python-docx).
"""
from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

from backend.repositories.artifacts import create_artifact
from backend.utils import paths as paths_module

_MAX_FILENAME_STEM_LEN = 80
_MAX_SHEET_NAME_LEN = 31  # Excel's hard limit on sheet name length


class XlsxRenderError(Exception):
    """Raised on any rendering/write/persistence failure.

    Same contract as docx_renderer.DocxRenderError: no partial file is ever
    left in data/artifacts/, and no Artifact row is created when this is
    raised (docs/artifacts.md "Failure handling").
    """


def _sanitize_filename_stem(title: str) -> str:
    """Same normalization as docx_renderer.py, for consistency between the
    two artifact types' user-facing filenames."""
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_")
    if not stem:
        stem = "Workbook"
    return stem[:_MAX_FILENAME_STEM_LEN]


def _sanitize_sheet_name(name: str, index: int) -> str:
    """Excel sheet names: max 31 chars, and cannot contain: \ / ? * [ ] :

    docs/capabilities.md#create_xlsx does not specify sheet-name sanitization
    explicitly — this is a rendering-layer necessity (an unsanitized name
    would raise inside openpyxl itself), not a schema decision. Falls back
    to "Sheet{index}" if the name becomes empty after stripping invalid
    characters.
    """
    cleaned = re.sub(r'[\\/?*\[\]:]', "_", name).strip()
    if not cleaned:
        cleaned = f"Sheet{index + 1}"
    return cleaned[:_MAX_SHEET_NAME_LEN]


def _build_workbook(payload: dict[str, Any]) -> Workbook:
    """Populate the fixed XLSX template with payload content.

    Template (docs/artifacts.md "Templates" XLSX): one sheet per sheets[]
    entry, first row = headers (bold), subsequent rows = rows. No
    charts/formulas for SIH scope, per artifacts.md.

    Ragged-row handling per finalisation decision (§7/§11):
    - Short rows (fewer cells than headers): pad remaining cells with None
    - Long rows (more cells than headers): preserve all provided cells
    - Duplicate sheet names: rejected at validation layer (create_xlsx.py)
    """
    workbook = Workbook()
    # openpyxl creates one default sheet ("Sheet") on Workbook() — remove it
    # since we create our own sheets explicitly below, in order.
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    header_font = Font(bold=True)

    for index, sheet_spec in enumerate(payload["sheets"]):
        sheet_name = _sanitize_sheet_name(sheet_spec["name"], index)
        worksheet = workbook.create_sheet(title=sheet_name)

        headers = sheet_spec["headers"]
        worksheet.append(headers)
        for cell in worksheet[1]:
            cell.font = header_font

        for row in sheet_spec["rows"]:
            # Handle ragged rows: pad short rows, preserve long rows
            if len(row) < len(headers):
                row = list(row) + [None] * (len(headers) - len(row))
            worksheet.append(row)

    return workbook


def render_xlsx(artifact_id: str, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Render a validated create_xlsx payload to disk and persist the Artifact row.

    Args:
        artifact_id: pre-generated UUID this file will be stored under.
        job_id: the Job this artifact belongs to (required, mirrors
            docx_renderer.render_docx's contract).
        payload: validated input matching docs/capabilities.md#create_xlsx
            exactly: {title, sheets: [{name, headers, rows}]}. Caller
            (create_xlsx.py) is responsible for validation.

    Returns:
        {"artifact_id": str, "filename": str}.

    Raises:
        XlsxRenderError: on any openpyxl failure, disk-write failure, or
            Artifact-row persistence failure. Same atomic-write guarantee
            as docx_renderer.render_docx: temp file in the same directory
            as the destination, moved into place with os.replace only on
            full success; orphaned file removed if the Artifact-row insert
            fails after the file is already written.
    """
    final_path = paths_module.artifacts_path(artifact_id, ".xlsx")

    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".xlsx.tmp", dir=paths_module.ARTIFACTS_ROOT)
    os.close(tmp_fd)
    tmp_path = Path(tmp_path_str)

    try:
        workbook = _build_workbook(payload)
        workbook.save(tmp_path)
        size_bytes = tmp_path.stat().st_size
        os.replace(tmp_path, final_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise XlsxRenderError(f"failed to render/write xlsx: {exc}") from exc

    stem = _sanitize_filename_stem(payload["title"])
    filename = f"{stem}.xlsx"

    try:
        create_artifact(
            job_id=job_id,
            type="xlsx",
            filename=filename,
            storage_path=final_path.name,  # relative path under data/artifacts/, matches docx_renderer.py's convention
            size_bytes=size_bytes,
        )
    except Exception as exc:
        final_path.unlink(missing_ok=True)
        raise XlsxRenderError(f"failed to persist Artifact row: {exc}") from exc

    return {"artifact_id": artifact_id, "filename": filename}