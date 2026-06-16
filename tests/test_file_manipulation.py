import pytest

from stupidex.tools.file_manipulation import execute_edit_tool


@pytest.mark.asyncio
async def test_edit_tool_display_summarizes_change_counts_and_compacts_diff(monkeypatch):
    files = {"sample.txt": "one\ntwo\nthree\n"}

    class FakeAsyncFile:
        def __init__(self, file_path, mode="r"):
            self.file_path = file_path
            self.mode = mode

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def read(self):
            return files[self.file_path]

        async def write(self, content):
            files[self.file_path] = content

    def fake_open(file_path, mode="r", *_args, **_kwargs):
        return FakeAsyncFile(file_path, mode)

    monkeypatch.setattr("stupidex.tools.file_manipulation.aiofiles.open", fake_open)

    result = await execute_edit_tool("sample.txt", "two\n", "TWO\nadded\n")

    assert result.display == "Edited sample.txt (+2 -1)"
    assert files["sample.txt"] == "one\nTWO\nadded\nthree\n"
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
async def test_edit_tool_not_found_uses_structured_error(monkeypatch):
    class FakeAsyncFile:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def read(self):
            return "content\n"

    def fake_open(file_path, mode="r", *_args, **_kwargs):
        return FakeAsyncFile()

    monkeypatch.setattr("stupidex.tools.file_manipulation.aiofiles.open", fake_open)

    result = await execute_edit_tool("sample.txt", "missing", "replacement")

    assert result.display == "String not found in sample.txt"
    assert '<edit_result path="sample.txt" success="false" replacements="0"' in result.content
    assert 'error="string_not_found"' in result.content
    assert '<diff format="unified" />' in result.content
