"""RAG progress frontend/backend contract tests."""
from __future__ import annotations

import re
from pathlib import Path

from stock_analyze_system.services.prompts import ANALYSIS_TYPE_NAMES


def test_analysis_labels_match_backend_analysis_type_names():
    repo_root = Path(__file__).resolve().parents[3]
    app_js = (
        repo_root / "src/stock_analyze_system/web/static/app.js"
    ).read_text(encoding="utf-8")
    match = re.search(
        r"const\s+ANALYSIS_LABELS\s*=\s*\{(?P<body>.*?)\};",
        app_js,
        re.S,
    )
    assert match is not None, "ANALYSIS_LABELS declaration missing"
    frontend_types = re.findall(
        r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:",
        match.group("body"),
        re.M,
    )

    assert frontend_types == list(ANALYSIS_TYPE_NAMES)
