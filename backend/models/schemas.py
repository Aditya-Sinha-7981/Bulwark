from typing import Literal, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict
from pydantic.types import UUID
from datetime import datetime


class PolicyDecision(BaseModel):
    decision: Literal["allow", "deny"]
    reason: str
    rule: str


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


# ===== Registry Entry =====
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


# ===== Errors =====
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