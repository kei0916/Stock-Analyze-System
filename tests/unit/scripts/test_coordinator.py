"""Tests for coordinator: clean → generate → copy pipeline."""
from pathlib import Path

import pytest

from scripts.gen_docs.coordinator import GenContext, run_pipeline


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """疑似 repo: src/<pkg>, docs/, docs-site/docs/ を持つ"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "docs").mkdir()
    (repo / "docs-site").mkdir()
    (repo / "src").mkdir()

    pkg = repo / "src" / "stock_analyze_system"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    cli = pkg / "cli"
    cli.mkdir()
    (cli / "__init__.py").write_text("")
    (cli / "app.py").write_text("def f():\n    return 1\n")

    return repo


def test_run_pipeline_creates_l1_generated_dir(fake_repo: Path) -> None:
    ctx = GenContext(
        repo_root=fake_repo,
        package_path=fake_repo / "src" / "stock_analyze_system",
        cli_parser=None,  # cli_reference は parser=None でも stub を生成する
    )
    run_pipeline(ctx)

    generated = fake_repo / "docs" / "generated"
    assert (generated / "module-index.md").exists()
    assert (generated / "dependency-graph.md").exists()


def test_run_pipeline_writes_cli_reference_stub_when_parser_is_none(
    fake_repo: Path,
) -> None:
    """parser が None でも cli-reference.md は必ず生成される（stub）。

    sidebars.js は `generated/cli-reference` を常に参照するため、ファイルが
    無いと Docusaurus が broken doc id でビルドに失敗する。欠落させず、
    生成不能の旨を本文に書いた stub を出す。
    """
    ctx = GenContext(
        repo_root=fake_repo,
        package_path=fake_repo / "src" / "stock_analyze_system",
        cli_parser=None,
    )
    run_pipeline(ctx)

    cli_ref = fake_repo / "docs" / "generated" / "cli-reference.md"
    assert cli_ref.exists()
    body = cli_ref.read_text()
    assert body.startswith("# ")
    # 生成不能であることが読み手に分かる
    assert "unavailable" in body.lower() or "生成できません" in body


def test_run_pipeline_cleans_stale_files(fake_repo: Path) -> None:
    """前回実行で残った生成物が削除される。"""
    stale = fake_repo / "docs" / "generated"
    stale.mkdir()
    (stale / "stale.md").write_text("stale content")

    site_docs = fake_repo / "docs-site" / "docs"
    site_docs.mkdir()
    (site_docs / "old.md").write_text("old")

    ctx = GenContext(
        repo_root=fake_repo,
        package_path=fake_repo / "src" / "stock_analyze_system",
        cli_parser=None,
    )
    run_pipeline(ctx)

    # 古いファイルは消える
    assert not (stale / "stale.md").exists()
    assert not (site_docs / "old.md").exists()


def test_run_pipeline_copies_l2_overview_when_present(fake_repo: Path) -> None:
    overview = fake_repo / "docs" / "system-overview.md"
    overview.write_text("# Overview\n\ncontent\n")

    ctx = GenContext(
        repo_root=fake_repo,
        package_path=fake_repo / "src" / "stock_analyze_system",
        cli_parser=None,
    )
    run_pipeline(ctx)

    copied = fake_repo / "docs-site" / "docs" / "overview.md"
    assert copied.exists()
    assert "# Overview" in copied.read_text()
