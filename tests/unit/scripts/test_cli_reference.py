"""Tests for cli-reference.md generator."""
import argparse

from scripts.gen_docs.cli_reference import build_cli_reference


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="test-prog", description="Test program")
    subparsers = parser.add_subparsers(dest="command")

    sub_hello = subparsers.add_parser("hello", help="Print hello")
    sub_hello.add_argument("--name", type=str, default="world")

    sub_count = subparsers.add_parser("count", help="Count things")
    sub_count.add_argument("--limit", type=int, default=10)

    return parser


def test_build_cli_reference_lists_subcommands() -> None:
    md = build_cli_reference(_make_parser())

    assert "hello" in md
    assert "count" in md
    assert "Print hello" in md
    assert "Count things" in md


def test_build_cli_reference_includes_prog_name() -> None:
    md = build_cli_reference(_make_parser())
    assert "test-prog" in md


def test_build_cli_reference_handles_parser_without_subcommands() -> None:
    parser = argparse.ArgumentParser(prog="empty")
    md = build_cli_reference(parser)
    # 例外を投げず、サブコマンドなしの旨を含む Markdown を返す
    assert "empty" in md
    assert "subcommand" in md.lower() or "no commands" in md.lower()


def test_build_cli_reference_escapes_command_names() -> None:
    parser = argparse.ArgumentParser(prog="escape-test")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("pipe|cmd", help="Pipe command")

    md = build_cli_reference(parser)

    assert r"`pipe\|cmd`" in md
    assert "`pipe|cmd`" not in md
