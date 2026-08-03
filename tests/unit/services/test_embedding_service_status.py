"""Regression tests for EmbeddingService status ChromaDB scan behavior.

Audit finding: get_embedding_status() scanned the entire chunk collection's
metadata twice per call (once inside ChunkVectorStore.get_stats, once to
rebuild the same distinct-paper set), and validate_sync() did a third scan.
Chunk IDs encode the paper ID ("{paper_id}_{chunk_index}"), so a single
IDs-only fetch suffices. These tests use fake stores that count collection
accesses and assert no metadata scans occur.
"""
import pytest

import embeddings.vectorstore as vectorstore_module
import services.embedding_service as embedding_service_module
from services.embedding_service import EmbeddingService
from literature_core import Paper, PaperChunk


class FakeCollection:
    """Minimal ChromaDB collection stub that records get() calls."""

    def __init__(self, ids):
        self._ids = list(ids)
        self.get_calls: list[list] = []

    def get(self, include=None, **kwargs):
        self.get_calls.append(list(include or []))
        result = {"ids": list(self._ids)}
        if include and "metadatas" in include:
            result["metadatas"] = [
                {"paper_id": int(str(i).rsplit("_", 1)[0]), "chunk_index": 0}
                for i in self._ids
            ]
        return result

    def count(self):
        return len(self._ids)


class FakePaperStore:
    def __init__(self, ids):
        self.collection = FakeCollection(ids)

    def get_stats(self):
        return {"count": self.collection.count()}


class FakeChunkStore:
    """Mimics ChunkVectorStore, whose get_stats does a full metadata scan."""

    def __init__(self, ids):
        self.collection = FakeCollection(ids)

    def get_stats(self):
        results = self.collection.get(include=["metadatas"])
        paper_ids = {m["paper_id"] for m in results["metadatas"] or []}
        return {"total_chunks": self.collection.count(), "papers_indexed": len(paper_ids)}


@pytest.fixture
def status_env(db, monkeypatch):
    """Test DB with three papers (two chunk-embedded) and fake vector stores."""
    monkeypatch.setattr(embedding_service_module, "get_session", db.get_session)

    with db.get_session() as session:
        p1 = Paper(title="Paper one", abstract="abstract one")
        p2 = Paper(title="Paper two", abstract="abstract two")
        p3 = Paper(title="Paper three", abstract="abstract three")
        session.add_all([p1, p2, p3])
        session.flush()
        ids = (p1.id, p2.id, p3.id)
        session.add_all([
            PaperChunk(paper_id=p1.id, chunk_order=0, content="chunk text 1"),
            PaperChunk(paper_id=p2.id, chunk_order=0, content="chunk text 2"),
            PaperChunk(paper_id=p3.id, chunk_order=0, content="chunk text 3"),
        ])

    p1_id, p2_id, p3_id = ids
    # Paper-level embeddings exist for p1 only; chunk embeddings for p1, p2
    paper_store = FakePaperStore([str(p1_id)])
    chunk_store = FakeChunkStore([f"{p1_id}_0", f"{p1_id}_1", f"{p2_id}_0"])

    monkeypatch.setattr(vectorstore_module, "get_vector_store", lambda: paper_store)
    monkeypatch.setattr(vectorstore_module, "get_chunk_store", lambda: chunk_store)

    return {
        "paper_ids": ids,
        "paper_store": paper_store,
        "chunk_store": chunk_store,
    }


class TestGetEmbeddingStatusScans:
    def test_no_chunk_metadata_scans(self, status_env):
        chunk_collection = status_env["chunk_store"].collection

        EmbeddingService.get_embedding_status(include_ids=True)

        metadata_scans = [c for c in chunk_collection.get_calls if "metadatas" in c]
        assert metadata_scans == [], (
            f"Status must not scan chunk metadata; saw {len(metadata_scans)} metadata scans"
        )
        assert len(chunk_collection.get_calls) <= 1, (
            f"Chunk collection scanned {len(chunk_collection.get_calls)} times, expected one IDs-only fetch"
        )

    def test_status_counts_correct(self, status_env):
        p1_id, p2_id, p3_id = status_env["paper_ids"]

        status = EmbeddingService.get_embedding_status(include_ids=True)

        assert status.total_papers == 3
        assert status.chunk_embeddings_count == 3
        assert status.papers_with_chunks == 2
        assert status.papers_needing_chunk_embedding == 1
        assert status.paper_ids_needing_chunk_embedding == [p3_id]
        # Paper-level: p1 embedded, p2/p3 have abstracts but no embedding
        assert status.paper_embeddings_count == 1
        assert status.papers_needing_paper_embedding == 2
        assert sorted(status.paper_ids_needing_paper_embedding) == [p2_id, p3_id]


class TestValidateSyncScans:
    def test_orphan_detection_without_metadata_scan(self, db, monkeypatch):
        monkeypatch.setattr(embedding_service_module, "get_session", db.get_session)

        with db.get_session() as session:
            paper = Paper(title="Kept paper", abstract="abstract")
            session.add(paper)
            session.flush()
            kept_id = paper.id

        paper_store = FakePaperStore([str(kept_id)])
        # Chunk embeddings exist for the kept paper and for a deleted paper
        chunk_store = FakeChunkStore([f"{kept_id}_0", "99999_0", "99999_1"])
        monkeypatch.setattr(vectorstore_module, "get_vector_store", lambda: paper_store)
        monkeypatch.setattr(vectorstore_module, "get_chunk_store", lambda: chunk_store)

        issues = EmbeddingService.validate_sync()

        assert issues["orphaned_chunks"] == [99999]
        metadata_scans = [
            c for c in chunk_store.collection.get_calls if "metadatas" in c
        ]
        assert metadata_scans == [], "validate_sync must not scan chunk metadata"
