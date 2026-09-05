"""Unified schemas for Bulwark backend.

This module contains:
- SECTION 1: Database Row Dataclasses (Task 3)
- SECTION 2: Configuration Models (Task 2)
- SECTION 3: Capability Contract Schemas (Task 7)
- SECTION 4: Registry Entry & Errors (Task 7)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.types import UUID


# =============================================================================
# SECTION 1: Database Row Dataclasses (Task 3)
# These match the exact schema from docs/data-model.md.
# Use for type safety when working with repository results.
# =============================================================================


@dataclass
class ConversationRow:
    """Row for conversations table."""
    conversation_id: str
    created_at: str
    updated_at: str


@dataclass
class MessageRow:
    """Row for messages table."""
    message_id: str
    conversation_id: str
    role: str  # 'user' | 'orchestrator'
    content: str
    job_id: Optional[str]
    created_at: str


@dataclass
class JobRow:
    """Row for jobs table."""
    job_id: str
    conversation_id: str
    status: str  # 'created' | 'running' | 'completed' | 'failed'
    input_message: str
    final_message: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    created_at: str
    updated_at: str
    completed_at: Optional[str]


@dataclass
class JobStepRow:
    """Row for job_steps table."""
    job_step_id: str
    job_id: str
    sequence: int
    kind: str  # 'orchestrator_reasoning' | 'capability_invocation'
    capability_name: Optional[str]
    status: str  # 'pending' | 'running' | 'succeeded' | 'failed' | 'denied'
    input_payload: str  # JSON
    output_payload: Optional[str]  # JSON
    error_message: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]


@dataclass
class DocumentRow:
    """Row for documents table."""
    document_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    uploaded_at: str


@dataclass
class ArtifactRow:
    """Row for artifacts table."""
    artifact_id: str
    job_id: str
    type: str  # 'docx' | 'xlsx' | 'pptx'
    filename: str
    storage_path: str
    size_bytes: int
    created_at: str


@dataclass
class CapabilityExecutionRow:
    """Row for capability_executions table."""
    capability_execution_id: str
    job_step_id: str
    capability_name: str
    resource_type: Optional[str]  # 'reasoning' | 'code_generation' | 'vision' | 'embedding' | None
    policy_decision: str  # 'allow' | 'deny'
    policy_reason: Optional[str]
    duration_ms: Optional[int]


@dataclass
class ModelExecutionRow:
    """Row for model_executions table."""
    model_execution_id: str
    capability_execution_id: str
    resource_type: str
    model_identifier: str
    runtime: str
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    duration_ms: Optional[int]
    load_triggered: int  # 0 or 1 (bool)


@dataclass
class AuditEventRow:
    """Row for audit_events table."""
    event_id: str
    job_id: Optional[str]
    event_type: str
    component: str
    timestamp: str
    payload: str  # JSON


@dataclass
class ResourceStateRow:
    """Row for resource_state table."""
    resource_type: str  # PK
    model_identifier: str
    status: str  # 'unloaded' | 'loading' | 'loaded'
    loaded_at: Optional[str]
    last_used_at: Optional[str]


@dataclass
class KnowledgeBaseDocumentRow:
    """Row for knowledge_base_documents table."""
    kb_document_id: str
    title: str
    category: Optional[str]
    status: str  # 'ingesting' | 'ready' | 'failed'
    storage_path: str
    chunk_count: int
    ingested_at: Optional[str]


# Type aliases for common unions
JobStatus = str  # 'created' | 'running' | 'completed' | 'failed'
MessageRole = str  # 'user' | 'orchestrator'
JobStepKind = str  # 'orchestrator_reasoning' | 'capability_invocation'
JobStepStatus = str  # 'pending' | 'running' | 'succeeded' | 'failed' | 'denied'
PolicyDecisionStr = str  # 'allow' | 'deny'
ResourceType = str  # 'reasoning' | 'code_generation' | 'vision' | 'embedding'
ResourceStatus = str  # 'unloaded' | 'loading' | 'loaded'
ArtifactType = str  # 'docx' | 'xlsx' | 'pptx'
KBDocumentStatus = str  # 'ingesting' | 'ready' | 'failed'

# Valid enum values for validation
VALID_JOB_STATUSES = frozenset(("created", "running", "completed", "failed"))
VALID_MESSAGE_ROLES = frozenset(("user", "orchestrator"))
VALID_JOB_STEP_KINDS = frozenset(("orchestrator_reasoning", "capability_invocation"))
VALID_JOB_STEP_STATUSES = frozenset(("pending", "running", "succeeded", "failed", "denied"))
VALID_POLICY_DECISIONS = frozenset(("allow", "deny"))
VALID_RESOURCE_TYPES = frozenset(("reasoning", "code_generation", "vision", "embedding"))
VALID_RESOURCE_STATUSES = frozenset(("unloaded", "loading", "loaded"))
VALID_ARTIFACT_TYPES = frozenset(("docx", "xlsx", "pptx"))
VALID_KB_DOCUMENT_STATUSES = frozenset(("ingesting", "ready", "failed"))


# =============================================================================
# SECTION 2: Configuration Models (Task 2)
# Typed config models for the four `config/*.yaml` files.
#
# One Pydantic model per file (`ResourcesFile`, `CapabilitiesFile`, `PolicyFile`,
# `AppFile`), matching `docs/configuration.md` exactly. `backend/config.py` loads,
# merges, and validates the raw YAML into these before exposing `settings`.
#
# `extra="forbid"` everywhere so an unrecognized *nested* key fails validation
# loudly (a schema violation) rather than being silently dropped; unknown
# *top-level* keys in the YAML file are handled separately by the loader as a
# non-fatal warning per the task's documented error-handling rules.
# =============================================================================


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


RESOURCE_TYPES = ("reasoning", "code_generation", "vision", "embedding")


# ---------------------------------------------------------------------------
# config/resources.yaml
# ---------------------------------------------------------------------------


class ResourceEntry(StrictModel):
    model: str
    runtime: Literal["ollama"]
    context_window: int | None = None
    keep_alive: str


class ResourcesConfig(StrictModel):
    reasoning: ResourceEntry
    code_generation: ResourceEntry
    vision: ResourceEntry
    embedding: ResourceEntry

    def for_type(self, resource_type: str) -> ResourceEntry:
        if resource_type not in RESOURCE_TYPES:
            raise KeyError(
                f"unknown resource type '{resource_type}'; expected one of {RESOURCE_TYPES}"
            )
        return getattr(self, resource_type)


class ResourcesFile(StrictModel):
    resources: ResourcesConfig


# ---------------------------------------------------------------------------
# config/capabilities.yaml
# ---------------------------------------------------------------------------


class ExtractDocumentConfig(StrictModel):
    enabled: bool
    timeout_seconds: int
    max_file_size_mb: int


class SearchKnowledgeBaseConfig(StrictModel):
    enabled: bool
    timeout_seconds: int
    default_top_k: int


class GenerateCodeConfig(StrictModel):
    enabled: bool
    timeout_seconds: int


class ExecuteCodeConfig(StrictModel):
    enabled: bool
    timeout_seconds: int
    cpu_limit: int
    memory_limit_mb: int
    max_output_bytes: int


class CreateDocxConfig(StrictModel):
    enabled: bool
    timeout_seconds: int


class CreateXlsxConfig(StrictModel):
    enabled: bool
    timeout_seconds: int


class CapabilitiesConfig(StrictModel):
    extract_document: ExtractDocumentConfig
    search_knowledge_base: SearchKnowledgeBaseConfig
    generate_code: GenerateCodeConfig
    execute_code: ExecuteCodeConfig
    create_docx: CreateDocxConfig
    create_xlsx: CreateXlsxConfig


class CapabilitiesFile(StrictModel):
    capabilities: CapabilitiesConfig


# ---------------------------------------------------------------------------
# config/policy.yaml
# ---------------------------------------------------------------------------


class PolicyConfig(StrictModel):
    network_access_allowed: bool
    max_job_steps: int
    malformed_output_free_retries: int

    @field_validator("network_access_allowed")
    @classmethod
    def _reject_network_access(cls, value: bool) -> bool:
        if value:
            raise ValueError(
                "policy.network_access_allowed must be false — this is a zero-egress "
                "invariant (AGENTS.md §6 rule 10) and cannot be enabled via config"
            )
        return value


class PolicyFile(StrictModel):
    policy: PolicyConfig


# ---------------------------------------------------------------------------
# config/app.yaml
# ---------------------------------------------------------------------------

_LOOPBACK_HOSTS = ("localhost", "127.0.0.1")


class AppSection(StrictModel):
    host: str
    port: int
    cors_origins: list[str]


class PathsSection(StrictModel):
    data_root: str
    uploads: str
    extraction: str
    artifacts: str
    sandbox: str
    tmp: str
    db: str
    chroma: str


class OcrEscalationThresholds(StrictModel):
    mean_confidence_below: float
    completeness_below: float
    handwriting_detected: bool
    layout_complexity_flag: bool


class OcrSection(StrictModel):
    escalation_thresholds: OcrEscalationThresholds


class OllamaSection(StrictModel):
    base_url: str
    request_timeout_seconds: int

    @field_validator("base_url")
    @classmethod
    def _reject_non_loopback(cls, value: str) -> str:
        from urllib.parse import urlparse

        host = urlparse(value).hostname
        if host not in _LOOPBACK_HOSTS:
            raise ValueError(
                f"ollama.base_url host '{host}' is not loopback (must be one of "
                f"{_LOOPBACK_HOSTS}) — no external Ollama endpoint is supported "
                "(docs/security.md layer 3, AGENTS.md §6 rules 9-10)"
            )
        return value


class AppFile(StrictModel):
    app: AppSection
    paths: PathsSection
    ocr: OcrSection
    ollama: OllamaSection


class AppConfig(StrictModel):
    """The flattened shape exposed as `settings.app`.

    `config/app.yaml` nests `host`/`port`/`cors_origins` under an `app:` key
    sibling to `paths:`/`ocr:`/`ollama:`. `docs/configuration.md` and the task
    spec both expect `settings.app.host` *and* `settings.app.paths.db` —
    i.e. one flat object, not `settings.app.app.host`. The loader builds this
    from the validated `AppFile`.
    """

    host: str
    port: int
    cors_origins: list[str]
    paths: PathsSection
    ocr: OcrSection
    ollama: OllamaSection


# =============================================================================
# SECTION 3: Capability Contract Schemas (Task 7)
# One input model and one output model per capability, matching docs/capabilities.md exactly.
# strict models (extra="forbid") reject unknown/extra fields.
# =============================================================================


# ===== extract_document =====
class ExtractDocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID


class ExtractDocumentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extracted_text: str
    extraction_method: Literal["ocr", "vision_escalation"]
    confidence: float
    warnings: List[str]


# ===== search_knowledge_base =====
class SearchKnowledgeBaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    top_k: int = 5


class SearchKnowledgeBaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kb_document_id: UUID
    title: str
    chunk_text: str
    score: float


class SearchKnowledgeBaseOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: List[SearchKnowledgeBaseResult]


# ===== generate_code =====
class GenerateCodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_description: str
    language: Literal["python"]


class GenerateCodeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    language: Literal["python"]
    explanation: str


# ===== execute_code =====
class ExecuteCodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    language: Literal["python"]
    input_files: List[str] = []


class ExecuteCodeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    output_files: List[str]


# ===== create_docx =====
class CreateDocxSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: str
    body: str


class CreateDocxMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prepared_by: str
    date: datetime


class CreateDocxInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    sections: List[CreateDocxSection]
    metadata: CreateDocxMetadata


class CreateDocxOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: UUID
    filename: str


# ===== create_xlsx =====
class CreateXlsxSheet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    headers: List[str]
    rows: List[List[str]]


class CreateXlsxInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    sheets: List[CreateXlsxSheet]


class CreateXlsxOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: UUID
    filename: str


# ===== create_pptx (deferred) =====
# Same shape as create_docx per docs/capabilities.md
# Defined but not exposed for validation/testing per Task 7 spec
class CreatePptxInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    sections: List[CreateDocxSection]
    metadata: CreateDocxMetadata


class CreatePptxOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: UUID
    filename: str


# =============================================================================
# SECTION 4: Registry Entry & Errors (Task 7)
# =============================================================================


class CapabilityRegistryEntry(BaseModel):
    """Registry entry matching docs/capabilities.md Common contract shape."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    purpose: str
    resource_type: Optional[Literal["reasoning", "code_generation", "vision", "embedding"]]
    permissions: List[str]
    network_access: Literal[False] = False
    filesystem_scope: List[str]
    timeout_seconds: int
    retry_policy: str
    enabled: bool = True


class UnknownCapabilityError(Exception):
    """Raised when a capability name is not found in the registry."""
    def __init__(self, capability_name: str):
        self.capability_name = capability_name
        super().__init__(f"Unknown capability: {capability_name}")


class CapabilityValidationError(Exception):
    """Raised when capability input/output validation fails."""
    def __init__(self, capability_name: str, errors: List[str], is_input: bool = True):
        self.capability_name = capability_name
        self.errors = errors
        self.is_input = is_input
        direction = "input" if is_input else "output"
        super().__init__(f"Capability '{capability_name}' {direction} validation failed: {'; '.join(errors)}")