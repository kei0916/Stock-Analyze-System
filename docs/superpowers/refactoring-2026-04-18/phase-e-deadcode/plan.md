# Phase E: Dead Code Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** master.md Backlog と /simplify で確定した 11 項目のデッドコード (public methods / functions) を src/ から削除し、対応 test を削除または `get_with_items` API に書換える。

**Architecture:** Layer 単位で 3 commit (repo / service / shared) + docs 1 commit の 4 Task 構成。各 Task は **削除型 TDD** で進める: (a) 既存 test が PASS していることを先に確認 → (b) 削除対象 test を削除/書換 → (c) 実装を削除 → (d) `grep -rn <symbol> src/ tests/` で 0 件確認 → (e) 全テスト PASS 確認 → (f) commit。Phase C / D と同粒度。

**Tech Stack:** Python 3.12, pytest, ruff, uv, SQLAlchemy 2.0 async, Infisical wrapper (`scripts/infisical-run`) 経由で実行する。

**Parent spec:** `docs/superpowers/refactoring-2026-04-18/phase-e-deadcode/design.md`

---

## Files mapped

| Layer | src files | test files |
|---|---|---|
| Task 1 (repo) | `repositories/filing.py`, `repositories/watchlist.py`, `repositories/company.py` | `tests/unit/repositories/test_filing_repo.py`, `test_watchlist_repo.py`, `test_company_repo.py` |
| Task 2 (service) | `services/financial.py`, `services/valuation.py`, `services/rag_service.py`, `services/metrics.py` | `tests/unit/services/test_financial_service.py`, `test_valuation_service.py`, `test_rag_service.py`, `test_metrics.py` |
| Task 3 (shared) | `shared/formatters.py` | `tests/unit/test_shared_formatters.py` |
| Task 4 (docs) | `docs/superpowers/refactoring-2026-04-18/master.md` | (新規) `phase-e-deadcode/report.md` |

---

## Conventions

- 全コマンドは Infisical wrapper 経由:
  `scripts/infisical-run uv run <subcommand>`
- テスト実行例:
  `scripts/infisical-run uv run pytest tests/unit/repositories/ -v`
- ruff 実行例:
  `scripts/infisical-run uv run ruff check src/stock_analyze_system/services/`
- grep 実行例:
  `grep -rn '<symbol>' src/ tests/`

---

## Task 1: Repo layer — 4 methods 削除

**Files:**
- Modify: `src/stock_analyze_system/repositories/filing.py:48-58` (2 methods 削除)
- Modify: `src/stock_analyze_system/repositories/watchlist.py:24-30` (1 method 削除)
- Modify: `src/stock_analyze_system/repositories/company.py:50-52` (1 method 削除)
- Modify: `tests/unit/repositories/test_filing_repo.py:51-84` (2 tests 削除)
- Modify: `tests/unit/repositories/test_watchlist_repo.py:32-47, 66-70` (1 class 削除 + 1 test 書換)
- Modify: `tests/unit/repositories/test_company_repo.py:81-95` (1 test 削除)

---

- [ ] **Step 1.1: Baseline green 確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/repositories/ -v
```
Expected: 全 PASS。現行 suite が削除開始前に緑であることを確認する。

---

- [ ] **Step 1.2: `test_filing_repo.py` から 2 test を削除**

`tests/unit/repositories/test_filing_repo.py` の 51-84 行 (`test_find_by_accession` と `test_find_by_doc_id`) を削除する。削除後の該当領域は以下の形になる (L50 の空行と L87 の `test_find_existing_accessions` が連続する):

削除前 (L50 以降):
```python

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


async def test_find_existing_accessions(session):
```

削除後 (L50 以降):
```python


async def test_find_existing_accessions(session):
```

---

- [ ] **Step 1.3: `test_watchlist_repo.py` の `TestListItems` クラスを削除**

`tests/unit/repositories/test_watchlist_repo.py` から 32-47 行目 (`class TestListItems:` 全体) を削除する。`test_get_with_items_empty_list` (L103) が既に同じカバレッジを提供しているので test 欠損なし。

削除前:
```python
class TestListItems:
    async def test_returns_items(self, session, watchlist_repo, sample_watchlist):
        item = WatchlistItem(
            watchlist_id=sample_watchlist.id,
            company_id="US_AAPL",
            status="monitoring",
        )
        session.add(item)
        await session.flush()
        items = await watchlist_repo.list_items(sample_watchlist.id)
        assert len(items) == 1
        assert items[0].company_id == "US_AAPL"

    async def test_returns_empty_for_no_items(self, watchlist_repo, sample_watchlist):
        items = await watchlist_repo.list_items(sample_watchlist.id)
        assert items == []


class TestAddItem:
```

削除後:
```python
class TestAddItem:
```

---

- [ ] **Step 1.4: `test_watchlist_repo.py` の `TestDeleteItem` を書換**

`test_deletes_item` (L66-70) は `list_items` で削除後の state を検証している。`find_item` を使った等価検証に書き換える。

削除前 (L65-70):
```python
class TestDeleteItem:
    async def test_deletes_item(self, session, watchlist_repo, sample_watchlist):
        item = await watchlist_repo.add_item(sample_watchlist.id, "US_AAPL")
        await watchlist_repo.delete_item(item)
        items = await watchlist_repo.list_items(sample_watchlist.id)
        assert items == []
```

書換後:
```python
class TestDeleteItem:
    async def test_deletes_item(self, session, watchlist_repo, sample_watchlist):
        item = await watchlist_repo.add_item(sample_watchlist.id, "US_AAPL")
        await watchlist_repo.delete_item(item)
        found = await watchlist_repo.find_item(sample_watchlist.id, "US_AAPL")
        assert found is None
```

---

- [ ] **Step 1.5: `test_company_repo.py` から `test_list_by_market` を削除**

`tests/unit/repositories/test_company_repo.py` の 81-95 行目 (`test_list_by_market`) を削除する。削除前:

```python


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

削除後: ファイル末尾は `test_search_japanese_name` の最後の `assert len(results) == 1` で終わる。

---

- [ ] **Step 1.6: test 削除/書換後の中間緑確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/repositories/test_filing_repo.py tests/unit/repositories/test_watchlist_repo.py tests/unit/repositories/test_company_repo.py -v
```
Expected: **PASS**。削除 test は既にファイルから消えているので影響なし。書換えた `test_deletes_item` は `find_item` で検証しているため、実装 (`list_items`) がまだ残っている状態でも PASS する。

**Note (削除型 TDD)**: 通常 TDD は RED → GREEN → REFACTOR だが、Phase E は「実装削除のみ」なので「test 先消去 → 緑維持確認 → 実装消去 → 緑維持確認」の安全削除パターンを採る。後段で実装を消した時点で test 側に caller が残っていれば test が即 RED になり気付ける。

---

- [ ] **Step 1.7: `filing.py` から 2 methods を削除**

`src/stock_analyze_system/repositories/filing.py` の 48-58 行 (6 + 5 + 空行) を削除する。

削除前 (L46-60):
```python
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

    async def _find_existing_keys(
```

削除後:
```python
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _find_existing_keys(
```

---

- [ ] **Step 1.8: `watchlist.py` から `list_items` を削除**

`src/stock_analyze_system/repositories/watchlist.py` の 24-31 行 (`list_items` + 末尾空行) を削除する。

削除前 (L22-32):
```python
        return result.scalar_one_or_none()

    async def list_items(self, watchlist_id: int) -> list[WatchlistItem]:
        """アイテム一覧"""
        stmt = select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_item(
```

削除後:
```python
        return result.scalar_one_or_none()

    async def find_item(
```

---

- [ ] **Step 1.9: `company.py` から `list_by_market` を削除**

`src/stock_analyze_system/repositories/company.py` の 50-52 行を削除する。`list_by_market` の直前の空行もセットで削除。

削除前 (L48-52):
```python
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_market(self, market: str) -> list[Company]:
        """市場別一覧"""
        return await self.list_all(market=market)
```

削除後 (ファイル末尾):
```python
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

---

- [ ] **Step 1.10: 削除検証 — grep が 0 件であること**

Run:
```bash
grep -rn "find_by_accession\|find_by_doc_id\|list_by_market" src/ tests/
grep -rn "watchlist_repo\.list_items\|WatchlistRepository.*list_items\|\.list_items(" src/stock_analyze_system/ tests/unit/
```
Expected: 両コマンドとも **0 件** (no output)。`src/` と `tests/unit/` 配下からシンボルが完全に消えている。

---

- [ ] **Step 1.11: 全 repo tests 緑確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/repositories/ -v
```
Expected: **全 PASS**。削除した method と削除した test の両方が消えているため数は減る (現行より -3 程度)。

---

- [ ] **Step 1.12: ruff clean 確認**

Run:
```bash
scripts/infisical-run uv run ruff check src/stock_analyze_system/repositories/ tests/unit/repositories/
```
Expected: `All checks passed!`

---

- [ ] **Step 1.13: Commit**

```bash
git add \
  src/stock_analyze_system/repositories/filing.py \
  src/stock_analyze_system/repositories/watchlist.py \
  src/stock_analyze_system/repositories/company.py \
  tests/unit/repositories/test_filing_repo.py \
  tests/unit/repositories/test_watchlist_repo.py \
  tests/unit/repositories/test_company_repo.py
git commit -m "$(cat <<'EOF'
refactor(repo): drop dead methods (find_by_accession/doc_id, list_items, list_by_market)

- FilingRepository から find_by_accession / find_by_doc_id 削除 (src 内 caller 0)
- WatchlistRepository.list_items 削除 (Phase C で get_with_items に置換済)
- CompanyRepository.list_by_market 削除 (src 内 caller 0)
- 対応 test 削除 3 件 + test_watchlist_repo.py の test_deletes_item を find_item 検証へ書換

Phase E Task 1.
EOF
)"
```

---

## Task 2: Service layer — 5 methods 削除

**Files:**
- Modify: `src/stock_analyze_system/services/financial.py:17-33, 135-146` (`build_chart_data` + private helpers)
- Modify: `src/stock_analyze_system/services/valuation.py:105-115` (`build_chart_data`)
- Modify: `src/stock_analyze_system/services/rag_service.py:139-151` (`ask_questions`)
- Modify: `src/stock_analyze_system/services/metrics.py:176-185, 190-197` (`peg_ratio`, `cagr`)
- Modify: `tests/unit/services/test_financial_service.py:95-115` (`TestBuildChartData` class 削除)
- Modify: `tests/unit/services/test_valuation_service.py:112-124` (`TestBuildChartData` class 削除)
- Modify: `tests/unit/services/test_rag_service.py:186-196` (`TestAskQuestions` class 削除)
- Modify: `tests/unit/services/test_metrics.py:136-144, 148-153` (5 test methods 削除)

---

- [ ] **Step 2.1: Baseline green 確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/services/ -v
```
Expected: 全 PASS。

---

- [ ] **Step 2.2: `test_financial_service.py` の `TestBuildChartData` を削除**

`tests/unit/services/test_financial_service.py` の 95-115 行目 (`class TestBuildChartData:` 全体) を削除する。これはファイル末尾のクラスなので、削除後ファイルは `TestUpsertFinancialData` の `repo.upsert.assert_called_once()` で終わる。

削除範囲:
```python


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

---

- [ ] **Step 2.3: `test_valuation_service.py` の `TestBuildChartData` を削除**

`tests/unit/services/test_valuation_service.py` の 112-124 行目 (`class TestBuildChartData:` 全体) を削除する。これもファイル末尾のクラスなので、削除後ファイルは `TestComputeGroupDeviation` の最後の `assert results[0]["per_zscore"] is None` で終わる。

削除範囲:
```python


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

---

- [ ] **Step 2.4: `test_rag_service.py` の `TestAskQuestions` を削除**

`tests/unit/services/test_rag_service.py` の 186-196 行目 (`class TestAskQuestions:` 全体) を削除する。

削除範囲:
```python


class TestAskQuestions:
    async def test_ask_multiple_questions(self, service, pageindex_service):
        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/filings/sec/US_AAPL/2025"

        results = await service.ask_questions(filing, ["Q1?", "Q2?"])

        assert len(results) == 2
        assert all(isinstance(r, QueryResult) for r in results)
```

削除後、`TestAskQuestion` (単数形) の直後に `TestGetIndexStatus` が続く形になる。

---

- [ ] **Step 2.5: `test_metrics.py` の 5 test を削除**

`tests/unit/services/test_metrics.py` の以下 5 test methods を削除する。クラス自体は残す。

削除対象 1 — `TestValuation` クラスから (L136-144):
```python
    def test_peg_ratio(self):
        result = metrics.peg_ratio(20.0, 0.15)
        assert result == pytest.approx(20.0 / 15.0)

    def test_peg_ratio_zero_growth(self):
        assert metrics.peg_ratio(20.0, 0.0) is None

    def test_peg_ratio_negative_growth(self):
        assert metrics.peg_ratio(20.0, -0.1) is None
```

削除後、`TestValuation` は `test_psr` (L133-134) で終わる。

削除対象 2 — `TestUtilities` クラスから (L148-153):
```python
    def test_cagr(self):
        result = metrics.cagr(100.0, 200.0, 5.0)
        assert result == pytest.approx((200 / 100) ** (1 / 5) - 1)

    def test_cagr_negative_begin(self):
        assert metrics.cagr(-100.0, 200.0, 5.0) is None

```

削除後、`class TestUtilities:` 直下の最初の test が `test_is_anomaly_true` (元 L155) になる。

---

- [ ] **Step 2.6: test 削除後に緑を確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/services/ -v
```
Expected: **全 PASS**。削除 test 8 件分テスト数が減っている ( -10 程度)。実装はまだ残っているが、caller から消えた削除 method 群は free-standing なので他 test には影響しない。

---

- [ ] **Step 2.7: `financial.py` から `build_chart_data` と専用ヘルパを削除**

`src/stock_analyze_system/services/financial.py` から以下を削除する:
- L17-33 の module-level helpers (`_YOY_MIN_DAYS`, `_YOY_MAX_DAYS` は `compute_timeseries_metrics` が使うので残す)
- 正確には `_CHART_KEYS` / `_PCT_KEYS` / `_to_pct` のみ削除 (**L20-33**)
- L135-146 の `build_chart_data` method

削除対象 1 (L17-33):
```python
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
```

書換後 (L17-):
```python
_YOY_MIN_DAYS = 330
_YOY_MAX_DAYS = 400
```

削除対象 2 (L134-146):
```python
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

書換後:
```python
            results.append(entry)
        return results
```

---

- [ ] **Step 2.8: `valuation.py` から `build_chart_data` を削除**

`src/stock_analyze_system/services/valuation.py` の 104-116 行 (`build_chart_data` method + 前後の空行) を削除する。

削除前 (L102-117):
```python
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


def compute_valuation_from_financials(
```

削除後:
```python
        return results


def compute_valuation_from_financials(
```

---

- [ ] **Step 2.9: `rag_service.py` から `ask_questions` を削除**

`src/stock_analyze_system/services/rag_service.py` の 139-151 行 (`ask_questions` method + 前後の空行) を削除する。

削除前 (L137-153):
```python
        return await self._pageindex.query(tree, question, pdf_path)

    async def ask_questions(
        self, filing, questions: list[str],
    ) -> list[QueryResult]:
        """複数質問を逐次実行する"""
        tree = await self._pageindex.get_or_create_index(filing)
        pdf_path = Path(filing.storage_path) / "converted.pdf"

        results: list[QueryResult] = []
        for q in questions:
            logger.info("RAG Q&A for filing %d: %s", filing.id, q[:50])
            result = await self._pageindex.query(tree, q, pdf_path)
            results.append(result)
        return results

    async def get_index_status(self, company_id: str) -> list[dict]:
```

削除後:
```python
        return await self._pageindex.query(tree, question, pdf_path)

    async def get_index_status(self, company_id: str) -> list[dict]:
```

---

- [ ] **Step 2.10: `metrics.py` から `peg_ratio` と `cagr` を削除**

`src/stock_analyze_system/services/metrics.py` から以下を削除する。

削除対象 1 — `peg_ratio` (L175-185) と直前の空行:
```python


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
```

削除対象 2 — `cagr` (L190-197) と直前の空行を含む:
```python


def cagr(begin_value: float | None,
         end_value: float | None,
         years: float | None) -> float | None:
    if any(v is None for v in (begin_value, end_value, years)):
        return None
    if begin_value <= 0 or end_value <= 0 or years <= 0:
        return None
    return (end_value / begin_value) ** (1.0 / years) - 1.0
```

削除後の該当領域 (元 L173 `psr` の閉じ以降、元 L188 `# ── Utilities ──` 以降):
```python
def psr(market_cap: float | None,
        revenue: float | None) -> float | None:
    return _safe_div(market_cap, revenue, require_positive_denom=True)


# ── Utilities ──────────────────────────────────────────────────

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

---

- [ ] **Step 2.11: 削除検証 — grep が 0 件であること**

Run:
```bash
grep -rn "build_chart_data\|ask_questions" src/ tests/
grep -rn "metrics\.peg_ratio\|metrics\.cagr\|^def peg_ratio\|^def cagr" src/stock_analyze_system/services/
```
Expected: 両コマンドとも **0 件**。

**Note:** 第2コマンドで `metrics\.peg_ratio` を検索するが、`models/screening.py:31` の `peg_ratio: Mapped[...]` (DB column) と `ingestion/yahoo_finance.py:89` の `"peg_ratio"` (dict key) は別物なので `src/stock_analyze_system/services/` に limit している。これらは削除しない。

---

- [ ] **Step 2.12: 未使用 import の cleanup**

`src/stock_analyze_system/services/financial.py` で `_to_pct` / `_CHART_KEYS` / `_PCT_KEYS` が消えたため、他の import が unused になっていないか確認する。`valuation.py` でも同様。

Run:
```bash
scripts/infisical-run uv run ruff check src/stock_analyze_system/services/
```
Expected: `All checks passed!`。もし F401 (unused import) 等が出た場合は該当 import を削除してから再実行する。

---

- [ ] **Step 2.13: 全 service tests 緑確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/services/ -v
```
Expected: **全 PASS** (削除 test 分だけ減少)。

---

- [ ] **Step 2.14: Commit**

```bash
git add \
  src/stock_analyze_system/services/financial.py \
  src/stock_analyze_system/services/valuation.py \
  src/stock_analyze_system/services/rag_service.py \
  src/stock_analyze_system/services/metrics.py \
  tests/unit/services/test_financial_service.py \
  tests/unit/services/test_valuation_service.py \
  tests/unit/services/test_rag_service.py \
  tests/unit/services/test_metrics.py
git commit -m "$(cat <<'EOF'
refactor(service): drop dead methods (build_chart_data, ask_questions, peg_ratio, cagr)

- FinancialService.build_chart_data / ValuationService.build_chart_data 削除
  (CLI/Web/API から未呼出。financial.py の専用ヘルパ _CHART_KEYS / _PCT_KEYS / _to_pct も削除)
- RagService.ask_questions 削除 (RAG API は query() 単一経路)
- metrics.peg_ratio / metrics.cagr (module-level) 削除 (src 内 caller 0)
- 対応 test: TestBuildChartData x2 class 削除、TestAskQuestions class 削除、
  test_metrics.py の test_peg_ratio* 3 件 + test_cagr* 2 件削除

Phase E Task 2.
EOF
)"
```

---

## Task 3: Shared layer — 2 functions 削除

**Files:**
- Modify: `src/stock_analyze_system/shared/formatters.py:11-14, 29-32` (`fmt_pct`, `fmt_ratio` 削除)
- Modify: `tests/unit/test_shared_formatters.py:3-5, 20-29, 46-54` (import 更新 + 2 parametrized class 削除)

---

- [ ] **Step 3.1: Baseline green 確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/test_shared_formatters.py -v
```
Expected: 全 PASS (4 parametrized test が動く)。

---

- [ ] **Step 3.2: `test_shared_formatters.py` の import と 2 class を削除**

`tests/unit/test_shared_formatters.py` を以下のように編集する。

削除前 (L1-5):
```python
"""共有フォーマッタのテスト"""
import pytest
from stock_analyze_system.shared.formatters import (
    fmt_number, fmt_pct, fmt_large, fmt_ratio,
)
```

書換後 (L1-5):
```python
"""共有フォーマッタのテスト"""
import pytest
from stock_analyze_system.shared.formatters import (
    fmt_number, fmt_large,
)
```

削除 2 — `class TestFmtPct:` (L20-29) を削除。周辺と合わせて:

削除前 (L18-32):
```python
        assert fmt_number(val, precision) == expected


class TestFmtPct:
    @pytest.mark.parametrize("val, precision, expected", [
        (0.15, 1, "15.0%"),
        (0.0, 1, "0.0%"),
        (-0.05, 1, "-5.0%"),
        (1.0, 0, "100%"),
        (None, 1, "N/A"),
    ])
    def test_fmt_pct(self, val, precision, expected):
        assert fmt_pct(val, precision) == expected


class TestFmtLarge:
```

書換後:
```python
        assert fmt_number(val, precision) == expected


class TestFmtLarge:
```

削除 3 — `class TestFmtRatio:` (L46-54) を削除。ファイル末尾のクラスなので削除後は `TestFmtLarge` で終わる:

削除前 (L44-54):
```python
        assert fmt_large(val) == expected


class TestFmtRatio:
    @pytest.mark.parametrize("val, precision, expected", [
        (1.5, 2, "1.50"),
        (0.0, 2, "0.00"),
        (-3.14, 1, "-3.1"),
        (None, 2, "N/A"),
    ])
    def test_fmt_ratio(self, val, precision, expected):
        assert fmt_ratio(val, precision) == expected
```

削除後 (ファイル末尾):
```python
        assert fmt_large(val) == expected
```

---

- [ ] **Step 3.3: test 削除後に緑を確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/test_shared_formatters.py -v
```
Expected: **PASS** (`test_fmt_number` と `test_fmt_large` の 2 parametrized test が残存)。合計で 12 test case (`fmt_number` 5 + `fmt_large` 7)。

---

- [ ] **Step 3.4: `formatters.py` から `fmt_pct` と `fmt_ratio` を削除**

`src/stock_analyze_system/shared/formatters.py` から以下を削除する。

削除対象 1 — `fmt_pct` (L11-14) とその前後空行:
```python


def fmt_pct(val: float | None, precision: int = 1) -> str:
    if val is None:
        return "N/A"
    return f"{val * 100:.{precision}f}%"
```

削除対象 2 — `fmt_ratio` (L29-32) とその前の空行:
```python


def fmt_ratio(val: float | None, precision: int = 2) -> str:
    if val is None:
        return "N/A"
    return f"{val:.{precision}f}"
```

削除後のファイル全体 (想定):
```python
"""共有数値フォーマットユーティリティ（CLI, Web 共通）"""
from __future__ import annotations


def fmt_number(val: float | None, precision: int = 1) -> str:
    if val is None:
        return "N/A"
    return f"{val:.{precision}f}"


def fmt_large(val: float | None, precision: int = 1) -> str:
    if val is None:
        return "N/A"
    if abs(val) >= 1e12:
        return f"{val / 1e12:.{precision}f}T"
    if abs(val) >= 1e9:
        return f"{val / 1e9:.{precision}f}B"
    if abs(val) >= 1e6:
        return f"{val / 1e6:.{precision}f}M"
    return f"{val:,.0f}"
```

---

- [ ] **Step 3.5: 削除検証 — grep が 0 件であること**

Run:
```bash
grep -rn "fmt_pct\|fmt_ratio" src/ tests/
```
Expected: **0 件**。

---

- [ ] **Step 3.6: shared tests + ruff 緑確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/test_shared_formatters.py -v
scripts/infisical-run uv run ruff check src/stock_analyze_system/shared/ tests/unit/test_shared_formatters.py
```
Expected: pytest 全 PASS (12 test case)、ruff `All checks passed!`

---

- [ ] **Step 3.7: Commit**

```bash
git add \
  src/stock_analyze_system/shared/formatters.py \
  tests/unit/test_shared_formatters.py
git commit -m "$(cat <<'EOF'
refactor(shared): drop unused formatters (fmt_pct, fmt_ratio)

- shared/formatters.py から fmt_pct / fmt_ratio 削除 (src 内 caller 0)
- test_shared_formatters.py から TestFmtPct / TestFmtRatio parametrized class 削除
- import から fmt_pct / fmt_ratio を除去
- fmt_number / fmt_large は CLI/Web の大量箇所で利用中、継続保持

Phase E Task 3.
EOF
)"
```

---

## Task 4: Docs — Backlog 再分類 + `report.md`

**Files:**
- Modify: `docs/superpowers/refactoring-2026-04-18/master.md` (Phase 進捗表 + Backlog セクション)
- Create: `docs/superpowers/refactoring-2026-04-18/phase-e-deadcode/report.md`

---

- [ ] **Step 4.1: 全 suite 緑を最終確認**

Run:
```bash
scripts/infisical-run uv run pytest -q
```
Expected: **全 PASS** (現行 805 → Phase E 削除後は 790-795 程度、warnings 許容)。ここで commit SHA を記録する (Task 4 で報告書に引用):

```bash
git log --oneline -4
```
各 Task commit の SHA をメモする。

---

- [ ] **Step 4.2: `master.md` の Phase 進捗表を更新**

`docs/superpowers/refactoring-2026-04-18/master.md` の Phase 進捗表 (L11-17) の Phase E 行を更新する。

書換前:
```markdown
| 3 | E — デッドコード削除 | 未使用 import・到達不能コード・未使用分岐の撤去 | ⚪ Pending | — | — | — |
```

書換後:
```markdown
| 3 | **E — デッドコード削除** | 未使用 import・到達不能コード・未使用分岐の撤去 | ✅ **Done** | [design.md](phase-e-deadcode/design.md) | [plan.md](phase-e-deadcode/plan.md) | [report.md](phase-e-deadcode/report.md) |
```

---

- [ ] **Step 4.3: `master.md` の 最新更新 セクションに 2026-04-24 エントリを追加**

L23 付近の `## 最新更新` ブロックの先頭に以下を追加する:

```markdown
- 2026-04-24: [phase-e-deadcode/report.md](phase-e-deadcode/report.md)
  - Phase E 完了。repo/service/shared 3 layer で計 11 項目のデッドコード削除
    (`FilingRepository.find_by_accession` / `find_by_doc_id`,
    `WatchlistRepository.list_items`, `CompanyRepository.list_by_market`,
    `FinancialService.build_chart_data`, `ValuationService.build_chart_data`,
    `RagService.ask_questions`, `metrics.peg_ratio`, `metrics.cagr`,
    `formatters.fmt_pct`, `formatters.fmt_ratio`)。
  - Backlog の (C)/(D) 候補 5 項目は「Intentionally kept」として
    保持理由 + 将来の削除トリガーを付けて Backlog に再分類。
```

---

- [ ] **Step 4.4: `master.md` の Backlog 更新**

L88 付近の `## Backlog` ブロックから旧 `**Phase E (デッドコード) 候補:**` (L102-103 付近の 2 行) を削除し、代わりに「Phase E 消費済」と「Intentionally kept」を追加する。

旧:
```markdown
**Phase E (デッドコード) 候補:**
- `FilingRepository.find_by_accession` / `find_by_doc_id` は src/ 内に caller なし (テストのみ)。
```

新:
```markdown
**Phase E (デッドコード):**
- 2026-04-24 に消費。Task 1 (repo 4 method) + Task 2 (service 5 method) + Task 3 (shared 2 function) = 11 項目削除。
- 消費した項目: `FilingRepository.find_by_accession`, `FilingRepository.find_by_doc_id`,
  `WatchlistRepository.list_items`, `CompanyRepository.list_by_market`,
  `FinancialService.build_chart_data`, `ValuationService.build_chart_data`,
  `RagService.ask_questions`, `metrics.peg_ratio`, `metrics.cagr`,
  `formatters.fmt_pct`, `formatters.fmt_ratio`

**Phase E (デッドコード) — Intentionally kept:**
- `exceptions.RateLimitError` / `ParsingError` / `LlmConnectionError` / `LlmResponseError`: ingestion / LLM 層の broad catch に拾われている可能性。Phase B の broad catch 精査で再評価。
- `config.daily_limit` / `config.batch_size`: SEC 429 対応 / batch ingestion の将来拡張枠。YAML 例に載っており現時点では削除すると不整合。rate-limit 設計確定後に再評価。
- `config.lm_studio_base_url`: Qwen3.6 + llama.cpp 単一ルート確定後に削除候補。現時点 (2026-04-23 snapshot) は Ollama / LM Studio / llama.cpp の 3 ルート検証中。
- `models/competitor_group.py` (`CompetitorGroup` / `CompetitorGroupMember`): 未実装機能 (競合銘柄分析) のスキーマ予約。Alembic migration 含む大工事のため別 Phase で対応。
- ingestion client の未使用 method 群 (`fmp.*`, `sec_edgar.*`, `yahoo_finance.*` 計 11 個): SDK 完全性のため保持。screening / RAG 拡張で利用予定。
```

---

- [ ] **Step 4.5: `report.md` を新規作成**

`docs/superpowers/refactoring-2026-04-18/phase-e-deadcode/report.md` を作成する。テンプレ中の `TASK_1_SHA` / `TASK_2_SHA` / `TASK_3_SHA` は Step 4.1 でメモした Task 1-3 の commit SHA に置換する。Task 4 自体の commit SHA は自己参照になるので「(本 commit)」のまま残す。

内容:

````markdown
# Phase E: Dead Code Deletion — Report

**Status**: ✅ Done (2026-04-24)
**Branch**: `codex-refactoring-followups-20260419`
**Spec**: [design.md](design.md)
**Plan**: [plan.md](plan.md)

---

## 成果物

| Task | Layer | Commit | 内容 |
|---|---|---|---|
| 1 | repo | `TASK_1_SHA` | `FilingRepository.find_by_accession` / `find_by_doc_id`, `WatchlistRepository.list_items`, `CompanyRepository.list_by_market` 削除。対応 test 削除 3 件 + `test_deletes_item` を `find_item` へ書換 |
| 2 | service | `TASK_2_SHA` | `FinancialService.build_chart_data` (+ `_CHART_KEYS` / `_PCT_KEYS` / `_to_pct`), `ValuationService.build_chart_data`, `RagService.ask_questions`, `metrics.peg_ratio`, `metrics.cagr` 削除。対応 test 8 件削除 |
| 3 | shared | `TASK_3_SHA` | `formatters.fmt_pct` / `fmt_ratio` 削除。parametrized test 2 class 削除 |
| 4 | docs | (本 commit) | `master.md` Backlog 再分類 + Phase E ✅ Done 更新、`report.md` 新規作成 |

---

## 削除統計

- **src/ 削除**: ~167 行 (11 public method/function + 3 専用 private helper: `_CHART_KEYS` / `_PCT_KEYS` / `_to_pct`)
- **test 削除 (declaration 単位)**: 標準 test 8 件 + 削除クラス 4 個 (`TestListItems`, `TestBuildChartData` x2, `TestAskQuestions`、内包 test 計 5 件) + parametrized クラス 2 個 (`TestFmtPct` / `TestFmtRatio`、parametrize 展開で 9 case 相当)
- **suite 件数換算**: pytest 表示で約 -22 case (parametrize を 1 case ずつ数えた場合)
- **書換 test**: `test_deletes_item` を `find_item` 検証へ 1 件
- **影響ファイル数**: src 8 files + tests 8 files + docs 2 files = 18 files

---

## 消費した Backlog 項目 (11 項目)

- [x] `FilingRepository.find_by_accession`
- [x] `FilingRepository.find_by_doc_id`
- [x] `WatchlistRepository.list_items`
- [x] `CompanyRepository.list_by_market`
- [x] `FinancialService.build_chart_data`
- [x] `ValuationService.build_chart_data`
- [x] `RagService.ask_questions`
- [x] `metrics.peg_ratio`
- [x] `metrics.cagr`
- [x] `formatters.fmt_pct`
- [x] `formatters.fmt_ratio`

---

## Intentionally kept (保持決定 — 5 カテゴリ)

| 保持対象 | 保持理由 | 将来の削除トリガー |
|---|---|---|
| `exceptions.RateLimitError` / `ParsingError` / `LlmConnectionError` / `LlmResponseError` | broad catch に拾われている可能性、catch 側の精査が必要 | Phase B で broad catch を絞り込む段階 |
| `config.daily_limit` / `config.batch_size` | SEC 429 対応 / batch ingestion の将来拡張枠、YAML 例に載っている | rate-limit 設計確定時 |
| `config.lm_studio_base_url` | Qwen3.6 + llama.cpp 完全移行後に不要、現状は 3 ルート検証中 | 単一ルート確定後 (Phase E-2 候補) |
| `models/competitor_group.py` (`CompetitorGroup` / `CompetitorGroupMember`) | 未実装機能 (競合銘柄分析) のスキーマ予約、migration 含む大工事 | 機能実装 or 正式 scrap 判断時 |
| ingestion client の未使用 method 群 (`fmp.*`, `sec_edgar.*`, `yahoo_finance.*` 計 11 個) | SDK 完全性のため保持、将来の screening / RAG 拡張で使用予定 | 明示的 SDK 切り離し設計時 |

詳細は [design.md §Non-goals 扱いの候補](design.md#non-goals-扱いの候補-backlog-に理由付きで残す) を参照。

---

## Verification

全コマンドは Infisical wrapper 経由で実行した。

- `scripts/infisical-run uv run pytest tests/unit/repositories/ -v`
  - 結果: 全 PASS (現行より -3 件分)
- `scripts/infisical-run uv run pytest tests/unit/services/ -v`
  - 結果: 全 PASS (現行より -10 件分)
- `scripts/infisical-run uv run pytest tests/unit/test_shared_formatters.py -v`
  - 結果: 全 PASS (4 parametrized test → 2 parametrized test)
- `scripts/infisical-run uv run pytest -q`
  - 結果: Phase E 前 805 → Phase E 後 N passed, 4 deselected (N ≈ 783)
- `scripts/infisical-run uv run ruff check src/stock_analyze_system/ tests/`
  - 結果: `All checks passed!`
- `grep -rn "find_by_accession\|find_by_doc_id\|list_by_market\|build_chart_data\|ask_questions\|fmt_pct\|fmt_ratio" src/ tests/`
  - 結果: **0 件**
- `grep -rn "^def peg_ratio\|^def cagr" src/stock_analyze_system/services/metrics.py`
  - 結果: **0 件**

---

## 関連記録

- `../master.md` — project-wide tracker (Phase E 行が ✅ Done、Backlog 再分類済)
- `../phase-c-dry/report.md` — Phase C で同 rule 例外を先に適用した先例
- `../phase-d-performance/report.md` — Phase D で同 layer パターンを最初に使った先例
````

---

- [ ] **Step 4.6: 最終 suite 緑確認**

Run:
```bash
scripts/infisical-run uv run pytest -q -W error::DeprecationWarning -W error::RuntimeWarning
```
Expected: **全 PASS** (warnings-as-errors でも通る)。

---

- [ ] **Step 4.7: Commit**

```bash
git add \
  docs/superpowers/refactoring-2026-04-18/master.md \
  docs/superpowers/refactoring-2026-04-18/phase-e-deadcode/report.md
git commit -m "$(cat <<'EOF'
docs(refactor): Phase E done — dead code removal

- repo/service/shared 3 layer で計 11 項目削除 (~167 src 行 + 対応 test)
- master.md Backlog を「消費済」「Intentionally kept (5 項目)」に再分類
- Phase 進捗表 E を ✅ Done に更新、spec/plan/report リンク反映

Phase E completion. Backlog の Phase E 候補 + /simplify 確認済 (B) 群を消費。
EOF
)"
```

---

## Tests & acceptance (Phase 全体)

- [ ] **全 unit tests PASS**: 現 805 → Task 1-3 で test 削除 (parametrize 展開で約 -22 case) → **約 783 PASS 見込み** (誤差 ±5)
- [ ] **全 integration tests PASS**: 無変更 (削除対象は integration からも未参照)
- [ ] **coverage**: 96% 維持 (削除対象は test のみカバーの dead code、母数も縮む)
- [ ] **ruff clean**: Phase E 新規 0 errors
- [ ] **grep が 0 件**: 削除 symbol 11 個がすべて src/ と tests/ 配下から消失
- [ ] **4 commit**: Task 1 → Task 2 → Task 3 → Task 4 の順、各 commit 直後に pytest 緑確認

## 作業順序 (推奨)

1. **Task 1** (repo layer) — 最小リスク、test 書換 1 件だけ注意
2. **Task 2** (service layer) — 削除行数最大、import cleanup 忘れずに (`ruff check`)
3. **Task 3** (shared layer) — 最小、parametrized test 削除のみ
4. **Task 4** (docs) — 最終化、commit SHA を `report.md` に転記

**/simplify は不要**: Phase E は削除のみで新規コードなし、重複発生の余地がない。

---

## 参照

- Phase E spec: [design.md](design.md)
- master tracker: [../master.md](../master.md)
- Phase C 先例 (rule 例外 + Backlog 再分類): [../phase-c-dry/report.md](../phase-c-dry/report.md)
- Phase D 先例 (layer パターン): [../phase-d-performance/report.md](../phase-d-performance/report.md)
