"""Tests for RAG chunker (U9)."""

from stupidex.rag.chunker import chunk_file


def test_chunker_single_line():
    """Single line file produces one chunk."""
    chunks = chunk_file("test.py", "x = 1\n")
    assert len(chunks) == 1
    assert chunks[0].content == "x = 1\n"
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 1


def test_chunker_empty_file():
    """Empty file produces no chunks."""
    chunks = chunk_file("test.py", "")
    assert chunks == []


def test_chunker_whitespace_only():
    """Whitespace-only file produces no chunks."""
    chunks = chunk_file("test.py", "   \n\n  ")
    assert chunks == []


def test_chunker_binary_file():
    """Binary file (with null bytes) produces no chunks."""
    chunks = chunk_file("test.py", "def foo():\n\x00\x01\x02")
    assert chunks == []


def test_chunker_large_file_splits():
    """Large file should be split into multiple chunks."""
    code = "def foo():\n    pass\n\n" * 200
    chunks = chunk_file("test.py", code, chunk_size=2000, chunk_overlap=200)
    assert len(chunks) > 1
    assert len(chunks) <= 10


def test_chunker_respects_line_numbers():
    """Chunks should have correct line numbers."""
    lines = [f"line {i}" for i in range(1, 101)]
    content = "\n".join(lines)
    chunks = chunk_file("test.py", content, chunk_size=200, chunk_overlap=50)

    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.start_line >= 1
        assert chunk.end_line >= chunk.start_line
        if i > 0:
            assert chunk.start_line >= chunks[i-1].start_line


def test_chunker_overlap():
    """Chunks should overlap by the specified amount."""
    code = "A\n" * 1000
    chunks = chunk_file("test.py", code, chunk_size=100, chunk_overlap=20)

    if len(chunks) > 1:
        for i in range(len(chunks) - 1):
            overlap_region = chunks[i].content[-20:]
            next_start = chunks[i + 1].content[:20]
            assert overlap_region == next_start, (
                f"Chunk {i} end does not match chunk {i + 1} start: "
                f"{overlap_region!r} != {next_start!r}"
            )


def test_chunker_preserves_content():
    """Chunks should preserve the original content."""
    original = "def hello():\n    return 'world'\n"
    chunks = chunk_file("test.py", original)
    assert chunks[0].content == original


def test_chunker_multiline_function():
    """Multiline function should be chunked correctly."""
    code = """
def complex_function(a, b, c):
    if a > b:
        return a + c
    else:
        return b + c

def another_function():
    pass
"""
    chunks = chunk_file("test.py", code.strip())
    assert len(chunks) >= 1


def test_chunker_markdown_file():
    """Markdown file should be chunked correctly."""
    content = "# Title\n\nSome text\n\n## Section\n\nMore text\n"
    chunks = chunk_file("doc.md", content)
    assert len(chunks) == 1


def test_chunker_json_file():
    """JSON file should be chunked correctly."""
    content = '{"key": "value", "nested": {"a": 1}}\n'
    chunks = chunk_file("config.json", content)
    assert len(chunks) == 1


def test_chunker_very_large_chunks():
    """File smaller than chunk_size should produce single chunk."""
    small_code = "x = 1\n" * 100
    chunks = chunk_file("test.py", small_code, chunk_size=10000, chunk_overlap=200)
    assert len(chunks) == 1


def test_chunker_custom_size():
    """Custom chunk_size should be respected."""
    code = "line\n" * 100
    chunks = chunk_file("test.py", code, chunk_size=50, chunk_overlap=10)
    assert len(chunks) > 1
