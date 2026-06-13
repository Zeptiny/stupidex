"""Tests for RAG indexing pipeline (U3)."""
from pathlib import Path

import pytest

from stupidex.rag.embedder import Embedder
from stupidex.rag.indexer import (
    _discover_files,
    _should_include,
    clear_index,
    get_status,
    index_project,
)
from stupidex.rag.store import RAGStore


class FakeEmbedder(Embedder):
    """Deterministic fake embedder for tests — no network calls."""

    def __init__(self, dim: int = 8):
        super().__init__(model="fake-model")
        self.dim = dim
        self._call_count = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib as _hl

        self._call_count += 1
        results = []
        for t in texts:
            h = _hl.md5(t.encode()).hexdigest()
            vec = [int(h[i : i + 2], 16) / 255.0 for i in range(0, self.dim * 2, 2)]
            # pad if dim > len(vec)
            while len(vec) < self.dim:
                vec.append(0.0)
            results.append(vec[: self.dim])
        return results


# ---------------------------------------------------------------------------
# _should_include
# ---------------------------------------------------------------------------


def test_should_include_python():
    assert _should_include(Path("foo.py")) is True


def test_should_include_markdown():
    assert _should_include(Path("README.md")) is True


def test_should_exclude_pyc():
    assert _should_include(Path("foo.pyc")) is False


def test_should_exclude_so():
    assert _should_include(Path("lib.so")) is False


def test_should_exclude_unknown():
    assert _should_include(Path("Makefile")) is False


# ---------------------------------------------------------------------------
# _discover_files
# ---------------------------------------------------------------------------


def test_discover_files_skips_git_and_node_modules(tmp_path):
    (tmp_path / "good.py").write_text("x = 1")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git stuff")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("var x")

    files = _discover_files(tmp_path, None, [".git", "node_modules"])
    names = [f.name for f in files]
    assert "good.py" in names
    assert "config" not in names
    assert "pkg.js" not in names


def test_discover_files_specific_paths(tmp_path):
    (tmp_path / "a.py").write_text("a")
    (tmp_path / "b.py").write_text("b")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("c")

    files = _discover_files(tmp_path, [str(sub)], [])
    names = [f.name for f in files]
    assert names == ["c.py"]


def test_discover_files_empty_project(tmp_path):
    files = _discover_files(tmp_path, None, [])
    assert files == []


# ---------------------------------------------------------------------------
# index_project — core pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_initial_processses_all_files(tmp_path):
    (tmp_path / "main.py").write_text("def hello():\n    return 'hi'")
    (tmp_path / "utils.py").write_text("def add(a, b):\n    return a + b")

    embedder = FakeEmbedder()
    result = await index_project(
        project_path=str(tmp_path),
        embedder=embedder,
    )

    assert result.files_scanned == 2
    assert result.files_indexed == 2
    assert result.files_skipped == 0
    assert result.errors == []
    assert result.duration_seconds >= 0

    # verify store has data
    store = RAGStore(str(tmp_path))
    status = store.status()
    assert status.total_files == 2
    assert status.total_chunks >= 2


@pytest.mark.asyncio
async def test_index_skips_unchanged_files(tmp_path):
    (tmp_path / "app.py").write_text("x = 1")

    embedder = FakeEmbedder()

    r1 = await index_project(project_path=str(tmp_path), embedder=embedder)
    assert r1.files_indexed == 1

    # second run — same content
    r2 = await index_project(project_path=str(tmp_path), embedder=embedder)
    assert r2.files_skipped == 1
    assert r2.files_indexed == 0


@pytest.mark.asyncio
async def test_index_detects_modified_files(tmp_path):
    (tmp_path / "app.py").write_text("x = 1")

    embedder = FakeEmbedder()

    await index_project(project_path=str(tmp_path), embedder=embedder)

    # modify the file
    (tmp_path / "app.py").write_text("x = 2\ny = 3")

    r = await index_project(project_path=str(tmp_path), embedder=embedder)
    assert r.files_indexed == 1
    assert r.files_skipped == 0


@pytest.mark.asyncio
async def test_index_force_reindexes_everything(tmp_path):
    (tmp_path / "a.py").write_text("x = 1")

    embedder = FakeEmbedder()

    await index_project(project_path=str(tmp_path), embedder=embedder)

    r = await index_project(project_path=str(tmp_path), embedder=embedder, force=True)
    assert r.files_indexed == 1
    assert r.files_skipped == 0


@pytest.mark.asyncio
async def test_index_removes_deleted_files(tmp_path):
    (tmp_path / "keep.py").write_text("a = 1")
    (tmp_path / "remove.py").write_text("b = 2")

    embedder = FakeEmbedder()
    await index_project(project_path=str(tmp_path), embedder=embedder)

    # delete one file
    (tmp_path / "remove.py").unlink()

    r = await index_project(project_path=str(tmp_path), embedder=embedder)
    assert r.files_deleted == 1

    store = RAGStore(str(tmp_path))
    hashes = store.get_file_hashes()
    assert "keep.py" in hashes
    assert "remove.py" not in hashes


@pytest.mark.asyncio
async def test_index_skips_binary_and_large_files(tmp_path):
    (tmp_path / "binary.py").write_text("\x00\x01\x02")
    (tmp_path / "normal.py").write_text("print('hello')")

    embedder = FakeEmbedder()
    r = await index_project(project_path=str(tmp_path), embedder=embedder)

    assert r.files_indexed == 1
    assert r.files_scanned == 2


@pytest.mark.asyncio
async def test_index_skips_stupidex_dir(tmp_path):
    rag_dir = tmp_path / ".stupidex" / "rag"
    rag_dir.mkdir(parents=True)
    (rag_dir / "old.py").write_text("stale")
    (tmp_path / "real.py").write_text("fresh")

    embedder = FakeEmbedder()
    r = await index_project(project_path=str(tmp_path), embedder=embedder)

    assert r.files_indexed == 1
    names = [Path(e.split(":")[0]).name for e in r.errors] if r.errors else []
    assert all("old.py" not in n for n in names)


@pytest.mark.asyncio
async def test_index_empty_project(tmp_path):
    embedder = FakeEmbedder()
    r = await index_project(project_path=str(tmp_path), embedder=embedder)
    assert r.files_scanned == 0
    assert r.files_indexed == 0
    assert r.errors == []


@pytest.mark.asyncio
async def test_index_captures_errors(tmp_path):
    """Indexing a file that exists but can't be chunked should not crash."""
    (tmp_path / "empty.py").write_text("")

    embedder = FakeEmbedder()
    r = await index_project(project_path=str(tmp_path), embedder=embedder)
    # empty file produces 0 chunks — not an error, just skipped
    assert r.errors == []


@pytest.mark.asyncio
async def test_index_progress_callback(tmp_path):
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "b.py").write_text("y = 2")

    calls: list[tuple] = []

    def cb(path, done, total):
        calls.append((path, done, total))

    embedder = FakeEmbedder()
    await index_project(project_path=str(tmp_path), embedder=embedder, progress_callback=cb)

    assert len(calls) == 2
    assert all(isinstance(c[0], str) for c in calls)
    assert calls[-1][2] == 2  # total


# ---------------------------------------------------------------------------
# get_status / clear_index
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_status_empty(tmp_path):
    s = get_status(project_path=str(tmp_path))
    assert s.total_files == 0
    assert s.total_chunks == 0
    assert s.last_indexed is None


@pytest.mark.asyncio
async def test_get_status_after_index(tmp_path):
    (tmp_path / "x.py").write_text("val = 42")

    embedder = FakeEmbedder()
    await index_project(project_path=str(tmp_path), embedder=embedder)

    s = get_status(project_path=str(tmp_path))
    assert s.total_files >= 1
    assert s.total_chunks >= 1
    assert s.last_indexed is not None


@pytest.mark.asyncio
async def test_clear_index(tmp_path):
    (tmp_path / "x.py").write_text("val = 42")
    embedder = FakeEmbedder()
    await index_project(project_path=str(tmp_path), embedder=embedder)

    clear_index(project_path=str(tmp_path))

    s = get_status(project_path=str(tmp_path))
    assert s.total_files == 0
    assert s.total_chunks == 0
