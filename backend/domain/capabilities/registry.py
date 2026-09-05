"""
Capability Registry

Loads capability contracts from docs/capabilities.md as code, merges
configuration from config/capabilities.yaml, and provides validation
against input/output schemas.

No execution logic — contracts and validation only.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel
from backend.models.schemas import (
    CapabilityRegistryEntry,
    ExtractDocumentInput,
    ExtractDocumentOutput,
    SearchKnowledgeBaseInput,
    SearchKnowledgeBaseOutput,
    GenerateCodeInput,
    GenerateCodeOutput,
    ExecuteCodeInput,
    ExecuteCodeOutput,
    CreateDocxInput,
    CreateDocxOutput,
    CreateXlsxInput,
    CreateXlsxOutput,
    UnknownCapabilityError,
    CapabilityValidationError,
)


# Static capability definitions from docs/capabilities.md
# Deferred capabilities have "deferred": True flag
_STATIC_CAPABILITIES = {
    "extract_document": {
        "name": "extract_document",
        "purpose": "Extract text/structured content from an uploaded document image (scanned report, handwritten note, photograph). Internally tiered — see document-processing.md for the OCR → escalation logic. This tiering is invisible to the Orchestrator; it sees one capability, one result.",
        "resource_type": "vision",
        "permissions": ["read_uploads"],
        "network_access": False,
        "filesystem_scope": ["data/uploads"],
        "timeout_seconds": 120,
        "retry_policy": "none automatic",
        "deferred": False,
    },
    "search_knowledge_base": {
        "name": "search_knowledge_base",
        "purpose": "Explicit retrieval against the local knowledge base.",
        "resource_type": "embedding",
        "permissions": ["read_chroma_index"],
        "network_access": False,
        "filesystem_scope": [],
        "timeout_seconds": 10,
        "retry_policy": "none",
        "deferred": False,
    },
    "generate_code": {
        "name": "generate_code",
        "purpose": "Produce code for a described task. Does not execute it — see execute_code.",
        "resource_type": "code_generation",
        "permissions": [],
        "network_access": False,
        "filesystem_scope": [],
        "timeout_seconds": 30,
        "retry_policy": "none automatic",
        "deferred": False,
    },
    "execute_code": {
        "name": "execute_code",
        "purpose": "Run generated code in the isolated Docker sandbox and capture the result.",
        "resource_type": None,
        "permissions": ["create_docker_container", "read_sandbox_input", "write_sandbox_output"],
        "network_access": False,
        "filesystem_scope": ["data/sandbox"],
        "timeout_seconds": 30,
        "retry_policy": "none automatic",
        "deferred": False,
    },
    "create_docx": {
        "name": "create_docx",
        "purpose": "Deterministically render a Word document from structured findings.",
        "resource_type": None,
        "permissions": ["write_artifacts"],
        "network_access": False,
        "filesystem_scope": ["data/artifacts"],
        "timeout_seconds": 15,
        "retry_policy": "none automatic",
        "deferred": False,
    },
    "create_xlsx": {
        "name": "create_xlsx",
        "purpose": "Deterministically render an Excel file from structured tabular data.",
        "resource_type": None,
        "permissions": ["write_artifacts"],
        "network_access": False,
        "filesystem_scope": ["data/artifacts"],
        "timeout_seconds": 15,
        "retry_policy": "none automatic",
        "deferred": False,
    },
    "create_pptx": {
        "name": "create_pptx",
        "purpose": "Deterministically render a PowerPoint presentation from structured findings.",
        "resource_type": None,
        "permissions": ["write_artifacts"],
        "network_access": False,
        "filesystem_scope": ["data/artifacts"],
        "timeout_seconds": 15,
        "retry_policy": "none automatic",
        "deferred": True,  # Deferred per docs/capabilities.md and docs/requirements.md
    },
}

# Input/output schema mapping
# create_pptx is deferred per Task 7 spec — declared in registry but not exposed for validation
_INPUT_SCHEMAS = {
    "extract_document": ExtractDocumentInput,
    "search_knowledge_base": SearchKnowledgeBaseInput,
    "generate_code": GenerateCodeInput,
    "execute_code": ExecuteCodeInput,
    "create_docx": CreateDocxInput,
    "create_xlsx": CreateXlsxInput,
}

_OUTPUT_SCHEMAS = {
    "extract_document": ExtractDocumentOutput,
    "search_knowledge_base": SearchKnowledgeBaseOutput,
    "generate_code": GenerateCodeOutput,
    "execute_code": ExecuteCodeOutput,
    "create_docx": CreateDocxOutput,
    "create_xlsx": CreateXlsxOutput,
}


class CapabilityRegistry:
    """Registry for capability contracts with validation."""

    def __init__(self, capabilities_config: Optional[Dict[str, Any]] = None):
        """
        Initialize the registry with static definitions overlaid with config.

        Args:
            capabilities_config: Dict with "capabilities" key mapping capability name
                to dict with enabled, timeout_seconds, and per-capability limits.
                Example: {"capabilities": {"extract_document": {"enabled": True, "timeout_seconds": 120}}}
        """
        self._entries: Dict[str, CapabilityRegistryEntry] = {}
        self._config = capabilities_config or {}
        self._limits: Dict[str, Dict[str, Any]] = {}  # Store per-capability limits
        self._load_registry()

    def _load_registry(self) -> None:
        """Load all capabilities, merging static definitions with config."""
        config_caps = self._config.get("capabilities", {}) if self._config else {}

        # Fail fast: config entry for unknown capability
        for cfg_name in config_caps:
            if cfg_name not in _STATIC_CAPABILITIES:
                raise ValueError(f"config/capabilities.yaml contains unknown capability: {cfg_name}")

        for name, static in _STATIC_CAPABILITIES.items():
            # Merge with config
            cfg = config_caps.get(name, {})

            # Check if capability is deferred (not in config)
            is_deferred = static.get("deferred", False)
            has_config = name in config_caps

            if not has_config:
                if not static.get("deferred", False):
                    # Non-deferred capability missing config → fail fast
                    raise ValueError(f"Missing config entry for capability: {name}")
                # Deferred capability without config → default to disabled
                cfg = {}
            else:
                cfg = config_caps[name]

            # Store per-capability limits from config (all keys except enabled, timeout_seconds)
            self._limits[name] = {k: v for k, v in cfg.items() if k not in ("enabled", "timeout_seconds")}

            entry = CapabilityRegistryEntry(
                name=name,
                purpose=static["purpose"],
                resource_type=static["resource_type"],
                permissions=static["permissions"],
                network_access=static["network_access"],
                filesystem_scope=static["filesystem_scope"],
                timeout_seconds=cfg.get("timeout_seconds", static["timeout_seconds"]),
                retry_policy=static["retry_policy"],
                enabled=False if is_deferred else cfg.get("enabled", True),
            )

            # Ensure network_access is always false (invariant)
            if entry.network_access is not False:
                raise ValueError(f"Capability {name} must have network_access: false")

            self._entries[name] = entry

    def get(self, name: str) -> CapabilityRegistryEntry:
        """Get a capability entry by name. Raises UnknownCapabilityError if not found."""
        if name not in self._entries:
            raise UnknownCapabilityError(name)
        return self._entries[name]

    def all(self) -> List[CapabilityRegistryEntry]:
        """Get all capability entries in stable order."""
        # Stable order: extract_document, search_knowledge_base, generate_code,
        # execute_code, create_docx, create_xlsx, create_pptx
        order = [
            "extract_document",
            "search_knowledge_base",
            "generate_code",
            "execute_code",
            "create_docx",
            "create_xlsx",
            "create_pptx",
        ]
        return [self._entries[name] for name in order if name in self._entries]

    def validate_input(self, name: str, payload: Dict[str, Any]) -> BaseModel:
        """
        Validate an input payload against the capability's input schema.

        Returns the validated model instance.
        Raises CapabilityValidationError on failure.
        """
        if name not in _INPUT_SCHEMAS:
            raise UnknownCapabilityError(name)

        schema_class = _INPUT_SCHEMAS[name]
        try:
            return schema_class(**payload)
        except Exception as e:
            errors = self._extract_validation_errors(e)
            raise CapabilityValidationError(name, errors, is_input=True)

    def validate_output(self, name: str, payload: Dict[str, Any]) -> BaseModel:
        """
        Validate an output payload against the capability's output schema.

        Returns the validated model instance.
        Raises CapabilityValidationError on failure.
        """
        if name not in _OUTPUT_SCHEMAS:
            raise UnknownCapabilityError(name)

        schema_class = _OUTPUT_SCHEMAS[name]
        try:
            return schema_class(**payload)
        except Exception as e:
            errors = self._extract_validation_errors(e)
            raise CapabilityValidationError(name, errors, is_input=False)

    def is_enabled(self, name: str) -> bool:
        """Check if a capability is enabled."""
        return self.get(name).enabled

    def resource_type(self, name: str) -> Optional[str]:
        """Get the resource type for a capability."""
        return self.get(name).resource_type

    def timeout_seconds(self, name: str) -> int:
        """Get the timeout for a capability."""
        return self.get(name).timeout_seconds

    def filesystem_scope(self, name: str) -> List[str]:
        """Get the filesystem scope for a capability."""
        return self.get(name).filesystem_scope

    def permissions(self, name: str) -> List[str]:
        """Get the permissions for a capability."""
        return self.get(name).permissions

    # Per-capability limit accessors
    def max_file_size_mb(self, name: str) -> Optional[int]:
        """Get max_file_size_mb for extract_document."""
        return self._limits.get(name, {}).get("max_file_size_mb")

    def default_top_k(self, name: str) -> Optional[int]:
        """Get default_top_k for search_knowledge_base."""
        return self._limits.get(name, {}).get("default_top_k")

    def cpu_limit(self, name: str) -> Optional[int]:
        """Get cpu_limit for execute_code."""
        return self._limits.get(name, {}).get("cpu_limit")

    def memory_limit_mb(self, name: str) -> Optional[int]:
        """Get memory_limit_mb for execute_code."""
        return self._limits.get(name, {}).get("memory_limit_mb")

    def max_output_bytes(self, name: str) -> Optional[int]:
        """Get max_output_bytes for execute_code."""
        return self._limits.get(name, {}).get("max_output_bytes")

    def _extract_validation_errors(self, exc: Exception) -> List[str]:
        """Extract readable error messages from Pydantic validation error."""
        errors = []
        if hasattr(exc, "errors"):
            for err in exc.errors():
                loc = ".".join(str(x) for x in err["loc"])
                msg = err["msg"]
                errors.append(f"{loc}: {msg}")
        else:
            errors.append(str(exc))
        return errors


# Global registry instance (initialized at startup)
_registry: Optional[CapabilityRegistry] = None


def get_registry(capabilities_config: Optional[Dict[str, Any]] = None) -> CapabilityRegistry:
    """Get or create the global registry instance."""
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry(capabilities_config)
    return _registry


def set_registry(registry: CapabilityRegistry) -> None:
    """Set the global registry instance (for testing)."""
    global _registry
    _registry = registry