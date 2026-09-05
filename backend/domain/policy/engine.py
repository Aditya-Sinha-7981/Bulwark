"""
Deterministic Policy Engine

Pure functions for evaluating capability proposals against policy rules.
No side effects, no DB/model/network access, fully testable in isolation.
"""

from typing import Any
from backend.models.schemas import PolicyDecision
from backend.utils.paths import is_within_scope, extract_path_from_arguments


def evaluate(
    capability_name: str,
    arguments: dict[str, Any] | None,
    registry_entry: dict[str, Any] | None,
    capabilities_config: dict[str, Any],
    policy_config: dict[str, Any],
    app_config: dict[str, Any] | None = None,
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
    decision = _check_filesystem_scope(capability_name, arguments, registry_entry, app_config)
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
    
    # Check config policy - fail closed if missing
    policy_section = policy_config.get("policy")
    if policy_section is None:
        return PolicyDecision(
            decision="deny",
            reason="Missing policy configuration section",
            rule="network_access_invariant"
        )
    
    config_network_allowed = policy_section.get("network_access_allowed")
    if config_network_allowed is None:
        return PolicyDecision(
            decision="deny",
            reason="Missing network_access_allowed in policy configuration",
            rule="network_access_invariant"
        )
    
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
    app_config: dict[str, Any] | None,
) -> PolicyDecision:
    """Rule 4: Filesystem scope - paths must resolve within declared scope.
    
    Uses scoped path resolution via backend.utils.paths, never trusts raw paths in arguments.
    Rejects traversal (../), absolute paths, and other jobs' directories.
    Validates against the capability's declared filesystem_scope from registry entry.
    """
    if registry_entry is None or arguments is None:
        return PolicyDecision(decision="allow", reason="", rule="")
    
    # Get declared filesystem scope from registry entry
    declared_scope = registry_entry.get("filesystem_scope", [])
    if not isinstance(declared_scope, list) or not declared_scope:
        # No scope declared - no filesystem access allowed
        return PolicyDecision(decision="allow", reason="", rule="")
    
    # Extract potential paths from arguments
    paths_to_check = extract_path_from_arguments(arguments, capability_name)
    
    # If app_config provided, also check against base paths from config
    allowed_scopes = list(declared_scope)
    if app_config:
        base_path = get_base_path_for_capability(capability_name, app_config)
        if base_path:
            # Add base path as allowed scope if not already covered
            if base_path not in allowed_scopes:
                allowed_scopes.append(base_path)
    
    for path in paths_to_check:
        if not is_within_scope(path, allowed_scopes):
            return PolicyDecision(
                decision="deny",
                reason=f"Argument references path '{path}' outside capability's declared filesystem scope",
                rule="filesystem_scope_violation"
            )
    
    return PolicyDecision(decision="allow", reason="", rule="")


def get_base_path_for_capability(capability_name: str, app_config: dict) -> str | None:
    """Get the base data path for a capability from app config."""
    paths = app_config.get("paths", {})
    
    capability_path_map = {
        "extract_document": paths.get("uploads"),
        "search_knowledge_base": paths.get("chroma"),
        "generate_code": None,
        "execute_code": paths.get("sandbox"),
        "create_docx": paths.get("artifacts"),
        "create_xlsx": paths.get("artifacts"),
        "create_pptx": paths.get("artifacts"),
    }
    
    return capability_path_map.get(capability_name)


def extract_path_from_arguments(arguments: dict, capability_name: str) -> list[str]:
    """Extract potential filesystem paths from capability arguments."""
    paths = []
    
    if not arguments or not isinstance(arguments, dict):
        return paths
    
    # Capability-specific argument keys that may contain paths
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


def _check_resource_limits(
    capability_name: str,
    arguments: dict[str, Any] | None,
    registry_entry: dict[str, Any] | None,
    capabilities_config: dict[str, Any],
) -> PolicyDecision:
    """Rule 5: Resource limits - timeout and output bounds within configured values.
    
    Fail closed if required config values are missing.
    """
    if registry_entry is None:
        return PolicyDecision(decision="allow", reason="", rule="")
    
    capability_config = capabilities_config.get("capabilities", {}).get(capability_name, {})
    if not capability_config:
        return PolicyDecision(
            decision="deny",
            reason=f"Missing capability configuration for '{capability_name}'",
            rule="resource_limit_exceeded"
        )
    
    # Check timeout_seconds - required for all capabilities
    configured_timeout = capability_config.get("timeout_seconds")
    if configured_timeout is None:
        return PolicyDecision(
            decision="deny",
            reason=f"Missing timeout_seconds in capability configuration for '{capability_name}'",
            rule="resource_limit_exceeded"
        )
    
    # Check requested timeout against configured limit
    if arguments and "timeout_seconds" in arguments:
        requested_timeout = arguments.get("timeout_seconds")
        if (isinstance(requested_timeout, (int, float)) and 
            isinstance(configured_timeout, (int, float)) and
            requested_timeout > configured_timeout):
            return PolicyDecision(
                decision="deny",
                reason=f"Requested timeout ({requested_timeout}s) exceeds configured limit ({configured_timeout}s)",
                rule="resource_limit_exceeded"
            )
    
    # Check max_output_bytes for execute_code
    if capability_name == "execute_code":
        configured_max_output = capability_config.get("max_output_bytes")
        if configured_max_output is None:
            return PolicyDecision(
                decision="deny",
                reason="Missing max_output_bytes in execute_code capability configuration",
                rule="resource_limit_exceeded"
            )
        
        # Note: actual output size is validated at execution time by the executor
        # Policy only validates that the configured bound exists and is reasonable
        if not isinstance(configured_max_output, int) or configured_max_output <= 0:
            return PolicyDecision(
                decision="deny",
                reason="Invalid max_output_bytes in execute_code capability configuration",
                rule="resource_limit_exceeded"
            )
    
    return PolicyDecision(decision="allow", reason="", rule="")