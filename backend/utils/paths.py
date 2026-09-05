"""Scoped filesystem-path helpers resolved from `settings.app.paths`.

Every path composed here lives under one of the configured roots
(`config/app.yaml` `paths:`). No function accepts a raw absolute path or a
`..` component from a caller — `docs/security.md` "Filesystem restrictions":
Executors must only ever touch scoped paths, never caller-supplied absolute
paths.
"""

from __future__ import annotations

import pathlib

from backend.config import REPO_ROOT, settings


def _resolve_root(relative: str) -> pathlib.Path:
    return (REPO_ROOT / relative).resolve()


DATA_ROOT = _resolve_root(settings.app.paths.data_root)
UPLOADS_ROOT = _resolve_root(settings.app.paths.uploads)
EXTRACTION_ROOT = _resolve_root(settings.app.paths.extraction)
ARTIFACTS_ROOT = _resolve_root(settings.app.paths.artifacts)
SANDBOX_ROOT = _resolve_root(settings.app.paths.sandbox)
TMP_ROOT = _resolve_root(settings.app.paths.tmp)
DB_FILE = _resolve_root(settings.app.paths.db)
CHROMA_ROOT = _resolve_root(settings.app.paths.chroma)


def _reject_unsafe(*components: str) -> None:
    for component in components:
        purepath = pathlib.PurePath(component)
        if purepath.is_absolute():
            raise ValueError(f"path component must not be absolute: {component!r}")
        if ".." in purepath.parts:
            raise ValueError(f"path component must not contain '..': {component!r}")


def uploads_path(document_id: str, ext: str) -> pathlib.Path:
    _reject_unsafe(document_id, ext)
    return UPLOADS_ROOT / f"{document_id}{ext}"


def extraction_path(document_id: str) -> pathlib.Path:
    _reject_unsafe(document_id)
    return EXTRACTION_ROOT / document_id


def artifacts_path(artifact_id: str, ext: str) -> pathlib.Path:
    _reject_unsafe(artifact_id, ext)
    return ARTIFACTS_ROOT / f"{artifact_id}{ext}"


def sandbox_dir(execution_id: str) -> pathlib.Path:
    _reject_unsafe(execution_id)
    return SANDBOX_ROOT / execution_id


def db_path() -> pathlib.Path:
    return DB_FILE


def chroma_dir() -> pathlib.Path:
    return CHROMA_ROOT


def tmp_dir() -> pathlib.Path:
    return TMP_ROOT


def all_managed_dirs() -> list[pathlib.Path]:
    """Directories the backend must create idempotently at startup."""
    return [
        DATA_ROOT,
        UPLOADS_ROOT,
        EXTRACTION_ROOT,
        ARTIFACTS_ROOT,
        SANDBOX_ROOT,
        TMP_ROOT,
        DB_FILE.parent,
        CHROMA_ROOT,
    ]
