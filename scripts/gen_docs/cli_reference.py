"""cli-reference.md 生成器。

argparse の `ArgumentParser` を受け取り、サブパーサーの一覧を Markdown
テーブルで出力する。プロジェクトの `cli/app.py:build_parser()` をそのまま
渡せる前提。
"""
from __future__ import annotations

import argparse


def _markdown_table_text(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", " ").strip()


def _find_subparsers_action(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction | None:
    for action in parser._actions:  # noqa: SLF001 — argparse 内部 API 利用
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            return action
    return None


def build_cli_reference(parser: argparse.ArgumentParser) -> str:
    """ArgumentParser からサブコマンド一覧 Markdown を生成する。"""
    prog = parser.prog or "<unknown>"
    description = parser.description or ""

    lines: list[str] = []
    lines.append(f"# CLI Reference — `{prog}`")
    lines.append("")
    if description:
        lines.append(description)
        lines.append("")

    subparsers_action = _find_subparsers_action(parser)
    if subparsers_action is None or not subparsers_action.choices:
        lines.append("_No subcommands defined._")
        lines.append("")
        return "\n".join(lines)

    lines.append("| Command | Description |")
    lines.append("|---------|-------------|")

    # subparsers_action.choices: dict[str, ArgumentParser]
    # subparsers_action._choices_actions: 各サブパーサの help を持つ
    help_by_name = {
        a.dest: a.help or "" for a in subparsers_action._choices_actions  # noqa: SLF001
    }
    for name in sorted(subparsers_action.choices.keys()):
        sub_parser = subparsers_action.choices[name]
        help_text = help_by_name.get(name) or sub_parser.description or ""
        # Markdown の縦棒をエスケープ
        command = _markdown_table_text(name)
        help_text = _markdown_table_text(help_text)
        lines.append(f"| `{command}` | {help_text} |")

    lines.append("")
    return "\n".join(lines)
