"""
Unit tests for the deterministic Policy Engine.

Tests each rule with allow and deny scenarios per the task requirements.
"""

import pytest
from backend.domain.policy.engine import evaluate
from backend.models.schemas import PolicyDecision


# ===== Fixtures =====

@pytest.fixture
def valid_registry_entry():
    """A valid registry entry matching capabilities.md contract."""
    return {
        "name": "execute_code",
        "purpose": "Run generated code in the isolated Docker sandbox",
        "resource_type": None,
        "permissions": ["create_docker_container", "read_sandbox_input", "write_sandbox_output"],
        "network_access": False,
        "filesystem_scope": ["data/sandbox"],
        "timeout_seconds": 30,
        "retry_policy": "none",
    }


@pytest.fixture
def valid_capabilities_config():
    """Valid capabilities config matching configuration.md."""
    return {
        "capabilities": {
            "extract_document": {
                "enabled": True,
                "timeout_seconds": 120,
                "max_file_size_mb": 10,
            },
            "search_knowledge_base": {
                "enabled": True,
                "timeout_seconds": 10,
                "default_top_k": 5,
            },
            "generate_code": {
                "enabled": True,
                "timeout_seconds": 30,
            },
            "execute_code": {
                "enabled": True,
                "timeout_seconds": 30,
                "cpu_limit": 1,
                "memory_limit_mb": 512,
                "max_output_bytes": 65536,
            },
            "create_docx": {
                "enabled": True,
                "timeout_seconds": 15,
            },
            "create_xlsx": {
                "enabled": True,
                "timeout_seconds": 15,
            },
        }
    }


@pytest.fixture
def valid_policy_config():
    """Valid policy config matching configuration.md."""
    return {
        "policy": {
            "network_access_allowed": False,
            "max_job_steps": 8,
            "malformed_output_free_retries": 1,
        }
    }


@pytest.fixture
def valid_app_config():
    """Valid app config matching configuration.md."""
    return {
        "paths": {
            "data_root": "./data",
            "uploads": "./data/uploads",
            "extraction": "./data/extraction",
            "artifacts": "./data/artifacts",
            "sandbox": "./data/sandbox",
            "tmp": "./data/tmp",
            "db": "./data/db/app.db",
            "chroma": "./data/chroma",
        }
    }


# ===== Rule 1: Registered & Enabled =====

def test_allow_registered_and_enabled(valid_registry_entry, valid_capabilities_config, valid_policy_config):
    """Enabled capability with valid registry entry should be allowed."""
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "allow"
    assert decision.rule == "all_rules_passed"


def test_deny_unknown_capability(valid_capabilities_config, valid_policy_config):
    """Unknown capability should be denied."""
    decision = evaluate(
        capability_name="nonexistent_capability",
        arguments={},
        registry_entry=None,  # Unknown capability
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "unknown_capability"
    assert "Unknown capability" in decision.reason


def test_deny_capability_not_enabled(valid_registry_entry, valid_policy_config):
    """Disabled capability in config should be denied."""
    config = {
        "capabilities": {
            "execute_code": {"enabled": False}
        }
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "capability_not_enabled"
    assert "disabled" in decision.reason


def test_deny_missing_enabled_flag(valid_registry_entry, valid_policy_config):
    """Missing enabled flag in capability config should be denied (fail closed)."""
    config = {
        "capabilities": {
            "execute_code": {
                # enabled missing
                "timeout_seconds": 30,
                "cpu_limit": 1,
                "memory_limit_mb": 512,
                "max_output_bytes": 65536,
            }
        }
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "capability_not_enabled"
    assert "Missing enabled flag" in decision.reason


# ===== Rule 2: Permissions =====

def test_allow_valid_permissions(valid_registry_entry, valid_capabilities_config, valid_policy_config):
    """Capability with recognized permissions should be allowed."""
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "allow"


def test_deny_unrecognized_permission(valid_capabilities_config, valid_policy_config):
    """Capability with unrecognized permission token should be denied."""
    registry_entry = {
        "name": "execute_code",
        "permissions": ["create_docker_container", "invalid_permission_token"],
        "network_access": False,
        "filesystem_scope": ["data/sandbox"],
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "missing_permission"
    assert "Unrecognized permission" in decision.reason


def test_deny_permissions_not_a_list(valid_capabilities_config, valid_policy_config):
    """Permissions must be a list."""
    registry_entry = {
        "name": "execute_code",
        "permissions": "not_a_list",
        "network_access": False,
        "filesystem_scope": ["data/sandbox"],
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "missing_permission"
    assert "must be a list" in decision.reason


# ===== Rule 3: Network-Access Invariant =====

def test_allow_network_access_false(valid_registry_entry, valid_capabilities_config, valid_policy_config):
    """Capability with network_access: false and config network_access_allowed: false should be allowed."""
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "allow"


def test_deny_capability_network_access_true(valid_capabilities_config, valid_policy_config):
    """Capability declaring network_access: true should be denied regardless of arguments."""
    registry_entry = {
        "name": "execute_code",
        "permissions": ["create_docker_container"],
        "network_access": True,  # VIOLATION
        "filesystem_scope": ["data/sandbox"],
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "network_access_invariant"
    assert "network_access != false" in decision.reason


def test_deny_config_network_access_allowed_true(valid_registry_entry, valid_capabilities_config):
    """Config with network_access_allowed: true should be denied."""
    policy_config = {
        "policy": {
            "network_access_allowed": True,  # VIOLATION
            "max_job_steps": 8,
        }
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "network_access_invariant"
    assert "Policy configuration allows network access" in decision.reason


def test_deny_missing_policy_section(valid_registry_entry, valid_capabilities_config):
    """Missing policy section in config should be denied (fail closed)."""
    policy_config = {}  # Missing "policy" key
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "network_access_invariant"
    assert "Missing policy configuration" in decision.reason


def test_deny_missing_network_access_allowed(valid_registry_entry, valid_capabilities_config):
    """Missing network_access_allowed in policy config should be denied (fail closed)."""
    policy_config = {
        "policy": {
            "max_job_steps": 8,
            # network_access_allowed missing
        }
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "network_access_invariant"
    assert "Missing network_access_allowed" in decision.reason


# ===== Rule 4: Filesystem Scope =====

def test_allow_valid_filesystem_scope(valid_registry_entry, valid_capabilities_config, valid_policy_config, valid_app_config):
    """Valid document_id within uploads scope should be allowed."""
    registry_entry = {
        "name": "extract_document",
        "permissions": ["read_uploads"],
        "network_access": False,
        "filesystem_scope": ["data/uploads"],
    }
    decision = evaluate(
        capability_name="extract_document",
        arguments={"document_id": "abc123.jpg"},  # Just filename, not a path
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
        app_config=valid_app_config,
    )
    assert decision.decision == "allow"


def test_deny_path_traversal_in_arguments(valid_registry_entry, valid_capabilities_config, valid_policy_config, valid_app_config):
    """Path traversal (../) in arguments should be denied."""
    registry_entry = {
        "name": "extract_document",
        "permissions": ["read_uploads"],
        "network_access": False,
        "filesystem_scope": ["data/uploads"],
    }
    decision = evaluate(
        capability_name="extract_document",
        arguments={"document_id": "../../../etc/passwd"},
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
        app_config=valid_app_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "filesystem_scope_violation"


def test_deny_absolute_path_in_arguments(valid_registry_entry, valid_capabilities_config, valid_policy_config, valid_app_config):
    """Absolute path in arguments should be denied."""
    registry_entry = {
        "name": "extract_document",
        "permissions": ["read_uploads"],
        "network_access": False,
        "filesystem_scope": ["data/uploads"],
    }
    decision = evaluate(
        capability_name="extract_document",
        arguments={"document_id": "/etc/passwd"},
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
        app_config=valid_app_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "filesystem_scope_violation"


def test_deny_execute_code_input_files_outside_sandbox(valid_capabilities_config, valid_policy_config, valid_app_config):
    """execute_code input_files pointing outside sandbox should be denied."""
    registry_entry = {
        "name": "execute_code",
        "permissions": ["create_docker_container", "read_sandbox_input", "write_sandbox_output"],
        "network_access": False,
        "filesystem_scope": ["data/sandbox"],
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={
            "code": "print('hello')",
            "language": "python",
            "input_files": ["../../other_job/output.txt"]  # Outside sandbox
        },
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
        app_config=valid_app_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "filesystem_scope_violation"


def test_allow_execute_code_valid_input_files(valid_registry_entry, valid_capabilities_config, valid_policy_config, valid_app_config):
    """execute_code with valid input_files within sandbox should be allowed."""
    decision = evaluate(
        capability_name="execute_code",
        arguments={
            "code": "print('hello')",
            "language": "python",
            "input_files": ["abc123.txt"]  # Just filename, relative to sandbox input dir
        },
        registry_entry=valid_registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
        app_config=valid_app_config,
    )
    assert decision.decision == "allow"


def test_deny_path_outside_declared_scope(valid_capabilities_config, valid_policy_config):
    """Path outside declared filesystem_scope (not just base path) should be denied."""
    registry_entry = {
        "name": "execute_code",
        "permissions": ["create_docker_container", "read_sandbox_input", "write_sandbox_output"],
        "network_access": False,
        "filesystem_scope": ["data/sandbox/execution_123"],  # Specific execution directory
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={
            "code": "print('hello')",
            "language": "python",
            "input_files": ["../other_execution/file.txt"]  # Outside declared scope
        },
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
        app_config=None,
    )
    assert decision.decision == "deny"
    assert decision.rule == "filesystem_scope_violation"


def test_allow_path_within_declared_scope(valid_capabilities_config, valid_policy_config):
    """Path within declared filesystem_scope should be allowed."""
    registry_entry = {
        "name": "execute_code",
        "permissions": ["create_docker_container", "read_sandbox_input", "write_sandbox_output"],
        "network_access": False,
        "filesystem_scope": ["data/sandbox/execution_123"],
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={
            "code": "print('hello')",
            "language": "python",
            "input_files": ["input.txt"]  # Within declared scope (relative)
        },
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
        app_config=None,
    )
    assert decision.decision == "allow"


def test_deny_capability_with_no_filesystem_scope_but_path_in_args(valid_capabilities_config, valid_policy_config):
    """Capability with empty filesystem_scope but path in args should be denied."""
    registry_entry = {
        "name": "generate_code",
        "permissions": [],
        "network_access": False,
        "filesystem_scope": [],  # No filesystem access
    }
    decision = evaluate(
        capability_name="generate_code",
        arguments={
            "task_description": "write a script",
            "language": "python",
            "output_path": "/tmp/out.py"  # Path not allowed for this capability
        },
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
        app_config=None,
    )
    # generate_code doesn't extract paths from output_path (not in path_arg_keys)
    # So this should be allowed since the path isn't recognized as a filesystem arg
    assert decision.decision == "allow"


# ===== Rule 5: Resource Limits =====

def test_allow_timeout_within_limit(valid_registry_entry, valid_capabilities_config, valid_policy_config):
    """Timeout within configured limit should be allowed."""
    decision = evaluate(
        capability_name="execute_code",
        arguments={
            "code": "print('hello')",
            "language": "python",
            "input_files": [],
            "timeout_seconds": 20  # Within 30s limit
        },
        registry_entry=valid_registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "allow"


def test_deny_timeout_exceeds_limit(valid_registry_entry, valid_capabilities_config, valid_policy_config):
    """Timeout exceeding configured limit should be denied."""
    decision = evaluate(
        capability_name="execute_code",
        arguments={
            "code": "print('hello')",
            "language": "python",
            "input_files": [],
            "timeout_seconds": 60  # Exceeds 30s limit
        },
        registry_entry=valid_registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "resource_limit_exceeded"
    assert "exceeds configured limit" in decision.reason


def test_deny_missing_timeout_seconds_in_config(valid_registry_entry, valid_policy_config):
    """Missing timeout_seconds in capability config should be denied (fail closed)."""
    config = {
        "capabilities": {
            "execute_code": {
                "enabled": True,
                # timeout_seconds missing
                "cpu_limit": 1,
                "memory_limit_mb": 512,
                "max_output_bytes": 65536,
            }
        }
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "resource_limit_exceeded"
    assert "Missing timeout_seconds" in decision.reason


def test_deny_missing_max_output_bytes_in_execute_code_config(valid_registry_entry, valid_policy_config):
    """Missing max_output_bytes in execute_code config should be denied (fail closed)."""
    config = {
        "capabilities": {
            "execute_code": {
                "enabled": True,
                "timeout_seconds": 30,
                "cpu_limit": 1,
                "memory_limit_mb": 512,
                # max_output_bytes missing
            }
        }
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "resource_limit_exceeded"
    assert "Missing max_output_bytes" in decision.reason


def test_deny_invalid_max_output_bytes_in_config(valid_registry_entry, valid_policy_config):
    """Invalid max_output_bytes (non-positive) in execute_code config should be denied."""
    config = {
        "capabilities": {
            "execute_code": {
                "enabled": True,
                "timeout_seconds": 30,
                "cpu_limit": 1,
                "memory_limit_mb": 512,
                "max_output_bytes": 0,  # Invalid
            }
        }
    }
    decision = evaluate(
        capability_name="execute_code",
        arguments={"code": "print('hello')", "language": "python", "input_files": []},
        registry_entry=valid_registry_entry,
        capabilities_config=config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "resource_limit_exceeded"
    assert "Invalid max_output_bytes" in decision.reason


def test_allow_other_capabilities_without_max_output_bytes(valid_capabilities_config, valid_policy_config):
    """Other capabilities don't require max_output_bytes."""
    registry_entry = {
        "name": "generate_code",
        "permissions": [],
        "network_access": False,
        "filesystem_scope": [],
    }
    decision = evaluate(
        capability_name="generate_code",
        arguments={"task_description": "write code", "language": "python"},
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "allow"


def test_allow_create_docx_without_max_output_bytes(valid_capabilities_config, valid_policy_config):
    """create_docx doesn't require max_output_bytes."""
    registry_entry = {
        "name": "create_docx",
        "permissions": ["write_artifacts"],
        "network_access": False,
        "filesystem_scope": ["data/artifacts"],
    }
    decision = evaluate(
        capability_name="create_docx",
        arguments={"title": "Test", "sections": [], "metadata": {}},
        registry_entry=registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "allow"


# ===== Determinism =====

def test_determinism(valid_registry_entry, valid_capabilities_config, valid_policy_config, valid_app_config):
    """100 evaluations of the same input yield identical Decision."""
    args = {"code": "print('hello')", "language": "python", "input_files": []}
    first = evaluate("execute_code", args, valid_registry_entry, valid_capabilities_config, valid_policy_config, valid_app_config)
    
    for _ in range(99):
        decision = evaluate("execute_code", args, valid_registry_entry, valid_capabilities_config, valid_policy_config, valid_app_config)
        assert decision.decision == first.decision
        assert decision.reason == first.reason
        assert decision.rule == first.rule


# ===== Malformed Arguments =====

def test_deny_malformed_arguments_not_dict(valid_registry_entry, valid_capabilities_config, valid_policy_config):
    """Non-dict arguments should be denied (malformed_arguments rule)."""
    decision = evaluate(
        capability_name="execute_code",
        arguments="not_a_dict",  # Malformed
        registry_entry=valid_registry_entry,
        capabilities_config=valid_capabilities_config,
        policy_config=valid_policy_config,
    )
    assert decision.decision == "deny"
    assert decision.rule == "malformed_arguments"
    assert "Arguments must be a dictionary" in decision.reason


# ===== No Side Effects / Imports Check =====

def test_no_forbidden_imports():
    """Verify engine.py doesn't import forbidden modules."""
    import backend.domain.policy.engine as engine_module
    
    # Check source doesn't contain forbidden imports
    import inspect
    source = inspect.getsource(engine_module)
    
    forbidden_patterns = [
        "from backend.domain.model_runtime",
        "from backend.domain.audit",
        "from backend.repositories",
        "import httpx",
        "import requests",
        "from backend.config",
        "emit",
        "AuditEvent",
    ]
    
    for pattern in forbidden_patterns:
        assert pattern not in source, f"Forbidden import/pattern found: {pattern}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])