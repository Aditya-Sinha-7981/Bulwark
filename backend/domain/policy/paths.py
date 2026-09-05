"""Policy-engine scoped path authorization helpers.

Built on top of backend.utils.paths (which provides the canonical path roots).
"""

from __future__ import annotations

import os
from typing import List

from backend.utils.paths import (
    UPLOADS_ROOT,
    EXTRACTION_ROOT,
    ARTIFACTS_ROOT,
    SANDBOX_ROOT,
    CHROMA_ROOT,
)


# Capability -> allowed scope root mapping
CAPABILITY_SCOPES = {
    "extract_document": [str(UPLOADS_ROOT)],
    "search_knowledge_base": [str(CHROMA_ROOT)],
    "generate_code": [],  # No filesystem access
    "execute_code": [str(SANDBOX_ROOT)],
    "create_docx": [str(ARTIFACTS_ROOT)],
    "create_xlsx": [str(ARTIFACTS_ROOT)],
    "create_pptx": [str(ARTIFACTS_ROOT)],
}


def resolve_within_scope(path: str, allowed_scopes: List[str]) -> str | None:
    """
    Resolve a path against a list of allowed scope prefixes.

    Returns the resolved absolute path if it falls within any allowed scope,
    otherwise returns None (indicating scope violation).

    Rejects:
    - Absolute paths (must be relative)
    - Path traversal attempts (..)
    - Paths that resolve outside allowed scopes

    For relative paths without separators (e.g., "file.txt"), treats them as
    relative to each allowed scope and checks if the resulting path is within that scope.
    """
    if not path or not isinstance(path, str):
        return None

    # Reject absolute paths
    if os.path.isabs(path):
        return None

    # Reject path traversal attempts
    path_parts = path.split(os.sep)
    if ".." in path_parts:
        return None

    # Check against each allowed scope
    for scope in allowed_scopes:
        try:
            scope_path = os.path.normpath(scope)
            # Join the relative path with the scope to get the full requested path
            requested_path = os.path.normpath(os.path.join(scope_path, path))

            # Verify the requested path is within the scope
            rel_path = os.path.relpath(requested_path, scope_path)
            if not rel_path.startswith("..") and not os.path.isabs(rel_path):
                return requested_path
        except ValueError:
            # Cross-device on Windows, etc. - not within this scope
            continue
        except Exception:
            continue

    return None


def is_within_scope(path: str, allowed_scopes: List[str]) -> bool:
    """Check if a path resolves within any of the allowed scopes."""
    return resolve_within_scope(path, allowed_scopes) is not None


def get_allowed_scopes_for_capability(capability_name: str) -> List[str]:
    """Get the allowed filesystem scopes for a capability."""
    return CAPABILITY_SCOPES.get(capability_name, [])


def extract_paths_from_arguments(arguments: dict, capability_name: str) -> List[str]:
    """Extract potential filesystem paths from capability arguments."""
    paths = []

    if not arguments or not isinstance(arguments, dict):
        return paths

    path_arg_keys = {
        "extract_document": ["document_id"],
        "execute_code": ["input_files"],
        "create_docx": [],
        "create_xlsx": [],
        "create_pptx": [],
        "search_knowledge_base": [],
        "generate_code": [],
    }

    keys = path_arg_keys.get(capability_name, [])

    for key in keys:
        value = arguments.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            paths.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    paths.append(item)

    return paths