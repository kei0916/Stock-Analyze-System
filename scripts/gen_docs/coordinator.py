"""Living Docs 生成パイプラインのオーケストレーション。

ステップ:
  1. `docs/generated/` と `docs-site/docs/` を rm -rf (clean 再生成)
  2. L1 生成物を `docs/generated/` に出力
  3. L2 (`docs/system-overview.md`, `docs/current-work.md`) を `docs-site/docs/` にコピー
  4. L1 を `docs-site/docs/generated/` にコピー
"""
from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

from scripts.gen_docs.cli_reference import build_cli_reference
from scripts.gen_docs.dependency_graph import build_dependency_graph
from scripts.gen_docs.module_index import build_module_index


@dataclass(frozen=True)
class GenContext:
    repo_root: Path
    package_path: Path
    cli_parser: argparse.ArgumentParser | None


def _clean(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_if_present(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


_CLI_REFERENCE_STUB = (
    "# CLI Reference — unavailable\n"
    "\n"
    "> このページは自動生成されますが、今回の生成では `cli.app:build_parser()` の\n"
    "> import に失敗したため CLI コマンド一覧を生成できませんでした。\n"
    "> `make docs` のログの WARNING を確認してください。\n"
)


def run_pipeline(ctx: GenContext) -> None:
    generated = ctx.repo_root / "docs" / "generated"
    site_docs = ctx.repo_root / "docs-site" / "docs"

    # 1. clean
    _clean(generated)
    _clean(site_docs)

    # 2. L1 を docs/generated/ に生成
    _write(generated / "module-index.md", build_module_index(ctx.package_path))
    _write(generated / "dependency-graph.md", build_dependency_graph(ctx.package_path))
    # cli-reference.md は sidebars.js が常に参照するため、parser 不在・生成失敗の
    # どちらでも必ずファイルを作る（stub）。欠落させると Docusaurus が
    # broken doc id でビルドに失敗する。
    cli_reference_md = _CLI_REFERENCE_STUB
    if ctx.cli_parser is not None:
        try:
            cli_reference_md = build_cli_reference(ctx.cli_parser)
        except Exception as exc:  # noqa: BLE001 — 生成失敗は warning のみで継続
            print(f"[gen_docs] WARNING: cli-reference generation failed: {exc}")
            cli_reference_md = _CLI_REFERENCE_STUB
    _write(generated / "cli-reference.md", cli_reference_md)

    # 3. L2 を docs-site/docs/ にコピー
    _copy_if_present(
        ctx.repo_root / "docs" / "system-overview.md",
        site_docs / "overview.md",
    )
    _copy_if_present(
        ctx.repo_root / "docs" / "current-work.md",
        site_docs / "current-work.md",
    )

    # 4. L1 を docs-site/docs/generated/ にコピー
    if generated.exists():
        for md in generated.glob("*.md"):
            _copy_if_present(md, site_docs / "generated" / md.name)
