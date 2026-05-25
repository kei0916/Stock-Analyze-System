"""Packaging and dependency contract tests."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _pyproject() -> dict:
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())


def test_web_templates_and_static_are_packaged():
    data = _pyproject()
    package_data = data["tool"]["setuptools"]["package-data"]
    patterns = set(package_data["stock_analyze_system"])

    assert "web/templates/**/*.html" in patterns
    assert "web/static/*" in patterns


def test_weasyprint_dependency_matches_url_fetcher_api():
    data = _pyproject()
    deps = data["project"]["dependencies"]
    spec = next(dep for dep in deps if dep.startswith("weasyprint"))
    lower_bound = int(re.search(r">=(\d+)", spec).group(1))

    assert lower_bound >= 68
