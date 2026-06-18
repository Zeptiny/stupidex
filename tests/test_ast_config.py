import os
from unittest import mock

from stupidex.config import AST_INDEX_DB, PROJECT_AST_DIR, Config, ConfigManager, get_config


def test_ast_path_constants():
    assert PROJECT_AST_DIR == ".stupidex/ast"
    assert AST_INDEX_DB == "symbols.db"


def test_default_ast_max_file_size():
    ConfigManager.reset()
    cfg = Config()
    assert cfg.ast_max_file_size == 1_048_576


def test_config_loads_default_ast_max_file_size():
    ConfigManager.reset()
    with mock.patch("stupidex.config._load_json", return_value={}):
        cfg = get_config()
    assert cfg.ast_max_file_size == 1_048_576


def test_env_override_ast_max_file_size():
    ConfigManager.reset()
    with (
        mock.patch.dict(os.environ, {"STUPIDEX_AST_MAX_FILE_SIZE": "256000"}),
        mock.patch("stupidex.config._load_json", return_value={}),
    ):
        cfg = get_config()
    assert cfg.ast_max_file_size == 256000


def test_validate_clamps_non_positive_ast_max_file_size():
    cfg = Config(ast_max_file_size=-1)
    ConfigManager.reset()
    with mock.patch("stupidex.config._load_json", return_value={}):
        ConfigManager._instance = None
        from stupidex.config import _validate_config

        validated = _validate_config(cfg)
    assert validated.ast_max_file_size == 1_048_576


def test_validate_clamps_zero_ast_max_file_size():
    cfg = Config(ast_max_file_size=0)
    ConfigManager.reset()
    from stupidex.config import _validate_config

    validated = _validate_config(cfg)
    assert validated.ast_max_file_size == 1_048_576


def test_invalid_type_ast_max_file_size_falls_back():
    cfg = Config(ast_max_file_size="not_an_int")
    ConfigManager.reset()
    from stupidex.config import _validate_config

    validated = _validate_config(cfg)
    assert validated.ast_max_file_size == 1_048_576
