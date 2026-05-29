"""app.py のテスト"""
import argparse

import pytest

from stock_analyze_system.cli import app as app_module
from stock_analyze_system.cli.app import build_parser
from stock_analyze_system.config import AppConfig


class TestBuildParser:
    def test_creates_parser(self):
        parser = build_parser()
        assert parser.prog == "stock-analyze"

    def test_global_json_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--json", "company", "search", "test"])
        assert args.json is True

    def test_no_command_defaults(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_company_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["company", "search", "test"])
        assert args.command == "company"

    def test_config_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "/tmp/test.yaml", "company", "search", "test"])
        assert args.config == "/tmp/test.yaml"

    def test_global_json_is_respected_when_followed_by_rag(self):
        parser = build_parser()
        args = parser.parse_args(["--json", "rag", "health"])
        assert args.json is True

    def test_rag_subcommand_json_works_alone(self):
        parser = build_parser()
        args = parser.parse_args(["rag", "--json", "health"])
        assert args.json is True

    def test_rag_subcommand_no_json_default_false(self):
        parser = build_parser()
        args = parser.parse_args(["rag", "health"])
        assert args.json is False


class TestMain:
    async def test_worker_uses_own_lifecycle(self, monkeypatch):
        config = AppConfig()
        handler_calls = []

        async def handler(args, cfg):
            handler_calls.append((args, cfg))

        args = argparse.Namespace(
            command="worker",
            config="unused.yaml",
            db_path=None,
            handler=handler,
        )

        class Parser:
            def parse_args(self):
                return args

        create_db_engine = pytest.fail

        monkeypatch.setattr(app_module, "build_parser", lambda: Parser())
        monkeypatch.setattr(app_module, "load_config", lambda path: config)
        monkeypatch.setattr(app_module, "create_db_engine", create_db_engine)

        await app_module.main()

        assert handler_calls == [(args, config)]

    async def test_main_initializes_file_logging_via_setup_logging(
        self, monkeypatch, tmp_path,
    ):
        """worker/serve でも setup_logging が呼ばれ data/logs/stock_analyze.log
        相当の FileHandler が wire される (回帰: cli/app.py が
        logging.basicConfig しか呼ばず stdout/stderr にしか出ていなかった)。"""
        config = AppConfig()
        config.logging.file = str(tmp_path / "stock_analyze.log")
        config.logging.level = "INFO"

        async def handler(args, cfg):
            return None

        args = argparse.Namespace(
            command="worker",
            config="unused.yaml",
            db_path=None,
            handler=handler,
        )

        class Parser:
            def parse_args(self):
                return args

        captured: list = []

        def fake_setup_logging(logging_config):
            captured.append(logging_config)

        monkeypatch.setattr(app_module, "build_parser", lambda: Parser())
        monkeypatch.setattr(app_module, "load_config", lambda path: config)
        monkeypatch.setattr(app_module, "setup_logging", fake_setup_logging)

        await app_module.main()

        assert captured == [config.logging]

    async def test_exits_with_handler_return_code(self, monkeypatch, tmp_path):
        async def handler(args, services):
            return 7

        class Parser:
            def parse_args(self):
                return argparse.Namespace(
                    command="company",
                    config="unused.yaml",
                    db_path=str(tmp_path / "test.db"),
                    handler=handler,
                )

        cfg = AppConfig()
        cfg.database.path = str(tmp_path / "ignored.db")
        monkeypatch.setattr(app_module, "build_parser", lambda: Parser())
        monkeypatch.setattr(app_module, "load_config", lambda path: cfg)

        with pytest.raises(SystemExit) as exc_info:
            await app_module.main()

        assert exc_info.value.code == 7
