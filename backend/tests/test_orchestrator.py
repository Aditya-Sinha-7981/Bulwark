"""
Orchestrator Agent Tests

Tests for the Orchestrator loop per docs/testing.md "Agent tests":
- Prompt builder includes all 7 required elements and every capability from the fixture registry
- Proposal parser: valid shapes, malformed cases (non-JSON, bad action, unknown capability, schema-invalid args)
- test_terminate_on_empty_content: empty respond → malformed, not terminal
- classify_step: exhaustive classification tests
- step(): orchestrator_step emitted on every call
- Static check: no forbidden imports in agent.py
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.domain.capabilities.registry import CapabilityRegistry
from backend.domain.orchestrator.agent import classify_step, step
from backend.domain.orchestrator.prompt_builder import build_system_prompt
from backend.domain.orchestrator.proposal_parser import parse_proposal
from backend.models.schemas import (
    GenerationResult,
    OrchestratorContext,
    ParseResult,
    StepOutcome,
)

MAX_JOB_STEPS = 8


# ===== Fixtures =====

CAPABILITIES_CONFIG = {
    "capabilities": {
        "extract_document": {"enabled": True, "timeout_seconds": 120, "max_file_size_mb": 10},
        "search_knowledge_base": {"enabled": True, "timeout_seconds": 10, "default_top_k": 5},
        "generate_code": {"enabled": True, "timeout_seconds": 30},
        "execute_code": {"enabled": True, "timeout_seconds": 30, "cpu_limit": 1, "memory_limit_mb": 512, "max_output_bytes": 65536},
        "create_docx": {"enabled": True, "timeout_seconds": 15},
        "create_xlsx": {"enabled": True, "timeout_seconds": 15},
    }
}


@pytest.fixture
def registry():
    """Create a fixture Registry with test config."""
    return CapabilityRegistry(CAPABILITIES_CONFIG)


class FakeModelClient:
    """Fake ModelClient that returns scripted GenerationResult objects."""

    def __init__(self, responses: Optional[List[str]] = None):
        self._responses = responses or []
        self._call_count = 0
        self.calls: List[Dict[str, Any]] = []

    async def generate(
        self,
        resource_type: str,
        prompt: str,
        *,
        images: Optional[List[bytes]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        self.calls.append({
            "resource_type": resource_type,
            "prompt": prompt,
            "images": images,
            "options": options,
        })
        text = self._responses[self._call_count] if self._call_count < len(self._responses) else "{}"
        self._call_count += 1
        return GenerationResult(
            text=text,
            prompt_tokens=100,
            completion_tokens=50,
            duration_ms=200,
            model_identifier="test-model",
            load_triggered=False,
        )


def _make_context(
    job_id: str = "test-job-id",
    conversation_id: str = "test-conv-id",
    system_prompt: str = "",
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    tool_results: Optional[List[Dict[str, Any]]] = None,
    malformed_error: Optional[str] = None,
) -> OrchestratorContext:
    """Create an OrchestratorContext for testing."""
    return OrchestratorContext(
        job_id=job_id,
        conversation_id=conversation_id,
        system_prompt=system_prompt or "System prompt",
        conversation_history=conversation_history or [],
        tool_results=tool_results or [],
        malformed_error=malformed_error,
    )


# ===== Prompt Builder Tests =====

class TestPromptBuilder:
    def test_prompt_includes_role_and_scope(self, registry):
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        assert "Orchestrator" in prompt
        assert "propose" in prompt.lower() or "proposal" in prompt.lower()

    def test_prompt_includes_all_enabled_capabilities(self, registry):
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        for cap in registry.all():
            if cap.enabled:
                assert cap.name in prompt, f"capability {cap.name} missing from prompt"

    def test_prompt_includes_capability_purposes(self, registry):
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        for cap in registry.all():
            if cap.enabled:
                assert cap.purpose in prompt, f"purpose for {cap.name} missing from prompt"

    def test_prompt_includes_input_schemas(self, registry):
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        # Check that JSON schema representations are present
        assert "document_id" in prompt  # extract_document input
        assert "query" in prompt  # search_knowledge_base input
        assert "task_description" in prompt  # generate_code input

    def test_prompt_includes_proposal_format(self, registry):
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        assert "invoke_capability" in prompt
        assert "respond" in prompt
        assert '"action"' in prompt

    def test_prompt_includes_explicit_retrieval_rule(self, registry):
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        assert "search_knowledge_base" in prompt
        assert "explicitly" in prompt.lower() or "EXPLICITLY" in prompt

    def test_prompt_includes_policy_denial_rule(self, registry):
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        assert "Policy" in prompt
        assert "denial" in prompt.lower() or "denied" in prompt.lower()
        assert "final" in prompt.lower()

    def test_prompt_includes_untrusted_data_rule(self, registry):
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        assert "untrusted" in prompt.lower() or "UNTRUSTED" in prompt
        assert "extract_document" in prompt
        assert "search_knowledge_base" in prompt

    def test_prompt_includes_step_limit(self, registry):
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        assert "step" in prompt.lower()
        assert "limit" in prompt.lower() or "converge" in prompt.lower()

    def test_prompt_does_not_include_disabled_capabilities(self, registry):
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        # create_pptx is deferred/disabled — should not appear in prompt
        # (it's in registry.all() but not in the prompt since not enabled)
        # Check that deferred capability purpose is NOT in the prompt
        assert "PowerPoint" not in prompt

    def test_prompt_reads_from_registry_not_hand_copied(self, registry):
        """Verify prompt is built from registry.all(), not a hardcoded string."""
        prompt = build_system_prompt(registry, MAX_JOB_STEPS)
        # The prompt should contain the exact purpose text from the registry
        for cap in registry.all():
            if cap.enabled:
                # Purpose is read from registry, not hand-copied
                assert cap.purpose in prompt


# ===== Proposal Parser Tests =====

class TestProposalParser:
    def test_valid_invoke_capability(self, registry):
        raw = json.dumps({
            "action": "invoke_capability",
            "capability": "extract_document",
            "arguments": {"document_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8"},
        })
        result = parse_proposal(raw, registry)
        assert result.kind == "proposal"
        assert result.proposal is not None
        assert result.proposal.action == "invoke_capability"
        assert result.proposal.capability == "extract_document"

    def test_valid_respond(self, registry):
        raw = json.dumps({"action": "respond", "content": "The answer is 42."})
        result = parse_proposal(raw, registry)
        assert result.kind == "proposal"
        assert result.proposal is not None
        assert result.proposal.action == "respond"
        assert result.proposal.content == "The answer is 42."

    def test_non_json_output(self, registry):
        result = parse_proposal("This is not JSON at all", registry)
        assert result.kind == "malformed"
        assert "non-JSON" in result.error

    def test_unknown_action_value(self, registry):
        raw = json.dumps({"action": "execute", "capability": "test"})
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "unknown action" in result.error

    def test_missing_action_field(self, registry):
        raw = json.dumps({"capability": "test"})
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "missing" in result.error and "action" in result.error

    def test_unknown_capability_name(self, registry):
        raw = json.dumps({
            "action": "invoke_capability",
            "capability": "nonexistent_capability",
            "arguments": {},
        })
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "unknown capability" in result.error

    def test_schema_invalid_arguments(self, registry):
        raw = json.dumps({
            "action": "invoke_capability",
            "capability": "extract_document",
            "arguments": {"wrong_field": "value"},
        })
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "invalid arguments" in result.error.lower() or "validation" in result.error.lower()

    def test_invoke_missing_capability_field(self, registry):
        raw = json.dumps({
            "action": "invoke_capability",
            "arguments": {"document_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8"},
        })
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "capability" in result.error

    def test_invoke_missing_arguments_field(self, registry):
        raw = json.dumps({
            "action": "invoke_capability",
            "capability": "extract_document",
        })
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "arguments" in result.error

    def test_respond_missing_content_field(self, registry):
        raw = json.dumps({"action": "respond"})
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "content" in result.error

    def test_respond_content_not_string(self, registry):
        raw = json.dumps({"action": "respond", "content": 123})
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "string" in result.error

    def test_json_array_not_object(self, registry):
        raw = json.dumps([{"action": "respond", "content": "test"}])
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "not a JSON object" in result.error


# ===== test_terminate_on_empty_content (exact name per docs/agent.md) =====

class TestTerminateOnEmptyContent:
    def test_terminate_on_empty_content(self, registry):
        """Empty respond content → malformed, NOT terminal.

        This test is cited verbatim in docs/agent.md as the lock on this behavior.
        A respond with empty content must not terminate the Job — treat it as a
        malformed step, give the model one corrective turn per the malformed-output rule.
        """
        raw = json.dumps({"action": "respond", "content": ""})
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "empty respond content" in result.error

        # classify_step with no retry used: not terminal, does not count against limit
        outcome = classify_step(result, malformed_retry_used=False)
        assert outcome.terminal is False
        assert outcome.counts_against_limit is False

    def test_terminate_on_whitespace_only_content(self, registry):
        """Whitespace-only content is also empty per the strip() check."""
        raw = json.dumps({"action": "respond", "content": "   \n\t  "})
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        assert "empty respond content" in result.error

    def test_valid_respond_terminates(self, registry):
        """Non-empty respond content terminates the Job."""
        raw = json.dumps({"action": "respond", "content": "The answer is 42."})
        result = parse_proposal(raw, registry)
        assert result.kind == "proposal"
        outcome = classify_step(result, malformed_retry_used=False)
        assert outcome.terminal is True


# ===== classify_step Exhaustive Tests =====

class TestClassifyStep:
    def test_malformed_retry_not_used(self, registry):
        """Malformed + retry_used=False → free turn, does not count against limit."""
        raw = "not json"
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        outcome = classify_step(result, malformed_retry_used=False)
        assert outcome.counts_against_limit is False
        assert outcome.terminal is False

    def test_malformed_retry_used(self, registry):
        """Malformed + retry_used=True → counts against limit."""
        raw = "not json"
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        outcome = classify_step(result, malformed_retry_used=True)
        assert outcome.counts_against_limit is True
        assert outcome.terminal is False

    def test_malformed_unknown_capability_retry_not_used(self, registry):
        """Unknown capability + retry_used=False → free turn."""
        raw = json.dumps({
            "action": "invoke_capability",
            "capability": "nonexistent",
            "arguments": {},
        })
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        outcome = classify_step(result, malformed_retry_used=False)
        assert outcome.counts_against_limit is False
        assert outcome.terminal is False

    def test_malformed_unknown_capability_retry_used(self, registry):
        """Unknown capability + retry_used=True → counts against limit."""
        raw = json.dumps({
            "action": "invoke_capability",
            "capability": "nonexistent",
            "arguments": {},
        })
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"
        outcome = classify_step(result, malformed_retry_used=True)
        assert outcome.counts_against_limit is True
        assert outcome.terminal is False

    def test_valid_respond_non_empty(self, registry):
        """Valid respond with non-empty content → terminal, does not count."""
        raw = json.dumps({"action": "respond", "content": "Done."})
        result = parse_proposal(raw, registry)
        assert result.kind == "proposal"
        outcome = classify_step(result, malformed_retry_used=False)
        assert outcome.terminal is True
        assert outcome.counts_against_limit is False

    def test_valid_invoke_capability(self, registry):
        """Valid invoke_capability → not terminal, counts against limit."""
        raw = json.dumps({
            "action": "invoke_capability",
            "capability": "extract_document",
            "arguments": {"document_id": "6ba7b810-9dad-41d1-80b4-00c04fd430c8"},
        })
        result = parse_proposal(raw, registry)
        assert result.kind == "proposal"
        outcome = classify_step(result, malformed_retry_used=False)
        assert outcome.terminal is False
        assert outcome.counts_against_limit is True

    def test_empty_respond_malformed_not_terminal(self, registry):
        """Empty respond content → malformed, not terminal regardless of retry flag."""
        raw = json.dumps({"action": "respond", "content": ""})
        result = parse_proposal(raw, registry)
        assert result.kind == "malformed"

        outcome_no_retry = classify_step(result, malformed_retry_used=False)
        assert outcome_no_retry.terminal is False
        assert outcome_no_retry.counts_against_limit is False

        outcome_retry = classify_step(result, malformed_retry_used=True)
        assert outcome_retry.terminal is False
        assert outcome_retry.counts_against_limit is True


# ===== Agent step() Tests =====

class TestAgentStep:
    @pytest.mark.asyncio
    async def test_step_emits_orchestrator_step_event(self, registry):
        """orchestrator_step is emitted on every step() call."""
        fake_client = FakeModelClient([
            json.dumps({"action": "respond", "content": "Hello!"})
        ])
        ctx = _make_context(system_prompt="test prompt")

        with patch("backend.domain.orchestrator.agent.emit", new_callable=AsyncMock) as mock_emit:
            result = await step(ctx, fake_client, registry, MAX_JOB_STEPS)

            assert result.kind == "proposal"
            assert result.proposal is not None
            assert result.proposal.action == "respond"

            # Verify orchestrator_step was emitted
            mock_emit.assert_called_once()
            call_args = mock_emit.call_args
            assert call_args.kwargs["event_type"] == "orchestrator_step"
            assert call_args.kwargs["component"] == "orchestrator"
            assert call_args.kwargs["job_id"] == "test-job-id"
            payload = call_args.kwargs["payload"]
            assert payload["action"] == "respond"
            assert "raw_proposal" in payload

    @pytest.mark.asyncio
    async def test_step_emits_event_for_malformed_output(self, registry):
        """orchestrator_step emitted even for malformed output."""
        fake_client = FakeModelClient(["not valid json"])
        ctx = _make_context(system_prompt="test prompt")

        with patch("backend.domain.orchestrator.agent.emit", new_callable=AsyncMock) as mock_emit:
            result = await step(ctx, fake_client, registry, MAX_JOB_STEPS)

            assert result.kind == "malformed"
            mock_emit.assert_called_once()
            payload = mock_emit.call_args.kwargs["payload"]
            assert payload["action"] == "malformed"

    @pytest.mark.asyncio
    async def test_step_calls_model_with_reasoning_resource_type(self, registry):
        """step() calls model_client.generate with 'reasoning' resource type."""
        fake_client = FakeModelClient([
            json.dumps({"action": "respond", "content": "done"})
        ])
        ctx = _make_context(system_prompt="test prompt")

        with patch("backend.domain.orchestrator.agent.emit", new_callable=AsyncMock):
            await step(ctx, fake_client, registry, MAX_JOB_STEPS)

        assert len(fake_client.calls) == 1
        assert fake_client.calls[0]["resource_type"] == "reasoning"

    @pytest.mark.asyncio
    async def test_step_includes_conversation_history_in_prompt(self, registry):
        """step() includes conversation history in the prompt sent to the model."""
        fake_client = FakeModelClient([
            json.dumps({"action": "respond", "content": "done"})
        ])
        history = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "orchestrator", "content": "4"},
        ]
        ctx = _make_context(system_prompt="test", conversation_history=history)

        with patch("backend.domain.orchestrator.agent.emit", new_callable=AsyncMock):
            await step(ctx, fake_client, registry, MAX_JOB_STEPS)

        prompt_sent = fake_client.calls[0]["prompt"]
        assert "What is 2+2?" in prompt_sent
        assert "4" in prompt_sent

    @pytest.mark.asyncio
    async def test_step_includes_tool_results_in_prompt(self, registry):
        """step() includes tool results in the prompt."""
        fake_client = FakeModelClient([
            json.dumps({"action": "respond", "content": "done"})
        ])
        tool_results = [
            {
                "role": "tool_result",
                "capability": "extract_document",
                "result": {"extracted_text": "Hello world"},
                "status": "succeeded",
            }
        ]
        ctx = _make_context(system_prompt="test", tool_results=tool_results)

        with patch("backend.domain.orchestrator.agent.emit", new_callable=AsyncMock):
            await step(ctx, fake_client, registry, MAX_JOB_STEPS)

        prompt_sent = fake_client.calls[0]["prompt"]
        assert "extract_document" in prompt_sent
        assert "succeeded" in prompt_sent

    @pytest.mark.asyncio
    async def test_step_includes_malformed_error_in_prompt(self, registry):
        """step() includes malformed error as corrective context."""
        fake_client = FakeModelClient([
            json.dumps({"action": "respond", "content": "corrected"})
        ])
        ctx = _make_context(
            system_prompt="test",
            malformed_error="non-JSON output: Expecting value",
        )

        with patch("backend.domain.orchestrator.agent.emit", new_callable=AsyncMock):
            await step(ctx, fake_client, registry, MAX_JOB_STEPS)

        prompt_sent = fake_client.calls[0]["prompt"]
        assert "malformed" in prompt_sent.lower()
        assert "correct" in prompt_sent.lower()

    @pytest.mark.asyncio
    async def test_step_returns_parse_result(self, registry):
        """step() returns the ParseResult from the parser."""
        fake_client = FakeModelClient([
            json.dumps({"action": "respond", "content": "The answer is 42."})
        ])
        ctx = _make_context(system_prompt="test")

        with patch("backend.domain.orchestrator.agent.emit", new_callable=AsyncMock):
            result = await step(ctx, fake_client, registry, MAX_JOB_STEPS)

        assert isinstance(result, ParseResult)
        assert result.kind == "proposal"
        assert result.proposal.action == "respond"
        assert result.proposal.content == "The answer is 42."


# ===== Forbidden Imports Static Check =====

class TestForbiddenImports:
    def test_agent_py_has_no_forbidden_imports(self):
        """agent.py must NOT import from forbidden modules.

        Allowed: domain/capabilities/registry.py, domain/audit/events.py
        Forbidden: domain/model_runtime, domain/policy (engine), domain/sandbox,
                   domain/rag, domain/artifacts, domain/document_processing,
                   domain/capabilities/<executor files>
        """
        agent_path = Path(__file__).parent.parent / "domain" / "orchestrator" / "agent.py"
        content = agent_path.read_text()

        forbidden_patterns = [
            r"from\s+backend\.domain\.model_runtime",
            r"import\s+backend\.domain\.model_runtime",
            r"from\s+backend\.domain\.policy",
            r"import\s+backend\.domain\.policy",
            r"from\s+backend\.domain\.sandbox",
            r"import\s+backend\.domain\.sandbox",
            r"from\s+backend\.domain\.rag",
            r"import\s+backend\.domain\.rag",
            r"from\s+backend\.domain\.artifacts",
            r"import\s+backend\.domain\.artifacts",
            r"from\s+backend\.domain\.document_processing",
            r"import\s+backend\.domain\.document_processing",
            # Executor files under capabilities
            r"from\s+backend\.domain\.capabilities\.(extract_document|search_knowledge_base|generate_code|execute_code|create_docx|create_xlsx|create_pptx)",
            r"import\s+backend\.domain\.capabilities\.(extract_document|search_knowledge_base|generate_code|execute_code|create_docx|create_xlsx|create_pptx)",
        ]

        for pattern in forbidden_patterns:
            match = re.search(pattern, content)
            assert match is None, f"agent.py contains forbidden import: {match.group()}"

    def test_agent_py_allows_registry_import(self):
        """agent.py is allowed to import from domain/capabilities/registry.py."""
        agent_path = Path(__file__).parent.parent / "domain" / "orchestrator" / "agent.py"
        content = agent_path.read_text()
        assert "from backend.domain.capabilities.registry import" in content

    def test_agent_py_allows_audit_emit_import(self):
        """agent.py is allowed to import emit from domain/audit/events.py."""
        agent_path = Path(__file__).parent.parent / "domain" / "orchestrator" / "agent.py"
        content = agent_path.read_text()
        assert "from backend.domain.audit.events import emit" in content
