"""Packaging and dependency contract tests."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.version import Version


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


def test_security_sensitive_dependency_floors_are_pinned_to_fixed_versions():
    data = _pyproject()
    deps = data["project"]["dependencies"]

    expected = {
        "idna": Version("3.15"),
        "pypdf": Version("6.10.2"),
        "urllib3": Version("2.7.0"),
    }
    for package, minimum in expected.items():
        spec = next(dep for dep in deps if dep.startswith(f"{package}>="))
        match = re.search(r">=([0-9][^,<;\s]*)", spec)
        assert match is not None, spec
        assert Version(match.group(1)) >= minimum
