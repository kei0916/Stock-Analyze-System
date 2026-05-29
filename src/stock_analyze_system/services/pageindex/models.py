"""PageIndex ビルド/クエリの戻り値 dataclass."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class BuildTiming:
    """インデックス構築の工程別所要時間（秒）"""

    total: float = 0.0
    page_index_call: float = 0.0

    def __str__(self) -> str:
        return (
            f"total={self.total:.1f}s "
            f"(page_index={self.page_index_call:.1f}s)"
        )


@dataclass
class QueryTiming:
    """RAGクエリの工程別所要時間（秒）"""

    total: float = 0.0
    tree_search: float = 0.0
    context_build: float = 0.0
    answer_generation: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"total={self.total:.1f}s "
            f"(search={self.tree_search:.1f}s, "
            f"context={self.context_build:.1f}s, "
            f"answer={self.answer_generation:.1f}s)"
        )

    def format_cli(self, wall_time: float | None = None) -> str:
        """CLI表示用フォーマット"""
        total = wall_time if wall_time is not None else self.total
        return f"search={self.tree_search:.1f}s answer={self.answer_generation:.1f}s total={total:.1f}s"


@dataclass
class BuildResult:
    """インデックス構築結果"""

    tree: dict
    timing: BuildTiming = field(default_factory=BuildTiming)


@dataclass
class QueryResult:
    """RAGクエリ結果"""

    answer: str
    source_pages: list[int]
    source_sections: list[str]
    confidence: float
    model: str
    timing: QueryTiming = field(default_factory=QueryTiming)

    def to_dict(self) -> dict:
        return asdict(self)
