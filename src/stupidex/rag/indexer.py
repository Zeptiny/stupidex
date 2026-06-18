"""RAG Pipeline: file discovery -> chunking -> embedding -> vector store."""

import asyncio
import hashlib
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from stupidex.config import get_config

from .chunker import Chunk, chunk_file
from .embedder import Embedder
from .store import RAGStore

logger = logging.getLogger(__name__)

INCLUDE_EXTS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".txt",
    ".yaml", ".yml", ".toml", ".json", ".sql", ".sh",
    ".rs", ".go", ".java", ".c", ".cpp", ".h", ".hpp",
    ".css", ".html", ".rb", ".php", ".swift", ".kt",
})

SKIP_EXTS = frozenset({".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe"})


@dataclass
class IndexResult:
    files_scanned: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    files_deleted: int = 0
    chunks_created: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class IndexStatus:
    total_files: int = 0
    total_chunks: int = 0
    last_indexed: str | None = None


async def index_project(
    project_path: str | None = None,
    paths: list[str] | None = None,
    force: bool = False,
    embedder: Embedder | None = None,
    progress_callback: Callable | None = None,
) -> IndexResult:
    """Run the full RAG indexing pipeline.

    Args:
        project_path: Root directory of the project. Uses cwd if None.
        paths: Specific files/dirs to index. None = entire project.
        force: If True, re-index everything regardless of hash.
        embedder: Embedder instance. Creates one with defaults if None.
        progress_callback: Optional ``(file_path, done, total) -> None``.

    Returns:
        IndexResult with stats about the run.
    """
    cfg = get_config()
    if project_path is None:
        project_path = str(Path.cwd())

    t0 = asyncio.get_event_loop().time()

    # --- discovery (I/O-heavy -> thread) ---
    loop = asyncio.get_event_loop()
    files = await loop.run_in_executor(
        None, _discover_files, Path(project_path), paths, cfg.ignored_dirs
    )
    stats = IndexResult(files_scanned=len(files))

    if not files:
        store = RAGStore(project_path)
        store.init_db()
        await loop.run_in_executor(None, _flush_store, store, [], [])
        if embedder is None:
            embedder = Embedder(model=cfg.rag_embedding_model or None)
        stats.duration_seconds = asyncio.get_event_loop().time() - t0
        return stats

    store = RAGStore(project_path)
    store.init_db()

    if embedder is None:
        embedder = Embedder(model=cfg.rag_embedding_model or None)

    existing_hashes: dict[str, str] = {}
    if not force:
        existing_hashes = await loop.run_in_executor(
            None, store.get_file_hashes
        )

    indexed_files: set[str] = set()
    all_chunks: list[Chunk] = []
    all_embeddings: list[list[float]] = []
    file_hashes: dict[str, str] = {}

    for i, filepath in enumerate(files):
        try:
            rel = str(filepath.relative_to(project_path))
        except ValueError:
            logger.warning("Skipping path outside project: %s", filepath)
            continue

        if progress_callback:
            try:
                progress_callback(rel, i, len(files))
            except Exception:
                pass

        try:
            # read + hash in executor
            content, file_hash = await loop.run_in_executor(
                None, _read_and_hash, filepath
            )

            if content is None:
                logger.debug("Skipping %s (binary, empty, or too large)", rel)
                if not force and existing_hashes.get(rel):
                    await loop.run_in_executor(None, store.delete_by_file, rel)
                continue

            # skip unchanged
            if not force and existing_hashes.get(rel) == file_hash:
                stats.files_skipped += 1
                indexed_files.add(rel)
                continue

            # chunk
            chunks = chunk_file(rel, content, cfg.rag_chunk_size, cfg.rag_chunk_overlap)
            if not chunks:
                if not force and existing_hashes.get(rel):
                    await loop.run_in_executor(None, store.delete_by_file, rel)
                indexed_files.add(rel)
                continue

            # embed
            texts = [c.content for c in chunks]
            embeddings = await embedder.embed(texts)

            all_chunks.extend(chunks)
            all_embeddings.extend(embeddings)
            stats.files_indexed += 1
            stats.chunks_created += len(chunks)
            indexed_files.add(rel)
            if file_hash:
                file_hashes[rel] = file_hash

        except Exception as e:
            msg = f"{rel}: {e}"
            logger.warning("Indexing error: %s", msg)
            stats.errors.append(msg)

    # flush everything to store at once (always, so last_indexed is set)
    await loop.run_in_executor(None, _flush_store, store, all_chunks, all_embeddings)

    # update per-file hashes using captured hashes from initial read
    for rel, h in file_hashes.items():
        if rel in indexed_files:
            try:
                await loop.run_in_executor(
                    None, store.update_file_hash, rel, h
                )
            except Exception:
                pass

    # restore hashes for skipped (unchanged) files that were cleared by upsert
    for rel in indexed_files:
        if rel not in file_hashes and rel in existing_hashes:
            try:
                await loop.run_in_executor(
                    None, store.update_file_hash, rel, existing_hashes[rel]
                )
            except Exception:
                pass

    # remove files deleted since last index
    if not force and existing_hashes:
        current_rels: set[str] = set()
        for f in files:
            try:
                current_rels.add(str(f.relative_to(project_path)))
            except ValueError:
                pass
        for stored_path in existing_hashes:
            if stored_path not in current_rels:
                await loop.run_in_executor(
                    None, store.delete_by_file, stored_path
                )
                stats.files_deleted += 1

    stats.duration_seconds = asyncio.get_event_loop().time() - t0
    logger.info(
        "Index complete: %d indexed, %d skipped, %d deleted, %d chunks in %.1fs",
        stats.files_indexed,
        stats.files_skipped,
        stats.files_deleted,
        stats.chunks_created,
        stats.duration_seconds,
    )
    return stats


def get_status(project_path: str | None = None) -> IndexStatus:
    """Return current index status without running a new index."""
    if project_path is None:
        project_path = str(Path.cwd())
    store = RAGStore(project_path)
    s = store.status()
    return IndexStatus(
        total_files=s.total_files,
        total_chunks=s.total_chunks,
        last_indexed=s.last_indexed,
    )


def clear_index(project_path: str | None = None) -> None:
    """Delete the RAG index for a project."""
    if project_path is None:
        project_path = str(Path.cwd())
    store = RAGStore(project_path)
    store.clear()


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _discover_files(
    root: Path,
    paths: list[str] | None,
    ignored_dirs: list[str],
) -> list[Path]:
    skip = set(ignored_dirs) | {
        "node_modules", ".git", "__pycache__",
        ".venv", "venv", "env",
        ".stupidex", "dist", "build",
        ".next", ".cache", "target",
    }

    if paths:
        result: list[Path] = []
        for p_str in paths:
            p = Path(p_str)
            if not p.is_absolute():
                p = root / p
            if p.is_file() and _should_include(p):
                result.append(p)
            elif p.is_dir():
                result.extend(_walk(p, skip))
        return sorted(set(result))

    return sorted(_walk(root, skip))


def _walk(directory: Path, skip: set[str]) -> list[Path]:
    files: list[Path] = []
    try:
        entries = list(os.scandir(directory))
    except PermissionError:
        return files

    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            if entry.name not in skip:
                files.extend(_walk(Path(entry.path), skip))
        elif entry.is_file(follow_symlinks=False):
            p = Path(entry.path)
            if _should_include(p):
                files.append(p)
    return files


def _should_include(filepath: Path) -> bool:
    ext = filepath.suffix.lower()
    if ext in SKIP_EXTS:
        return False
    return ext in INCLUDE_EXTS


def _read_and_hash(filepath: Path) -> tuple[str | None, str | None]:
    """Read file content and compute MD5 hash. Returns (content, hash)."""
    cfg = get_config()
    try:
        size = filepath.stat().st_size
        if size > cfg.rag_max_file_size:
            logger.debug("Skipping %s (%d bytes > limit)", filepath, size)
            return None, None
        if size == 0:
            return None, None

        content = filepath.read_text(encoding="utf-8", errors="replace")
        if "\0" in content:
            return None, None

        h = hashlib.md5(content.encode("utf-8")).hexdigest()
        return content, h
    except Exception:
        return None, None


def _flush_store(
    store: RAGStore,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> None:
    """Batch-upsert all chunks + embeddings into the store."""
    store.upsert(chunks, embeddings)
