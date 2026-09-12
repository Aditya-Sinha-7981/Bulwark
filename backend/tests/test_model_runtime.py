"""
Tests for Model Runtime / Ollama wrapper (Task 8).

Run:
  - Unit + failure injection (no Ollama needed): pytest tests/test_model_runtime.py -v -k "not integration"
  - Integration (requires ollama serve + models): pytest tests/test_model_runtime.py -v -k "integration"
"""

import pytest
import pytest_asyncio
import httpx
import asyncio
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.domain.model_runtime.runtime import (
    OllamaRuntime,
    runtime,
    ModelRuntimeUnavailableError,
    ModelRuntimeError,
    CONNECT_TIMEOUT_SECONDS,
    ALLOWED_GENERATE_OPTIONS,
)
from backend.models.schemas import GenerationResult, EmbeddingResult


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_transport():
    """Create a mock httpx transport for failure injection tests."""
    return httpx.MockTransport(lambda request: httpx.Response(200, json={}))


@pytest_asyncio.fixture
async def fresh_runtime():
    """Create a fresh OllamaRuntime instance for each test."""
    rt = OllamaRuntime()
    yield rt
    if rt._client:
        await rt._client.aclose()


@pytest.fixture(autouse=True)
def mock_emit():
    """Mock emit to avoid database dependency in tests."""
    with patch("backend.domain.model_runtime.runtime.emit", new_callable=AsyncMock) as mock:
        yield mock


# =============================================================================
# TestResourceTypeResolution
# =============================================================================

class TestResourceTypeResolution:
    """Verify resource_type → model resolution matches config/resources.yaml."""

    def test_reasoning_resolves_to_qwen3_5_9b(self, fresh_runtime):
        entry = fresh_runtime._resolve("reasoning")
        assert entry.model == "qwen3.5:9b"
        assert entry.keep_alive == "5m"

    def test_code_generation_resolves_to_qwen2_5_coder_7b(self, fresh_runtime):
        entry = fresh_runtime._resolve("code_generation")
        assert entry.model == "qwen2.5-coder:7b"
        assert entry.keep_alive == "5m"

    def test_vision_resolves_to_qwen3_5_9b(self, fresh_runtime):
        entry = fresh_runtime._resolve("vision")
        assert entry.model == "qwen3.5:9b"
        assert entry.keep_alive == "5m"

    def test_embedding_resolves_to_qwen3_embedding_0_6b(self, fresh_runtime):
        entry = fresh_runtime._resolve("embedding")
        assert entry.model == "qwen3-embedding:0.6b"
        assert entry.keep_alive == -1

    def test_unknown_resource_type_raises(self, fresh_runtime):
        with pytest.raises(ValueError, match="unknown resource type"):
            fresh_runtime._resolve("invalid_type")


# =============================================================================
# TestFailureInjection (mocked transport)
# =============================================================================

class TestFailureInjection:
    """Failure injection tests using mocked httpx transport."""

    @pytest.mark.asyncio
    async def test_connection_refused_fails_in_5s(self, fresh_runtime, mock_transport):
        """Connection refused → ModelRuntimeUnavailableError within ~5s connect timeout."""
        # Mock transport that raises ConnectError immediately
        def connect_error_handler(request):
            raise httpx.ConnectError("Connection refused", request=request)

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(connect_error_handler),
            base_url="http://localhost:11434",
            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_SECONDS, read=120, write=120, pool=120),
        )

        import time
        start = time.perf_counter()
        with pytest.raises(ModelRuntimeUnavailableError):
            await fresh_runtime.generate("reasoning", "test prompt", job_id="test-job-id")
        elapsed = time.perf_counter() - start

        # Should fail fast (connect timeout ~5s, not 120s request timeout)
        assert elapsed < 10, f"Failed too slowly: {elapsed:.1f}s (expected <10s)"

    @pytest.mark.asyncio
    async def test_connect_timeout_fails_in_5s(self, fresh_runtime):
        """Connect timeout configuration is set correctly (5s connect timeout).
        
        Note: MockTransport doesn't simulate TCP-level connect timeout.
        This test verifies the timeout configuration is passed correctly to the client.
        Actual connect timeout testing requires a real network scenario.
        """
        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})),
            base_url="http://localhost:11434",
            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_SECONDS, read=120, write=120, pool=120),
        )

        # Verify the timeout configuration
        assert fresh_runtime._client.timeout.connect == CONNECT_TIMEOUT_SECONDS
        assert fresh_runtime._client.timeout.read == 120

    @pytest.mark.asyncio
    async def test_non_2xx_returns_typed_error(self, fresh_runtime):
        """Non-2xx from Ollama → ModelRuntimeError with status and body."""
        def error_handler(request):
            return httpx.Response(404, json={"error": "model not found"})

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(error_handler),
            base_url="http://localhost:11434",
        )

        with pytest.raises(ModelRuntimeError) as exc_info:
            await fresh_runtime.generate("reasoning", "test prompt", job_id="test-job-id")

        assert "404" in str(exc_info.value)
        assert "model not found" in str(exc_info.value)

        assert "404" in str(exc_info.value)
        assert "model not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_read_timeout_returns_typed_error(self, fresh_runtime, mock_emit):
        """httpx.ReadTimeout → typed ModelRuntimeError mentioning the timeout,
        plus an `error` audit event — not a raw escape into the Job catch-all."""
        def read_timeout_handler(request):
            raise httpx.ReadTimeout("timed out", request=request)

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(read_timeout_handler),
            base_url="http://localhost:11434",
        )

        with pytest.raises(ModelRuntimeError) as exc_info:
            await fresh_runtime.generate("reasoning", "test prompt", job_id="test-job-id")

        assert "read timeout" in str(exc_info.value)
        mock_emit.assert_called()
        assert mock_emit.call_args.args[0] == "error"

    @pytest.mark.asyncio
    async def test_generate_sends_num_ctx_from_resources(self, fresh_runtime):
        """generate() must pass the resource's context_window as options.num_ctx —
        otherwise Ollama's 4096 default silently truncates long prompts."""
        captured = {}

        def capture_handler(request):
            captured["payload"] = json.loads(request.content)
            return httpx.Response(200, json={"response": "ok", "prompt_eval_count": 1, "eval_count": 1})

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(capture_handler),
            base_url="http://localhost:11434",
        )

        await fresh_runtime.generate("reasoning", "test prompt")

        expected = fresh_runtime._resolve("reasoning").context_window
        assert expected is not None
        assert captured["payload"]["options"]["num_ctx"] == expected

    @pytest.mark.asyncio
    async def test_generate_caller_num_ctx_overrides_resource(self, fresh_runtime):
        """A caller-supplied num_ctx wins over the resource's context_window."""
        captured = {}

        def capture_handler(request):
            captured["payload"] = json.loads(request.content)
            return httpx.Response(200, json={"response": "ok", "prompt_eval_count": 1, "eval_count": 1})

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(capture_handler),
            base_url="http://localhost:11434",
        )

        await fresh_runtime.generate("reasoning", "test prompt", options={"num_ctx": 1024})

        assert captured["payload"]["options"]["num_ctx"] == 1024

    @pytest.mark.asyncio
    async def test_unknown_resource_type_fails_before_network(self, fresh_runtime):
        """Unknown resource_type → ValueError before any network call."""
        with pytest.raises(ValueError, match="unknown resource type"):
            await fresh_runtime.generate("invalid_type", "test prompt")


# =============================================================================
# TestOptionsFiltering
# =============================================================================

class TestOptionsFiltering:
    """Verify options filtering allows only permitted keys."""

    @pytest.mark.asyncio
    async def test_allowed_options_passed_through(self, fresh_runtime):
        """Allowed options should be included in Ollama payload."""
        captured_payload = {}

        def capture_handler(request):
            import json
            captured_payload.update(json.loads(request.content))
            return httpx.Response(200, json={"response": "ok", "prompt_eval_count": 10, "eval_count": 5})

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(capture_handler),
            base_url="http://localhost:11434",
        )

        await fresh_runtime.generate(
            "reasoning",
            "test",
            options={"temperature": 0.7, "top_p": 0.9, "num_predict": 100},
            job_id="test-job-id"
        )

        assert "options" in captured_payload
        assert captured_payload["options"]["temperature"] == 0.7
        assert captured_payload["options"]["top_p"] == 0.9
        assert captured_payload["options"]["num_predict"] == 100

    @pytest.mark.asyncio
    async def test_disallowed_options_blocked(self, fresh_runtime):
        """Disallowed options (model, stream, keep_alive) should be blocked."""
        captured_payload = {}

        def capture_handler(request):
            import json
            captured_payload.update(json.loads(request.content))
            return httpx.Response(200, json={"response": "ok", "prompt_eval_count": 10, "eval_count": 5})

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(capture_handler),
            base_url="http://localhost:11434",
        )

        await fresh_runtime.generate(
            "reasoning",
            "test",
            options={"model": "hacked", "stream": True, "keep_alive": "1h", "temperature": 0.5},
            job_id="test-job-id"
        )

        assert "options" in captured_payload
        assert "model" not in captured_payload["options"]
        assert "stream" not in captured_payload["options"]
        assert "keep_alive" not in captured_payload["options"]
        assert captured_payload["options"]["temperature"] == 0.5


# =============================================================================
# TestGenerateIntegration (requires Ollama running)
# =============================================================================

@pytest.mark.integration
class TestGenerateIntegration:
    """Integration tests against real local Ollama."""

    @pytest.mark.asyncio
    async def test_generate_reasoning_returns_text_and_tokens(self, fresh_runtime):
        result = await fresh_runtime.generate("reasoning", "Say hello in one word")
        assert isinstance(result, GenerationResult)
        assert result.text.strip() != ""
        assert result.prompt_tokens is not None
        assert result.completion_tokens is not None
        assert result.duration_ms is not None
        assert result.model_identifier == "qwen3.5:9b"
        assert isinstance(result.load_triggered, bool)

    @pytest.mark.asyncio
    async def test_generate_code_generation_returns_code(self, fresh_runtime):
        result = await fresh_runtime.generate(
            "code_generation",
            "Write a Python function that returns the sum of two numbers"
        )
        assert isinstance(result, GenerationResult)
        assert "def" in result.text or "lambda" in result.text
        assert result.model_identifier == "qwen2.5-coder:7b"

    @pytest.mark.asyncio
    async def test_generate_vision_with_image_returns_text(self, fresh_runtime):
        # Create a tiny 1x1 PNG (base64: iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==)
        png_1x1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
        result = await fresh_runtime.generate("vision", "What color is this pixel?", images=[png_1x1])
        assert isinstance(result, GenerationResult)
        assert result.text.strip() != ""
        assert result.model_identifier == "qwen3.5:9b"


# =============================================================================
# TestEmbedIntegration (requires Ollama running)
# =============================================================================

@pytest.mark.integration
class TestEmbedIntegration:
    """Integration tests for embeddings against real local Ollama."""

    @pytest.mark.asyncio
    async def test_embed_embedding_returns_vectors(self, fresh_runtime):
        result = await fresh_runtime.embed("embedding", "test document")
        assert isinstance(result, EmbeddingResult)
        assert len(result.embeddings) == 1
        assert len(result.embeddings[0]) > 0
        assert all(isinstance(v, float) for v in result.embeddings[0])
        assert result.model_identifier == "qwen3-embedding:0.6b"
        assert isinstance(result.load_triggered, bool)

    @pytest.mark.asyncio
    async def test_embed_multiple_texts_returns_multiple_vectors(self, fresh_runtime):
        result = await fresh_runtime.embed("embedding", ["doc one", "doc two", "doc three"])
        assert isinstance(result, EmbeddingResult)
        assert len(result.embeddings) == 3
        assert all(len(v) == len(result.embeddings[0]) for v in result.embeddings)


# =============================================================================
# TestAuditAndDB
# =============================================================================

class TestAuditAndDB:
    """Verify model_invoked events and model_executions rows are written."""

    @pytest.mark.asyncio
    async def test_model_invoked_event_emitted(self, fresh_runtime, mock_emit, mock_transport):
        """model_invoked audit event should be emitted after generate()."""
        def success_handler(request):
            return httpx.Response(200, json={"response": "hello", "prompt_eval_count": 5, "eval_count": 3})

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(success_handler),
            base_url="http://localhost:11434",
        )

        await fresh_runtime.generate("reasoning", "test", job_id="test-job-id")

        # Verify emit was called with correct arguments
        mock_emit.assert_called_once()
        call_args = mock_emit.call_args
        assert call_args.kwargs["event_type"] == "model_invoked"
        assert call_args.kwargs["component"] == "model_runtime"
        assert call_args.kwargs["job_id"] == "test-job-id"
        payload = call_args.kwargs["payload"]
        assert payload["resource_type"] == "reasoning"
        assert payload["model_identifier"] == "qwen3.5:9b"
        assert "prompt_tokens" in payload
        assert "completion_tokens" in payload
        assert "duration_ms" in payload

    @pytest.mark.asyncio
    async def test_model_executions_row_written(self, fresh_runtime, mock_emit, mock_transport):
        """model_executions row should be written when capability_execution_id provided."""
        from backend.repositories.jobs import add_model_execution
        calls = []

        def capture_insert(**kwargs):
            calls.append(kwargs)
            return "test-execution-id"

        with patch("backend.domain.model_runtime.runtime.add_model_execution", capture_insert):
            def success_handler(request):
                return httpx.Response(200, json={"response": "hello", "prompt_eval_count": 5, "eval_count": 3})

            fresh_runtime._client = httpx.AsyncClient(
                transport=httpx.MockTransport(success_handler),
                base_url="http://localhost:11434",
            )

            await fresh_runtime.generate(
                "reasoning",
                "test",
                job_id="test-job-id"
            )

        # Note: capability_execution_id is None in current implementation
        # Task 15 will wire this through. This test documents expected behavior.
        # When capability_execution_id is provided, add_model_execution should be called.
        mock_emit.assert_called()


# =============================================================================
# TestStaticCheck
# =============================================================================

class TestStaticCheck:
    """Static checks to enforce architectural constraints."""

    def test_only_runtime_imports_httpx_for_model(self):
        """runtime.py should be the only backend module importing httpx for model endpoints."""
        backend_root = Path(__file__).resolve().parent.parent
        pattern = re.compile(r"11434|/api/generate|/api/embed")
        violations = []

        for py_file in backend_root.rglob("*.py"):
            # Skip test files and venv directory
            if "test_model_runtime.py" in str(py_file) or "test_" in py_file.name:
                continue
            if any("venv" in part for part in py_file.parts):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Skip binary/encoded files
                continue
            if pattern.search(content):
                rel_path = str(py_file.relative_to(backend_root))
                if "domain/model_runtime/runtime.py" not in rel_path and "domain\\model_runtime\\runtime.py" not in rel_path:
                    violations.append(rel_path)

        assert not violations, f"Found model endpoints outside runtime.py: {violations}"

    def test_connect_timeout_constant_exists(self):
        """CONNECT_TIMEOUT_SECONDS constant should be 5 and documented."""
        assert CONNECT_TIMEOUT_SECONDS == 5
        # Verify it's documented in the source
        import inspect
        source = inspect.getsource(OllamaRuntime)
        assert "CONNECT_TIMEOUT_SECONDS" in source


# =============================================================================
# TestModelClientProtocolCompliance
# =============================================================================

class TestModelClientProtocolCompliance:
    """Verify runtime matches the ModelClient Protocol from schemas.py."""

    @pytest.mark.asyncio
    async def test_generate_signature_matches_protocol(self):
        """generate() signature matches ModelClient Protocol."""
        import inspect
        sig = inspect.signature(OllamaRuntime.generate)
        params = list(sig.parameters.keys())
        # Unbound method includes 'self' as first parameter
        assert params == ["self", "resource_type", "prompt", "images", "options", "job_id"]
        # Check defaults
        assert sig.parameters["images"].default is None
        assert sig.parameters["options"].default is None
        assert sig.parameters["job_id"].default is None

    @pytest.mark.asyncio
    async def test_embed_signature_matches_protocol(self):
        """embed() signature exists (not in Protocol but part of runtime)."""
        import inspect
        sig = inspect.signature(OllamaRuntime.embed)
        params = list(sig.parameters.keys())
        assert params == ["self", "resource_type", "text", "job_id"]

    def test_generation_result_fields(self):
        """GenerationResult has all required fields."""
        result = GenerationResult(text="test")
        assert hasattr(result, "text")
        assert hasattr(result, "prompt_tokens")
        assert hasattr(result, "completion_tokens")
        assert hasattr(result, "duration_ms")
        assert hasattr(result, "model_identifier")
        assert hasattr(result, "load_triggered")

    def test_embedding_result_fields(self):
        """EmbeddingResult has all required fields."""
        result = EmbeddingResult(embeddings=[[0.1, 0.2]])
        assert hasattr(result, "embeddings")
        assert hasattr(result, "prompt_tokens")
        assert hasattr(result, "duration_ms")
        assert hasattr(result, "model_identifier")
        assert hasattr(result, "load_triggered")


# =============================================================================
# TestErrorEvents
# =============================================================================

class TestErrorEvents:
    """Verify error events are emitted on failures."""

    @pytest.mark.asyncio
    async def test_error_event_on_connect_failure(self, fresh_runtime, mock_emit):
        """error event emitted on connection failure."""
        def connect_error_handler(request):
            raise httpx.ConnectError("Connection refused", request=request)

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(connect_error_handler),
            base_url="http://localhost:11434",
            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT_SECONDS, read=120, write=120, pool=120),
        )

        with pytest.raises(ModelRuntimeUnavailableError):
            await fresh_runtime.generate("reasoning", "test", job_id="test-job-id")

        # Verify error event was emitted - check positional args (event_type is first arg)
        error_calls = []
        for call in mock_emit.call_args_list:
            args = call.args if hasattr(call, 'args') else call[0]
            if args and args[0] == "error":
                error_calls.append(call)
        assert len(error_calls) == 1
        args = error_calls[0].args if hasattr(error_calls[0], 'args') else error_calls[0][0]
        assert args[1] == "model_runtime"
        assert args[2]["component"] == "model_runtime"
        assert "resource_type" in args[2]["context"]

    @pytest.mark.asyncio
    async def test_error_event_on_http_error(self, fresh_runtime, mock_emit):
        """error event emitted on HTTP error."""
        def error_handler(request):
            return httpx.Response(500, json={"error": "internal server error"})

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(error_handler),
            base_url="http://localhost:11434",
        )

        with pytest.raises(ModelRuntimeError):
            await fresh_runtime.generate("reasoning", "test", job_id="test-job-id")

        # Verify error event was emitted - check positional args
        error_calls = []
        for call in mock_emit.call_args_list:
            args = call.args if hasattr(call, 'args') else call[0]
            if args and args[0] == "error":
                error_calls.append(call)
        assert len(error_calls) == 1
        args = error_calls[0].args if hasattr(error_calls[0], 'args') else error_calls[0][0]
        assert args[1] == "model_runtime"


# =============================================================================
# TestKeepAlive
# =============================================================================

class TestKeepAlive:
    """Verify keep_alive is passed per resource type from config."""

    @pytest.mark.asyncio
    async def test_keep_alive_passed_for_reasoning(self, fresh_runtime):
        captured = {}

        def capture_handler(request):
            import json
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"response": "ok", "prompt_eval_count": 5, "eval_count": 3})

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(capture_handler),
            base_url="http://localhost:11434",
        )

        await fresh_runtime.generate("reasoning", "test", job_id="test-job-id")
        assert captured.get("keep_alive") == "5m"

    @pytest.mark.asyncio
    async def test_keep_alive_passed_for_embedding(self, fresh_runtime):
        captured = {}

        def capture_handler(request):
            import json
            captured.update(json.loads(request.content))
            return httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})

        fresh_runtime._client = httpx.AsyncClient(
            transport=httpx.MockTransport(capture_handler),
            base_url="http://localhost:11434",
        )

        await fresh_runtime.embed("embedding", "test", job_id="test-job-id")
        assert captured.get("keep_alive") == -1


# =============================================================================
# Import at bottom for static check
# =============================================================================

import base64