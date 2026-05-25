"""共通Enum定義"""
from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from enum import StrEnum
except ImportError:  # Python 3.10
    from enum import Enum
    class StrEnum(str, Enum):
        pass


if TYPE_CHECKING:
    from stock_analyze_system.models.filing import Filing


class FilingType(StrEnum):
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    TWENTY_F = "20-F"
    SIX_K = "6-K"
    ANNUAL_REPORT = "annual_report"
    QUARTERLY_REPORT = "quarterly_report"


class PeriodType(StrEnum):
    ANNUAL = "annual"
    QUARTERLY = "quarterly"


class AccountingStandard(StrEnum):
    """Companyモデルに格納される会計基準値。

    XBRLタクソノミキー("us-gaap", "ifrs-full")とは異なる。
    タクソノミキーは ingestion/xbrl/taxonomy.py でローカル定数として管理。
    """
    US_GAAP = "US-GAAP"
    IFRS = "IFRS"
    JP_GAAP = "JP-GAAP"


class FilingSource(StrEnum):
    """ファイリング取得元。"""

    SEC = "SEC"
    EDINET = "EDINET"


# ADR-004 amendment 2026-05-17 §A:
# FilingSectionExtractor は SEC source の HTML 4 種だけを扱う。UI 候補
# (rag_filing_options) と API 境界 (POST /api/analysis-jobs) の両方で
# 同じ集合を参照するための単一情報源。
ADR004_FILING_TYPES: frozenset[FilingType] = frozenset({
    FilingType.TEN_K,
    FilingType.TEN_Q,
    FilingType.TWENTY_F,
    FilingType.SIX_K,
})


def is_adr004_supported(filing: "Filing | None") -> bool:
    """ADR-004 amendment §A: filing が `FilingSectionExtractor` の対象か判定。

    UI 候補 (`rag_filing_options`) / API 境界 (`POST /api/analysis-jobs` の
    422) / worker defense-in-depth (`AnalysisWorker._run_job`) の 3 箇所が
    同じ条件を参照するため、述語ごと単一情報源に集約する。
    """
    return (
        filing is not None
        and filing.source == FilingSource.SEC
        and filing.filing_type in ADR004_FILING_TYPES
    )


# `ADR004_FILING_TYPES` を人間可読な supported list として表現したもの。
# worker / API のエラーメッセージで参照するための単一情報源
# (literal を埋め込むと filing_type 追加時に drift する)。
ADR004_SUPPORTED_DESC: str = "SEC + {" + ", ".join(
    sorted(t.value for t in ADR004_FILING_TYPES)
) + "}"
