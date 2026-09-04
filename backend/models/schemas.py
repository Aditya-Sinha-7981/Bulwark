"""Typed config models for the four `config/*.yaml` files.

One Pydantic model per file (`ResourcesFile`, `CapabilitiesFile`, `PolicyFile`,
`AppFile`), matching `docs/configuration.md` exactly. `backend/config.py` loads,
merges, and validates the raw YAML into these before exposing `settings`.

`extra="forbid"` everywhere so an unrecognized *nested* key fails validation
loudly (a schema violation) rather than being silently dropped; unknown
*top-level* keys in the YAML file are handled separately by the loader as a
non-fatal warning per the task's documented error-handling rules.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RESOURCE_TYPES = ("reasoning", "code_generation", "vision", "embedding")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


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
