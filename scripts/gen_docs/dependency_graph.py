"""dependency-graph.md 生成器。

パッケージ配下の Python ファイルを ast でパースし、同一パッケージ内の
モジュール間 import 関係を Mermaid flowchart として出力する。
"""
from __future__ import annotations

import ast
from pathlib import Path


EXCLUDED = {"__pycache__"}


def _top_level_module_of(rel_parts: tuple[str, ...]) -> str | None:
    """('cli', 'app.py') → 'cli'。深さ 0 のファイル (config.py 等) は None。"""
    if len(rel_parts) < 2:
        return None
    return rel_parts[0]


def _internal_target(import_name: str, package_name: str) -> str | None:
    """import 文の対象が自パッケージ配下なら、トップレベルモジュール名を返す。

    例: `stock_analyze_system.services.rag_service` (package_name='stock_analyze_system')
        → 'services'
    """
    parts = import_name.split(".")
    if parts[0] != package_name or len(parts) < 2:
        return None
    return parts[1]


def _extract_imports(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None and node.level == 0:
                names.append(node.module)
                names.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def build_dependency_graph(package_root: Path) -> str:
    """同一パッケージ内のモジュール間依存を Mermaid 図として返す。"""
    package_name = package_root.name
    edges: set[tuple[str, str]] = set()
    nodes: set[str] = set()

    for py in package_root.rglob("*.py"):
        if any(part in EXCLUDED for part in py.parts):
            continue
        rel = py.relative_to(package_root)
        source_module = _top_level_module_of(rel.parts)
        if source_module is None:
            continue
        nodes.add(source_module)
        try:
            src_text = py.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for imp in _extract_imports(src_text):
            target = _internal_target(imp, package_name)
            if target is None or target == source_module:
                continue
            nodes.add(target)
            edges.add((source_module, target))

    lines: list[str] = []
    lines.append(f"# Dependency Graph — `{package_name}`")
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart LR")
    for node in sorted(nodes):
        lines.append(f"  {node}")
    for src, dst in sorted(edges):
        lines.append(f"  {src} --> {dst}")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)
