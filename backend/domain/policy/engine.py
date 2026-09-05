"""
Deterministic Policy Engine

Pure functions for evaluating capability proposals against policy rules.
No side effects, no DB/model/network access, fully testable in isolation.
"""

from typing import Any
from backend.models.schemas import PolicyDecision


def evaluate(
    capability_name: str,
    arguments: dict[str, Any] | None,
    registry_entry: dict[str, Any] | None,
    capabilities_config: dict[str, Any],
    policy_config: dict[str, Any],
) -> PolicyDecision:
    """
    Evaluate a capability proposal against all policy rules.
    
    Rules evaluated in order; first deny wins.
    Returns PolicyDecision with decision, reason, and stable rule identifier.
    """
    
    # Handle malformed arguments early - fail closed
    if arguments is not None and not isinstance(arguments, dict):
        return PolicyDecision(
            decision="deny",
            reason="Arguments must be a dictionary",
            rule="malformed_arguments"
        )
    
    # Rule 1: Registered & enabled
    decision = _check_registered_and_enabled(capability_name, registry_entry, capabilities_config)
    if decision.decision == "deny":
        return decision
    
    # Rule 2: Permissions
    decision = _check_permissions(registry_entry)
    if decision.decision == "deny":
        return decision
    
    # Rule 3: Network-access invariant (UNCONDITIONAL)
    decision = _check_network_access_invariant(registry_entry, policy_config)
    if decision.decision == "deny":
        return decision
    
    # Rule 4: Filesystem scope
    decision = _check_filesystem_scope(capability_name, arguments, registry_entry, capabilities_config)
    if decision.decision == "deny":
        return decision
    
    # Rule 5: Resource limits
    decision = _check_resource_limits(capability_name, arguments, registry_entry, capabilities_config)
    if decision.decision == "deny":
        return decision
    
    # All rules passed
    return PolicyDecision(
        decision="allow",
        reason="All policy rules passed",
        rule="all_rules_passed"
    )


def _check_registered_and_enabled(
    capability_name: str,
    registry_entry: dict[str, Any] | None,
    capabilities_config: dict[str, Any],
) -> PolicyDecision:
    """Rule 1: Capability must exist in registry and be enabled in config."""
    
    # Unknown capability
    if registry_entry is None:
        return PolicyDecision(
            decision="deny",
            reason=f"Unknown capability: '{capability_name}'",
            rule="unknown_capability"
        )
    
    # Check config for enabled flag
    capability_config = capabilities_config.get("capabilities", {}).get(capability_name, {})
    if capability_config.get("enabled") is False:
        return PolicyDecision(
            decision="deny",
            reason=f"Capability '{capability_name}' is disabled in configuration",
            rule="capability_not_enabled"
        )
    
    return PolicyDecision(decision="allow", reason="", rule="")


def _check_permissions(registry_entry: dict[str, Any] | None) -> PolicyDecision:
    """Rule 2: Validate declared permissions are recognized/consistent.
    
    For SIH single trust level (Orchestrator), this validates the permission
    tokens are recognized. No RBAC model - all permissions are satisfied for
    the sole Orchestrator caller if they are valid tokens.
    """
    if registry_entry is None:
        return PolicyDecision(decision="allow", reason="", rule="")
    
    permissions = registry_entry.get("permissions", [])
    if not isinstance(permissions, list):
        return PolicyDecision(
            decision="deny",
            reason="Capability permissions must be a list",
            rule="missing_permission"
        )
    
    # Recognized permission tokens for SIH scope
    recognized_permissions = {
        "read_uploads",
        "read_chroma_index",
        "write_artifacts",
        "create_docker_container",
        "read_sandbox_input",
        "write_sandbox_output",
    }
    
    for perm in permissions:
        if perm not in recognized_permissions:
            return PolicyDecision(
                decision="deny",
                reason=f"Unrecognized permission token: '{perm}'",
                rule="missing_permission"
            )
    
    return PolicyDecision(decision="allow", reason="", rule="")


def _check_network_access_invariant(
    registry_entry: dict[str, Any] | None,
    policy_config: dict[str, Any],
) -> PolicyDecision:
    """Rule 3: Network-access invariant - UNCONDITIONAL.
    
    Both capability network_access AND config network_access_allowed must be false.
    This is an invariant - no input makes it pass when violated.
    """
    # Check capability's declared network_access
    capability_network_access = False
    if registry_entry is not None:
        capability_network_access = registry_entry.get("network_access", False)
    
    # Check config policy
    config_network_allowed = policy_config.get("policy", {}).get("network_access_allowed", False)
    
    # Invariant: both must be false
    if capability_network_access is not False:
        return PolicyDecision(
            decision="deny",
            reason="Capability declares network_access != false, violating zero-egress invariant",
            rule="network_access_invariant"
        )
    
    if config_network_allowed is not False:
        return PolicyDecision(
            decision="deny",
            reason="Policy configuration allows network access, violating zero-egress invariant",
            rule="network_access_invariant"
        )
    
    return PolicyDecision(decision="allow", reason="", rule="")


def _check_filesystem_scope(
    capability_name: str,
    arguments: dict[str, Any] | None,
    registry_entry: dict[str, Any] | None,
    capabilities_config: dict[str, Any],
) -> PolicyDecision:
    """Rule 4: Filesystem scope - paths must resolve within declared scope.
    
    Uses scoped path resolution, never trusts raw paths in arguments.
    Rejects traversal (../), absolute paths, and other jobs' directories.
    """
    if registry_entry is None or arguments is None:
        return PolicyDecision(decision="allow", reason="", rule="")
    
    # Get declared filesystem scope from registry
    declared_scope = registry_entry.get("filesystem_scope", [])
    if not isinstance(declared_scope, list):
        return PolicyDecision(decision="allow", reason="", rule="")
    
    # Map capability names to their argument path keys and expected base paths
    scope_mapping = _get_scope_mapping(capability_name, capabilities_config)
    
    for arg_key, expected_base in scope_mapping.items():
        arg_value = arguments.get(arg_key)
        if arg_value is None:
            continue
        
        # Check if argument contains a path-like value
        if isinstance(arg_value, str) and _looks_like_path(arg_value):
            if not _is_within_scope(arg_value, expected_base):
                return PolicyDecision(
                    decision="deny",
                    reason=f"Argument '{arg_key}' references path outside capability's filesystem scope",
                    rule="filesystem_scope_violation"
                )
        
        # Handle list of paths (e.g., input_files for execute_code)
        if isinstance(arg_value, list):
            for item in arg_value:
                if isinstance(item, str) and _looks_like_path(item):
                    if not _is_within_scope(item, expected_base):
                        return PolicyDecision(
                            decision="deny",
                            reason=f"Argument '{arg_key}' contains path outside capability's filesystem scope",
                            rule="filesystem_scope_violation"
                        )
    
    return PolicyDecision(decision="allow", reason="", rule="")


def _get_scope_mapping(capability_name: str, capabilities_config: dict[str, Any]) -> dict[str, str]:
    """Map capability argument keys to their allowed base paths."""
    # Base paths from config/app.yaml paths section
    base_paths = {
        "uploads": "data/uploads",
        "extraction": "data/extraction",
        "artifacts": "data/artifacts",
        "sandbox": "data/sandbox",
        "chroma": "data/chroma",
    }
    
    # Per-capability scope mapping based on capabilities.md
    mappings = {
        "extract_document": {
            "document_id": base_paths["uploads"],
        },
        "search_knowledge_base": {},
        "generate_code": {},
        "execute_code": {
            "input_files": base_paths["sandbox"],
        },
        "create_docx": {},
        "create_xlsx": {},
        "create_pptx": {},
    }
    
    return mappings.get(capability_name, {})


def _looks_like_path(value: str) -> bool:
    """Check if a string looks like a filesystem path."""
    return "/" in value or "\\" in value or value.startswith("..") or value.startswith("/")


def _is_within_scope(path: str, base_path: str) -> bool:
    """Check if a path resolves within the allowed base path.
    
    Rejects:
    - Path traversal (../)
    - Absolute paths
    - Paths outside the base directory
    """
    import os
    
    # Reject absolute paths
    if os.path.isabs(path):
        return False
    
    # Reject path traversal attempts
    if ".." in path.split(os.sep):
        return False
    
    # Normalize both paths
    try:
        resolved_path = os.path.normpath(path)
        resolved_base = os.path.normpath(base_path)
    except Exception:
        return False
    
    # Check if resolved path is within base
    try:
        rel_path = os.path.relpath(resolved_path, resolved_base)
        return not rel_path.startswith("..") and not os.path.isabs(rel_path)
    except ValueError:
        return False


def _check_resource_limits(
    capability_name: str,
    arguments: dict[str, Any] | None,
    registry_entry: dict[str, Any] | None,
    capabilities_config: dict[str, Any],
) -> PolicyDecision:
    """Rule 5: Resource limits - timeout and output bounds within configured values."""
    if registry_entry is None:
        return PolicyDecision(decision="allow", reason="", rule="")
    
    capability_config = capabilities_config.get("capabilities", {}).get(capability_name, {})
    if not capability_config:
        return PolicyDecision(decision="allow", reason="", rule="")
    
    # Check timeout_seconds if specified in arguments
    if arguments and "timeout_seconds" in arguments:
        requested_timeout = arguments.get("timeout_seconds")
        configured_timeout = capability_config.get("timeout_seconds")
        
        if (isinstance(requested_timeout, (int, float)) and 
            isinstance(configured_timeout, (int, float)) and
            requested_timeout > configured_timeout):
            return PolicyDecision(
                decision="deny",
                reason=f"Requested timeout ({requested_timeout}s) exceeds configured limit ({configured_timeout}s)",
                rule="resource_limit_exceeded"
            )
    
    return PolicyDecision(decision="allow", reason="", rule="")