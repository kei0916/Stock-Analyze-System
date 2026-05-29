"""Tests for module-index.md generator."""
from pathlib import Path

import pytest

from scripts.gen_docs.module_index import build_module_index


@pytest.fixture
def fake_src(tmp_path: Path) -> Path:
    """src ライクなディレクトリを作って返す。
    パッケージルート (__init__.py) と 2 つのモジュール (cli, services) を含む。
    """
    pkg = tmp_path / "stock_analyze_system"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "config.py").write_text("X = 1\n")

    cli = pkg / "cli"
    cli.mkdir()
    (cli / "__init__.py").write_text("")
    (cli / "app.py").write_text("def f():\n    return 1\n")

    services = pkg / "services"
    services.mkdir()
    (services / "__init__.py").write_text("")
    (services / "rag_service.py").write_text(
        "class R:\n"
        "    pass\n"
        "def helper():\n"
        "    return 'ok'\n"
    )

    return pkg


def test_build_module_index_lists_top_level_modules(fake_src: Path) -> None:
    md = build_module_index(fake_src)

    # マークダウン本文に各モジュール名と相対パスが含まれる
    assert "cli" in md
    assert "services" in md
    # 行数 (LOC) も含まれる
    assert "LOC" in md or "loc" in md.lower()
    # マークダウンテーブルとして整形されている
    assert "|" in md


def test_build_module_index_excludes_pycache(fake_src: Path) -> None:
    (fake_src / "__pycache__").mkdir()
    (fake_src / "__pycache__" / "junk.pyc").write_bytes(b"")

    md = build_module_index(fake_src)

    assert "__pycache__" not in md


def test_build_module_index_returns_markdown_with_header(fake_src: Path) -> None:
    md = build_module_index(fake_src)

    assert md.startswith("# ")
    assert md.endswith("\n")
