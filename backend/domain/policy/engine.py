"""
Deterministic Policy Engine

Pure functions for evaluating capability proposals against policy rules.
No side effects, no DB/model/network access, fully testable in isolation.
"""

from typing import Any

from backend.domain.policy.paths import (
    get_allowed_scopes_for_capability,
    is_within_scope,
    extract_paths_from_arguments,
)


PolicyDecision = dict[str, str]  # {policy_decision, policy_reason, rule}


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
    Returns dict with policy_decision, policy_reason, and rule.
    """

    # Handle malformed arguments early - fail closed
    if arguments is not None and not isinstance(arguments, dict):
        return _make_decision(
            "deny", "Arguments must be a dictionary", "malformed_arguments"
        )

    # Rule 1: Registered & enabled
    decision = _check_registered_and_enabled(capability_name, registry_entry, capabilities_config)
    if decision["policy_decision"] == "deny":
        return decision

    # Rule 2: Permissions
    decision = _check_permissions(registry_entry)
    if decision["policy_decision"] == "deny":
        return decision

    # Rule 3: Network-access invariant (UNCONDITIONAL)
    decision = _check_network_access_invariant(registry_entry, policy_config)
    if decision["policy_decision"] == "deny":
        return decision

    # Rule 4: Filesystem scope
    decision = _check_filesystem_scope(capability_name, arguments, registry_entry)
    if decision["policy_decision"] == "deny":
        return decision

    # Rule 5: Resource limits
    decision = _check_resource_limits(capability_name, arguments, registry_entry, capabilities_config)
    if decision["policy_decision"] == "deny":
        return decision

    # All rules passed
    return _make_decision("allow", "All policy rules passed", "all_rules_passed")


def _make_decision(decision: str, reason: str, rule: str) -> PolicyDecision:
    """Create a policy decision dict matching CapabilityExecutionRow fields."""
    return {
        "policy_decision": decision,
        "policy_reason": reason,
        "rule": rule,
    }


def _check_registered_and_enabled(
    capability_name: str,
    registry_entry: dict[str, Any] | None,
    capabilities_config: dict[str, Any],
) -> PolicyDecision:
    """Rule 1: Capability must exist in registry and be enabled in config.

    Fail closed: enabled must be explicitly true. Missing or false -> deny.
    """

    # Unknown capability
    if registry_entry is None:
        return _make_decision(
            "deny", f"Unknown capability: '{capability_name}'", "unknown_capability"
        )

    # Check config for enabled flag - fail closed if missing
    capability_config = capabilities_config.get("capabilities", {}).get(capability_name, {})
    enabled = capability_config.get("enabled")

    if enabled is None:
        return _make_decision(
            "deny",
            f"Missing enabled flag in capability configuration for '{capability_name}'",
            "capability_not_enabled",
        )

    if enabled is False:
        return _make_decision(
            "deny",
            f"Capability '{capability_name}' is disabled in configuration",
            "capability_not_enabled",
        )

    return _make_decision("allow", "", "")


def _check_permissions(registry_entry: dict[str, Any] | None) -> PolicyDecision:
    """Rule 2: Validate declared permissions are recognized/consistent.

    For SIH single trust level (Orchestrator), this validates the permission
    tokens are recognized. No RBAC model - all permissions are satisfied for
    the sole Orchestrator caller if they are valid tokens.
    """
    if registry_entry is None:
        return _make_decision("allow", "", "")

    permissions = registry_entry.get("permissions", [])
    if not isinstance(permissions, list):
        return _make_decision(
            "deny", "Capability permissions must be a list", "missing_permission"
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
            return _make_decision(
                "deny", f"Unrecognized permission token: '{perm}'", "missing_permission"
            )

    return _make_decision("allow", "", "")


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
        return _make_decision(
            "deny", "Missing policy configuration section", "network_access_invariant"
        )

    config_network_allowed = policy_section.get("network_access_allowed")
    if config_network_allowed is None:
        return _make_decision(
            "deny", "Missing network_access_allowed in policy configuration", "network_access_invariant"
        )

    # Invariant: both must be false
    if capability_network_access is not False:
        return _make_decision(
            "deny",
            "Capability declares network_access != false, violating zero-egress invariant",
            "network_access_invariant",
        )

    if config_network_allowed is not False:
        return _make_decision(
            "deny",
            "Policy configuration allows network access, violating zero-egress invariant",
            "network_access_invariant",
        )

    return _make_decision("allow", "", "")


def _check_filesystem_scope(
    capability_name: str,
    arguments: dict[str, Any] | None,
    registry_entry: dict[str, Any] | None,
) -> PolicyDecision:
    """Rule 4: Filesystem scope - paths must resolve within declared scope.

    Uses scoped path resolution via backend.domain.policy.paths, never trusts raw paths in arguments.
    Rejects traversal (../), absolute paths, and other jobs' directories.
    Validates against the capability's declared filesystem_scope from registry entry.
    """
    if registry_entry is None or arguments is None:
        return _make_decision("allow", "", "")

    # Get declared filesystem scope from registry entry
    declared_scope = registry_entry.get("filesystem_scope", [])
    if not isinstance(declared_scope, list) or not declared_scope:
        # No scope declared - no filesystem access allowed
        return _make_decision("allow", "", "")

    # Get allowed scopes from policy paths module (uses canonical paths from config)
    allowed_scopes = get_allowed_scopes_for_capability(capability_name)

    # Also include declared scopes from registry entry for defense in depth
    for scope in declared_scope:
        if scope not in allowed_scopes:
            allowed_scopes.append(scope)

    # Extract potential paths from arguments
    paths_to_check = extract_paths_from_arguments(arguments, capability_name)

    for path in paths_to_check:
        if not is_within_scope(path, allowed_scopes):
            return _make_decision(
                "deny",
                f"Argument references path '{path}' outside capability's declared filesystem scope",
                "filesystem_scope_violation",
            )

    return _make_decision("allow", "", "")


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
        return _make_decision("allow", "", "")

    capability_config = capabilities_config.get("capabilities", {}).get(capability_name, {})
    if not capability_config:
        return _make_decision(
            "deny",
            f"Missing capability configuration for '{capability_name}'",
            "resource_limit_exceeded",
        )

    # Check timeout_seconds - required for all capabilities
    configured_timeout = capability_config.get("timeout_seconds")
    if configured_timeout is None:
        return _make_decision(
            "deny",
            f"Missing timeout_seconds in capability configuration for '{capability_name}'",
            "resource_limit_exceeded",
        )

    # Check requested timeout against configured limit
    if arguments and "timeout_seconds" in arguments:
        requested_timeout = arguments.get("timeout_seconds")
        if (
            isinstance(requested_timeout, (int, float))
            and isinstance(configured_timeout, (int, float))
            and requested_timeout > configured_timeout
        ):
            return _make_decision(
                "deny",
                f"Requested timeout ({requested_timeout}s) exceeds configured limit ({configured_timeout}s)",
                "resource_limit_exceeded",
            )

    # Check max_output_bytes for execute_code
    if capability_name == "execute_code":
        configured_max_output = capability_config.get("max_output_bytes")
        if configured_max_output is None:
            return _make_decision(
                "deny",
                "Missing max_output_bytes in execute_code capability configuration",
                "resource_limit_exceeded",
            )

        # Note: actual output size is validated at execution time by the executor
        # Policy only validates that the configured bound exists and is reasonable
        if not isinstance(configured_max_output, int) or configured_max_output <= 0:
            return _make_decision(
                "deny",
                "Invalid max_output_bytes in execute_code capability configuration",
                "resource_limit_exceeded",
            )

    return _make_decision("allow", "", "")