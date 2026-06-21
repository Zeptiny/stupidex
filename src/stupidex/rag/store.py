import logging
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from stupidex.config import PROJECT_RAG_DIR, RAG_INDEX_DB, RAG_VECTORS_FILE, get_config
from stupidex.rag.chunker import Chunk

logger = logging.getLogger(__name__)

_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    file_path TEXT PRIMARY KEY,
    hash TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class SearchResult:
    file_path: str
    content: str
    start_line: int
    end_line: int
    score: float


@dataclass
class StoreStatus:
    total_chunks: int
    total_files: int
    last_indexed: str | None
    last_index_duration: float | None


@dataclass
class VectorState:
    """In-memory snapshot of the vectors table aligned with chunk_ids.

    Used by the batch upsert/delete/flush path to avoid reloading and
    rewriting vectors.npy once per file.
    """

    chunk_ids: list[int]
    vectors: list[list[float]]
    id_to_index: dict[int, int]


class RAGStore:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.rag_dir = Path(project_path) / PROJECT_RAG_DIR
        self.vectors_file = self.rag_dir / RAG_VECTORS_FILE
        self.db_path = self.rag_dir / RAG_INDEX_DB

    def _ensure_dir(self) -> None:
        self.rag_dir.mkdir(parents=True, exist_ok=True)

    def init_db(self) -> None:
        self._ensure_dir()
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(_DB_SCHEMA)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Corrupted index.db, rebuilding: %s", e)
            if self.db_path.exists():
                self.db_path.unlink()
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(_DB_SCHEMA)
            conn.commit()
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        self._ensure_dir()
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("SELECT 1 FROM chunks LIMIT 1")
            return conn
        except Exception as e:
            logger.error("Corrupted index.db, rebuilding: %s", e)
            if conn is not None:
                conn.close()
            if self.db_path.exists():
                self.db_path.unlink()
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(_DB_SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")
            return conn

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunks ({len(chunks)}) and embeddings ({len(embeddings)}) count mismatch"
            )

        self._ensure_dir()
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM files")

            if chunks:
                chunk_data = [
                    (c.file_path, c.start_line, c.end_line, c.content)
                    for c in chunks
                ]
                conn.executemany(
                    "INSERT INTO chunks (file_path, start_line, end_line, content) "
                    "VALUES (?, ?, ?, ?)",
                    chunk_data,
                )

            file_chunks: dict[str, int] = {}
            for c in chunks:
                file_chunks[c.file_path] = file_chunks.get(c.file_path, 0) + 1

            for fp, count in file_chunks.items():
                conn.execute(
                    "INSERT OR REPLACE INTO files (file_path, hash, chunk_count) VALUES (?, '', ?)",
                    (fp, count),
                )

            now = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_indexed', ?)",
                (now,),
            )

            conn.commit()
        finally:
            conn.close()

        self._save_vectors(embeddings)

    def _save_vectors(self, embeddings: list[list[float]]) -> None:
        self._ensure_dir()
        if not embeddings:
            if self.vectors_file.exists():
                self.vectors_file.unlink()
            return
        arr = np.array(embeddings, dtype=np.float32)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self.rag_dir), suffix=".tmp"
        )
        os.close(tmp_fd)
        try:
            np.save(tmp_path, arr, allow_pickle=False)
            actual = tmp_path + ".npy"
            os.replace(actual, str(self.vectors_file))
        except BaseException:
            for p in (tmp_path, tmp_path + ".npy"):
                try:
                    os.unlink(p)
                except OSError:
                    pass
            raise
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _load_vectors(self) -> list[list[float]] | None:
        npy_path = self.vectors_file

        if npy_path.exists():
            try:
                arr = np.load(str(npy_path), allow_pickle=False)
                if arr.ndim != 2 or arr.dtype != np.float32:
                    raise ValueError("Invalid vectors array shape or dtype")
                return arr.tolist()
            except Exception as e:
                logger.error("Corrupted vectors.npy, clearing index: %s", e)
                self.clear()
                return None

        return None

    def _get_all_chunks(self) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT chunk_id, file_path, start_line, end_line, content "
                "FROM chunks ORDER BY chunk_id"
            )
            return [
                {
                    "chunk_id": row[0],
                    "file_path": row[1],
                    "start_line": row[2],
                    "end_line": row[3],
                    "content": row[4],
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def search(
        self,
        query_embedding: list[float],
        top_k: int | None = None,
        file_pattern: str | None = None,
    ) -> list[SearchResult]:
        if top_k is None:
            top_k = get_config().rag.top_k

        vectors = self._load_vectors()
        if not vectors:
            return []

        chunks = self._get_all_chunks()
        if not chunks:
            return []

        if len(vectors) != len(chunks):
            logger.warning(
                "Vector count (%d) != chunk count (%d), index may be stale",
                len(vectors),
                len(chunks),
            )
            min_len = min(len(vectors), len(chunks))
            vectors = vectors[:min_len]
            chunks = chunks[:min_len]

        if vectors and len(query_embedding) != len(vectors[0]):
            raise ValueError(
                f"Query embedding dimension ({len(query_embedding)}) does not match "
                f"stored vector dimension ({len(vectors[0])}). "
                "Re-index with the correct embedding model."
            )

        scores = self._cosine_similarity(query_embedding, vectors)

        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

        results: list[SearchResult] = []
        for idx, score in indexed:
            if len(results) >= top_k:
                break
            chunk = chunks[idx]
            if file_pattern and not _match_pattern(chunk["file_path"], file_pattern):
                continue
            results.append(
                SearchResult(
                    file_path=chunk["file_path"],
                    content=chunk["content"],
                    start_line=chunk["start_line"],
                    end_line=chunk["end_line"],
                    score=float(score),
                )
            )

        return results

    @staticmethod
    def _cosine_similarity(
        query: list[float], vectors: list[list[float]]
    ) -> list[float]:
        q = np.array(query, dtype=np.float32)
        v = np.array(vectors, dtype=np.float32)
        norms = np.linalg.norm(v, axis=1) * np.linalg.norm(q)
        norms = np.where(norms == 0, 1, norms)
        return (v @ q / norms).tolist()

    def clear(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()
        if self.vectors_file.exists():
            self.vectors_file.unlink()

    def status(self) -> StoreStatus:
        if not self.db_path.exists():
            return StoreStatus(
                total_chunks=0,
                total_files=0,
                last_indexed=None,
                last_index_duration=None,
            )

        conn = self._get_conn()
        try:
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            row = conn.execute(
                "SELECT value FROM meta WHERE key='last_indexed'"
            ).fetchone()
            last_indexed = row[0] if row else None
            row2 = conn.execute(
                "SELECT value FROM meta WHERE key='last_index_duration'"
            ).fetchone()
            duration = float(row2[0]) if row2 else None

            return StoreStatus(
                total_chunks=chunk_count,
                total_files=file_count,
                last_indexed=last_indexed,
                last_index_duration=duration,
            )
        finally:
            conn.close()

    def record_index_duration(self, duration: float) -> None:
        """Store the duration of the last full index operation."""
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_index_duration', ?)",
                (str(duration),),
            )
            conn.commit()
        finally:
            conn.close()

    def touch_last_indexed(self) -> None:
        """Mark last_indexed timestamp without modifying chunks/vectors."""
        conn = self._get_conn()
        try:
            now = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_indexed', ?)",
                (now,),
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_file(
        self,
        file_path: str,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        """Replace all chunks and embeddings for a single file.

        Preserves chunks and vectors for all other files.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunks ({len(chunks)}) and embeddings ({len(embeddings)}) count mismatch"
            )

        old_ids = self._get_ordered_chunk_ids()
        old_vectors = self._load_vectors()
        id_to_vec: dict[int, list[float]] = {}
        if old_vectors is not None and len(old_vectors) == len(old_ids):
            id_to_vec = dict(zip(old_ids, old_vectors, strict=False))

        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))
            conn.execute("DELETE FROM files WHERE file_path = ?", (file_path,))

            if chunks:
                chunk_data = [
                    (c.file_path, c.start_line, c.end_line, c.content)
                    for c in chunks
                ]
                conn.executemany(
                    "INSERT INTO chunks (file_path, start_line, end_line, content) "
                    "VALUES (?, ?, ?, ?)",
                    chunk_data,
                )
                conn.execute(
                    "INSERT OR REPLACE INTO files (file_path, hash, chunk_count) VALUES (?, '', ?)",
                    (file_path, len(chunks)),
                )
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO files (file_path, hash, chunk_count) VALUES (?, '', 0)",
                    (file_path,),
                )

            now = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_indexed', ?)",
                (now,),
            )
            conn.commit()
        finally:
            conn.close()

        # Rebuild vectors: keep old vectors for surviving chunks, append new
        # embeddings for this file's new chunks only (scope by _chunk_ids_for_file
        # so a stale vectors.npy can't mis-assign embeddings to other files).
        file_new_id_set = set(self._chunk_ids_for_file(file_path))
        new_ids = self._get_ordered_chunk_ids()
        new_vectors: list[list[float]] = []
        embed_idx = 0
        for cid in new_ids:
            if cid in id_to_vec:
                new_vectors.append(id_to_vec[cid])
            elif cid in file_new_id_set and embed_idx < len(embeddings):
                new_vectors.append(embeddings[embed_idx])
                embed_idx += 1
        # else: chunk for another file with no old vector — skip (stale rebuild).

        self._save_vectors(new_vectors)

    def delete_by_file(self, file_path: str) -> None:
        old_ids = self._get_ordered_chunk_ids()
        vectors = self._load_vectors()

        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))
            conn.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
            conn.commit()
        finally:
            conn.close()

        if vectors is not None and old_ids and len(vectors) == len(old_ids):
            id_to_vec = dict(zip(old_ids, vectors, strict=False))
            new_ids = self._get_ordered_chunk_ids()
            aligned = [id_to_vec[cid] for cid in new_ids if cid in id_to_vec]
            if aligned:
                self._save_vectors(aligned)
            else:
                p = self.vectors_file
                if p.exists():
                    p.unlink()

    def load_vector_state(self) -> VectorState:
        """Load chunk_ids + vectors once, building the position index.

        If the on-disk vectors are missing or out of sync with the chunk
        table, both lists are treated as empty (callers will rebuild the
        full vector set as files are upserted, matching the non-batch
        ``upsert_file``/``delete_by_file`` behavior for a stale index).
        """
        chunk_ids = self._get_ordered_chunk_ids()
        vectors = self._load_vectors()
        if vectors is None or len(vectors) != len(chunk_ids):
            chunk_ids = []
            vectors = []
        id_to_index = {cid: i for i, cid in enumerate(chunk_ids)}
        return VectorState(
            chunk_ids=list(chunk_ids),
            vectors=list(vectors),
            id_to_index=id_to_index,
        )

    def _chunk_ids_for_file(self, file_path: str) -> list[int]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT chunk_id FROM chunks WHERE file_path = ? ORDER BY chunk_id",
                (file_path,),
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def upsert_file_batch(
        self,
        state: VectorState,
        file_path: str,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
        """Batch upsert: mutate ``state`` in place, do NOT touch vectors.npy.

        sqlite is updated (delete + insert for ``file_path``) and the new
        chunk_ids are appended to ``state`` aligned with ``embeddings``.
        Old chunk_ids for ``file_path`` are dropped from ``state``.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunks ({len(chunks)}) and embeddings ({len(embeddings)}) count mismatch"
            )

        old_ids = self._chunk_ids_for_file(file_path)

        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))
            conn.execute("DELETE FROM files WHERE file_path = ?", (file_path,))

            if chunks:
                chunk_data = [
                    (c.file_path, c.start_line, c.end_line, c.content)
                    for c in chunks
                ]
                conn.executemany(
                    "INSERT INTO chunks (file_path, start_line, end_line, content) "
                    "VALUES (?, ?, ?, ?)",
                    chunk_data,
                )
                conn.execute(
                    "INSERT OR REPLACE INTO files (file_path, hash, chunk_count) VALUES (?, '', ?)",
                    (file_path, len(chunks)),
                )
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO files (file_path, hash, chunk_count) VALUES (?, '', 0)",
                    (file_path,),
                )

            now = datetime.now(UTC).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_indexed', ?)",
                (now,),
            )
            conn.commit()

            new_ids = (
                [
                    r[0]
                    for r in conn.execute(
                        "SELECT chunk_id FROM chunks WHERE file_path = ? ORDER BY chunk_id",
                        (file_path,),
                    ).fetchall()
                ]
                if chunks
                else []
            )
        finally:
            conn.close()

        # Drop old vectors for this file from state (only those present).
        drop_indices = sorted(
            (state.id_to_index[cid] for cid in old_ids if cid in state.id_to_index),
            reverse=True,
        )
        for idx in drop_indices:
            state.chunk_ids.pop(idx)
            state.vectors.pop(idx)

        # Append new chunk_ids + embeddings.
        for cid, vec in zip(new_ids, embeddings, strict=True):
            state.chunk_ids.append(cid)
            state.vectors.append(list(vec))

        # Rebuild position index (indices shifted by pops above).
        state.id_to_index = {cid: i for i, cid in enumerate(state.chunk_ids)}

    def delete_by_file_batch(self, state: VectorState, file_path: str) -> None:
        """Batch delete: mutate ``state`` in place, do NOT touch vectors.npy."""
        old_ids = self._chunk_ids_for_file(file_path)

        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))
            conn.execute("DELETE FROM files WHERE file_path = ?", (file_path,))
            conn.commit()
        finally:
            conn.close()

        drop_indices = sorted(
            (state.id_to_index[cid] for cid in old_ids if cid in state.id_to_index),
            reverse=True,
        )
        for idx in drop_indices:
            state.chunk_ids.pop(idx)
            state.vectors.pop(idx)
        state.id_to_index = {cid: i for i, cid in enumerate(state.chunk_ids)}

    def flush_vector_state(self, state: VectorState) -> None:
        """Single write of the accumulated vectors to vectors.npy."""
        self._save_vectors(state.vectors)

    def _get_ordered_chunk_ids(self) -> list[int]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT chunk_id FROM chunks ORDER BY chunk_id"
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def get_file_hashes(self) -> dict[str, str]:
        if not self.db_path.exists():
            return {}

        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT file_path, hash FROM files").fetchall()
            return {row[0]: row[1] for row in rows}
        finally:
            conn.close()

    def update_file_hash(self, file_path: str, file_hash: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO files (file_path, hash, chunk_count) "
                "VALUES (?, ?, COALESCE((SELECT chunk_count FROM files WHERE file_path = ?), 0))",
                (file_path, file_hash, file_path),
            )
            conn.commit()
        finally:
            conn.close()


def _match_pattern(file_path: str, pattern: str) -> bool:
    import fnmatch

    return fnmatch.fnmatch(file_path, pattern)
