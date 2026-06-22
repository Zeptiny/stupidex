"""Tests for chain._reconcile_orphan_tool_results mutation (P1-29)."""

import unittest

from stupidex.domain.chain import Chain, ChainStatus, _reconcile_orphan_tool_results
from stupidex.domain.message import Message, MessageRole, MessageType, Usage


def _assistant_with_tool_calls(tc_id: str | None) -> Message:
    tc: dict = {"function": {"name": "lookup", "arguments": "{}"}}
    if tc_id is not None:
        tc["id"] = tc_id
    return Message(
        MessageRole.ASSISTANT,
        "",
        MessageType.TEXT,
        tool_calls=[tc],
    )


def _tool_result(tc_id: str | None) -> Message:
    return Message(
        MessageRole.TOOL,
        "result",
        MessageType.TOOL_RESULT,
        tool_call_id=tc_id,
    )


class TestReconcileOrphanToolResults(unittest.TestCase):
    def test_empty_list_no_mutation(self):
        messages: list[Message] = []
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(messages, [])

    def test_orphan_tool_result_dropped(self):
        messages = [_tool_result("orphan")]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 0)

    def test_assistant_tool_calls_registers_ids(self):
        messages = [
            _assistant_with_tool_calls("tc1"),
            _tool_result("tc1"),
        ]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 2)

    def test_tool_result_with_matching_id_kept(self):
        messages = [
            _assistant_with_tool_calls("tc1"),
            _tool_result("tc1"),
        ]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(messages[0].role, MessageRole.ASSISTANT)
        self.assertEqual(messages[1].tool_call_id, "tc1")

    def test_assistant_tool_calls_without_id_not_registered(self):
        messages = [
            _assistant_with_tool_calls(None),
            _tool_result("missing-id"),
        ]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, MessageRole.ASSISTANT)

    def test_none_tool_call_id_kept(self):
        messages = [_tool_result(None)]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 1)
        self.assertIsNone(messages[0].tool_call_id)

    def test_multiple_orphans_all_dropped(self):
        messages = [
            _tool_result("a"),
            _tool_result("b"),
            _tool_result("c"),
        ]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 0)

    def test_duplicate_tool_results_for_seen_id_second_dropped(self):
        """P2-3: a second TOOL_RESULT with an already-served tool_call_id is
        dropped at replay time (strict OpenAI/Anthropic providers 400 on
        duplicate tool_call_id in the same history)."""
        messages = [
            _assistant_with_tool_calls("tc1"),
            _tool_result("tc1"),
            _tool_result("tc1"),
        ]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, MessageRole.ASSISTANT)
        self.assertEqual(messages[1].tool_call_id, "tc1")

    def test_duplicate_tool_result_across_turns_second_dropped_as_orphan(self):
        """P2-3 edge case: same tool_call_id appearing across two separate
        turns. The second tool(tc1) is dropped — as orphan, because
        pending_tool_call_ids was reset by the intervening assistant(content)
        message; the duplicate-result check is not what fires here. Both
        drop paths converge on the same outcome without firing duplicate-drop
        log noise."""
        messages = [
            _assistant_with_tool_calls("tc1"),
            _tool_result("tc1"),
            Message(MessageRole.ASSISTANT, "intermediate", MessageType.TEXT),
            _tool_result("tc1"),
        ]
        _reconcile_orphan_tool_results(messages)
        # The first tool(tc1) is kept (paired), the second is dropped as orphan
        # (no preceding assistant tool_calls in this turn). Both drops converge
        # on the same outcome: only one tool(tc1) survives.
        kept_tool_results = [m for m in messages if m.role == MessageRole.TOOL]
        self.assertEqual(len(kept_tool_results), 1)
        self.assertEqual(kept_tool_results[0].tool_call_id, "tc1")

    def test_duplicate_tool_result_back_to_back_first_kept(self):
        """P2-3 edge case: back-to-back duplicate — first kept, second dropped,
        preserving order."""
        messages = [
            _assistant_with_tool_calls("tc1"),
            _tool_result("tc1"),
            _tool_result("tc1"),
            _tool_result("tc1"),
        ]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1].tool_call_id, "tc1")

    def test_tool_result_before_assistant_partner_dropped(self):
        messages = [
            _tool_result("tc1"),
            _assistant_with_tool_calls("tc1"),
        ]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, MessageRole.ASSISTANT)

    def test_no_op_preserves_list_identity(self):
        messages = [
            _assistant_with_tool_calls("tc1"),
            _tool_result("tc1"),
        ]
        original = messages
        _reconcile_orphan_tool_results(messages)
        self.assertIs(messages, original)

    def test_mutation_preserves_list_identity_replaces_contents(self):
        messages = [
            _tool_result("orphan"),
            _assistant_with_tool_calls("tc1"),
            _tool_result("tc1"),
        ]
        original = messages
        _reconcile_orphan_tool_results(messages)
        self.assertIs(messages, original)
        self.assertEqual(len(messages), 2)

    def test_user_message_kept(self):
        messages = [
            Message(MessageRole.USER, "hi", MessageType.TEXT),
        ]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "hi")

    def test_system_message_kept(self):
        messages = [
            Message(MessageRole.SYSTEM, "sys", MessageType.TEXT),
        ]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].content, "sys")

    def test_round_trip_from_storage_dict_runs_reconcile(self):
        data = {
            "model": "m",
            "messages": [
                {
                    "role": "tool",
                    "content": "result",
                    "type": "tool_result",
                    "tool_call_id": "orphan",
                },
                {
                    "role": "assistant",
                    "content": "",
                    "type": "text",
                    "tool_calls": [{"id": "tc1", "function": {"name": "f", "arguments": "{}"}}],
                },
                {
                    "role": "tool",
                    "content": "result",
                    "type": "tool_result",
                    "tool_call_id": "tc1",
                },
            ],
            "start_time": 0.0,
            "end_time": None,
            "status": "completed",
        }
        chain = Chain.from_storage_dict(data)
        self.assertEqual(len(chain.messages), 2)
        self.assertEqual(chain.messages[0].role, MessageRole.ASSISTANT)
        self.assertEqual(chain.messages[1].tool_call_id, "tc1")


class TestChainFinishIdempotency(unittest.TestCase):
    """P2-14: Chain.finish() must be a no-op once the chain has left RUNNING."""

    def test_finish_completes_running_chain(self):
        chain = Chain()
        self.assertIsNone(chain.end_time)
        chain.finish()
        self.assertIsNotNone(chain.end_time)
        self.assertEqual(chain.status, ChainStatus.COMPLETED)

    def test_finish_twice_second_call_is_noop(self):
        chain = Chain()
        chain.finish(ChainStatus.COMPLETED)
        first_end = chain.end_time
        first_status = chain.status
        self.assertIsNotNone(first_end)
        chain.finish(ChainStatus.FAILED)
        self.assertEqual(chain.end_time, first_end)
        self.assertEqual(chain.status, first_status)

    def test_finish_failed_is_terminal_idempotent(self):
        chain = Chain()
        chain.finish(ChainStatus.FAILED)
        first_end = chain.end_time
        chain.finish(ChainStatus.COMPLETED)
        self.assertEqual(chain.end_time, first_end)
        self.assertEqual(chain.status, ChainStatus.FAILED)

    def test_finish_interrupted_is_terminal_idempotent(self):
        chain = Chain()
        chain.finish(ChainStatus.INTERRUPTED)
        first_end = chain.end_time
        chain.finish(ChainStatus.COMPLETED)
        self.assertEqual(chain.end_time, first_end)
        self.assertEqual(chain.status, ChainStatus.INTERRUPTED)


class TestChainFormatElapsed(unittest.TestCase):
    """P2-14: Chain.format_elapsed boundary outputs."""

    def test_zero_seconds_renders_milliseconds(self):
        self.assertEqual(Chain.format_elapsed(0), "0ms")

    def test_sub_second_renders_milliseconds(self):
        self.assertEqual(Chain.format_elapsed(0.5), "500ms")

    def test_just_under_one_second_renders_milliseconds(self):
        self.assertEqual(Chain.format_elapsed(0.999), "999ms")

    def test_exactly_one_second_renders_seconds(self):
        self.assertEqual(Chain.format_elapsed(1), "1.0s")

    def test_just_under_one_minute_renders_seconds(self):
        self.assertEqual(Chain.format_elapsed(59.9), "59.9s")

    def test_exactly_fifty_nine_seconds(self):
        self.assertEqual(Chain.format_elapsed(59), "59.0s")

    def test_exactly_sixty_seconds_rolls_to_minutes(self):
        self.assertEqual(Chain.format_elapsed(60), "1m 0s")

    def test_one_hour(self):
        self.assertEqual(Chain.format_elapsed(3600), "60m 0s")

    def test_one_hour_fifty_nine_minutes(self):
        self.assertEqual(Chain.format_elapsed(3600 + 59 * 60), "119m 0s")

    def test_one_hour_fifty_nine_minutes_thirty_seconds(self):
        self.assertEqual(Chain.format_elapsed(3600 + 59 * 60 + 30), "119m 30s")


class TestChainFormatTokens(unittest.TestCase):
    """U3: Chain.format_tokens boundary outputs."""

    def test_below_thousand_is_raw(self):
        self.assertEqual(Chain.format_tokens(0), "0")

    def test_just_under_thousand_is_raw(self):
        self.assertEqual(Chain.format_tokens(999), "999")

    def test_thousand_rolls_to_k(self):
        # 1000 / 1000 = 1.0 → "1.0k"
        self.assertEqual(Chain.format_tokens(1000), "1.0k")

    def test_twelve_hundred(self):
        self.assertEqual(Chain.format_tokens(1200), "1.2k")

    def test_twelve_thousand(self):
        self.assertEqual(Chain.format_tokens(12345), "12.3k")

    def test_just_under_million_stays_k(self):
        self.assertEqual(Chain.format_tokens(999_999), "1000.0k")

    def test_million_rolls_to_M(self):
        self.assertEqual(Chain.format_tokens(1_000_000), "1.0M")

    def test_one_and_a_half_million(self):
        self.assertEqual(Chain.format_tokens(1_500_000), "1.5M")


class TestChainFooterWidgetTokenDisplay(unittest.TestCase):
    """U3: ChainFooterWidget renders per-chain input/cached/output tokens."""

    def _footer_text(self, chain: Chain) -> str:
        # Import lazily so a textual import failure in the test environment
        # only affects these cases, not the rest of the test module.
        from stupidex.widgets.message_widget import ChainFooterWidget

        widget = ChainFooterWidget(chain)
        return widget._build_text()

    def test_footer_text_with_usage_shows_subset_format(self):
        chain = Chain(model="gpt-4o")
        chain.messages = [
            Message(MessageRole.USER, "hi", MessageType.TEXT),
            Message(
                MessageRole.ASSISTANT,
                "hello",
                MessageType.TEXT,
                usage=Usage(1000, 200, 1200, cached_tokens=400),
            ),
        ]
        text = self._footer_text(chain)
        self.assertIn("1.0k", text)  # input
        self.assertIn("400", text)  # cached (parenthetical subset)
        self.assertIn("200", text)  # output
        self.assertIn("↑1.0k", text)
        self.assertIn("(⟲400)", text)
        self.assertIn("↓200", text)

    def test_footer_text_no_usage_omits_token_segment(self):
        chain = Chain(model="gpt-4o")
        chain.messages = [
            Message(MessageRole.USER, "hi", MessageType.TEXT),
            Message(MessageRole.ASSISTANT, "hello", MessageType.TEXT),
        ]
        text = self._footer_text(chain)
        self.assertIn("gpt-4o", text)
        self.assertNotIn("↑", text)
        self.assertNotIn("↓", text)
        self.assertNotIn("⟲", text)

    def test_footer_text_uses_last_usage_message(self):
        chain = Chain(model="m")
        chain.messages = [
            Message(
                MessageRole.ASSISTANT,
                "first",
                MessageType.TEXT,
                usage=Usage(10, 5, 15, cached_tokens=1),
            ),
            Message(
                MessageRole.ASSISTANT,
                "second",
                MessageType.TEXT,
                usage=Usage(2000, 800, 2800, cached_tokens=500),
            ),
        ]
        text = self._footer_text(chain)
        # Should reflect the second (last) usage, not the first.
        self.assertIn("2.0k", text)
        self.assertIn("800", text)
        self.assertIn("500", text)
        self.assertNotIn("10", text)


if __name__ == "__main__":
    unittest.main()
