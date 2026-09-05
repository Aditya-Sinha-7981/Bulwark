"""
Capability Contract Tests

Validates that all capability input/output schemas match docs/capabilities.md exactly.
Tests both valid and invalid payloads for each capability.
"""

import pytest
from backend.models.schemas import (
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
    CreateDocxMetadata,
    CapabilityRegistryEntry,
)
from backend.domain.capabilities.registry import (
    CapabilityRegistry,
    UnknownCapabilityError,
    CapabilityValidationError,
)


# ===== Valid payloads for each capability =====
# Using valid UUID strings (any valid UUID version)
VALID_UUID = "6ba7b810-9dad-41d1-80b4-00c04fd430c8"
VALID_UUID_2 = "6ba7b810-9dad-41d1-80b4-00c04fd430c9"
VALID_UUID_V1 = "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"  # UUID v1 example
VALID_ISO8601_DATE = "2026-01-15T10:30:00+00:00"

VALID_EXTRACT_DOCUMENT_INPUT = {"document_id": VALID_UUID}
VALID_EXTRACT_DOCUMENT_OUTPUT = {
    "extracted_text": "Sample extracted text",
    "extraction_method": "ocr",
    "confidence": 0.95,
    "warnings": [],
}

VALID_SEARCH_KB_INPUT = {"query": "test query", "top_k": 5}
VALID_SEARCH_KB_INPUT_MINIMAL = {"query": "test query"}  # top_k defaults to 5
VALID_SEARCH_KB_OUTPUT = {
    "results": [
        {
            "kb_document_id": VALID_UUID,
            "title": "Test Doc",
            "chunk_text": "Test chunk text",
            "score": 0.9,
        }
    ]
}

VALID_GENERATE_CODE_INPUT = {"task_description": "Write a hello world", "language": "python"}
VALID_GENERATE_CODE_OUTPUT = {
    "code": "print('hello')",
    "language": "python",
    "explanation": "Prints hello world",
}

VALID_EXECUTE_CODE_INPUT = {
    "code": "print('hello')",
    "language": "python",
    "input_files": ["doc1.txt", "doc2.txt"],
}
VALID_EXECUTE_CODE_INPUT_MINIMAL = {"code": "print('hello')", "language": "python"}
VALID_EXECUTE_CODE_OUTPUT = {
    "stdout": "hello\n",
    "stderr": "",
    "exit_code": 0,
    "timed_out": False,
    "output_files": ["artifact1", "artifact2"],  # List[str] per docs/capabilities.md
}

VALID_CREATE_DOCX_INPUT = {
    "title": "Test Document",
    "sections": [{"heading": "Section 1", "body": "Body text"}],
    "metadata": {"prepared_by": "Test User", "date": "2026-01-15T10:30:00+00:00"},
}
VALID_CREATE_DOCX_OUTPUT = {
    "artifact_id": VALID_UUID,
    "filename": "Test_Document.docx",
}

VALID_CREATE_XLSX_INPUT = {
    "title": "Test Spreadsheet",
    "sheets": [
        {"name": "Sheet1", "headers": ["A", "B"], "rows": [["1", "2"], ["3", "4"]]}
    ],
}
VALID_CREATE_XLSX_OUTPUT = {
    "artifact_id": VALID_UUID,
    "filename": "Test_Spreadsheet.xlsx",
}


# ===== Fixtures =====

@pytest.fixture
def capabilities_config():
    """Fixture matching docs/configuration.md capabilities.yaml exactly.
    
    Note: create_pptx is NOT in this config — it is deferred per docs/capabilities.md
    and docs/configuration.md, and the registry handles it as deferred (enabled: false).
    """
    return {
        "capabilities": {
            "extract_document": {"enabled": True, "timeout_seconds": 120, "max_file_size_mb": 10},
            "search_knowledge_base": {"enabled": True, "timeout_seconds": 10, "default_top_k": 5},
            "generate_code": {"enabled": True, "timeout_seconds": 30},
            "execute_code": {"enabled": True, "timeout_seconds": 30, "cpu_limit": 1, "memory_limit_mb": 512, "max_output_bytes": 65536},
            "create_docx": {"enabled": True, "timeout_seconds": 15},
            "create_xlsx": {"enabled": True, "timeout_seconds": 15},
            # create_pptx is NOT in config — it is deferred per docs/capabilities.md and docs/configuration.md
        }
    }


@pytest.fixture
def registry(capabilities_config):
    """Create a registry with test config."""
    return CapabilityRegistry(capabilities_config)


# ===== Schema validation tests =====

class TestExtractDocumentSchemas:
    def test_valid_input(self):
        model = ExtractDocumentInput(**VALID_EXTRACT_DOCUMENT_INPUT)
        assert str(model.document_id) == VALID_UUID

    def test_valid_input_non_v4_uuid(self):
        """Non-v4 UUID should be accepted (generic UUID validation)."""
        model = ExtractDocumentInput(**{"document_id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"})
        assert str(model.document_id) == "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"

    def test_valid_output(self):
        model = ExtractDocumentOutput(**VALID_EXTRACT_DOCUMENT_OUTPUT)
        assert model.extracted_text == VALID_EXTRACT_DOCUMENT_OUTPUT["extracted_text"]
        assert model.extraction_method == "ocr"
        assert model.confidence == 0.95
        assert model.warnings == []

    def test_input_missing_required_field(self):
        with pytest.raises(Exception) as exc_info:
            ExtractDocumentInput(**{})
        assert "document_id" in str(exc_info.value)

    def test_input_wrong_type(self):
        with pytest.raises(Exception) as exc_info:
            ExtractDocumentInput(**{"document_id": 123})
        assert "document_id" in str(exc_info.value)

    def test_input_invalid_uuid_rejected(self):
        """Malformed UUID string should be rejected."""
        with pytest.raises(Exception) as exc_info:
            ExtractDocumentInput(**{"document_id": "not-a-uuid"})
        assert "document_id" in str(exc_info.value)

    def test_input_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            ExtractDocumentInput(**{"document_id": VALID_UUID, "extra_field": "not allowed"})
        assert "extra_field" in str(exc_info.value)

    def test_output_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            ExtractDocumentOutput(**{**VALID_EXTRACT_DOCUMENT_OUTPUT, "extra": "not allowed"})
        assert "extra" in str(exc_info.value)

    def test_output_wrong_type(self):
        with pytest.raises(Exception) as exc_info:
            ExtractDocumentOutput(**{**VALID_EXTRACT_DOCUMENT_OUTPUT, "confidence": "not a float"})
        assert "confidence" in str(exc_info.value)


class TestSearchKnowledgeBaseSchemas:
    def test_valid_input_full(self):
        model = SearchKnowledgeBaseInput(**VALID_SEARCH_KB_INPUT)
        assert model.query == "test query"
        assert model.top_k == 5

    def test_valid_input_minimal(self):
        model = SearchKnowledgeBaseInput(**VALID_SEARCH_KB_INPUT_MINIMAL)
        assert model.query == "test query"
        assert model.top_k == 5  # default

    def test_valid_output(self):
        model = SearchKnowledgeBaseOutput(**VALID_SEARCH_KB_OUTPUT)
        assert len(model.results) == 1
        assert str(model.results[0].kb_document_id) == VALID_UUID
        assert model.results[0].score == 0.9

    def test_output_non_v4_uuid(self):
        """Non-v4 UUID should be accepted in results."""
        output = {
            "results": [{
                "kb_document_id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
                "title": "Test",
                "chunk_text": "text",
                "score": 0.5,
            }]
        }
        model = SearchKnowledgeBaseOutput(**output)
        assert str(model.results[0].kb_document_id) == "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"

    def test_input_missing_required_field(self):
        with pytest.raises(Exception) as exc_info:
            SearchKnowledgeBaseInput(**{})
        assert "query" in str(exc_info.value)

    def test_input_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            SearchKnowledgeBaseInput(**{"query": "test", "extra_field": "not allowed"})
        assert "extra_field" in str(exc_info.value)

    def test_output_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            SearchKnowledgeBaseOutput(**{**VALID_SEARCH_KB_OUTPUT, "extra": "not allowed"})
        assert "extra" in str(exc_info.value)

    def test_output_invalid_uuid_rejected(self):
        """Malformed UUID in results should be rejected."""
        bad_output = {
            "results": [{
                "kb_document_id": "not-a-uuid",
                "title": "Test",
                "chunk_text": "text",
                "score": 0.5,
            }]
        }
        with pytest.raises(Exception) as exc_info:
            SearchKnowledgeBaseOutput(**bad_output)
        assert "kb_document_id" in str(exc_info.value)


class TestGenerateCodeSchemas:
    def test_valid_input(self):
        model = GenerateCodeInput(**VALID_GENERATE_CODE_INPUT)
        assert model.task_description == "Write a hello world"
        assert model.language == "python"

    def test_valid_output(self):
        model = GenerateCodeOutput(**VALID_GENERATE_CODE_OUTPUT)
        assert model.code == "print('hello')"
        assert model.language == "python"
        assert model.explanation == "Prints hello world"

    def test_input_missing_required_field(self):
        with pytest.raises(Exception) as exc_info:
            GenerateCodeInput(**{})
        err_str = str(exc_info.value)
        assert "task_description" in err_str or "language" in err_str

    def test_input_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            GenerateCodeInput(**{**VALID_GENERATE_CODE_INPUT, "extra_field": "not allowed"})
        assert "extra_field" in str(exc_info.value)

    def test_output_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            GenerateCodeOutput(**{**VALID_GENERATE_CODE_OUTPUT, "extra": "not allowed"})
        assert "extra" in str(exc_info.value)


class TestExecuteCodeSchemas:
    def test_valid_input_full(self):
        model = ExecuteCodeInput(**VALID_EXECUTE_CODE_INPUT)
        assert model.code == "print('hello')"
        assert model.language == "python"
        assert model.input_files == ["doc1.txt", "doc2.txt"]

    def test_valid_input_minimal(self):
        model = ExecuteCodeInput(**VALID_EXECUTE_CODE_INPUT_MINIMAL)
        assert model.input_files == []

    def test_valid_output(self):
        model = ExecuteCodeOutput(**VALID_EXECUTE_CODE_OUTPUT)
        assert model.stdout == "hello\n"
        assert model.exit_code == 0
        assert model.timed_out is False
        assert model.output_files == ["artifact1", "artifact2"]

    def test_input_missing_required_field(self):
        with pytest.raises(Exception) as exc_info:
            ExecuteCodeInput(**{})
        err_str = str(exc_info.value)
        assert "code" in err_str or "language" in err_str

    def test_input_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            ExecuteCodeInput(**{**VALID_EXECUTE_CODE_INPUT, "extra_field": "not allowed"})
        assert "extra_field" in str(exc_info.value)

    def test_output_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            ExecuteCodeOutput(**{**VALID_EXECUTE_CODE_OUTPUT, "extra": "not allowed"})
        assert "extra" in str(exc_info.value)

    def test_output_files_accepts_strings_not_uuids(self):
        """output_files is List[str] per docs/capabilities.md, not UUIDs."""
        output = {
            "stdout": "hello\n",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "output_files": ["artifact1", "artifact2", "not-a-uuid"],
        }
        model = ExecuteCodeOutput(**output)
        assert model.output_files == ["artifact1", "artifact2", "not-a-uuid"]


class TestCreateDocxSchemas:
    def test_valid_input(self):
        model = CreateDocxInput(**VALID_CREATE_DOCX_INPUT)
        assert model.title == "Test Document"
        assert len(model.sections) == 1
        assert model.sections[0].heading == "Section 1"
        assert model.metadata.prepared_by == "Test User"
        assert model.metadata.date.isoformat() == "2026-01-15T10:30:00+00:00"

    def test_valid_output(self):
        model = CreateDocxOutput(**VALID_CREATE_DOCX_OUTPUT)
        assert str(model.artifact_id) == VALID_UUID
        assert model.filename == "Test_Document.docx"

    def test_output_non_v4_uuid(self):
        """Non-v4 UUID should be accepted for artifact_id."""
        model = CreateDocxOutput(**{"artifact_id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6", "filename": "test.docx"})
        assert str(model.artifact_id) == "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"

    def test_input_missing_required_field(self):
        with pytest.raises(Exception) as exc_info:
            CreateDocxInput(**{})
        err_str = str(exc_info.value)
        assert "title" in err_str or "sections" in err_str or "metadata" in err_str

    def test_input_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            CreateDocxInput(**{**VALID_CREATE_DOCX_INPUT, "extra_field": "not allowed"})
        assert "extra_field" in str(exc_info.value)

    def test_output_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            CreateDocxOutput(**{**VALID_CREATE_DOCX_OUTPUT, "extra": "not allowed"})
        assert "extra" in str(exc_info.value)

    def test_output_invalid_uuid_rejected(self):
        """Malformed UUID in artifact_id should be rejected."""
        bad_output = {**VALID_CREATE_DOCX_OUTPUT, "artifact_id": "not-a-uuid"}
        with pytest.raises(Exception) as exc_info:
            CreateDocxOutput(**bad_output)
        assert "artifact_id" in str(exc_info.value)

    def test_metadata_valid_iso8601_date(self):
        """Valid ISO8601 date should be accepted."""
        model = CreateDocxMetadata(prepared_by="Test", date="2026-01-15T10:30:00+00:00")
        assert model.date.isoformat() == "2026-01-15T10:30:00+00:00"

    def test_metadata_invalid_date_rejected(self):
        """Invalid date string should be rejected."""
        with pytest.raises(Exception) as exc_info:
            CreateDocxMetadata(prepared_by="Test", date="not-a-date")
        assert "date" in str(exc_info.value)

    def test_metadata_invalid_format_rejected(self):
        """Non-ISO8601 date format should be rejected."""
        with pytest.raises(Exception) as exc_info:
            CreateDocxMetadata(prepared_by="Test", date="01/15/2026")
        assert "date" in str(exc_info.value)


class TestCreateXlsxSchemas:
    def test_valid_input(self):
        model = CreateXlsxInput(**VALID_CREATE_XLSX_INPUT)
        assert model.title == "Test Spreadsheet"
        assert len(model.sheets) == 1
        assert model.sheets[0].name == "Sheet1"
        assert model.sheets[0].headers == ["A", "B"]
        assert model.sheets[0].rows == [["1", "2"], ["3", "4"]]

    def test_valid_output(self):
        model = CreateXlsxOutput(**VALID_CREATE_XLSX_OUTPUT)
        assert str(model.artifact_id) == VALID_UUID
        assert model.filename == "Test_Spreadsheet.xlsx"

    def test_output_non_v4_uuid(self):
        """Non-v4 UUID should be accepted for artifact_id."""
        model = CreateXlsxOutput(**{"artifact_id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6", "filename": "test.xlsx"})
        assert str(model.artifact_id) == "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"

    def test_input_missing_required_field(self):
        with pytest.raises(Exception) as exc_info:
            CreateXlsxInput(**{})
        err_str = str(exc_info.value)
        assert "title" in err_str or "sheets" in err_str

    def test_input_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            CreateXlsxInput(**{**VALID_CREATE_XLSX_INPUT, "extra_field": "not allowed"})
        assert "extra_field" in str(exc_info.value)

    def test_output_extra_field_rejected(self):
        with pytest.raises(Exception) as exc_info:
            CreateXlsxOutput(**{**VALID_CREATE_XLSX_OUTPUT, "extra": "not allowed"})
        assert "extra" in str(exc_info.value)

    def test_output_invalid_uuid_rejected(self):
        """Malformed UUID in artifact_id should be rejected."""
        bad_output = {**VALID_CREATE_XLSX_OUTPUT, "artifact_id": "not-a-uuid"}
        with pytest.raises(Exception) as exc_info:
            CreateXlsxOutput(**bad_output)
        assert "artifact_id" in str(exc_info.value)


# ===== Registry tests =====

class TestCapabilityRegistry:
    def test_registry_loads_all_capabilities(self, registry):
        all_caps = registry.all()
        names = [c.name for c in all_caps]
        expected = [
            "extract_document",
            "search_knowledge_base",
            "generate_code",
            "execute_code",
            "create_docx",
            "create_xlsx",
            "create_pptx",
        ]
        assert names == expected

    def test_registry_entry_has_all_common_fields(self, registry):
        for cap in registry.all():
            assert cap.name
            assert cap.purpose
            assert cap.resource_type in ["reasoning", "code_generation", "vision", "embedding", None]
            assert isinstance(cap.permissions, list)
            assert cap.network_access is False  # Invariant
            assert isinstance(cap.filesystem_scope, list)
            assert isinstance(cap.timeout_seconds, int)
            assert isinstance(cap.retry_policy, str)
            assert isinstance(cap.enabled, bool)

    def test_resource_types_match_docs(self, registry):
        assert registry.resource_type("extract_document") == "vision"
        assert registry.resource_type("search_knowledge_base") == "embedding"
        assert registry.resource_type("generate_code") == "code_generation"
        assert registry.resource_type("execute_code") is None
        assert registry.resource_type("create_docx") is None
        assert registry.resource_type("create_xlsx") is None
        assert registry.resource_type("create_pptx") is None

    def test_network_access_invariant(self, registry):
        for cap in registry.all():
            assert cap.network_access is False
            # Should not be able to set true through public API
            with pytest.raises(Exception):
                cap.network_access = True

    def test_get_known_capability(self, registry):
        entry = registry.get("extract_document")
        assert entry.name == "extract_document"
        assert entry.purpose

    def test_get_unknown_capability_raises(self, registry):
        with pytest.raises(UnknownCapabilityError) as exc_info:
            registry.get("nonexistent_capability")
        assert "nonexistent_capability" in str(exc_info.value)

    def test_validate_input_valid(self, registry):
        validated = registry.validate_input("extract_document", VALID_EXTRACT_DOCUMENT_INPUT)
        assert isinstance(validated, ExtractDocumentInput)
        assert str(validated.document_id) == VALID_UUID

    def test_validate_input_invalid_missing_field(self, registry):
        with pytest.raises(CapabilityValidationError) as exc_info:
            registry.validate_input("extract_document", {})
        assert "document_id" in str(exc_info.value)
        assert exc_info.value.capability_name == "extract_document"
        assert exc_info.value.is_input is True

    def test_validate_input_invalid_wrong_type(self, registry):
        with pytest.raises(CapabilityValidationError) as exc_info:
            registry.validate_input("extract_document", {"document_id": 123})
        assert "document_id" in str(exc_info.value)

    def test_validate_input_invalid_extra_field(self, registry):
        with pytest.raises(CapabilityValidationError) as exc_info:
            registry.validate_input("extract_document", {"document_id": VALID_UUID, "extra": "field"})
        assert "extra" in str(exc_info.value)

    def test_validate_input_invalid_uuid_rejected(self, registry):
        """Malformed UUID in validate_input should be rejected."""
        with pytest.raises(CapabilityValidationError) as exc_info:
            registry.validate_input("extract_document", {"document_id": "not-a-uuid"})
        assert "document_id" in str(exc_info.value)

    def test_validate_output_valid(self, registry):
        validated = registry.validate_output("extract_document", VALID_EXTRACT_DOCUMENT_OUTPUT)
        assert isinstance(validated, ExtractDocumentOutput)
        assert validated.extracted_text == VALID_EXTRACT_DOCUMENT_OUTPUT["extracted_text"]

    def test_validate_output_invalid(self, registry):
        with pytest.raises(CapabilityValidationError) as exc_info:
            registry.validate_output("extract_document", {**VALID_EXTRACT_DOCUMENT_OUTPUT, "confidence": "not a float"})
        assert "confidence" in str(exc_info.value)
        assert exc_info.value.is_input is False

    def test_validate_unknown_capability_raises(self, registry):
        with pytest.raises(UnknownCapabilityError):
            registry.validate_input("nonexistent", {})
        with pytest.raises(UnknownCapabilityError):
            registry.validate_output("nonexistent", {})

    def test_validate_create_pptx_not_exposed(self, registry):
        """create_pptx is deferred — not exposed for validation."""
        with pytest.raises(UnknownCapabilityError):
            registry.validate_input("create_pptx", {})
        with pytest.raises(UnknownCapabilityError):
            registry.validate_output("create_pptx", {})

    def test_enabled_flag_from_config(self, registry):
        assert registry.is_enabled("extract_document") is True
        assert registry.is_enabled("create_pptx") is False  # Deferred

    def test_timeout_from_config(self, registry):
        assert registry.timeout_seconds("extract_document") == 120
        assert registry.timeout_seconds("search_knowledge_base") == 10
        assert registry.timeout_seconds("generate_code") == 30
        assert registry.timeout_seconds("execute_code") == 30
        assert registry.timeout_seconds("create_docx") == 15
        assert registry.timeout_seconds("create_xlsx") == 15
        assert registry.timeout_seconds("create_pptx") == 15

    def test_filesystem_scope(self, registry):
        assert registry.filesystem_scope("extract_document") == ["data/uploads"]
        assert registry.filesystem_scope("search_knowledge_base") == []
        assert registry.filesystem_scope("execute_code") == ["data/sandbox"]
        assert registry.filesystem_scope("create_docx") == ["data/artifacts"]

    def test_permissions(self, registry):
        assert registry.permissions("extract_document") == ["read_uploads"]
        assert registry.permissions("search_knowledge_base") == ["read_chroma_index"]
        assert registry.permissions("generate_code") == []
        assert "create_docker_container" in registry.permissions("execute_code")
        assert "write_artifacts" in registry.permissions("create_docx")

    def test_config_missing_entry_fails_fast(self):
        # Config missing entry for known non-deferred capability
        bad_config = {"capabilities": {"extract_document": {"enabled": True}}}
        with pytest.raises(ValueError) as exc_info:
            CapabilityRegistry(bad_config)
        assert "Missing config entry" in str(exc_info.value)

    def test_config_unknown_capability_fails_fast(self):
        # Config has entry for unknown capability
        bad_config = {"capabilities": {"unknown_capability": {"enabled": True, "timeout_seconds": 10}}}
        with pytest.raises(ValueError) as exc_info:
            CapabilityRegistry(bad_config)
        assert "unknown capability" in str(exc_info.value).lower()

    def test_network_access_cannot_be_true_in_config(self):
        config = {"capabilities": {name: {"enabled": True, "timeout_seconds": 10} for name in [
            "extract_document", "search_knowledge_base", "generate_code", "execute_code",
            "create_docx", "create_xlsx", "create_pptx"
        ]}}
        reg = CapabilityRegistry(config)
        for cap in reg.all():
            assert cap.network_access is False

    def test_registry_order_stable(self, registry):
        """Registry.all() returns capabilities in stable documented order."""
        all_caps = registry.all()
        names = [c.name for c in all_caps]
        all_caps_2 = registry.all()
        names_2 = [c.name for c in all_caps_2]
        assert names == names_2

    def test_create_pptx_in_all_but_disabled(self, registry):
        """create_pptx is in registry.all() but disabled (deferred)."""
        names = [c.name for c in registry.all()]
        assert "create_pptx" in names
        assert registry.is_enabled("create_pptx") is False

    # Per-capability limit accessor tests
    def test_max_file_size_mb_accessor(self, registry):
        assert registry.max_file_size_mb("extract_document") == 10
        assert registry.max_file_size_mb("search_knowledge_base") is None
        assert registry.max_file_size_mb("execute_code") is None

    def test_default_top_k_accessor(self, registry):
        assert registry.default_top_k("search_knowledge_base") == 5
        assert registry.default_top_k("extract_document") is None

    def test_execute_code_limits_accessors(self, registry):
        assert registry.cpu_limit("execute_code") == 1
        assert registry.memory_limit_mb("execute_code") == 512
        assert registry.max_output_bytes("execute_code") == 65536
        assert registry.cpu_limit("extract_document") is None
        assert registry.memory_limit_mb("extract_document") is None
        assert registry.max_output_bytes("extract_document") is None

    def test_deferred_capability_has_no_config_limits(self, registry):
        """Deferred capability (create_pptx) has no config limits since it's not in config."""
        assert registry.max_file_size_mb("create_pptx") is None
        assert registry.cpu_limit("create_pptx") is None

    def test_deferred_capability_no_config_entry_ok(self):
        """Deferred capability without config entry should not fail."""
        # Config without create_pptx (matching authoritative config)
        config = {
            "capabilities": {
                "extract_document": {"enabled": True, "timeout_seconds": 120},
                "search_knowledge_base": {"enabled": True, "timeout_seconds": 10},
                "generate_code": {"enabled": True, "timeout_seconds": 30},
                "execute_code": {"enabled": True, "timeout_seconds": 30},
                "create_docx": {"enabled": True, "timeout_seconds": 15},
                "create_xlsx": {"enabled": True, "timeout_seconds": 15},
                # create_pptx intentionally omitted
            }
        }
        registry = CapabilityRegistry(config)
        assert registry.is_enabled("create_pptx") is False
        assert registry.timeout_seconds("create_pptx") == 15  # from static default

    def test_non_deferred_missing_config_fails(self):
        """Non-deferred capability missing config should fail."""
        bad_config = {"capabilities": {"extract_document": {"enabled": True}}}
        with pytest.raises(ValueError) as exc_info:
            CapabilityRegistry(bad_config)
        assert "Missing config entry" in str(exc_info.value)

    def test_deferred_always_disabled_even_with_config(self):
        """Deferred capability (create_pptx) must ALWAYS be disabled, even if config tries to enable it."""
        config = {
            "capabilities": {
                "extract_document": {"enabled": True, "timeout_seconds": 120},
                "search_knowledge_base": {"enabled": True, "timeout_seconds": 10},
                "generate_code": {"enabled": True, "timeout_seconds": 30},
                "execute_code": {"enabled": True, "timeout_seconds": 30},
                "create_docx": {"enabled": True, "timeout_seconds": 15},
                "create_xlsx": {"enabled": True, "timeout_seconds": 15},
                "create_pptx": {"enabled": True, "timeout_seconds": 15},  # should be ignored
            }
        }
        registry = CapabilityRegistry(config)
        assert registry.is_enabled("create_pptx") is False  # ALWAYS False for deferred
        assert registry.timeout_seconds("create_pptx") == 15


class TestCapabilityRegistryEntry:
    def test_entry_model_valid(self):
        entry = CapabilityRegistryEntry(
            name="test",
            purpose="Test",
            resource_type="vision",
            permissions=["read_uploads"],
            network_access=False,
            filesystem_scope=["data/uploads"],
            timeout_seconds=120,
            retry_policy="none",
        )
        assert entry.name == "test"
        assert entry.network_access is False

    def test_entry_rejects_network_access_true(self):
        with pytest.raises(Exception):
            CapabilityRegistryEntry(
                name="test",
                purpose="Test",
                resource_type="vision",
                permissions=[],
                network_access=True,  # Should fail
                filesystem_scope=[],
                timeout_seconds=10,
                retry_policy="none",
            )

    def test_entry_rejects_extra_field(self):
        with pytest.raises(Exception):
            CapabilityRegistryEntry(
                name="test",
                purpose="Test",
                resource_type="vision",
                permissions=[],
                network_access=False,
                filesystem_scope=[],
                timeout_seconds=10,
                retry_policy="none",
                extra_field="not allowed",
            )