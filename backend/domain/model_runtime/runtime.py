"""
Model Runtime — Ollama HTTP Client Wrapper

The single backend module that talks to Ollama's local HTTP API.
Callers request a resource type (reasoning, code_generation, vision, embedding);
this module resolves it via config/resources.yaml to a concrete model and calls
the appropriate Ollama endpoint.

Emits model_invoked audit events and writes model_executions rows.
Fails cleanly with typed errors when Ollama is unreachable — never hangs.
"""

from __future__ import annotations

import base64
import time
from typing import Optional

import httpx

from backend.config import settings
from backend.domain.audit.events import emit
from backend.repositories.jobs import add_model_execution
from backend.models.schemas import EmbeddingResult, GenerationResult


# Locked connect timeout — NOT configurable, deliberately distinct from request timeout.
# This catches "Ollama not running at all" fast (~5s), while the 120s request timeout
# tolerates genuine cold model loads. See Task 8 spec §7 Requirement 5.
CONNECT_TIMEOUT_SECONDS = 5

# Allowed Ollama options keys that callers may pass through.
# Runtime-controlled fields (model, stream, keep_alive, endpoint) are blocked.
ALLOWED_GENERATE_OPTIONS = frozenset({
    "temperature",
    "top_p",
    "top_k",
    "repeat_penalty",
    "num_predict",
    "num_ctx",
    "seed",
    "stop",
})


class ModelRuntimeUnavailableError(Exception):
    """Ollama connection refused / DNS / unreachable — fast failure (~5s)."""
    pass


class ModelRuntimeError(Exception):
    """Non-2xx from Ollama (bad model name, OOM, etc.)."""
    pass


class OllamaRuntime:
    """Thin wrapper around Ollama's HTTP API (/api/generate, /api/embed)."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            if self._client is not None:
                await self._client.aclose()
            self._client = httpx.AsyncClient(
                base_url=settings.app.ollama.base_url,
                timeout=httpx.Timeout(
                    connect=CONNECT_TIMEOUT_SECONDS,
                    read=settings.app.ollama.request_timeout_seconds,
                    write=settings.app.ollama.request_timeout_seconds,
                    pool=settings.app.ollama.request_timeout_seconds,
                ),
            )
        return self._client

    def _resolve(self, resource_type: str):
        """Resolve resource_type to its config entry (model, keep_alive, etc.)."""
        try:
            return settings.resources.for_type(resource_type)
        except KeyError as e:
            raise ValueError(str(e)) from e

    async def generate(
        self,
        resource_type: str,
        prompt: str,
        *,
        images: list[bytes] | None = None,
        options: dict | None = None,
        job_id: str | None = None,
    ) -> GenerationResult:
        """
        Generate text using the specified resource type.

        Args:
            resource_type: One of "reasoning", "code_generation", "vision".
            prompt: The input prompt.
            images: Optional list of image bytes (only used for vision).
            options: Optional dict of Ollama generation options (filtered to allowed keys).

        Returns:
            GenerationResult with text, token counts, timing, and model info.

        Raises:
            ModelRuntimeUnavailableError: If Ollama is unreachable.
            ModelRuntimeError: If Ollama returns non-2xx.
            ValueError: If resource_type is unknown.
        """
        entry = self._resolve(resource_type)
        model = entry.model
        keep_alive = entry.keep_alive

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
        }

        if options:
            filtered = {k: v for k, v in options.items() if k in ALLOWED_GENERATE_OPTIONS}
            if filtered:
                payload["options"] = filtered

        if images:
            payload["images"] = [base64.b64encode(img).decode() for img in images]

        client = await self._get_client()
        start = time.perf_counter()

        try:
            resp = await client.post("/api/generate", json=payload)
            duration_ms = int((time.perf_counter() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()

            # Best-effort load_triggered: cold loads take significantly longer
            load_triggered = duration_ms > 30000

            result = GenerationResult(
                text=data.get("response", ""),
                prompt_tokens=data.get("prompt_eval_count"),
                completion_tokens=data.get("eval_count"),
                duration_ms=duration_ms,
                model_identifier=model,
                load_triggered=load_triggered,
            )

            await self._record(model, resource_type, result, capability_execution_id=None, job_id=job_id)

            return result

        except httpx.ConnectError as e:
            await emit(
                "error",
                "model_runtime",
                {"component": "model_runtime", "message": str(e), "context": {"resource_type": resource_type}},
                job_id=job_id,
            )
            raise ModelRuntimeUnavailableError(f"Ollama unreachable: {e}") from e
        except httpx.ConnectTimeout as e:
            await emit(
                "error",
                "model_runtime",
                {"component": "model_runtime", "message": "Connection timeout", "context": {"resource_type": resource_type}},
                job_id=job_id,
            )
            raise ModelRuntimeUnavailableError("Ollama connection timeout (5s)") from e
        except httpx.HTTPStatusError as e:
            await emit(
                "error",
                "model_runtime",
                {
                    "component": "model_runtime",
                    "message": f"HTTP {e.response.status_code}",
                    "context": {"resource_type": resource_type, "body": e.response.text},
                },
                job_id=job_id,
            )
            raise ModelRuntimeError(f"Ollama error {e.response.status_code}: {e.response.text}") from e

    async def embed(
        self,
        resource_type: str,
        text: str | list[str],
        *,
        job_id: str | None = None,
    ) -> EmbeddingResult:
        """
        Generate embeddings using the embedding resource type.

        Args:
            resource_type: Must be "embedding".
            text: Single string or list of strings to embed.

        Returns:
            EmbeddingResult with vectors, timing, and model info.

        Raises:
            ModelRuntimeUnavailableError: If Ollama is unreachable.
            ModelRuntimeError: If Ollama returns non-2xx.
            ValueError: If resource_type is not "embedding".
        """
        if resource_type != "embedding":
            raise ValueError(f"embed() only supports 'embedding' resource type, got '{resource_type}'")

        entry = self._resolve(resource_type)
        model = entry.model
        keep_alive = entry.keep_alive

        texts = [text] if isinstance(text, str) else text
        payload = {
            "model": model,
            "input": texts,
            "keep_alive": keep_alive,
        }

        client = await self._get_client()
        start = time.perf_counter()

        try:
            resp = await client.post("/api/embed", json=payload)
            duration_ms = int((time.perf_counter() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()

            load_triggered = duration_ms > 10000

            result = EmbeddingResult(
                embeddings=data.get("embeddings", []),
                prompt_tokens=None,
                duration_ms=duration_ms,
                model_identifier=model,
                load_triggered=load_triggered,
            )

            await self._record(model, resource_type, result, capability_execution_id=None, job_id=job_id)

            return result

        except httpx.ConnectError as e:
            await emit(
                "error",
                "model_runtime",
                {"component": "model_runtime", "message": str(e), "context": {"resource_type": resource_type}},
                job_id=job_id,
            )
            raise ModelRuntimeUnavailableError(f"Ollama unreachable: {e}") from e
        except httpx.ConnectTimeout as e:
            await emit(
                "error",
                "model_runtime",
                {"component": "model_runtime", "message": "Connection timeout", "context": {"resource_type": resource_type}},
                job_id=job_id,
            )
            raise ModelRuntimeUnavailableError("Ollama connection timeout (5s)") from e
        except httpx.HTTPStatusError as e:
            await emit(
                "error",
                "model_runtime",
                {
                    "component": "model_runtime",
                    "message": f"HTTP {e.response.status_code}",
                    "context": {"resource_type": resource_type, "body": e.response.text},
                },
                job_id=job_id,
            )
            raise ModelRuntimeError(f"Ollama error {e.response.status_code}: {e.response.text}") from e

    async def is_model_loaded(self, model_identifier: str) -> bool:
        """Return whether the specified model is currently loaded in Ollama.

        Ollama's process/model-state endpoint is intentionally accessed only
        through Model Runtime. Lifecycle Manager must not know Ollama HTTP
        endpoints.
        """
        client = await self._get_client()

        try:
            response = await client.get("/api/ps")
            response.raise_for_status()
            data = response.json()

            return any(
                model_info.get("name") == model_identifier
                for model_info in data.get("models", [])
            )

        except httpx.ConnectError as e:
            raise ModelRuntimeUnavailableError(
                f"Ollama unreachable: {e}"
            ) from e

        except httpx.ConnectTimeout as e:
            raise ModelRuntimeUnavailableError(
                "Ollama connection timeout (5s)"
            ) from e

        except httpx.HTTPStatusError as e:
            raise ModelRuntimeError(
                f"Ollama error {e.response.status_code}: "
                f"{e.response.text}"
            ) from e

    async def unload(self, model_identifier: str) -> None:
        """Request immediate unloading of a model from Ollama.

        The lifecycle policy belongs to Lifecycle Manager; the HTTP operation
        belongs here in Model Runtime.
        """
        client = await self._get_client()

        payload = {
            "model": model_identifier,
            "prompt": "",
            "stream": False,
            "keep_alive": 0,
        }

        try:
            response = await client.post("/api/generate", json=payload)
            response.raise_for_status()

        except httpx.ConnectError as e:
            raise ModelRuntimeUnavailableError(
                f"Ollama unreachable: {e}"
            ) from e

        except httpx.ConnectTimeout as e:
            raise ModelRuntimeUnavailableError(
                "Ollama connection timeout (5s)"
            ) from e

        except httpx.HTTPStatusError as e:
            raise ModelRuntimeError(
                f"Ollama error {e.response.status_code}: "
                f"{e.response.text}"
            ) from e

    async def _record(
        self,
        model: str,
        resource_type: str,
        result: GenerationResult | EmbeddingResult,
        capability_execution_id: Optional[str],
        job_id: Optional[str] = None,
    ) -> None:
        """Emit model_invoked event and write model_executions row."""
        await emit(
            event_type="model_invoked",
            component="model_runtime",
            payload={
                "resource_type": resource_type,
                "model_identifier": model,
                "prompt_tokens": getattr(result, "prompt_tokens", None),
                "completion_tokens": getattr(result, "completion_tokens", None),
                "duration_ms": result.duration_ms,
            },
            job_id=job_id,
        )

        if capability_execution_id:
            add_model_execution(
                capability_execution_id=capability_execution_id,
                resource_type=resource_type,
                model_identifier=model,
                runtime="ollama",
                prompt_tokens=getattr(result, "prompt_tokens", None),
                completion_tokens=getattr(result, "completion_tokens", None),
                duration_ms=result.duration_ms,
                load_triggered=result.load_triggered,
            )


# Module-level singleton for dependency injection.
# Matches the ModelClient Protocol in backend/models/schemas.py field-for-field.
runtime = OllamaRuntime()