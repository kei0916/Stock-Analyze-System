"""PageIndex ツリーインデックスの構築・クエリ (公開 API)."""
from __future__ import annotations

from stock_analyze_system.services.pageindex.models import (
    BuildResult,
    BuildTiming,
    QueryResult,
    QueryTiming,
)
from stock_analyze_system.services.pageindex.service import PageIndexService
from stock_analyze_system.services.pageindex.tree_utils import (
    collect_node_map,
    count_nodes,
    extract_page_count,
    node_page,
    strip_text,
)

__all__ = [
    "BuildResult",
    "BuildTiming",
    "PageIndexService",
    "QueryResult",
    "QueryTiming",
    "collect_node_map",
    "count_nodes",
    "extract_page_count",
    "node_page",
    "strip_text",
]
