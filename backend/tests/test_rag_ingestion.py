"""
Tests for the RAG ingestion pipeline and KB API (Task 12.a).

Covers the ingestion half of the round-trip (docs/testing.md "RAG tests");
retrieval is Task 12.b. Uses a fake embedding backend (fixed-dimension
vectors, no network) and a temp Chroma directory per test.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import scripts.init_db as init_db
from backend.domain.model_runtime.runtime import ModelRuntimeError
from backend.domain.rag import ingestion as ingestion_module
from backend.models.schemas import EmbeddingResult
from backend.repositories import audit_events as audit_events_repo
from backend.repositories import knowledge_base as kb_repo
from backend.repositories.db import get_connection
from main import app


FAKE_EMBEDDING_DIM = 8


class FakeEmbed:
    """Deterministic fake embedding backend — fixed-dimension vectors, no network.

    Matches the ModelRuntime.embed(resource_type, text, *, job_id=None) signature.
    """

    def __init__(self, fail_marker: str | None = None):
        self.fail_marker = fail_marker
        self.calls: list[list[str]] = []

    async def __call__(self, resource_type, text, *, job_id=None):
        assert resource_type == "embedding"
        texts = [text] if isinstance(text, str) else text
        self.calls.append(texts)
        if self.fail_marker and any(self.fail_marker in t for t in texts):
            raise ModelRuntimeError("fake embedding backend: injected failure")
        vectors = [[float(i % 7) / 7.0] * FAKE_EMBEDDING_DIM for i, _ in enumerate(texts)]
        return EmbeddingResult(embeddings=vectors, duration_ms=1, model_identifier="fake-embed")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Temp SQLite DB + temp Chroma dir + fake embedding backend, all isolated per test."""
    db_path = tmp_path / "test.db"
    original_get_db_path = init_db.get_db_path
    init_db.get_db_path = lambda: db_path
    init_db.main()
    init_db.get_db_path = original_get_db_path

    monkeypatch.setattr(kb_repo, "get_connection", lambda: get_connection(db_path))
    monkeypatch.setattr(audit_events_repo, "get_connection", lambda: get_connection(db_path))

    chroma_path = tmp_path / "chroma"
    monkeypatch.setattr(ingestion_module, "chroma_dir", lambda: chroma_path)
    ingestion_module.reset_chroma_client()

    fake_embed = FakeEmbed()
    monkeypatch.setattr(ingestion_module.model_runtime, "embed", fake_embed)

    # Uploaded source files also need a scoped, isolated destination.
    uploads_path = tmp_path / "uploads"
    uploads_path.mkdir(parents=True, exist_ok=True)

    import backend.api.knowledge_base as kb_api

    monkeypatch.setattr(kb_api, "UPLOADS_ROOT", uploads_path)
    monkeypatch.setattr(kb_api, "uploads_path", lambda doc_id, ext: uploads_path / f"{doc_id}{ext}")

    yield {"db_path": db_path, "chroma_path": chroma_path, "fake_embed": fake_embed}

    ingestion_module.reset_chroma_client()


@pytest.fixture
def client(env):
    return TestClient(app)


def _wait_for_status(kb_document_id: str, expected: set[str], timeout: float = 5.0) -> dict:
    """FastAPI's TestClient runs BackgroundTasks synchronously within the request,
    so this should already be satisfied on the first check — poll briefly as a
    safety margin rather than assuming a specific ASGI implementation detail."""
    deadline = time.monotonic() + timeout
    doc = None
    while time.monotonic() < deadline:
        doc = kb_repo.get_kb_document(kb_document_id)
        if doc and doc["status"] in expected:
            return doc
        time.sleep(0.05)
    return doc


SOP_MARKDOWN = (
    "# Sample SOP\n\n"
    + ("This is a synthetic standard operating procedure paragraph. " * 40 + "\n\n") * 3
)


def _post_document(client, filename="sop.md", content=SOP_MARKDOWN, content_type="text/markdown", metadata=None):
    files = {"file": (filename, content.encode("utf-8"), content_type)}
    data = {}
    if metadata is not None:
        data["metadata"] = json.dumps(metadata)
    return client.post("/api/v1/knowledge-base/documents", files=files, data=data)


class TestIngestionAcceptedAndLifecycle:
    def test_post_returns_202_and_ingesting_row(self, client, env):
        resp = _post_document(client, metadata={"title": "Sample SOP", "category": "maintenance"})
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "ingesting"
        assert body["kb_document_id"]

        doc = kb_repo.get_kb_document(body["kb_document_id"])
        assert doc is not None

    def test_ingestion_completes_to_ready(self, client, env):
        resp = _post_document(client, metadata={"title": "Sample SOP", "category": "maintenance"})
        kb_document_id = resp.json()["kb_document_id"]

        doc = _wait_for_status(kb_document_id, {"ready", "failed"})
        assert doc["status"] == "ready"
        assert doc["chunk_count"] > 0
        assert doc["ingested_at"] is not None
        assert doc["title"] == "Sample SOP"
        assert doc["category"] == "maintenance"


class TestChromaIndexing:
    def test_chunks_indexed_with_metadata(self, client, env):
        resp = _post_document(client, metadata={"title": "Sample SOP", "category": "maintenance"})
        kb_document_id = resp.json()["kb_document_id"]
        doc = _wait_for_status(kb_document_id, {"ready", "failed"})
        assert doc["status"] == "ready"

        collection = ingestion_module.get_kb_collection()
        result = collection.get(where={"kb_document_id": kb_document_id})
        assert len(result["ids"]) == doc["chunk_count"]

        for metadata, text in zip(result["metadatas"], result["documents"]):
            assert metadata["kb_document_id"] == kb_document_id
            assert metadata["title"] == "Sample SOP"
            assert metadata["category"] == "maintenance"
            assert isinstance(metadata["chunk_index"], int)
            assert text  # chunk text present

        indices = sorted(m["chunk_index"] for m in result["metadatas"])
        assert indices == list(range(doc["chunk_count"]))

    def test_chunk_sizing_approximate_target_and_deterministic(self):
        text = "x" * 5000
        chunks = ingestion_module.chunk_text(text)
        # ~2000-char target for all but the last chunk.
        for chunk in chunks[:-1]:
            assert 1800 <= len(chunk) <= 2000
        assert len(chunks) >= 2

        # Deterministic: identical input -> identical chunk boundaries.
        chunks_again = ingestion_module.chunk_text(text)
        assert chunks == chunks_again

    def test_reingesting_same_file_has_identical_chunk_boundaries(self, client, env):
        resp1 = _post_document(client, metadata={"title": "Sample SOP"})
        id1 = resp1.json()["kb_document_id"]
        doc1 = _wait_for_status(id1, {"ready", "failed"})
        assert doc1["status"] == "ready"

        resp2 = _post_document(client, metadata={"title": "Sample SOP"})
        id2 = resp2.json()["kb_document_id"]
        doc2 = _wait_for_status(id2, {"ready", "failed"})
        assert doc2["status"] == "ready"

        assert id1 != id2  # distinct documents (no dedup — accepted gap)
        assert doc1["chunk_count"] == doc2["chunk_count"]

        collection = ingestion_module.get_kb_collection()
        chunks1 = collection.get(where={"kb_document_id": id1})
        chunks2 = collection.get(where={"kb_document_id": id2})
        texts1 = [d for _, d in sorted(zip(chunks1["metadatas"], chunks1["documents"]), key=lambda p: p[0]["chunk_index"])]
        texts2 = [d for _, d in sorted(zip(chunks2["metadatas"], chunks2["documents"]), key=lambda p: p[0]["chunk_index"])]
        assert texts1 == texts2


class TestListAndDelete:
    def test_list_shows_ready_and_chunk_count(self, client, env):
        resp = _post_document(client, metadata={"title": "Sample SOP"})
        kb_document_id = resp.json()["kb_document_id"]
        doc = _wait_for_status(kb_document_id, {"ready", "failed"})
        assert doc["status"] == "ready"

        list_resp = client.get("/api/v1/knowledge-base")
        assert list_resp.status_code == 200
        documents = list_resp.json()["documents"]
        entry = next(d for d in documents if d["kb_document_id"] == kb_document_id)
        assert entry["status"] == "ready"
        assert entry["chunk_count"] == doc["chunk_count"]
        assert entry["title"] == "Sample SOP"

    def test_delete_removes_row_and_chunks_leaves_others(self, client, env):
        resp1 = _post_document(client, metadata={"title": "Doc One"})
        id1 = resp1.json()["kb_document_id"]
        _wait_for_status(id1, {"ready", "failed"})

        resp2 = _post_document(client, metadata={"title": "Doc Two"})
        id2 = resp2.json()["kb_document_id"]
        doc2 = _wait_for_status(id2, {"ready", "failed"})
        assert doc2["status"] == "ready"

        del_resp = client.delete(f"/api/v1/knowledge-base/documents/{id1}")
        assert del_resp.status_code == 200

        assert kb_repo.get_kb_document(id1) is None
        collection = ingestion_module.get_kb_collection()
        assert collection.get(where={"kb_document_id": id1})["ids"] == []

        # Second document untouched.
        assert kb_repo.get_kb_document(id2) is not None
        remaining = collection.get(where={"kb_document_id": id2})
        assert len(remaining["ids"]) == doc2["chunk_count"]

    def test_delete_unknown_id_returns_404(self, client, env):
        resp = client.delete("/api/v1/knowledge-base/documents/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestFailureHandling:
    def test_unparseable_file_marks_failed_no_chunks(self, client, env):
        # Invalid UTF-8 bytes with a .txt extension: passes the MIME gate,
        # fails at parse time.
        invalid_bytes = b"\xff\xfe\x00not valid utf-8 at all\xff"
        files = {"file": ("bad.txt", invalid_bytes, "text/plain")}
        resp = client.post("/api/v1/knowledge-base/documents", files=files, data={})
        assert resp.status_code == 202
        kb_document_id = resp.json()["kb_document_id"]

        doc = _wait_for_status(kb_document_id, {"ready", "failed"})
        assert doc["status"] == "failed"
        assert doc["chunk_count"] == 0

        collection = ingestion_module.get_kb_collection()
        assert collection.get(where={"kb_document_id": kb_document_id})["ids"] == []

    def test_embedding_failure_mid_run_marks_failed_no_partial_chunks(self, client, env):
        env["fake_embed"].fail_marker = "synthetic standard operating procedure"

        resp = _post_document(client, metadata={"title": "Will Fail"})
        kb_document_id = resp.json()["kb_document_id"]

        doc = _wait_for_status(kb_document_id, {"ready", "failed"})
        assert doc["status"] == "failed"

        collection = ingestion_module.get_kb_collection()
        assert collection.get(where={"kb_document_id": kb_document_id})["ids"] == []

    def test_reingesting_same_source_creates_second_document(self, client, env):
        resp1 = _post_document(client, metadata={"title": "Dup"})
        id1 = resp1.json()["kb_document_id"]
        _wait_for_status(id1, {"ready", "failed"})

        resp2 = _post_document(client, metadata={"title": "Dup"})
        id2 = resp2.json()["kb_document_id"]
        _wait_for_status(id2, {"ready", "failed"})

        assert id1 != id2
        all_docs = kb_repo.list_kb_documents()
        ids = {d["kb_document_id"] for d in all_docs}
        assert {id1, id2}.issubset(ids)
