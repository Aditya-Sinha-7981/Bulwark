"""
Typed row dataclasses for Bulwark database entities.

These match the exact schema from docs/data-model.md.
Use for type safety when working with repository results.
"""

from dataclasses import dataclass
from typing import Optional


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
PolicyDecision = str  # 'allow' | 'deny'
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