"""Tests for RAG vector store (U9)."""

import pytest

from stupidex.rag.chunker import Chunk
from stupidex.rag.store import RAGStore


def test_store_init_creates_directory(tmp_path):
    """Store init_db should create the rag directory."""
    store = RAGStore(str(tmp_path))
    store.init_db()
    assert (tmp_path / ".stupidex" / "rag").exists()


def test_store_init_creates_tables(tmp_path):
    """Store init_db should create all required tables."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    conn = store._get_conn()
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "chunks" in table_names
        assert "files" in table_names
        assert "meta" in table_names
    finally:
        conn.close()


def test_store_upsert_replaces_existing(tmp_path):
    """Upsert should replace existing chunks."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks1 = [Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1, language="python")]
    store.upsert(chunks1, [[0.5, 0.5]])
    assert store.status().total_chunks == 1

    chunks2 = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1, language="python"),
        Chunk(file_path="b.py", content="y=2", start_line=1, end_line=1, language="python"),
    ]
    store.upsert(chunks2, [[0.5, 0.5], [0.6, 0.6]])
    assert store.status().total_chunks == 2


def test_store_upsert_mismatch_raises(tmp_path):
    """Upsert with mismatched chunk/embedding counts should raise."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1, language="python")]
    with pytest.raises(ValueError, match="mismatch"):
        store.upsert(chunks, [[0.5, 0.5], [0.6, 0.6]])


def test_store_search_with_filter(tmp_path):
    """Search with file_pattern should filter results."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [
        Chunk(file_path="src/a.py", content="x=1", start_line=1, end_line=1, language="python"),
        Chunk(file_path="tests/b.py", content="y=2", start_line=1, end_line=1, language="python"),
        Chunk(file_path="src/c.ts", content="z=3", start_line=1, end_line=1, language="typescript"),
    ]
    embeddings = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
    store.upsert(chunks, embeddings)

    results = store.search([1.0, 0.0], top_k=10, file_pattern="src/*")
    assert len(results) == 2
    assert all(r.file_path.startswith("src/") for r in results)


def test_store_status_empty(tmp_path):
    """Status should return zeros for empty store."""
    store = RAGStore(str(tmp_path))
    status = store.status()
    assert status.total_chunks == 0
    assert status.total_files == 0
    assert status.embedding_model == ""
    assert status.last_indexed is None


def test_store_status_after_upsert(tmp_path):
    """Status should reflect actual data after upsert."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1, language="python"),
        Chunk(file_path="a.py", content="x=2", start_line=2, end_line=2, language="python"),
        Chunk(file_path="b.py", content="y=1", start_line=1, end_line=1, language="python"),
    ]
    store.upsert(chunks, [[0.5, 0.5], [0.5, 0.5], [0.6, 0.6]])
    store.save_embedding_model("test-model")

    status = store.status()
    assert status.total_chunks == 3
    assert status.total_files == 2
    assert status.embedding_model == "test-model"
    assert status.last_indexed is not None


def test_store_delete_by_file(tmp_path):
    """delete_by_file should remove all chunks for that file."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1, language="python"),
        Chunk(file_path="a.py", content="x=2", start_line=2, end_line=2, language="python"),
        Chunk(file_path="b.py", content="y=1", start_line=1, end_line=1, language="python"),
    ]
    store.upsert(chunks, [[0.5, 0.5], [0.5, 0.5], [0.6, 0.6]])

    store.delete_by_file("a.py")

    status = store.status()
    assert status.total_chunks == 1
    assert status.total_files == 1

    results = store.search([0.6, 0.6], top_k=10)
    assert all(r.file_path == "b.py" for r in results)
    assert len(results) == 1


def test_store_get_file_hashes_empty(tmp_path):
    """get_file_hashes should return empty dict for new store."""
    store = RAGStore(str(tmp_path))
    store.init_db()
    hashes = store.get_file_hashes()
    assert hashes == {}


def test_store_update_file_hash(tmp_path):
    """update_file_hash should create or update hash entry."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    store.update_file_hash("src/main.py", "abc123")
    hashes = store.get_file_hashes()
    assert hashes["src/main.py"] == "abc123"

    store.update_file_hash("src/main.py", "def456")
    hashes = store.get_file_hashes()
    assert hashes["src/main.py"] == "def456"


def test_store_save_embedding_model(tmp_path):
    """save_embedding_model should persist model name."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    store.save_embedding_model("text-embedding-3-small")
    status = store.status()
    assert status.embedding_model == "text-embedding-3-small"


def test_store_clear_removes_everything(tmp_path):
    """clear should remove all data files."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1, language="python")]
    store.upsert(chunks, [[0.5, 0.5]])

    store.clear()

    assert not (tmp_path / ".stupidex" / "rag" / "index.db").exists()
    assert not (tmp_path / ".stupidex" / "rag" / "vectors.npy").exists()
