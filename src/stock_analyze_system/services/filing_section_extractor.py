"""SEC ファイリング固定セクション抽出 (LLM 非依存).

ADR-004 (`docs/adr/004-sec-filing-section-extractor.md`) の実装本体。
PageIndex に依存していた定型分析 4 種 (business_summary / risk_factors / mda / competitors)
の章テキスト取得段を、SEC ファイリング種別ごとの法定章構造から決定論的に取り出す。

LLM 呼び出しはこのモジュールには存在しない。
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from stock_analyze_system.services.prompts import ANALYSIS_TYPE_NAMES

if TYPE_CHECKING:
    from stock_analyze_system.models.filing import Filing

logger = logging.getLogger(__name__)


class ExtractionInputMissingError(RuntimeError):
    """storage_path に raw HTML が無く、章抽出の入力自体が欠落している."""


# ANALYSIS_TYPE_NAMES key -> ordered list of section lookup candidates.
# Real SEC filings expose keys like "Item 1A"; edgartools' parser may also
# emit semantic keys ("risk_factors", "business", "mda") for synthetic /
# minimal HTML — both are tried in order.
_SECTION_KEY_MAP: dict[str, dict[str, tuple[str, ...]]] = {
    "10-K": {
        "business_summary": ("Item 1", "business"),
        "risk_factors": ("Item 1A", "risk_factors"),
        "mda": ("Item 7", "mda"),
        # ADR-004 calls for separating the "Competition" subsection inside
        # Item 1; edgartools does not detect it as its own section, so for
        # now we fall back to all of Item 1 and let the step-3 LLM prompt
        # extract competitive context. Subsection regex is a follow-up.
        "competitors": ("Item 1", "business"),
    },
    "10-Q": {
        # 10-Q has no business chapter; UI is expected to show "10-K 参照" when empty.
        # MD&A is Part I Item 2 specifically — must be part-qualified because
        # Part II also has an Item 2 (Unregistered Sales of Equity Securities).
        "mda": ("part_i_item_2",),
        # Risk factors live in Part II Item 1A only, so the unqualified key is safe.
        "risk_factors": ("part_ii_item_1a", "Item 1A", "risk_factors"),
    },
    "20-F": {
        # ADR-004 maps these to Item 4 / Item 3D / Item 5 / Item 4B respectively,
        # but edgartools surfaces only the parent items (Item 3, Item 4) — the
        # 3D/4B subsections are not separated. Item 3 is dominated by Risk Factors
        # in practice; Item 4 contains Business Overview + Competition.
        "business_summary": ("part_i_item_4", "Item 4"),
        "risk_factors": ("part_i_item_3", "Item 3"),
        "mda": ("part_i_item_5", "Item 5"),
        "competitors": ("part_i_item_4", "Item 4"),
    },
    "6-K": {
        # 6-K has no statutory section structure. Fields below are still listed
        # to advertise intent; the actual text comes from _FULL_TEXT_FALLBACK.
    },
}


# Fields that, when their _SECTION_KEY_MAP lookup yields empty, fall back to the
# full document text. Only applied to filing types where chapter structure is
# not legally fixed (Regulation S-K does not regulate 6-K).
_FULL_TEXT_FALLBACK: dict[str, tuple[str, ...]] = {
    "6-K": ("business_summary", "mda"),
}


# analysis_types whose absence is by design per filing type. Callers (RagService)
# treat these as success rather than failure and persist a placeholder result.
_STRUCTURALLY_EMPTY: dict[str, frozenset[str]] = {
    "10-Q": frozenset({"business_summary", "competitors"}),
    "6-K": frozenset({"risk_factors", "competitors"}),
}


def is_structurally_empty(filing_type: str, analysis_type: str) -> bool:
    return analysis_type in _STRUCTURALLY_EMPTY.get(filing_type, frozenset())


# Regex fallback applied when _SECTION_KEY_MAP lookup yields empty AND the form
# has a legally fixed structure (so we know which Item heading to look for).
# Real-world trigger: TEM Q3 2025 10-Q — its HTML uses U+2009 (thin space)
# between "Item" and the number, which edgartools' HTMLParser fails to index.
# Patterns intentionally allow any whitespace (including thin/non-breaking) and
# match the LAST occurrence in the doc — TOC mentions appear before body text.
_REGEX_FALLBACK: dict[str, dict[str, tuple[str, str | None]]] = {
    "10-Q": {
        "mda": (
            r"(?im)^\s*Item\s*\d?\s*2\.?\s+Management",
            r"(?im)^\s*Item\s*\d?\s*3\.?\s+",
        ),
    },
}


class FilingSectionExtractor:
    """SEC ファイリングから定型分析用の章テキストを抽出する."""

    async def extract(self, filing: Filing) -> dict[str, str]:
        """Return a dict keyed by ANALYSIS_TYPE_NAMES with extracted section text.

        Fallback chain (ADR-004 §Answer):
        1. edgartools HTMLParser (consumes iXBRL + HTML structure)
        2. Regex pickup from full_text when _REGEX_FALLBACK has a pattern
        3. Full document text when _FULL_TEXT_FALLBACK lists the analysis_type
        """
        result = {name: "" for name in ANALYSIS_TYPE_NAMES}

        html_path = self._find_raw_html(filing.storage_path)
        if html_path is None:
            message = (
                f"raw HTML input missing for filing {getattr(filing, 'id', '?')}: "
                f"storage_path={filing.storage_path!r}"
            )
            logger.warning(message)
            raise ExtractionInputMissingError(message)

        sections, full_text = await asyncio.to_thread(
            self._parse_html, html_path, filing.filing_type,
        )

        mapping = _SECTION_KEY_MAP.get(filing.filing_type, {})
        regex_patterns = _REGEX_FALLBACK.get(filing.filing_type, {})
        for analysis_key, candidates in mapping.items():
            text = self._lookup(sections, *candidates)
            if not text and analysis_key in regex_patterns and full_text:
                start_re, end_re = regex_patterns[analysis_key]
                text = self._regex_extract(full_text, start_re, end_re)
                if text:
                    logger.info(
                        "filing %s: %s recovered via regex fallback",
                        getattr(filing, "id", "?"), analysis_key,
                    )
            result[analysis_key] = text

        full_text_fields = _FULL_TEXT_FALLBACK.get(filing.filing_type, ())
        if full_text_fields and full_text:
            for analysis_key in full_text_fields:
                if not result[analysis_key]:
                    result[analysis_key] = full_text

        return result

    @staticmethod
    def _find_raw_html(storage_path: str | None) -> Path | None:
        """`<storage_path>/raw/*.htm` の最初の HTML を返す."""
        if not storage_path:
            return None
        raw_dir = Path(storage_path) / "raw"
        if not raw_dir.is_dir():
            return None
        for entry in sorted(raw_dir.iterdir()):
            if entry.suffix.lower() in (".htm", ".html"):
                return entry
        return None

    @staticmethod
    def _parse_html(html_path: Path, filing_type: str) -> tuple[dict, str]:
        """Parse HTML once and return (sections_dict, full_text). Sync; runs in executor."""
        from edgar.documents import HTMLParser
        from edgar.documents.config import ParserConfig

        html = html_path.read_text(encoding="utf-8")
        parser = HTMLParser(ParserConfig(form=filing_type))
        doc = parser.parse(html)
        return doc.sections, doc.text() or ""

    @staticmethod
    def _lookup(sections, *keys: str) -> str:
        """渡された候補キーで sections.get() を順に試し、最初に取れた text を返す."""
        for key in keys:
            section = sections.get(key)
            if section is None:
                continue
            text = section.text() or ""
            if text:
                return text
        return ""

    @staticmethod
    def _regex_extract(full_text: str, start_re: str, end_re: str | None) -> str:
        """Pick the LAST start match (skip TOC) and slice until end pattern or EOF."""
        matches = list(re.finditer(start_re, full_text))
        if not matches:
            return ""
        start_match = matches[-1]
        start = start_match.start()
        if end_re:
            search_pos = start_match.end()
            end_match = re.search(end_re, full_text[search_pos:])
            end = search_pos + end_match.start() if end_match else len(full_text)
        else:
            end = len(full_text)
        return full_text[start:end].strip()
