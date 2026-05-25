"""設定管理のテスト"""
import os
from pathlib import Path
from unittest.mock import patch

from stock_analyze_system.config import (
    AppConfig,
    DatabaseConfig,
    PageIndexConfig,
    load_config,
    _load_dotenv,
    _merge_dict_to_dataclass,
    _resolve_project_path,
)


class TestMergeDictToDataclass:
    def test_empty_dict(self):
        result = _merge_dict_to_dataclass(DatabaseConfig, {})
        assert result.path == "data/stock_analyze.db"

    def test_none_input(self):
        result = _merge_dict_to_dataclass(DatabaseConfig, None)
        assert result.path == "data/stock_analyze.db"

    def test_valid_fields(self):
        result = _merge_dict_to_dataclass(DatabaseConfig, {"path": "/tmp/test.db"})
        assert result.path == "/tmp/test.db"

    def test_unknown_fields_ignored(self):
        result = _merge_dict_to_dataclass(DatabaseConfig, {"path": "/tmp/t.db", "unknown": 42})
        assert result.path == "/tmp/t.db"


class TestResolveProjectPath:
    def test_returns_absolute_path(self):
        result = _resolve_project_path("config/settings.yaml")
        assert result.is_absolute()
        assert result.name == "settings.yaml"


class TestLoadDotenv:
    def test_loads_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('TEST_VAR_XYZ="hello"\n')
        os.environ.pop("TEST_VAR_XYZ", None)
        _load_dotenv(env_file)
        assert os.environ.get("TEST_VAR_XYZ") == "hello"
        os.environ.pop("TEST_VAR_XYZ", None)

    def test_does_not_overwrite_existing(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR_XYZ=new\n")
        os.environ["TEST_VAR_XYZ"] = "old"
        _load_dotenv(env_file)
        assert os.environ["TEST_VAR_XYZ"] == "old"
        os.environ.pop("TEST_VAR_XYZ", None)

    def test_skips_comments_and_blanks(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nKEY=value\n")
        os.environ.pop("KEY", None)
        _load_dotenv(env_file)
        assert os.environ.get("KEY") == "value"
        os.environ.pop("KEY", None)

    def test_missing_file_no_error(self, tmp_path):
        _load_dotenv(tmp_path / "nonexistent")  # should not raise


class TestLoadConfig:
    def test_default_config(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        config = load_config(yaml_path)
        assert isinstance(config, AppConfig)
        assert config.database.path == "data/stock_analyze.db"
        assert config.llm.backend == "llamacpp"
        assert config.llm.base_url == "http://localhost:8080/v1"
        assert config.llm.model == "openai/Qwen3.6-27B-Q4_K_M.gguf"
        assert config.llm.model_quality == "openai/Qwen3.6-27B-Q4_K_M.gguf"
        assert config.llm.enable_thinking is False
        assert config.sec_edgar.rate_limit_rps == 10

    def test_repo_default_settings_bind_to_localhost(self):
        config = load_config(_resolve_project_path("config/settings.yaml"))
        assert config.web.host == "127.0.0.1"

    def test_yaml_override(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("database:\n  path: /custom/path.db\n")
        config = load_config(yaml_path)
        assert config.database.path == "/custom/path.db"

    def test_env_var_override(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        with patch.dict(os.environ, {"SEC_EDGAR_EMAIL": "test@example.com"}):
            config = load_config(yaml_path)
            assert config.sec_edgar.email == "test@example.com"

    def test_loads_dotenv_file_for_backward_compatibility(self, monkeypatch, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text("SEC_EDGAR_EMAIL=dotenv@example.com\n")

        with patch.dict(os.environ, {"STOCK_ANALYZE_LOAD_DOTENV": "1"}, clear=False):
            os.environ.pop("SEC_EDGAR_EMAIL", None)
            monkeypatch.setattr(
                "stock_analyze_system.config._resolve_project_path",
                lambda relative: dotenv_path if relative == ".env" else Path(relative),
            )

            config = load_config(yaml_path)

        assert config.sec_edgar.email == "dotenv@example.com"

    def test_can_disable_dotenv_loading_for_managed_secrets(self, monkeypatch, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text("SEC_EDGAR_EMAIL=dotenv@example.com\n")

        with patch.dict(os.environ, {"STOCK_ANALYZE_LOAD_DOTENV": "0"}):
            os.environ.pop("SEC_EDGAR_EMAIL", None)
            monkeypatch.setattr(
                "stock_analyze_system.config._resolve_project_path",
                lambda relative: dotenv_path if relative == ".env" else Path(relative),
            )

            config = load_config(yaml_path)

        assert config.sec_edgar.email == ""

    def test_env_var_edinet(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        with patch.dict(os.environ, {"EDINET_API_KEY": "mykey"}):
            config = load_config(yaml_path)
            assert config.edinet.api_key == "mykey"

    def test_env_var_fmp(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        with patch.dict(os.environ, {"FMP_API_KEY": "fmpkey"}):
            config = load_config(yaml_path)
            assert config.fmp.api_key == "fmpkey"

    def test_pageindex_config_exists(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        config = load_config(yaml_path)
        assert isinstance(config.pageindex, PageIndexConfig)
        assert config.pageindex.enabled is False

    def test_missing_yaml_file(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert isinstance(config, AppConfig)


def test_google_sheets_defaults(config):
    assert config.google_sheets.enabled is False
    assert config.google_sheets.spreadsheet_id == ""
    assert config.google_sheets.worksheet_name == "test"
    assert config.google_sheets.credentials_json_path == ""
    assert config.google_sheets.credentials_json_env == "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON"
    assert config.google_sheets.batch_size == 500
    assert config.google_sheets.poll_interval_seconds == 30
    assert config.google_sheets.max_poll_attempts == 10


def test_google_sheets_env_overrides(monkeypatch):
    from stock_analyze_system.config import load_config

    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "sheet-123")
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH", "/tmp/sa.json")
    monkeypatch.setenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')

    cfg = load_config("does-not-exist.yaml")

    assert cfg.google_sheets.spreadsheet_id == "sheet-123"
    assert cfg.google_sheets.credentials_json_path == "/tmp/sa.json"
    assert cfg.google_sheets.credentials_json == '{"type":"service_account"}'
