"""serve CLI tests"""
import argparse

import pytest

from stock_analyze_system.cli.serve import register_parser


class TestPortDefault:
    def test_port_not_specified_uses_default(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        args = parser.parse_args(["serve"])
        assert args.port is None

    def test_port_explicit_value(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        args = parser.parse_args(["serve", "--port", "3000"])
        assert args.port == 3000


class TestPortValidation:
    def test_port_negative_rejected(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        with pytest.raises(SystemExit):
            parser.parse_args(["serve", "--port", "-1"])

    def test_port_zero_rejected(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        with pytest.raises(SystemExit):
            parser.parse_args(["serve", "--port", "0"])

    def test_port_too_large_rejected(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        with pytest.raises(SystemExit):
            parser.parse_args(["serve", "--port", "70000"])

    def test_port_valid_range(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register_parser(sub)
        args = parser.parse_args(["serve", "--port", "8080"])
        assert args.port == 8080


class TestWebAppFactoryImport:
    """serve.py が参照する web:create_app が import 可能なこと"""

    def test_web_app_factory_importable(self):
        from stock_analyze_system.web import create_app
        assert callable(create_app)
