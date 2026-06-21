"""Tests for Message persistence and deserialization (P1-27)."""

import unittest

from stupidex.domain.message import Message, MessageRole, MessageType, Usage


class TestUsageDeserializationForwardCompat(unittest.TestCase):
    """Forward-compat: persisted usage dicts may carry extra keys from a newer
    writer or a different provider. The loader must filter rather than crash the
    whole session restore (see session.py:56/130).
    """

    def _msg_with_usage(self, usage_dict) -> Message:
        data = {
            "role": "assistant",
            "content": "hi",
            "type": "text",
            "usage": usage_dict,
        }
        return Message.from_storage_dict(data)

    def test_extra_key_in_usage_does_not_raise(self):
        """Extra keys (reasoning_tokens, prompt_tokens_details, ...) are dropped."""
        msg = self._msg_with_usage(
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "reasoning_tokens": 99,
                "prompt_tokens_details": {"cached_tokens": 4},
            }
        )
        self.assertIsNotNone(msg.usage)
        assert msg.usage is not None  # for type narrowing
        self.assertEqual(msg.usage.prompt_tokens, 10)
        self.assertEqual(msg.usage.completion_tokens, 5)
        self.assertEqual(msg.usage.total_tokens, 15)

    def test_missing_key_in_usage_defaults_to_zero(self):
        """Partial/corrupt usage dict does not raise; missing fields are 0."""
        msg = self._msg_with_usage({"prompt_tokens": 7})
        assert msg.usage is not None
        self.assertEqual(msg.usage.prompt_tokens, 7)
        self.assertEqual(msg.usage.completion_tokens, 0)
        self.assertEqual(msg.usage.total_tokens, 0)

    def test_completely_empty_usage_defaults_to_zero(self):
        """An empty usage dict yields an all-zero Usage rather than raising."""
        msg = self._msg_with_usage({})
        assert msg.usage is not None
        self.assertEqual(msg.usage.prompt_tokens, 0)
        self.assertEqual(msg.usage.completion_tokens, 0)
        self.assertEqual(msg.usage.total_tokens, 0)

    def test_none_usage_yields_none(self):
        """An explicit `usage: null` yields Message.usage is None."""
        msg = Message.from_storage_dict(
            {"role": "user", "content": "hi", "type": "text", "usage": None}
        )
        self.assertIsNone(msg.usage)

    def test_absent_usage_key_yields_none(self):
        """An absent `usage` key yields Message.usage is None."""
        msg = Message.from_storage_dict(
            {"role": "user", "content": "hi", "type": "text"}
        )
        self.assertIsNone(msg.usage)

    def test_round_trip_preserves_known_fields(self):
        """to_storage_dict -> from_storage_dict preserves the three known fields."""
        orig = Message(
            MessageRole.ASSISTANT,
            "hi",
            MessageType.TEXT,
            usage=Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )
        restored = Message.from_storage_dict(orig.to_storage_dict())
        assert restored.usage is not None
        self.assertEqual(
            restored.usage,
            Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )

    def test_extra_keys_in_usage_do_not_break_session_load(self):
        """Simulates the full-session restore path: a drifted usage dict on one
        message must not cascade-fail the whole session load. This pins the
        P1-27 fix against the chain.py:59 comprehension propagation path.
        """
        # Hand-construct a storage dict for one assistant message with drifted usage.
        data = {
            "role": "assistant",
            "content": "hello",
            "type": "text",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "cache_read_input_tokens": 40,  # forward-compat extra
                "cache_creation_input_tokens": 5,  # forward-compat extra
            },
        }
        # If from_storage_dict raised, a list comprehension over many messages
        # (chain.py:59) would propagate the exception up to SessionManager.load
        # which returns None (data loss). Verify the loader returns a Message.
        msg = Message.from_storage_dict(data)
        self.assertEqual(msg.role, MessageRole.ASSISTANT)
        self.assertEqual(msg.content, "hello")
        assert msg.usage is not None
        self.assertEqual(msg.usage.total_tokens, 150)


class TestMessageToDict(unittest.TestCase):
    """Tests for Message.to_dict() content/tool_call_id/tool_calls contracts (P1-30)."""

    def _tool_calls(self):
        return [{"id": "tc1", "function": {"name": "x", "arguments": "{}"}}]

    def test_assistant_with_tool_calls_and_content_keeps_string(self):
        msg = Message(
            MessageRole.ASSISTANT,
            "hello",
            MessageType.TEXT,
            tool_calls=self._tool_calls(),
        )
        d = msg.to_dict()
        self.assertEqual(d["content"], "hello")
        self.assertIn("tool_calls", d)

    def test_assistant_with_tool_calls_empty_content_becomes_none(self):
        msg = Message(
            MessageRole.ASSISTANT,
            "",
            MessageType.TEXT,
            tool_calls=self._tool_calls(),
        )
        d = msg.to_dict()
        self.assertIsNone(d["content"])
        self.assertIn("tool_calls", d)

    def test_assistant_with_tool_calls_none_content_becomes_none(self):
        msg = Message(
            MessageRole.ASSISTANT,
            None,  # type: ignore[arg-type]
            MessageType.TEXT,
            tool_calls=self._tool_calls(),
        )
        d = msg.to_dict()
        self.assertIsNone(d["content"])

    def test_assistant_without_tool_calls_keeps_empty_content(self):
        msg = Message(MessageRole.ASSISTANT, "", MessageType.TEXT, tool_calls=None)
        d = msg.to_dict()
        self.assertEqual(d["content"], "")
        self.assertNotIn("tool_calls", d)

    def test_tool_role_empty_content_preserved(self):
        msg = Message(
            MessageRole.TOOL,
            "",
            MessageType.TOOL_RESULT,
            tool_call_id="tc1",
        )
        d = msg.to_dict()
        self.assertEqual(d["content"], "")

    def test_user_role_content_preserved(self):
        msg = Message(MessageRole.USER, "hi", MessageType.TEXT)
        d = msg.to_dict()
        self.assertEqual(d["content"], "hi")

    def test_system_role_content_preserved(self):
        msg = Message(MessageRole.SYSTEM, "sys", MessageType.TEXT)
        d = msg.to_dict()
        self.assertEqual(d["content"], "sys")

    def test_tool_call_id_included_when_truthy(self):
        msg = Message(
            MessageRole.TOOL,
            "result",
            MessageType.TOOL_RESULT,
            tool_call_id="tc1",
        )
        d = msg.to_dict()
        self.assertEqual(d["tool_call_id"], "tc1")

    def test_tool_call_id_omitted_when_falsy(self):
        msg = Message(
            MessageRole.TOOL,
            "result",
            MessageType.TOOL_RESULT,
            tool_call_id=None,
        )
        d = msg.to_dict()
        self.assertNotIn("tool_call_id", d)

    def test_tool_calls_deep_copied(self):
        msg = Message(
            MessageRole.ASSISTANT,
            "",
            MessageType.TEXT,
            tool_calls=self._tool_calls(),
        )
        d = msg.to_dict()
        assert d["tool_calls"] is not None  # for type narrowing
        d["tool_calls"][0]["function"]["arguments"] = "mutated"
        self.assertEqual(
            msg.tool_calls[0]["function"]["arguments"], "{}"  # type: ignore[index]
        )


if __name__ == "__main__":
    unittest.main()
