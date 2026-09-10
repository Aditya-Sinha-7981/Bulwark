"""
Sandbox-output-file → Artifact conversion (Task 15 Requirement 6).

`execute_code` (Task 13) returns raw `output_files` as candidate *filenames* it
wrote inside the sandbox — never `artifact_id`s. Task 13 must not persist
Artifacts itself (locked ownership). This module reuses Task 14.a's
atomic-write-then-persist primitive, generalised to *copy* an existing file
rather than *render* one:

    copy sandbox file → data/artifacts/{artifact_id}.{ext}  (atomic)
    → Artifact row  → `artifact_created` audit event  → return artifact_id

Known, flagged limitation (Task 15 Requirement 6, AGENTS.md §6 rule 13):
`docs/data-model.md#Artifact` only defines `type ∈ {docx, xlsx, pptx}`. A
sandbox script can emit any extension (`.csv`, `.png`, ...). Rather than invent
an undocumented `type`, only `.docx`/`.xlsx` outputs are converted here; any
other extension is left un-persisted and reported via an `error` audit event by
the caller. Extending the enum is a data-model change needing a project-lead
decision — not made here. No current demo workflow needs generic output files
downloadable (docs/demo.md Workflow B ends with "the verified result and the
code").
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from backend.domain.audit.events import emit
from backend.repositories.artifacts import create_artifact
from backend.utils import paths as paths_module

# Extension → documented Artifact.type (docs/data-model.md#Artifact).
_EXT_TO_TYPE = {".docx": "docx", ".xlsx": "xlsx", ".pptx": "pptx"}


class SandboxOutputPersistError(Exception):
    """Copy or Artifact-row persistence failed. Caller records a failed
    tool-result; no partial file / row is left behind."""


def supported_extension(filename: str) -> bool:
    """True if this output file maps to a documented Artifact.type."""
    return Path(filename).suffix.lower() in _EXT_TO_TYPE


async def persist_sandbox_output_as_artifact(
    source_path: Path | str,
    job_id: str,
) -> Optional[str]:
    """
    Copy one sandbox output file into the artifact store and persist its row.

    Args:
        source_path: absolute path to the file the sandbox produced. The
            caller (Job Manager dispatch loop) resolves this from the
            sandbox execution directory — this helper never accepts a
            caller-supplied relative/traversal path into `data/artifacts`.
        job_id: the Job that produced it (Artifact.job_id, not nullable).

    Returns:
        The new `artifact_id`, or None if the extension is not a documented
        Artifact.type (the file is intentionally not persisted — see module
        docstring).

    Raises:
        SandboxOutputPersistError: the source file is missing, or the copy /
            row insert failed.
    """
    source = Path(source_path)
    ext = source.suffix.lower()
    artifact_type = _EXT_TO_TYPE.get(ext)
    if artifact_type is None:
        return None

    if not source.is_file():
        raise SandboxOutputPersistError(f"sandbox output file not found: {source}")

    # Same atomic-write guarantee as docx_renderer.render_docx: stage inside
    # ARTIFACTS_ROOT, then os.replace into the final id-named path only on a
    # complete copy.
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=f"{ext}.tmp", dir=paths_module.ARTIFACTS_ROOT)
    os.close(tmp_fd)
    tmp_path = Path(tmp_path_str)

    try:
        shutil.copyfile(source, tmp_path)
        size_bytes = tmp_path.stat().st_size
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise SandboxOutputPersistError(f"failed to copy sandbox output: {exc}") from exc

    filename = source.name

    try:
        # Unlike the renderers, we use the id create_artifact() actually
        # returns and name the file after it, so storage_path, the on-disk
        # name, and the row id all agree.
        artifact_id = create_artifact(
            job_id=job_id,
            type=artifact_type,
            filename=filename,
            storage_path=f"{{placeholder}}{ext}",  # rewritten below once id is known
            size_bytes=size_bytes,
        )
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise SandboxOutputPersistError(f"failed to persist Artifact row: {exc}") from exc

    final_path = paths_module.artifacts_path(artifact_id, ext)
    try:
        os.replace(tmp_path, final_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise SandboxOutputPersistError(f"failed to place artifact file: {exc}") from exc

    _rewrite_storage_path(artifact_id, final_path.name)

    await emit(
        "artifact_created",
        "job_manager",
        {"artifact_id": artifact_id, "type": artifact_type, "filename": filename},
        job_id=job_id,
    )
    return artifact_id


def _rewrite_storage_path(artifact_id: str, storage_path: str) -> None:
    """Set the row's storage_path to the final id-named file.

    create_artifact() mints the id, so the row is inserted first with a
    placeholder and corrected here — a field setter on an existing column,
    no schema change (docs/data-model.md#Artifact).
    """
    from backend.repositories.db import get_connection

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE artifacts SET storage_path = ? WHERE artifact_id = ?",
            (storage_path, artifact_id),
        )
        conn.commit()
    finally:
        conn.close()
