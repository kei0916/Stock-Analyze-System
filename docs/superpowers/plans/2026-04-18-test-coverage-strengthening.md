# Test Coverage Strengthening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** プロジェクト全体にテストカバレッジ強化層を追加し、今後のリファクタリングを安全に実施できる基盤を作る。ソースコードは一切変更しない (テスト追加のみ)。

**Architecture:** 3 Phase 構成。Phase A (PR1-5): 責務が集中する5領域に特性化 (characterization) テストを追加。Phase B (PR6-7): 未カバー分岐にテスト追加 + 防御的コードは `# pragma: no cover` で除外。Phase C (PR8): `container.setup_services()` を使った結合テスト 3 シナリオを追加。

**Tech Stack:** Python 3.10+, pytest 8, pytest-asyncio, SQLAlchemy 2.0 async, in-memory SQLite, FastAPI TestClient (既存のみ使用)

**Spec:** `docs/superpowers/specs/2026-04-18-test-coverage-strengthening-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `tests/unit/characterization/__init__.py` | Phase A パッケージ |
| `tests/unit/characterization/test_xbrl_parse_golden.py` | Phase A-1: SEC XBRL パース結果のゴールデン比較 |
| `tests/unit/characterization/test_valuation_compute_golden.py` | Phase A-2: `compute_valuation_from_financials` 全指標ゴールデン |
| `tests/unit/characterization/test_container_assembly.py` | Phase A-3: `setup_services()` DI 配線検証 |
| `tests/unit/characterization/test_verification_report_schema.py` | Phase A-4: 検証レポート JSON スキーマ固定 |
| `tests/unit/characterization/test_enum_integration.py` | Phase A-5: StrEnum と argparse/DB/JSON の相互運用性 |
| `tests/fixtures/__init__.py` | fixtures パッケージマーカー |
| `tests/fixtures/xbrl/sample_sec_10k.json` | Phase A-1 入力 (SEC Company Facts 縮小版) |
| `tests/fixtures/xbrl/expected_parse_result.json` | Phase A-1 期待値 (ゴールデン) |
| `tests/fixtures/xbrl/README.md` | ゴールデン再生成手順 |
| `tests/fixtures/valuation/expected_valuation.json` | Phase A-2 期待値 (ゴールデン) |
| `tests/fixtures/valuation/README.md` | 再生成手順 |
| `tests/fixtures/reports/expected_verification.json` | Phase A-4 期待値 (ゴールデン) |
| `tests/fixtures/reports/README.md` | 再生成手順 |
| `scripts/generate_fixtures/gen_xbrl_golden.py` | A-1 ゴールデン生成スクリプト |
| `scripts/generate_fixtures/gen_valuation_golden.py` | A-2 ゴールデン生成スクリプト |
| `scripts/generate_fixtures/gen_verification_golden.py` | A-4 ゴールデン生成スクリプト |
| `tests/integration/conftest.py` | Phase C: `build_test_config()` + 外部クライアントモック |
| `tests/integration/test_service_assembly.py` | Phase C: 3 シナリオ結合テスト |

### Modified Files
| File | Change |
|------|--------|
| `pyproject.toml` | `[tool.pytest.ini_options].markers` に `characterization` / `integration` 追記 |
| `src/stock_analyze_system/services/pageindex_service.py` | Phase B-2: 外部 lib 呼び出し部に `# pragma: no cover` 追加 (ソース行のコメント追加のみ、ロジック不変) |
| `src/stock_analyze_system/models/base.py` | Phase B-2: sync fallback 行に `# pragma: no cover` |
| `tests/unit/web/test_watchlists.py` | Phase B-1: 未ログインリダイレクトテスト追加 |
| `tests/unit/web/test_targets.py` | Phase B-1: 未ログインリダイレクトテスト追加 |
| `tests/unit/web/test_stocks.py` | Phase B-1: 未ログインリダイレクトテスト追加 |
| `tests/unit/web/test_dashboard.py` | Phase B-1: 未ログインリダイレクトテスト追加 |
| `tests/unit/web/test_rag.py` | Phase B-1: 未ログインリダイレクトテスト追加 |
| `tests/unit/web/test_api.py` | Phase B-1: 404/400 エラーパステスト追加 |
| `tests/unit/web/test_jobs.py` | Phase B-1: sync失敗時 flash テスト追加 |
| `tests/unit/web/test_auth.py` | Phase B-1: 署名無効/期限切れテスト追加 |
| `tests/unit/cli/test_watchlist_cli.py` | Phase B-2: エラーパステスト追加 |
| `tests/unit/cli/test_valuation_cli.py` | Phase B-2: エラーパステスト追加 |
| `tests/unit/cli/test_financial_cli.py` | Phase B-2: バリデーションテスト追加 |
| `tests/unit/ingestion/test_edinet_xbrl_parser.py` | Phase B-2: 分岐テスト追加 |
| `tests/unit/ingestion/test_sec_edgar.py` | Phase B-2: リトライ/エラーテスト追加 |

### Note on pragma exemptions

pragma 除外 (ソースファイルへの `# pragma: no cover` コメント追加) は**仕様上許容された唯一のソース変更**。spec で合意済み (セクション3)。ロジックは一切変わらない。

---

## Task 1: セットアップ (マーカー登録 + ディレクトリ作成)

**Files:**
- Modify: `pyproject.toml:56-59`
- Create: `tests/unit/characterization/__init__.py` (空)
- Create: `tests/fixtures/__init__.py` (空)

- [ ] **Step 1: `pyproject.toml` に pytest マーカーを追加**

現在 (lines 57-59):
```toml
markers = [
    "rag_model(name): テストで使用するモデル名をマーク（タイミングレポート用）",
]
```

変更後:
```toml
markers = [
    "rag_model(name): テストで使用するモデル名をマーク（タイミングレポート用）",
    "characterization: リファクタ保護用の振る舞い固定テスト",
    "integration: 結合テスト (実DB・サービス組立て経由)",
]
```

- [ ] **Step 2: ディレクトリとパッケージマーカーを作成**

```bash
mkdir -p tests/unit/characterization tests/fixtures/xbrl tests/fixtures/valuation tests/fixtures/reports tests/integration scripts/generate_fixtures
touch tests/unit/characterization/__init__.py tests/fixtures/__init__.py
```

- [ ] **Step 3: マーカー登録を検証**

Run: `uv run pytest --markers 2>&1 | grep -E "characterization|integration"`
Expected: 2 行出力 ("@pytest.mark.characterization" と "@pytest.mark.integration")

- [ ] **Step 4: 全テスト通過確認**

Run: `uv run pytest tests/ -q 2>&1 | tail -5`
Expected: `632 passed`

- [ ] **Step 5: コミット**

```bash
git add pyproject.toml tests/unit/characterization/__init__.py tests/fixtures/__init__.py
git commit -m "$(cat <<'EOF'
test: register characterization/integration markers + scaffold dirs

Phase A/B/C テスト追加の下準備。マーカー登録とディレクトリ作成のみ、
既存テストへの影響なし。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2 (PR1): XBRL パーサー特性化テスト

**Files:**
- Create: `scripts/generate_fixtures/gen_xbrl_golden.py`
- Create: `tests/fixtures/xbrl/sample_sec_10k.json`
- Create: `tests/fixtures/xbrl/expected_parse_result.json`
- Create: `tests/fixtures/xbrl/README.md`
- Create: `tests/unit/characterization/test_xbrl_parse_golden.py`

- [ ] **Step 1: サンプル SEC Company Facts 入力を作成**

`tests/fixtures/xbrl/sample_sec_10k.json` を作成。SEC Company Facts の実構造を模した縮小版 (5 タグ程度)。

```json
{
  "cik": 320193,
  "entityName": "Apple Inc.",
  "facts": {
    "us-gaap": {
      "Revenues": {
        "label": "Revenues",
        "units": {
          "USD": [
            {"end": "2023-09-30", "val": 383285000000, "fy": 2023, "fp": "FY", "form": "10-K", "start": "2022-10-01"},
            {"end": "2022-09-24", "val": 394328000000, "fy": 2022, "fp": "FY", "form": "10-K", "start": "2021-09-26"},
            {"end": "2023-07-01", "val": 81797000000, "fy": 2023, "fp": "Q3", "form": "10-Q", "start": "2023-04-02"}
          ]
        }
      },
      "NetIncomeLoss": {
        "label": "Net Income",
        "units": {
          "USD": [
            {"end": "2023-09-30", "val": 96995000000, "fy": 2023, "fp": "FY", "form": "10-K", "start": "2022-10-01"},
            {"end": "2022-09-24", "val": 99803000000, "fy": 2022, "fp": "FY", "form": "10-K", "start": "2021-09-26"}
          ]
        }
      },
      "Assets": {
        "label": "Assets",
        "units": {
          "USD": [
            {"end": "2023-09-30", "val": 352755000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2022-09-24", "val": 352583000000, "fy": 2022, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "StockholdersEquity": {
        "label": "Stockholders Equity",
        "units": {
          "USD": [
            {"end": "2023-09-30", "val": 62146000000, "fy": 2023, "fp": "FY", "form": "10-K"},
            {"end": "2022-09-24", "val": 50672000000, "fy": 2022, "fp": "FY", "form": "10-K"}
          ]
        }
      },
      "EarningsPerShareBasic": {
        "label": "EPS Basic",
        "units": {
          "USD/shares": [
            {"end": "2023-09-30", "val": 6.16, "fy": 2023, "fp": "FY", "form": "10-K", "start": "2022-10-01"},
            {"end": "2022-09-24", "val": 6.15, "fy": 2022, "fp": "FY", "form": "10-K", "start": "2021-09-26"}
          ]
        }
      }
    }
  }
}
```

- [ ] **Step 2: ゴールデン生成スクリプトを作成**

`scripts/generate_fixtures/gen_xbrl_golden.py`:

```python
"""SEC XBRL パース結果のゴールデン fixture を生成するスクリプト。

使い方:
    uv run python scripts/generate_fixtures/gen_xbrl_golden.py

現行実装の出力を tests/fixtures/xbrl/expected_parse_result.json に保存する。
実装変更時は手動で再実行し、差分を PR レビュー対象にすること。
"""
from __future__ import annotations

import json
from pathlib import Path

from stock_analyze_system.ingestion.xbrl.parser import SecXbrlParser

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "tests/fixtures/xbrl/sample_sec_10k.json"
OUTPUT = ROOT / "tests/fixtures/xbrl/expected_parse_result.json"


def main() -> None:
    facts = json.loads(INPUT.read_text())
    parser = SecXbrlParser()
    annual = parser.parse_company_facts(facts, period_type="annual")
    quarterly = parser.parse_company_facts(facts, period_type="quarterly")
    result = {"annual": annual, "quarterly": quarterly}
    OUTPUT.write_text(json.dumps(result, indent=2, default=str))
    print(f"Wrote {OUTPUT} ({len(annual)} annual, {len(quarterly)} quarterly records)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: ゴールデンファイル生成**

```bash
uv run python scripts/generate_fixtures/gen_xbrl_golden.py
```

Expected: `Wrote .../expected_parse_result.json (N annual, M quarterly records)`

生成された JSON を目視確認し、明らかに不正なら STOP して原因調査する (このゴールデンが現行仕様のスナップショットとなる)。

- [ ] **Step 4: README を作成**

`tests/fixtures/xbrl/README.md`:

```markdown
# XBRL Fixtures

## Files
- `sample_sec_10k.json`: SEC Company Facts の縮小サンプル (5タグ、annual + quarterly)
- `expected_parse_result.json`: `SecXbrlParser.parse_company_facts()` のゴールデン出力

## 再生成手順

実装を意図的に変更した場合のみ実行:

```bash
uv run python scripts/generate_fixtures/gen_xbrl_golden.py
```

差分は PR レビューで必ず確認すること。
```

- [ ] **Step 5: 特性化テストを書く (failing テストとして先に)**

`tests/unit/characterization/test_xbrl_parse_golden.py`:

```python
"""SEC XBRL パーサーの出力を固定するゴールデンテスト。

将来パーサーがリファクタされた場合でも入出力が一致することを保証する。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_analyze_system.ingestion.xbrl.parser import SecXbrlParser
from stock_analyze_system.ingestion.xbrl.period_filter import (
    ANNUAL_MIN_DAYS, QUARTERLY_MAX_DAYS, duration_ok, merge_near_dates,
)
from stock_analyze_system.ingestion.xbrl.taxonomy import detect_taxonomy

FIXTURES = Path(__file__).parent.parent.parent / "fixtures/xbrl"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.characterization
class TestSecXbrlParserGolden:
    def test_annual_parse_matches_golden(self):
        facts = _load("sample_sec_10k.json")
        expected = _load("expected_parse_result.json")
        parser = SecXbrlParser()
        result = parser.parse_company_facts(facts, period_type="annual")
        # JSON round-trip で型を揃える (date → str)
        result_normalized = json.loads(json.dumps(result, default=str))
        assert result_normalized == expected["annual"]

    def test_quarterly_parse_matches_golden(self):
        facts = _load("sample_sec_10k.json")
        expected = _load("expected_parse_result.json")
        parser = SecXbrlParser()
        result = parser.parse_company_facts(facts, period_type="quarterly")
        result_normalized = json.loads(json.dumps(result, default=str))
        assert result_normalized == expected["quarterly"]


@pytest.mark.characterization
class TestPeriodFilterBoundaries:
    def test_duration_ok_annual_exactly_min_days(self):
        assert duration_ok(ANNUAL_MIN_DAYS, "annual") is True

    def test_duration_ok_annual_below_min(self):
        assert duration_ok(ANNUAL_MIN_DAYS - 1, "annual") is False

    def test_duration_ok_quarterly_exactly_max(self):
        assert duration_ok(QUARTERLY_MAX_DAYS, "quarterly") is True

    def test_duration_ok_quarterly_above_max(self):
        assert duration_ok(QUARTERLY_MAX_DAYS + 1, "quarterly") is False


@pytest.mark.characterization
class TestTaxonomyDetection:
    def test_detect_us_gaap(self):
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": []}}}}}
        taxonomy, subtree, currency = detect_taxonomy(facts)
        assert taxonomy == "us-gaap"
        assert currency == "USD"

    def test_detect_ifrs(self):
        facts = {"facts": {"ifrs-full": {"Revenue": {"units": {"EUR": []}}}}}
        taxonomy, subtree, currency = detect_taxonomy(facts)
        assert taxonomy == "ifrs-full"
        assert currency == "EUR"
```

- [ ] **Step 6: テスト実行 (パスすることを確認)**

Run: `uv run pytest tests/unit/characterization/test_xbrl_parse_golden.py -v`
Expected: すべて PASS (ゴールデンは Step 3 で現行出力を保存済みのため)

失敗した場合:
- `period_filter` / `taxonomy` から import できない関数があれば、実コードを確認して API 名を合わせる (`detect_taxonomy` などの戻り値 tuple の要素順)
- ゴールデン比較が失敗する場合は `date` 型の扱いを見直す

- [ ] **Step 7: フルテスト通過確認**

Run: `uv run pytest tests/ -q 2>&1 | tail -3`
Expected: 既存 632 + 新規 (約 9 テスト) = 641 passed

- [ ] **Step 8: コミット**

```bash
git add scripts/generate_fixtures/gen_xbrl_golden.py tests/fixtures/xbrl/ tests/unit/characterization/test_xbrl_parse_golden.py
git commit -m "$(cat <<'EOF'
test: characterize SEC XBRL parser output (golden snapshots)

Phase A-1: SecXbrlParser.parse_company_facts() の annual/quarterly 出力を
ゴールデン化し、period_filter と taxonomy 検出の境界動作を固定する。
今後のパーサー分割・リファクタから現行挙動を保護する。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3 (PR2): ValuationService 特性化テスト

**Files:**
- Create: `scripts/generate_fixtures/gen_valuation_golden.py`
- Create: `tests/fixtures/valuation/expected_valuation.json`
- Create: `tests/fixtures/valuation/README.md`
- Create: `tests/unit/characterization/test_valuation_compute_golden.py`

- [ ] **Step 1: ゴールデン生成スクリプトを作成**

`scripts/generate_fixtures/gen_valuation_golden.py`:

```python
"""compute_valuation_from_financials の出力ゴールデンを生成。

使い方: uv run python scripts/generate_fixtures/gen_valuation_golden.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from stock_analyze_system.services.valuation import compute_valuation_from_financials

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tests/fixtures/valuation/expected_valuation.json"


@dataclass
class _FD:
    """FinancialData stand-in"""
    eps: float | None
    net_income: float | None
    equity: float | None
    shares_outstanding: float | None
    total_debt: float | None
    cash: float | None
    ebitda: float | None
    revenue: float | None
    fcf: float | None


def main() -> None:
    # Apple-like 2023 annual, rough numbers
    fd = _FD(
        eps=6.16, net_income=96995000000.0,
        equity=62146000000.0, shares_outstanding=15800000000.0,
        total_debt=111088000000.0, cash=29965000000.0,
        ebitda=125820000000.0, revenue=383285000000.0,
        fcf=99584000000.0,
    )
    result = compute_valuation_from_financials(
        stock_price=150.0, fd=fd, currency="USD",
        val_date=date(2023, 9, 30), market_cap=None,
    )
    OUTPUT.write_text(json.dumps(result, indent=2, default=str))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: ゴールデン生成**

```bash
uv run python scripts/generate_fixtures/gen_valuation_golden.py
```

生成された `expected_valuation.json` を目視確認。per / pbr / ev_ebitda / psr / fcf_yield が数値として妥当か確認 (極端に大きい・小さい値でないこと)。

- [ ] **Step 3: README を作成**

`tests/fixtures/valuation/README.md`:

```markdown
# Valuation Fixtures

## Files
- `expected_valuation.json`: `compute_valuation_from_financials()` の代表入力に対する期待出力

## 再生成手順
```bash
uv run python scripts/generate_fixtures/gen_valuation_golden.py
```
実装を意図的に変更した場合のみ。差分は PR で必ず確認する。
```

- [ ] **Step 4: 特性化テストを書く**

`tests/unit/characterization/test_valuation_compute_golden.py`:

```python
"""compute_valuation_from_financials の計算結果を固定するゴールデンテスト。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from stock_analyze_system.services.valuation import compute_valuation_from_financials

FIXTURES = Path(__file__).parent.parent.parent / "fixtures/valuation"


@dataclass
class _FD:
    eps: float | None = None
    net_income: float | None = None
    equity: float | None = None
    shares_outstanding: float | None = None
    total_debt: float | None = None
    cash: float | None = None
    ebitda: float | None = None
    revenue: float | None = None
    fcf: float | None = None


def _apple_fd() -> _FD:
    return _FD(
        eps=6.16, net_income=96995000000.0,
        equity=62146000000.0, shares_outstanding=15800000000.0,
        total_debt=111088000000.0, cash=29965000000.0,
        ebitda=125820000000.0, revenue=383285000000.0,
        fcf=99584000000.0,
    )


@pytest.mark.characterization
class TestComputeValuationGolden:
    def test_full_valuation_matches_golden(self):
        expected = json.loads((FIXTURES / "expected_valuation.json").read_text())
        result = compute_valuation_from_financials(
            stock_price=150.0, fd=_apple_fd(), currency="USD",
            val_date=date(2023, 9, 30), market_cap=None,
        )
        result_norm = json.loads(json.dumps(result, default=str))
        assert result_norm == expected

    def test_none_stock_price_returns_empty_metrics(self):
        """stock_price=None の場合、全指標 None + currency/date/market_cap 保持"""
        result = compute_valuation_from_financials(
            stock_price=None, fd=_apple_fd(), currency="JPY",
            val_date=date(2024, 3, 31), market_cap=1000.0,
        )
        assert result["currency"] == "JPY"
        assert result["date"] == date(2024, 3, 31)
        assert result["market_cap"] == 1000.0
        assert result["stock_price"] is None
        for key in ("per", "pbr", "ev_ebitda", "psr", "fcf_yield"):
            assert result[key] is None, f"{key} should be None"

    def test_zero_shares_outstanding_gives_none_pbr(self):
        """shares_outstanding=0 で PBR は None になる (ゼロ除算回避)"""
        fd = _apple_fd()
        fd.shares_outstanding = 0
        result = compute_valuation_from_financials(
            stock_price=150.0, fd=fd, currency="USD",
            val_date=date(2023, 9, 30), market_cap=None,
        )
        assert result["pbr"] is None

    def test_missing_equity_gives_none_pbr(self):
        fd = _apple_fd()
        fd.equity = None
        result = compute_valuation_from_financials(
            stock_price=150.0, fd=fd, currency="USD",
            val_date=date(2023, 9, 30), market_cap=None,
        )
        assert result["pbr"] is None

    def test_missing_shares_gives_none_effective_mcap_metrics(self):
        """shares_outstanding=None かつ market_cap=None → EV/EBITDA, PSR, FCF yield が None"""
        fd = _apple_fd()
        fd.shares_outstanding = None
        result = compute_valuation_from_financials(
            stock_price=150.0, fd=fd, currency="USD",
            val_date=date(2023, 9, 30), market_cap=None,
        )
        assert result["ev_ebitda"] is None
        assert result["psr"] is None
        assert result["fcf_yield"] is None

    def test_explicit_market_cap_overrides_shares_calculation(self):
        """market_cap 指定時は shares_outstanding ではなく market_cap を使う"""
        fd = _apple_fd()
        explicit_mcap = 2_500_000_000_000.0
        result = compute_valuation_from_financials(
            stock_price=150.0, fd=fd, currency="USD",
            val_date=date(2023, 9, 30), market_cap=explicit_mcap,
        )
        assert result["market_cap"] == explicit_mcap
```

- [ ] **Step 5: テスト実行**

Run: `uv run pytest tests/unit/characterization/test_valuation_compute_golden.py -v`
Expected: 6 テスト全 PASS

- [ ] **Step 6: フルテスト通過確認**

Run: `uv run pytest tests/ -q 2>&1 | tail -3`
Expected: 既存 + 新規 = 647 passed (前タスク 641 + 6)

- [ ] **Step 7: コミット**

```bash
git add scripts/generate_fixtures/gen_valuation_golden.py tests/fixtures/valuation/ tests/unit/characterization/test_valuation_compute_golden.py
git commit -m "$(cat <<'EOF'
test: characterize compute_valuation_from_financials outputs

Phase A-2: 代表入力に対するゴールデン + 5つの境界/欠損値シナリオで
バリュエーション計算ロジックを保護。将来の valuation.py 再編から守る。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4 (PR3): CLI DI コンテナ組立てテスト

**Files:**
- Create: `tests/unit/characterization/test_container_assembly.py`
- Create: `tests/integration/conftest.py` (build_test_config ヘルパーを Phase C で流用するため早期作成)

- [ ] **Step 1: `build_test_config()` ヘルパーを作成**

`tests/integration/__init__.py` が無い場合は作成:

```bash
touch tests/integration/__init__.py
```

`tests/integration/conftest.py`:

```python
"""結合テスト共通フィクスチャ。

AppConfig のテスト用インスタンス生成と、外部クライアントモックを提供する。
本ファイルは Phase A-3 (container assembly) と Phase C (service assembly) で共有する。
"""
from __future__ import annotations

from stock_analyze_system.config import (
    AppConfig, DatabaseConfig, SecEdgarConfig, EdinetConfig, FmpConfig,
    YahooFinanceConfig, LlmConfig, FilingsConfig, LoggingConfig,
    WebConfig, PageIndexConfig,
)


def build_test_config(pageindex_enabled: bool = False) -> AppConfig:
    """テスト用の最小 AppConfig を返す。

    - 外部 API キーは空文字 (実通信が走らない初期化のみ確認)
    - PageIndex は引数で有効/無効切替
    - LLM は ollama デフォルト (初期化時通信なし)
    """
    return AppConfig(
        database=DatabaseConfig(path=":memory:"),
        sec_edgar=SecEdgarConfig(email="test@example.com"),
        edinet=EdinetConfig(api_key="test"),
        fmp=FmpConfig(api_key="test"),
        yahoo_finance=YahooFinanceConfig(),
        llm=LlmConfig(),
        filings=FilingsConfig(),
        logging=LoggingConfig(),
        web=WebConfig(session_secret="test-secret"),
        pageindex=PageIndexConfig(enabled=pageindex_enabled),
    )
```

- [ ] **Step 2: 特性化テストを書く**

`tests/unit/characterization/test_container_assembly.py`:

```python
"""setup_services() が組み立てる ServiceContainer の契約を固定するテスト。"""
from __future__ import annotations

import pytest

from stock_analyze_system.cli.container import ServiceContainer, setup_services
from tests.integration.conftest import build_test_config


@pytest.mark.characterization
class TestSetupServicesAssembly:
    async def test_returns_service_container_instance(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert isinstance(services, ServiceContainer)

    async def test_all_required_services_are_non_none(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert services.company_service is not None
        assert services.financial_service is not None
        assert services.valuation_service is not None
        assert services.filing_service is not None
        assert services.watchlist_service is not None
        assert services.target_service is not None
        assert services.job_service is not None
        assert services.financial_sync is not None
        assert services.filing_sync is not None

    async def test_rag_service_none_when_pageindex_disabled(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert services.rag_service is None

    async def test_rag_service_created_when_pageindex_enabled(self, session):
        config = build_test_config(pageindex_enabled=True)
        services = await setup_services(session, config)
        assert services.rag_service is not None
        # RAG service は PageIndexService を保持する
        assert hasattr(services.rag_service, "_pageindex_service") or \
               hasattr(services.rag_service, "pageindex_service")

    async def test_service_class_names_match_expected(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert type(services.company_service).__name__ == "CompanyService"
        assert type(services.financial_service).__name__ == "FinancialService"
        assert type(services.valuation_service).__name__ == "ValuationService"
        assert type(services.filing_service).__name__ == "FilingService"
        assert type(services.watchlist_service).__name__ == "WatchlistService"
        assert type(services.target_service).__name__ == "AnalysisTargetService"
        assert type(services.job_service).__name__ == "JobService"
        assert type(services.financial_sync).__name__ == "FinancialSyncService"
        assert type(services.filing_sync).__name__ == "FilingSyncService"

    async def test_screening_service_default_none(self, session):
        """Phase 5 未実装のため screening_service は None のまま"""
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)
        assert services.screening_service is None
```

**注意**: テストが `from tests.integration.conftest import build_test_config` で import しているが、pytest の標準では `tests.integration` パッケージを import できない場合がある。その場合は `tests/integration/__init__.py` を作成し、`pyproject.toml` の `[tool.pytest.ini_options].pythonpath` に `.` を追加するか、ヘルパーを `tests/integration/_helpers.py` として `conftest.py` とは別に配置する。

- [ ] **Step 3: テスト実行**

Run: `uv run pytest tests/unit/characterization/test_container_assembly.py -v`

もし `ImportError: No module named 'tests.integration.conftest'` が出た場合、`build_test_config` を `tests/integration/_config.py` という別モジュールに切り出し、conftest は `from ._config import build_test_config` で再エクスポートする。テスト側も `from tests.integration._config import build_test_config` に変更する。

Expected: 6 テスト全 PASS

- [ ] **Step 4: フルテスト通過確認**

Run: `uv run pytest tests/ -q 2>&1 | tail -3`
Expected: 647 + 6 = 653 passed

- [ ] **Step 5: コミット**

```bash
git add tests/integration/ tests/unit/characterization/test_container_assembly.py
git commit -m "$(cat <<'EOF'
test: characterize setup_services() DI container assembly

Phase A-3: ServiceContainer の組立て契約を固定。RAG 有効/無効分岐、
全必須サービスの存在、型名を検証。build_test_config ヘルパーを
Phase C で再利用する形で先出し配置。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5 (PR4): 検証レポート JSON スキーマ特性化テスト

**Files:**
- Create: `scripts/generate_fixtures/gen_verification_golden.py`
- Create: `tests/fixtures/reports/expected_verification.json`
- Create: `tests/fixtures/reports/README.md`
- Create: `tests/unit/characterization/test_verification_report_schema.py`

- [ ] **Step 1: ゴールデン生成スクリプトを作成**

`scripts/generate_fixtures/gen_verification_golden.py`:

```python
"""save_verification_report の出力 JSON ゴールデンを生成。"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from stock_analyze_system.services.verification_report import save_verification_report

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tests/fixtures/reports/expected_verification.json"

FIXED_TREE = {"doc_name": "10-K_2024_TEST"}
FIXED_LOG = [
    {
        "mode": "sampling",
        "accuracy": 0.95,
        "checked_count": 20,
        "correct_count": 19,
        "incorrect_count": 1,
        "items": [
            {
                "title": "売上高",
                "page_number": 42,
                "answer": "correct",
                "thinking": "matched financial statement",
                "page_text_snippet": "売上高は前年比...",
            }
        ],
    },
    {
        "mode": "full",
        "accuracy": 1.0,
        "checked_count": 100,
        "correct_count": 100,
        "incorrect_count": 0,
        "items": [],
    },
]


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = save_verification_report(
            company_id="US_AAPL", filing_id=42,
            tree=FIXED_TREE, verification_log=FIXED_LOG,
            node_count=123, output_dir=Path(tmp),
        )
        data = json.loads(path.read_text())
    # timestamp は実行時刻依存のため除外
    data["timestamp"] = "REDACTED"
    OUTPUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: ゴールデン生成**

```bash
uv run python scripts/generate_fixtures/gen_verification_golden.py
```

- [ ] **Step 3: README を作成**

`tests/fixtures/reports/README.md`:

```markdown
# Verification Report Fixtures

## Files
- `expected_verification.json`: `save_verification_report()` の出力 JSON スキーマゴールデン (timestamp は "REDACTED")

## 再生成
```bash
uv run python scripts/generate_fixtures/gen_verification_golden.py
```
```

- [ ] **Step 4: 特性化テストを書く**

`tests/unit/characterization/test_verification_report_schema.py`:

```python
"""検証レポート JSON スキーマを固定するテスト。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_analyze_system.services.verification_report import save_verification_report

FIXTURES = Path(__file__).parent.parent.parent / "fixtures/reports"

FIXED_TREE = {"doc_name": "10-K_2024_TEST"}
FIXED_LOG = [
    {
        "mode": "sampling",
        "accuracy": 0.95,
        "checked_count": 20,
        "correct_count": 19,
        "incorrect_count": 1,
        "items": [
            {
                "title": "売上高",
                "page_number": 42,
                "answer": "correct",
                "thinking": "matched financial statement",
                "page_text_snippet": "売上高は前年比...",
            }
        ],
    },
    {
        "mode": "full",
        "accuracy": 1.0,
        "checked_count": 100,
        "correct_count": 100,
        "incorrect_count": 0,
        "items": [],
    },
]


def _build_report(tmp_path: Path) -> dict:
    path = save_verification_report(
        company_id="US_AAPL", filing_id=42,
        tree=FIXED_TREE, verification_log=FIXED_LOG,
        node_count=123, output_dir=tmp_path,
    )
    return json.loads(path.read_text())


@pytest.mark.characterization
class TestVerificationReportSchema:
    def test_top_level_keys(self, tmp_path):
        data = _build_report(tmp_path)
        assert set(data.keys()) == {
            "company_id", "filing_id", "doc_name",
            "timestamp", "node_count", "phases",
        }
        assert isinstance(data["company_id"], str)
        assert isinstance(data["filing_id"], int)
        assert isinstance(data["node_count"], int)
        assert isinstance(data["phases"], list)

    def test_phase_schema(self, tmp_path):
        data = _build_report(tmp_path)
        phase = data["phases"][0]
        assert set(phase.keys()) == {
            "mode", "accuracy", "checked_count",
            "correct_count", "incorrect_count", "items",
        }
        assert isinstance(phase["items"], list)

    def test_item_schema(self, tmp_path):
        data = _build_report(tmp_path)
        item = data["phases"][0]["items"][0]
        assert set(item.keys()) == {
            "title", "page_number", "answer",
            "thinking", "page_text_snippet",
        }

    def test_matches_golden_snapshot(self, tmp_path):
        data = _build_report(tmp_path)
        expected = json.loads((FIXTURES / "expected_verification.json").read_text())
        # timestamp は実行時刻依存のため除外して比較
        data["timestamp"] = "REDACTED"
        assert data == expected

    def test_unicode_not_escaped(self, tmp_path):
        """ensure_ascii=False により日本語はエスケープされない"""
        path = save_verification_report(
            company_id="JP_X", filing_id=1,
            tree={"doc_name": "10-K"}, verification_log=FIXED_LOG,
            node_count=1, output_dir=tmp_path,
        )
        raw = path.read_text()
        assert "売上高" in raw
        assert "\\u58f2" not in raw

    def test_two_phases_preserved(self, tmp_path):
        data = _build_report(tmp_path)
        assert len(data["phases"]) == 2
        assert data["phases"][0]["mode"] == "sampling"
        assert data["phases"][1]["mode"] == "full"
```

- [ ] **Step 5: テスト実行**

Run: `uv run pytest tests/unit/characterization/test_verification_report_schema.py -v`
Expected: 6 テスト全 PASS

- [ ] **Step 6: フルテスト通過確認**

Run: `uv run pytest tests/ -q 2>&1 | tail -3`
Expected: 653 + 6 = 659 passed

- [ ] **Step 7: コミット**

```bash
git add scripts/generate_fixtures/gen_verification_golden.py tests/fixtures/reports/ tests/unit/characterization/test_verification_report_schema.py
git commit -m "$(cat <<'EOF'
test: characterize verification report JSON schema

Phase A-4: save_verification_report() の出力スキーマ (キー構成・型・
Unicode保存) を固定。外部ツール/ダッシュボードが参照する可能性があるため
契約として保護する。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6 (PR5): Enum 文字列互換性テスト

**Files:**
- Create: `tests/unit/characterization/test_enum_integration.py`

- [ ] **Step 1: 特性化テストを書く**

`tests/unit/characterization/test_enum_integration.py`:

```python
"""FilingType/PeriodType/AccountingStandard の文字列互換性を固定するテスト。

将来 StrEnum から別形式に変更された場合、argparse/DB/JSON/dict/set での
相互運用が壊れないか検知する。
"""
from __future__ import annotations

import argparse
import json

import pytest

from stock_analyze_system.cli.helpers import add_filing_type_argument
from stock_analyze_system.models.enums import (
    AccountingStandard, FilingType, PeriodType,
)
from stock_analyze_system.models.filing import Filing


@pytest.mark.characterization
class TestFilingTypeStringCompat:
    def test_enum_equals_plain_string(self):
        assert FilingType.TEN_K == "10-K"
        assert "10-K" == FilingType.TEN_K
        assert FilingType.TWENTY_F == "20-F"
        assert FilingType.TEN_Q == "10-Q"
        assert FilingType.SIX_K == "6-K"

    def test_enum_in_string_tuple(self):
        assert FilingType.TEN_K in ("10-K", "20-F")

    def test_string_in_enum_set(self):
        filed_forms = {FilingType.TEN_K, FilingType.TWENTY_F}
        assert "10-K" in filed_forms

    def test_dict_key_interchange(self):
        d = {FilingType.TEN_K: "annual_report"}
        assert d["10-K"] == "annual_report"

    def test_json_serializes_as_plain_string(self):
        data = {"type": FilingType.TEN_K}
        assert json.dumps(data) == '{"type": "10-K"}'


@pytest.mark.characterization
class TestFilingTypeArgparseIntegration:
    def _parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        add_filing_type_argument(parser)
        return parser

    def test_default_is_ten_k(self):
        args = self._parser().parse_args([])
        assert args.filing_type == FilingType.TEN_K
        assert args.filing_type == "10-K"

    def test_accepts_all_valid_values(self):
        for value in ("10-K", "10-Q", "20-F", "6-K"):
            args = self._parser().parse_args(["--filing-type", value])
            assert args.filing_type == value

    def test_rejects_invalid_value(self, capsys):
        with pytest.raises(SystemExit):
            self._parser().parse_args(["--filing-type", "INVALID_FORM"])


@pytest.mark.characterization
class TestPeriodType:
    def test_string_equivalence(self):
        assert PeriodType.ANNUAL == "annual"
        assert PeriodType.QUARTERLY == "quarterly"

    def test_in_tuple_comparison(self):
        assert PeriodType.ANNUAL in ("annual", "quarterly")

    def test_json_serialization(self):
        assert json.dumps({"p": PeriodType.ANNUAL}) == '{"p": "annual"}'


@pytest.mark.characterization
class TestAccountingStandard:
    def test_values(self):
        assert AccountingStandard.US_GAAP == "US-GAAP"
        assert AccountingStandard.IFRS == "IFRS"
        assert AccountingStandard.JP_GAAP == "JP-GAAP"

    def test_string_comparison_bidirectional(self):
        assert "US-GAAP" == AccountingStandard.US_GAAP


@pytest.mark.characterization
class TestFilingTypeDatabaseRoundtrip:
    async def test_saved_as_plain_string_and_readable_both_ways(self, session):
        """FilingType を DB に保存し、str としても enum としても比較できる"""
        # Company を先に作成 (Filing は company_id の FK を持つ)
        from stock_analyze_system.models.company import Company
        company = Company(
            id="US_TEST", ticker="TEST", name="Test Corp",
            country="US", accounting_standard="US-GAAP",
        )
        session.add(company)
        await session.commit()

        filing = Filing(
            company_id="US_TEST", filing_type=FilingType.TEN_K,
            fiscal_year=2024, filing_date="2024-03-01",
            accession_number="test-0001", source_url="http://test",
        )
        session.add(filing)
        await session.commit()
        filing_id = filing.id

        # 別リフレッシュで読み込み
        session.expire_all()
        loaded = await session.get(Filing, filing_id)
        assert loaded.filing_type == "10-K"
        assert loaded.filing_type == FilingType.TEN_K
```

**注意**: `Filing` / `Company` モデルの実フィールド名 (例: `filing_type` or `form_type`) を `src/stock_analyze_system/models/filing.py` で確認し、フィクスチャのフィールド名を合わせる。相違があれば実フィールド名にテストを合わせる (この Step で src を読んでから書く)。

- [ ] **Step 2: Filing / Company モデルのフィールド名を確認**

Run: `grep -n "filing_type\|form_type\|accession_number\|accounting_standard" src/stock_analyze_system/models/filing.py src/stock_analyze_system/models/company.py`

もし `form_type` が実際の名前だった場合、テスト側を `form_type=` に置換。`accounting_standard` が異なれば合わせる。

- [ ] **Step 3: テスト実行**

Run: `uv run pytest tests/unit/characterization/test_enum_integration.py -v`
Expected: 全 PASS (DB ラウンドトリップ含む)

- [ ] **Step 4: フルテスト通過確認**

Run: `uv run pytest tests/ -q 2>&1 | tail -3`
Expected: 659 + 14前後 = 約 673 passed

- [ ] **Step 5: コミット**

```bash
git add tests/unit/characterization/test_enum_integration.py
git commit -m "$(cat <<'EOF'
test: characterize StrEnum string compatibility across argparse/DB/JSON

Phase A-5: FilingType/PeriodType/AccountingStandard と plain str の
相互運用を argparse/JSON/dict/set/DB ラウンドトリップで検証。
将来 StrEnum から別形式に変更しても互換性ブレイクを検知できる。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7 (PR6): Web ルート・認証の未カバー分岐テスト

**Files:**
- Modify: `tests/unit/web/test_watchlists.py`
- Modify: `tests/unit/web/test_targets.py`
- Modify: `tests/unit/web/test_stocks.py`
- Modify: `tests/unit/web/test_dashboard.py`
- Modify: `tests/unit/web/test_rag.py`
- Modify: `tests/unit/web/test_api.py`
- Modify: `tests/unit/web/test_jobs.py`
- Modify: `tests/unit/web/test_auth.py`

- [ ] **Step 1: 現状の未カバー行を再確認**

Run: `uv run pytest --cov=stock_analyze_system.web --cov-report=term-missing tests/unit/web -q 2>&1 | grep -E "routes/|auth.py"`

各ファイルの未カバー行番号を把握する。

- [ ] **Step 2: 既存 `tests/unit/web/conftest.py` のパターンを確認**

Read: `tests/unit/web/conftest.py`
未ログイン状態の TestClient / ログイン済み TestClient の両 fixture の有無を確認。無ければ追加する。

- [ ] **Step 3: watchlists / targets / stocks / dashboard / rag に未ログインテスト追加**

各 `test_*.py` の末尾付近に以下パターンを追加 (5ファイル分):

```python
class TestUnauthenticatedRedirect:
    def test_get_requires_login(self, unauth_client):
        response = unauth_client.get("/watchlists", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"].startswith("/login")
```

対象エンドポイント:
- `test_watchlists.py`: `GET /watchlists`, `GET /watchlists/{id}`, `POST /watchlists`
- `test_targets.py`: `GET /targets`, `POST /targets`, `POST /targets/{id}/delete`
- `test_stocks.py`: `GET /stocks`, `GET /stocks/{ticker}`
- `test_dashboard.py`: `GET /` (ダッシュボード)
- `test_rag.py`: `GET /rag`

各エンドポイントが未ログイン時 302 → `/login` にリダイレクトすることを検証。

- [ ] **Step 4: test_api.py に 404/400 エラーパステスト追加**

`web/routes/api.py` の未カバー行 (83, 98, 107-112, 125-126, 139-143, 155-160) に対応する:

```python
class TestApiErrorPaths:
    def test_valuations_returns_404_when_company_not_found(self, auth_client):
        response = auth_client.get("/api/stocks/UNKNOWN_ID/valuations")
        assert response.status_code == 404

    def test_financials_returns_404_when_company_not_found(self, auth_client):
        response = auth_client.get("/api/stocks/UNKNOWN_ID/financials")
        assert response.status_code == 404

    def test_metrics_returns_404_when_company_not_found(self, auth_client):
        response = auth_client.get("/api/stocks/UNKNOWN_ID/metrics")
        assert response.status_code == 404

    def test_rag_analyses_returns_404_when_company_not_found(self, auth_client):
        response = auth_client.get("/api/stocks/UNKNOWN_ID/rag/analyses")
        assert response.status_code == 404
```

実装を確認してエンドポイント名を合わせる (`routes/api.py` を読む)。

- [ ] **Step 5: test_jobs.py に sync 失敗時の flash テスト追加**

`web/routes/jobs.py:52-54` は sync 失敗時のエラー flash 設定。mock で JobService が例外を投げるようにして検証:

```python
class TestJobSyncFailure:
    def test_filing_sync_failure_shows_error_flash(self, auth_client, monkeypatch):
        async def _fail(*args, **kwargs):
            raise RuntimeError("sync failed")
        # filing_sync モジュールの sync メソッドを失敗させる
        monkeypatch.setattr(
            "stock_analyze_system.services.filing_sync.FilingSyncService.sync_filings",
            _fail,
        )
        response = auth_client.post("/jobs/filing-sync", follow_redirects=False)
        # redirect (302) し、次のアクセスで flash が表示される
        assert response.status_code == 302
```

実装を確認してエンドポイント名 (`/jobs/filing-sync` or similar) とモック先を合わせる。

- [ ] **Step 6: test_auth.py に失敗系テスト追加**

`web/auth.py:69-71` (署名検証失敗) と `:80-86` (セッション無効/期限切れ) に対応:

```python
class TestAuthFailures:
    def test_invalid_signature_rejected(self):
        from stock_analyze_system.web.auth import verify_session_token
        # 改竄されたトークン
        bad_token = "valid_payload.invalid_signature"
        assert verify_session_token(bad_token, secret="test") is None

    def test_expired_session_rejected(self):
        from stock_analyze_system.web.auth import (
            create_session_token, verify_session_token,
        )
        import time
        token = create_session_token(
            user="admin", secret="test", ttl_seconds=0,
        )
        time.sleep(0.01)  # TTL=0 なので即座に期限切れ
        assert verify_session_token(token, secret="test") is None

    def test_malformed_token_rejected(self):
        from stock_analyze_system.web.auth import verify_session_token
        assert verify_session_token("not-a-valid-token", secret="test") is None
```

関数名が違う場合は `src/stock_analyze_system/web/auth.py` を読んで合わせる。

- [ ] **Step 7: テスト実行 (該当ファイルのみ)**

Run: `uv run pytest tests/unit/web -v 2>&1 | tail -30`
Expected: 既存 + 新規 (約 15 テスト) 全 PASS

- [ ] **Step 8: カバレッジ向上を確認**

Run: `uv run pytest --cov=stock_analyze_system.web --cov-report=term tests/unit/web -q 2>&1 | grep -E "routes/|auth.py|TOTAL"`

`watchlists.py` / `targets.py` / `stocks.py` / `dashboard.py` / `rag.py` / `api.py` / `auth.py` が 90% 以上になっていることを確認。

- [ ] **Step 9: フルテスト通過確認**

Run: `uv run pytest tests/ -q 2>&1 | tail -3`
Expected: 約 688 passed (前タスク 673 + 15)

- [ ] **Step 10: コミット**

```bash
git add tests/unit/web/
git commit -m "$(cat <<'EOF'
test: cover missing branches in web routes & auth

Phase B-1: 未ログインリダイレクト (5ルート)、API 404エラー (4エンドポイント)、
Jobs sync 失敗時 flash、認証の署名無効/期限切れ/不正トークン分岐を追加。
Web 関連カバレッジを 68-86% → 90%+ に引き上げ。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8 (PR7): CLI・ingestion の未カバー分岐テスト + pragma 除外

**Files:**
- Modify: `tests/unit/cli/test_watchlist_cli.py`
- Modify: `tests/unit/cli/test_valuation_cli.py`
- Modify: `tests/unit/cli/test_financial_cli.py`
- Modify: `tests/unit/ingestion/test_edinet_xbrl_parser.py`
- Modify: `tests/unit/ingestion/test_sec_edgar.py`
- Modify: `tests/unit/services/test_pageindex_service.py` (repository 経由のカバーも確認)
- Modify: `src/stock_analyze_system/services/pageindex_service.py` (pragma コメント追加のみ)
- Modify: `src/stock_analyze_system/models/base.py` (pragma コメント追加のみ)

- [ ] **Step 1: PageIndexService に pragma 除外を追加**

`src/stock_analyze_system/services/pageindex_service.py:242-292` (`_build_index_async` メソッド) の関数定義行末に `# pragma: no cover` 相当は Python では難しいため、ブロック冒頭に `# pragma: no cover` コメントを追加する coverage 設定を利用する。

**推奨方法**: `.coveragerc` または `pyproject.toml` で exclude lines を増やす。既存の pyproject を確認し、次のエントリを追加:

`pyproject.toml` に `[tool.coverage.run]` と `[tool.coverage.report]` セクションを追加:

```toml
[tool.coverage.run]
source = ["stock_analyze_system"]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.:",
]
exclude_also = [
    # PageIndex lib の外部 async builder 呼び出しは実環境 llama-server 依存
    # でテスト困難 (integration/test_llamacpp_server.py で疎通のみ検証)
    "def _build_index_async",
    "async def _generate_summaries_safe",
    # SQLAlchemy sync fallback はフルプロジェクトで async 前提
    "def get_sync_session",
]
```

**代わりにインラインで pragma コメントを付ける場合** (上記が使えない coverage バージョンなら):

`pageindex_service.py:240-297` の該当メソッド定義冒頭行末に:
```python
    async def _build_index_async(self, pdf_path: str, model: str) -> dict:  # pragma: no cover
```

`:298-347` の `_generate_summaries_safe`:
```python
    async def _generate_summaries_safe(  # pragma: no cover
        self,
```

この場合、メソッド本体全体が除外対象になる (coverage.py の挙動: `pragma: no cover` 付き定義行は関数全体を除外)。

- [ ] **Step 2: models/base.py に pragma 追加**

`src/stock_analyze_system/models/base.py:38-42` (sync fallback) の該当行末に `# pragma: no cover` を追加。該当行を実ファイルで確認した上で追記する。

- [ ] **Step 3: pragma 適用後のカバレッジ確認**

Run: `uv run pytest --cov=stock_analyze_system.services.pageindex_service --cov=stock_analyze_system.models.base --cov-report=term -q 2>&1 | tail -10`

Expected: `pageindex_service.py` は 77% → 95%+ に上がる。`models/base.py` も 92% → 100% 近くに。

- [ ] **Step 4: cli/watchlist_cli エラーパステスト追加**

未カバー行 (44, 66, 74-75, 82, 90-91, 100, 109, 117-119) は主に "指定された watchlist が存在しない"、"company が存在しない" 系のエラー出力。

`tests/unit/cli/test_watchlist_cli.py` 末尾付近に追加:

```python
class TestWatchlistCliErrorPaths:
    async def test_add_item_unknown_watchlist_exits(self, capsys, make_services):
        services = make_services()
        services.watchlist_service.get_watchlist.return_value = None
        with pytest.raises(SystemExit):
            await watchlist_add_item_handler(
                services,
                argparse.Namespace(watchlist_id=999, company_id="US_X"),
            )
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower() or "存在" in captured.err

    async def test_remove_item_unknown_watchlist_exits(self, capsys, make_services):
        # 同様のパターン
        ...

    async def test_delete_watchlist_unknown_exits(self, capsys, make_services):
        ...
```

実 CLI 関数名 (例: `_handle_watchlist_add`, `_watchlist_add_item`) は `src/stock_analyze_system/cli/watchlist.py` を読んで確認する。

- [ ] **Step 5: cli/valuation_cli エラーパステスト追加**

未カバー行 (30, 41-42, 45, 61, 70-71, 74-75, 77, 103) に対応する失敗パスのテストを追加。

- [ ] **Step 6: cli/financial_cli バリデーションテスト追加**

`cli/financial.py` の choices 違反や欠損値の分岐を検証。

- [ ] **Step 7: ingestion/edinet_xbrl_parser 重要分岐テスト追加**

未カバー行 19 行のうち、ログのみ/防御的 except は pragma 除外、データ分岐 (XML 欠損タグ、period 決定ロジック) はテスト追加。

具体的には `tests/unit/ingestion/test_edinet_xbrl_parser.py` に以下のようなケースを追加:

```python
class TestEdinetXbrlParserBranches:
    def test_missing_context_returns_empty(self):
        """context が XML に無い場合は空結果"""
        ...

    def test_unknown_period_type_skipped(self):
        ...
```

実コードを読んで該当分岐に対応するテストを書く。

- [ ] **Step 8: ingestion/sec_edgar リトライ・エラーテスト追加**

未カバー行 (57-58, 68, 93-95) に対応する (リトライ時のログ、API エラー時のハンドリング)。

```python
class TestSecEdgarErrorHandling:
    async def test_retries_on_503(self, respx_mock): ...
    async def test_empty_response_returns_empty_list(self, respx_mock): ...
```

- [ ] **Step 9: フルテスト通過確認 + カバレッジ確認**

Run: `uv run pytest tests/ -q 2>&1 | tail -3`
Expected: 約 705-710 passed

Run: `uv run pytest --cov=stock_analyze_system --cov-report=term tests/ -q 2>&1 | tail -15`
Expected: 全体カバレッジ 92% → 96-98%

- [ ] **Step 10: コミット**

```bash
git add src/stock_analyze_system/services/pageindex_service.py src/stock_analyze_system/models/base.py pyproject.toml tests/unit/cli/ tests/unit/ingestion/
git commit -m "$(cat <<'EOF'
test: cover missing branches in CLI/ingestion + pragma exclusions

Phase B-2: CLI エラーパス (watchlist/valuation/financial)、ingestion
分岐テスト (edinet_xbrl/sec_edgar) を追加。PageIndex 外部 lib 呼び出し部と
SQLAlchemy sync fallback を # pragma: no cover で除外 (ロジック不変)。
全体カバレッジ 92% → ~97% に到達。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9 (PR8): Service 組立て層結合テスト

**Files:**
- Modify: `tests/integration/conftest.py` (外部クライアントモック factory を追加)
- Create: `tests/integration/test_service_assembly.py`

- [ ] **Step 1: 外部クライアントモックを conftest に追加**

`tests/integration/conftest.py` に追記 (Task 4 で作成したファイルに append):

```python
import pytest


class _MockSecClient:
    def __init__(self):
        self._filings = []
        self._facts = {"facts": {"us-gaap": {}}}

    def set_filings(self, data): self._filings = data
    def set_company_facts(self, data): self._facts = data

    async def fetch_filings(self, cik, form_type=None): return self._filings
    async def fetch_company_facts(self, cik): return self._facts
    async def fetch_cik_by_ticker(self, ticker): return "0000000001"


class _MockEdinetClient:
    async def fetch_filings(self, *args, **kwargs): return []
    async def fetch_xbrl(self, *args, **kwargs): return b""


class _MockYahooClient:
    async def fetch_quote(self, ticker): return {"price": 150.0}
    async def fetch_historical(self, *args, **kwargs): return []


class _MockFmpClient:
    async def fetch_ratios(self, *args, **kwargs): return []
    async def fetch_profile(self, *args, **kwargs): return {}


@pytest.fixture
def mock_sec_client(monkeypatch):
    mock = _MockSecClient()
    monkeypatch.setattr(
        "stock_analyze_system.cli.container.SecEdgarClient",
        lambda **kw: mock,
    )
    return mock


@pytest.fixture
def mock_edinet_client(monkeypatch):
    mock = _MockEdinetClient()
    monkeypatch.setattr(
        "stock_analyze_system.cli.container.EdinetClient",
        lambda **kw: mock,
    )
    return mock


@pytest.fixture
def mock_yahoo_client(monkeypatch):
    mock = _MockYahooClient()
    monkeypatch.setattr(
        "stock_analyze_system.cli.container.YahooFinanceClient",
        lambda **kw: mock,
    )
    return mock


@pytest.fixture
def mock_fmp_client(monkeypatch):
    mock = _MockFmpClient()
    monkeypatch.setattr(
        "stock_analyze_system.cli.container.FmpClient",
        lambda **kw: mock,
    )
    return mock


@pytest.fixture
def all_mock_clients(mock_sec_client, mock_edinet_client, mock_yahoo_client, mock_fmp_client):
    """4 外部クライアントを一度にモックするヘルパー"""
    return {
        "sec": mock_sec_client,
        "edinet": mock_edinet_client,
        "yahoo": mock_yahoo_client,
        "fmp": mock_fmp_client,
    }
```

- [ ] **Step 2: 結合テスト 3 シナリオを書く**

`tests/integration/test_service_assembly.py`:

```python
"""Service 組立て層の結合テスト。

setup_services() で実組み立てした ServiceContainer を使い、
in-memory SQLite 上で複数サービス協調シナリオを検証する。
外部 API はモック、LLM は呼ばない (PageIndex 無効)。
"""
from __future__ import annotations

import pytest

from stock_analyze_system.cli.container import setup_services
from stock_analyze_system.models.enums import FilingType, PeriodType
from tests.integration.conftest import build_test_config


@pytest.mark.integration
class TestFullSyncFlow:
    async def test_company_filings_flow(self, session, all_mock_clients):
        """企業登録 → Filings sync (SEC モック) → 永続化"""
        all_mock_clients["sec"].set_filings([
            {
                "accessionNumber": "0000320193-23-000106",
                "form": "10-K",
                "filingDate": "2023-11-03",
                "primaryDocument": "aapl-20230930.htm",
            },
        ])
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)

        # 1. 企業を作成
        await services.company_service.create_company(
            id="US_TEST", ticker="TEST", name="Test Corp",
            country="US", accounting_standard="US-GAAP",
            cik="0000320193",
        )

        # 2. Filings を sync (モックが1件返す)
        synced = await services.filing_sync.sync_filings(
            "US_TEST", filing_type=FilingType.TEN_K,
        )
        assert synced.created_count == 1

        # 3. DB 永続化を確認 (別の filing_service で読む)
        filings = await services.filing_service.list_filings("US_TEST")
        assert len(filings) == 1
        assert filings[0].filing_type == FilingType.TEN_K


@pytest.mark.integration
class TestWatchlistTargetFlow:
    async def test_watchlist_with_items_persistence(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)

        await services.company_service.create_company(
            id="US_A", ticker="A", name="A Corp",
            country="US", accounting_standard="US-GAAP",
        )
        await services.company_service.create_company(
            id="US_B", ticker="B", name="B Corp",
            country="US", accounting_standard="US-GAAP",
        )

        wl = await services.watchlist_service.create_watchlist(name="Tech")
        await services.watchlist_service.add_item(wl.id, "US_A")
        await services.watchlist_service.add_item(wl.id, "US_B")

        reloaded = await services.watchlist_service.get_watchlist(wl.id)
        assert reloaded is not None
        assert len(reloaded.items) == 2

    async def test_analysis_target_registration(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)

        await services.company_service.create_company(
            id="US_A", ticker="A", name="A Corp",
            country="US", accounting_standard="US-GAAP",
        )

        await services.target_service.add_target("US_A", priority=1)
        targets = await services.target_service.list_targets()
        assert any(t.company_id == "US_A" for t in targets)


@pytest.mark.integration
class TestRagDisabledFallback:
    async def test_non_rag_features_work_with_rag_disabled(self, session):
        config = build_test_config(pageindex_enabled=False)
        services = await setup_services(session, config)

        assert services.rag_service is None
        assert services.company_service is not None

        await services.company_service.create_company(
            id="US_X", ticker="X", name="X Corp",
            country="US", accounting_standard="US-GAAP",
        )
        company = await services.company_service.get_company("US_X")
        assert company is not None
        assert company.ticker == "X"

    async def test_rag_service_assembled_when_enabled(self, session):
        config = build_test_config(pageindex_enabled=True)
        services = await setup_services(session, config)

        assert services.rag_service is not None
        # rag_service は PageIndexService を保持する
        assert hasattr(services.rag_service, "_pageindex_service") or \
               hasattr(services.rag_service, "pageindex_service")
```

**注意**:
- `CompanyService.create_company()` / `WatchlistService.create_watchlist()` / `AnalysisTargetService.add_target()` / `FilingSyncService.sync_filings()` の実際のメソッドシグネチャは実 src を読んで合わせる (キーワード引数名・必須引数)。
- `Company` モデルのコンストラクタ必須フィールドは `models/company.py` で確認。不足フィールドがあれば追加 (例: `sector`, `industry`)。
- `sync_filings` の戻り値 (`created_count` プロパティを持つか) は `services/filing_sync.py` を確認。

- [ ] **Step 3: シグネチャ確認と修正**

各サービスメソッドのシグネチャを実 src で確認し、テストの引数を合わせる:

```bash
grep -n "def create_company\|async def sync_filings\|async def create_watchlist\|async def add_target\|async def add_item\|async def list_filings" src/stock_analyze_system/services/*.py
```

必要があればテスト引数を修正。

- [ ] **Step 4: テスト実行**

Run: `uv run pytest tests/integration/test_service_assembly.py -v`
Expected: 5 テスト全 PASS

エラーがあれば:
1. `ImportError: build_test_config` → Task 4 の結論通り `_config.py` 分離パターンを使う
2. DB FK エラー → Company 作成時の必須フィールドを追加
3. モック差し替えが効かない → `monkeypatch.setattr` の参照パスを `cli.container.SecEdgarClient` で一致させる (`container.py` での `import` スタイルに依存)

- [ ] **Step 5: カバレッジ確認 (補助)**

Run: `uv run pytest --cov=stock_analyze_system --cov-report=term -m integration tests/integration/test_service_assembly.py -q 2>&1 | tail -10`

**注意**: 結合テストの目的はカバレッジ底上げではなく「複数サービス協調の回帰検知」。数値は参考値にとどめる。

- [ ] **Step 6: フルテスト通過確認**

Run: `uv run pytest tests/ -q 2>&1 | tail -3`
Expected: 約 715 passed

Run: `uv run pytest -m integration tests/ -q 2>&1 | tail -3`
Expected: `6 passed` (既存 1 + 新規 5)

Run: `uv run pytest -m characterization tests/ -q 2>&1 | tail -3`
Expected: 約 44 passed (Task 2-6 合計)

- [ ] **Step 7: コミット**

```bash
git add tests/integration/
git commit -m "$(cat <<'EOF'
test: add service-layer integration tests via setup_services()

Phase C: container.setup_services() でサービスを実組み立てし、
in-memory SQLite 上で 3 協調シナリオ (full sync / watchlist+target
永続化 / RAG 有効無効) を検証。外部 API はモック、CLI/Web 表層は
含めない Service 層限定の結合テスト。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: 仕上げ (最終検証)

**Files:** — (ソース変更なし)

- [ ] **Step 1: 全テスト通過の最終確認**

Run: `uv run pytest tests/ -v --tb=short 2>&1 | tail -20`
Expected: 全 PASS、追加 ~85 テスト (characterization 約 44 + Phase B 約 30 + Phase C 5 + Task 1 マーカーは既存テストに 0 追加)

- [ ] **Step 2: マーカー単独実行確認**

```bash
uv run pytest -m characterization tests/ -q
uv run pytest -m integration tests/ -q
uv run pytest -m "not characterization and not integration" tests/ -q
```

それぞれが正しく絞り込まれることを確認。合計値が Step 1 と一致すること。

- [ ] **Step 3: 最終カバレッジレポート**

Run: `uv run pytest --cov=stock_analyze_system --cov-report=term --cov-report=html tests/ -q 2>&1 | tail -20`

- 全体カバレッジ **≥ 96%** を確認
- `htmlcov/index.html` を目視 (任意)
- 90% を切るモジュールが無いか確認。あれば Phase B で見落としたので追加検討

- [ ] **Step 4: ruff lint 確認**

Run: `uv run ruff check src/ tests/`
Expected: エラーなし

- [ ] **Step 5: 完了チェックリスト記録 (spec に追記)**

`docs/superpowers/specs/2026-04-18-test-coverage-strengthening-design.md` の「5-5. 完了の定義」セクションで以下を `[x]` にマーク:
- Phase A 5 PR すべてマージ済み
- Phase B 2 PR マージ済み
- Phase C 1 PR マージ済み
- `pytest tests/ -v` 全件通過
- `uv run pytest --cov` で 96% 以上
- `tests/fixtures/` 配下に再生成手順 README 完備
- `docs/superpowers/plans/2026-04-18-test-coverage-strengthening.md` (本ファイル) コミット済み

- [ ] **Step 6: 完了コミット**

```bash
git add docs/superpowers/specs/2026-04-18-test-coverage-strengthening-design.md
git commit -m "$(cat <<'EOF'
docs: mark test coverage strengthening complete

全 Phase (A: 5領域特性化 / B: 分岐潰し + pragma / C: 結合テスト 3 シナリオ)
を完了。テスト数 632 → ~715、カバレッジ 92% → ~97%。
今後のリファクタリングを安全に実施できる基盤が整った。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## 依存関係と実行順序

```
Task 1 (setup)
  ↓
Task 2 ─┬─ Task 3 ─┬─ Task 4 ─┬─ Task 5 ─┬─ Task 6   (Phase A: 5 領域、並行可能)
  ↓                              ↓ (Task 4 の build_test_config は Task 9 で再利用)
                               Task 7              (Phase B-1: Web)
                                   ↓
                               Task 8              (Phase B-2: CLI/ingestion + pragma)
                                   ↓
                               Task 9              (Phase C: integration)
                                   ↓
                               Task 10             (最終検証)
```

**並行実行の注意**: Task 2-6 は互いに独立だが、subagent-driven 実行では 1 Task ずつ逐次推奨 (ゴールデン生成失敗の影響範囲を限定するため)。

---

## Troubleshooting

| 症状 | 原因候補 | 対処 |
|------|---------|------|
| `from tests.integration.conftest import build_test_config` で ImportError | conftest.py は pytest 専用で直接 import 不可 | `tests/integration/_config.py` に `build_test_config` を切り出し、conftest はそこから再エクスポート。テスト側も `_config.py` から import |
| Filing モデルの属性エラー (`filing_type` vs `form_type`) | 実モデル定義との乖離 | `src/stock_analyze_system/models/filing.py` を確認して実フィールド名に合わせる |
| `monkeypatch.setattr` で外部クライアントモックが効かない | `container.py` 内 `from X import Y` スタイルだと参照先はローカル変数 | `"stock_analyze_system.cli.container.SecEdgarClient"` の参照先を `container.py` での import 方法に合わせる。`from X import Y` なら `"container.Y"`、`import X; X.Y()` なら `"X.Y"` |
| ゴールデン JSON が実行ごとに変わる | timestamp / 浮動小数の丸め | スクリプト側で timestamp を固定または除外。浮動小数は `round(x, 6)` 等で正規化 |
| PageIndex enabled=True のテストが外部通信で失敗 | LlmClient 初期化時に LM Studio に接続を試みる | `LlmConfig(backend="ollama")` のままなら初期化時通信はなし。それでも失敗するなら `PageIndexConfig(enabled=True, backend="ollama", lm_studio_base_url="http://localhost:1")` で到達不能な URL を設定し、初期化のみで通信しないことを確認 |
| pragma が coverage に反映されない | coverage 設定不足 | `pyproject.toml` の `[tool.coverage.report].exclude_lines` に `"pragma: no cover"` が含まれることを確認 |
