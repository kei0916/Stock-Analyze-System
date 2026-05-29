"""FilingSectionExtractor 単体テスト (ADR-004)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from stock_analyze_system.services.filing_section_extractor import (
    ExtractionInputMissingError,
    FilingSectionExtractor,
)
from stock_analyze_system.services.prompts import ANALYSIS_TYPE_NAMES


@dataclass
class FakeFiling:
    id: int
    filing_type: str
    storage_path: str


MINIMAL_10K_HTML = """<html><body>
<p>Item 1. Business</p>
<p>We sell widgets.</p>
<p>Item 1A. Risk Factors</p>
<p>The widget market is volatile and may decline.</p>
<p>Item 7. Management Discussion and Analysis</p>
<p>Revenue grew 10% year over year.</p>
</body></html>"""


def _write_minimal_filing(tmp_path: Path, html: str = MINIMAL_10K_HTML) -> FakeFiling:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "filing.htm").write_text(html, encoding="utf-8")
    return FakeFiling(id=1, filing_type="10-K", storage_path=str(tmp_path))


async def test_extract_returns_all_four_keys(tmp_path: Path) -> None:
    filing = _write_minimal_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert set(result.keys()) == set(ANALYSIS_TYPE_NAMES)


async def test_extract_raises_when_raw_html_missing(tmp_path: Path) -> None:
    """converted.pdf だけの filing は extractor 入力欠落として失敗する."""
    (tmp_path / "converted.pdf").write_text("pdf bytes", encoding="utf-8")
    filing = FakeFiling(id=10, filing_type="10-K", storage_path=str(tmp_path))
    extractor = FilingSectionExtractor()

    with pytest.raises(ExtractionInputMissingError, match="raw HTML"):
        await extractor.extract(filing)


async def test_extract_10k_risk_factors_from_html(tmp_path: Path) -> None:
    """10-K HTML から Item 1A (Risk Factors) を抽出して risk_factors キーに入れる."""
    filing = _write_minimal_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "widget market is volatile" in result["risk_factors"]


async def test_extract_10k_business_summary_from_html(tmp_path: Path) -> None:
    """10-K HTML から Item 1 (Business) を抽出して business_summary キーに入れる."""
    filing = _write_minimal_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "We sell widgets" in result["business_summary"]


async def test_extract_10k_mda_from_html(tmp_path: Path) -> None:
    """10-K HTML から Item 7 (MD&A) を抽出して mda キーに入れる."""
    filing = _write_minimal_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "Revenue grew 10%" in result["mda"]


MINIMAL_10Q_HTML = """<html><body>
<p>Part I. Financial Information</p>
<p>Item 1. Financial Statements</p>
<p>Balance sheet content.</p>
<p>Item 2. Management Discussion and Analysis</p>
<p>Sales declined this quarter.</p>
<p>Part II. Other Information</p>
<p>Item 1A. Risk Factors</p>
<p>New tariffs may hurt margins.</p>
</body></html>"""


def _write_10q_filing(tmp_path: Path) -> FakeFiling:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "filing.htm").write_text(MINIMAL_10Q_HTML, encoding="utf-8")
    return FakeFiling(id=2, filing_type="10-Q", storage_path=str(tmp_path))


async def test_extract_10q_risk_factors_from_html(tmp_path: Path) -> None:
    """10-Q では Part II Item 1A を risk_factors にマップする."""
    filing = _write_10q_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "tariffs may hurt margins" in result["risk_factors"]


async def test_extract_10q_mda_from_html(tmp_path: Path) -> None:
    """10-Q では Part I Item 2 を mda にマップする (Part II Item 2 と区別)."""
    filing = _write_10q_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "Sales declined this quarter" in result["mda"]


async def test_extract_10q_business_summary_is_empty(tmp_path: Path) -> None:
    """10-Q には business summary 章が無く、空文字列で返る (UI が "10-K 参照" 等を表示)."""
    filing = _write_10q_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert result["business_summary"] == ""
    assert result["competitors"] == ""


MINIMAL_20F_HTML = """<html><body>
<p>Part I</p>
<p>Item 3. Key Information</p>
<p>Risk Factors: foreign exchange volatility is significant.</p>
<p>Item 4. Information on the Company</p>
<p>We design and fabricate semiconductors. Our main rivals are competitor A and B.</p>
<p>Item 5. Operating and Financial Review and Prospects</p>
<p>Net revenue grew driven by AI demand.</p>
</body></html>"""


def _write_20f_filing(tmp_path: Path) -> FakeFiling:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "filing.htm").write_text(MINIMAL_20F_HTML, encoding="utf-8")
    return FakeFiling(id=3, filing_type="20-F", storage_path=str(tmp_path))


async def test_extract_20f_business_summary(tmp_path: Path) -> None:
    """20-F では Item 4 を business_summary にマップする."""
    filing = _write_20f_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "design and fabricate semiconductors" in result["business_summary"]


async def test_extract_20f_risk_factors(tmp_path: Path) -> None:
    """20-F では Item 3 (Key Information, 内部に 3D Risk Factors) を risk_factors に。"""
    filing = _write_20f_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "foreign exchange volatility" in result["risk_factors"]


async def test_extract_20f_mda(tmp_path: Path) -> None:
    """20-F では Item 5 を mda にマップする."""
    filing = _write_20f_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "AI demand" in result["mda"]


async def test_extract_20f_competitors(tmp_path: Path) -> None:
    """20-F competitors は Item 4 (Item 4B が分離検出されないため Item 4 全体) を返す."""
    filing = _write_20f_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "competitor A and B" in result["competitors"]


async def test_extract_10k_competitors_from_item1(tmp_path: Path) -> None:
    """10-K competitors は Item 1 を流用する (Competition subsection 分離は段階拡張)."""
    filing = _write_minimal_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "We sell widgets" in result["competitors"]


MINIMAL_6K_HTML = """<html><body>
<h1>Form 6-K Report of Foreign Issuer</h1>
<p>The company announces quarterly revenue of $100M, up 5% year over year.</p>
<p>Margins expanded due to operational efficiencies.</p>
</body></html>"""


def _write_6k_filing(tmp_path: Path) -> FakeFiling:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "filing.htm").write_text(MINIMAL_6K_HTML, encoding="utf-8")
    return FakeFiling(id=4, filing_type="6-K", storage_path=str(tmp_path))


async def test_extract_6k_falls_back_to_full_text(tmp_path: Path) -> None:
    """6-K は法定章構造が無いため、business_summary / mda に全文を返す (fallback 4 段目)."""
    filing = _write_6k_filing(tmp_path)
    extractor = FilingSectionExtractor()

    result = await extractor.extract(filing)

    assert "quarterly revenue of $100M" in result["business_summary"]
    assert "quarterly revenue of $100M" in result["mda"]
    # risk_factors / competitors は規定されないため空 placeholder
    assert result["risk_factors"] == ""
    assert result["competitors"] == ""


# ---- regex fallback (real-world case: TEM 10-Q where parser misses Item 2) ----

TEM_LIKE_FULL_TEXT = (
    "Table of Contents\n"
    "Item 1. Financial Statements    10\n"
    "Item 2. Management's Discussion and Analysis    11\n"
    "Item 3. Quantitative and Qualitative Disclosures About Market Risk    15\n"
    "\n"
    "Item 1. Financial Statements\n"
    "Consolidated balance sheets follow.\n"
    "\n"
    "Item 2. Management's Discussion and Analysis of Financial Condition\n"
    "Revenue declined due to seasonal factors. Operating expenses rose.\n"
    "\n"
    "Item 3. Quantitative and Qualitative Disclosures About Market Risk\n"
    "Interest rate exposure is modest.\n"
)


async def test_extract_10q_mda_via_regex_when_parser_returns_empty(
    tmp_path: Path, monkeypatch,
) -> None:
    """parser が part_i_item_2 を見落としたら、full_text を正規表現で切り出す."""
    filing = _write_10q_filing(tmp_path)
    extractor = FilingSectionExtractor()

    def fake_parse(html_path: Path, filing_type: str):
        return {}, TEM_LIKE_FULL_TEXT

    monkeypatch.setattr(
        FilingSectionExtractor, "_parse_html", staticmethod(fake_parse),
    )

    result = await extractor.extract(filing)

    assert "Revenue declined" in result["mda"]
    # TOC エントリではなく本文 (より長い) が取れていること
    assert "seasonal factors" in result["mda"]


def test_regex_extract_excludes_end_match_regardless_of_start_match_length() -> None:
    """`_regex_extract` must search for the end pattern from the position
    immediately after the start match — not from `start + 10`. The latter
    silently embeds the end heading inside the result whenever the start
    pattern matches fewer than 10 characters."""
    extractor = FilingSectionExtractor()
    full_text = "A\nbody\nstop\n"  # start match "A" is 1 char; end "stop" lives 7 chars later
    result = extractor._regex_extract(full_text, r"(?m)^A$", r"(?m)^stop$")
    assert "body" in result
    assert "stop" not in result
