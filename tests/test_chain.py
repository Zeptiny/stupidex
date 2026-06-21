"""Tests for chain._reconcile_orphan_tool_results mutation (P1-29)."""

import unittest

from stupidex.domain.chain import Chain, ChainStatus, _reconcile_orphan_tool_results
from stupidex.domain.message import Message, MessageRole, MessageType


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

    def test_duplicate_tool_results_for_seen_id_both_kept(self):
        messages = [
            _assistant_with_tool_calls("tc1"),
            _tool_result("tc1"),
            _tool_result("tc1"),
        ]
        _reconcile_orphan_tool_results(messages)
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[1].tool_call_id, "tc1")
        self.assertEqual(messages[2].tool_call_id, "tc1")

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


if __name__ == "__main__":
    unittest.main()
