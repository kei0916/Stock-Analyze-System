"""Tests for `python -m scripts.gen_docs` entrypoint."""
from pathlib import Path

from scripts.gen_docs import __main__ as gen_main


def test_main_runs_pipeline_with_repo_root(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    package = repo / "src" / "stock_analyze_system"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")

    calls = []
    monkeypatch.setattr(gen_main, "_load_cli_parser", lambda: None)
    monkeypatch.setattr(gen_main, "run_pipeline", lambda ctx: calls.append(ctx))

    result = gen_main.main(["--repo-root", str(repo)])

    assert result == 0
    assert len(calls) == 1
    assert calls[0].repo_root == repo.resolve()
    assert calls[0].package_path == package.resolve()
    assert calls[0].cli_parser is None


def test_main_returns_error_when_package_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    result = gen_main.main(["--repo-root", str(repo)])

    assert result == 1
