"""Tests for MCP server config validation in Config (U7)."""
import unittest
from dataclasses import asdict

from stupidex.config import Config, _validate_config


class TestMCPConfigValidation(unittest.TestCase):
    def test_valid_mcp_servers_load_correctly(self):
        servers = {"my-server": {"command": "node", "args": ["server.js"]}}
        cfg = Config(mcp_servers=servers)
        validated = _validate_config(cfg)
        self.assertEqual(validated.mcp_servers, servers)

    def test_empty_mcp_servers_defaults_to_empty_dict(self):
        cfg = Config(mcp_servers={})
        validated = _validate_config(cfg)
        self.assertEqual(validated.mcp_servers, {})

    def test_mcp_servers_not_a_dict_defaults_to_empty(self):
        cfg = Config()
        values = asdict(cfg)
        values["mcp_servers"] = "not-a-dict"
        raw = Config(**values)
        validated = _validate_config(raw)
        self.assertEqual(validated.mcp_servers, {})

    def test_invalid_server_name_with_underscores_is_rejected(self):
        servers = {"bad_name": {"command": "node"}, "good-name": {"command": "node"}}
        cfg = Config(mcp_servers=servers)
        validated = _validate_config(cfg)
        self.assertNotIn("bad_name", validated.mcp_servers)
        self.assertIn("good-name", validated.mcp_servers)

    def test_invalid_server_name_with_special_chars_is_rejected(self):
        servers = {"bad@name!": {"command": "node"}, "ok": {"command": "node"}}
        cfg = Config(mcp_servers=servers)
        validated = _validate_config(cfg)
        self.assertNotIn("bad@name!", validated.mcp_servers)
        self.assertIn("ok", validated.mcp_servers)

    def test_server_config_not_a_dict_is_skipped(self):
        servers = {"bad-server": "not-a-dict", "good-server": {"command": "node"}}
        cfg = Config(mcp_servers=servers)
        validated = _validate_config(cfg)
        self.assertNotIn("bad-server", validated.mcp_servers)
        self.assertIn("good-server", validated.mcp_servers)

    def test_deep_merge_project_overrides_same_name_home_entry(self):
        home_servers = {"shared": {"command": "home-cmd"}}
        project_servers = {"shared": {"command": "project-cmd"}}

        merged = {**{}, **home_servers}
        merged = {**merged, **project_servers}

        cfg = Config(mcp_servers=merged)
        validated = _validate_config(cfg)
        self.assertEqual(validated.mcp_servers["shared"]["command"], "project-cmd")

    def test_deep_merge_home_entries_not_in_project_are_preserved(self):
        home_servers = {"home-only": {"command": "home-cmd"}, "shared": {"command": "home-cmd"}}
        project_servers = {"shared": {"command": "project-cmd"}}

        merged = {**{}, **home_servers}
        merged = {**merged, **project_servers}

        cfg = Config(mcp_servers=merged)
        validated = _validate_config(cfg)
        self.assertIn("home-only", validated.mcp_servers)
        self.assertEqual(validated.mcp_servers["home-only"]["command"], "home-cmd")
        self.assertEqual(validated.mcp_servers["shared"]["command"], "project-cmd")

    def test_command_must_be_string_for_stdio_server(self):
        servers = {"bad": {"command": ["python", "-m", "foo"]}, "good": {"command": "python"}}
        cfg = Config(mcp_servers=servers)
        validated = _validate_config(cfg)
        self.assertNotIn("bad", validated.mcp_servers)
        self.assertIn("good", validated.mcp_servers)

    def test_args_must_be_list(self):
        servers = {"bad": {"command": "python", "args": "not-a-list"}, "good": {"command": "python", "args": ["-m", "foo"]}}
        cfg = Config(mcp_servers=servers)
        validated = _validate_config(cfg)
        self.assertNotIn("bad", validated.mcp_servers)
        self.assertIn("good", validated.mcp_servers)

    def test_command_validation_skipped_for_url_servers(self):
        servers = {"sse": {"url": "http://localhost:3000"}}
        cfg = Config(mcp_servers=servers)
        validated = _validate_config(cfg)
        self.assertIn("sse", validated.mcp_servers)


if __name__ == "__main__":
    unittest.main()
