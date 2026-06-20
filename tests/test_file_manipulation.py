import pytest

from stupidex.tools.file_manipulation import execute_edit_tool, execute_write_tool


@pytest.mark.asyncio
async def test_edit_tool_display_summarizes_change_counts_and_compacts_diff(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sample.txt").write_text("one\ntwo\nthree\n")

    result = await execute_edit_tool("sample.txt", "two\n", "TWO\nadded\n")

    assert result.display == "Edited sample.txt (+2 -1)"
    assert (tmp_path / "sample.txt").read_text() == "one\nTWO\nadded\nthree\n"
    assert result.content.startswith(
        '<edit_result path="sample.txt" success="true" replacements="1" '
        'replace_all="false" added="2" removed="1">'
    )
    assert '<diff format="unified"><![CDATA[' in result.content
    assert result.content.endswith("\n]]></diff>\n</edit_result>")
    assert (
        "--- old/sample.txt\n"
        "+++ new/sample.txt\n"
        "@@ -1,3 +1,4 @@\n"
        " one\n"
        "-two\n"
        "+TWO\n"
        "+added\n"
        " three"
    ) in result.content
    assert "\n-two\n\n+TWO" not in result.content


@pytest.mark.asyncio
async def test_edit_tool_not_found_uses_structured_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sample.txt").write_text("content\n")

    result = await execute_edit_tool("sample.txt", "missing", "replacement")

    assert result.display == "String not found in sample.txt"
    assert '<edit_result path="sample.txt" success="false" replacements="0"' in result.content
    assert 'error="string_not_found"' in result.content
    assert '<diff format="unified" />' in result.content


# ---------------------------------------------------------------------------
# P1-14: atomic writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_tool_writes_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = await execute_write_tool("out.txt", "hello\nworld\n")
    assert (tmp_path / "out.txt").read_text() == "hello\nworld\n"
    assert "Wrote 2 lines" in result.display


@pytest.mark.asyncio
async def test_edit_tool_preserves_file_mode_bits(tmp_path, monkeypatch):
    import os
    import stat

    monkeypatch.chdir(tmp_path)
    target = tmp_path / "f.txt"
    target.write_text("a\nb\n")
    os.chmod(target, 0o640)
    original_mode = stat.S_IMODE(os.stat(target).st_mode)

    await execute_edit_tool("f.txt", "a\n", "A\n")

    assert target.read_text() == "A\nb\n"
    assert stat.S_IMODE(os.stat(target).st_mode) == original_mode


@pytest.mark.asyncio
async def test_write_tool_fires_post_write_callbacks(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from stupidex.tools.ast import post_write_callbacks

    monkeypatch.chdir(tmp_path)
    cb = AsyncMock()
    post_write_callbacks.append(cb)
    try:
        await execute_write_tool("cb.txt", "data\n")
        cb.assert_called_once()
    finally:
        post_write_callbacks.remove(cb)


@pytest.mark.asyncio
async def test_write_tool_creates_parent_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = await execute_write_tool("nested/deep/dir/file.txt", "content\n")
    assert (tmp_path / "nested" / "deep" / "dir" / "file.txt").read_text() == "content\n"
    assert "Wrote" in result.display

