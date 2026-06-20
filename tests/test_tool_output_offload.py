import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.domain.session import get_current_session_id, set_current_session_id
from stupidex.llm import client as llm_client
from stupidex.llm.client import _TOOL_OUTPUT_INLINE_THRESHOLD, _maybe_offload_tool_output


class ToolOutputOffloadTest(unittest.TestCase):
    def setUp(self):
        self._prev_session = get_current_session_id()

    def tearDown(self):
        set_current_session_id(self._prev_session)

    def test_small_output_passes_through_unchanged(self):
        content = "x" * (_TOOL_OUTPUT_INLINE_THRESHOLD - 1)
        result = _maybe_offload_tool_output("read", content, "call-1")
        self.assertEqual(result, content)

    def test_exactly_threshold_passes_through(self):
        content = "y" * _TOOL_OUTPUT_INLINE_THRESHOLD
        result = _maybe_offload_tool_output("read", content, "call-1")
        self.assertEqual(result, content)

    def test_large_output_offloaded_to_cache_file(self):
        set_current_session_id("test-session-offload")
        content = "A" * (_TOOL_OUTPUT_INLINE_THRESHOLD + 5000)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(llm_client, "HOME_CONFIG_DIR", Path(tmp)):
                result = _maybe_offload_tool_output("edit", content, "call-9")
            self.assertIn("edit_result", result)
            self.assertIn("file=\"", result)
            self.assertIn("<warning>", result)
            start = result.index('file="') + len('file="')
            path = result[start:result.index('"', start)]
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), content)
            self.assertNotIn(content[:1000], result)

    def test_skip_set_read_passes_through_unchanged(self):
        set_current_session_id("test-session-offload")
        content = "B" * (_TOOL_OUTPUT_INLINE_THRESHOLD * 5)
        result = _maybe_offload_tool_output("read", content, "call-2")
        self.assertEqual(result, content)

    def test_skip_set_glob_passes_through_unchanged(self):
        set_current_session_id("test-session-offload")
        content = "C" * (_TOOL_OUTPUT_INLINE_THRESHOLD * 3)
        result = _maybe_offload_tool_output("glob", content, "call-3")
        self.assertEqual(result, content)

    def test_no_session_hard_truncates_with_warning(self):
        set_current_session_id(None)
        content = "D" * (_TOOL_OUTPUT_INLINE_THRESHOLD + 2000)
        result = _maybe_offload_tool_output("edit", content, "call-4")
        self.assertIn("<warning>", result)
        self.assertIn("truncated", result)
        self.assertIn("no active session", result)
        self.assertLessEqual(len(result), _TOOL_OUTPUT_INLINE_THRESHOLD * 3)

    def test_executor_task_offloads_large_result_and_keeps_full_content_on_queue(self):
        async def fake_execute_tool(tc, filtered_tools):
            return Message(
                role=MessageRole.TOOL,
                content="Z" * (_TOOL_OUTPUT_INLINE_THRESHOLD + 1000),
                type=MessageType.TOOL_RESULT,
                tool_call_id=tc["id"],
            )

        original = llm_client._execute_tool
        llm_client._execute_tool = fake_execute_tool
        set_current_session_id("test-session-exec")
        try:
            async def run():
                msg_q: asyncio.Queue = asyncio.Queue(maxsize=10)
                ready_q: asyncio.Queue = asyncio.Queue()
                api_messages: list[dict] = []
                assistant_appended = asyncio.Event()
                assistant_appended.set()
                tc = {"id": "call-x", "function": {"name": "edit", "arguments": "{}"}}
                await ready_q.put(tc)
                await ready_q.put(None)
                executor_t = asyncio.create_task(llm_client._executor_task(
                    msg_q, ready_q, api_messages, {}, assistant_appended,
                ))
                msgs = []
                while True:
                    m = await msg_q.get()
                    if m is None:
                        break
                    msgs.append(m)
                await executor_t
                return msgs, api_messages

            with tempfile.TemporaryDirectory() as tmp, patch.object(llm_client, "HOME_CONFIG_DIR", Path(tmp)):
                msgs, api_messages = asyncio.run(run())
            queued = [m for m in msgs if m.type == MessageType.TOOL_RESULT]
            self.assertEqual(len(queued), 1)
            self.assertEqual(len(queued[0].content), _TOOL_OUTPUT_INLINE_THRESHOLD + 1000)
            tool_msgs = [m for m in api_messages if m["role"] == "tool"]
            self.assertEqual(len(tool_msgs), 1)
            self.assertIn("edit_result", tool_msgs[0]["content"])
            self.assertIn("<warning>", tool_msgs[0]["content"])
            self.assertLess(len(tool_msgs[0]["content"]), _TOOL_OUTPUT_INLINE_THRESHOLD + 1000)
        finally:
            llm_client._execute_tool = original


if __name__ == "__main__":
    unittest.main()
