"""Tests for multi-provider config in `Config` — U1 + U4 verification.

Covers R1, R2, R3, R4, R11, R12 (see
docs/plans/2026-06-18-001-feat-multi-provider-support-plan.md).

Pattern mirrors `tests/test_mcp_config.py`: construct `Config(...)`,
call `_validate_config(cfg)` directly, assert per-entry outcomes.
"""
import json
import os
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import stupidex.config as cfg_mod
from stupidex.config import (
    Config,
    ConfigManager,
    _deep_merge_provider_dict,
    _merge_from_env,
    _validate_config,
    get_model_for_tier,
)

_RESERVED_ENV_KEYS = (
    "STUPIDEX_DEFAULT_MODEL",
    "STUPIDEX_RAG_EMBEDDING_MODEL",
)


class TestProvidersConfigValidation(unittest.TestCase):
    """Scenario 1-8: pure-function validation of `providers[alias]` entries."""

    def setUp(self) -> None:
        # Never leak env state across tests.
        self._saved_env = {k: os.environ.pop(k, None) for k in _RESERVED_ENV_KEYS}

    def tearDown(self) -> None:
        for k, v in self._saved_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def test_two_valid_providers_load_cleanly(self):
        """Scenario 1: R1, R4 — api_key literal + api_key_env coexist."""
        providers = {
            "work-openai": {
                "base_url": "https://api.openai.com",
                "api_key": "sk-test",
                "litellm_provider": "openai",
                "models": {"gpt-4o": {}},
            },
            "anthropic-prod": {
                "api_key_env": "ANTHROPIC_KEY",
                "litellm_provider": "anthropic",
                "models": {"claude-3-opus": {}},
            },
        }
        cfg = Config(providers=providers)
        validated = _validate_config(cfg)
        self.assertIn("work-openai", validated.providers)
        self.assertIn("anthropic-prod", validated.providers)
        self.assertEqual(validated.providers["work-openai"]["api_key"], "sk-test")
        self.assertEqual(validated.providers["anthropic-prod"]["api_key_env"], "ANTHROPIC_KEY")

    def test_empty_providers_stays_empty(self):
        """Scenario 2: explicit empty dict is preserved (does NOT fall back to default_factory)."""
        cfg = Config(providers={})
        validated = _validate_config(cfg)
        self.assertEqual(validated.providers, {})

    def test_provider_alias_with_slash_is_skipped(self):
        """Scenario 3 (AE4): alias containing '/' breaks alias/model syntax → skip."""
        providers = {"work/openai": {"api_key": "sk-test"}, "ok-alias": {"api_key": "sk-test"}}
        cfg = Config(providers=providers)
        validated = _validate_config(cfg)
        self.assertNotIn("work/openai", validated.providers)
        self.assertIn("ok-alias", validated.providers)

    def test_both_api_key_and_api_key_env_drops_env_with_warning(self):
        """Scenario 4 (R4): literal api_key wins over api_key_env when both set."""
        cfg = Config(providers={"prov1": {"api_key": "sk-lit", "api_key_env": "ENV_NAME"}})
        validated = _validate_config(cfg)
        self.assertIn("api_key", validated.providers["prov1"])
        self.assertNotIn("api_key_env", validated.providers["prov1"])
        self.assertEqual(validated.providers["prov1"]["api_key"], "sk-lit")

    def test_non_dict_provider_entry_is_skipped(self):
        """Scenario 5: entry that isn't a dict is warn-and-skip."""
        cfg = Config(providers={"bad-prov": "not-a-dict", "good-prov": {"api_key": "sk"}})
        validated = _validate_config(cfg)
        self.assertNotIn("bad-prov", validated.providers)
        self.assertIn("good-prov", validated.providers)

    def test_unknown_model_override_field_is_dropped(self):
        """Scenario 6: override fields outside the allowed set are warn-and-drop per-field."""
        cfg = Config(
            providers={
                "work-openai": {
                    "models": {
                        "gpt-4o": {"cost_per_token": 0.001, "max_input_tokens": 32768},
                    }
                }
            }
        )
        validated = _validate_config(cfg)
        gpt4o = validated.providers["work-openai"]["models"]["gpt-4o"]
        self.assertNotIn("cost_per_token", gpt4o)
        self.assertEqual(gpt4o, {"max_input_tokens": 32768})

    def test_rag_embedding_defaults_and_field_absence(self):
        """Scenario 7: rag_embedding_model default; rag_embedding_provider field absent."""
        cfg = Config()
        self.assertEqual(cfg.rag_embedding_model, "fastembed/BAAI/bge-small-en-v1.5")
        self.assertFalse(hasattr(cfg, "rag_embedding_provider"))

    def test_reserved_fastembed_alias_is_rejected(self):
        """Scenario 8: alias literally 'fastembed' is reserved; warn-and-skip."""
        cfg = Config(providers={"fastembed": {"models": {"x": {}}}})
        validated = _validate_config(cfg)
        self.assertNotIn("fastembed", validated.providers)


class TestProvidersConfigMerge(unittest.TestCase):
    """Scenario 9 (R12): recursive deep-merge of providers.<alias>.models."""

    def test_models_subdict_recursively_merged(self):
        home = {"work-openai": {"models": {"gpt-4o": {}, "gpt-4o-mini": {}}}}
        project = {"work-openai": {"models": {"gpt-4o": {"max_input_tokens": 32768}}}}
        merged = _deep_merge_provider_dict(home, project)
        models = merged["work-openai"]["models"]
        self.assertIn("gpt-4o-mini", models)
        self.assertEqual(models["gpt-4o"], {"max_input_tokens": 32768})

    def test_home_only_entry_fields_preserved_when_project_adds_model(self):
        """R12: home-only fields (e.g. api_key) survive when project adds a new model."""
        home = {"work-openai": {"api_key": "sk-home", "models": {"gpt-4o": {}}}}
        project = {
            "work-openai": {
                "models": {"gpt-4o": {"max_input_tokens": 32768}, "gpt-4o-mini": {}}
            }
        }
        merged = _deep_merge_provider_dict(home, project)
        self.assertEqual(merged["work-openai"]["api_key"], "sk-home")
        self.assertIn("gpt-4o-mini", merged["work-openai"]["models"])

    def test_project_only_aliases_added(self):
        home = {"home-alias": {"api_key": "sk"}}
        project = {"project-alias": {"api_key": "sk2"}}
        merged = _deep_merge_provider_dict(home, project)
        self.assertIn("home-alias", merged)
        self.assertIn("project-alias", merged)

    def test_mcp_servers_still_shallow_merges_entry_fields(self):
        """mcp_servers reuses the same helper; old behavior preserved (no nested models)."""
        home = {"shared": {"command": "home-cmd"}, "home-only": {"command": "home-cmd"}}
        project = {"shared": {"command": "project-cmd"}}
        merged = _deep_merge_provider_dict(home, project)
        self.assertEqual(merged["shared"]["command"], "project-cmd")
        self.assertEqual(merged["home-only"]["command"], "home-cmd")


class TestProvidersConfigEnvOverride(unittest.TestCase):
    """Scenario 10: STUPIDEX_RAG_EMBEDDING_MODEL override still maps."""

    def test_rag_embedding_model_env_override(self):
        os.environ["STUPIDEX_RAG_EMBEDDING_MODEL"] = "work-openai/text-embedding-3-large"
        try:
            cfg = Config()
            merged = _merge_from_env(cfg)
            self.assertEqual(merged.rag_embedding_model, "work-openai/text-embedding-3-large")
        finally:
            del os.environ["STUPIDEX_RAG_EMBEDDING_MODEL"]


class TestProvidersConfigDefaults(unittest.TestCase):
    """Scenario 11, 12, 13, 14 (U4): defaults + first-run install."""

    def test_default_model_and_tier_models_emit_alias_model_strings(self):
        """Scenario 11: Config() defaults use the `alias/model` convention."""
        cfg = Config()
        self.assertEqual(cfg.default_model, "default/mimo-v2.5")
        for tier in ("tolo", "tainha", "papudo", "papaca"):
            self.assertEqual(cfg.tier_models[tier], "default/mimo-v2.5", f"tier {tier}")

    def test_default_providers_entry_has_url_and_model(self):
        """R11: shipping default seeds a `default` provider reproducing today's defaults."""
        cfg = Config()
        default = cfg.providers["default"]
        self.assertEqual(default["base_url"], "https://opencode.ai/zen/go/v1")
        self.assertEqual(default["litellm_provider"], "openai")
        self.assertIn("mimo-v2.5", default["models"])
        # No api_key/api_key_env shipped in the default — rely on litellm env detection.
        self.assertNotIn("api_key", default)
        self.assertNotIn("api_key_env", default)

    def test_first_run_install_seeds_default_provider_and_loads(self):
        """Scenario 12, covers F4: ensure_home_config() writes providers.default; load() returns defaults."""
        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir = Path(tmpdir_str)
            home_path = tmpdir / "config.json"
            home_agents = tmpdir / "agents"
            home_skills = tmpdir / "skills"

            with patch.object(cfg_mod, "HOME_CONFIG_DIR", tmpdir), \
                 patch.object(cfg_mod, "HOME_CONFIG_PATH", home_path), \
                 patch.object(cfg_mod, "HOME_AGENTS_DIR", home_agents), \
                 patch.object(cfg_mod, "HOME_SKILLS_DIR", home_skills), \
                 patch("stupidex.agents.seed_agents_dir"), \
                 patch("stupidex.agents.load_agents"), \
                 patch("stupidex.skills.seed_skills_dir"), \
                 patch("stupidex.skills.load_skills"), \
                 patch("stupidex.personality.load_personalities"):
                ConfigManager.reset()
                ConfigManager.ensure_home_config()

                # File was written and contains providers.default
                self.assertTrue(home_path.exists())
                with open(home_path) as f:
                    data = json.load(f)
                self.assertIn("providers", data)
                self.assertIn("default", data["providers"])
                self.assertEqual(
                    data["providers"]["default"]["base_url"],
                    "https://opencode.ai/zen/go/v1",
                )

                # ConfigManager.load() returns the seeded defaults (no env, no project file in tmpdir).
                ConfigManager.reset()
                cfg = ConfigManager.load()
                self.assertEqual(cfg.default_model, "default/mimo-v2.5")
                self.assertEqual(get_model_for_tier("tolo"), "default/mimo-v2.5")
                self.assertIn("default", cfg.providers)
                self.assertEqual(
                    cfg.providers["default"]["litellm_provider"], "openai"
                )

    def test_custom_tier_model_resolution_returns_string(self):
        """Scenario 13: tier_models.tolo set to a custom alias/model → get_model_for_tier returns it."""
        cfg = Config(tier_models={"tolo": "work-openai/gpt-4o-mini"})
        # Direct field access pins storage; tier resolution flows through get_model_for_tier via ConfigManager.
        self.assertEqual(cfg.tier_models["tolo"], "work-openai/gpt-4o-mini")
        # Wire it through the singleton path so get_model_for_tier sees the custom value.
        original_instance = ConfigManager._instance
        try:
            ConfigManager._instance = cfg
            self.assertEqual(get_model_for_tier("tolo"), "work-openai/gpt-4o-mini")
        finally:
            ConfigManager._instance = original_instance

    def test_tier_model_with_unknown_alias_stored_as_string(self):
        """Scenario 14: resolution failure is U3's concern; U1 just stores the string."""
        cfg = Config(tier_models={"tolo": "missing-alias/gpt-4o"})
        self.assertEqual(cfg.tier_models["tolo"], "missing-alias/gpt-4o")
        # And validation does not reject alias/model-style tier_model strings.
        validated = _validate_config(cfg)
        self.assertEqual(validated.tier_models["tolo"], "missing-alias/gpt-4o")


class TestProvidersConfigRoundtripDefaults(unittest.TestCase):
    """Direct mirror of the plan's verification one-liners."""

    def test_asdict_config_writes_providers(self):
        """ensure_home_config uses asdict(Config()); confirm providers round-trips."""
        data = asdict(Config())
        self.assertIn("providers", data)
        self.assertEqual(
            data["providers"]["default"]["base_url"], "https://opencode.ai/zen/go/v1"
        )
        self.assertNotIn("rag_embedding_provider", data)
        self.assertNotIn("base_url", data)
        self.assertNotIn("provider_api_type", data)


if __name__ == "__main__":
    unittest.main()
