"""Tests for RAG vector store (U9)."""

import tempfile
import unittest

import numpy as np
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

    chunks1 = [Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1)]
    store.upsert(chunks1, [[0.5, 0.5]])
    assert store.status().total_chunks == 1

    chunks2 = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1),
        Chunk(file_path="b.py", content="y=2", start_line=1, end_line=1),
    ]
    store.upsert(chunks2, [[0.5, 0.5], [0.6, 0.6]])
    assert store.status().total_chunks == 2


def test_store_upsert_mismatch_raises(tmp_path):
    """Upsert with mismatched chunk/embedding counts should raise."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1)]
    with pytest.raises(ValueError, match="mismatch"):
        store.upsert(chunks, [[0.5, 0.5], [0.6, 0.6]])


def test_store_search_with_filter(tmp_path):
    """Search with file_pattern should filter results."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [
        Chunk(file_path="src/a.py", content="x=1", start_line=1, end_line=1),
        Chunk(file_path="tests/b.py", content="y=2", start_line=1, end_line=1),
        Chunk(file_path="src/c.ts", content="z=3", start_line=1, end_line=1),
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
    assert status.last_indexed is None


def test_store_status_after_upsert(tmp_path):
    """Status should reflect actual data after upsert."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1),
        Chunk(file_path="a.py", content="x=2", start_line=2, end_line=2),
        Chunk(file_path="b.py", content="y=1", start_line=1, end_line=1),
    ]
    store.upsert(chunks, [[0.5, 0.5], [0.5, 0.5], [0.6, 0.6]])

    status = store.status()
    assert status.total_chunks == 3
    assert status.total_files == 2
    assert status.last_indexed is not None


def test_store_delete_by_file(tmp_path):
    """delete_by_file should remove all chunks for that file."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1),
        Chunk(file_path="a.py", content="x=2", start_line=2, end_line=2),
        Chunk(file_path="b.py", content="y=1", start_line=1, end_line=1),
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


def test_store_clear_removes_everything(tmp_path):
    """clear should remove all data files."""
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1)]
    store.upsert(chunks, [[0.5, 0.5]])

    store.clear()

    assert not (tmp_path / ".stupidex" / "rag" / "index.db").exists()
    assert not (tmp_path / ".stupidex" / "rag" / "vectors.npy").exists()


class TestUpsertFileVectorRebuild(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = RAGStore(self._tmp.name)
        self.store.init_db()

    def tearDown(self):
        self._tmp.cleanup()

    def _files_row(self, file_path):
        conn = self.store._get_conn()
        try:
            return conn.execute(
                "SELECT hash, chunk_count FROM files WHERE file_path = ?",
                (file_path,),
            ).fetchone()
        finally:
            conn.close()

    def _chunk_file_paths_in_order(self):
        return [c["file_path"] for c in self.store._get_all_chunks()]

    def _vectors(self):
        v = self.store._load_vectors()
        return v if v is not None else []

    def test_upsert_two_files_vectors_in_chunk_id_order(self):
        c1 = Chunk(file_path="f1.py", content="a=1", start_line=1, end_line=1)
        c2 = Chunk(file_path="f2.py", content="b=2", start_line=1, end_line=1)
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]

        self.store.upsert_file("f1.py", [c1], [v1])
        self.store.upsert_file("f2.py", [c2], [v2])

        self.assertEqual(self._chunk_file_paths_in_order(), ["f1.py", "f2.py"])
        vectors = self._vectors()
        self.assertEqual(len(vectors), 2)
        self.assertEqual(list(vectors[0]), v1)
        self.assertEqual(list(vectors[1]), v2)

    def test_upsert_second_file_preserves_first_file_vectors(self):
        c1 = Chunk(file_path="f1.py", content="a=1", start_line=1, end_line=1)
        c2 = Chunk(file_path="f1.py", content="a=2", start_line=2, end_line=2)
        c3 = Chunk(file_path="f2.py", content="b=3", start_line=1, end_line=1)
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        v3 = [0.0, 0.0, 1.0]

        self.store.upsert_file("f1.py", [c1, c2], [v1, v2])
        self.store.upsert_file("f2.py", [c3], [v3])

        vectors = self._vectors()
        self.assertEqual(len(vectors), 3)
        self.assertEqual(list(vectors[0]), v1)
        self.assertEqual(list(vectors[1]), v2)
        self.assertEqual(list(vectors[2]), v3)

    def test_upsert_empty_chunks_creates_stub_files_row(self):
        self.store.upsert_file("f1.py", [], [])

        row = self._files_row("f1.py")
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "")
        self.assertEqual(row[1], 0)
        self.assertEqual(self.store.status().total_chunks, 0)
        self.assertEqual(self._vectors(), [])

    def test_upsert_replace_existing_file_realigns_vectors(self):
        c1 = Chunk(file_path="f1.py", content="a=1", start_line=1, end_line=1)
        c2 = Chunk(file_path="f1.py", content="a=2", start_line=2, end_line=2)
        c3 = Chunk(file_path="f1.py", content="b=9", start_line=1, end_line=1)
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        v3 = [0.5, 0.5, 0.5]

        self.store.upsert_file("f1.py", [c1, c2], [v1, v2])
        self.store.upsert_file("f1.py", [c3], [v3])

        self.assertEqual(self.store.status().total_chunks, 1)
        vectors = self._vectors()
        self.assertEqual(len(vectors), 1)
        self.assertEqual(list(vectors[0]), v3)

    def test_upsert_no_existing_vectors_all_new_embeddings(self):
        self.assertFalse(self.store.vectors_file.exists())

        c1 = Chunk(file_path="f1.py", content="a=1", start_line=1, end_line=1)
        c2 = Chunk(file_path="f1.py", content="a=2", start_line=2, end_line=2)
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]

        self.store.upsert_file("f1.py", [c1, c2], [v1, v2])

        vectors = self._vectors()
        self.assertEqual(len(vectors), 2)
        self.assertEqual(list(vectors[0]), v1)
        self.assertEqual(list(vectors[1]), v2)

    def test_upsert_vector_count_mismatch_uses_all_new_embeddings(self):
        c1 = Chunk(file_path="f1.py", content="a=1", start_line=1, end_line=1)
        c2 = Chunk(file_path="f1.py", content="a=2", start_line=2, end_line=2)
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        self.store.upsert_file("f1.py", [c1, c2], [v1, v2])

        np.save(str(self.store.vectors_file), np.array([v1], dtype=np.float32))

        v3 = [0.5, 0.5, 0.0]
        v4 = [0.0, 0.5, 0.5]
        self.store.upsert_file("f1.py", [c1, c2], [v3, v4])

        vectors = self._vectors()
        self.assertEqual(len(vectors), 2)
        self.assertEqual(list(vectors[0]), v3)
        self.assertEqual(list(vectors[1]), v4)

    def test_upsert_then_delete_then_upsert_realigns(self):
        c1 = Chunk(file_path="f1.py", content="a=1", start_line=1, end_line=1)
        c2 = Chunk(file_path="f1.py", content="b=2", start_line=1, end_line=1)
        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]

        self.store.upsert_file("f1.py", [c1], [v1])
        self.store.delete_by_file("f1.py")
        self.store.upsert_file("f1.py", [c2], [v2])

        self.assertEqual(self.store.status().total_chunks, 1)
        vectors = self._vectors()
        self.assertEqual(len(vectors), 1)
        self.assertEqual(list(vectors[0]), v2)
