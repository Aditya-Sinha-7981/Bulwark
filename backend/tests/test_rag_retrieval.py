"""
Tests for the RAG retrieval pipeline and search_knowledge_base capability
(Task 12.b).

Covers the retrieval half of the round-trip (docs/testing.md "RAG tests");
ingestion is Task 12.a. Manually seeds a temp Chroma collection matching
Task 12.a's frozen metadata contract (kb_document_id, title, category,
chunk_index) rather than going through the ingestion pipeline, per this
task's "Parallel-development notes".
"""

import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from backend.domain.capabilities import search_knowledge_base as skb
from backend.domain.model_runtime.runtime import ModelRuntimeError, ModelRuntimeUnavailableError
from backend.domain.rag import ingestion as ingestion_module
from backend.domain.rag import retrieval as retrieval_module
from backend.models.schemas import EmbeddingResult


class FakeEmbed:
    """Deterministic fake embedding backend — a fixed vector per query string,
    so tests can craft exact Chroma L2 distances (and therefore exact scores)."""

    def __init__(self):
        self.vector_for: dict[str, list[float]] = {}
        self.raise_error: Exception | None = None
        self.calls: list[str] = []

    async def __call__(self, resource_type, text, *, job_id=None):
        assert resource_type == "embedding"
        self.calls.append(text)
        if self.raise_error:
            raise self.raise_error
        vector = self.vector_for.get(text, [0.0, 0.0])
        return EmbeddingResult(embeddings=[vector], duration_ms=1, model_identifier="fake-embed")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Temp Chroma dir + fake embedding backend, isolated per test."""
    chroma_path = tmp_path / "chroma"
    monkeypatch.setattr(ingestion_module, "chroma_dir", lambda: chroma_path)
    ingestion_module.reset_chroma_client()

    fake_embed = FakeEmbed()
    monkeypatch.setattr(retrieval_module.model_runtime, "embed", fake_embed)

    yield {"chroma_path": chroma_path, "fake_embed": fake_embed}

    ingestion_module.reset_chroma_client()


def _doc_id(name: str) -> str:
    """Deterministic, readable-name -> valid-UUID mapping (kb_document_id is
    UUID-typed per docs/capabilities.md, but tests want stable readable names)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name))


def _seed_chunk(doc_name, chunk_index, title, chunk_text, vector, category="maintenance"):
    """Write one chunk directly into the shared knowledge_base collection,
    matching Task 12.a's frozen chunk-metadata contract exactly. Returns the
    UUID actually stored as kb_document_id."""
    kb_document_id = _doc_id(doc_name)
    collection = ingestion_module.get_kb_collection()
    collection.add(
        ids=[f"{kb_document_id}:{chunk_index}"],
        embeddings=[vector],
        metadatas=[
            {
                "kb_document_id": kb_document_id,
                "title": title,
                "category": category,
                "chunk_index": chunk_index,
            }
        ],
        documents=[chunk_text],
    )
    return kb_document_id


class TestRelevantQuery:
    @pytest.mark.asyncio
    async def test_relevant_hit_returned_with_score_and_shape(self, env):
        query_vector = [0.0, 0.0]
        env["fake_embed"].vector_for["pump maintenance procedure"] = query_vector
        _seed_chunk("doc-1", 0, "Pump SOP", "Follow the pump maintenance procedure.", query_vector)

        hits = await retrieval_module.retrieve("pump maintenance procedure", top_k=5)

        assert len(hits) == 1
        hit = hits[0]
        assert set(hit.keys()) == {"kb_document_id", "title", "chunk_text", "score"}
        assert hit["kb_document_id"] == _doc_id("doc-1")
        assert hit["title"] == "Pump SOP"
        assert hit["chunk_text"] == "Follow the pump maintenance procedure."
        assert hit["score"] >= retrieval_module.RELEVANCE_FLOOR

    @pytest.mark.asyncio
    async def test_hits_ordered_by_score_descending(self, env):
        query_vector = [0.0, 0.0]
        env["fake_embed"].vector_for["q"] = query_vector
        # Closer vector (smaller distance -> higher score) seeded second,
        # so ordering can't be an accident of insertion order.
        _seed_chunk("doc-far", 0, "Far", "far chunk", [0.5, 0.0])
        _seed_chunk("doc-near", 0, "Near", "near chunk", [0.1, 0.0])

        hits = await retrieval_module.retrieve("q", top_k=5)

        assert len(hits) == 2
        assert hits[0]["kb_document_id"] == _doc_id("doc-near")
        assert hits[1]["kb_document_id"] == _doc_id("doc-far")
        assert hits[0]["score"] > hits[1]["score"]

    @pytest.mark.asyncio
    async def test_top_k_default_and_explicit_honored(self, env):
        query_vector = [0.0, 0.0]
        env["fake_embed"].vector_for["q"] = query_vector
        for i in range(8):
            _seed_chunk(f"doc-{i}", 0, f"Doc {i}", f"chunk {i}", [0.01 * i, 0.0])

        default_hits = await retrieval_module.retrieve("q")
        assert len(default_hits) == 5  # default top_k

        limited_hits = await retrieval_module.retrieve("q", top_k=2)
        assert len(limited_hits) == 2

        all_hits = await retrieval_module.retrieve("q", top_k=8)
        assert len(all_hits) == 8


class TestHonestEmpty:
    @pytest.mark.asyncio
    async def test_no_hit_above_floor_returns_succeeded_empty(self, env):
        query_vector = [0.0, 0.0]
        env["fake_embed"].vector_for["uncovered topic"] = query_vector
        # distance = 4.0 -> score = 1/5 = 0.2, well below the 0.50 floor.
        _seed_chunk("doc-1", 0, "Unrelated", "totally unrelated content", [2.0, 0.0])

        hits = await retrieval_module.retrieve("uncovered topic", top_k=5)

        assert hits == []  # honest empty, not an exception

    @pytest.mark.asyncio
    async def test_floor_boundary_excludes_just_below_includes_just_above(self, env):
        query_vector = [0.0, 0.0]
        env["fake_embed"].vector_for["boundary query"] = query_vector

        # score = 1/(1+distance) >= 0.50  <=>  distance <= 1.0
        # Just above the floor: distance = 0.96 -> score ≈ 0.5102
        _seed_chunk("doc-above", 0, "Above", "above the floor", [0.96 ** 0.5, 0.0])
        # Just below the floor: distance = 1.04 -> score ≈ 0.4902
        _seed_chunk("doc-below", 0, "Below", "below the floor", [1.04 ** 0.5, 0.0])

        hits = await retrieval_module.retrieve("boundary query", top_k=5)

        ids = {h["kb_document_id"] for h in hits}
        assert _doc_id("doc-above") in ids
        assert _doc_id("doc-below") not in ids
        for h in hits:
            assert h["score"] >= 0.50


class TestRetrievalFailure:
    @pytest.mark.asyncio
    async def test_embedding_failure_raises_retrieval_error(self, env):
        _seed_chunk("doc-1", 0, "Doc", "some chunk", [0.0, 0.0])
        env["fake_embed"].raise_error = ModelRuntimeUnavailableError("Ollama unreachable")

        with pytest.raises(retrieval_module.RetrievalError, match="embedding failed"):
            await retrieval_module.retrieve("any query", top_k=5)

    @pytest.mark.asyncio
    async def test_embedding_model_error_raises_retrieval_error(self, env):
        _seed_chunk("doc-1", 0, "Doc", "some chunk", [0.0, 0.0])
        env["fake_embed"].raise_error = ModelRuntimeError("bad model response")

        with pytest.raises(retrieval_module.RetrievalError):
            await retrieval_module.retrieve("any query", top_k=5)

    @pytest.mark.asyncio
    async def test_empty_uninitialised_collection_raises_retrieval_error(self, env):
        # Never seeded — collection is empty/uninitialised.
        env["fake_embed"].vector_for["anything"] = [0.0, 0.0]

        with pytest.raises(retrieval_module.RetrievalError, match="empty or uninitialised"):
            await retrieval_module.retrieve("anything", top_k=5)

    @pytest.mark.asyncio
    async def test_chroma_query_error_raises_retrieval_error(self, env, monkeypatch):
        _seed_chunk("doc-1", 0, "Doc", "some chunk", [0.0, 0.0])
        env["fake_embed"].vector_for["q"] = [0.0, 0.0]

        collection = ingestion_module.get_kb_collection()

        def broken_query(*args, **kwargs):
            raise RuntimeError("simulated Chroma query failure")

        monkeypatch.setattr(collection, "query", broken_query)
        monkeypatch.setattr(retrieval_module, "get_kb_collection", lambda: collection)

        with pytest.raises(retrieval_module.RetrievalError, match="Chroma query failed"):
            await retrieval_module.retrieve("q", top_k=5)

    @pytest.mark.asyncio
    async def test_empty_result_and_failure_are_distinguishable(self, env):
        """The two 'nothing returned' cases must not be conflatable by a caller."""
        # Case 1: populated collection, no hit above floor -> succeeds, [].
        env["fake_embed"].vector_for["far query"] = [0.0, 0.0]
        _seed_chunk("doc-1", 0, "Doc", "unrelated", [10.0, 0.0])
        hits = await retrieval_module.retrieve("far query", top_k=5)
        assert hits == []

        # Case 2: reset to an empty collection -> raises, does not return [].
        ingestion_module.reset_chroma_client()
        # Re-point at a fresh empty directory to simulate "never ingested".
        import tempfile

        with tempfile.TemporaryDirectory() as fresh_dir:
            import backend.domain.rag.ingestion as ing

            original = ing.chroma_dir
            ing.chroma_dir = lambda: Path(fresh_dir)
            ing.reset_chroma_client()
            try:
                env["fake_embed"].vector_for["far query"] = [0.0, 0.0]
                with pytest.raises(retrieval_module.RetrievalError):
                    await retrieval_module.retrieve("far query", top_k=5)
            finally:
                ing.chroma_dir = original
                ing.reset_chroma_client()


class TestSearchKnowledgeBaseExecutor:
    @pytest.mark.asyncio
    async def test_executor_returns_validated_shape(self, env):
        query_vector = [0.0, 0.0]
        env["fake_embed"].vector_for["pump maintenance"] = query_vector
        _seed_chunk("doc-1", 0, "Pump SOP", "pump maintenance steps", query_vector)

        result = await skb.execute_search_knowledge_base(
            job_id="job-1",
            arguments={"query": "pump maintenance", "top_k": 5},
        )

        assert set(result.keys()) == {"results"}
        assert len(result["results"]) == 1
        item = result["results"][0]
        assert set(item.keys()) == {"kb_document_id", "title", "chunk_text", "score"}
        assert item["title"] == "Pump SOP"

    @pytest.mark.asyncio
    async def test_executor_empty_result_does_not_raise(self, env):
        env["fake_embed"].vector_for["uncovered"] = [0.0, 0.0]
        _seed_chunk("doc-1", 0, "Doc", "unrelated", [10.0, 0.0])

        result = await skb.execute_search_knowledge_base(
            job_id="job-1",
            arguments={"query": "uncovered", "top_k": 5},
        )
        assert result == {"results": []}

    @pytest.mark.asyncio
    async def test_executor_propagates_retrieval_error(self, env):
        # Nothing seeded -> empty/uninitialised collection.
        env["fake_embed"].vector_for["q"] = [0.0, 0.0]

        with pytest.raises(retrieval_module.RetrievalError):
            await skb.execute_search_knowledge_base(job_id="job-1", arguments={"query": "q"})

    @pytest.mark.asyncio
    async def test_executor_rejects_empty_query(self, env):
        with pytest.raises(skb.CapabilityValidationError):
            await skb.execute_search_knowledge_base(job_id="job-1", arguments={"query": "   "})


class TestStaticGuards:
    """docs/rag.md 'Explicit invocation — restated' / ADR-03: no code path may
    perform retrieval outside an explicit search_knowledge_base invocation."""

    def test_only_search_knowledge_base_capability_imports_retrieval(self):
        backend_root = Path(__file__).resolve().parent.parent
        import_pattern = re.compile(r"domain\.rag\.retrieval|domain\.rag import retrieval|from \.retrieval import|from \. import retrieval")
        allowed_files = {
            "domain/capabilities/search_knowledge_base.py",
            "domain/rag/retrieval.py",
        }
        violations = []

        for py_file in backend_root.rglob("*.py"):
            if any("venv" in part for part in py_file.parts):
                continue
            if "test_" in py_file.name or "__pycache__" in py_file.parts:
                continue
            rel_path = str(py_file.relative_to(backend_root)).replace("\\", "/")
            if rel_path in allowed_files:
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if import_pattern.search(content):
                violations.append(rel_path)

        assert not violations, f"Unexpected retrieval imports outside search_knowledge_base.py: {violations}"

    def test_no_prepend_retrieved_context_code_exists(self):
        backend_root = Path(__file__).resolve().parent.parent
        suspicious_pattern = re.compile(r"prepend.{0,40}(retriev|context)|auto.?retriev", re.IGNORECASE)
        violations = []

        for py_file in backend_root.rglob("*.py"):
            if any("venv" in part for part in py_file.parts):
                continue
            if "test_" in py_file.name or "__pycache__" in py_file.parts:
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if suspicious_pattern.search(content):
                violations.append(str(py_file.relative_to(backend_root)))

        assert not violations, f"Found possible auto-retrieve / prepend-context code: {violations}"
