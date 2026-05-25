# Phase 3: サービス層 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repository層（9ドメインリポジトリ）とService層（ドメインサービス + Sync/オーケストレーション + metrics純粋関数）を構築し、データ取得→DB永続化→指標計算のパイプラインを完成させる

**Architecture:** Repository層は `BaseRepository[T]` を継承したドメイン固有リポジトリ（各リポジトリが自身のモデルクラスを知っており、コンストラクタは `session` のみ受け取る。仕様書セクション9.5のDI例は `CompanyRepository(session)` 形式に読み替える）。Service層はコンストラクタDIでリポジトリを受け取る。Syncサービスは Ingestion クライアント + Repository を橋渡しする非同期オーケストレーション。metrics.py は副作用なしの純粋関数群。`compute_metrics` / `compute_timeseries_metrics` 等の I/O 不要な計算メソッドは同期関数として実装する（仕様書の `async` は省略形として扱う）。

**Tech Stack:** Python 3.10+, SQLAlchemy 2.x (AsyncSession), pytest-asyncio, asyncio

**Spec:** `docs/superpowers/specs/2026-03-21-stock-analyze-system-design.md` セクション6, 7

**Reference project:** `<legacy-stock-analyzer-repo>/src/stock_analyzer/services/` — 潜在バグ調査済み

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/stock_analyze_system/repositories/company.py` | CompanyRepository |
| Create | `src/stock_analyze_system/repositories/financial.py` | FinancialRepository |
| Create | `src/stock_analyze_system/repositories/valuation.py` | ValuationRepository |
| Create | `src/stock_analyze_system/repositories/filing.py` | FilingRepository |
| Create | `src/stock_analyze_system/repositories/analysis.py` | AnalysisRepository |
| Create | `src/stock_analyze_system/repositories/watchlist.py` | WatchlistRepository |
| Create | `src/stock_analyze_system/repositories/screening.py` | ScreeningRepository |
| Create | `src/stock_analyze_system/repositories/target.py` | TargetRepository |
| Create | `src/stock_analyze_system/repositories/document_index.py` | DocumentIndexRepository |
| Create | `src/stock_analyze_system/services/__init__.py` | パッケージ初期化 |
| Create | `src/stock_analyze_system/services/metrics.py` | 25個の純粋関数（財務指標計算） |
| Create | `src/stock_analyze_system/services/company.py` | CompanyService |
| Create | `src/stock_analyze_system/services/financial.py` | FinancialService |
| Create | `src/stock_analyze_system/services/valuation.py` | ValuationService |
| Create | `src/stock_analyze_system/services/filing.py` | FilingService |
| Create | `src/stock_analyze_system/services/watchlist.py` | WatchlistService |
| Create | `src/stock_analyze_system/services/analysis_target.py` | AnalysisTargetService |
| Create | `src/stock_analyze_system/services/financial_sync.py` | FinancialSyncService |
| Create | `src/stock_analyze_system/services/filing_sync.py` | FilingSyncService |
| Create | `src/stock_analyze_system/services/job.py` | JobService + SyncResult/DailyUpdateResult |
| Create | `tests/unit/repositories/__init__.py` | テストパッケージ |
| Create | `tests/unit/repositories/test_company_repo.py` | CompanyRepository テスト |
| Create | `tests/unit/repositories/test_financial_repo.py` | FinancialRepository テスト |
| Create | `tests/unit/repositories/test_valuation_repo.py` | ValuationRepository テスト |
| Create | `tests/unit/repositories/test_filing_repo.py` | FilingRepository テスト |
| Create | `tests/unit/repositories/test_other_repos.py` | Analysis/Watchlist/Screening/Target/DocIndex テスト |
| Create | `tests/unit/services/__init__.py` | テストパッケージ |
| Create | `tests/unit/services/test_metrics.py` | metrics 純粋関数テスト |
| Create | `tests/unit/services/test_company_service.py` | CompanyService テスト |
| Create | `tests/unit/services/test_financial_service.py` | FinancialService テスト |
| Create | `tests/unit/services/test_valuation_service.py` | ValuationService テスト |
| Create | `tests/unit/services/test_filing_service.py` | FilingService テスト |
| Create | `tests/unit/services/test_watchlist_service.py` | WatchlistService テスト |
| Create | `tests/unit/services/test_analysis_target_service.py` | AnalysisTargetService テスト |
| Create | `tests/unit/services/test_financial_sync.py` | FinancialSyncService テスト |
| Create | `tests/unit/services/test_filing_sync.py` | FilingSyncService テスト |
| Create | `tests/unit/services/test_job_service.py` | JobService テスト |

---

## 参考プロジェクト潜在バグ調査結果

`<legacy-stock-analyzer-repo>/src/stock_analyzer/services/` および `<legacy-stock-analyzer-repo>/src/stock_analyzer/repositories/` の調査で発見した問題:

| # | ファイル | 問題 | 重要度 | 対策 |
|---|---------|------|--------|------|
| 既知#4 | `job_service.py` | `financials_count` が常に0。`_update_from_sec()` / `_update_from_edinet()` の戻り値（bool）からカウントを取得していない | Major | SyncResult を dataclass 化し、sync 関数が `int`（レコード数）を返すように変更 |
| 既知#7 | `company_service.py` | `_US_MARKETS` を定義しているが検証に使用していない。未知の市場が US として黙って処理される | Minor | `build_company_id()` で `_US_MARKETS` と `_JP_MARKETS` の両方を検証し、未知市場で `ValueError` を raise |
| 新発見1 | `job_service.py` | `_compute_valuation_from_financials()` で `stock_price` が None の場合に `TypeError` が発生する | Critical | `stock_price is None` で早期 return |
| 新発見2 | `job_service.py` | PBR 計算で `shares` の None チェックが暗黙的。`shares and shares > 0` ではなく `shares is not None and shares > 0` を使用すべき | Critical | 明示的な `is not None` チェック |
| 新発見3 | `job_service.py` | `run_daily_update()` で `except Exception` を使用。SystemExit 等も捕捉してしまう | Minor | 具体的な例外クラスを列挙 |
| 新発見4 | `financial_sync.py` | Q4 減算で結果の妥当性チェックなし。負の Q4 値がそのまま永続化される | Major | 減算結果のログ出力（WARNING レベル）を追加 |
| 新発見5 | `valuation_service.py` | `compute_group_deviation()` が入力リストを in-place 変更する | Minor | 新しいリストを返すように変更（仕様書の記載通り） |
| 新発見6 | `financial_service.py` | YoY 四半期マッチングの日数範囲（330-400日）がマジックナンバー | Minor | 名前付き定数に抽出 |

---

### Task 1: Domain Repositories（CompanyRepository, FinancialRepository, ValuationRepository）

**Files:**
- Create: `src/stock_analyze_system/repositories/company.py`
- Create: `src/stock_analyze_system/repositories/financial.py`
- Create: `src/stock_analyze_system/repositories/valuation.py`
- Create: `tests/unit/repositories/__init__.py`
- Create: `tests/unit/repositories/test_company_repo.py`
- Create: `tests/unit/repositories/test_financial_repo.py`
- Create: `tests/unit/repositories/test_valuation_repo.py`
- Existing: `src/stock_analyze_system/repositories/base.py` — BaseRepository[T] 基底クラス
- Existing: `src/stock_analyze_system/models/company.py` — Company モデル
- Existing: `src/stock_analyze_system/models/financial_data.py` — FinancialData モデル（UniqueConstraint: company_id + period_type + fiscal_year_end + accounting_standard）
- Existing: `src/stock_analyze_system/models/valuation.py` — Valuation モデル（UniqueConstraint: company_id + date）
- Existing: `tests/conftest.py` — `async_engine`, `session` フィクスチャ（インメモリ SQLite）

- [ ] **Step 1: テストを書く**

```python
# tests/unit/repositories/__init__.py
# (空ファイル)

# tests/unit/repositories/test_company_repo.py
"""CompanyRepository のテスト"""
from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.company import CompanyRepository


async def test_find_by_identifier_ticker(session):
    """ticker で企業を検索できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple Inc.",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    result = await repo.find_by_identifier("AAPL")
    assert result is not None
    assert result.id == "US_AAPL"


async def test_find_by_identifier_security_code(session):
    """security_code で企業を検索できること"""
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        market="TSE_PRIME", accounting_standard="IFRS",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    result = await repo.find_by_identifier("7203")
    assert result is not None
    assert result.id == "JP_7203"


async def test_find_by_identifier_company_id(session):
    """company_id のサフィックスで検索できること"""
    session.add(Company(
        id="US_MSFT", ticker="MSFT", name="Microsoft",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    result = await repo.find_by_identifier("US_MSFT")
    assert result is not None
    assert result.id == "US_MSFT"


async def test_find_by_identifier_not_found(session):
    """存在しない識別子で None が返ること"""
    repo = CompanyRepository(session)
    result = await repo.find_by_identifier("NONEXIST")
    assert result is None


async def test_search(session):
    """部分一致検索が動作すること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple Inc.",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="US_MSFT", ticker="MSFT", name="Microsoft Corp.",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    results = await repo.search("apple")
    assert len(results) == 1
    assert results[0].id == "US_AAPL"


async def test_search_japanese_name(session):
    """日本語名での部分一致検索が動作すること"""
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        name_ja="トヨタ自動車", market="TSE_PRIME", accounting_standard="IFRS",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    results = await repo.search("トヨタ")
    assert len(results) == 1


async def test_list_by_market(session):
    """市場別一覧が取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        market="TSE_PRIME", accounting_standard="IFRS",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    results = await repo.list_by_market("NASDAQ")
    assert len(results) == 1
    assert results[0].id == "US_AAPL"
```

```python
# tests/unit/repositories/test_financial_repo.py
"""FinancialRepository のテスト"""
from datetime import date

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.repositories.financial import FinancialRepository


async def test_get_timeseries(session):
    """時系列データを fiscal_year_end 降順で取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    for yr in (2022, 2023, 2024):
        session.add(FinancialData(
            company_id="US_AAPL", accounting_standard="US-GAAP",
            currency="USD", period_type="annual",
            fiscal_year_end=date(yr, 9, 28), revenue=float(yr * 1e9),
        ))
    await session.flush()
    repo = FinancialRepository(session)
    results = await repo.get_timeseries("US_AAPL", "annual", years=5)
    assert len(results) == 3
    assert results[0].fiscal_year_end > results[1].fiscal_year_end


async def test_get_latest(session):
    """最新レコードを1件取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual",
        fiscal_year_end=date(2023, 9, 28), revenue=383e9,
    ))
    session.add(FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual",
        fiscal_year_end=date(2024, 9, 28), revenue=394e9,
    ))
    await session.flush()
    repo = FinancialRepository(session)
    result = await repo.get_latest("US_AAPL", "annual")
    assert result is not None
    assert result.fiscal_year_end == date(2024, 9, 28)


async def test_get_latest_none(session):
    """データなしの場合 None を返すこと"""
    repo = FinancialRepository(session)
    result = await repo.get_latest("US_NONEXIST", "annual")
    assert result is None


async def test_bulk_upsert(session):
    """一括 upsert で新規挿入と更新が動作すること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FinancialRepository(session)
    records = [
        {
            "accounting_standard": "US-GAAP", "currency": "USD",
            "period_type": "annual", "fiscal_year_end": date(2024, 9, 28),
            "revenue": 394e9,
        },
    ]
    count = await repo.bulk_upsert("US_AAPL", records)
    assert count == 1
    # 再実行で更新されること
    records[0]["revenue"] = 400e9
    count = await repo.bulk_upsert("US_AAPL", records)
    assert count == 1
    result = await repo.get_latest("US_AAPL", "annual")
    assert result.revenue == 400e9
```

```python
# tests/unit/repositories/test_valuation_repo.py
"""ValuationRepository のテスト"""
from datetime import date

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.valuation import Valuation
from stock_analyze_system.repositories.valuation import ValuationRepository


async def test_get_history(session):
    """履歴を date 降順で取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    for month in (1, 2, 3):
        session.add(Valuation(
            company_id="US_AAPL", currency="USD",
            date=date(2024, month, 1), stock_price=180.0 + month,
        ))
    await session.flush()
    repo = ValuationRepository(session)
    results = await repo.get_history("US_AAPL", years=1)
    assert len(results) == 3
    assert results[0].date > results[1].date


async def test_get_latest(session):
    """最新バリュエーションを取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(Valuation(
        company_id="US_AAPL", currency="USD",
        date=date(2024, 1, 1), stock_price=185.0, per=28.5,
    ))
    session.add(Valuation(
        company_id="US_AAPL", currency="USD",
        date=date(2024, 6, 1), stock_price=210.0, per=32.0,
    ))
    await session.flush()
    repo = ValuationRepository(session)
    result = await repo.get_latest("US_AAPL")
    assert result is not None
    assert result.date == date(2024, 6, 1)


async def test_bulk_upsert(session):
    """一括 upsert が動作すること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = ValuationRepository(session)
    records = [
        {"currency": "USD", "date": date(2024, 1, 1), "stock_price": 185.0},
        {"currency": "USD", "date": date(2024, 2, 1), "stock_price": 190.0},
    ]
    count = await repo.bulk_upsert("US_AAPL", records)
    assert count == 2
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/repositories/ -v --no-header 2>&1 | head -30`
Expected: FAIL (import errors — モジュールが存在しない)

- [ ] **Step 3: 実装を書く**

```python
# src/stock_analyze_system/repositories/company.py
"""企業リポジトリ"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.base import BaseRepository


class CompanyRepository(BaseRepository[Company]):
    """Company ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Company)

    async def find_by_identifier(self, query: str) -> Company | None:
        """ticker / security_code / company_id いずれでも検索"""
        q = query.upper()
        stmt = select(Company).where(
            or_(
                Company.ticker.ilike(q),
                Company.security_code.ilike(q),
                Company.id.ilike(q),
                Company.id.ilike(f"%_{q}"),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(self, query: str, limit: int = 20) -> list[Company]:
        """名前/ticker/security_code/日本語名で部分一致検索"""
        pattern = f"%{query}%"
        stmt = (
            select(Company)
            .where(
                or_(
                    Company.name.ilike(pattern),
                    Company.ticker.ilike(pattern),
                    Company.security_code.ilike(pattern),
                    Company.name_ja.ilike(pattern),
                )
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_market(self, market: str) -> list[Company]:
        """市場別一覧"""
        return await self.list_all(market=market)
```

```python
# src/stock_analyze_system/repositories/financial.py
"""財務データリポジトリ"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class FinancialRepository(BaseRepository[FinancialData]):
    """FinancialData ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, FinancialData)

    async def get_timeseries(
        self, company_id: str, period_type: str, years: int = 10,
    ) -> list[FinancialData]:
        """時系列データを fiscal_year_end 降順で取得"""
        cutoff = date.today() - timedelta(days=years * 365)
        stmt = (
            select(FinancialData)
            .where(
                FinancialData.company_id == company_id,
                FinancialData.period_type == period_type,
                FinancialData.fiscal_year_end >= cutoff,
            )
            .order_by(FinancialData.fiscal_year_end.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(
        self, company_id: str, period_type: str,
    ) -> FinancialData | None:
        """最新レコードを1件取得"""
        stmt = (
            select(FinancialData)
            .where(
                FinancialData.company_id == company_id,
                FinancialData.period_type == period_type,
            )
            .order_by(FinancialData.fiscal_year_end.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def bulk_upsert(
        self, company_id: str, records: list[dict],
    ) -> int:
        """一括 upsert。戻り値は処理レコード数。"""
        count = 0
        for record in records:
            filters = {
                "company_id": company_id,
                "period_type": record["period_type"],
                "fiscal_year_end": record["fiscal_year_end"],
                "accounting_standard": record["accounting_standard"],
            }
            data = {k: v for k, v in record.items()
                    if k not in ("period_type", "fiscal_year_end", "accounting_standard")}
            await self.upsert(filters, data)
            count += 1
        return count
```

```python
# src/stock_analyze_system/repositories/valuation.py
"""バリュエーションリポジトリ"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.valuation import Valuation
from stock_analyze_system.repositories.base import BaseRepository


class ValuationRepository(BaseRepository[Valuation]):
    """Valuation ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Valuation)

    async def get_history(
        self, company_id: str, years: int = 10,
    ) -> list[Valuation]:
        """履歴を date 降順で取得"""
        cutoff = date.today() - timedelta(days=years * 365)
        stmt = (
            select(Valuation)
            .where(
                Valuation.company_id == company_id,
                Valuation.date >= cutoff,
            )
            .order_by(Valuation.date.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(self, company_id: str) -> Valuation | None:
        """最新バリュエーションを取得"""
        stmt = (
            select(Valuation)
            .where(Valuation.company_id == company_id)
            .order_by(Valuation.date.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def bulk_upsert(
        self, company_id: str, records: list[dict],
    ) -> int:
        """一括 upsert。戻り値は処理レコード数。"""
        count = 0
        for record in records:
            filters = {
                "company_id": company_id,
                "date": record["date"],
            }
            data = {k: v for k, v in record.items() if k != "date"}
            await self.upsert(filters, data)
            count += 1
        return count
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/repositories/test_company_repo.py tests/unit/repositories/test_financial_repo.py tests/unit/repositories/test_valuation_repo.py -v --no-header 2>&1 | tail -20`
Expected: ALL PASSED

- [ ] **Step 5: コミット**

```bash
cd <repo-root>
git add src/stock_analyze_system/repositories/company.py src/stock_analyze_system/repositories/financial.py src/stock_analyze_system/repositories/valuation.py tests/unit/repositories/
git commit -m "feat: add Company, Financial, Valuation repositories"
```

---

### Task 2: Domain Repositories（Filing, Analysis, Watchlist, Screening, Target, DocumentIndex）

**Files:**
- Create: `src/stock_analyze_system/repositories/filing.py`
- Create: `src/stock_analyze_system/repositories/analysis.py`
- Create: `src/stock_analyze_system/repositories/watchlist.py`
- Create: `src/stock_analyze_system/repositories/screening.py`
- Create: `src/stock_analyze_system/repositories/target.py`
- Create: `src/stock_analyze_system/repositories/document_index.py`
- Create: `tests/unit/repositories/test_filing_repo.py`
- Create: `tests/unit/repositories/test_other_repos.py`
- Existing: `src/stock_analyze_system/models/filing.py` — Filing モデル（accession_no unique, doc_id unique）
- Existing: `src/stock_analyze_system/models/company_analysis.py` — CompanyAnalysis モデル（UniqueConstraint: company_id + filing_id + analysis_type）
- Existing: `src/stock_analyze_system/models/watchlist.py` — Watchlist + WatchlistItem
- Existing: `src/stock_analyze_system/models/screening.py` — ScreeningCache（company_id が PK）
- Existing: `src/stock_analyze_system/models/analysis_target.py` — AnalysisTarget（company_id unique）
- Existing: `src/stock_analyze_system/models/document_index.py` — DocumentIndex（filing_id unique）

- [ ] **Step 1: テストを書く**

```python
# tests/unit/repositories/test_filing_repo.py
"""FilingRepository のテスト"""
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.filing import FilingRepository


async def test_get_latest_filing(session):
    """最新ファイリングを filing_type 指定で取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2023,
    ))
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
    ))
    await session.flush()
    repo = FilingRepository(session)
    result = await repo.get_latest_filing("US_AAPL", "10-K")
    assert result is not None
    assert result.fiscal_year == 2024


async def test_list_filings(session):
    """企業のファイリング一覧を取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
    ))
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-Q",
        period_type="quarterly", fiscal_year=2024,
    ))
    await session.flush()
    repo = FilingRepository(session)
    results = await repo.list_filings("US_AAPL")
    assert len(results) == 2


async def test_find_by_accession(session):
    """accession_no で検索できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000320193-24-000123",
    ))
    await session.flush()
    repo = FilingRepository(session)
    result = await repo.find_by_accession("0000320193-24-000123")
    assert result is not None
    assert result.fiscal_year == 2024


async def test_find_by_doc_id(session):
    """doc_id で検索できること"""
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        market="TSE_PRIME", accounting_standard="IFRS",
    ))
    await session.flush()
    session.add(Filing(
        company_id="JP_7203", source="EDINET", filing_type="annual_report",
        period_type="annual", fiscal_year=2024, doc_id="S100ABC123",
    ))
    await session.flush()
    repo = FilingRepository(session)
    result = await repo.find_by_doc_id("S100ABC123")
    assert result is not None
```

```python
# tests/unit/repositories/test_other_repos.py
"""Analysis, Watchlist, Screening, Target, DocumentIndex リポジトリのテスト"""
from datetime import datetime, timezone

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.company_analysis import CompanyAnalysis
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem
from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.models.analysis_target import AnalysisTarget
from stock_analyze_system.models.document_index import DocumentIndex
from stock_analyze_system.repositories.analysis import AnalysisRepository
from stock_analyze_system.repositories.watchlist import WatchlistRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.repositories.target import TargetRepository
from stock_analyze_system.repositories.document_index import DocumentIndexRepository


async def _setup_company_and_filing(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    f = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
    )
    session.add(f)
    await session.flush()
    return f


# --- AnalysisRepository ---

async def test_analysis_get_by_type(session):
    """分析タイプ別取得ができること"""
    f = await _setup_company_and_filing(session)
    session.add(CompanyAnalysis(
        company_id="US_AAPL", filing_id=f.id,
        analysis_type="financial_summary",
        result_json='{"summary": "test"}', model_name="test-model",
    ))
    await session.flush()
    repo = AnalysisRepository(session)
    result = await repo.get_by_type("US_AAPL", f.id, "financial_summary")
    assert result is not None
    assert result.analysis_type == "financial_summary"


async def test_analysis_get_analyses(session):
    """企業+ファイリングの分析結果一覧を取得できること"""
    f = await _setup_company_and_filing(session)
    session.add(CompanyAnalysis(
        company_id="US_AAPL", filing_id=f.id,
        analysis_type="type_a",
        result_json='{}', model_name="test-model",
    ))
    session.add(CompanyAnalysis(
        company_id="US_AAPL", filing_id=f.id,
        analysis_type="type_b",
        result_json='{}', model_name="test-model",
    ))
    await session.flush()
    repo = AnalysisRepository(session)
    results = await repo.get_analyses("US_AAPL", f.id)
    assert len(results) == 2


# --- WatchlistRepository ---

async def test_watchlist_get_by_name(session):
    """名前でウォッチリストを取得できること"""
    session.add(Watchlist(name="My List"))
    await session.flush()
    repo = WatchlistRepository(session)
    result = await repo.get_by_name("My List")
    assert result is not None
    assert result.name == "My List"


async def test_watchlist_find_item(session):
    """ウォッチリストアイテムを検索できること"""
    wl = Watchlist(name="Test")
    session.add(wl)
    await session.flush()
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    item = WatchlistItem(watchlist_id=wl.id, company_id="US_AAPL")
    session.add(item)
    await session.flush()
    repo = WatchlistRepository(session)
    result = await repo.find_item(wl.id, "US_AAPL")
    assert result is not None


# --- ScreeningRepository ---

async def test_screening_upsert_and_get_cache(session):
    """スクリーニングキャッシュの upsert と取得"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = ScreeningRepository(session)
    await repo.upsert_cache("US_AAPL", {"stock_price": 185.0, "per": 28.5})
    result = await repo.get_cache("US_AAPL")
    assert result is not None
    assert result.stock_price == 185.0


# --- TargetRepository ---

async def test_target_list_and_find(session):
    """ターゲット一覧と企業別検索"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = TargetRepository(session)
    target = AnalysisTarget(company_id="US_AAPL", source="manual")
    session.add(target)
    await session.flush()
    results = await repo.list_targets()
    assert len(results) == 1
    found = await repo.find_by_company("US_AAPL")
    assert found is not None


async def test_target_bulk_add(session):
    """一括追加（重複スキップ）"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="US_MSFT", ticker="MSFT", name="Microsoft",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = TargetRepository(session)
    count = await repo.bulk_add([
        {"company_id": "US_AAPL", "source": "screening"},
        {"company_id": "US_MSFT", "source": "screening"},
    ])
    assert count == 2
    # 重複追加 → スキップ
    count = await repo.bulk_add([
        {"company_id": "US_AAPL", "source": "screening"},
    ])
    assert count == 0


# --- DocumentIndexRepository ---

async def test_document_index_save_and_get(session):
    """インデックスの保存と取得"""
    f = await _setup_company_and_filing(session)
    repo = DocumentIndexRepository(session)
    di = await repo.save_index(
        filing_id=f.id, company_id="US_AAPL",
        data={"index_json": '{"nodes": []}', "model_name": "test",
              "page_count": 10, "node_count": 5},
    )
    assert di.id is not None
    result = await repo.get_by_filing(f.id)
    assert result is not None
    assert result.page_count == 10
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/repositories/test_filing_repo.py tests/unit/repositories/test_other_repos.py -v --no-header 2>&1 | head -20`
Expected: FAIL (import errors)

- [ ] **Step 3: 実装を書く**

```python
# src/stock_analyze_system/repositories/filing.py
"""ファイリングリポジトリ"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.base import BaseRepository


class FilingRepository(BaseRepository[Filing]):
    """Filing ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Filing)

    async def get_latest_filing(
        self, company_id: str, filing_type: str,
    ) -> Filing | None:
        """最新ファイリングを取得"""
        stmt = (
            select(Filing)
            .where(
                Filing.company_id == company_id,
                Filing.filing_type == filing_type,
            )
            .order_by(Filing.fiscal_year.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_filings(self, company_id: str) -> list[Filing]:
        """企業のファイリング一覧（fiscal_year 降順）"""
        stmt = (
            select(Filing)
            .where(Filing.company_id == company_id)
            .order_by(Filing.fiscal_year.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_accession(self, accession_no: str) -> Filing | None:
        """accession_no で検索"""
        stmt = select(Filing).where(Filing.accession_no == accession_no)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_doc_id(self, doc_id: str) -> Filing | None:
        """doc_id で検索"""
        stmt = select(Filing).where(Filing.doc_id == doc_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
```

```python
# src/stock_analyze_system/repositories/analysis.py
"""分析結果リポジトリ"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.company_analysis import CompanyAnalysis
from stock_analyze_system.repositories.base import BaseRepository


class AnalysisRepository(BaseRepository[CompanyAnalysis]):
    """CompanyAnalysis ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, CompanyAnalysis)

    async def get_analyses(
        self, company_id: str, filing_id: int,
    ) -> list[CompanyAnalysis]:
        """企業+ファイリングの分析結果一覧"""
        stmt = select(CompanyAnalysis).where(
            CompanyAnalysis.company_id == company_id,
            CompanyAnalysis.filing_id == filing_id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_type(
        self, company_id: str, filing_id: int, analysis_type: str,
    ) -> CompanyAnalysis | None:
        """タイプ別取得"""
        stmt = select(CompanyAnalysis).where(
            CompanyAnalysis.company_id == company_id,
            CompanyAnalysis.filing_id == filing_id,
            CompanyAnalysis.analysis_type == analysis_type,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
```

```python
# src/stock_analyze_system/repositories/watchlist.py
"""ウォッチリストリポジトリ"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem
from stock_analyze_system.repositories.base import BaseRepository


class WatchlistRepository(BaseRepository[Watchlist]):
    """Watchlist ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Watchlist)

    async def get_by_name(self, name: str) -> Watchlist | None:
        """名前検索"""
        stmt = select(Watchlist).where(Watchlist.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_items(self, watchlist_id: int) -> list[WatchlistItem]:
        """アイテム一覧"""
        stmt = select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_item(
        self, watchlist_id: int, company_id: str,
    ) -> WatchlistItem | None:
        """アイテム検索"""
        stmt = select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.company_id == company_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_item(
        self, watchlist_id: int, company_id: str,
        status: str = "monitoring", investment_thesis: str | None = None,
    ) -> WatchlistItem:
        """アイテム追加"""
        item = WatchlistItem(
            watchlist_id=watchlist_id, company_id=company_id,
            status=status, investment_thesis=investment_thesis,
        )
        self._session.add(item)
        await self._session.flush()
        return item

    async def delete_item(self, item: WatchlistItem) -> None:
        """アイテム削除"""
        await self._session.delete(item)
        await self._session.flush()
```

```python
# src/stock_analyze_system/repositories/screening.py
"""スクリーニングキャッシュリポジトリ"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.repositories.base import BaseRepository


class ScreeningRepository(BaseRepository[ScreeningCache]):
    """ScreeningCache ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ScreeningCache)

    async def get_cache(self, company_id: str) -> ScreeningCache | None:
        """キャッシュ取得（PK が company_id）"""
        return await self.get_by_id(company_id)

    async def upsert_cache(self, company_id: str, data: dict) -> ScreeningCache:
        """キャッシュ upsert"""
        return await self.upsert({"company_id": company_id}, data)

    async def list_stale(self, hours: int = 24) -> list[ScreeningCache]:
        """指定時間以上古いキャッシュ一覧"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = select(ScreeningCache).where(
            ScreeningCache.updated_at < cutoff,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

```python
# src/stock_analyze_system/repositories/target.py
"""分析対象リポジトリ"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.analysis_target import AnalysisTarget
from stock_analyze_system.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class TargetRepository(BaseRepository[AnalysisTarget]):
    """AnalysisTarget ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, AnalysisTarget)

    async def list_targets(self) -> list[AnalysisTarget]:
        """全ターゲット一覧"""
        return await self.list_all()

    async def find_by_company(self, company_id: str) -> AnalysisTarget | None:
        """企業ID で検索"""
        stmt = select(AnalysisTarget).where(
            AnalysisTarget.company_id == company_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def bulk_add(self, records: list[dict]) -> int:
        """一括追加（既存はスキップ）。戻り値は追加数。"""
        count = 0
        for record in records:
            existing = await self.find_by_company(record["company_id"])
            if existing is not None:
                continue
            target = AnalysisTarget(**record)
            self._session.add(target)
            await self._session.flush()
            count += 1
        return count
```

```python
# src/stock_analyze_system/repositories/document_index.py
"""ドキュメントインデックスリポジトリ"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.document_index import DocumentIndex
from stock_analyze_system.repositories.base import BaseRepository


class DocumentIndexRepository(BaseRepository[DocumentIndex]):
    """DocumentIndex ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, DocumentIndex)

    async def get_by_filing(self, filing_id: int) -> DocumentIndex | None:
        """filing_id で検索"""
        stmt = select(DocumentIndex).where(
            DocumentIndex.filing_id == filing_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def save_index(
        self, filing_id: int, company_id: str, data: dict,
    ) -> DocumentIndex:
        """インデックスを upsert"""
        return await self.upsert(
            {"filing_id": filing_id},
            {"company_id": company_id, **data},
        )
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/repositories/ -v --no-header 2>&1 | tail -30`
Expected: ALL PASSED

- [ ] **Step 5: コミット**

```bash
cd <repo-root>
git add src/stock_analyze_system/repositories/filing.py src/stock_analyze_system/repositories/analysis.py src/stock_analyze_system/repositories/watchlist.py src/stock_analyze_system/repositories/screening.py src/stock_analyze_system/repositories/target.py src/stock_analyze_system/repositories/document_index.py tests/unit/repositories/test_filing_repo.py tests/unit/repositories/test_other_repos.py
git commit -m "feat: add Filing, Analysis, Watchlist, Screening, Target, DocumentIndex repositories"
```

---

### Task 3: metrics.py — 財務指標の純粋関数群

**Files:**
- Create: `src/stock_analyze_system/services/__init__.py`
- Create: `src/stock_analyze_system/services/metrics.py`
- Create: `tests/unit/services/__init__.py`
- Create: `tests/unit/services/test_metrics.py`
- Reference: `<legacy-stock-analyzer-repo>/src/stock_analyzer/services/metrics.py` — 25個の純粋関数。全関数が `float | None` を返す安全設計。`_safe_div` ヘルパーで除算を統一。

**注意点:**
- 参考プロジェクトの metrics.py は完成度が高くバグなし。同一の関数シグネチャと動作を踏襲する
- `_safe_div(numerator, denominator, require_positive_denom)` を基盤とする
- 全関数は同期（I/Oなし）、副作用なし

- [ ] **Step 1: テストを書く**

```python
# tests/unit/services/__init__.py
# (空ファイル)

# tests/unit/services/test_metrics.py
"""metrics 純粋関数のテスト"""
import pytest

from stock_analyze_system.services import metrics


class TestSafeDiv:
    def test_normal(self):
        assert metrics._safe_div(10.0, 2.0) == 5.0

    def test_none_numerator(self):
        assert metrics._safe_div(None, 2.0) is None

    def test_none_denominator(self):
        assert metrics._safe_div(10.0, None) is None

    def test_zero_denominator(self):
        assert metrics._safe_div(10.0, 0.0) is None

    def test_negative_denom_allowed(self):
        assert metrics._safe_div(10.0, -2.0) == -5.0

    def test_negative_denom_rejected(self):
        assert metrics._safe_div(10.0, -2.0, require_positive_denom=True) is None


class TestProfitability:
    def test_operating_margin(self):
        assert metrics.operating_margin(30.0, 100.0) == pytest.approx(0.3)

    def test_operating_margin_none(self):
        assert metrics.operating_margin(None, 100.0) is None

    def test_net_margin(self):
        assert metrics.net_margin(20.0, 100.0) == pytest.approx(0.2)

    def test_roe(self):
        assert metrics.roe(10.0, 50.0) == pytest.approx(0.2)

    def test_roa(self):
        assert metrics.roa(10.0, 200.0) == pytest.approx(0.05)

    def test_roic(self):
        result = metrics.roic(
            operating_income=100.0, tax_expense=25.0,
            income_before_tax=100.0, total_debt=200.0,
            equity=300.0, cash=50.0,
        )
        # NOPAT = 100 * (1 - 0.25) = 75, IC = 200 + 300 - 50 = 450
        assert result == pytest.approx(75.0 / 450.0)

    def test_roic_negative_income_before_tax(self):
        assert metrics.roic(100.0, 25.0, -10.0, 200.0, 300.0, 50.0) is None

    def test_roic_zero_invested_capital(self):
        assert metrics.roic(100.0, 25.0, 100.0, 0.0, 50.0, 50.0) is None


class TestEfficiency:
    def test_asset_turnover(self):
        assert metrics.asset_turnover(200.0, 400.0) == pytest.approx(0.5)

    def test_inventory_turnover(self):
        assert metrics.inventory_turnover(150.0, 50.0) == pytest.approx(3.0)


class TestStability:
    def test_equity_ratio(self):
        assert metrics.equity_ratio(100.0, 400.0) == pytest.approx(0.25)

    def test_current_ratio(self):
        assert metrics.current_ratio(150.0, 100.0) == pytest.approx(1.5)

    def test_de_ratio(self):
        assert metrics.de_ratio(200.0, 400.0) == pytest.approx(0.5)


class TestGrowth:
    def test_revenue_growth(self):
        assert metrics.revenue_growth(110.0, 100.0) == pytest.approx(0.1)

    def test_revenue_growth_zero_previous(self):
        assert metrics.revenue_growth(110.0, 0.0) is None

    def test_revenue_growth_negative_previous(self):
        assert metrics.revenue_growth(110.0, -10.0) is None

    def test_eps_growth(self):
        assert metrics.eps_growth(5.5, 5.0) == pytest.approx(0.1)

    def test_eps_growth_negative_previous(self):
        assert metrics.eps_growth(5.5, -5.0) is None

    def test_fcf_growth(self):
        assert metrics.fcf_growth(22.0, 20.0) == pytest.approx(0.1)


class TestShareholderReturn:
    def test_dividend_payout_primary(self):
        result = metrics.dividend_payout_ratio(dividends_paid=-50.0, net_income=100.0)
        assert result == pytest.approx(0.5)

    def test_dividend_payout_fallback(self):
        result = metrics.dividend_payout_ratio(dps=2.0, eps=4.0)
        assert result == pytest.approx(0.5)

    def test_total_payout_ratio(self):
        result = metrics.total_payout_ratio(-30.0, -20.0, 100.0)
        assert result == pytest.approx(0.5)


class TestValuation:
    def test_per_primary(self):
        assert metrics.per(stock_price=100.0, eps=5.0) == pytest.approx(20.0)

    def test_per_fallback(self):
        assert metrics.per(market_cap=1000.0, net_income=50.0) == pytest.approx(20.0)

    def test_per_negative_eps(self):
        assert metrics.per(stock_price=100.0, eps=-5.0) is None

    def test_pbr(self):
        assert metrics.pbr(1000.0, 500.0) == pytest.approx(2.0)

    def test_ev_ebitda(self):
        result = metrics.ev_ebitda(
            market_cap=1000.0, total_debt=200.0, cash=100.0, ebitda=110.0,
        )
        assert result == pytest.approx((1000 + 200 - 100) / 110)

    def test_ev_ebitda_negative_ebitda(self):
        assert metrics.ev_ebitda(1000.0, 200.0, 100.0, -10.0) is None

    def test_psr(self):
        assert metrics.psr(1000.0, 500.0) == pytest.approx(2.0)

    def test_peg_ratio(self):
        result = metrics.peg_ratio(20.0, 0.15)
        assert result == pytest.approx(20.0 / 15.0)

    def test_peg_ratio_zero_growth(self):
        assert metrics.peg_ratio(20.0, 0.0) is None

    def test_peg_ratio_negative_growth(self):
        assert metrics.peg_ratio(20.0, -0.1) is None


class TestUtilities:
    def test_cagr(self):
        result = metrics.cagr(100.0, 200.0, 5.0)
        assert result == pytest.approx((200 / 100) ** (1 / 5) - 1)

    def test_cagr_negative_begin(self):
        assert metrics.cagr(-100.0, 200.0, 5.0) is None

    def test_is_anomaly_true(self):
        assert metrics.is_anomaly(140.0, 100.0, threshold=0.3) is True

    def test_is_anomaly_false(self):
        assert metrics.is_anomaly(110.0, 100.0, threshold=0.3) is False

    def test_is_anomaly_none(self):
        assert metrics.is_anomaly(None, 100.0) is None
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_metrics.py -v --no-header 2>&1 | head -20`
Expected: FAIL (module not found)

- [ ] **Step 3: 実装を書く**

```python
# src/stock_analyze_system/services/__init__.py
# (空ファイル)

# src/stock_analyze_system/services/metrics.py
"""財務指標の純粋関数群（同期・副作用なし）"""
from __future__ import annotations


def _safe_div(
    numerator: float | None, denominator: float | None,
    *, require_positive_denom: bool = False,
) -> float | None:
    """numerator / denominator を安全に計算。無効な入力は None を返す。"""
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    if require_positive_denom and denominator < 0:
        return None
    return numerator / denominator


# ── Profitability ──────────────────────────────────────────────

def operating_margin(operating_income: float | None,
                     revenue: float | None) -> float | None:
    return _safe_div(operating_income, revenue, require_positive_denom=True)


def net_margin(net_income: float | None,
               revenue: float | None) -> float | None:
    return _safe_div(net_income, revenue, require_positive_denom=True)


def roe(net_income: float | None,
        equity: float | None) -> float | None:
    return _safe_div(net_income, equity, require_positive_denom=True)


def roa(net_income: float | None,
        total_assets: float | None) -> float | None:
    return _safe_div(net_income, total_assets, require_positive_denom=True)


def roic(operating_income: float | None,
         tax_expense: float | None,
         income_before_tax: float | None,
         total_debt: float | None,
         equity: float | None,
         cash: float | None) -> float | None:
    if any(v is None for v in (operating_income, tax_expense,
                                income_before_tax, total_debt, equity, cash)):
        return None
    if income_before_tax == 0 or income_before_tax < 0:
        return None
    tax_rate = tax_expense / income_before_tax
    nopat = operating_income * (1.0 - tax_rate)
    invested_capital = total_debt + equity - cash
    if invested_capital <= 0:
        return None
    return nopat / invested_capital


# ── Efficiency ─────────────────────────────────────────────────

def asset_turnover(revenue: float | None,
                   total_assets: float | None) -> float | None:
    return _safe_div(revenue, total_assets, require_positive_denom=True)


def inventory_turnover(cogs: float | None,
                       inventory: float | None) -> float | None:
    return _safe_div(cogs, inventory, require_positive_denom=True)


# ── Stability ──────────────────────────────────────────────────

def equity_ratio(equity: float | None,
                 total_assets: float | None) -> float | None:
    return _safe_div(equity, total_assets, require_positive_denom=True)


def current_ratio(current_assets: float | None,
                  current_liabilities: float | None) -> float | None:
    return _safe_div(current_assets, current_liabilities, require_positive_denom=True)


def de_ratio(total_debt: float | None,
             equity: float | None) -> float | None:
    return _safe_div(total_debt, equity, require_positive_denom=True)


# ── Growth ─────────────────────────────────────────────────────

def revenue_growth(revenue_current: float | None,
                   revenue_previous: float | None) -> float | None:
    if revenue_current is None or revenue_previous is None:
        return None
    if revenue_previous <= 0:
        return None
    return (revenue_current - revenue_previous) / revenue_previous


def eps_growth(eps_current: float | None,
               eps_previous: float | None) -> float | None:
    if eps_current is None or eps_previous is None:
        return None
    if eps_previous == 0 or eps_previous < 0:
        return None
    return (eps_current - eps_previous) / eps_previous


def fcf_growth(fcf_current: float | None,
               fcf_previous: float | None) -> float | None:
    if fcf_current is None or fcf_previous is None:
        return None
    if fcf_previous == 0 or fcf_previous < 0:
        return None
    return (fcf_current - fcf_previous) / fcf_previous


# ── Shareholder Return ─────────────────────────────────────────

def dividend_payout_ratio(dividends_paid: float | None = None,
                          net_income: float | None = None,
                          dps: float | None = None,
                          eps: float | None = None) -> float | None:
    if dividends_paid is not None and net_income is not None and net_income > 0:
        return abs(dividends_paid) / net_income
    if dps is not None and eps is not None and eps > 0:
        return dps / eps
    return None


def total_payout_ratio(dividends_paid: float | None,
                       share_repurchases: float | None,
                       net_income: float | None) -> float | None:
    if any(v is None for v in (dividends_paid, share_repurchases, net_income)):
        return None
    if net_income <= 0:
        return None
    return (abs(dividends_paid) + abs(share_repurchases)) / net_income


# ── Valuation ──────────────────────────────────────────────────

def per(stock_price: float | None = None,
        eps: float | None = None,
        market_cap: float | None = None,
        net_income: float | None = None) -> float | None:
    if stock_price is not None and eps is not None and eps > 0:
        return stock_price / eps
    if market_cap is not None and net_income is not None and net_income > 0:
        return market_cap / net_income
    return None


def pbr(market_cap: float | None,
        equity: float | None) -> float | None:
    return _safe_div(market_cap, equity, require_positive_denom=True)


def ev_ebitda(market_cap: float | None,
              total_debt: float | None,
              cash: float | None,
              ebitda: float | None) -> float | None:
    if any(v is None for v in (market_cap, total_debt, cash, ebitda)):
        return None
    if ebitda <= 0:
        return None
    ev = market_cap + total_debt - cash
    return ev / ebitda


def psr(market_cap: float | None,
        revenue: float | None) -> float | None:
    return _safe_div(market_cap, revenue, require_positive_denom=True)


def peg_ratio(per_value: float | None,
              eps_growth_rate: float | None) -> float | None:
    if per_value is None or eps_growth_rate is None:
        return None
    if eps_growth_rate <= 0:
        return None
    growth_pct = eps_growth_rate * 100
    if growth_pct == 0:
        return None
    return per_value / growth_pct


# ── Utilities ──────────────────────────────────────────────────

def cagr(begin_value: float | None,
         end_value: float | None,
         years: float | None) -> float | None:
    if any(v is None for v in (begin_value, end_value, years)):
        return None
    if begin_value <= 0 or end_value <= 0 or years <= 0:
        return None
    return (end_value / begin_value) ** (1.0 / years) - 1.0


def is_anomaly(current: float | None,
               previous: float | None,
               threshold: float = 0.3) -> bool | None:
    if current is None or previous is None:
        return None
    if previous == 0:
        return None
    change = abs((current - previous) / previous)
    return change > threshold
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_metrics.py -v --no-header 2>&1 | tail -30`
Expected: ALL PASSED

- [ ] **Step 5: コミット**

```bash
cd <repo-root>
git add src/stock_analyze_system/services/__init__.py src/stock_analyze_system/services/metrics.py tests/unit/services/__init__.py tests/unit/services/test_metrics.py
git commit -m "feat: add metrics.py with 25 pure financial metric functions"
```

---

### Task 4: CompanyService（Bug #7 修正含む）

**Files:**
- Create: `src/stock_analyze_system/services/company.py`
- Create: `tests/unit/services/test_company_service.py`
- Existing: `src/stock_analyze_system/repositories/company.py` — CompanyRepository（Task 1 で作成）
- Existing: `src/stock_analyze_system/models/company.py` — Company モデル

**Bug #7 対策:** `build_company_id()` で `_US_MARKETS` と `_JP_MARKETS` の両方を検証し、未知市場で `ValueError` を raise する。

- [ ] **Step 1: テストを書く**

```python
# tests/unit/services/test_company_service.py
"""CompanyService のテスト"""
import pytest

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.services.company import CompanyService


class TestBuildCompanyId:
    """build_company_id 静的メソッド（Bug #7 修正確認含む）"""

    def test_us_market(self):
        assert CompanyService.build_company_id(
            ticker="AAPL", security_code=None, market="NASDAQ",
        ) == "US_AAPL"

    def test_jp_market(self):
        assert CompanyService.build_company_id(
            ticker=None, security_code="7203", market="TSE_PRIME",
        ) == "JP_7203"

    def test_unknown_market_raises(self):
        """Bug #7: 未知の市場で ValueError が発生すること"""
        with pytest.raises(ValueError, match="Unknown market"):
            CompanyService.build_company_id(
                ticker="TEST", security_code=None, market="INVALID_MARKET",
            )

    def test_us_market_no_ticker_raises(self):
        with pytest.raises(ValueError, match="ticker is required"):
            CompanyService.build_company_id(
                ticker=None, security_code=None, market="NYSE",
            )

    def test_jp_market_no_security_code_raises(self):
        with pytest.raises(ValueError, match="security_code is required"):
            CompanyService.build_company_id(
                ticker=None, security_code=None, market="TSE_PRIME",
            )

    def test_all_us_markets(self):
        for market in ("NYSE", "NASDAQ", "AMEX", "OTC"):
            result = CompanyService.build_company_id(
                ticker="TEST", security_code=None, market=market,
            )
            assert result == "US_TEST"

    def test_all_jp_markets(self):
        for market in ("TSE_PRIME", "TSE_STANDARD", "TSE_GROWTH", "TSE"):
            result = CompanyService.build_company_id(
                ticker=None, security_code="1234", market=market,
            )
            assert result == "JP_1234"


class TestResolveYfTicker:
    """Yahoo Finance ticker 解決"""

    def test_us_company(self):
        company = Company(
            id="US_AAPL", ticker="AAPL", name="Apple",
            market="NASDAQ", accounting_standard="US-GAAP",
        )
        assert CompanyService.resolve_yf_ticker(company) == "AAPL"

    def test_jp_company(self):
        company = Company(
            id="JP_7203", security_code="7203", name="Toyota",
            market="TSE_PRIME", accounting_standard="IFRS",
        )
        assert CompanyService.resolve_yf_ticker(company) == "7203.T"

    def test_jp_no_security_code(self):
        company = Company(
            id="JP_UNKNOWN", name="Unknown",
            market="TSE_PRIME", accounting_standard="IFRS",
        )
        assert CompanyService.resolve_yf_ticker(company) is None


class TestCompanyServiceAsync:
    """非同期サービスメソッド"""

    async def test_register_company_new(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)
        company = await svc.register_company({
            "ticker": "AAPL", "name": "Apple Inc.",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        assert company.id == "US_AAPL"
        assert company.ticker == "AAPL"

    async def test_register_company_update(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)
        await svc.register_company({
            "ticker": "AAPL", "name": "Apple Inc.",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        updated = await svc.register_company({
            "ticker": "AAPL", "name": "Apple Inc. (Updated)",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        assert updated.name == "Apple Inc. (Updated)"

    async def test_get_company(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)
        await svc.register_company({
            "ticker": "AAPL", "name": "Apple",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        result = await svc.get_company("US_AAPL")
        assert result is not None

    async def test_search_companies(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)
        await svc.register_company({
            "ticker": "AAPL", "name": "Apple Inc.",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        results = await svc.search_companies("Apple")
        assert len(results) == 1

    async def test_find_by_identifier(self, session):
        repo = CompanyRepository(session)
        svc = CompanyService(repo)
        await svc.register_company({
            "ticker": "AAPL", "name": "Apple",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        })
        result = await svc.find_by_identifier("AAPL")
        assert result is not None
        assert result.id == "US_AAPL"
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_company_service.py -v --no-header 2>&1 | head -20`
Expected: FAIL

- [ ] **Step 3: 実装を書く**

```python
# src/stock_analyze_system/services/company.py
"""企業サービス"""
from __future__ import annotations

import logging

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.company import CompanyRepository

logger = logging.getLogger(__name__)

_US_MARKETS = frozenset({"NYSE", "NASDAQ", "AMEX", "OTC"})
_JP_MARKETS = frozenset({"TSE_PRIME", "TSE_STANDARD", "TSE_GROWTH", "TSE"})


class CompanyService:
    """企業の登録・検索サービス"""

    def __init__(self, company_repo: CompanyRepository):
        self._repo = company_repo

    async def register_company(self, data: dict) -> Company:
        """企業を登録または更新"""
        company_id = self.build_company_id(
            ticker=data.get("ticker"),
            security_code=data.get("security_code"),
            market=data["market"],
        )
        filters = {"id": company_id}
        remainder = {
            "ticker": data.get("ticker"),
            "security_code": data.get("security_code"),
            "name": data["name"],
            "name_ja": data.get("name_ja"),
            "market": data["market"],
            "sector": data.get("sector"),
            "accounting_standard": data.get("accounting_standard", "US-GAAP"),
            "cik": data.get("cik"),
            "edinet_code": data.get("edinet_code"),
        }
        company = await self._repo.upsert(filters, remainder)
        logger.info("Registered/updated company %s (%s)", company_id, data["name"])
        return company

    async def get_company(self, company_id: str) -> Company | None:
        return await self._repo.get_by_id(company_id)

    async def search_companies(self, query: str, limit: int = 20) -> list[Company]:
        return await self._repo.search(query, limit=limit)

    async def find_by_identifier(self, query: str) -> Company | None:
        return await self._repo.find_by_identifier(query)

    @staticmethod
    def build_company_id(
        ticker: str | None, security_code: str | None, market: str,
    ) -> str:
        """市場と識別子から企業IDを生成。Bug #7 修正: 未知市場で ValueError。"""
        if market in _JP_MARKETS:
            if security_code is None:
                raise ValueError("security_code is required for JP markets")
            return f"JP_{security_code}"
        if market in _US_MARKETS:
            if ticker is None:
                raise ValueError("ticker is required for US markets")
            return f"US_{ticker}"
        raise ValueError(f"Unknown market: {market}")

    @staticmethod
    def is_us_market(company_id: str) -> bool:
        return company_id.startswith("US_")

    @staticmethod
    def resolve_yf_ticker(company: Company) -> str | None:
        """Yahoo Finance ticker を解決"""
        if company.id.startswith("US_"):
            return company.ticker
        return f"{company.security_code}.T" if company.security_code else None
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_company_service.py -v --no-header 2>&1 | tail -20`
Expected: ALL PASSED

- [ ] **Step 5: コミット**

```bash
cd <repo-root>
git add src/stock_analyze_system/services/company.py tests/unit/services/test_company_service.py
git commit -m "feat: add CompanyService with Bug #7 fix (market validation)"
```

---

### Task 5: FinancialService + ValuationService

**Files:**
- Create: `src/stock_analyze_system/services/financial.py`
- Create: `src/stock_analyze_system/services/valuation.py`
- Create: `tests/unit/services/test_financial_service.py`
- Create: `tests/unit/services/test_valuation_service.py`
- Existing: `src/stock_analyze_system/services/metrics.py` — Task 3 で作成
- Existing: `src/stock_analyze_system/repositories/financial.py` — Task 1 で作成
- Existing: `src/stock_analyze_system/repositories/valuation.py` — Task 1 で作成
- Reference: `<legacy-stock-analyzer-repo>/src/stock_analyzer/services/financial_service.py` — compute_metrics, compute_timeseries_metrics, build_chart_data
- Reference: `<legacy-stock-analyzer-repo>/src/stock_analyzer/services/valuation_service.py` — compute_per_range, compare_valuations, compute_group_deviation, build_chart_data

**Bug修正:**
- 新発見5: `compute_group_deviation()` は入力を変更せず新しいリストを返す
- 新発見6: YoY 四半期マッチング日数を名前付き定数に抽出（`_YOY_MIN_DAYS = 330`, `_YOY_MAX_DAYS = 400`）

- [ ] **Step 1: テストを書く**

```python
# tests/unit/services/test_financial_service.py
"""FinancialService のテスト"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.services.financial import FinancialService


def _make_fd(**kwargs):
    """FinancialData 風のモックオブジェクト"""
    fd = MagicMock()
    defaults = {
        "revenue": None, "operating_income": None, "net_income": None,
        "total_assets": None, "equity": None, "current_assets": None,
        "current_liabilities": None, "total_debt": None, "cash": None,
        "inventory": None, "cogs": None, "operating_cf": None,
        "capex": None, "fcf": None, "ebitda": None, "eps": None,
        "dps": None, "tax_expense": None, "income_before_tax": None,
        "shares_outstanding": None, "dividends_paid": None,
        "share_repurchases": None, "period_type": "annual",
        "fiscal_year_end": date(2024, 9, 28),
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(fd, k, v)
    return fd


class TestComputeMetrics:
    def test_basic_metrics(self):
        fd = _make_fd(
            revenue=100.0, operating_income=30.0, net_income=20.0,
            total_assets=500.0, equity=200.0,
        )
        svc = FinancialService(AsyncMock())
        result = svc.compute_metrics(fd)
        assert result["operating_margin"] == pytest.approx(0.3)
        assert result["net_margin"] == pytest.approx(0.2)
        assert result["roe"] == pytest.approx(0.1)

    def test_all_none_inputs(self):
        fd = _make_fd()
        svc = FinancialService(AsyncMock())
        result = svc.compute_metrics(fd)
        assert all(v is None for v in result.values())


class TestComputeTimeseriesMetrics:
    def test_annual_growth(self):
        """年次データの前年比成長率が計算されること"""
        fd_2024 = _make_fd(
            revenue=120.0, eps=6.0, fcf=30.0,
            fiscal_year_end=date(2024, 9, 28), period_type="annual",
        )
        fd_2023 = _make_fd(
            revenue=100.0, eps=5.0, fcf=25.0,
            fiscal_year_end=date(2023, 9, 28), period_type="annual",
        )
        svc = FinancialService(AsyncMock())
        results = svc.compute_timeseries_metrics([fd_2024, fd_2023])
        assert len(results) == 2
        assert results[0]["revenue_growth"] == pytest.approx(0.2)
        assert results[0]["eps_growth"] == pytest.approx(0.2)

    def test_quarterly_yoy(self):
        """四半期データの前年同期比が計算されること"""
        fd_q1_2024 = _make_fd(
            revenue=50.0, eps=2.5,
            fiscal_year_end=date(2024, 3, 31), period_type="quarterly",
        )
        fd_q1_2023 = _make_fd(
            revenue=40.0, eps=2.0,
            fiscal_year_end=date(2023, 3, 31), period_type="quarterly",
        )
        svc = FinancialService(AsyncMock())
        results = svc.compute_timeseries_metrics([fd_q1_2024, fd_q1_2023])
        assert results[0]["revenue_growth"] == pytest.approx(0.25)


class TestUpsertFinancialData:
    async def test_upsert_financial_data(self):
        """upsert_financial_data がリポジトリ経由で動作すること"""
        repo = AsyncMock()
        repo.upsert.return_value = MagicMock(id=1)
        svc = FinancialService(repo)
        result = await svc.upsert_financial_data("US_AAPL", {
            "accounting_standard": "US-GAAP", "currency": "USD",
            "period_type": "annual", "fiscal_year_end": date(2024, 9, 28),
            "revenue": 394e9,
        })
        repo.upsert.assert_called_once()


class TestBuildChartData:
    def test_chart_data_chronological(self):
        """チャートデータが時系列順（古い→新しい）で返ること"""
        svc = FinancialService(AsyncMock())
        ts_metrics = [
            {"fiscal_year_end": date(2024, 9, 28), "revenue": 394e9,
             "operating_income": 119e9, "net_income": 94e9,
             "eps": 6.13, "fcf": 111e9, "ebitda": 130e9,
             "roe": 0.47, "operating_margin": 0.30, "net_margin": 0.24,
             "revenue_growth": 0.05, "eps_growth": 0.1},
            {"fiscal_year_end": date(2023, 9, 28), "revenue": 383e9,
             "operating_income": 114e9, "net_income": 97e9,
             "eps": 5.57, "fcf": 99e9, "ebitda": 125e9,
             "roe": 0.45, "operating_margin": 0.29, "net_margin": 0.25,
             "revenue_growth": None, "eps_growth": None},
        ]
        chart = svc.build_chart_data(ts_metrics)
        assert chart["labels"] == ["2023-09-28", "2024-09-28"]
        assert chart["revenue"] == [383e9, 394e9]
        # PCT keys should be ×100
        assert chart["roe"][0] == pytest.approx(45.0)
```

```python
# tests/unit/services/test_valuation_service.py
"""ValuationService のテスト"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.services.valuation import ValuationService


def _make_valuation(**kwargs):
    v = MagicMock()
    defaults = {
        "company_id": "US_AAPL", "date": date(2024, 1, 1),
        "stock_price": 185.0, "market_cap": 3e12,
        "per": 28.5, "pbr": 45.0, "ev_ebitda": 22.0,
        "psr": 7.5, "fcf_yield": 0.035,
    }
    defaults.update(kwargs)
    for k, v_val in defaults.items():
        setattr(v, k, v_val)
    return v


class TestUpsertValuation:
    async def test_upsert_valuation(self):
        """upsert_valuation がリポジトリ経由で動作すること"""
        repo = AsyncMock()
        repo.upsert.return_value = MagicMock(id=1)
        svc = ValuationService(repo)
        result = await svc.upsert_valuation("US_AAPL", {
            "date": date(2024, 1, 1), "currency": "USD",
            "stock_price": 185.0, "per": 28.5,
        })
        repo.upsert.assert_called_once()


class TestCompareValuations:
    async def test_compare_valuations(self):
        """複数企業の最新バリュエーション比較"""
        repo = AsyncMock()
        repo.get_latest.side_effect = [
            _make_valuation(company_id="US_AAPL", per=28.0),
            _make_valuation(company_id="US_MSFT", per=35.0),
        ]
        svc = ValuationService(repo)
        results = await svc.compare_valuations(["US_AAPL", "US_MSFT"])
        assert len(results) == 2
        assert results[0]["company_id"] == "US_AAPL"
        assert results[0]["per"] == 28.0

    async def test_compare_valuations_missing(self):
        """バリュエーションが無い企業は None 値で返ること"""
        repo = AsyncMock()
        repo.get_latest.return_value = None
        svc = ValuationService(repo)
        results = await svc.compare_valuations(["US_NONEXIST"])
        assert len(results) == 1
        assert results[0]["per"] is None


class TestComputePerRange:
    def test_normal(self):
        valuations = [
            _make_valuation(per=20.0),
            _make_valuation(per=25.0),
            _make_valuation(per=30.0),
        ]
        svc = ValuationService(AsyncMock())
        result = svc.compute_per_range(valuations)
        assert result["high"] == 30.0
        assert result["low"] == 20.0
        assert result["median"] == 25.0

    def test_empty(self):
        svc = ValuationService(AsyncMock())
        result = svc.compute_per_range([])
        assert result == {"high": None, "median": None, "low": None}

    def test_none_per_excluded(self):
        valuations = [
            _make_valuation(per=None),
            _make_valuation(per=20.0),
        ]
        svc = ValuationService(AsyncMock())
        result = svc.compute_per_range(valuations)
        assert result["high"] == 20.0


class TestComputeGroupDeviation:
    def test_zscore_calculation(self):
        """z-score が正しく計算されること"""
        comparisons = [
            {"company_id": "A", "per": 20.0, "pbr": 2.0, "ev_ebitda": 10.0, "psr": 3.0},
            {"company_id": "B", "per": 30.0, "pbr": 4.0, "ev_ebitda": 15.0, "psr": 5.0},
            {"company_id": "C", "per": 25.0, "pbr": 3.0, "ev_ebitda": 12.5, "psr": 4.0},
        ]
        svc = ValuationService(AsyncMock())
        results = svc.compute_group_deviation(comparisons)
        # 新発見5修正: 元のリストが変更されていないこと（新しいリストが返される）
        assert results is not comparisons
        assert all("per_zscore" in r for r in results)

    def test_insufficient_data(self):
        """データが2件未満の場合 zscore は None"""
        comparisons = [
            {"company_id": "A", "per": 20.0, "pbr": 2.0, "ev_ebitda": 10.0, "psr": 3.0},
        ]
        svc = ValuationService(AsyncMock())
        results = svc.compute_group_deviation(comparisons)
        assert results[0]["per_zscore"] is None


class TestBuildChartData:
    def test_chronological_order(self):
        """チャートデータが時系列順で返ること"""
        valuations = [
            _make_valuation(date=date(2024, 3, 1), stock_price=210.0, per=32.0,
                            pbr=48.0, ev_ebitda=24.0, psr=8.0),
            _make_valuation(date=date(2024, 1, 1), stock_price=185.0, per=28.0,
                            pbr=45.0, ev_ebitda=22.0, psr=7.5),
        ]
        svc = ValuationService(AsyncMock())
        chart = svc.build_chart_data(valuations)
        assert chart["labels"] == ["2024-01-01", "2024-03-01"]
        assert chart["stock_price"] == [185.0, 210.0]
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_financial_service.py tests/unit/services/test_valuation_service.py -v --no-header 2>&1 | head -20`
Expected: FAIL

- [ ] **Step 3: 実装を書く**

```python
# src/stock_analyze_system/services/financial.py
"""財務データサービス"""
from __future__ import annotations

import logging
import statistics
from typing import Any

from stock_analyze_system.repositories.financial import FinancialRepository
from stock_analyze_system.services import metrics

logger = logging.getLogger(__name__)

_YOY_MIN_DAYS = 330
_YOY_MAX_DAYS = 400

_CHART_KEYS = (
    "revenue", "operating_income", "net_income", "eps", "fcf",
    "roe", "operating_margin", "net_margin",
    "revenue_growth", "eps_growth",
)
_PCT_KEYS = frozenset({
    "roe", "operating_margin", "net_margin",
    "revenue_growth", "eps_growth",
})


def _to_pct(v: float | None) -> float | None:
    return v * 100 if v is not None else None


class FinancialService:
    """財務データの取得・指標計算サービス"""

    def __init__(self, financial_repo: FinancialRepository):
        self._repo = financial_repo

    async def upsert_financial_data(
        self, company_id: str, data: dict[str, Any],
    ):
        """財務データを upsert"""
        filter_keys = ("period_type", "fiscal_year_end", "accounting_standard")
        filters = {"company_id": company_id, **{k: data[k] for k in filter_keys}}
        remainder = {k: v for k, v in data.items() if k not in filter_keys}
        return await self._repo.upsert(filters, remainder)

    async def get_timeseries(
        self, company_id: str, period_type: str = "annual", years: int = 10,
    ):
        return await self._repo.get_timeseries(company_id, period_type, years)

    async def get_latest(self, company_id: str, period_type: str = "annual"):
        return await self._repo.get_latest(company_id, period_type)

    def compute_metrics(self, fd: Any) -> dict[str, float | None]:
        """単一期間の全指標を計算"""
        return {
            "operating_margin": metrics.operating_margin(fd.operating_income, fd.revenue),
            "net_margin": metrics.net_margin(fd.net_income, fd.revenue),
            "roe": metrics.roe(fd.net_income, fd.equity),
            "roa": metrics.roa(fd.net_income, fd.total_assets),
            "roic": metrics.roic(
                fd.operating_income, fd.tax_expense, fd.income_before_tax,
                fd.total_debt, fd.equity, fd.cash,
            ),
            "asset_turnover": metrics.asset_turnover(fd.revenue, fd.total_assets),
            "inventory_turnover": metrics.inventory_turnover(fd.cogs, fd.inventory),
            "equity_ratio": metrics.equity_ratio(fd.equity, fd.total_assets),
            "current_ratio": metrics.current_ratio(fd.current_assets, fd.current_liabilities),
            "de_ratio": metrics.de_ratio(fd.total_debt, fd.equity),
            "dividend_payout_ratio": metrics.dividend_payout_ratio(
                fd.dividends_paid, fd.net_income, dps=fd.dps, eps=fd.eps,
            ),
            "total_payout_ratio": metrics.total_payout_ratio(
                fd.dividends_paid, fd.share_repurchases, fd.net_income,
            ),
        }

    def compute_timeseries_metrics(
        self, data_list: list,
    ) -> list[dict[str, Any]]:
        """時系列指標（YoY成長率含む）を計算。data_list は newest-first。"""
        is_quarterly = (
            len(data_list) > 0 and data_list[0].period_type == "quarterly"
        )

        yoy_map: dict[int, Any] = {}
        if is_quarterly:
            for idx, fd in enumerate(data_list):
                for j in range(idx + 1, len(data_list)):
                    delta = (fd.fiscal_year_end - data_list[j].fiscal_year_end).days
                    if _YOY_MIN_DAYS <= delta <= _YOY_MAX_DAYS:
                        yoy_map[idx] = data_list[j]
                        break

        results: list[dict[str, Any]] = []
        for i, fd in enumerate(data_list):
            entry: dict[str, Any] = {
                "fiscal_year_end": fd.fiscal_year_end,
                "period_type": fd.period_type,
                "revenue": fd.revenue,
                "operating_income": fd.operating_income,
                "net_income": fd.net_income,
                "total_assets": fd.total_assets,
                "equity": fd.equity,
                "eps": fd.eps,
                "fcf": fd.fcf,
                "ebitda": fd.ebitda,
            }
            entry.update(self.compute_metrics(fd))

            if is_quarterly:
                prev = yoy_map.get(i)
            elif i + 1 < len(data_list):
                prev = data_list[i + 1]
            else:
                prev = None

            if prev is not None:
                entry["revenue_growth"] = metrics.revenue_growth(fd.revenue, prev.revenue)
                entry["eps_growth"] = metrics.eps_growth(fd.eps, prev.eps)
                entry["fcf_growth"] = metrics.fcf_growth(fd.fcf, prev.fcf)
                entry["revenue_anomaly"] = metrics.is_anomaly(fd.revenue, prev.revenue)
            else:
                entry["revenue_growth"] = None
                entry["eps_growth"] = None
                entry["fcf_growth"] = None
                entry["revenue_anomaly"] = None

            results.append(entry)
        return results

    def build_chart_data(self, ts_metrics_list: list[dict[str, Any]]) -> dict[str, list]:
        """時系列指標を chart-ready dict（時系列順）に変換"""
        chrono = ts_metrics_list[::-1]
        result: dict[str, list] = {
            "labels": [str(r["fiscal_year_end"]) for r in chrono],
        }
        for key in _CHART_KEYS:
            if key in _PCT_KEYS:
                result[key] = [_to_pct(r.get(key)) for r in chrono]
            else:
                result[key] = [r.get(key) for r in chrono]
        return result
```

```python
# src/stock_analyze_system/services/valuation.py
"""バリュエーションサービス"""
from __future__ import annotations

import copy
import logging
import statistics
from typing import Any

from stock_analyze_system.repositories.valuation import ValuationRepository

logger = logging.getLogger(__name__)

_DEVIATION_METRICS = ("per", "pbr", "ev_ebitda", "psr")


class ValuationService:
    """バリュエーションの計算・比較サービス"""

    def __init__(self, valuation_repo: ValuationRepository):
        self._repo = valuation_repo

    async def upsert_valuation(
        self, company_id: str, data: dict[str, Any],
    ):
        """バリュエーションを upsert"""
        filters = {"company_id": company_id, "date": data["date"]}
        remainder = {k: v for k, v in data.items() if k != "date"}
        return await self._repo.upsert(filters, remainder)

    async def get_history(self, company_id: str, years: int = 10):
        return await self._repo.get_history(company_id, years)

    async def get_latest(self, company_id: str):
        return await self._repo.get_latest(company_id)

    async def compare_valuations(
        self, company_ids: list[str],
    ) -> list[dict[str, Any]]:
        """複数企業の最新バリュエーション比較"""
        _empty = {
            "date": None, "stock_price": None, "market_cap": None,
            "per": None, "pbr": None, "ev_ebitda": None,
            "psr": None, "fcf_yield": None,
        }
        results: list[dict[str, Any]] = []
        for company_id in company_ids:
            latest = await self._repo.get_latest(company_id)
            if latest is None:
                results.append({"company_id": company_id, **_empty})
            else:
                results.append({
                    "company_id": company_id,
                    "date": latest.date,
                    "stock_price": latest.stock_price,
                    "market_cap": latest.market_cap,
                    "per": latest.per,
                    "pbr": latest.pbr,
                    "ev_ebitda": latest.ev_ebitda,
                    "psr": latest.psr,
                    "fcf_yield": latest.fcf_yield,
                })
        return results

    def compute_per_range(self, valuations: list) -> dict[str, float | None]:
        """PER の高値・中央値・安値を計算"""
        per_values = [v.per for v in valuations if v.per is not None and v.per > 0]
        if not per_values:
            return {"high": None, "median": None, "low": None}
        return {
            "high": max(per_values),
            "median": statistics.median(per_values),
            "low": min(per_values),
        }

    def compute_group_deviation(
        self, comparisons: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """各企業の比較行に z-score 偏差を追加。新発見5修正: 新しいリストを返す。"""
        results = copy.deepcopy(comparisons)

        for metric in _DEVIATION_METRICS:
            values = [
                r[metric] for r in results
                if r.get(metric) is not None
            ]
            if len(values) < 2:
                for r in results:
                    r[f"{metric}_zscore"] = None
                continue

            mean = statistics.mean(values)
            stdev = statistics.stdev(values)

            for r in results:
                val = r.get(metric)
                if val is None or stdev == 0:
                    r[f"{metric}_zscore"] = None
                else:
                    r[f"{metric}_zscore"] = round((val - mean) / stdev, 2)

        return results

    def build_chart_data(self, valuations: list) -> dict[str, list]:
        """バリュエーション履歴を chart-ready dict（時系列順）に変換"""
        chrono = valuations[::-1]
        return {
            "labels": [str(v.date) for v in chrono],
            "stock_price": [v.stock_price for v in chrono],
            "per": [v.per for v in chrono],
            "pbr": [v.pbr for v in chrono],
            "ev_ebitda": [v.ev_ebitda for v in chrono],
            "psr": [v.psr for v in chrono],
        }
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_financial_service.py tests/unit/services/test_valuation_service.py -v --no-header 2>&1 | tail -20`
Expected: ALL PASSED

- [ ] **Step 5: コミット**

```bash
cd <repo-root>
git add src/stock_analyze_system/services/financial.py src/stock_analyze_system/services/valuation.py tests/unit/services/test_financial_service.py tests/unit/services/test_valuation_service.py
git commit -m "feat: add FinancialService and ValuationService with bug fixes"
```

---

### Task 6: FilingService + WatchlistService + AnalysisTargetService

**Files:**
- Create: `src/stock_analyze_system/services/filing.py`
- Create: `src/stock_analyze_system/services/watchlist.py`
- Create: `src/stock_analyze_system/services/analysis_target.py`
- Create: `tests/unit/services/test_filing_service.py`
- Create: `tests/unit/services/test_watchlist_service.py`
- Create: `tests/unit/services/test_analysis_target_service.py`
- Existing: `src/stock_analyze_system/repositories/filing.py`, `watchlist.py`, `target.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/services/test_filing_service.py
"""FilingService のテスト"""
import hashlib
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

from stock_analyze_system.services.filing import FilingService


class TestFilingService:
    async def test_upsert_filing(self):
        repo = AsyncMock()
        repo.upsert.return_value = AsyncMock(id=1)
        svc = FilingService(repo)
        result = await svc.upsert_filing("US_AAPL", {
            "source": "SEC", "filing_type": "10-K",
            "period_type": "annual", "fiscal_year": 2024,
            "accession_no": "0000320193-24-000123",
        })
        repo.upsert.assert_called_once()

    async def test_get_latest_filing(self):
        repo = AsyncMock()
        repo.get_latest_filing.return_value = AsyncMock(fiscal_year=2024)
        svc = FilingService(repo)
        result = await svc.get_latest_filing("US_AAPL", "10-K")
        repo.get_latest_filing.assert_called_once_with("US_AAPL", "10-K")

    async def test_list_filings(self):
        repo = AsyncMock()
        repo.list_filings.return_value = [AsyncMock(), AsyncMock()]
        svc = FilingService(repo)
        results = await svc.list_filings("US_AAPL")
        assert len(results) == 2

    def test_get_storage_path(self):
        path = FilingService.get_storage_path(
            "data/filings", "SEC", "US_AAPL", 2024, "annual", "10-K", "acc123",
        )
        assert path == Path("data/filings/SEC/US_AAPL/2024/annual/10-K/acc123")

    def test_compute_content_hash(self):
        content = b"test content"
        result = FilingService.compute_content_hash(content)
        assert result == hashlib.sha256(content).hexdigest()
```

```python
# tests/unit/services/test_watchlist_service.py
"""WatchlistService のテスト"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.services.watchlist import WatchlistService
from stock_analyze_system.exceptions import NotFoundError, DuplicateError


class TestWatchlistService:
    async def test_create_watchlist(self):
        repo = AsyncMock()
        repo.get_by_name.return_value = None
        repo.upsert.return_value = MagicMock(id=1, name="My List")
        svc = WatchlistService(repo)
        result = await svc.create_watchlist("My List")
        assert result.name == "My List"

    async def test_create_watchlist_duplicate(self):
        repo = AsyncMock()
        repo.get_by_name.return_value = MagicMock(name="My List")
        svc = WatchlistService(repo)
        with pytest.raises(DuplicateError):
            await svc.create_watchlist("My List")

    async def test_add_item(self):
        repo = AsyncMock()
        repo.get_by_id.return_value = MagicMock(id=1)
        repo.find_item.return_value = None
        svc = WatchlistService(repo)
        await svc.add_item(1, "US_AAPL")
        # find_item で重複チェック後、session.add が呼ばれること

    async def test_add_item_duplicate(self):
        repo = AsyncMock()
        repo.get_by_id.return_value = MagicMock(id=1)
        repo.find_item.return_value = MagicMock()
        svc = WatchlistService(repo)
        with pytest.raises(DuplicateError):
            await svc.add_item(1, "US_AAPL")

    async def test_remove_item(self):
        item = MagicMock(id=42)
        repo = AsyncMock()
        repo.find_item.return_value = item
        repo.delete.return_value = True
        svc = WatchlistService(repo)
        # WatchlistItem の id を使って delete
        await svc.remove_item(1, "US_AAPL")

    async def test_remove_item_not_found(self):
        repo = AsyncMock()
        repo.find_item.return_value = None
        svc = WatchlistService(repo)
        with pytest.raises(NotFoundError):
            await svc.remove_item(1, "US_AAPL")
```

```python
# tests/unit/services/test_analysis_target_service.py
"""AnalysisTargetService のテスト"""
from unittest.mock import AsyncMock, MagicMock

from stock_analyze_system.services.analysis_target import AnalysisTargetService


class TestAnalysisTargetService:
    async def test_add_target(self):
        repo = AsyncMock()
        repo.find_by_company.return_value = None
        svc = AnalysisTargetService(repo)
        await svc.add_target("US_AAPL", source="manual")

    async def test_remove_target(self):
        repo = AsyncMock()
        target = MagicMock(id=1)
        repo.find_by_company.return_value = target
        repo.delete.return_value = True
        svc = AnalysisTargetService(repo)
        await svc.remove_target("US_AAPL")
        repo.delete.assert_called_once_with(1)

    async def test_list_targets(self):
        repo = AsyncMock()
        repo.list_targets.return_value = [MagicMock(), MagicMock()]
        svc = AnalysisTargetService(repo)
        results = await svc.list_targets()
        assert len(results) == 2

    async def test_add_from_screening(self):
        repo = AsyncMock()
        repo.bulk_add.return_value = 3
        svc = AnalysisTargetService(repo)
        count = await svc.add_from_screening(["US_AAPL", "US_MSFT", "US_GOOG"])
        assert count == 3
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_filing_service.py tests/unit/services/test_watchlist_service.py tests/unit/services/test_analysis_target_service.py -v --no-header 2>&1 | head -20`
Expected: FAIL

- [ ] **Step 3: 実装を書く**

```python
# src/stock_analyze_system/services/filing.py
"""ファイリングサービス"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from stock_analyze_system.repositories.filing import FilingRepository

logger = logging.getLogger(__name__)


class FilingService:
    """ファイリングの登録・検索サービス"""

    def __init__(self, filing_repo: FilingRepository):
        self._repo = filing_repo

    async def upsert_filing(self, company_id: str, data: dict[str, Any]):
        """ファイリングを upsert。accession_no/doc_id で既存検索後、repo.upsert に委譲。"""
        accession_no = data.get("accession_no")
        doc_id = data.get("doc_id")

        # 既存レコードの重複キーを特定して upsert に渡す
        if accession_no:
            filters = {"accession_no": accession_no}
        elif doc_id:
            filters = {"doc_id": doc_id}
        else:
            filters = {
                "company_id": company_id,
                "fiscal_year": data["fiscal_year"],
                "filing_type": data["filing_type"],
                "period_type": data["period_type"],
            }
            data = {k: v for k, v in data.items()
                    if k not in ("fiscal_year", "filing_type", "period_type")}

        return await self._repo.upsert(
            {**filters, "company_id": company_id},
            {k: v for k, v in data.items() if k not in filters},
        )

    async def get_latest_filing(self, company_id: str, filing_type: str):
        return await self._repo.get_latest_filing(company_id, filing_type)

    async def list_filings(self, company_id: str):
        return await self._repo.list_filings(company_id)

    @staticmethod
    def get_storage_path(
        base_path: str, source: str, company_id: str,
        fiscal_year: int, period_type: str, filing_type: str, key: str,
    ) -> Path:
        """階層的ストレージパスを構築"""
        return (
            Path(base_path) / source / company_id
            / str(fiscal_year) / period_type / filing_type / key
        )

    @staticmethod
    def compute_content_hash(content: bytes) -> str:
        """SHA-256 ハッシュを計算"""
        return hashlib.sha256(content).hexdigest()
```

```python
# src/stock_analyze_system/services/watchlist.py
"""ウォッチリストサービス"""
from __future__ import annotations

import logging

from stock_analyze_system.exceptions import DuplicateError, NotFoundError
from stock_analyze_system.repositories.watchlist import WatchlistRepository

logger = logging.getLogger(__name__)


class WatchlistService:
    """ウォッチリストの CRUD サービス"""

    def __init__(self, watchlist_repo: WatchlistRepository):
        self._repo = watchlist_repo

    async def create_watchlist(self, name: str, description: str | None = None):
        """ウォッチリストを作成（名前重複で DuplicateError）"""
        existing = await self._repo.get_by_name(name)
        if existing is not None:
            raise DuplicateError(f"Watchlist '{name}' already exists")
        return await self._repo.upsert({"name": name}, {"description": description})

    async def list_watchlists(self):
        return await self._repo.list_all()

    async def get_watchlist(self, watchlist_id: int):
        return await self._repo.get_by_id(watchlist_id)

    async def add_item(
        self, watchlist_id: int, company_id: str,
        status: str = "monitoring", investment_thesis: str | None = None,
    ):
        """アイテムを追加（重複で DuplicateError）"""
        wl = await self._repo.get_by_id(watchlist_id)
        if wl is None:
            raise NotFoundError(f"Watchlist {watchlist_id} not found")
        existing = await self._repo.find_item(watchlist_id, company_id)
        if existing is not None:
            raise DuplicateError(
                f"Company {company_id} already in watchlist {watchlist_id}",
            )
        return await self._repo.add_item(
            watchlist_id, company_id,
            status=status, investment_thesis=investment_thesis,
        )

    async def remove_item(self, watchlist_id: int, company_id: str):
        """アイテムを削除（未検出で NotFoundError）"""
        item = await self._repo.find_item(watchlist_id, company_id)
        if item is None:
            raise NotFoundError(
                f"Company {company_id} not in watchlist {watchlist_id}",
            )
        await self._repo.delete_item(item)
```

```python
# src/stock_analyze_system/services/analysis_target.py
"""分析対象サービス"""
from __future__ import annotations

import logging

from stock_analyze_system.exceptions import NotFoundError
from stock_analyze_system.repositories.target import TargetRepository

logger = logging.getLogger(__name__)


class AnalysisTargetService:
    """分析対象銘柄の管理サービス"""

    def __init__(self, target_repo: TargetRepository):
        self._repo = target_repo

    async def add_target(
        self, company_id: str, source: str = "manual", criteria: str | None = None,
    ):
        """ターゲットを追加（既存はスキップ）"""
        existing = await self._repo.find_by_company(company_id)
        if existing is not None:
            return existing
        return await self._repo.upsert(
            {"company_id": company_id},
            {"source": source, "criteria": criteria},
        )

    async def remove_target(self, company_id: str) -> None:
        """ターゲットを削除"""
        target = await self._repo.find_by_company(company_id)
        if target is None:
            raise NotFoundError(f"Target for {company_id} not found")
        await self._repo.delete(target.id)

    async def list_targets(self) -> list[AnalysisTarget]:
        return await self._repo.list_targets()

    async def add_from_screening(self, company_ids: list[str]) -> int:
        """スクリーニング結果からターゲットを一括追加"""
        records = [
            {"company_id": cid, "source": "screening"}
            for cid in company_ids
        ]
        return await self._repo.bulk_add(records)
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_filing_service.py tests/unit/services/test_watchlist_service.py tests/unit/services/test_analysis_target_service.py -v --no-header 2>&1 | tail -20`
Expected: ALL PASSED

- [ ] **Step 5: コミット**

```bash
cd <repo-root>
git add src/stock_analyze_system/services/filing.py src/stock_analyze_system/services/watchlist.py src/stock_analyze_system/services/analysis_target.py tests/unit/services/test_filing_service.py tests/unit/services/test_watchlist_service.py tests/unit/services/test_analysis_target_service.py
git commit -m "feat: add FilingService, WatchlistService, AnalysisTargetService"
```

---

### Task 7: FinancialSyncService（Bug #4 修正含む）

**Files:**
- Create: `src/stock_analyze_system/services/financial_sync.py`
- Create: `tests/unit/services/test_financial_sync.py`
- Existing: `src/stock_analyze_system/ingestion/sec_edgar.py` — SecEdgarClient
- Existing: `src/stock_analyze_system/ingestion/sec_xbrl_parser.py` — SecXbrlParser
- Existing: `src/stock_analyze_system/ingestion/edinet.py` — EdinetClient
- Existing: `src/stock_analyze_system/ingestion/edinet_xbrl_parser.py` — EdinetXbrlParser
- Existing: `src/stock_analyze_system/ingestion/yahoo_finance.py` — YahooFinanceClient
- Existing: `src/stock_analyze_system/ingestion/fmp.py` — FmpClient
- Existing: `src/stock_analyze_system/repositories/financial.py`
- Existing: `src/stock_analyze_system/services/company.py`
- Reference: `<legacy-stock-analyzer-repo>/src/stock_analyzer/services/financial_sync.py` — 同期版の _update_from_sec, _update_from_edinet, _fill_q4_from_yahoo_and_subtract

**Bug修正:**
- 既知#4: sync 関数が `int`（upsert レコード数）を返す。SyncResult.financials_count に正しく反映
- 新発見1: `stock_price is None` 時の早期 return（→ Task 8 の JobService で対処）
- 新発見4: Q4 減算結果をログ出力（WARNING レベル）

**注意:** このサービスは非同期。参考プロジェクトの同期版を async/await に変換する。Ingestion クライアントは既に非同期。

- [ ] **Step 1: テストを書く**

```python
# tests/unit/services/test_financial_sync.py
"""FinancialSyncService のテスト"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stock_analyze_system.services.financial_sync import FinancialSyncService


def _make_parser_records(count: int = 2) -> list[dict]:
    """SecXbrlParser.parse_company_facts の戻り値を模擬"""
    records = []
    for i in range(count):
        records.append({
            "fiscal_year_end": f"{2024 - i}-09-28",
            "currency": "USD",
            "revenue": float((400 - i * 10) * 1e9),
            "net_income": float((95 - i * 5) * 1e9),
        })
    return records


class TestUpdateFromSec:
    async def test_returns_record_count(self):
        """Bug #4: SEC 更新がレコード数を返すこと"""
        repo = AsyncMock()
        repo.upsert.return_value = MagicMock()
        sec_client = AsyncMock()
        sec_client.get_company_facts.return_value = {"facts": {"us-gaap": {}}}

        svc = FinancialSyncService(
            financial_repo=repo, sec_client=sec_client,
            edinet_client=AsyncMock(), yahoo_client=AsyncMock(),
            fmp_client=AsyncMock(),
        )

        with patch.object(svc, "_parse_and_upsert_sec", return_value=3):
            count = await svc.update_from_sec(
                "US_AAPL", "0000320193", "US-GAAP",
                period_types=("annual",),
            )
        assert count == 3

    async def test_returns_zero_on_failure(self):
        """SEC API 失敗時に 0 を返すこと"""
        sec_client = AsyncMock()
        sec_client.get_company_facts.side_effect = Exception("API error")

        svc = FinancialSyncService(
            financial_repo=AsyncMock(), sec_client=sec_client,
            edinet_client=AsyncMock(), yahoo_client=AsyncMock(),
            fmp_client=AsyncMock(),
        )
        count = await svc.update_from_sec(
            "US_AAPL", "0000320193", "US-GAAP",
        )
        assert count == 0


class TestUpdateFromEdinet:
    async def test_returns_record_count(self):
        """Bug #4: EDINET 更新がレコード数を返すこと"""
        repo = AsyncMock()
        edinet_client = AsyncMock()
        edinet_client.search_filings.return_value = [
            {"docID": "S100001", "docTypeCode": "120", "periodEnd": "2024-03-31"},
        ]
        edinet_client.download_xbrl.return_value = "/tmp/xbrl"

        svc = FinancialSyncService(
            financial_repo=repo, sec_client=AsyncMock(),
            edinet_client=edinet_client, yahoo_client=AsyncMock(),
            fmp_client=AsyncMock(),
        )

        with patch.object(svc, "_parse_and_upsert_edinet", return_value=1):
            count = await svc.update_from_edinet("JP_7203", "E02144")
        assert count == 1


class TestFcfDerivation:
    def test_fcf_from_operating_cf_and_capex(self):
        """FCF = operating_cf - abs(capex) で安全に導出されること"""
        svc = FinancialSyncService(
            financial_repo=AsyncMock(), sec_client=AsyncMock(),
            edinet_client=AsyncMock(), yahoo_client=AsyncMock(),
            fmp_client=AsyncMock(),
        )
        record = {"operating_cf": 100.0, "capex": -30.0, "fcf": None}
        svc._derive_fcf(record)
        assert record["fcf"] == 70.0

    def test_fcf_not_overwritten(self):
        """既存 FCF は上書きしない"""
        svc = FinancialSyncService(
            financial_repo=AsyncMock(), sec_client=AsyncMock(),
            edinet_client=AsyncMock(), yahoo_client=AsyncMock(),
            fmp_client=AsyncMock(),
        )
        record = {"operating_cf": 100.0, "capex": -30.0, "fcf": 80.0}
        svc._derive_fcf(record)
        assert record["fcf"] == 80.0
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_financial_sync.py -v --no-header 2>&1 | head -20`
Expected: FAIL

- [ ] **Step 3: 実装を書く**

```python
# src/stock_analyze_system/services/financial_sync.py
"""財務データ同期サービス（SEC/EDINET → DB）"""
from __future__ import annotations

import logging
from datetime import date as date_type
from datetime import timedelta
from typing import Any

from stock_analyze_system.repositories.financial import FinancialRepository

logger = logging.getLogger(__name__)

# Q4 減算対象フィールド（フロー項目のみ。per-share は除外）
# Q4 fill (Yahoo Finance 8-K + Annual-Q3 subtraction) は sync_company 内で
# 将来的に実装予定。新発見4: 減算結果が負の場合は WARNING ログを出力する。
_Q4_SUBTRACTION_FIELDS = (
    "revenue", "operating_income", "net_income", "ebitda",
    "cogs", "tax_expense", "income_before_tax",
    "operating_cf", "capex", "fcf",
    "dividends_paid", "share_repurchases",
)
_DATE_MATCH_TOLERANCE = 15


class FinancialSyncService:
    """SEC/EDINET からの財務データ取得・永続化オーケストレーション"""

    def __init__(
        self,
        financial_repo: FinancialRepository,
        sec_client: Any,
        edinet_client: Any,
        yahoo_client: Any,
        fmp_client: Any,
    ):
        self._repo = financial_repo
        self._sec = sec_client
        self._edinet = edinet_client
        self._yahoo = yahoo_client
        self._fmp = fmp_client

    async def update_from_sec(
        self,
        company_id: str,
        cik: str,
        acct_std: str,
        period_types: tuple[str, ...] = ("annual",),
    ) -> int:
        """SEC EDGAR から財務データを取得・upsert。戻り値はレコード数。"""
        try:
            facts = await self._sec.get_company_facts(cik)
        except (ValueError, OSError, KeyError) as exc:
            logger.exception("SEC EDGAR fetch failed for %s", company_id)
            return 0

        total_count = 0
        for period_type in period_types:
            count = await self._parse_and_upsert_sec(
                company_id, facts, acct_std, period_type,
            )
            total_count += count

        logger.info(
            "Financial update for %s: %d records from SEC EDGAR",
            company_id, total_count,
        )
        return total_count

    async def _parse_and_upsert_sec(
        self, company_id: str, facts: dict,
        acct_std: str, period_type: str,
    ) -> int:
        """SEC facts を parse して DB に upsert。戻り値は upsert レコード数。"""
        from stock_analyze_system.ingestion.sec_xbrl_parser import SecXbrlParser

        parser = SecXbrlParser()
        try:
            records = parser.parse_company_facts(facts, period_type=period_type)
        except (ValueError, KeyError):
            logger.warning(
                "SEC EDGAR parse failed for %s period_type=%s",
                company_id, period_type,
            )
            return 0

        count = 0
        for record in records:
            currency = record.pop("currency", "USD")
            self._derive_fcf(record)
            data = {
                "accounting_standard": acct_std,
                "currency": currency,
                "period_type": period_type,
                "fiscal_year_end": date_type.fromisoformat(record["fiscal_year_end"]),
                **{k: v for k, v in record.items() if k != "fiscal_year_end"},
            }
            await self._repo.upsert(
                {
                    "company_id": company_id,
                    "period_type": data["period_type"],
                    "fiscal_year_end": data["fiscal_year_end"],
                    "accounting_standard": data["accounting_standard"],
                },
                {k: v for k, v in data.items()
                 if k not in ("period_type", "fiscal_year_end", "accounting_standard")},
            )
            count += 1
        return count

    async def update_from_edinet(
        self, company_id: str, edinet_code: str,
    ) -> int:
        """EDINET から財務データを取得・upsert。戻り値はレコード数。"""
        try:
            today = date_type.today()
            docs = await self._edinet.search_filings(
                edinet_code,
                (today - timedelta(days=365 * 2)).isoformat(),
                today.isoformat(),
            )
        except (ValueError, OSError, KeyError) as exc:
            logger.exception("EDINET search failed for %s", company_id)
            return 0

        if not docs:
            return 0

        total = 0
        for doc in docs:
            count = await self._parse_and_upsert_edinet(company_id, doc)
            total += count

        logger.info(
            "Financial update for %s: %d records from EDINET",
            company_id, total,
        )
        return total

    async def _parse_and_upsert_edinet(
        self, company_id: str, doc: dict,
    ) -> int:
        """EDINET ドキュメントを parse して upsert。戻り値はレコード数。"""
        doc_id = doc.get("docID")
        if not doc_id:
            return 0
        try:
            from stock_analyze_system.ingestion.edinet_xbrl_parser import EdinetXbrlParser

            xbrl_dir = await self._edinet.download_xbrl(doc_id)
            parser = EdinetXbrlParser()
            std = parser.detect_accounting_standard(xbrl_dir)
            result = parser.parse_xbrl_directory(xbrl_dir, std)
            if not result:
                return 0

            data = {
                "accounting_standard": std.upper().replace("_", "-"),
                "currency": "JPY",
                "period_type": "annual",
                **result,
            }
            await self._repo.upsert(
                {
                    "company_id": company_id,
                    "period_type": data["period_type"],
                    "fiscal_year_end": data["fiscal_year_end"],
                    "accounting_standard": data["accounting_standard"],
                },
                {k: v for k, v in data.items()
                 if k not in ("period_type", "fiscal_year_end", "accounting_standard")},
            )
            return 1
        except (ValueError, OSError, KeyError) as exc:
            logger.exception("EDINET parse failed for doc %s", doc_id)
            return 0

    @staticmethod
    def _derive_fcf(record: dict) -> None:
        """FCF を operating_cf - abs(capex) で安全に導出"""
        if record.get("fcf") is not None:
            return
        op_cf = record.get("operating_cf")
        capex = record.get("capex")
        if op_cf is not None and capex is not None:
            record["fcf"] = op_cf - abs(capex)
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_financial_sync.py -v --no-header 2>&1 | tail -20`
Expected: ALL PASSED

- [ ] **Step 5: コミット**

```bash
cd <repo-root>
git add src/stock_analyze_system/services/financial_sync.py tests/unit/services/test_financial_sync.py
git commit -m "feat: add FinancialSyncService with Bug #4 fix (financials_count)"
```

---

### Task 8: FilingSyncService + JobService（SyncResult/DailyUpdateResult）

**Files:**
- Create: `src/stock_analyze_system/services/filing_sync.py`
- Create: `src/stock_analyze_system/services/job.py`
- Create: `tests/unit/services/test_filing_sync.py`
- Create: `tests/unit/services/test_job_service.py`
- Existing: `src/stock_analyze_system/services/financial_sync.py` — Task 7
- Existing: `src/stock_analyze_system/services/company.py` — Task 4
- Existing: `src/stock_analyze_system/services/valuation.py` — Task 5
- Reference: `<legacy-stock-analyzer-repo>/src/stock_analyzer/services/filing_sync.py`
- Reference: `<legacy-stock-analyzer-repo>/src/stock_analyzer/services/job_service.py`

**Bug修正:**
- 既知#4: SyncResult を dataclass 化。financials_count, filings_count, valuations_count を正しくカウント
- 新発見1: `_compute_valuation_from_financials` で `stock_price is None` 早期 return
- 新発見2: `shares is not None and shares > 0` の明示的チェック
- 新発見3: `except Exception` → 具体的な例外クラス

- [ ] **Step 1: テストを書く**

```python
# tests/unit/services/test_filing_sync.py
"""FilingSyncService のテスト"""
from unittest.mock import AsyncMock, MagicMock

from stock_analyze_system.services.filing_sync import FilingSyncService


class TestFilingSyncService:
    async def test_update_from_sec_returns_count(self):
        """SEC ファイリング更新がカウントを返すこと"""
        filing_repo = AsyncMock()
        sec_client = AsyncMock()
        sec_client.list_filings.return_value = [
            {
                "form": "10-K", "accessionNumber": "acc-001",
                "reportDate": "2024-09-28", "filingDate": "2024-11-01",
                "documentUrl": "https://example.com/doc",
            },
        ]
        filing_repo.find_by_accession.return_value = None
        filing_repo.upsert.return_value = MagicMock(id=1)

        svc = FilingSyncService(
            filing_repo=filing_repo, sec_client=sec_client,
            edinet_client=AsyncMock(),
        )
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 1

    async def test_update_from_sec_skip_existing(self):
        """既存ファイリングはスキップされること"""
        filing_repo = AsyncMock()
        sec_client = AsyncMock()
        sec_client.list_filings.return_value = [
            {
                "form": "10-K", "accessionNumber": "acc-001",
                "reportDate": "2024-09-28", "filingDate": "2024-11-01",
                "documentUrl": "https://example.com/doc",
            },
        ]
        filing_repo.find_by_accession.return_value = MagicMock(id=1)

        svc = FilingSyncService(
            filing_repo=filing_repo, sec_client=sec_client,
            edinet_client=AsyncMock(),
        )
        count = await svc.update_from_sec("US_AAPL", "0000320193")
        assert count == 0
```

```python
# tests/unit/services/test_job_service.py
"""JobService のテスト"""
from dataclasses import asdict
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.services.job import (
    DailyUpdateResult, JobService, SyncResult,
    compute_valuation_from_financials,
)


class TestSyncResult:
    def test_dataclass_defaults(self):
        result = SyncResult(company_id="US_AAPL")
        assert result.financials_count == 0
        assert result.filings_count == 0
        assert result.valuations_count == 0
        assert result.errors == []

    def test_serializable(self):
        result = SyncResult(company_id="US_AAPL", financials_count=5)
        d = asdict(result)
        assert d["financials_count"] == 5


class TestComputeValuationFromFinancials:
    def test_normal(self):
        fd = MagicMock(
            eps=6.0, equity=100e9, shares_outstanding=15e9,
            total_debt=100e9, cash=50e9, ebitda=130e9,
            revenue=394e9, fcf=111e9, net_income=94e9,
        )
        result = compute_valuation_from_financials(
            stock_price=185.0, fd=fd, currency="USD",
            val_date=date(2024, 1, 1), market_cap=3e12,
        )
        assert result["stock_price"] == 185.0
        assert result["per"] is not None

    def test_stock_price_none_returns_minimal(self):
        """新発見1: stock_price が None の場合、安全に処理されること"""
        fd = MagicMock(eps=6.0, equity=100e9)
        result = compute_valuation_from_financials(
            stock_price=None, fd=fd, currency="USD",
            val_date=date(2024, 1, 1),
        )
        assert result["stock_price"] is None
        assert result["per"] is None

    def test_shares_none_explicit_check(self):
        """新発見2: shares_outstanding が None でも TypeError にならないこと"""
        fd = MagicMock(
            eps=6.0, equity=100e9, shares_outstanding=None,
            total_debt=100e9, cash=50e9, ebitda=130e9,
            revenue=394e9, fcf=111e9, net_income=94e9,
        )
        result = compute_valuation_from_financials(
            stock_price=185.0, fd=fd, currency="USD",
            val_date=date(2024, 1, 1),
        )
        # market_cap is None → effective_mcap is None
        assert result["ev_ebitda"] is None


class TestJobService:
    async def test_sync_company_counts(self):
        """Bug #4: sync_company が正しいカウントを返すこと"""
        company = MagicMock(
            id="US_AAPL", cik="0000320193", edinet_code=None,
            accounting_standard="US-GAAP",
        )
        company_svc = AsyncMock()
        company_svc.get_company.return_value = company
        company_svc.resolve_yf_ticker = MagicMock(return_value="AAPL")

        financial_sync = AsyncMock()
        financial_sync.update_from_sec.return_value = 5

        filing_sync = AsyncMock()
        filing_sync.update_from_sec.return_value = 2

        valuation_svc = AsyncMock()
        yahoo_client = AsyncMock()
        yahoo_client.get_stock_price.return_value = {
            "price": 185.0, "market_cap": 3e12, "currency": "USD",
        }

        financial_svc = AsyncMock()
        fd_mock = MagicMock(
            eps=6.0, equity=100e9, shares_outstanding=15e9,
            total_debt=100e9, cash=50e9, ebitda=130e9,
            revenue=394e9, fcf=111e9, net_income=94e9,
        )
        financial_svc.get_latest.return_value = fd_mock

        svc = JobService(
            company_svc=company_svc,
            financial_sync=financial_sync,
            filing_sync=filing_sync,
            valuation_svc=valuation_svc,
            financial_svc=financial_svc,
            yahoo_client=yahoo_client,
            fmp_client=AsyncMock(),
        )
        result = await svc.sync_company("US_AAPL")
        assert result.financials_count == 5
        assert result.filings_count == 2
        assert result.valuations_count >= 1

    async def test_sync_company_not_found(self):
        """存在しない企業で ValueError"""
        company_svc = AsyncMock()
        company_svc.get_company.return_value = None

        svc = JobService(
            company_svc=company_svc,
            financial_sync=AsyncMock(),
            filing_sync=AsyncMock(),
            valuation_svc=AsyncMock(),
            financial_svc=AsyncMock(),
            yahoo_client=AsyncMock(),
            fmp_client=AsyncMock(),
        )
        with pytest.raises(ValueError, match="not found"):
            await svc.sync_company("US_NONEXIST")
```

- [ ] **Step 2: テスト失敗を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_filing_sync.py tests/unit/services/test_job_service.py -v --no-header 2>&1 | head -20`
Expected: FAIL

- [ ] **Step 3: 実装を書く**

```python
# src/stock_analyze_system/services/filing_sync.py
"""ファイリング同期サービス（SEC/EDINET → DB）"""
from __future__ import annotations

import logging
from datetime import date as date_type
from datetime import timedelta
from typing import Any

from stock_analyze_system.repositories.filing import FilingRepository

logger = logging.getLogger(__name__)


class FilingSyncService:
    """SEC/EDINET からのファイリング取得・登録オーケストレーション"""

    def __init__(
        self,
        filing_repo: FilingRepository,
        sec_client: Any,
        edinet_client: Any,
    ):
        self._repo = filing_repo
        self._sec = sec_client
        self._edinet = edinet_client

    async def update_from_sec(
        self, company_id: str, cik: str,
    ) -> int:
        """SEC EDGAR からファイリングを取得・登録。戻り値は新規登録数。"""
        try:
            filing_list = await self._sec.list_filings(cik, max_years=2)
        except (ValueError, OSError, KeyError) as exc:
            logger.exception("SEC EDGAR filing list failed for %s", company_id)
            return 0

        if not filing_list:
            return 0

        count = 0
        for entry in filing_list:
            accession = entry.get("accessionNumber")
            if not accession:
                continue

            existing = await self._repo.find_by_accession(accession)
            if existing is not None:
                continue

            form = entry["form"]
            report_date = entry.get("reportDate", "")
            filed_date = entry.get("filingDate", "")
            period_type = "annual" if form in ("10-K", "20-F") else "quarterly"
            fiscal_year = int(report_date[:4]) if report_date else int(filed_date[:4])

            data = {
                "source": "SEC",
                "filing_type": form,
                "period_type": period_type,
                "fiscal_year": fiscal_year,
                "accession_no": accession,
            }
            if report_date:
                data["period_end"] = date_type.fromisoformat(report_date)
            if filed_date:
                data["filed_at"] = date_type.fromisoformat(filed_date)

            await self._repo.upsert({"company_id": company_id}, data)
            count += 1

        logger.info("Filing update for %s: %d new filings", company_id, count)
        return count

    async def update_from_edinet(
        self, company_id: str, edinet_code: str,
    ) -> int:
        """EDINET からファイリングを取得・登録。戻り値は登録数。"""
        today = date_type.today()
        try:
            docs = await self._edinet.search_filings(
                edinet_code,
                (today - timedelta(days=365 * 2)).isoformat(),
                today.isoformat(),
            )
        except (ValueError, OSError, KeyError) as exc:
            logger.exception("EDINET filing search failed for %s", company_id)
            return 0

        if not docs:
            return 0

        count = 0
        for doc in docs:
            doc_id = doc.get("docID")
            if not doc_id:
                continue

            existing = await self._repo.find_by_doc_id(doc_id)
            if existing is not None:
                continue

            fiscal_year_str = doc.get("periodEnd", "")[:4]
            fiscal_year = int(fiscal_year_str) if fiscal_year_str.isdigit() else today.year
            doc_type = doc.get("docTypeCode", "")
            period_type = "annual" if doc_type in ("120", "130") else "quarterly"
            filing_type = "annual_report" if period_type == "annual" else "quarterly_report"

            data = {
                "source": "EDINET",
                "filing_type": filing_type,
                "period_type": period_type,
                "fiscal_year": fiscal_year,
                "doc_id": doc_id,
            }
            await self._repo.upsert({"company_id": company_id}, data)
            count += 1

        logger.info("Filing update for %s: %d filings from EDINET", company_id, count)
        return count
```

```python
# src/stock_analyze_system/services/job.py
"""バッチオーケストレーションサービス"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime, timezone
from typing import Any

from stock_analyze_system.services import metrics

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """単一企業の同期結果"""
    company_id: str
    financials_count: int = 0
    filings_count: int = 0
    valuations_count: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_reasons: list[str] = field(default_factory=list)


@dataclass
class DailyUpdateResult:
    """日次更新サイクルの結果"""
    market: str
    total_companies: int = 0
    results: list[SyncResult] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


def compute_valuation_from_financials(
    stock_price: float | None,
    fd: Any,
    currency: str,
    val_date: date_type,
    market_cap: float | None = None,
) -> dict[str, Any]:
    """株価と財務データからバリュエーション dict を計算。

    新発見1修正: stock_price が None の場合は安全に処理。
    新発見2修正: shares_outstanding の明示的 None チェック。
    """
    if stock_price is None:
        return {
            "currency": currency,
            "date": val_date,
            "stock_price": None,
            "market_cap": market_cap,
            "per": None,
            "pbr": None,
            "ev_ebitda": None,
            "psr": None,
            "fcf_yield": None,
        }

    per_val = metrics.per(
        stock_price, fd.eps,
        market_cap=market_cap, net_income=fd.net_income,
    )

    if market_cap is not None:
        pbr_val = metrics.pbr(market_cap, fd.equity)
    else:
        shares = fd.shares_outstanding
        bvps = None
        if fd.equity is not None and shares is not None and shares > 0:
            bvps = fd.equity / shares
        pbr_val = stock_price / bvps if bvps is not None and bvps > 0 else None

    effective_mcap = market_cap
    if effective_mcap is None:
        shares = fd.shares_outstanding
        effective_mcap = stock_price * shares if shares is not None else None

    ev_ebitda_val = (
        metrics.ev_ebitda(effective_mcap, fd.total_debt, fd.cash, fd.ebitda)
        if effective_mcap is not None else None
    )
    psr_val = (
        metrics.psr(effective_mcap, fd.revenue)
        if effective_mcap is not None else None
    )
    fcf_yield_val = None
    if fd.fcf is not None and effective_mcap is not None and effective_mcap > 0:
        fcf_yield_val = fd.fcf / effective_mcap

    return {
        "currency": currency,
        "date": val_date,
        "stock_price": stock_price,
        "market_cap": effective_mcap,
        "per": per_val,
        "pbr": pbr_val,
        "ev_ebitda": ev_ebitda_val,
        "psr": psr_val,
        "fcf_yield": fcf_yield_val,
    }


class JobService:
    """バッチ同期オーケストレーション"""

    def __init__(
        self,
        company_svc: Any,
        financial_sync: Any,
        filing_sync: Any,
        valuation_svc: Any,
        financial_svc: Any,
        yahoo_client: Any,
        fmp_client: Any,
    ):
        self._company_svc = company_svc
        self._financial_sync = financial_sync
        self._filing_sync = filing_sync
        self._valuation_svc = valuation_svc
        self._financial_svc = financial_svc
        self._yahoo = yahoo_client
        self._fmp = fmp_client

    async def sync_company(self, company_id: str) -> SyncResult:
        """単一企業の全データ同期。Bug #4 修正: カウントを正しく追跡。"""
        company = await self._company_svc.get_company(company_id)
        if company is None:
            raise ValueError(f"Company '{company_id}' not found")

        result = SyncResult(company_id=company_id)

        # 1. Financial data
        cik = company.cik
        edinet_code = company.edinet_code
        acct_std = company.accounting_standard

        if cik:
            count = await self._financial_sync.update_from_sec(
                company_id, cik, acct_std,
                period_types=("annual", "quarterly"),
            )
            result.financials_count = count
        elif (not self._company_svc.is_us_market(company_id)
              and edinet_code):
            count = await self._financial_sync.update_from_edinet(
                company_id, edinet_code,
            )
            result.financials_count = count

        # 2. Filing data
        if cik:
            result.filings_count = await self._filing_sync.update_from_sec(
                company_id, cik,
            )
        elif (not self._company_svc.is_us_market(company_id)
              and edinet_code):
            result.filings_count = await self._filing_sync.update_from_edinet(
                company_id, edinet_code,
            )

        # 3. Valuation from Yahoo Finance
        yf_ticker = self._company_svc.resolve_yf_ticker(company)
        if yf_ticker:
            try:
                price_data = await self._yahoo.get_stock_price(yf_ticker)
                if price_data:
                    currency = price_data.get("currency", "USD")
                    stock_price = price_data.get("price")
                    market_cap_val = price_data.get("market_cap")

                    latest_fd = await self._financial_svc.get_latest(
                        company_id, "annual",
                    )
                    if latest_fd:
                        val_data = compute_valuation_from_financials(
                            stock_price, latest_fd, currency,
                            date_type.today(), market_cap=market_cap_val,
                        )
                    else:
                        val_data = {
                            "currency": currency,
                            "date": date_type.today(),
                            "stock_price": stock_price,
                            "market_cap": market_cap_val,
                        }

                    await self._valuation_svc.upsert_valuation(
                        company_id, val_data,
                    )
                    result.valuations_count += 1
            except (ValueError, TypeError, AttributeError) as exc:
                result.errors.append(f"Valuation error: {exc}")
                logger.warning("Valuation failed for %s: %s", company_id, exc)

        return result

    async def run_daily_update(self, market: str = "us") -> DailyUpdateResult:
        """日次更新サイクル。新発見3修正: 具体的な例外のみ捕捉。"""
        result = DailyUpdateResult(market=market)

        # 企業一覧は company_repo.list_by_market 経由で取得
        # market → prefix: "us" → list companies whose ID starts with "US_"
        market_prefix = market.upper()
        companies = await self._company_svc._repo.list_all()
        companies = [c for c in companies if c.id.startswith(f"{market_prefix}_")]
        result.total_companies = len(companies)

        for company in companies:
            try:
                sync_result = await self.sync_company(company.id)
                result.results.append(sync_result)
            except (ValueError, TypeError, AttributeError, OSError) as exc:
                logger.exception("Sync failed for %s", company.id)
                sr = SyncResult(company_id=company.id)
                sr.errors.append(str(exc))
                result.results.append(sr)

        result.finished_at = datetime.now(timezone.utc)
        logger.info(
            "Daily update complete for market=%s: %d companies",
            market, result.total_companies,
        )
        return result
```

- [ ] **Step 4: テスト成功を確認**

Run: `cd <repo-root> && python -m pytest tests/unit/services/test_filing_sync.py tests/unit/services/test_job_service.py -v --no-header 2>&1 | tail -20`
Expected: ALL PASSED

- [ ] **Step 5: 全テスト実行**

Run: `cd <repo-root> && python -m pytest tests/ -v --no-header 2>&1 | tail -30`
Expected: ALL PASSED（Phase 1 + Phase 2 + Phase 3 の全テスト）

- [ ] **Step 6: コミット**

```bash
cd <repo-root>
git add src/stock_analyze_system/services/filing_sync.py src/stock_analyze_system/services/job.py tests/unit/services/test_filing_sync.py tests/unit/services/test_job_service.py
git commit -m "feat: add FilingSyncService, JobService with Bug #4 fix and SyncResult dataclass"
```

---

### Task 9: Repositories __init__.py エクスポート + 全テスト確認

**Files:**
- Modify: `src/stock_analyze_system/repositories/__init__.py`

- [ ] **Step 1: リポジトリパッケージの公開インターフェースを定義**

```python
# src/stock_analyze_system/repositories/__init__.py
"""リポジトリパッケージ"""
from stock_analyze_system.repositories.base import BaseRepository
from stock_analyze_system.repositories.company import CompanyRepository
from stock_analyze_system.repositories.financial import FinancialRepository
from stock_analyze_system.repositories.valuation import ValuationRepository
from stock_analyze_system.repositories.filing import FilingRepository
from stock_analyze_system.repositories.analysis import AnalysisRepository
from stock_analyze_system.repositories.watchlist import WatchlistRepository
from stock_analyze_system.repositories.screening import ScreeningRepository
from stock_analyze_system.repositories.target import TargetRepository
from stock_analyze_system.repositories.document_index import DocumentIndexRepository

__all__ = [
    "BaseRepository",
    "CompanyRepository",
    "FinancialRepository",
    "ValuationRepository",
    "FilingRepository",
    "AnalysisRepository",
    "WatchlistRepository",
    "ScreeningRepository",
    "TargetRepository",
    "DocumentIndexRepository",
]
```

- [ ] **Step 2: 全テスト実行**

Run: `cd <repo-root> && python -m pytest tests/ -v --tb=short 2>&1 | tail -40`
Expected: ALL PASSED

- [ ] **Step 3: ruff lint 実行**

Run: `cd <repo-root> && python -m ruff check src/stock_analyze_system/repositories/ src/stock_analyze_system/services/ tests/unit/repositories/ tests/unit/services/ 2>&1`
Expected: All checks passed (または修正可能な警告のみ)

- [ ] **Step 4: コミット**

```bash
cd <repo-root>
git add src/stock_analyze_system/repositories/__init__.py
git commit -m "feat: add repositories package exports"
```
