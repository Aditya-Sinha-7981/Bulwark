"""
Scoped filesystem path helpers for Policy engine.

Provides safe path resolution within declared capability filesystem scopes.
No external dependencies, cross-platform (Windows/macOS).
"""

import os
from typing import List


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
    """
    Check if a path resolves within any of the allowed scopes.
    
    Returns True if path is within scope, False otherwise.
    """
    return resolve_within_scope(path, allowed_scopes) is not None


def get_base_path_for_capability(capability_name: str, app_config: dict) -> str | None:
    """
    Get the base data path for a capability from app config.
    
    Reads from config/app.yaml paths section.
    """
    paths = app_config.get("paths", {})
    
    capability_path_map = {
        "extract_document": paths.get("uploads"),
        "search_knowledge_base": paths.get("chroma"),
        "generate_code": None,  # No filesystem access
        "execute_code": paths.get("sandbox"),
        "create_docx": paths.get("artifacts"),
        "create_xlsx": paths.get("artifacts"),
        "create_pptx": paths.get("artifacts"),
    }
    
    return capability_path_map.get(capability_name)


def extract_path_from_arguments(arguments: dict, capability_name: str) -> List[str]:
    """
    Extract potential filesystem paths from capability arguments.
    
    Returns a list of path strings found in the arguments.
    """
    paths = []
    
    if not arguments or not isinstance(arguments, dict):
        return paths
    
    # Capability-specific argument keys that may contain paths
    path_arg_keys = {
        "extract_document": ["document_id"],
        "execute_code": ["input_files"],
        "create_docx": [],  # Output handled by artifact system
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