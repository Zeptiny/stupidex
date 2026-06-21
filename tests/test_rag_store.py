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


# ---------------------------------------------------------------------------
# Batch vector-state API
# ---------------------------------------------------------------------------


def test_load_vector_state_empty_store(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()

    state = store.load_vector_state()
    assert state.chunk_ids == []
    assert state.vectors == []
    assert state.id_to_index == {}


def test_load_vector_state_after_upsert(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1),
        Chunk(file_path="b.py", content="y=2", start_line=1, end_line=1),
    ]
    store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0]])

    state = store.load_vector_state()
    assert len(state.chunk_ids) == 2
    assert len(state.vectors) == 2
    assert state.id_to_index[state.chunk_ids[0]] == 0
    assert state.id_to_index[state.chunk_ids[1]] == 1
    assert state.vectors[0] == [1.0, 0.0]
    assert state.vectors[1] == [0.0, 1.0]


def test_upsert_file_batch_updates_state_single_file(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()

    state = store.load_vector_state()
    assert state.chunk_ids == []

    chunks = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1),
        Chunk(file_path="a.py", content="x=2", start_line=2, end_line=2),
    ]
    embeddings = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

    store.upsert_file_batch(state, "a.py", chunks, embeddings)

    # state mirrors sqlite
    db_ids = store._get_ordered_chunk_ids()
    assert state.chunk_ids == db_ids
    assert len(state.vectors) == 2
    assert state.vectors[0] == [1.0, 0.0, 0.0]
    assert state.vectors[1] == [0.0, 1.0, 0.0]
    assert state.id_to_index == {cid: i for i, cid in enumerate(db_ids)}
    # vectors.npy not yet written
    assert not store.vectors_file.exists()


def test_upsert_file_batch_replace_existing_in_state(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks_v1 = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1),
        Chunk(file_path="a.py", content="x=2", start_line=2, end_line=2),
    ]
    embeddings_v1 = [[1.0, 0.0], [0.0, 1.0]]
    store.upsert(chunks_v1, embeddings_v1)

    state = store.load_vector_state()
    assert len(state.chunk_ids) == 2

    # Replace a.py with a single new chunk
    chunks_v2 = [Chunk(file_path="a.py", content="new", start_line=1, end_line=1)]
    embeddings_v2 = [[0.5, 0.5]]
    store.upsert_file_batch(state, "a.py", chunks_v2, embeddings_v2)

    db_ids = store._get_ordered_chunk_ids()
    assert state.chunk_ids == db_ids
    assert len(state.vectors) == 1
    assert state.vectors[0] == [0.5, 0.5]
    assert state.id_to_index[db_ids[0]] == 0


def test_upsert_file_batch_second_file_preserves_first(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()

    state = store.load_vector_state()

    c1 = Chunk(file_path="f1.py", content="a=1", start_line=1, end_line=1)
    c2 = Chunk(file_path="f2.py", content="b=2", start_line=1, end_line=1)
    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]

    store.upsert_file_batch(state, "f1.py", [c1], [v1])
    store.upsert_file_batch(state, "f2.py", [c2], [v2])

    assert state.chunk_ids == store._get_ordered_chunk_ids()
    assert len(state.vectors) == 2
    assert state.vectors[0] == v1
    assert state.vectors[1] == v2


def test_upsert_file_batch_mismatch_raises(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()
    state = store.load_vector_state()

    chunks = [Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1)]
    with pytest.raises(ValueError, match="mismatch"):
        store.upsert_file_batch(state, "a.py", chunks, [[0.1], [0.2]])


def test_delete_by_file_batch_updates_state(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1),
        Chunk(file_path="a.py", content="x=2", start_line=2, end_line=2),
        Chunk(file_path="b.py", content="y=1", start_line=1, end_line=1),
    ]
    store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])

    state = store.load_vector_state()
    assert len(state.chunk_ids) == 3

    store.delete_by_file_batch(state, "a.py")

    db_ids = store._get_ordered_chunk_ids()
    assert state.chunk_ids == db_ids
    assert len(state.vectors) == 1
    assert state.vectors[0] == [0.5, 0.5]
    assert state.id_to_index == {db_ids[0]: 0}
    assert store.status().total_chunks == 1


def test_delete_by_file_batch_does_not_save_vectors(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [
        Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1),
        Chunk(file_path="b.py", content="y=1", start_line=1, end_line=1),
    ]
    store.upsert(chunks, [[1.0, 0.0], [0.0, 1.0]])

    state = store.load_vector_state()

    save_calls = 0
    real_save = store._save_vectors

    def counting_save(embeddings):
        nonlocal save_calls
        save_calls += 1
        return real_save(embeddings)

    store._save_vectors = counting_save
    store.delete_by_file_batch(state, "a.py")

    assert save_calls == 0  # batch delete must NOT write vectors.npy


def test_delete_by_file_batch_unknown_file_noop(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()

    chunks = [Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1)]
    store.upsert(chunks, [[1.0, 0.0]])

    state = store.load_vector_state()
    before_ids = list(state.chunk_ids)
    before_vecs = [list(v) for v in state.vectors]

    store.delete_by_file_batch(state, "nonexistent.py")

    assert state.chunk_ids == before_ids
    assert state.vectors == before_vecs


def test_flush_vector_state_writes_once(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()

    state = store.load_vector_state()
    chunks = [Chunk(file_path="a.py", content="x=1", start_line=1, end_line=1)]
    store.upsert_file_batch(state, "a.py", chunks, [[0.7, 0.3]])

    save_calls = 0
    real_save = store._save_vectors

    def counting_save(embeddings):
        nonlocal save_calls
        save_calls += 1
        return real_save(embeddings)

    store._save_vectors = counting_save
    store.flush_vector_state(state)

    assert save_calls == 1
    assert store.vectors_file.exists()
    loaded = store._load_vectors()
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded[0][0] == pytest.approx(0.7, abs=1e-5)
    assert loaded[0][1] == pytest.approx(0.3, abs=1e-5)


def test_search_correct_after_batch_index(tmp_path):
    store = RAGStore(str(tmp_path))
    store.init_db()

    state = store.load_vector_state()
    chunks = [
        Chunk(file_path="src/a.py", content="alpha", start_line=1, end_line=1),
        Chunk(file_path="src/b.py", content="beta", start_line=1, end_line=1),
        Chunk(file_path="tests/c.py", content="gamma", start_line=1, end_line=1),
    ]
    embeddings = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
    store.upsert_file_batch(state, "src/a.py", [chunks[0]], [embeddings[0]])
    store.upsert_file_batch(state, "src/b.py", [chunks[1]], [embeddings[1]])
    store.upsert_file_batch(state, "tests/c.py", [chunks[2]], [embeddings[2]])
    store.flush_vector_state(state)

    results = store.search([1.0, 0.0], top_k=10)
    assert len(results) == 3
    assert results[0].file_path == "src/a.py"

    filtered = store.search([1.0, 0.0], top_k=10, file_pattern="src/*")
    assert len(filtered) == 2
    assert all(r.file_path.startswith("src/") for r in filtered)
