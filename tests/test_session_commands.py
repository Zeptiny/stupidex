"""Tests for the `/model` picker construction (unit U5).

Covers R7, R10 (see
docs/plans/2026-06-18-001-feat-multi-provider-support-plan.md).

Pattern mirrors `tests/test_providers_config.py` and `tests/test_mcp_config.py`:
`unittest.TestCase` classes that exercise the construction helper as a pure
function, with `resolve_model_metadata` mocked to avoid litellm/network
calls. One integration-style case (`TestExecuteCommandEmptyConfig`) drives the
`/model` dispatch path via `execute_command` with a mock `app`.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from stupidex.commands.session_commands import (
    _build_model_picker_items,
    _format_model_label,
    execute_command,
)
from stupidex.config import Config


def _meta(
    max_in: int | None = None,
    max_out: int | None = None,
    supports_vision: bool = False,
    mode: str = "chat",
) -> dict:
    """Build the resolved-metadata dict shape returned by `resolve_model_metadata`."""
    return {
        "max_input_tokens": max_in,
        "max_output_tokens": max_out,
        "supports_vision": supports_vision,
        "mode": mode,
    }


_RESOLVER = "stupidex.commands.session_commands.resolve_model_metadata"
_GET_CONFIG = "stupidex.commands.session_commands.get_config"
_DISCOVER = "stupidex.commands.session_commands.discover_provider_models"


class TestBuildModelPickerItems(unittest.TestCase):
    """Pure-function tests for the picker-item construction helper (scenarios 1-9)."""

    def _cfg(self, providers: dict) -> Config:
        return Config(providers=providers)

    # ------------------------------------------------------------------
    # Scenarios 1 + 2: happy paths
    # ------------------------------------------------------------------

    def test_happy_path_two_providers_one_model_each(self):
        """Scenario 1: two providers, one model each -- 2 picker items, fully labeled."""
        cfg = self._cfg(
            {
                "work-openai": {"models": {"gpt-4o": {}}},
                "anthropic-prod": {"models": {"claude-3-opus": {}}},
            }
        )

        def fake_resolver(alias: str, model_id: str) -> dict:
            if (alias, model_id) == ("work-openai", "gpt-4o"):
                return _meta(max_in=128000, max_out=16384, supports_vision=True)
            if (alias, model_id) == ("anthropic-prod", "claude-3-opus"):
                return _meta(max_in=200000, max_out=4096)
            raise AssertionError(f"unexpected resolver call: ({alias!r}, {model_id!r})")

        with patch(_RESOLVER, side_effect=fake_resolver) as mock:
            items = _build_model_picker_items(cfg)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].id, "work-openai/gpt-4o")
        self.assertEqual(items[0].label, "work-openai/gpt-4o [vision] [text] 128k→16k")
        self.assertEqual(items[1].id, "anthropic-prod/claude-3-opus")
        self.assertEqual(items[1].label, "anthropic-prod/claude-3-opus [text] 200k→4k")
        mock.assert_any_call("work-openai", "gpt-4o")
        mock.assert_any_call("anthropic-prod", "claude-3-opus")

    def test_covers_ae5_multiple_providers_multiple_models(self):
        """Scenario 2 (covers AE5): two providers, three models; badges + tokens on each."""
        cfg = self._cfg(
            {
                "work-openai": {"models": {"gpt-4o": {}, "gpt-4o-mini": {}}},
                "anthropic-prod": {"models": {"claude-3-opus": {}}},
            }
        )
        responses = {
            ("work-openai", "gpt-4o"): _meta(max_in=128000, max_out=16384, supports_vision=True),
            ("work-openai", "gpt-4o-mini"): _meta(max_in=128000, max_out=16384, supports_vision=True),
            ("anthropic-prod", "claude-3-opus"): _meta(max_in=200000, max_out=4096, supports_vision=True),
        }

        def fake_resolver(alias: str, model_id: str) -> dict:
            return responses[(alias, model_id)]

        with patch(_RESOLVER, side_effect=fake_resolver):
            items = _build_model_picker_items(cfg)

        self.assertEqual(len(items), 3)
        self.assertEqual(
            [item.id for item in items],
            [
                "work-openai/gpt-4o",
                "work-openai/gpt-4o-mini",
                "anthropic-prod/claude-3-opus",
            ],
        )
        # Every label carries the [vision] + [text] + token shorthand segments.
        for item in items:
            self.assertIn("[vision]", item.label)
            self.assertIn("[text]", item.label)
            self.assertIn("→", item.label)
            self.assertIn("k", item.label)

        self.assertEqual(items[0].label, "work-openai/gpt-4o [vision] [text] 128k→16k")
        self.assertEqual(items[1].label, "work-openai/gpt-4o-mini [vision] [text] 128k→16k")
        self.assertEqual(items[2].label, "anthropic-prod/claude-3-opus [vision] [text] 200k→4k")

    # ------------------------------------------------------------------
    # Scenarios 3 + 4: capability badges
    # ------------------------------------------------------------------

    def test_vision_badge_present_when_supported(self):
        """Scenario 3: supports_vision=True -> '[vision]' appears in label."""
        cfg = self._cfg({"p1": {"models": {"m1": {}}}})
        with patch(_RESOLVER, return_value=_meta(supports_vision=True)):
            items = _build_model_picker_items(cfg)
        self.assertEqual(len(items), 1)
        self.assertIn("[vision]", items[0].label)

    def test_vision_badge_absent_when_unsupported(self):
        """Scenario 3: supports_vision=False -> '[vision]' absent from label."""
        cfg = self._cfg({"p1": {"models": {"m1": {}}}})
        with patch(_RESOLVER, return_value=_meta(supports_vision=False)):
            items = _build_model_picker_items(cfg)
        self.assertEqual(len(items), 1)
        self.assertNotIn("[vision]", items[0].label)

    def test_text_badge_present_for_chat_mode(self):
        """Scenario 4: mode='chat' -> '[text]' appears in label."""
        cfg = self._cfg({"p1": {"models": {"m1": {}}}})
        with patch(_RESOLVER, return_value=_meta(mode="chat")):
            items = _build_model_picker_items(cfg)
        self.assertIn("[text]", items[0].label)

    def test_text_badge_present_for_completion_mode(self):
        """Scenario 4: mode='completion' -> '[text]' appears in label."""
        cfg = self._cfg({"p1": {"models": {"m1": {}}}})
        with patch(_RESOLVER, return_value=_meta(mode="completion")):
            items = _build_model_picker_items(cfg)
        self.assertIn("[text]", items[0].label)

    def test_text_badge_absent_for_embedding_mode(self):
        """Scenario 4: mode='embedding' -> '[text]' absent from label."""
        cfg = self._cfg({"p1": {"models": {"m1": {}}}})
        with patch(_RESOLVER, return_value=_meta(mode="embedding")):
            items = _build_model_picker_items(cfg)
        self.assertNotIn("[text]", items[0].label)

    # ------------------------------------------------------------------
    # Scenarios 5 + 6: token shorthand
    # ------------------------------------------------------------------

    def test_token_shorthand_rendered_when_both_int(self):
        """Scenario 5: max_input=128000, max_output=16384 -> '128k→16k' appended."""
        cfg = self._cfg({"p1": {"models": {"m1": {}}}})
        with patch(_RESOLVER, return_value=_meta(max_in=128000, max_out=16384)):
            items = _build_model_picker_items(cfg)
        self.assertIn("128k→16k", items[0].label)

    def test_token_shorthand_omitted_when_max_in_none(self):
        """Scenario 6: max_input_tokens=None -> no token shorthand on label."""
        cfg = self._cfg({"p1": {"models": {"m1": {}}}})
        with patch(_RESOLVER, return_value=_meta(max_in=None, max_out=16384)):
            items = _build_model_picker_items(cfg)
        self.assertNotIn("→", items[0].label)
        self.assertNotIn("None", items[0].label)

    def test_token_shorthand_omitted_when_max_out_none(self):
        """Scenario 6: max_output_tokens=None -> no token shorthand on label."""
        cfg = self._cfg({"p1": {"models": {"m1": {}}}})
        with patch(_RESOLVER, return_value=_meta(max_in=128000, max_out=None)):
            items = _build_model_picker_items(cfg)
        self.assertNotIn("→", items[0].label)
        self.assertNotIn("None", items[0].label)

    def test_token_shorthand_omitted_when_both_none(self):
        """Scenario 6: both limits None -> no token shorthand on label."""
        cfg = self._cfg({"p1": {"models": {"m1": {}}}})
        with patch(_RESOLVER, return_value=_meta(max_in=None, max_out=None)):
            items = _build_model_picker_items(cfg)
        self.assertNotIn("→", items[0].label)

    # ------------------------------------------------------------------
    # Scenario 7: empty models
    # ------------------------------------------------------------------

    def test_empty_models_dict_contributes_no_items(self):
        """Scenario 7: a provider with models={} contributes nothing; others still appear."""
        cfg = self._cfg(
            {
                "work-openai": {"models": {}},
                "anthropic-prod": {"models": {"claude-3-opus": {}}},
            }
        )
        with patch(_RESOLVER, return_value=_meta()):
            items = _build_model_picker_items(cfg)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "anthropic-prod/claude-3-opus")

    def test_all_providers_empty_models_produces_empty_list(self):
        """Scenario 7 (alt): every provider's models dict empty -> empty list (no exception)."""
        cfg = self._cfg(
            {
                "work-openai": {"models": {}},
                "local": {"models": {}},
            }
        )
        with patch(_RESOLVER) as mock_resolver:
            items = _build_model_picker_items(cfg)
        self.assertEqual(items, [])
        mock_resolver.assert_not_called()

    # ------------------------------------------------------------------
    # Scenario 8: id format
    # ------------------------------------------------------------------

    def test_id_format_is_alias_slash_model_with_no_badges(self):
        """Scenario 8: PickerItem.id is exactly 'alias/model' (no badges or tokens)."""
        cfg = self._cfg({"work-openai": {"models": {"gpt-4o": {}}}})
        with patch(
            _RESOLVER,
            return_value=_meta(max_in=128000, max_out=16384, supports_vision=True),
        ):
            items = _build_model_picker_items(cfg)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "work-openai/gpt-4o")
        # ID must be badge-free -- this is what `change_model` stores.
        self.assertNotIn("[", items[0].id)
        self.assertNotIn("→", items[0].id)

    # ------------------------------------------------------------------
    # Scenario 9: resolver integration
    # ------------------------------------------------------------------

    def test_resolver_called_with_alias_and_model_id(self):
        """Scenario 9: resolve_model_metadata is called with (alias, model_id) per entry."""
        cfg = self._cfg(
            {
                "work-openai": {"models": {"gpt-4o": {}, "gpt-4o-mini": {}}},
                "local": {"models": {"llama-70b": {}}},
            }
        )
        with patch(_RESOLVER, return_value=_meta()) as mock:
            _build_model_picker_items(cfg)

        mock.assert_any_call("work-openai", "gpt-4o")
        mock.assert_any_call("work-openai", "gpt-4o-mini")
        mock.assert_any_call("local", "llama-70b")
        self.assertEqual(mock.call_count, 3)

    # ------------------------------------------------------------------
    # Defensive: resolver failure
    # ------------------------------------------------------------------

    def test_resolver_exception_skips_model_keeps_others(self):
        """Defensive: a model whose resolver raises is skipped; the rest remain."""
        cfg = self._cfg(
            {
                "work-openai": {
                    "models": {"gpt-4o": {}, "broken-model": {}, "gpt-4o-mini": {}}
                }
            }
        )

        def fake_resolver(alias: str, model_id: str) -> dict:
            if model_id == "broken-model":
                raise RuntimeError("simulated resolver failure")
            return _meta()

        with patch(_RESOLVER, side_effect=fake_resolver):
            items = _build_model_picker_items(cfg)

        self.assertEqual(
            [item.id for item in items],
            ["work-openai/gpt-4o", "work-openai/gpt-4o-mini"],
        )

    def test_non_dict_provider_entry_is_skipped(self):
        """Defensive: a non-dict provider entry is skipped without raising."""
        cfg = self._cfg(
            {
                "broken": "not-a-dict",  # type: ignore[dict-item]
                "ok": {"models": {"m1": {}}},
            }
        )
        with patch(_RESOLVER, return_value=_meta()):
            items = _build_model_picker_items(cfg)
        self.assertEqual([item.id for item in items], ["ok/m1"])

    def test_non_dict_models_field_is_skipped(self):
        """Defensive: a provider whose 'models' field is not a dict is skipped."""
        cfg = self._cfg(
            {
                "broken": {"models": "not-a-dict"},  # type: ignore[dict-item]
                "ok": {"models": {"m1": {}}},
            }
        )
        with patch(_RESOLVER, return_value=_meta()):
            items = _build_model_picker_items(cfg)
        self.assertEqual([item.id for item in items], ["ok/m1"])


class TestBuildModelPickerItemsDiscovery(unittest.TestCase):
    """Hybrid fallback (R10): undeclared models trigger GET /models discovery."""

    def _cfg(self, providers: dict) -> Config:
        return Config(providers=providers)

    def test_empty_models_dict_triggers_discovery(self):
        """Provider with no declared models falls back to endpoint discovery."""
        cfg = self._cfg({
            "openai-prod": {
                "base_url": "https://api.openai.com/v1",
                "litellm_provider": "openai",
                "api_key": "sk-test",
            }
        })
        with (
            patch(_DISCOVER, return_value=["gpt-4o", "gpt-4o-mini"]),
            patch(_RESOLVER, return_value=_meta()),
        ):
            items = _build_model_picker_items(cfg)
        ids = [i.id for i in items]
        self.assertEqual(ids, ["openai-prod/gpt-4o", "openai-prod/gpt-4o-mini"])

    def test_declared_models_skip_discovery(self):
        """When models are declared, the GET /models endpoint is never hit."""
        cfg = self._cfg({
            "openai-prod": {
                "base_url": "https://api.openai.com/v1",
                "models": {"gpt-4o": {}},
            }
        })
        with patch(_DISCOVER) as mock_discover, patch(_RESOLVER, return_value=_meta()):
            _build_model_picker_items(cfg)
        mock_discover.assert_not_called()

    def test_discovery_returns_empty_skips_provider_silently(self):
        """Empty discovery result = no items for that provider, no raise."""
        cfg = self._cfg({
            "dead-endpoint": {
                "base_url": "http://localhost:9999/v1",
                "litellm_provider": "openai",
            },
            "ok": {"models": {"m1": {}}},
        })
        with (
            patch(_DISCOVER, return_value=[]),
            patch(_RESOLVER, return_value=_meta()),
        ):
            items = _build_model_picker_items(cfg)
        self.assertEqual([item.id for item in items], ["ok/m1"])

    def test_discovery_failure_swallowed_silently(self):
        """If discovery raises, that provider is skipped, others still appear."""
        cfg = self._cfg({
            "broken": {"base_url": "http://example.com"},
            "ok": {"models": {"m1": {}}},
        })
        with (
            patch(_DISCOVER, side_effect=RuntimeError("boom")),
            patch(_RESOLVER, return_value=_meta()),
        ):
            items = _build_model_picker_items(cfg)
        self.assertEqual([item.id for item in items], ["ok/m1"])


class TestFormatModelLabel(unittest.TestCase):
    """Direct unit tests for the label formatter (covers each branch combination)."""

    def test_no_badges_no_tokens(self):
        label = _format_model_label(
            "p1", "m1", _meta(supports_vision=False, mode="embedding")
        )
        self.assertEqual(label, "p1/m1")

    def test_vision_only(self):
        label = _format_model_label(
            "p1", "m1", _meta(supports_vision=True, mode="embedding")
        )
        self.assertEqual(label, "p1/m1 [vision]")

    def test_text_only(self):
        label = _format_model_label(
            "p1", "m1", _meta(supports_vision=False, mode="chat")
        )
        self.assertEqual(label, "p1/m1 [text]")

    def test_completion_text_only(self):
        label = _format_model_label(
            "p1", "m1", _meta(supports_vision=False, mode="completion")
        )
        self.assertEqual(label, "p1/m1 [text]")

    def test_tokens_only(self):
        label = _format_model_label(
            "p1",
            "m1",
            _meta(max_in=128000, max_out=16384, supports_vision=False, mode="embedding"),
        )
        self.assertEqual(label, "p1/m1 128k→16k")

    def test_full_label_with_all_segments(self):
        """Scenario 5 (alt): all optional segments appear in the expected order."""
        label = _format_model_label(
            "work-openai",
            "gpt-4o",
            _meta(max_in=128000, max_out=16384, supports_vision=True, mode="chat"),
        )
        self.assertEqual(label, "work-openai/gpt-4o [vision] [text] 128k→16k")

    def test_token_shorthand_sub_1000(self):
        """Sub-1000 token counts render as plain decimals (no 'k' suffix that would misstate magnitude)."""
        label = _format_model_label(
            "p1",
            "m1",
            _meta(
                max_in=500,
                max_out=200,
                supports_vision=False,
                mode="embedding",
            ),
        )
        self.assertEqual(label, "p1/m1 500→200")


class TestExecuteCommandEmptyConfig(unittest.TestCase):
    """Integration-style tests for the `/model` dispatch path on empty configs."""

    def test_empty_providers_notifies_warning_and_does_not_push(self):
        """Scenario 7: empty providers dict -> 'No models configured' notify, no push_screen."""
        cfg = Config(providers={})
        app = MagicMock()
        with patch(_GET_CONFIG, return_value=cfg):
            asyncio.run(execute_command(app, "/model"))
        app.notify.assert_called_once_with(
            "No models configured. Add providers to your config.",
            severity="warning",
        )
        app.push_screen.assert_not_called()

    def test_all_empty_model_dicts_notifies_warning(self):
        """Scenario 7 (alt): providers present but every models dict empty -> still notifies."""
        cfg = Config(
            providers={
                "work-openai": {"models": {}},
                "local": {"models": {}},
            }
        )
        app = MagicMock()
        with patch(_GET_CONFIG, return_value=cfg), patch(_RESOLVER) as mock_resolver:
            asyncio.run(execute_command(app, "/model"))
        # Resolver is never consulted when no models exist.
        mock_resolver.assert_not_called()
        app.notify.assert_called_once()
        self.assertEqual(
            app.notify.call_args.args[0],
            "No models configured. Add providers to your config.",
        )
        self.assertEqual(app.notify.call_args.kwargs["severity"], "warning")
        app.push_screen.assert_not_called()

    def test_non_empty_config_pushes_picker(self):
        """Happy path: a non-empty config pushes OptionPicker (resolver mocked)."""
        cfg = Config(providers={"p1": {"models": {"m1": {}}}})
        app = MagicMock()
        # `rerender_footer` is awaited inside `on_picked`; MagicMock is not awaitable.
        app.rerender_footer = AsyncMock()
        with patch(_GET_CONFIG, return_value=cfg), patch(
            _RESOLVER, return_value=_meta()
        ):
            asyncio.run(execute_command(app, "/model"))
        app.notify.assert_not_called()
        app.push_screen.assert_called_once()
        # The pushed OptionPicker carries one item with id 'p1/m1'.
        pushed_picker = app.push_screen.call_args.args[0]
        self.assertEqual(len(pushed_picker._items), 1)
        self.assertEqual(pushed_picker._items[0].id, "p1/m1")
        # on_picked callback is the second positional arg; invoke it to verify wiring.
        on_picked = app.push_screen.call_args.args[1]
        asyncio.run(on_picked("p1/m1"))
        app.sessions.change_model.assert_called_once_with("p1/m1")
        app.rerender_footer.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
