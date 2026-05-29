"""Direct PageIndex import compatibility tests."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest


def _pageindex_utils_available() -> bool:
    try:
        return importlib.util.find_spec("pageindex.utils") is not None
    except ModuleNotFoundError:
        return False


def test_direct_pageindex_import_works_without_importing_app_first():
    if not _pageindex_utils_available():
        pytest.skip("optional PageIndex package is not installed")
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["PYTHONWARNINGS"] = "error::DeprecationWarning"
    code = textwrap.dedent(
        """
        import pageindex.utils as utils
        import PyPDF2

        assert hasattr(utils.PyPDF2, "PdfReader")
        assert hasattr(PyPDF2, "PdfReader")
        print(PyPDF2.__file__)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "/src/PyPDF2/" in result.stdout.strip()
