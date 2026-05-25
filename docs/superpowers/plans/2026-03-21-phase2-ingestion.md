# Phase 2: データ取得層 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SEC EDGAR、EDINET、Yahoo Finance、FMP の非同期データ取得クライアントとXBRLパーサーを構築する

**Architecture:** 全クライアントは `BaseClient` を継承し `AsyncRateLimiter` + httpx.AsyncClient で非同期HTTP通信。パーサーは純粋関数（同期、I/O不要）。YahooFinance は yfinance(同期) を `asyncio.to_thread()` でラップ。

**Tech Stack:** Python 3.10+, httpx (async), yfinance, PyYAML, pytest-asyncio, pytest-httpx

**Spec:** `docs/superpowers/specs/2026-03-21-stock-analyze-system-design.md` セクション5

**Reference project:** `<legacy-stock-analyzer-repo>/src/stock_analyzer/ingestion/` — 潜在バグ調査済み

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/stock_analyze_system/ingestion/__init__.py` | パッケージ初期化 |
| Create | `src/stock_analyze_system/ingestion/base.py` | AsyncRateLimiter + BaseClient |
| Create | `src/stock_analyze_system/ingestion/sec_edgar.py` | SEC EDGAR API クライアント |
| Create | `src/stock_analyze_system/ingestion/sec_xbrl_parser.py` | SEC XBRL パーサー |
| Create | `src/stock_analyze_system/ingestion/edinet.py` | EDINET API クライアント |
| Create | `src/stock_analyze_system/ingestion/edinet_xbrl_parser.py` | EDINET XBRL パーサー |
| Create | `src/stock_analyze_system/ingestion/yahoo_finance.py` | Yahoo Finance クライアント |
| Create | `src/stock_analyze_system/ingestion/fmp.py` | FMP API クライアント |
| Create | `config/us_gaap_mapping.yaml` | US-GAAP XBRL タグマッピング |
| Create | `config/ifrs_mapping.yaml` | IFRS XBRL タグマッピング |
| Create | `config/edinet_taxonomy_mapping.yaml` | EDINET タクソノミマッピング |
| Create | `tests/unit/ingestion/__init__.py` | テストパッケージ |
| Create | `tests/unit/ingestion/test_base.py` | AsyncRateLimiter + BaseClient テスト |
| Create | `tests/unit/ingestion/test_sec_xbrl_parser.py` | SEC XBRL パーサーテスト |
| Create | `tests/unit/ingestion/test_sec_edgar.py` | SEC EDGAR クライアントテスト |
| Create | `tests/unit/ingestion/test_edinet_xbrl_parser.py` | EDINET XBRL パーサーテスト |
| Create | `tests/unit/ingestion/test_edinet.py` | EDINET クライアントテスト |
| Create | `tests/unit/ingestion/test_yahoo_finance.py` | Yahoo Finance テスト |
| Create | `tests/unit/ingestion/test_fmp.py` | FMP クライアントテスト |

---

## 参考プロジェクト潜在バグ調査結果

Phase 2 開始時の `<legacy-stock-analyzer-repo>/src/stock_analyzer/ingestion/` 調査で発見した問題:

| # | ファイル | 問題 | 対策 |
|---|---------|------|------|
| 既知#10 | `edinet.py` | APIキー未設定時に無通知スキップ | WARNINGログ + スキップ理由返却 |
| 既知#18 | `sec_edgar.py` | `get_submissions` でファイリングページネーション未対応。`filings.files` の追加JSONを取得していない | `filings.files[]` の追加ページもフェッチして結合 |
| 既知#19 | `edinet_xbrl_parser.py` | XBRLコンテキスト未考慮。連結/単体の判別なし | コンテキスト要素で連結優先判別 |
| 新発見1 | `base.py` | `RateLimiter` が同期 (`time.sleep`)。async環境でブロッキング | `asyncio.sleep` ベースに変更 |
| 新発見2 | `base.py` | `RetryClient` が同期 `httpx.Client` 使用 | `httpx.AsyncClient` に変更 |
| 新発見3 | `yahoo_finance.py` | FCF導出で capex 符号未検証。`op_cf + capex` は capex が負前提 | `abs(capex)` で安全に導出 |
| 新発見4 | `sec_edgar.py` | `list_filings` で並列リストのインデックス長さ未検証 | `zip()` で安全にイテレート |
| 新発見5 | `sec_xbrl_parser.py` | `_merge_near_dates` で同一フィールドの値が黙って破棄される | ログ出力で可視化 |
| 新発見6 | `edinet.py` | `search_company_filings` が日単位ループで遅い | 月単位バッチ or 並行リクエスト（Phase 3で最適化） |

---

### Task 1: AsyncRateLimiter + BaseClient

**Files:**
- Create: `src/stock_analyze_system/ingestion/__init__.py`
- Create: `src/stock_analyze_system/ingestion/base.py`
- Create: `tests/unit/ingestion/__init__.py`
- Create: `tests/unit/ingestion/test_base.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/ingestion/test_base.py
"""AsyncRateLimiter + BaseClient のテスト"""
import asyncio
import time

import httpx
import pytest

from stock_analyze_system.ingestion.base import AsyncRateLimiter, BaseClient


class TestAsyncRateLimiter:
    async def test_first_acquire_immediate(self):
        limiter = AsyncRateLimiter(rate=10, interval=1.0)
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    async def test_rate_limiting_delays(self):
        limiter = AsyncRateLimiter(rate=2, interval=1.0)
        await limiter.acquire()
        await limiter.acquire()
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.3  # should wait ~0.5s

    async def test_zero_rate_raises(self):
        with pytest.raises(ValueError):
            AsyncRateLimiter(rate=0, interval=1.0)


class TestBaseClient:
    async def test_get_success(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/api", json={"ok": True})
        async with BaseClient(rate=10) as client:
            resp = await client._get("https://example.com/api")
            assert resp.status_code == 200
            assert resp.json() == {"ok": True}

    async def test_retry_on_429(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/api", status_code=429)
        httpx_mock.add_response(url="https://example.com/api", json={"ok": True})
        async with BaseClient(rate=10, max_retries=2, initial_backoff=0.01) as client:
            resp = await client._get("https://example.com/api")
            assert resp.status_code == 200

    async def test_retry_on_503(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/api", status_code=503)
        httpx_mock.add_response(url="https://example.com/api", json={"ok": True})
        async with BaseClient(rate=10, max_retries=2, initial_backoff=0.01) as client:
            resp = await client._get("https://example.com/api")
            assert resp.status_code == 200

    async def test_max_retries_exceeded(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/api", status_code=429)
        httpx_mock.add_response(url="https://example.com/api", status_code=429)
        httpx_mock.add_response(url="https://example.com/api", status_code=429)
        from stock_analyze_system.exceptions import ApiConnectionError
        async with BaseClient(rate=10, max_retries=2, initial_backoff=0.01) as client:
            with pytest.raises(ApiConnectionError):
                await client._get("https://example.com/api")

    async def test_no_retry_on_404(self, httpx_mock):
        """404等の非リトライ対象ステータスはリトライしない（M1修正）"""
        httpx_mock.add_response(url="https://example.com/api", status_code=404)
        import httpx as httpx_lib
        async with BaseClient(rate=10, max_retries=3, initial_backoff=0.01) as client:
            with pytest.raises(httpx_lib.HTTPStatusError):
                await client._get("https://example.com/api")

    async def test_custom_headers(self, httpx_mock):
        httpx_mock.add_response(url="https://example.com/api")
        async with BaseClient(rate=10, headers={"User-Agent": "TestBot"}) as client:
            await client._get("https://example.com/api")
        request = httpx_mock.get_request()
        assert request.headers["User-Agent"] == "TestBot"

    async def test_context_manager(self):
        client = BaseClient(rate=10)
        async with client:
            assert client._client is not None
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 実装**

```python
# src/stock_analyze_system/ingestion/__init__.py
```

```python
# src/stock_analyze_system/ingestion/base.py
"""非同期レートリミッター + HTTP基底クライアント"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from stock_analyze_system.exceptions import ApiConnectionError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 503}


class AsyncRateLimiter:
    """asyncio.sleep ベースのトークンバケットレートリミッター"""

    def __init__(self, rate: float, interval: float = 1.0):
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = rate
        self._interval = interval
        self._allowance = rate
        self._last_check = time.monotonic()

    async def acquire(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_check
        self._last_check = now
        self._allowance += elapsed * (self._rate / self._interval)
        if self._allowance > self._rate:
            self._allowance = self._rate
        if self._allowance < 1.0:
            wait = (1.0 - self._allowance) * (self._interval / self._rate)
            await asyncio.sleep(wait)
            self._allowance = 0.0
        else:
            self._allowance -= 1.0


class BaseClient:
    """全APIクライアントの基底クラス（httpx.AsyncClient + リトライ）"""

    def __init__(
        self,
        rate: float = 5.0,
        interval: float = 1.0,
        max_retries: int = 3,
        initial_backoff: float = 2.0,
        max_backoff: float = 60.0,
        headers: dict[str, str] | None = None,
    ):
        self._rate_limiter = AsyncRateLimiter(rate=rate, interval=interval)
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff
        self._max_backoff = max_backoff
        self._headers = headers or {}
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers=self._headers,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._client

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self._request("POST", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """HTTPリクエスト + 指数バックオフリトライ。

        max_retries はリトライ回数（初回含まず）。合計試行回数 = 1 + max_retries。
        リトライ対象は RETRYABLE_STATUS_CODES (429, 503) と接続エラーのみ。
        404等の非リトライ対象エラーは即座に raise する。
        """
        client = await self._ensure_client()
        backoff = self._initial_backoff
        last_exc: Exception | None = None
        total_attempts = 1 + self._max_retries

        for attempt in range(total_attempts):
            await self._rate_limiter.acquire()
            try:
                response = await client.request(method, url, **kwargs)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_exc = ApiConnectionError(
                        f"Retryable status {response.status_code} from {url}"
                    )
                    logger.warning(
                        "Retryable status %d from %s (attempt %d/%d)",
                        response.status_code, url, attempt + 1, total_attempts,
                    )
                else:
                    response.raise_for_status()
                    return response
            except httpx.HTTPStatusError:
                # 非リトライ対象ステータスエラー（404等）は即座に raise
                raise
            except httpx.HTTPError as exc:
                # 接続/タイムアウトエラーはリトライ対象
                last_exc = exc
                logger.warning(
                    "HTTP error from %s (attempt %d/%d): %s",
                    url, attempt + 1, total_attempts, exc,
                )
            if attempt < total_attempts - 1:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff)

        raise ApiConnectionError(
            f"Max retries ({self._max_retries}) exceeded for {url}"
        ) from last_exc

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        await self._ensure_client()
        return self

    async def __aexit__(self, *args):
        await self.close()
```

- [ ] **Step 4: テスト通過を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_base.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/ingestion/ tests/unit/ingestion/
git commit -m "feat: add AsyncRateLimiter and BaseClient for ingestion layer"
```

---

### Task 2: タクソノミマッピングYAML

**Files:**
- Create: `config/us_gaap_mapping.yaml`
- Create: `config/ifrs_mapping.yaml`
- Create: `config/edinet_taxonomy_mapping.yaml`

- [ ] **Step 1: US-GAAP マッピングを作成**

```yaml
# config/us_gaap_mapping.yaml
revenue:
  - us-gaap:Revenues
  - us-gaap:SalesRevenueNet
  - us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax
operating_income:
  - us-gaap:OperatingIncomeLoss
net_income:
  - us-gaap:NetIncomeLoss
  - us-gaap:ProfitLoss
total_assets:
  - us-gaap:Assets
equity:
  - us-gaap:StockholdersEquity
  - us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest
current_assets:
  - us-gaap:AssetsCurrent
current_liabilities:
  - us-gaap:LiabilitiesCurrent
total_debt:
  - us-gaap:Debt
  - us-gaap:LongTermDebt
  - us-gaap:DebtCurrent
cash:
  - us-gaap:CashAndCashEquivalentsAtCarryingValue
  - us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents
inventory:
  - us-gaap:InventoryNet
cogs:
  - us-gaap:CostOfGoodsAndServicesSold
  - us-gaap:CostOfRevenue
operating_cf:
  - us-gaap:NetCashProvidedByUsedInOperatingActivities
capex:
  - us-gaap:PaymentsToAcquirePropertyPlantAndEquipment
  - us-gaap:PaymentsToAcquireProductiveAssets
ebitda:
  - us-gaap:EarningsBeforeInterestTaxesDepreciationAmortization
eps:
  - us-gaap:EarningsPerShareDiluted
  - us-gaap:EarningsPerShareBasic
dps:
  - us-gaap:CommonStockDividendsPerShareDeclared
  - us-gaap:CommonStockDividendsPerShareCashPaid
tax_expense:
  - us-gaap:IncomeTaxExpenseBenefit
income_before_tax:
  - us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest
  - us-gaap:IncomeBeforeIncomeTaxes
shares_outstanding:
  - us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding
  - us-gaap:WeightedAverageNumberOfSharesOutstandingBasic
  - us-gaap:CommonStockSharesOutstanding
dividends_paid:
  - us-gaap:PaymentsOfDividends
  - us-gaap:PaymentsOfDividendsCommonStock
share_repurchases:
  - us-gaap:PaymentsForRepurchaseOfCommonStock
  - us-gaap:TreasuryStockPurchased
```

- [ ] **Step 2: IFRS マッピングを作成**

```yaml
# config/ifrs_mapping.yaml
revenue:
  - ifrs-full:Revenue
  - ifrs-full:RevenueFromContractsWithCustomers
operating_income:
  - ifrs-full:ProfitLossFromOperatingActivities
net_income:
  - ifrs-full:ProfitLossAttributableToOwnersOfParent
  - ifrs-full:ProfitLoss
total_assets:
  - ifrs-full:Assets
equity:
  - ifrs-full:EquityAttributableToOwnersOfParent
  - ifrs-full:Equity
current_assets:
  - ifrs-full:CurrentAssets
current_liabilities:
  - ifrs-full:CurrentLiabilities
total_debt:
  - ifrs-full:LongtermBorrowings
  - ifrs-full:ShorttermBorrowings
  - ifrs-full:CurrentPortionOfLongtermBorrowings
cash:
  - ifrs-full:CashAndCashEquivalents
inventory:
  - ifrs-full:Inventories
cogs:
  - ifrs-full:CostOfSales
operating_cf:
  - ifrs-full:CashFlowsFromUsedInOperatingActivities
capex:
  - ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities
  - ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities
ebitda: []
eps:
  - ifrs-full:DilutedEarningsLossPerShare
  - ifrs-full:BasicEarningsLossPerShare
dps:
  - ifrs-full:DividendsRecognisedAsDistributionsToOwnersPerShare
  - ifrs-full:DividendsPaidOrdinarySharesPerShare
tax_expense:
  - ifrs-full:IncomeTaxExpenseContinuingOperations
income_before_tax:
  - ifrs-full:ProfitLossBeforeTax
shares_outstanding:
  - ifrs-full:WeightedAverageShares
  - ifrs-full:AdjustedWeightedAverageShares
  - ifrs-full:NumberOfSharesIssuedAndFullyPaid
dividends_paid:
  - ifrs-full:DividendsPaidClassifiedAsFinancingActivities
  - ifrs-full:DividendsPaid
share_repurchases: []
```

- [ ] **Step 3: EDINET マッピングを作成**

```yaml
# config/edinet_taxonomy_mapping.yaml
revenue:
  jp_gaap:
    - jpcrp_cor:NetSalesSummaryOfBusinessResults
    - jpcrp_cor:NetSales
  ifrs:
    - jpcrp_cor:RevenueIFRSSummaryOfBusinessResults
    - jppfs_ifrs:Revenue

operating_income:
  jp_gaap:
    - jpcrp_cor:OperatingIncomeSummaryOfBusinessResults
    - jpcrp_cor:OperatingIncome
  ifrs:
    - jpcrp_cor:OperatingIncomeIFRSSummaryOfBusinessResults

net_income:
  jp_gaap:
    - jpcrp_cor:NetIncomeSummaryOfBusinessResults
    - jpcrp_cor:ProfitLossAttributableToOwnersOfParent
  ifrs:
    - jpcrp_cor:ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults
    - jppfs_ifrs:ProfitLossAttributableToOwnersOfParent

total_assets:
  jp_gaap:
    - jpcrp_cor:TotalAssetsSummaryOfBusinessResults
    - jppfs_cor:Assets
  ifrs:
    - jpcrp_cor:TotalAssetsIFRSSummaryOfBusinessResults
    - jppfs_ifrs:Assets

equity:
  jp_gaap:
    - jpcrp_cor:NetAssetsSummaryOfBusinessResults
    - jppfs_cor:NetAssets
  ifrs:
    - jpcrp_cor:EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults
    - jppfs_ifrs:EquityAttributableToOwnersOfParent

current_assets:
  jp_gaap:
    - jppfs_cor:CurrentAssets
  ifrs:
    - jppfs_ifrs:CurrentAssets

current_liabilities:
  jp_gaap:
    - jppfs_cor:CurrentLiabilities
  ifrs:
    - jppfs_ifrs:CurrentLiabilities

total_debt:
  jp_gaap:
    - jppfs_cor:LongTermLoansPayable
    - jppfs_cor:ShortTermLoansPayable
  ifrs:
    - jppfs_ifrs:BorrowingsNoncurrent
    - jppfs_ifrs:BorrowingsCurrent

cash:
  jp_gaap:
    - jppfs_cor:CashAndDeposits
  ifrs:
    - jppfs_ifrs:CashAndCashEquivalents

inventory:
  jp_gaap:
    - jppfs_cor:MerchandiseAndFinishedGoods
    - jppfs_cor:Inventories
  ifrs:
    - jppfs_ifrs:Inventories

cogs:
  jp_gaap:
    - jppfs_cor:CostOfSales
  ifrs:
    - jppfs_ifrs:CostOfSales

operating_cf:
  jp_gaap:
    - jpcrp_cor:CashFlowsFromUsedInOperatingActivitiesSummaryOfBusinessResults
    - jpcf_cor:NetCashProvidedByUsedInOperatingActivities
  ifrs:
    - jpcrp_cor:CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults

capex:
  jp_gaap:
    - jpcf_cor:PurchaseOfPropertyPlantAndEquipmentAndIntangibleAssets
  ifrs:
    - jpcf_cor:PurchaseOfPropertyPlantAndEquipmentAndIntangibleAssetsIFRS

ebitda: {}

eps:
  jp_gaap:
    - jpcrp_cor:BasicEarningsLossPerShareSummaryOfBusinessResults
  ifrs:
    - jpcrp_cor:BasicEarningsLossPerShareIFRSSummaryOfBusinessResults

dps:
  jp_gaap:
    - jpcrp_cor:DividendPaidPerShareSummaryOfBusinessResults
  ifrs:
    - jpcrp_cor:DividendPaidPerShareIFRSSummaryOfBusinessResults

tax_expense:
  jp_gaap:
    - jppfs_cor:IncomeTaxes
  ifrs:
    - jppfs_ifrs:IncomeTaxExpense

income_before_tax:
  jp_gaap:
    - jppfs_cor:IncomeBeforeIncomeTaxes
  ifrs:
    - jppfs_ifrs:ProfitLossBeforeTax

shares_outstanding:
  jp_gaap:
    - jpcrp_cor:NumberOfIssuedSharesAsOfDateOfAnnualSecuritiesReportDEI
  ifrs:
    - jpcrp_cor:NumberOfIssuedSharesAsOfDateOfAnnualSecuritiesReportDEI

dividends_paid:
  jp_gaap:
    - jpcf_cor:DividendsPaid
  ifrs:
    - jpcf_cor:DividendsPaidIFRS

share_repurchases:
  jp_gaap:
    - jpcf_cor:PurchaseOfTreasuryStock
  ifrs:
    - jpcf_cor:PurchaseOfTreasuryStockIFRS
```

- [ ] **Step 4: タクソノミYAMLのバリデーションテストを書く（M4修正）**

```python
# tests/unit/ingestion/test_taxonomy_yaml.py
"""タクソノミマッピングYAMLのバリデーションテスト"""
import yaml
import pytest
from pathlib import Path

from stock_analyze_system.config import _resolve_project_path


EXPECTED_FIELDS = {
    "revenue", "operating_income", "net_income", "total_assets", "equity",
    "current_assets", "current_liabilities", "total_debt", "cash", "inventory",
    "cogs", "operating_cf", "capex", "ebitda", "eps", "dps", "tax_expense",
    "income_before_tax", "shares_outstanding", "dividends_paid", "share_repurchases",
}


class TestUsGaapMapping:
    def test_loads_valid_yaml(self):
        path = _resolve_project_path("config/us_gaap_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_has_all_fields(self):
        path = _resolve_project_path("config/us_gaap_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field in EXPECTED_FIELDS:
            assert field in data, f"Missing field: {field}"

    def test_values_are_lists(self):
        path = _resolve_project_path("config/us_gaap_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field, tags in data.items():
            assert isinstance(tags, list), f"{field} should be a list"

    def test_tags_have_namespace_prefix(self):
        path = _resolve_project_path("config/us_gaap_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field, tags in data.items():
            for tag in tags:
                assert ":" in tag, f"{field} tag '{tag}' missing namespace prefix"


class TestIfrsMapping:
    def test_loads_valid_yaml(self):
        path = _resolve_project_path("config/ifrs_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_has_all_fields(self):
        path = _resolve_project_path("config/ifrs_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field in EXPECTED_FIELDS:
            assert field in data, f"Missing field: {field}"


class TestEdinetMapping:
    def test_loads_valid_yaml(self):
        path = _resolve_project_path("config/edinet_taxonomy_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)

    def test_has_jp_gaap_and_ifrs_keys(self):
        path = _resolve_project_path("config/edinet_taxonomy_mapping.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        for field, standards in data.items():
            if isinstance(standards, dict):
                assert "jp_gaap" in standards or "ifrs" in standards, \
                    f"{field} must have jp_gaap or ifrs key"
```

- [ ] **Step 5: テスト通過を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_taxonomy_yaml.py -v`
Expected: 全テスト PASS

- [ ] **Step 6: コミット**

```bash
git add config/ tests/unit/ingestion/test_taxonomy_yaml.py
git commit -m "feat: add XBRL taxonomy mapping YAML files with validation tests"
```

---

### Task 3: SEC XBRL パーサー

**Files:**
- Create: `src/stock_analyze_system/ingestion/sec_xbrl_parser.py`
- Create: `tests/unit/ingestion/test_sec_xbrl_parser.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/ingestion/test_sec_xbrl_parser.py
"""SEC XBRL パーサーのテスト (10-K/10-Q/20-F/6-K)"""
import pytest
import yaml
from unittest.mock import patch

SAMPLE_US_GAAP_FACTS = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {
                            "start": "2022-10-01", "end": "2023-09-30",
                            "val": 383285000000, "form": "10-K",
                            "fy": 2023, "fp": "FY",
                        },
                        {
                            "start": "2023-10-01", "end": "2024-09-28",
                            "val": 391035000000, "form": "10-K",
                            "fy": 2024, "fp": "FY",
                        },
                        {
                            "end": "2024-06-29", "val": 85777000000,
                            "form": "10-Q", "fy": 2024, "fp": "Q3",
                        },
                    ],
                },
            },
            "NetIncomeLoss": {
                "label": "Net Income (Loss)",
                "units": {
                    "USD": [
                        {
                            "start": "2022-10-01", "end": "2023-09-30",
                            "val": 96995000000, "form": "10-K",
                            "fy": 2023, "fp": "FY",
                        },
                        {
                            "start": "2023-10-01", "end": "2024-09-28",
                            "val": 93736000000, "form": "10-K",
                            "fy": 2024, "fp": "FY",
                        },
                    ],
                },
            },
            "EarningsPerShareDiluted": {
                "label": "Earnings Per Share, Diluted",
                "units": {
                    "USD/shares": [
                        {
                            "start": "2022-10-01", "end": "2023-09-30",
                            "val": 6.16, "form": "10-K",
                            "fy": 2023, "fp": "FY",
                        },
                    ],
                },
            },
        },
    },
}

SAMPLE_IFRS_FACTS = {
    "cik": 1046179,
    "entityName": "Taiwan Semiconductor Manufacturing Co Ltd",
    "facts": {
        "ifrs-full": {
            "Revenue": {
                "label": "Revenue",
                "units": {
                    "TWD": [
                        {
                            "start": "2022-01-01", "end": "2022-12-31",
                            "val": 2263891200000, "form": "20-F",
                            "fy": 2022, "fp": "FY",
                        },
                        {
                            "start": "2023-01-01", "end": "2023-12-31",
                            "val": 2161735800000, "form": "20-F",
                            "fy": 2023, "fp": "FY",
                        },
                    ],
                    "USD": [
                        {
                            "start": "2022-01-01", "end": "2022-12-31",
                            "val": 75882500000, "form": "20-F",
                            "fy": 2022, "fp": "FY",
                        },
                    ],
                },
            },
            "ProfitLoss": {
                "label": "Profit (loss)",
                "units": {
                    "TWD": [
                        {
                            "start": "2022-01-01", "end": "2022-12-31",
                            "val": 1016530200000, "form": "20-F",
                            "fy": 2022, "fp": "FY",
                        },
                        {
                            "start": "2023-04-01", "end": "2023-06-30",
                            "val": 300000000000, "form": "6-K",
                            "fy": 2023, "fp": None,
                        },
                    ],
                },
            },
            "Assets": {
                "label": "Assets",
                "units": {
                    "TWD": [
                        {
                            "end": "2022-12-31", "val": 5765188300000,
                            "form": "20-F", "fy": 2022, "fp": "FY",
                        },
                    ],
                },
            },
            "DilutedEarningsLossPerShare": {
                "label": "Diluted EPS",
                "units": {
                    "TWD/shares": [
                        {
                            "start": "2022-01-01", "end": "2022-12-31",
                            "val": 39.2, "form": "20-F",
                            "fy": 2022, "fp": "FY",
                        },
                    ],
                },
            },
        },
    },
}


@pytest.fixture
def us_gaap_mapping(tmp_path):
    mapping = {
        "revenue": ["us-gaap:Revenues", "us-gaap:SalesRevenueNet"],
        "net_income": ["us-gaap:NetIncomeLoss"],
        "eps": ["us-gaap:EarningsPerShareDiluted"],
        "total_assets": [],
    }
    p = tmp_path / "us_gaap_mapping.yaml"
    p.write_text(yaml.dump(mapping))
    return p


@pytest.fixture
def ifrs_mapping(tmp_path):
    mapping = {
        "revenue": ["ifrs-full:Revenue"],
        "net_income": ["ifrs-full:ProfitLoss"],
        "eps": ["ifrs-full:DilutedEarningsLossPerShare"],
        "total_assets": ["ifrs-full:Assets"],
    }
    p = tmp_path / "ifrs_mapping.yaml"
    p.write_text(yaml.dump(mapping))
    return p


@pytest.fixture
def parser(us_gaap_mapping, ifrs_mapping):
    from stock_analyze_system.ingestion.sec_xbrl_parser import (
        SecXbrlParser, _TAXONOMY_MAPPING_FILES,
    )
    with patch.dict(_TAXONOMY_MAPPING_FILES, {
        "us-gaap": str(us_gaap_mapping),
        "ifrs-full": str(ifrs_mapping),
    }):
        return SecXbrlParser()


class TestTenK:
    def test_parse_annual(self, parser):
        results = parser.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="annual")
        assert len(results) >= 2
        fy2023 = next(r for r in results if r["fiscal_year_end"] == "2023-09-30")
        assert fy2023["revenue"] == 383285000000
        assert fy2023["net_income"] == 96995000000
        assert fy2023["currency"] == "USD"

    def test_eps_from_usd_shares(self, parser):
        results = parser.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="annual")
        fy2023 = next(r for r in results if r["fiscal_year_end"] == "2023-09-30")
        assert fy2023["eps"] == 6.16

    def test_excludes_quarterly_data(self, parser):
        results = parser.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="annual")
        dates = [r["fiscal_year_end"] for r in results]
        assert "2024-06-29" not in dates


class TestTenQ:
    def test_parse_quarterly(self, parser):
        results = parser.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="quarterly")
        assert any(r["fiscal_year_end"] == "2024-06-29" for r in results)

    def test_excludes_annual_data(self, parser):
        results = parser.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="quarterly")
        dates = [r["fiscal_year_end"] for r in results]
        assert "2023-09-30" not in dates


class TestTwentyF:
    def test_parse_annual_ifrs(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="annual")
        assert len(results) >= 1
        fy2022 = next(r for r in results if r["fiscal_year_end"] == "2022-12-31")
        assert fy2022["revenue"] == 2263891200000
        assert fy2022["currency"] == "TWD"

    def test_total_assets_instant(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="annual")
        fy2022 = next(r for r in results if r["fiscal_year_end"] == "2022-12-31")
        assert fy2022["total_assets"] == 5765188300000

    def test_eps_twd_per_share(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="annual")
        fy2022 = next(r for r in results if r["fiscal_year_end"] == "2022-12-31")
        assert fy2022["eps"] == 39.2

    def test_excludes_6k_data(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="annual")
        dates = [r["fiscal_year_end"] for r in results]
        assert "2023-06-30" not in dates


class TestSixK:
    def test_parse_interim(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="quarterly")
        assert any(r["fiscal_year_end"] == "2023-06-30" for r in results)

    def test_excludes_20f_data(self, parser):
        results = parser.parse_company_facts(SAMPLE_IFRS_FACTS, period_type="quarterly")
        dates = [r["fiscal_year_end"] for r in results]
        assert "2022-12-31" not in dates


class TestTaxonomyDetection:
    def test_detects_us_gaap(self, parser):
        taxonomy, _, currency = parser._detect_taxonomy(SAMPLE_US_GAAP_FACTS)
        assert taxonomy == "us-gaap"
        assert currency == "USD"

    def test_detects_ifrs(self, parser):
        taxonomy, _, currency = parser._detect_taxonomy(SAMPLE_IFRS_FACTS)
        assert taxonomy == "ifrs-full"
        assert currency == "TWD"

    def test_empty_facts(self, parser):
        results = parser.parse_company_facts({"facts": {}}, period_type="annual")
        assert results == []


class TestFallbackTag:
    def test_fallback_to_second_tag(self, us_gaap_mapping, ifrs_mapping):
        from stock_analyze_system.ingestion.sec_xbrl_parser import (
            SecXbrlParser, _TAXONOMY_MAPPING_FILES,
        )
        mapping = {"revenue": ["us-gaap:NonExistentTag", "us-gaap:Revenues"]}
        custom = us_gaap_mapping.parent / "custom.yaml"
        custom.write_text(yaml.dump(mapping))
        with patch.dict(_TAXONOMY_MAPPING_FILES, {
            "us-gaap": str(custom),
            "ifrs-full": str(ifrs_mapping),
        }):
            p = SecXbrlParser()
        results = p.parse_company_facts(SAMPLE_US_GAAP_FACTS, period_type="annual")
        assert len(results) >= 1
        assert results[0]["revenue"] is not None

    def test_empty_us_gaap(self, parser):
        results = parser.parse_company_facts(
            {"facts": {"us-gaap": {}}}, period_type="annual",
        )
        assert results == []


class TestDurationFiltering:
    def test_quarterly_rejects_ytd_entry(self, parser):
        facts = {
            "Revenues": {
                "units": {
                    "USD": [
                        {"start": "2023-01-01", "end": "2023-06-30", "val": 5000,
                         "form": "10-Q", "fy": 2023, "fp": "Q2"},
                    ],
                },
            },
        }
        result = parser.resolve_tag(
            facts, ["Revenues"], "USD", ["10-Q"],
            duration_filter="quarterly",
        )
        assert "2023-06-30" not in result

    def test_quarterly_accepts_standalone_entry(self, parser):
        facts = {
            "Revenues": {
                "units": {
                    "USD": [
                        {"start": "2023-04-01", "end": "2023-06-30", "val": 2500,
                         "form": "10-Q", "fy": 2023, "fp": "Q2"},
                    ],
                },
            },
        }
        result = parser.resolve_tag(
            facts, ["Revenues"], "USD", ["10-Q"],
            duration_filter="quarterly",
        )
        assert result.get("2023-06-30") == 2500.0

    def test_quarterly_prefers_shortest_duration(self, parser):
        facts = {
            "Revenues": {
                "units": {
                    "USD": [
                        {"start": "2023-04-01", "end": "2023-06-30", "val": 5000,
                         "form": "10-Q", "fy": 2023, "fp": "Q2"},
                        {"start": "2023-05-17", "end": "2023-06-30", "val": 2000,
                         "form": "10-Q", "fy": 2023, "fp": "Q2"},
                    ],
                },
            },
        }
        result = parser.resolve_tag(
            facts, ["Revenues"], "USD", ["10-Q"],
            duration_filter="quarterly",
        )
        assert result.get("2023-06-30") == 2000.0
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_sec_xbrl_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: SEC XBRL パーサーを実装（C3修正: 完全な実装コード）**

```python
# src/stock_analyze_system/ingestion/sec_xbrl_parser.py
"""SEC XBRL Company Facts パーサー"""
from __future__ import annotations

import logging
from datetime import date as date_type
from pathlib import Path

import yaml

from stock_analyze_system.config import _resolve_project_path

logger = logging.getLogger(__name__)

_SHARE_FIELDS: set[str] = {"shares_outstanding", "eps", "dps"}
_INSTANT_FIELDS: set[str] = {
    "total_assets", "equity", "current_assets", "current_liabilities",
    "total_debt", "cash", "inventory", "shares_outstanding",
}
_CORE_FIELDS: set[str] = {
    "revenue", "operating_income", "net_income", "total_assets",
    "equity", "ebitda", "operating_cf", "eps",
}
_ANNUAL_MIN_DAYS = 300
_QUARTERLY_MAX_DAYS = 120
_DURATION_UNKNOWN = 99999

_FORM_MAP: dict[str, list[dict[str, str | None]]] = {
    "annual": [
        {"form": "10-K", "fp": "FY"},
        {"form": "20-F", "fp": "FY"},
    ],
    "quarterly": [
        {"form": "10-Q", "fp": None},
        {"form": "6-K", "fp": None},
        {"form": "10-K", "fp": None},
        {"form": "20-F", "fp": None},
    ],
}

_TAXONOMY_MAPPING_FILES: dict[str, str] = {
    "us-gaap": "config/us_gaap_mapping.yaml",
    "ifrs-full": "config/ifrs_mapping.yaml",
}


class SecXbrlParser:
    """XBRL Company Facts → 正規化財務レコード"""

    def __init__(self) -> None:
        self._mappings: dict[str, dict[str, list[str]]] = {}
        for taxonomy, rel_path in _TAXONOMY_MAPPING_FILES.items():
            path = _resolve_project_path(rel_path)
            if path.exists():
                self._mappings[taxonomy] = self._load_mapping(path)
            else:
                logger.warning("Mapping file not found: %s", path)

    def parse_company_facts(
        self, facts_json: dict, period_type: str = "annual",
    ) -> list[dict]:
        """Company Facts JSONから財務レコードを抽出"""
        filter_specs = _FORM_MAP.get(period_type)
        if filter_specs is None:
            raise ValueError(f"Unknown period_type '{period_type}'")

        taxonomy, facts_subtree, currency = self._detect_taxonomy(facts_json)
        mapping = self._mappings.get(taxonomy, {})
        if not mapping:
            return []

        forms = [spec["form"] for spec in filter_specs]
        fp_filter = filter_specs[0]["fp"]

        all_dates: set[str] = set()
        field_data: dict[str, dict[str, float]] = {}

        for field_name, tag_candidates in mapping.items():
            if not tag_candidates:
                field_data[field_name] = {}
                continue
            unit = self._pick_unit(field_name, currency)
            is_instant = field_name in _INSTANT_FIELDS
            duration_filter = period_type if not is_instant else None
            resolved = self.resolve_tag(
                facts_subtree, tag_candidates, unit, forms,
                fp_filter=fp_filter,
                duration_filter=duration_filter,
            )
            field_data[field_name] = resolved
            all_dates.update(resolved.keys())

        canonical_dates = self._merge_near_dates(all_dates, field_data, mapping)

        records: list[dict] = []
        for dt in sorted(canonical_dates):
            record: dict[str, object] = {"fiscal_year_end": dt, "currency": currency}
            has_core = False
            for field_name in mapping:
                val = field_data[field_name].get(dt)
                record[field_name] = val
                if val is not None and field_name in _CORE_FIELDS:
                    has_core = True
            if has_core:
                records.append(record)

        return records

    def resolve_tag(
        self, facts: dict, tag_candidates: list[str], unit: str,
        forms: list[str], fp_filter: str | None = None,
        duration_filter: str | None = None,
    ) -> dict[str, float]:
        """タグ候補を優先順に試行し、日付→値のマップを返す"""
        merged: dict[str, float] = {}
        merged_days: dict[str, int] = {}

        for candidate in tag_candidates:
            tag_name = candidate.split(":")[-1] if ":" in candidate else candidate
            tag_data = facts.get(tag_name)
            if tag_data is None:
                continue

            unit_data = self._find_unit_data(tag_data, unit)
            if not unit_data:
                continue

            for entry in unit_data:
                entry_form = entry.get("form")
                if entry_form not in forms:
                    continue
                if fp_filter and entry.get("fp") != fp_filter:
                    continue
                if (fp_filter != "FY"
                        and entry_form in ("10-K", "20-F")
                        and entry.get("fp") == "FY"):
                    continue

                end_date: str = entry.get("end", "")
                start_date: str = entry.get("start", "")
                days = (self._days_between(start_date, end_date)
                        if start_date and end_date else _DURATION_UNKNOWN)

                if duration_filter and start_date and end_date:
                    if not self._duration_ok(days, duration_filter):
                        continue

                val = entry.get("val")
                if end_date and val is not None:
                    prev_days = merged_days.get(end_date, _DURATION_UNKNOWN)
                    if end_date not in merged or days < prev_days:
                        merged[end_date] = float(val)
                        merged_days[end_date] = days

        return merged

    # --- 内部ヘルパー ---

    @staticmethod
    def _merge_near_dates(
        all_dates: set[str],
        field_data: dict[str, dict[str, float]],
        mapping: dict[str, list[str]],
    ) -> set[str]:
        """±3日以内の日付をマージ（新発見5修正: 値破棄時にログ出力）"""
        sorted_dates = sorted(all_dates)
        if len(sorted_dates) < 2:
            return all_dates

        clusters: list[list[str]] = [[sorted_dates[0]]]
        for d in sorted_dates[1:]:
            prev = clusters[-1][-1]
            if SecXbrlParser._days_between(prev, d) <= 3:
                clusters[-1].append(d)
            else:
                clusters.append([d])

        canonical: set[str] = set()
        for cluster in clusters:
            if len(cluster) == 1:
                canonical.add(cluster[0])
                continue

            best_date = cluster[0]
            best_count = 0
            for d in cluster:
                count = sum(
                    1 for fn in mapping if field_data.get(fn, {}).get(d) is not None
                )
                if count > best_count:
                    best_count = count
                    best_date = d

            canonical.add(best_date)
            for other in cluster:
                if other == best_date:
                    continue
                for fn in mapping:
                    fd = field_data.get(fn, {})
                    if other in fd:
                        if fd.get(best_date) is None:
                            fd[best_date] = fd[other]
                        else:
                            logger.debug(
                                "Discarding value for %s at %s (keeping %s value)",
                                fn, other, best_date,
                            )
                        del fd[other]

        return canonical

    @staticmethod
    def _days_between(start_date: str, end_date: str) -> int:
        try:
            return (date_type.fromisoformat(end_date)
                    - date_type.fromisoformat(start_date)).days
        except ValueError:
            return _DURATION_UNKNOWN

    @staticmethod
    def _duration_ok(days: int, mode: str) -> bool:
        if mode == "annual":
            return days >= _ANNUAL_MIN_DAYS
        if mode == "quarterly":
            return days <= _QUARTERLY_MAX_DAYS
        return True

    def _detect_taxonomy(self, facts_json: dict) -> tuple[str, dict, str]:
        """タクソノミと通貨を自動検出"""
        all_facts = facts_json.get("facts", {})
        us_gaap = all_facts.get("us-gaap", {})
        ifrs = all_facts.get("ifrs-full", {})

        if len(ifrs) > len(us_gaap):
            return "ifrs-full", ifrs, self._detect_currency(ifrs)
        elif us_gaap:
            return "us-gaap", us_gaap, "USD"
        elif ifrs:
            return "ifrs-full", ifrs, self._detect_currency(ifrs)
        return "us-gaap", {}, "USD"

    def _detect_currency(self, facts: dict) -> str:
        for probe_tag in ("Revenue", "Assets", "ProfitLoss"):
            tag_data = facts.get(probe_tag)
            if not tag_data:
                continue
            units = tag_data.get("units", {})
            for unit_key in units:
                if "/" in unit_key or unit_key in ("pure", "shares"):
                    continue
                if unit_key != "USD":
                    return unit_key
            if "USD" in units:
                return "USD"
        return "USD"

    def _pick_unit(self, field_name: str, currency: str) -> str:
        if field_name in _SHARE_FIELDS:
            return f"{currency}/shares"
        return currency

    def _find_unit_data(self, tag_data: dict, unit: str) -> list[dict] | None:
        units = tag_data.get("units", {})
        if unit in units:
            return units[unit]
        if unit.endswith("/shares"):
            if "USD/shares" in units:
                return units["USD/shares"]
            for key in units:
                if key.endswith("/shares"):
                    return units[key]
            if "shares" in units:
                return units["shares"]
        if unit != "USD" and "USD" in units:
            return units["USD"]
        if "USD/shares" in units:
            return units["USD/shares"]
        return None

    @staticmethod
    def _load_mapping(path: Path) -> dict[str, list[str]]:
        with open(path) as fh:
            raw: dict = yaml.safe_load(fh) or {}
        mapping: dict[str, list[str]] = {}
        for field, tags in raw.items():
            if isinstance(tags, list):
                mapping[field] = tags
        return mapping
```

- [ ] **Step 4: テスト通過を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_sec_xbrl_parser.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/ingestion/sec_xbrl_parser.py tests/unit/ingestion/test_sec_xbrl_parser.py
git commit -m "feat: add SEC XBRL parser with duration filtering"
```

---

### Task 4: SEC EDGAR クライアント

**Files:**
- Create: `src/stock_analyze_system/ingestion/sec_edgar.py`
- Create: `tests/unit/ingestion/test_sec_edgar.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/ingestion/test_sec_edgar.py
"""SEC EDGAR クライアントのテスト"""
import json

import pytest

from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient


@pytest.fixture
def mock_edgar(httpx_mock):
    """SEC EDGAR APIモックを設定"""
    return httpx_mock


class TestSearchCik:
    async def test_search_cik_found(self, mock_edgar):
        tickers_data = {
            "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": "789019", "ticker": "MSFT", "title": "Microsoft Corp"},
        }
        mock_edgar.add_response(
            url="https://www.sec.gov/files/company_tickers.json",
            json=tickers_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            cik = await client.search_cik("AAPL")
            assert cik == "0000320193"

    async def test_search_cik_not_found(self, mock_edgar):
        mock_edgar.add_response(
            url="https://www.sec.gov/files/company_tickers.json",
            json={},
        )
        async with SecEdgarClient(email="test@example.com") as client:
            cik = await client.search_cik("NONEXISTENT")
            assert cik is None

    async def test_search_cik_case_insensitive(self, mock_edgar):
        tickers_data = {
            "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple"},
        }
        mock_edgar.add_response(
            url="https://www.sec.gov/files/company_tickers.json",
            json=tickers_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            cik = await client.search_cik("aapl")
            assert cik == "0000320193"


class TestGetCompanyFacts:
    async def test_get_company_facts(self, mock_edgar):
        facts_data = {"cik": 320193, "entityName": "Apple", "facts": {}}
        mock_edgar.add_response(
            url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
            json=facts_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            result = await client.get_company_facts("0000320193")
            assert result["cik"] == 320193


class TestGetSubmissions:
    async def test_get_submissions_simple(self, mock_edgar):
        submissions_data = {
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K"], "filingDate": ["2024-11-01"],
                    "reportDate": ["2024-09-28"],
                    "accessionNumber": ["0000320193-24-000123"],
                    "primaryDocument": ["doc.htm"],
                    "primaryDocDescription": ["10-K"],
                },
                "files": [],
            },
        }
        mock_edgar.add_response(
            url="https://data.sec.gov/submissions/CIK0000320193.json",
            json=submissions_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            result = await client.get_submissions("0000320193")
            assert result["cik"] == "320193"

    async def test_get_submissions_with_pagination(self, mock_edgar):
        """ページネーション対応テスト（既知バグ#18修正確認）"""
        main_data = {
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K"], "filingDate": ["2024-11-01"],
                    "reportDate": ["2024-09-28"],
                    "accessionNumber": ["acc-1"],
                    "primaryDocument": ["doc1.htm"],
                    "primaryDocDescription": ["10-K"],
                },
                "files": [{"name": "CIK0000320193-submissions-001.json"}],
            },
        }
        page_data = {
            "form": ["10-Q"], "filingDate": ["2024-08-01"],
            "reportDate": ["2024-06-29"],
            "accessionNumber": ["acc-2"],
            "primaryDocument": ["doc2.htm"],
            "primaryDocDescription": ["10-Q"],
        }
        mock_edgar.add_response(
            url="https://data.sec.gov/submissions/CIK0000320193.json",
            json=main_data,
        )
        mock_edgar.add_response(
            url="https://data.sec.gov/submissions/CIK0000320193-submissions-001.json",
            json=page_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            result = await client.get_submissions("0000320193")
            forms = result["filings"]["recent"]["form"]
            assert len(forms) == 2
            assert "10-Q" in forms


class TestSearchEfts:
    async def test_search_efts(self, mock_edgar):
        """EFTS全文検索テスト（C2修正: 仕様書のsearch_efts追加）"""
        efts_data = {
            "hits": {
                "hits": [
                    {"_source": {"file_num": "001-36743", "entity_name": "Apple Inc."}},
                ],
                "total": {"value": 1},
            },
        }
        mock_edgar.add_response(
            url="https://efts.sec.gov/LATEST/search-index?q=%22AAPL%22&dateRange=custom&startdt=2024-01-01&enddt=2024-12-31",
            json=efts_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            result = await client.search_efts("AAPL", start_date="2024-01-01", end_date="2024-12-31")
            assert result["hits"]["total"]["value"] == 1


class TestListFilings:
    async def test_list_filings(self, mock_edgar):
        submissions_data = {
            "cik": "320193",
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "8-K"],
                    "filingDate": ["2024-11-01", "2024-08-02", "2024-07-15"],
                    "reportDate": ["2024-09-28", "2024-06-29", "2024-07-15"],
                    "accessionNumber": ["acc-1", "acc-2", "acc-3"],
                    "primaryDocument": ["doc1.htm", "doc2.htm", "doc3.htm"],
                    "primaryDocDescription": ["10-K", "10-Q", "8-K"],
                },
                "files": [],
            },
        }
        mock_edgar.add_response(
            url="https://data.sec.gov/submissions/CIK0000320193.json",
            json=submissions_data,
        )
        async with SecEdgarClient(email="test@example.com") as client:
            filings = await client.list_filings("0000320193", form_types=["10-K", "10-Q"])
            assert len(filings) == 2
            assert filings[0]["form"] == "10-K"
            assert "documentUrl" in filings[0]
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_sec_edgar.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: SEC EDGAR クライアントを実装**

```python
# src/stock_analyze_system/ingestion/sec_edgar.py
"""SEC EDGAR API クライアント (async)"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from stock_analyze_system.ingestion.base import BaseClient

logger = logging.getLogger(__name__)

_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


class SecEdgarClient(BaseClient):
    """SEC EDGAR 公開API クライアント"""

    def __init__(self, email: str, rate: float = 5.0):
        super().__init__(
            rate=rate,
            headers={"User-Agent": f"Stock-Analyze-System {email}"},
        )
        self._ticker_cik_map: dict[str, str] | None = None

    async def get_company_facts(self, cik: str) -> dict:
        """XBRL Company Facts を取得"""
        cik = cik.zfill(10)
        url = _COMPANY_FACTS_URL.format(cik=cik)
        resp = await self._get(url)
        return resp.json()

    async def get_submissions(self, cik: str) -> dict:
        """提出書類情報を取得（ページネーション対応 — バグ#18修正）"""
        cik = cik.zfill(10)
        url = _SUBMISSIONS_URL.format(cik=cik)
        resp = await self._get(url)
        data = resp.json()

        # ページネーション: files[] の追加ページもフェッチして recent に結合
        additional_files = data.get("filings", {}).get("files", [])
        for file_info in additional_files:
            page_url = f"https://data.sec.gov/submissions/{file_info['name']}"
            page_resp = await self._get(page_url)
            page_data = page_resp.json()
            recent = data["filings"]["recent"]
            for key in recent:
                if key in page_data:
                    recent[key].extend(page_data[key])

        return data

    async def get_filing_html(self, url: str) -> str:
        """ファイリングHTMLを取得"""
        resp = await self._get(url)
        return resp.text

    async def list_filings(
        self,
        cik: str,
        form_types: list[str] | None = None,
        max_years: int = 10,
    ) -> list[dict]:
        """ファイリング一覧を取得（フォームタイプ・年数フィルタ）"""
        if form_types is None:
            form_types = ["10-K", "10-Q", "20-F", "6-K"]

        data = await self.get_submissions(cik)
        recent = data.get("filings", {}).get("recent", {})

        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        report_dates = recent.get("reportDate", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        primary_descs = recent.get("primaryDocDescription", [])

        cutoff = datetime.now() - timedelta(days=max_years * 365)
        cik_num = cik.lstrip("0") or "0"
        results = []

        # zip で安全にイテレート（新発見4修正）
        for form, filing_date, report_date, acc_no, primary_doc, desc in zip(
            forms, filing_dates, report_dates,
            accession_numbers, primary_docs, primary_descs,
        ):
            if form not in form_types:
                continue
            try:
                if datetime.strptime(filing_date, "%Y-%m-%d") < cutoff:
                    continue
            except ValueError:
                continue

            acc_clean = acc_no.replace("-", "")
            doc_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{cik_num}/{acc_clean}/{primary_doc}"
            )
            results.append({
                "form": form,
                "filingDate": filing_date,
                "reportDate": report_date,
                "accessionNumber": acc_no,
                "primaryDocument": primary_doc,
                "primaryDocDescription": desc,
                "documentUrl": doc_url,
            })

        return results

    async def search_efts(
        self, query: str, start_date: str = "", end_date: str = "",
    ) -> dict:
        """EFTS全文検索（C2修正: 仕様書で定義済みのメソッド）"""
        url = "https://efts.sec.gov/LATEST/search-index"
        params: dict[str, str] = {"q": f'"{query}"'}
        if start_date and end_date:
            params["dateRange"] = "custom"
            params["startdt"] = start_date
            params["enddt"] = end_date
        resp = await self._get(url, params=params)
        return resp.json()

    async def search_cik(self, ticker: str) -> str | None:
        """ティッカーからCIKを検索"""
        if self._ticker_cik_map is None:
            await self._load_ticker_map()
        cik = self._ticker_cik_map.get(ticker.upper())
        if cik is None:
            return None
        return cik.zfill(10)

    async def _load_ticker_map(self) -> None:
        """SEC company_tickers.json をロード"""
        resp = await self._get(_COMPANY_TICKERS_URL)
        data = resp.json()
        self._ticker_cik_map = {}
        for entry in data.values():
            self._ticker_cik_map[entry["ticker"].upper()] = str(entry["cik_str"])
```

- [ ] **Step 4: テスト通過を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_sec_edgar.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/ingestion/sec_edgar.py tests/unit/ingestion/test_sec_edgar.py
git commit -m "feat: add SEC EDGAR async client with pagination support"
```

---

### Task 5: EDINET XBRL パーサー

**Files:**
- Create: `src/stock_analyze_system/ingestion/edinet_xbrl_parser.py`
- Create: `tests/unit/ingestion/test_edinet_xbrl_parser.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/ingestion/test_edinet_xbrl_parser.py
"""EDINET XBRL パーサーのテスト"""
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch
from xml.etree.ElementTree import Element, SubElement, ElementTree

from stock_analyze_system.ingestion.edinet_xbrl_parser import EdinetXbrlParser


@pytest.fixture
def edinet_mapping(tmp_path):
    mapping = {
        "revenue": {
            "jp_gaap": ["jpcrp_cor:NetSalesSummaryOfBusinessResults"],
            "ifrs": ["jppfs_ifrs:Revenue"],
        },
        "net_income": {
            "jp_gaap": ["jpcrp_cor:NetIncomeSummaryOfBusinessResults"],
            "ifrs": ["jppfs_ifrs:ProfitLossAttributableToOwnersOfParent"],
        },
        "total_assets": {
            "jp_gaap": ["jppfs_cor:Assets"],
            "ifrs": ["jppfs_ifrs:Assets"],
        },
    }
    p = tmp_path / "edinet_taxonomy_mapping.yaml"
    p.write_text(yaml.dump(mapping))
    return p


@pytest.fixture
def parser(edinet_mapping):
    return EdinetXbrlParser(mapping_path=str(edinet_mapping))


@pytest.fixture
def sample_xbrl_dir(tmp_path):
    """サンプルXBRLディレクトリを作成"""
    xbrl_dir = tmp_path / "doc_id_123" / "XBRL" / "PublicDoc"
    xbrl_dir.mkdir(parents=True)
    # 最小限のXBRLインスタンス文書を作成
    root = Element("{http://www.xbrl.org/2003/instance}xbrl")
    root.set("xmlns:jpcrp_cor", "http://disclosure.edinet-fsa.go.jp/jpcrp/cor")
    elem = SubElement(root, "{http://disclosure.edinet-fsa.go.jp/jpcrp/cor}NetSalesSummaryOfBusinessResults")
    elem.text = "5000000000"
    elem2 = SubElement(root, "{http://disclosure.edinet-fsa.go.jp/jpcrp/cor}NetIncomeSummaryOfBusinessResults")
    elem2.text = "1000000000"
    xbrl_file = xbrl_dir / "test_instance.xbrl"
    tree = ElementTree(root)
    tree.write(str(xbrl_file), xml_declaration=True, encoding="utf-8")
    return tmp_path / "doc_id_123"


class TestParseXbrlDirectory:
    def test_parse_jp_gaap(self, parser, sample_xbrl_dir):
        result = parser.parse_xbrl_directory(sample_xbrl_dir, accounting_standard="jp_gaap")
        assert result["revenue"] == 5000000000.0
        assert result["net_income"] == 1000000000.0

    def test_parse_missing_field_returns_none(self, parser, sample_xbrl_dir):
        result = parser.parse_xbrl_directory(sample_xbrl_dir, accounting_standard="jp_gaap")
        assert result.get("total_assets") is None

    def test_parse_nonexistent_dir_returns_empty(self, parser, tmp_path):
        result = parser.parse_xbrl_directory(tmp_path / "nonexistent")
        assert result == {} or all(v is None for v in result.values())


class TestDetectAccountingStandard:
    def test_detect_jp_gaap(self, parser, sample_xbrl_dir):
        standard = parser.detect_accounting_standard(sample_xbrl_dir)
        assert standard == "jp_gaap"


class TestConsolidatedStandalone:
    """既知バグ#19修正: XBRLコンテキストで連結/単体を判別"""

    def test_prefers_consolidated(self, parser, tmp_path):
        """連結と単体の両方がある場合、連結を優先する"""
        xbrl_dir = tmp_path / "consolidated_test" / "XBRL" / "PublicDoc"
        xbrl_dir.mkdir(parents=True)
        xbrl_content = '''<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:jpcrp_cor="http://disclosure.edinet-fsa.go.jp/jpcrp/cor">
  <context id="CurrentYearDuration_ConsolidatedMember">
    <entity><identifier>E02144</identifier></entity>
    <period><startDate>2023-04-01</startDate><endDate>2024-03-31</endDate></period>
    <scenario><member>ConsolidatedMember</member></scenario>
  </context>
  <context id="CurrentYearDuration_NonConsolidatedMember">
    <entity><identifier>E02144</identifier></entity>
    <period><startDate>2023-04-01</startDate><endDate>2024-03-31</endDate></period>
    <scenario><member>NonConsolidatedMember</member></scenario>
  </context>
  <jpcrp_cor:NetSalesSummaryOfBusinessResults contextRef="CurrentYearDuration_ConsolidatedMember">8000000000</jpcrp_cor:NetSalesSummaryOfBusinessResults>
  <jpcrp_cor:NetSalesSummaryOfBusinessResults contextRef="CurrentYearDuration_NonConsolidatedMember">3000000000</jpcrp_cor:NetSalesSummaryOfBusinessResults>
</xbrl>'''
        (xbrl_dir / "test.xbrl").write_text(xbrl_content, encoding="utf-8")
        result = parser.parse_xbrl_directory(
            tmp_path / "consolidated_test", accounting_standard="jp_gaap",
        )
        assert result["revenue"] == 8000000000.0

    def test_falls_back_to_standalone(self, parser, tmp_path):
        """単体のみの場合はそれを使用する"""
        xbrl_dir = tmp_path / "standalone_test" / "XBRL" / "PublicDoc"
        xbrl_dir.mkdir(parents=True)
        xbrl_content = '''<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:jpcrp_cor="http://disclosure.edinet-fsa.go.jp/jpcrp/cor">
  <context id="CurrentYearDuration_NonConsolidatedMember">
    <entity><identifier>E02144</identifier></entity>
    <period><startDate>2023-04-01</startDate><endDate>2024-03-31</endDate></period>
  </context>
  <jpcrp_cor:NetSalesSummaryOfBusinessResults contextRef="CurrentYearDuration_NonConsolidatedMember">3000000000</jpcrp_cor:NetSalesSummaryOfBusinessResults>
</xbrl>'''
        (xbrl_dir / "test.xbrl").write_text(xbrl_content, encoding="utf-8")
        result = parser.parse_xbrl_directory(
            tmp_path / "standalone_test", accounting_standard="jp_gaap",
        )
        assert result["revenue"] == 3000000000.0


class TestResolveValue:
    def test_resolves_numeric(self, parser):
        elements = {"Revenue": "1234567890"}
        result = parser._resolve_value(elements, ["Revenue"])
        assert result == 1234567890.0

    def test_returns_none_for_missing(self, parser):
        result = parser._resolve_value({}, ["NonExistent"])
        assert result is None

    def test_strips_namespace(self, parser):
        elements = {"Revenue": "999"}
        result = parser._resolve_value(elements, ["ns:Revenue"])
        assert result == 999.0
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_edinet_xbrl_parser.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: EDINET XBRL パーサーを実装**

```python
# src/stock_analyze_system/ingestion/edinet_xbrl_parser.py
"""EDINET XBRL パーサー"""
from __future__ import annotations

import logging
from pathlib import Path
from xml.etree import ElementTree

import yaml

logger = logging.getLogger(__name__)

_IFRS_NS_MARKER = "jppfs_ifrs"
_JP_GAAP_NS_MARKER = "jpcrp"


class EdinetXbrlParser:
    """EDINET XBRLファイリングの解析"""

    def __init__(self, mapping_path: str = "config/edinet_taxonomy_mapping.yaml"):
        self._mapping = self._load_mapping(mapping_path)

    def parse_xbrl_directory(
        self,
        xbrl_dir: str | Path,
        accounting_standard: str = "jp_gaap",
    ) -> dict:
        """XBRLディレクトリから財務データを抽出"""
        xbrl_dir = Path(xbrl_dir)
        instance_doc = self._find_instance_document(xbrl_dir)
        if instance_doc is None:
            logger.warning("No XBRL instance document found in %s", xbrl_dir)
            return {}

        try:
            tree = ElementTree.parse(str(instance_doc))
        except ElementTree.ParseError as e:
            logger.error("Failed to parse XBRL: %s", e)
            return {}

        # コンテキスト解析: 連結/単体を判別（既知バグ#19修正）
        # contextRef に "Consolidated" を含むものを連結、
        # "NonConsolidated" を含むものを単体と判定
        consolidated_values: dict[str, str] = {}
        standalone_values: dict[str, str] = {}
        no_context_values: dict[str, str] = {}

        for elem in tree.iter():
            tag = elem.tag
            if "}" in tag:
                local_name = tag.split("}")[-1]
            else:
                local_name = tag
            if not (elem.text and elem.text.strip()):
                continue
            text = elem.text.strip()
            context_ref = elem.get("contextRef", "")
            if "NonConsolidated" in context_ref:
                standalone_values[local_name] = text
            elif "Consolidated" in context_ref:
                consolidated_values[local_name] = text
            else:
                no_context_values[local_name] = text

        # 連結優先: consolidated > no_context > standalone
        element_values: dict[str, str] = {}
        element_values.update(standalone_values)
        element_values.update(no_context_values)
        element_values.update(consolidated_values)

        # accounting_standard の正規化
        std_key = accounting_standard.lower().replace("-", "_")

        result: dict[str, float | None] = {}
        for field_name, standards in self._mapping.items():
            if not isinstance(standards, dict):
                result[field_name] = None
                continue
            candidates = standards.get(std_key, [])
            if not candidates:
                result[field_name] = None
                continue
            result[field_name] = self._resolve_value(element_values, candidates)

        return result

    def detect_accounting_standard(self, xbrl_dir: str | Path) -> str:
        """会計基準を自動判別"""
        xbrl_dir = Path(xbrl_dir)
        instance_doc = self._find_instance_document(xbrl_dir)
        if instance_doc is None:
            return "jp_gaap"

        try:
            tree = ElementTree.parse(str(instance_doc))
        except ElementTree.ParseError:
            return "jp_gaap"

        namespaces: set[str] = set()
        for elem in tree.iter():
            if "}" in elem.tag:
                ns = elem.tag.split("}")[0].strip("{")
                namespaces.add(ns)

        for ns in namespaces:
            if _IFRS_NS_MARKER in ns:
                return "ifrs"
        return "jp_gaap"

    @staticmethod
    def _find_instance_document(xbrl_dir: Path) -> Path | None:
        """XBRLインスタンス文書を探索"""
        preferred_dirs = [xbrl_dir / "XBRL" / "PublicDoc", xbrl_dir]
        for search_dir in preferred_dirs:
            if not search_dir.exists():
                continue
            for ext in ("*.xbrl", "*.xml"):
                for candidate in search_dir.glob(ext):
                    name_lower = candidate.name.lower()
                    if "manifest" in name_lower or "schema" in name_lower:
                        continue
                    return candidate
        # フォールバック: 再帰探索
        for candidate in xbrl_dir.rglob("*.xbrl"):
            return candidate
        return None

    @staticmethod
    def _resolve_value(
        element_values: dict[str, str],
        candidates: list[str],
    ) -> float | None:
        """候補タグから値を解決"""
        for candidate in candidates:
            # namespace prefix を除去
            local_name = candidate.split(":")[-1] if ":" in candidate else candidate
            text = element_values.get(local_name)
            if text is not None:
                try:
                    return float(text)
                except (ValueError, TypeError):
                    continue
        return None

    @staticmethod
    def _load_mapping(mapping_path: str) -> dict:
        """マッピングYAMLを読み込み"""
        path = Path(mapping_path)
        if not path.exists():
            logger.warning("EDINET mapping file not found: %s", path)
            return {}
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        result: dict = {}
        for field_name, standards in data.items():
            if isinstance(standards, dict):
                result[field_name] = {
                    k: v if isinstance(v, list) else []
                    for k, v in standards.items()
                }
            else:
                result[field_name] = {}
        return result
```

- [ ] **Step 4: テスト通過を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_edinet_xbrl_parser.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/ingestion/edinet_xbrl_parser.py tests/unit/ingestion/test_edinet_xbrl_parser.py
git commit -m "feat: add EDINET XBRL parser"
```

---

### Task 6: EDINET クライアント

**Files:**
- Create: `src/stock_analyze_system/ingestion/edinet.py`
- Create: `tests/unit/ingestion/test_edinet.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/ingestion/test_edinet.py
"""EDINET クライアントのテスト"""
import pytest

from stock_analyze_system.ingestion.edinet import EdinetClient


class TestGetDocumentList:
    async def test_get_document_list(self, httpx_mock):
        response_data = {
            "metadata": {"status": "200"},
            "results": [
                {"docTypeCode": "120", "edinetCode": "E02144",
                 "docID": "S100TEST", "filerName": "Toyota"},
                {"docTypeCode": "130", "edinetCode": "E02144",
                 "docID": "S100SKIP", "filerName": "Toyota"},
            ],
        }
        httpx_mock.add_response(json=response_data)
        async with EdinetClient(api_key="test_key") as client:
            docs = await client.get_document_list("2024-03-01", doc_type="120")
            assert len(docs) == 1
            assert docs[0]["docID"] == "S100TEST"


class TestApiKeyValidation:
    async def test_warns_on_missing_api_key(self, httpx_mock, caplog):
        """APIキー未設定時にWARNINGログ（既知バグ#10修正確認）"""
        async with EdinetClient(api_key="") as client:
            import logging
            with caplog.at_level(logging.WARNING):
                docs = await client.get_document_list("2024-03-01")
            assert len(docs) == 0
            assert "API key" in caplog.text or "api_key" in caplog.text


class TestSearchCompanyFilings:
    async def test_search_returns_matching(self, httpx_mock):
        """M2修正: httpx_mock.reset() は無効なため、1日分のみテスト"""
        httpx_mock.add_response(json={
            "metadata": {"status": "200"},
            "results": [
                {"docTypeCode": "120", "edinetCode": "E02144",
                 "docID": "S100MATCH", "filerName": "Toyota"},
                {"docTypeCode": "120", "edinetCode": "E99999",
                 "docID": "S100OTHER", "filerName": "Other Corp"},
            ],
        })
        async with EdinetClient(api_key="test_key", rate_limit_interval=0.01) as client:
            results = await client.search_company_filings(
                "E02144", "2024-01-01", "2024-01-01",
            )
            assert len(results) == 1
            assert results[0]["docID"] == "S100MATCH"
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_edinet.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: EDINET クライアントを実装**

```python
# src/stock_analyze_system/ingestion/edinet.py
"""EDINET API v2 クライアント (async)"""
from __future__ import annotations

import logging
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from stock_analyze_system.ingestion.base import BaseClient

logger = logging.getLogger(__name__)

DOC_TYPE_YUHO = "120"


class EdinetClient(BaseClient):
    """EDINET API v2 クライアント"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.edinet-fsa.go.jp/api/v2",
        rate_limit_interval: float = 5.0,
    ):
        super().__init__(rate=1.0, interval=rate_limit_interval)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def get_document_list(
        self, date: str, doc_type: str = DOC_TYPE_YUHO,
    ) -> list[dict]:
        """指定日の書類一覧を取得"""
        if not self._api_key:
            logger.warning(
                "EDINET API key is not set. Skipping document list retrieval. "
                "Set EDINET_API_KEY environment variable."
            )
            return []

        url = f"{self._base_url}/documents.json"
        params = {"date": date, "type": 2, "Subscription-Key": self._api_key}
        resp = await self._get(url, params=params)
        data = resp.json()

        results = data.get("results", [])
        filtered = [
            doc for doc in results
            if doc.get("docTypeCode") == doc_type
        ]
        logger.info(
            "EDINET %s: %d documents found, %d matched type %s",
            date, len(results), len(filtered), doc_type,
        )
        return filtered

    async def download_xbrl_zip(
        self, doc_id: str, save_dir: str | Path,
    ) -> Path:
        """XBRLアーカイブをダウンロード・展開"""
        if not self._api_key:
            raise ValueError("EDINET API key is required for document download")

        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        url = f"{self._base_url}/documents/{doc_id}"
        params = {"type": 1, "Subscription-Key": self._api_key}
        resp = await self._get(url, params=params)

        zip_path = save_dir / f"{doc_id}.zip"
        zip_path.write_bytes(resp.content)

        extract_dir = save_dir / doc_id
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
        zip_path.unlink()

        return extract_dir

    async def search_company_filings(
        self,
        edinet_code: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """指定企業のファイリングを日付範囲で検索"""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        results: list[dict] = []

        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            try:
                docs = await self.get_document_list(date_str)
                for doc in docs:
                    if doc.get("edinetCode") == edinet_code:
                        results.append(doc)
            except Exception as e:
                logger.warning("EDINET search error for %s: %s", date_str, e)
            current += timedelta(days=1)

        return results
```

- [ ] **Step 4: テスト通過を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_edinet.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/ingestion/edinet.py tests/unit/ingestion/test_edinet.py
git commit -m "feat: add EDINET async client with API key validation"
```

---

### Task 7: Yahoo Finance クライアント

**Files:**
- Create: `src/stock_analyze_system/ingestion/yahoo_finance.py`
- Create: `tests/unit/ingestion/test_yahoo_finance.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/ingestion/test_yahoo_finance.py
"""Yahoo Finance クライアントのテスト"""
import math
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stock_analyze_system.ingestion.yahoo_finance import (
    YahooFinanceClient,
    _epoch_to_date,
)


class TestEpochToDate:
    def test_basic_conversion(self):
        assert _epoch_to_date(1759190400) == "2025-09-30"

    def test_float_input(self):
        assert _epoch_to_date(1759190400.0) == "2025-09-30"

    def test_epoch_zero(self):
        assert _epoch_to_date(0) == "1970-01-01"


class TestGetStockPrice:
    async def test_returns_price_data(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 185.0,
            "marketCap": 2800000000000,
            "fiftyTwoWeekHigh": 199.62,
            "fiftyTwoWeekLow": 124.17,
            "currency": "USD",
        }
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_stock_price("AAPL")
            assert result is not None
            assert result["price"] == 185.0
            assert result["market_cap"] == 2800000000000
            assert result["currency"] == "USD"

    async def test_returns_none_on_no_price(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {}
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_stock_price("INVALID")
            assert result is None


class TestGetScreeningInfo:
    async def test_returns_screening_data(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 185.0,
            "marketCap": 2800000000000,
            "trailingPE": 28.5,
            "trailingEps": 6.16,
            "returnOnEquity": 0.175,
            "operatingMargins": 0.30,
            "profitMargins": 0.26,
            "revenueGrowth": 0.05,
            "earningsGrowth": 0.10,
            "priceToBook": 45.0,
            "priceToSalesTrailing12Months": 7.5,
            "enterpriseToEbitda": 20.0,
            "forwardPE": 25.0,
            "dividendYield": 0.006,
            "debtToEquity": 150.0,
            "pegRatio": 2.5,
            "freeCashflow": 110000000000,
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "exchange": "NMS",
            "beta": 1.2,
            "averageVolume": 50000000,
            "mostRecentQuarter": 1727481600,
            "lastFiscalYearEnd": 1727481600,
        }
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_screening_info("AAPL")
            assert result is not None
            assert result["roe"] == 0.175
            assert result["de_ratio"] == 1.5  # 150/100
            assert result["sector"] == "Technology"

    async def test_fcf_yield_calculation(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 100.0,
            "marketCap": 1000,
            "freeCashflow": 100,
        }
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_screening_info("TEST")
            assert result is not None
            assert result["fcf_yield"] == pytest.approx(0.1)

    async def test_fcf_yield_zero_mcap(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "regularMarketPrice": 100.0,
            "marketCap": 0,
            "freeCashflow": 100,
        }
        with patch("stock_analyze_system.ingestion.yahoo_finance.yfinance") as mock_yf:
            mock_yf.Ticker.return_value = mock_ticker
            client = YahooFinanceClient()
            result = await client.get_screening_info("TEST")
            assert result is not None
            assert result["fcf_yield"] is None
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_yahoo_finance.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Yahoo Finance クライアントを実装**

```python
# src/stock_analyze_system/ingestion/yahoo_finance.py
"""Yahoo Finance クライアント (yfinance同期API → asyncio.to_thread ラップ)"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timezone

import yfinance

from stock_analyze_system.ingestion.base import AsyncRateLimiter

logger = logging.getLogger(__name__)


def _epoch_to_date(epoch: int | float) -> str:
    """Unixエポックを ISO日付文字列に変換"""
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).strftime("%Y-%m-%d")


class YahooFinanceClient:
    """yfinance ラッパー（asyncio.to_thread で非同期化）

    M3注記: BaseClient を継承しない。yfinance は同期ライブラリであり
    httpx.AsyncClient は不要。AsyncRateLimiter のみ使用して
    asyncio.to_thread() でスレッドプールに委譲する設計。
    """

    def __init__(self, rate: float = 2.0):
        self._rate_limiter = AsyncRateLimiter(rate=rate)

    async def get_stock_price(self, ticker: str) -> dict | None:
        """現在の株価情報を取得"""
        await self._rate_limiter.acquire()
        try:
            info = await asyncio.to_thread(self._fetch_info, ticker)
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            if price is None:
                return None
            return {
                "price": price,
                "market_cap": info.get("marketCap"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "currency": info.get("currency"),
            }
        except Exception as e:
            logger.warning("Yahoo Finance error for %s: %s", ticker, e)
            return None

    async def get_screening_info(self, ticker: str) -> dict | None:
        """スクリーニング用の総合情報を取得"""
        await self._rate_limiter.acquire()
        try:
            info = await asyncio.to_thread(self._fetch_info, ticker)
            price = info.get("regularMarketPrice") or info.get("currentPrice")
            if price is None:
                return None

            mcap = info.get("marketCap")
            fcf = info.get("freeCashflow")
            fcf_yield = (fcf / mcap) if (fcf is not None and mcap) else None

            de = info.get("debtToEquity")
            de_ratio = de / 100.0 if de is not None else None

            mrq = info.get("mostRecentQuarter")
            lfy = info.get("lastFiscalYearEnd")
            mrq_str = _epoch_to_date(mrq) if mrq else None
            lfy_str = _epoch_to_date(lfy) if lfy else None

            return {
                "stock_price": price,
                "market_cap": mcap,
                "trailing_per": info.get("trailingPE"),
                "eps": info.get("trailingEps"),
                "forward_per": info.get("forwardPE"),
                "pbr": info.get("priceToBook"),
                "psr": info.get("priceToSalesTrailing12Months"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "dividend_yield": info.get("dividendYield"),
                "roe": info.get("returnOnEquity"),
                "operating_margin": info.get("operatingMargins"),
                "net_margin": info.get("profitMargins"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "de_ratio": de_ratio,
                "peg_ratio": info.get("pegRatio"),
                "fcf_yield": fcf_yield,
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "exchange": info.get("exchange"),
                "beta": info.get("beta"),
                "volume": info.get("averageVolume"),
                "most_recent_quarter": mrq_str,
                "last_fiscal_year_end": lfy_str,
                "trailing_eps_date": f"TTM ending {mrq_str}" if mrq_str else "TTM",
            }
        except Exception as e:
            logger.warning("Yahoo Finance screening error for %s: %s", ticker, e)
            return None

    async def get_quarterly_financials(self, ticker: str) -> list[dict]:
        """四半期財務データを取得"""
        await self._rate_limiter.acquire()
        try:
            return await asyncio.to_thread(self._fetch_quarterly, ticker)
        except Exception as e:
            logger.warning("Yahoo Finance quarterly error for %s: %s", ticker, e)
            return []

    async def get_price_history(
        self, ticker: str, period: str = "10y",
    ) -> list[dict]:
        """株価履歴を取得"""
        await self._rate_limiter.acquire()
        try:
            return await asyncio.to_thread(self._fetch_history, ticker, period)
        except Exception as e:
            logger.warning("Yahoo Finance history error for %s: %s", ticker, e)
            return []

    @staticmethod
    def _fetch_info(ticker: str) -> dict:
        return yfinance.Ticker(ticker).info or {}

    @staticmethod
    def _fetch_quarterly(ticker: str) -> list[dict]:
        t = yfinance.Ticker(ticker)
        income = t.quarterly_income_stmt
        balance = t.quarterly_balance_sheet
        cashflow = t.quarterly_cashflow

        if income is None or income.empty:
            return []

        def _yf_val(df, col, *row_labels) -> float | None:
            if df is None or df.empty or col not in df.columns:
                return None
            for label in row_labels:
                if label in df.index:
                    val = df.at[label, col]
                    if isinstance(val, float) and math.isnan(val):
                        return None
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return None
            return None

        records = []
        for col in income.columns:
            date_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)

            rev = _yf_val(income, col, "Total Revenue", "Revenue")
            op_inc = _yf_val(income, col, "Operating Income", "Operating Revenue")
            ni = _yf_val(income, col, "Net Income", "Net Income Common Stockholders")
            ebitda_val = _yf_val(income, col, "EBITDA", "Normalized EBITDA")
            eps_val = _yf_val(income, col, "Diluted EPS", "Basic EPS")
            cogs_val = _yf_val(income, col, "Cost Of Revenue")
            tax_val = _yf_val(income, col, "Tax Provision", "Income Tax Expense")
            ibt = _yf_val(income, col, "Pretax Income")

            ta = _yf_val(balance, col, "Total Assets")
            eq = _yf_val(balance, col, "Stockholders Equity", "Total Equity Gross Minority Interest")
            ca = _yf_val(balance, col, "Current Assets")
            cl = _yf_val(balance, col, "Current Liabilities")
            td = _yf_val(balance, col, "Total Debt")
            cash_val = _yf_val(balance, col, "Cash And Cash Equivalents")
            inv = _yf_val(balance, col, "Inventory")
            shares = _yf_val(balance, col, "Share Issued", "Ordinary Shares Number")

            op_cf = _yf_val(cashflow, col, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
            capex_val = _yf_val(cashflow, col, "Capital Expenditure")
            fcf_val = _yf_val(cashflow, col, "Free Cash Flow")
            div_paid = _yf_val(cashflow, col, "Common Stock Dividend Paid", "Cash Dividends Paid")
            repurch = _yf_val(cashflow, col, "Repurchase Of Capital Stock")

            # FCF導出: capex符号を安全に処理（新発見3修正）
            if fcf_val is None and op_cf is not None and capex_val is not None:
                fcf_val = op_cf - abs(capex_val)

            records.append({
                "fiscal_year_end": date_str,
                "revenue": rev, "operating_income": op_inc, "net_income": ni,
                "total_assets": ta, "equity": eq, "current_assets": ca,
                "current_liabilities": cl, "total_debt": td, "cash": cash_val,
                "inventory": inv, "cogs": cogs_val,
                "operating_cf": op_cf, "capex": capex_val, "fcf": fcf_val,
                "ebitda": ebitda_val, "eps": eps_val,
                "tax_expense": tax_val, "income_before_tax": ibt,
                "shares_outstanding": shares,
                "dividends_paid": div_paid, "share_repurchases": repurch,
                "dps": None,
            })

        return records

    @staticmethod
    def _fetch_history(ticker: str, period: str) -> list[dict]:
        hist = yfinance.Ticker(ticker).history(period=period)
        if hist is None or hist.empty:
            return []
        records = []
        for idx, row in hist.iterrows():
            records.append({
                "date": idx.strftime("%Y-%m-%d"),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            })
        return records
```

- [ ] **Step 4: テスト通過を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_yahoo_finance.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/ingestion/yahoo_finance.py tests/unit/ingestion/test_yahoo_finance.py
git commit -m "feat: add Yahoo Finance async client with safe FCF derivation"
```

---

### Task 8: FMP クライアント

**Files:**
- Create: `src/stock_analyze_system/ingestion/fmp.py`
- Create: `tests/unit/ingestion/test_fmp.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/ingestion/test_fmp.py
"""FMP クライアントのテスト"""
import pytest

from stock_analyze_system.ingestion.fmp import FmpClient


class TestQuote:
    async def test_quote_success(self, httpx_mock):
        httpx_mock.add_response(json=[{
            "symbol": "AAPL", "price": 185.0, "changesPercentage": 1.5,
        }])
        async with FmpClient(api_key="test_key") as client:
            result = await client.quote("AAPL")
            assert result is not None
            assert result["price"] == 185.0

    async def test_quote_empty(self, httpx_mock):
        httpx_mock.add_response(json=[])
        async with FmpClient(api_key="test_key") as client:
            result = await client.quote("NONEXIST")
            assert result is None


class TestProfile:
    async def test_profile_success(self, httpx_mock):
        httpx_mock.add_response(json=[{
            "symbol": "AAPL", "companyName": "Apple Inc.",
            "sector": "Technology",
        }])
        async with FmpClient(api_key="test_key") as client:
            result = await client.profile("AAPL")
            assert result is not None
            assert result["companyName"] == "Apple Inc."

    async def test_profile_empty(self, httpx_mock):
        httpx_mock.add_response(json=[])
        async with FmpClient(api_key="test_key") as client:
            result = await client.profile("INVALID")
            assert result is None


class TestSearchName:
    async def test_search_name(self, httpx_mock):
        httpx_mock.add_response(json=[
            {"symbol": "AAPL", "name": "Apple Inc."},
            {"symbol": "AAPD", "name": "Apple Short"},
        ])
        async with FmpClient(api_key="test_key") as client:
            results = await client.search_name("Apple")
            assert len(results) == 2


class TestGetFinancialStatements:
    """M8修正: get_financial_statementsのテスト追加"""
    async def test_get_financial_statements_success(self, httpx_mock):
        httpx_mock.add_response(json=[{
            "date": "2024-09-28", "symbol": "AAPL",
            "revenue": 391035000000, "netIncome": 93736000000,
        }])
        async with FmpClient(api_key="test_key") as client:
            result = await client.get_financial_statements("AAPL")
            assert result is not None
            assert result["revenue"] == 391035000000

    async def test_get_financial_statements_empty(self, httpx_mock):
        httpx_mock.add_response(json=[])
        async with FmpClient(api_key="test_key") as client:
            result = await client.get_financial_statements("INVALID")
            assert result is None


class TestIsAvailable:
    async def test_is_available_true(self, httpx_mock):
        httpx_mock.add_response(json=[{"symbol": "AAPL", "price": 185.0}])
        async with FmpClient(api_key="test_key") as client:
            assert await client.is_available() is True

    async def test_is_available_no_key(self):
        async with FmpClient(api_key="") as client:
            assert await client.is_available() is False

    async def test_is_available_error(self, httpx_mock):
        httpx_mock.add_response(json={"Error Message": "Invalid API Key"})
        async with FmpClient(api_key="bad_key") as client:
            assert await client.is_available() is False


class TestGetStockNews:
    async def test_get_stock_news(self, httpx_mock):
        httpx_mock.add_response(json=[
            {"title": "Apple Q4 Results", "url": "https://example.com/news1"},
        ])
        async with FmpClient(api_key="test_key") as client:
            news = await client.get_stock_news("AAPL", limit=5)
            assert len(news) == 1
            assert news[0]["title"] == "Apple Q4 Results"


class TestErrorHandling:
    async def test_fmp_error_message(self, httpx_mock):
        httpx_mock.add_response(json={"Error Message": "Limit Reached"})
        from stock_analyze_system.exceptions import ApiResponseError
        async with FmpClient(api_key="test_key") as client:
            with pytest.raises(ApiResponseError, match="Limit Reached"):
                await client.quote("AAPL")
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_fmp.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: FMP クライアントを実装**

```python
# src/stock_analyze_system/ingestion/fmp.py
"""Financial Modeling Prep API クライアント (async)"""
from __future__ import annotations

import logging
from typing import Any

from stock_analyze_system.exceptions import ApiResponseError
from stock_analyze_system.ingestion.base import BaseClient

logger = logging.getLogger(__name__)


class FmpClient(BaseClient):
    """FMP API クライアント（無料プラン: 250 req/day, 5 req/s）"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://financialmodelingprep.com/stable",
        rate: float = 5.0,
    ):
        super().__init__(rate=rate)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def _get_json(self, path: str, params: dict | None = None) -> Any:
        """内部GET + 認証 + エラーチェック"""
        url = f"{self._base_url}/{path.lstrip('/')}"
        params = params or {}
        params["apikey"] = self._api_key
        resp = await self._get(url, params=params)
        data = resp.json()
        if isinstance(data, dict) and "Error Message" in data:
            raise ApiResponseError(data["Error Message"])
        return data

    async def quote(self, symbol: str) -> dict | None:
        """株価クオートを取得"""
        data = await self._get_json(f"/quote/{symbol}")
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    async def profile(self, symbol: str) -> dict | None:
        """企業プロファイルを取得"""
        data = await self._get_json(f"/profile/{symbol}")
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    async def search_name(
        self, query: str, exchange: str | None = None, limit: int = 50,
    ) -> list[dict]:
        """企業名検索"""
        params: dict[str, Any] = {"query": query, "limit": limit}
        if exchange:
            params["exchange"] = exchange
        data = await self._get_json("/search-name", params=params)
        return data if isinstance(data, list) else []

    async def get_financial_statements(self, ticker: str) -> dict | None:
        """財務諸表を取得"""
        data = await self._get_json(f"/income-statement/{ticker}", {"period": "annual"})
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    async def get_company_profile(self, ticker: str) -> dict | None:
        """企業プロファイルを取得（profileのエイリアス）"""
        return await self.profile(ticker)

    async def get_stock_news(
        self, ticker: str, limit: int = 10,
    ) -> list[dict]:
        """株式ニュースを取得"""
        data = await self._get_json(
            "/stock_news", params={"tickers": ticker, "limit": limit},
        )
        return data if isinstance(data, list) else []

    async def is_available(self) -> bool:
        """APIキーが有効かチェック"""
        if not self._api_key:
            return False
        try:
            await self.quote("AAPL")
            return True
        except Exception:
            return False
```

- [ ] **Step 4: テスト通過を確認**

Run: `python3 -m pytest tests/unit/ingestion/test_fmp.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: 全テスト通過を確認**

Run: `python3 -m pytest tests/ -v --tb=short`
Expected: 全テスト PASS

- [ ] **Step 6: ruff チェック**

Run: `ruff check src/stock_analyze_system/ingestion/ tests/unit/ingestion/`
Expected: エラーなし

- [ ] **Step 7: コミット**

```bash
git add src/stock_analyze_system/ingestion/fmp.py tests/unit/ingestion/test_fmp.py
git commit -m "feat: add FMP async client with error handling"
```

---

## Phase 2 完了条件

- [ ] `AsyncRateLimiter` が `asyncio.sleep` ベースで非ブロッキング
- [ ] `BaseClient` が `httpx.AsyncClient` で指数バックオフリトライ
- [ ] `SecEdgarClient` がページネーション対応（既知バグ#18修正）
- [ ] `SecXbrlParser` が10-K/10-Q/20-F/6-Kの全フォームをパース
- [ ] `EdinetClient` がAPIキー未設定時にWARNINGログ（既知バグ#10修正）
- [ ] `EdinetXbrlParser` がJP-GAAP/IFRSを判別、連結/単体を優先判別してパース（既知バグ#19修正）
- [ ] `YahooFinanceClient` が `asyncio.to_thread` で非同期化、FCF安全導出
- [ ] `FmpClient` がエラーメッセージ検出、`is_available()` でキー検証
- [ ] 3つのタクソノミマッピングYAMLが設置済み
- [ ] 全テスト PASS、ruff エラーなし
