"""`python -m scripts.gen_docs` エントリポイント。

repo root から実行する想定。`stock_analyze_system.cli.app:build_parser` の
import に失敗した場合は warning を出し、parser=None で続行する。
cli-reference.md は coordinator 側で stub が必ず生成されるため欠落しない。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.gen_docs.coordinator import GenContext, run_pipeline


def _load_cli_parser() -> argparse.ArgumentParser | None:
    try:
        from stock_analyze_system.cli.app import build_parser  # type: ignore

        return build_parser()
    except Exception as exc:  # noqa: BLE001
        print(f"[gen_docs] WARNING: failed to import cli.app: {exc}")
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gen_docs")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="repo の root path (default: 現在のディレクトリ)",
    )
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root.resolve()
    package_path = repo_root / "src" / "stock_analyze_system"
    if not package_path.exists():
        print(f"[gen_docs] ERROR: package not found at {package_path}", file=sys.stderr)
        return 1

    ctx = GenContext(
        repo_root=repo_root,
        package_path=package_path,
        cli_parser=_load_cli_parser(),
    )
    run_pipeline(ctx)
    print(
        f"[gen_docs] OK: generated to {repo_root / 'docs' / 'generated'} "
        f"and {repo_root / 'docs-site' / 'docs'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
