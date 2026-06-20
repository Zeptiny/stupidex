import asyncio
import contextlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import litellm

from stupidex.config import Config
from stupidex.domain.message import (
    Message,
    MessageRole,
    MessageType,
    StreamHistoryState,
    Usage,
    record_streamed_message,
)
from stupidex.llm import client as llm_client
from stupidex.llm.client import classify_error
from stupidex.llm.providers import ProviderResolutionError
from stupidex.widgets import message_widget


def chunk(*, reasoning: str = "", content: str = "", tool_calls=None, usage=None):
    delta = SimpleNamespace(
        reasoning_content=reasoning,
        content=content,
        tool_calls=tool_calls,
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=usage)


def tool_delta(index: int):
    return SimpleNamespace(
        index=index,
        id=f"call-{index}",
        function=SimpleNamespace(name="read", arguments='{"file_path":"README.md"}'),
    )


class StreamHistoryTest(unittest.TestCase):
    def test_record_streamed_message_updates_cumulative_snapshots(self):
        history = []
        state = StreamHistoryState()

        record_streamed_message(
            history,
            Message(MessageRole.ASSISTANT, "Let me read", MessageType.THINKING),
            state,
        )
        record_streamed_message(
            history,
            Message(MessageRole.ASSISTANT, "Let me read the file", MessageType.THINKING),
            state,
        )
        record_streamed_message(
            history,
            Message(MessageRole.ASSISTANT, "Calling tool: read", MessageType.TOOL_CALL),
            state,
        )
        record_streamed_message(
            history,
            Message(MessageRole.TOOL, "file contents", MessageType.TOOL_RESULT, tool_call_id="call-0"),
            state,
        )
        record_streamed_message(
            history,
            Message(MessageRole.ASSISTANT, "Answer", MessageType.TEXT),
            state,
        )
        record_streamed_message(
            history,
            Message(MessageRole.ASSISTANT, "Answer done", MessageType.TEXT),
            state,
        )
        record_streamed_message(
            history,
            Message(MessageRole.ASSISTANT, "", MessageType.TEXT, usage=Usage(1, 2, 3)),
            state,
        )

        self.assertEqual(
            [(msg.type, msg.content) for msg in history],
            [
                (MessageType.THINKING, "Let me read the file"),
                (MessageType.TOOL_RESULT, "file contents"),
                (MessageType.TEXT, "Answer done"),
            ],
        )
        self.assertEqual(history[-1].usage, Usage(1, 2, 3))

    def test_record_streamed_message_attaches_tool_calls_to_assistant_text(self):
        history = []
        state = StreamHistoryState()

        tool_calls = [{"id": "call-0", "type": "function",
                       "function": {"name": "read", "arguments": '{"file_path":"README.md"}'}}]

        record_streamed_message(
            history,
            Message(MessageRole.ASSISTANT, "Let me check", MessageType.TEXT),
            state,
        )
        record_streamed_message(
            history,
            Message(MessageRole.ASSISTANT, "Let me check", MessageType.TEXT, tool_calls=tool_calls),
            state,
        )
        record_streamed_message(
            history,
            Message(MessageRole.TOOL, "contents", MessageType.TOOL_RESULT, tool_call_id="call-0"),
            state,
        )

        self.assertEqual(len(history), 2)
        assistant_msg = history[0]
        self.assertEqual(assistant_msg.role, MessageRole.ASSISTANT)
        self.assertEqual(assistant_msg.content, "Let me check")
        self.assertEqual(assistant_msg.tool_calls, tool_calls)

    def test_record_streamed_message_anchors_tool_calls_without_content(self):
        """When the model calls a tool with no prior text content, the
        tool_calls block must still persist as an assistant message so the
        matching TOOL_RESULT is not orphaned on replay."""
        history = []
        state = StreamHistoryState()

        tool_calls = [{"id": "call-0", "type": "function",
                       "function": {"name": "read", "arguments": '{"file_path":"README.md"}'}}]

        # model goes straight to a tool call, no content
        appended = record_streamed_message(
            history,
            Message(MessageRole.ASSISTANT, "", MessageType.TEXT, tool_calls=tool_calls),
            state,
        )
        self.assertTrue(appended)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].tool_calls, tool_calls)
        self.assertEqual(history[0].content, "")

        record_streamed_message(
            history,
            Message(MessageRole.TOOL, "contents", MessageType.TOOL_RESULT, tool_call_id="call-0"),
            state,
        )
        self.assertEqual(len(history), 2)

        # Verify replay can pair the tool result with its assistant tool_calls message.
        api_messages = llm_client._history_to_api_messages(history)
        self.assertEqual(api_messages[0]["role"], "assistant")
        self.assertEqual(api_messages[0]["tool_calls"], tool_calls)
        self.assertEqual(api_messages[1]["role"], "tool")
        self.assertEqual(api_messages[1]["tool_call_id"], "call-0")

    def test_api_history_replays_thinking_and_drops_orphaned_tool_results(self):
        history = [
            Message(MessageRole.USER, "hello"),
            Message(MessageRole.ASSISTANT, "hidden reasoning", MessageType.THINKING),
            Message(MessageRole.ASSISTANT, "Calling tool: read", MessageType.TOOL_CALL),
            Message(MessageRole.TOOL, "tool output", MessageType.TOOL_RESULT, tool_call_id="call-0"),
            Message(MessageRole.ASSISTANT, "", MessageType.TEXT, usage=Usage(1, 2, 3)),
            Message(MessageRole.ASSISTANT, "final answer", MessageType.TEXT),
        ]

        self.assertEqual(
            llm_client._history_to_api_messages(history),
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hidden reasoning", "reasoning": "hidden reasoning"},
                {"role": "assistant", "content": "final answer"},
            ],
        )

    def test_api_history_includes_tool_calls_and_tool_results_with_matching_ids(self):
        assistant_msg = Message(
            MessageRole.ASSISTANT,
            "Let me check",
            MessageType.TEXT,
            tool_calls=[{"id": "call-0", "type": "function",
                         "function": {"name": "read", "arguments": '{"file_path":"README.md"}'}}],
        )
        history = [
            Message(MessageRole.USER, "hello"),
            assistant_msg,
            Message(MessageRole.TOOL, "file contents", MessageType.TOOL_RESULT, tool_call_id="call-0"),
            Message(MessageRole.ASSISTANT, "final answer", MessageType.TEXT),
        ]

        self.assertEqual(
            llm_client._history_to_api_messages(history),
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "Let me check",
                 "tool_calls": assistant_msg.tool_calls},
                {"role": "tool", "content": "file contents", "tool_call_id": "call-0"},
                {"role": "assistant", "content": "final answer"},
            ],
        )

    def test_api_history_drops_orphaned_tool_result_without_matching_assistant(self):
        history = [
            Message(MessageRole.USER, "hello"),
            Message(MessageRole.TOOL, "orphaned", MessageType.TOOL_RESULT, tool_call_id="call-9"),
            Message(MessageRole.ASSISTANT, "answer", MessageType.TEXT),
        ]

        self.assertEqual(
            llm_client._history_to_api_messages(history),
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "answer"},
            ],
        )


class StreamTaskTest(unittest.IsolatedAsyncioTestCase):
    async def test_dirty_thinking_flushes_before_content_display(self):
        async def response():
            yield chunk(reasoning="The user is")
            yield chunk(reasoning=" asking for help")
            yield chunk(content="Hey!")

        msg_q = asyncio.Queue(maxsize=1)
        ready_q = asyncio.Queue()
        api_messages = []
        assistant_appended = asyncio.Event()
        tool_calls_started = asyncio.Event()

        stream_t = asyncio.create_task(
            llm_client._stream_task(
                response(),
                msg_q,
                ready_q,
                api_messages,
                assistant_appended,
                tool_calls_started,
            )
        )
        executor_t = asyncio.create_task(
            llm_client._executor_task(
                msg_q,
                ready_q,
                api_messages,
                {},
                assistant_appended,
            )
        )

        messages = []
        while True:
            msg = await msg_q.get()
            if msg is None:
                break
            messages.append(msg)

        await asyncio.gather(stream_t, executor_t)

        full_thinking_index = next(
            i for i, msg in enumerate(messages)
            if msg.type == MessageType.THINKING and msg.content == "The user is asking for help"
        )
        content_index = next(
            i for i, msg in enumerate(messages)
            if msg.type == MessageType.TEXT and msg.content == "Hey!"
        )

        self.assertLess(full_thinking_index, content_index)

    async def test_dirty_thinking_flushes_before_tool_call_display(self):
        async def response():
            yield chunk(reasoning="Let me wait")
            yield chunk(reasoning=" for subagents")
            yield chunk(tool_calls=[tool_delta(0)])

        async def fake_execute_tool(tc, filtered_tools):
            return Message(
                role=MessageRole.TOOL,
                content=f"result {tc['id']}",
                type=MessageType.TOOL_RESULT,
                tool_call_id=tc["id"],
            )

        original_execute_tool = llm_client._execute_tool
        llm_client._execute_tool = fake_execute_tool
        try:
            msg_q = asyncio.Queue(maxsize=1)
            ready_q = asyncio.Queue()
            api_messages = []
            assistant_appended = asyncio.Event()
            tool_calls_started = asyncio.Event()

            stream_t = asyncio.create_task(
                llm_client._stream_task(
                    response(),
                    msg_q,
                    ready_q,
                    api_messages,
                    assistant_appended,
                    tool_calls_started,
                )
            )
            executor_t = asyncio.create_task(
                llm_client._executor_task(
                    msg_q,
                    ready_q,
                    api_messages,
                    {},
                    assistant_appended,
                )
            )

            messages = []
            while True:
                msg = await msg_q.get()
                if msg is None:
                    break
                messages.append(msg)

            await asyncio.gather(stream_t, executor_t)
        finally:
            llm_client._execute_tool = original_execute_tool

        full_thinking_index = next(
            i for i, msg in enumerate(messages)
            if msg.type == MessageType.THINKING and msg.content == "Let me wait for subagents"
        )
        tool_call_index = next(
            i for i, msg in enumerate(messages)
            if msg.type == MessageType.TOOL_CALL
        )

        self.assertLess(full_thinking_index, tool_call_index)

    async def test_dirty_thinking_flushes_before_async_tool_result(self):
        async def response():
            yield chunk(reasoning="Let me read")
            yield chunk(reasoning=" the source files")
            yield chunk(tool_calls=[tool_delta(0)])
            yield chunk(tool_calls=[tool_delta(1)])
            await asyncio.sleep(0.01)

        async def fake_execute_tool(tc, filtered_tools):
            return Message(
                role=MessageRole.TOOL,
                content=f"result {tc['id']}",
                type=MessageType.TOOL_RESULT,
                tool_call_id=tc["id"],
            )

        original_execute_tool = llm_client._execute_tool
        llm_client._execute_tool = fake_execute_tool
        try:
            msg_q = asyncio.Queue(maxsize=1)
            ready_q = asyncio.Queue()
            api_messages = []
            assistant_appended = asyncio.Event()
            tool_calls_started = asyncio.Event()

            stream_t = asyncio.create_task(
                llm_client._stream_task(
                    response(),
                    msg_q,
                    ready_q,
                    api_messages,
                    assistant_appended,
                    tool_calls_started,
                )
            )
            executor_t = asyncio.create_task(
                llm_client._executor_task(
                    msg_q,
                    ready_q,
                    api_messages,
                    {},
                    assistant_appended,
                )
            )

            messages = []
            while True:
                msg = await msg_q.get()
                if msg is None:
                    break
                messages.append(msg)

            await asyncio.gather(stream_t, executor_t)
        finally:
            llm_client._execute_tool = original_execute_tool

        full_thinking_index = next(
            i for i, msg in enumerate(messages)
            if msg.type == MessageType.THINKING and msg.content == "Let me read the source files"
        )
        first_tool_result_index = next(
            i for i, msg in enumerate(messages)
            if msg.type == MessageType.TOOL_RESULT
        )

        self.assertLess(full_thinking_index, first_tool_result_index)

    async def test_whitespace_reasoning_is_not_emitted(self):
        async def response():
            yield chunk(reasoning="   ")
            yield chunk(reasoning="\n\n")
            yield chunk(content="Hello")

        msg_q = asyncio.Queue(maxsize=1)
        ready_q = asyncio.Queue()
        api_messages = []
        assistant_appended = asyncio.Event()
        tool_calls_started = asyncio.Event()

        stream_t = asyncio.create_task(
            llm_client._stream_task(
                response(),
                msg_q,
                ready_q,
                api_messages,
                assistant_appended,
                tool_calls_started,
            )
        )
        executor_t = asyncio.create_task(
            llm_client._executor_task(
                msg_q,
                ready_q,
                api_messages,
                {},
                assistant_appended,
            )
        )

        messages = []
        while True:
            msg = await msg_q.get()
            if msg is None:
                break
            messages.append(msg)

        await asyncio.gather(stream_t, executor_t)

        self.assertEqual(
            [(msg.type, msg.content) for msg in messages],
            [(MessageType.TEXT, "Hello")],
        )

    async def test_final_text_message_does_not_duplicate_content(self):
        async def response():
            yield chunk(content="Hello")
            yield chunk(content=" world", usage=Usage(1, 2, 3))

        msg_q = asyncio.Queue(maxsize=1)
        ready_q = asyncio.Queue()
        api_messages = []
        assistant_appended = asyncio.Event()
        tool_calls_started = asyncio.Event()

        stream_t = asyncio.create_task(
            llm_client._stream_task(
                response(),
                msg_q,
                ready_q,
                api_messages,
                assistant_appended,
                tool_calls_started,
            )
        )
        executor_t = asyncio.create_task(
            llm_client._executor_task(
                msg_q,
                ready_q,
                api_messages,
                {},
                assistant_appended,
            )
        )

        messages = []
        while True:
            msg = await msg_q.get()
            if msg is None:
                break
            messages.append(msg)

        await asyncio.gather(stream_t, executor_t)

        text_messages = [msg for msg in messages if msg.type == MessageType.TEXT]
        self.assertEqual(len(text_messages), 3)
        self.assertEqual(text_messages[0].content, "Hello")
        self.assertEqual(text_messages[1].content, "Hello world")
        self.assertEqual(text_messages[2].content, "")
        self.assertEqual(text_messages[2].usage, Usage(1, 2, 3))


class StreamWidgetTest(unittest.IsolatedAsyncioTestCase):
    def test_tool_result_without_display_uses_safe_collapsed_title(self):
        raw_content = "x" * 300
        widget = message_widget.ToolResultMessageWidget(
            Message(MessageRole.TOOL, raw_content, MessageType.TOOL_RESULT)
        )

        collapsible = next(widget.compose())

        self.assertEqual(collapsible.title, "Tool result")

    def test_tool_result_display_title_is_one_line_and_bounded(self):
        widget = message_widget.ToolResultMessageWidget(
            Message(
                MessageRole.TOOL,
                "content",
                MessageType.TOOL_RESULT,
                display=f"Read README.md\n{'x' * 300}",
            )
        )

        collapsible = next(widget.compose())

        self.assertNotIn("\n", collapsible.title)
        self.assertLessEqual(len(collapsible.title), 120)
        self.assertTrue(collapsible.title.endswith("..."))

    def test_edit_tool_result_renders_compact_colored_diff(self):
        rendered = message_widget.get_tool_result_renderable(
            Message(
                MessageRole.TOOL,
                '<edit_result path="demo.py" success="true" replacements="1" '
                'replace_all="false" added="2" removed="1">\n'
                '<diff format="unified"><![CDATA[\n'
                "--- old/demo.py\n"
                "+++ new/demo.py\n"
                "@@ -1,3 +1,4 @@\n"
                " def alpha():\n"
                "-    return 1\n"
                "+    return 2\n"
                "+class Gamma:\n"
                "     pass\n"
                "]]></diff>\n"
                "</edit_result>",
                MessageType.TOOL_RESULT,
                display="Edited demo.py (+2 -1)",
            )
        )

        self.assertIn("   1  def alpha():\n", rendered.plain)
        self.assertIn("   2 -    return 1\n", rendered.plain)
        self.assertIn("   2 +    return 2\n", rendered.plain)
        self.assertIn("   3 +class Gamma:\n", rendered.plain)
        self.assertNotIn("@@", rendered.plain)
        self.assertNotIn("--- old/demo.py", rendered.plain)

        styles = {span.style for span in rendered.spans}
        self.assertIn(message_widget._DIFF_ADDED_STYLE, styles)
        self.assertIn(message_widget._DIFF_REMOVED_STYLE, styles)
        self.assertTrue(any(getattr(span.style, "color", None) is not None for span in rendered.spans))

    async def test_output_pane_hides_horizontal_overflow(self):
        from stupidex.app import Stupidex

        app = Stupidex()
        async with app.run_test():
            output = app.query_one("#output")

            self.assertEqual(output.styles.overflow_x, "hidden")
            self.assertEqual(output.styles.overflow_y, "auto")

    async def test_streamed_tool_result_group_has_spacing_after_thinking(self):
        from stupidex.app import Stupidex

        tool_results = [
            Message(
                MessageRole.TOOL,
                f"file contents {i}",
                MessageType.TOOL_RESULT,
                display=f"Read file_{i}.py lines 1-10",
            )
            for i in range(3)
        ]
        app = Stupidex()
        async with app.run_test(size=(100, 30)) as pilot:
            output = app.query_one("#output")
            state = message_widget.StreamWidgetState()

            await message_widget.mount_streamed_message(
                output,
                Message(MessageRole.USER, "Explore this codebase"),
                state,
            )
            await message_widget.mount_streamed_message(
                output,
                Message(MessageRole.ASSISTANT, "Checking the file", MessageType.THINKING),
                state,
            )
            await message_widget.mount_streamed_message(
                output,
                Message(
                    MessageRole.ASSISTANT,
                    "",
                    MessageType.TOOL_CALL,
                    metadata={"tool_name": "read"},
                ),
                state,
            )
            for _ in tool_results[1:]:
                await message_widget.mount_streamed_message(
                    output,
                    Message(
                        MessageRole.ASSISTANT,
                        "",
                        MessageType.TOOL_CALL,
                        metadata={"tool_name": "read"},
                    ),
                    state,
                )
            for result in tool_results:
                await message_widget.mount_streamed_message(output, result, state)
            await pilot.pause()

            user_widget = output.children[0]
            thinking_widget = output.children[1]
            tool_result_widgets = output.children[2:5]
            thinking_collapse = thinking_widget.query_one(".thinking-collapse")

            self.assertEqual(thinking_widget.region.y, user_widget.region.y + user_widget.region.height + 1)
            self.assertEqual(thinking_widget.region.y, thinking_collapse.region.y)
            self.assertEqual(thinking_widget.region.height, thinking_collapse.region.height)
            self.assertIn("after-thinking", tool_result_widgets[0].classes)
            self.assertEqual(
                tool_result_widgets[0].region.y,
                thinking_collapse.region.y + thinking_collapse.region.height + 1,
            )
            for previous, current in zip(tool_result_widgets, tool_result_widgets[1:], strict=False):
                self.assertNotIn("after-thinking", current.classes)
                self.assertEqual(current.region.y, previous.region.y + previous.region.height)

            await message_widget.mount_streamed_message(
                output,
                Message(MessageRole.ASSISTANT, "Checking another file", MessageType.THINKING),
                state,
            )
            await pilot.pause()

            next_thinking_widget = output.children[5]
            last_tool_result_widget = tool_result_widgets[-1]
            self.assertEqual(
                next_thinking_widget.region.y,
                last_tool_result_widget.region.y + last_tool_result_widget.region.height + 1,
            )

    async def test_streamed_tool_result_after_assistant_text_does_not_get_thinking_spacing(self):
        from stupidex.app import Stupidex

        app = Stupidex()
        async with app.run_test(size=(100, 30)) as pilot:
            output = app.query_one("#output")
            state = message_widget.StreamWidgetState()

            await message_widget.mount_streamed_message(
                output,
                Message(MessageRole.ASSISTANT, "Checking the file", MessageType.THINKING),
                state,
            )
            await message_widget.mount_streamed_message(
                output,
                Message(MessageRole.ASSISTANT, "Let me read the key files.", MessageType.TEXT),
                state,
            )
            await message_widget.mount_streamed_message(
                output,
                Message(
                    MessageRole.ASSISTANT,
                    "",
                    MessageType.TOOL_CALL,
                    metadata={"tool_name": "read"},
                ),
                state,
            )
            await message_widget.mount_streamed_message(
                output,
                Message(
                    MessageRole.TOOL,
                    "file contents",
                    MessageType.TOOL_RESULT,
                    display="Read README.md lines 1-10",
                ),
                state,
            )
            await pilot.pause()

            assistant_widget = output.children[1]
            tool_result_widget = output.children[2]

            self.assertNotIn("after-thinking", tool_result_widget.classes)
            self.assertEqual(tool_result_widget.region.y, assistant_widget.region.y + assistant_widget.region.height)

    async def test_thinking_flushes_before_first_assistant_text_widget_mount(self):
        events = []

        class FakeThinking:
            def flush(self):
                events.append("flush")

            def finish(self):
                events.append("finish")

        class FakeAssistantWidget:
            def __init__(self, msg):
                self.msg = msg

            def scroll_visible(self):
                pass

        class FakeContainer:
            async def mount(self, widget):
                events.append("mount")
                self.widget = widget

        container = FakeContainer()
        state = message_widget.StreamWidgetState(thinking=FakeThinking())

        with patch.object(message_widget, "AssistantMessageWidget", FakeAssistantWidget):
            await message_widget.mount_streamed_message(
                container,
                Message(MessageRole.ASSISTANT, "Hi!", MessageType.TEXT),
                state,
            )

        self.assertEqual(events, ["finish", "mount"])
        self.assertIs(state.content, container.widget)


class ClassifyErrorTest(unittest.TestCase):
    def test_authentication_error(self):
        exc = litellm.AuthenticationError(
            message="Invalid API key", llm_provider="openai", model="gpt-4"
        )
        title, detail = classify_error(exc)
        self.assertEqual(title, "Authentication Failed")
        self.assertIn("API key", detail)

    def test_rate_limit_error(self):
        exc = litellm.RateLimitError(
            message="Rate limit", llm_provider="openai", model="gpt-4"
        )
        title, detail = classify_error(exc)
        self.assertEqual(title, "Rate Limit Exceeded")
        self.assertIn("wait", detail)

    def test_api_connection_error(self):
        exc = litellm.APIConnectionError(
            message="Connection refused", llm_provider="openai", model="gpt-4"
        )
        title, detail = classify_error(exc)
        self.assertEqual(title, "Connection Failed")
        self.assertIn("network", detail.lower())

    def test_bad_request_error(self):
        exc = litellm.BadRequestError(
            message="Invalid model", llm_provider="openai", model="bad-model"
        )
        title, detail = classify_error(exc)
        self.assertEqual(title, "Invalid Request")
        self.assertIn("Invalid model", detail)

    def test_generic_api_error(self):
        exc = litellm.APIError(
            status_code=500,
            message="Server error",
            llm_provider="openai",
            model="gpt-4",
        )
        title, detail = classify_error(exc)
        self.assertEqual(title, "API Error")
        self.assertIn("Server error", detail)

    def test_timeout_error(self):
        exc = httpx.TimeoutException("Connection timed out")
        title, detail = classify_error(exc)
        self.assertEqual(title, "Request Timed Out")

    def test_http_error(self):
        exc = httpx.HTTPError("Bad gateway")
        title, detail = classify_error(exc)
        self.assertEqual(title, "HTTP Error")
        self.assertIn("Bad gateway", detail)

    def test_generic_exception(self):
        exc = RuntimeError("something broke")
        title, detail = classify_error(exc)
        self.assertEqual(title, "Unexpected Error")
        self.assertIn("something broke", detail)

    def test_error_messages_excluded_from_api_history(self):
        history = [
            Message(MessageRole.USER, "hello"),
            Message(MessageRole.ASSISTANT, "answer", MessageType.TEXT),
            Message(
                MessageRole.ASSISTANT,
                "Invalid API key",
                MessageType.ERROR,
                metadata={"error_title": "Authentication Failed"},
            ),
        ]
        api_messages = llm_client._history_to_api_messages(history)
        self.assertEqual(
            api_messages,
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "answer"},
            ],
        )

    def test_error_messages_pass_through_record_streamed_message(self):
        history = []
        state = StreamHistoryState()
        error_msg = Message(
            MessageRole.ASSISTANT,
            "Invalid API key",
            MessageType.ERROR,
            metadata={"error_title": "Authentication Failed"},
        )
        result = record_streamed_message(history, error_msg, state)
        self.assertTrue(result)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].type, MessageType.ERROR)

    def test_timeout_error_is_classified(self):
        exc = litellm.Timeout(
            message="Request timed out", llm_provider="openai", model="gpt-4"
        )
        title, detail = classify_error(exc)
        self.assertEqual(title, "Request Timed Out")
        self.assertIn("time", detail.lower())

    def test_internal_server_error_is_classified(self):
        exc = litellm.InternalServerError(
            message="Internal error", llm_provider="openai", model="gpt-4"
        )
        title, detail = classify_error(exc)
        self.assertEqual(title, "Server Error")
        self.assertIn("Internal error", detail)

    def test_service_unavailable_error_is_classified(self):
        exc = litellm.ServiceUnavailableError(
            message="Service down", llm_provider="openai", model="gpt-4"
        )
        title, detail = classify_error(exc)
        self.assertEqual(title, "Service Unavailable")

    def test_provider_resolution_error_is_classified(self):
        exc = ProviderResolutionError("Unknown provider alias 'nope'")
        title, detail = classify_error(exc)
        self.assertEqual(title, "Unknown Provider")
        self.assertIn("alias", detail)

    def test_provider_resolution_error_with_empty_message_uses_type_name(self):
        exc = ProviderResolutionError("")
        title, detail = classify_error(exc)
        self.assertEqual(title, "Unknown Provider")
        self.assertIn("ProviderResolutionError", detail)


class StreamResponseProviderResolutionTest(unittest.IsolatedAsyncioTestCase):
    """U3 -- stream_response resolves `alias/model` via resolve_model_ref
    and passes resolved base_url + api_key through to litellm.acompletion."""

    async def _drive_stream_response(self, *, model, providers, env=None):
        """Invoke stream_response with mocked deps; return captured acompletion kwargs.

        Patches litellm.acompletion to record kwargs and yield a single chunk with
        usage that lets the loop exit cleanly (no tool calls -> early return).
        """
        cfg = Config(providers=providers)

        captured: dict = {}

        async def fake_acompletion(**kwargs):
            captured.update(kwargs)

            async def _stream():
                yield chunk(content="hi", usage=Usage(1, 2, 3))

            return _stream()

        dummy_dynamic = Message(MessageRole.SYSTEM, "<dynamic/>", MessageType.TEXT)

        env_patches = []
        if env:
            for k, v in env.items():
                env_patches.append(patch.dict(os.environ, {k: v}, clear=False))

        acompletion_mock = AsyncMock(side_effect=fake_acompletion)
        with patch("stupidex.llm.client.get_config", return_value=cfg), \
                patch("stupidex.llm.providers.get_config", return_value=cfg), \
                patch("stupidex.llm.client.build_dynamic_system_prompt",
                      new=AsyncMock(return_value=dummy_dynamic)), \
                patch("stupidex.llm.client.get_tool_registry", return_value={}), \
                patch("stupidex.llm.client.litellm.acompletion", new=acompletion_mock):
            stack = contextlib.ExitStack()
            for p in env_patches:
                stack.enter_context(p)
            with stack:
                gen = llm_client.stream_response(
                    messages=[],
                    model=model,
                    allowed_tools=[],
                    system_prompt="",
                )
                async for _ in gen:
                    pass

        return captured

    async def test_resolves_alias_model_and_passes_tuple_to_acompletion(self):
        providers = {
            "default": {
                "base_url": "https://opencode.ai/zen/go/v1",
                "litellm_provider": "openai",
                "models": {"mimo-v2.5": {}},
            }
        }
        captured = await self._drive_stream_response(
            model="default/mimo-v2.5", providers=providers
        )

        self.assertEqual(captured["model"], "openai/mimo-v2.5")
        self.assertEqual(captured["base_url"], "https://opencode.ai/zen/go/v1")
        self.assertIsNone(captured["api_key"])

    async def test_passes_literal_api_key(self):
        providers = {
            "default": {
                "base_url": "https://example.test/v1",
                "litellm_provider": "openai",
                "api_key": "sk-test-123",
                "models": {"mimo-v2.5": {}},
            }
        }
        captured = await self._drive_stream_response(
            model="default/mimo-v2.5", providers=providers
        )

        self.assertEqual(captured["model"], "openai/mimo-v2.5")
        self.assertEqual(captured["base_url"], "https://example.test/v1")
        self.assertEqual(captured["api_key"], "sk-test-123")

    async def test_passes_api_key_env_value_when_set(self):
        providers = {
            "default": {
                "base_url": "https://example.test/v1",
                "litellm_provider": "openai",
                "api_key_env": "STUPIDEX_TEST_OPENAI_KEY",
                "models": {"mimo-v2.5": {}},
            }
        }
        captured = await self._drive_stream_response(
            model="default/mimo-v2.5",
            providers=providers,
            env={"STUPIDEX_TEST_OPENAI_KEY": "env-key-456"},
        )

        self.assertEqual(captured["api_key"], "env-key-456")

    async def test_bare_model_id_when_litellm_provider_unset(self):
        providers = {
            "custom": {
                "base_url": "https://example.test/v1",
                "models": {"my-model-id": {}},
            }
        }
        captured = await self._drive_stream_response(
            model="custom/my-model-id", providers=providers
        )

        self.assertEqual(captured["model"], "my-model-id")
        self.assertEqual(captured["base_url"], "https://example.test/v1")
        self.assertIsNone(captured["api_key"])

    async def test_routes_distinct_alias_to_correct_provider_covers_f3(self):
        providers = {
            "default": {
                "base_url": "https://default.test/v1",
                "litellm_provider": "openai",
                "models": {"mimo-v2.5": {}},
            },
            "work": {
                "base_url": "https://work.test/v1",
                "litellm_provider": "openai",
                "api_key": "sk-work-key",
                "models": {"gpt-4o": {}},
            },
        }
        captured_default = await self._drive_stream_response(
            model="default/mimo-v2.5", providers=providers
        )
        captured_work = await self._drive_stream_response(
            model="work/gpt-4o", providers=providers
        )

        self.assertEqual(captured_default["base_url"], "https://default.test/v1")
        self.assertIsNone(captured_default["api_key"])
        self.assertEqual(captured_default["model"], "openai/mimo-v2.5")

        self.assertEqual(captured_work["base_url"], "https://work.test/v1")
        self.assertEqual(captured_work["api_key"], "sk-work-key")
        self.assertEqual(captured_work["model"], "openai/gpt-4o")

    async def test_provider_resolution_failure_raises_before_a_completion(self):
        """An unknown alias -> ProviderResolutionError surfaces from stream_response.

        resolve_model_ref runs before the first litellm.acompletion call, so
        acompletion must not be invoked at all.
        """
        cfg = Config(providers={"default": {
            "base_url": "https://example.test/v1",
            "litellm_provider": "openai",
            "models": {"mimo-v2.5": {}},
        }})

        acompletion_mock = AsyncMock()

        with patch("stupidex.llm.client.get_config", return_value=cfg), \
                patch("stupidex.llm.providers.get_config", return_value=cfg), \
                patch("stupidex.llm.client.build_dynamic_system_prompt",
                      new=AsyncMock(return_value=Message(
                          MessageRole.SYSTEM, "<dynamic/>", MessageType.TEXT))), \
                patch("stupidex.llm.client.get_tool_registry", return_value={}), \
                patch("stupidex.llm.client.litellm.acompletion", new=acompletion_mock):
            gen = llm_client.stream_response(
                messages=[],
                model="typo-alias/mimo-v2.5",
                allowed_tools=[],
                system_prompt="",
            )
            with self.assertRaises(ProviderResolutionError):
                async for _ in gen:
                    pass

        acompletion_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
