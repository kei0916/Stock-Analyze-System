"""Tests for dependency-graph.md generator."""
from pathlib import Path

import pytest

from scripts.gen_docs.dependency_graph import build_dependency_graph


@pytest.fixture
def fake_pkg(tmp_path: Path) -> Path:
    pkg = tmp_path / "stock_analyze_system"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    cli = pkg / "cli"
    cli.mkdir()
    (cli / "__init__.py").write_text("")
    (cli / "app.py").write_text(
        "from stock_analyze_system.services import rag_service\n"
        "from stock_analyze_system.shared import logger\n"
        "import os\n"
        "from typing import Any\n"
    )

    services = pkg / "services"
    services.mkdir()
    (services / "__init__.py").write_text("")
    (services / "rag_service.py").write_text(
        "from stock_analyze_system.shared import logger\n"
    )

    shared = pkg / "shared"
    shared.mkdir()
    (shared / "__init__.py").write_text("")
    (shared / "logger.py").write_text("")

    return pkg


def test_build_dependency_graph_emits_mermaid(fake_pkg: Path) -> None:
    md = build_dependency_graph(fake_pkg)
    assert "```mermaid" in md
    assert "graph" in md or "flowchart" in md


def test_build_dependency_graph_captures_internal_edges(fake_pkg: Path) -> None:
    md = build_dependency_graph(fake_pkg)
    # cli -> services
    assert "cli --> services" in md or "cli-->services" in md
    # cli -> shared
    assert "cli --> shared" in md or "cli-->shared" in md
    # services -> shared
    assert "services --> shared" in md or "services-->shared" in md


def test_build_dependency_graph_ignores_external_imports(fake_pkg: Path) -> None:
    md = build_dependency_graph(fake_pkg)
    # 標準ライブラリは出さない
    assert "os" not in md.replace("# ", "").replace("```", "").replace("graph", "")
    # typing も出さない
    assert " --> typing" not in md


def test_build_dependency_graph_captures_package_root_imports(fake_pkg: Path) -> None:
    repositories = fake_pkg / "repositories"
    repositories.mkdir()
    (repositories / "__init__.py").write_text("")
    cli_extra = fake_pkg / "cli" / "extra.py"
    cli_extra.write_text("from stock_analyze_system import repositories\n")

    md = build_dependency_graph(fake_pkg)

    assert "cli --> repositories" in md or "cli-->repositories" in md
