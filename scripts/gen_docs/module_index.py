"""module-index.md 生成器。

`src/stock_analyze_system/` 配下を走査し、トップレベルモジュールの一覧を
Markdown テーブルで返す。
"""
from __future__ import annotations

from pathlib import Path


EXCLUDED = {"__pycache__", ".egg-info"}


def _is_python_module(path: Path) -> bool:
    return path.is_dir() and (path / "__init__.py").exists()


def _count_loc(path: Path) -> int:
    """配下の .py ファイルの実行コード行数を概算する (空行とコメントを除く)。"""
    total = 0
    for py in path.rglob("*.py"):
        if any(part in EXCLUDED for part in py.parts):
            continue
        for line in py.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                total += 1
    return total


def _count_files(path: Path) -> int:
    return sum(
        1
        for py in path.rglob("*.py")
        if not any(part in EXCLUDED for part in py.parts)
    )


def build_module_index(package_root: Path) -> str:
    """与えられたパッケージルート直下のモジュール一覧 Markdown を返す。"""
    rows: list[tuple[str, int, int, str]] = []
    for child in sorted(package_root.iterdir()):
        if child.name in EXCLUDED:
            continue
        if not _is_python_module(child):
            continue
        rel = f"{package_root.name}/{child.name}"
        files = _count_files(child)
        loc = _count_loc(child)
        readme = f"[README]({rel}/README.md)"
        rows.append((child.name, files, loc, readme))

    lines: list[str] = []
    lines.append(f"# Module Index — `{package_root.name}`")
    lines.append("")
    lines.append("| Module | Files | LOC | README |")
    lines.append("|--------|------:|----:|--------|")
    for name, files, loc, readme in rows:
        lines.append(f"| `{name}` | {files} | {loc} | {readme} |")
    lines.append("")
    return "\n".join(lines)
