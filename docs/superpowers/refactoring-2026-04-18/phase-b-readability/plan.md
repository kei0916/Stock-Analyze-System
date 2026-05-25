# Phase B: Readability / Naming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** design.md で確定した 3 クラスタ (履歴コメント除去 + Google スタイル docstring / `Any` → 具体型 / CLI `_handle_*` 型注釈統一) を 4 Task で順番に実装し、src/ 配下から `Bug #N 修正` / `新発見N 修正` / `Bug#N` 文字列を 0 件にする。

**Architecture:** Layer 単位で 3 実装 commit (services / ingestion+cli / cli 型注釈) + docs 1 commit。各 Task は振る舞い不変 (docstring と型アノテーションの変更のみ) のため **non-TDD**: (a) baseline tests green 確認 → (b) 実装変更 → (c) `grep -rn` で履歴残存チェック → (d) 全 unit tests / ruff を緑で確認 → (e) commit。

**Tech Stack:** Python 3.12, pytest, ruff, uv, Infisical wrapper (`scripts/infisical-run`) 経由で実行する。

**Parent spec:** `docs/superpowers/refactoring-2026-04-18/phase-b-readability/design.md`

---

## Scope expansion note (design 整合)

design.md §成功条件 1 は「src/ 配下に `Bug #N 修正` / `新発見N 修正` / `Bug#N` 文字列が 0 件」。実 grep で発見した 11 件のうち、design 本文の Task 列挙に載っていない 5 件 (下記) も Task 2 で同時に除去する。これが plan の **設計 → 実行の整合補正**である。

| 追加対象ファイル:行 | 内容 | 処理 |
|---|---|---|
| `cli/valuation.py:1` | `"""バリュエーションサブコマンド (Bug #16修正: argparse自動ヘルプ)"""` | 履歴 tail 除去 |
| `cli/watchlist.py:2` | `"""ウォッチリストサブコマンド (Bug #17修正: 全ハンドラ統一署名)"""` | 履歴 tail 除去 |
| `cli/watchlist.py:42` | `"""Bug #17修正: 全ハンドラが (args, services) を受け取る"""` | docstring 全置換 (1 行→空文字: self-evident) |
| `cli/jobs.py:2` | `"""ジョブサブコマンド (Bug #3修正: --type削除, sync/daily分離)"""` | 履歴 tail 除去 |
| `cli/serve.py:1` | `"""Webサーバー起動サブコマンド (Bug #15修正: port is not None, 新1修正: 範囲検証)"""` | 履歴 tail 除去 |
| `web/app.py:51` | `"""Bug #8: session_secret/password必須。空ならConfigErrorで起動を止める。"""` | docstring 全置換 (Google 化不要、self-evident) |

`cli/watchlist.py` / `cli/serve.py` / `web/app.py` の関数・method 全体の Google 化は design 対象外のため **行わない** (履歴除去のみ)。

---

## Files mapped

| Task | src files | test files |
|---|---|---|
| Task 1 (services/) | `services/company.py`, `services/job.py`, `services/valuation.py` | `tests/unit/services/test_company_service.py`, `test_job_service.py`, `test_valuation_service.py` |
| Task 2 (ingestion/ + cli/ + 追加 5 件) | `ingestion/sec_edgar.py`, `cli/valuation.py`, `cli/jobs.py`, + 追加: `cli/watchlist.py`, `cli/serve.py`, `web/app.py` | `tests/unit/ingestion/test_sec_edgar.py`, `tests/unit/cli/test_valuation_cli.py`, `test_jobs_cli.py`, `test_watchlist_cli.py`, `test_serve_cli.py`, `tests/unit/web/test_app.py` |
| Task 3 (CLI 型注釈) | `cli/company.py`, `cli/financial.py`, `cli/rag.py`, `cli/valuation.py` | `tests/unit/cli/test_company_cli.py`, `test_financial_cli.py`, `test_rag_cli.py`, `test_valuation_cli.py` |
| Task 4 (docs) | `docs/superpowers/refactoring-2026-04-18/master.md` | (新規) `phase-b-readability/report.md` |

---

## Conventions

- 全コマンドは Infisical wrapper 経由で実行:
  - tests: `scripts/infisical-run uv run pytest <path> -q`
  - ruff: `scripts/infisical-run uv run ruff check <path>`
  - 履歴残存 / tracker link 確認:
    `scripts/infisical-run uv run python scripts/verify_refactoring_phase.py`
    (post-review hardening で追加。`Bug` / `バグ` / `既知バグ` /
    `新発見` / `新N修正` を `src/stock_analyze_system/**/*.py` から検出し、
    `master.md` の markdown link が git-tracked file を指すことも検証する)
- docstring スタイル: Google スタイル (`Args:` / `Returns:` / `Raises:`)。空行 1 つでセクション分離。
- 振る舞い不変を徹底: 既存テストは全て無変更で PASS する
- `__init__` の self 代入のみ / 1 行 delegate method は既存 1 行 docstring を維持
- public API の引数名・並び・default は不変 (master rule §4)

---

## Task 1: services/ 層 (cluster A + B)

**Files:**
- Modify: `src/stock_analyze_system/services/company.py` (L60 履歴除去 + `build_company_id` Google 化、`CompanyService` 全 method Google 化)
- Modify: `src/stock_analyze_system/services/job.py` (L68 `sync_company`, L141 `run_daily_update` 履歴除去 + Google 化)
- Modify: `src/stock_analyze_system/services/valuation.py` (L80 `compute_group_deviation`, L106-117 `compute_valuation_from_financials` 履歴除去 + Google 化 + `fd: Any` → `FinancialData`、`ValuationService` 全 method Google 化)
- Test: 全て無変更で PASS を確認するのみ

---

- [ ] **Step 1.1: Baseline green 確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/services/test_company_service.py tests/unit/services/test_job_service.py tests/unit/services/test_valuation_service.py -q
```
Expected: 全 PASS。着手前に baseline が緑であることを確認する。

---

- [ ] **Step 1.2: `services/company.py` — `build_company_id` docstring + `CompanyService` 全 method Google 化**

`src/stock_analyze_system/services/company.py:60` の `build_company_id` docstring:

Before:
```python
    @staticmethod
    def build_company_id(
        ticker: str | None, security_code: str | None, market: str,
    ) -> str:
        """市場と識別子から企業IDを生成。Bug #7 修正: 未知市場で ValueError。"""
```

After:
```python
    @staticmethod
    def build_company_id(
        ticker: str | None, security_code: str | None, market: str,
    ) -> str:
        """市場と識別子から企業IDを生成する。

        Args:
            ticker: US 市場の ticker symbol。
            security_code: JP 市場の証券コード。
            market: 市場コード (JP_PRIME / US_NASDAQ 等)。

        Returns:
            `JP_<security_code>` または `US_<ticker>` 形式の企業ID。

        Raises:
            ValueError: 市場が未知、または必須識別子が不足している場合。
        """
```

同ファイルの他 method の docstring 整備:

- `CompanyService.__init__` → クラスレベル docstring に集約済 (`"""企業の登録・検索サービス"""` L16) のため追加 docstring 不要
- `register_company` (L21) — Before: `"""企業を登録または更新"""` → Google 化:
```python
    async def register_company(self, data: dict) -> Company:
        """企業を登録または更新する。

        Args:
            data: 登録データ。必須キーは `market` と `name`。
                  `ticker` / `security_code` / `sector` / `cik` / `edinet_code` /
                  `accounting_standard` / `name_ja` は任意。

        Returns:
            永続化された `Company` モデル。

        Raises:
            ValueError: `build_company_id` が拒絶する不正入力。
        """
```
- `get_company` (L44) — 1 行 delegate のため既存 docstring を新規追加 (現在なし):
```python
    async def get_company(self, company_id: str) -> Company | None:
        """ID から `Company` を取得する (存在しなければ None)。"""
        return await self._repo.get_by_id(company_id)
```
- `search_companies` (L47) — 1 行:
```python
    async def search_companies(self, query: str, limit: int = 20) -> list[Company]:
        """部分一致で企業を検索する。"""
        return await self._repo.search(query, limit=limit)
```
- `find_by_identifier` (L50) — 1 行:
```python
    async def find_by_identifier(self, query: str) -> Company | None:
        """ticker / security_code / company_id のいずれかで 1 件を特定する。"""
        return await self._repo.find_by_identifier(query)
```
- `list_companies` (L53) — 1 行:
```python
    async def list_companies(self, **filters: object) -> list[Company]:
        """フィルタに合致する全企業を列挙する。"""
        return await self._repo.list_all(**filters)
```
- `is_us_market` (L72) — 1 行:
```python
    @staticmethod
    def is_us_market(company_id: str) -> bool:
        """`company_id` が US マーケット企業 (`US_` 接頭辞) か判定する。"""
        return company_id.startswith("US_")
```
- `resolve_yf_ticker` (L76) — Google 化:
```python
    @staticmethod
    def resolve_yf_ticker(company: Company) -> str | None:
        """Yahoo Finance で使用可能な ticker 文字列を解決する。

        Args:
            company: 対象企業。

        Returns:
            US 市場なら `company.ticker`、JP 市場なら `<security_code>.T`。
            解決不能なら None。
        """
        if company.id.startswith("US_"):
            return company.ticker
        return f"{company.security_code}.T" if company.security_code else None
```

---

- [ ] **Step 1.3: `services/job.py` — `sync_company` / `run_daily_update` 履歴除去 + Google 化**

`src/stock_analyze_system/services/job.py:68` の `sync_company`:

Before:
```python
    async def sync_company(self, company_id: str) -> SyncResult:
        """単一企業の全データ同期。Bug #4 修正: カウントを正しく追跡。"""
```

After:
```python
    async def sync_company(self, company_id: str) -> SyncResult:
        """単一企業の全データを外部ソースから取り込み、DB に反映する。

        financial / filing / valuation の各カテゴリを並行ではなく順次処理する
        (LLM + SEC の同時実行でのデッドロックを回避するため)。

        Args:
            company_id: 対象企業 ID。

        Returns:
            各カテゴリの取り込み件数とエラー内訳を含む `SyncResult`。

        Raises:
            ValueError: `company_id` に該当する企業が存在しない場合。
        """
```

L141 の `run_daily_update`:

Before:
```python
    async def run_daily_update(self, market: str = "us") -> DailyUpdateResult:
        """日次更新サイクル。新発見3修正: 具体的な例外のみ捕捉。"""
```

After:
```python
    async def run_daily_update(self, market: str = "us") -> DailyUpdateResult:
        """指定市場の全企業に対して `sync_company` を順次実行する。

        個々の企業で発生した `ValueError` / `TypeError` / `AttributeError` /
        `OSError` は捕捉して結果に記録し、次の企業へ続行する。

        Args:
            market: `"us"` または `"jp"`。デフォルトは `"us"`。

        Returns:
            各企業の `SyncResult` を束ねた `DailyUpdateResult`。
        """
```

`JobService.__init__` (L49) は self 代入のみのためクラス docstring (`"""バッチ同期オーケストレーション"""` L47) に集約済で追加整備不要。

`SyncResult` (L26) / `DailyUpdateResult` (L37) の class docstring は既に日本語 1 行でありそのまま。

---

- [ ] **Step 1.4: `services/valuation.py` — 履歴除去 + `fd: Any → FinancialData` + 全 method Google 化**

`src/stock_analyze_system/services/valuation.py` のヘッダ。`Any` は残す (戻り値の heterogenous dict に必要) が、TYPE_CHECKING ガード下に `FinancialData` の import を追加:

Before (L1-12):
```python
"""バリュエーションサービス"""
from __future__ import annotations

import copy
import logging
import statistics
from datetime import date as date_type
from typing import Any

from stock_analyze_system.repositories.valuation import ValuationRepository
from stock_analyze_system.services import metrics
```

After:
```python
"""バリュエーションサービス"""
from __future__ import annotations

import copy
import logging
import statistics
from datetime import date as date_type
from typing import TYPE_CHECKING, Any

from stock_analyze_system.repositories.valuation import ValuationRepository
from stock_analyze_system.services import metrics

if TYPE_CHECKING:
    from stock_analyze_system.models.financial_data import FinancialData
```

`compute_group_deviation` (L77):

Before:
```python
    def compute_group_deviation(
        self, comparisons: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """各企業の比較行に z-score 偏差を追加。新発見5修正: 新しいリストを返す。"""
```

After:
```python
    def compute_group_deviation(
        self, comparisons: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """各企業の比較行に PER/PBR/EV-EBITDA/PSR の z-score 偏差列を加える。

        入力は破壊せず、deepcopy した新しいリストに `<metric>_zscore` キーを
        追加して返す。

        Args:
            comparisons: `compare_valuations` が返す辞書リスト。

        Returns:
            各行に 4 メトリクスの zscore (±2σ = ±2.0) を付与した新リスト。
            標本数 <2 または stdev=0 の metric については None を入れる。
        """
```

`compute_valuation_from_financials` (L106):

Before:
```python
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
```

After:
```python
def compute_valuation_from_financials(
    stock_price: float | None,
    fd: "FinancialData",
    currency: str,
    val_date: date_type,
    market_cap: float | None = None,
) -> dict[str, Any]:
    """株価と財務データから valuation dict を算出する。

    `stock_price` が None の場合は全メトリクスを None とした dict を返す
    (DB 側の upsert を途切れさせないため)。`market_cap` が明示されない場合は
    `fd.shares_outstanding * stock_price` を代替値とする。

    Args:
        stock_price: 株価 (通貨は `currency`)。None 可。
        fd: `FinancialData` レコード。EPS / equity / FCF 等を参照。
        currency: 通貨コード ("USD" / "JPY" 等)。
        val_date: バリュエーション基準日。
        market_cap: 時価総額。None の場合は `fd.shares_outstanding` から推定する。

    Returns:
        `currency` / `date` / `stock_price` / `market_cap` / `per` / `pbr` /
        `ev_ebitda` / `psr` / `fcf_yield` を含む dict。算出不能な項目は None。
    """
```

同ファイル他 method:
- `ValuationService.__init__` (L21) はクラス docstring に集約済で追加不要
- `upsert_valuation` (L24) — Google 化:
```python
    async def upsert_valuation(
        self, company_id: str, data: dict[str, Any],
    ):
        """(company_id, date) の一意キーでバリュエーション行を upsert する。

        Args:
            company_id: 対象企業 ID。
            data: 少なくとも `date` キーを含む dict。他のキーはそのまま列値へ。

        Returns:
            永続化された `Valuation` モデル。
        """
```
- `get_history` (L32) — 1 行:
```python
    async def get_history(self, company_id: str, years: int = 10):
        """過去 `years` 年分のバリュエーション履歴を古い順で返す。"""
        return await self._repo.get_history(company_id, years)
```
- `get_latest` (L35) — 1 行:
```python
    async def get_latest(self, company_id: str):
        """最新のバリュエーション 1 件を返す (存在しなければ None)。"""
        return await self._repo.get_latest(company_id)
```
- `compare_valuations` (L38) — Google 化:
```python
    async def compare_valuations(
        self, company_ids: list[str],
    ) -> list[dict[str, Any]]:
        """複数企業の最新バリュエーションを横並び dict 列に整形する。

        Args:
            company_ids: 比較対象の企業 ID リスト。

        Returns:
            `company_id` / `date` / `stock_price` / `market_cap` /
            `per` / `pbr` / `ev_ebitda` / `psr` / `fcf_yield` を含む辞書リスト。
            バリュエーションが未登録の企業は全値 None で埋める。
        """
```
- `compute_per_range` (L66) — Google 化:
```python
    def compute_per_range(self, valuations: list) -> dict[str, float | None]:
        """正の PER 値のみを抽出し、`high` / `median` / `low` を返す。

        Args:
            valuations: `get_history` の返値 (`Valuation` モデル列)。

        Returns:
            {"high", "median", "low"} の辞書。有効な PER が 1 件もなければ
            3 値とも None。
        """
```

---

- [ ] **Step 1.5: Task 1 検証 — tests / ruff / grep**

Run (並行可):
```bash
scripts/infisical-run uv run pytest tests/unit/services/test_company_service.py tests/unit/services/test_job_service.py tests/unit/services/test_valuation_service.py -q
scripts/infisical-run uv run ruff check src/stock_analyze_system/services/company.py src/stock_analyze_system/services/job.py src/stock_analyze_system/services/valuation.py
grep -rn '新発見\|Bug #[0-9]\|Bug#[0-9]' src/stock_analyze_system/services/
```
Expected:
- pytest: 全 PASS (変更前と同件数)
- ruff: clean
- grep: 0 件 (services/ 配下からは全消去)

---

- [ ] **Step 1.6: Task 1 commit**

```bash
git add src/stock_analyze_system/services/company.py src/stock_analyze_system/services/job.py src/stock_analyze_system/services/valuation.py
git commit -m "$(cat <<'EOF'
refactor(services): apply Google-style docstrings + strict types (Phase B cluster 1)

- services/company.py: Bug #7 履歴除去、build_company_id に Args/Returns/Raises、
  CompanyService 全 method を Google 化
- services/job.py: Bug #4 / 新発見3 履歴除去、sync_company / run_daily_update
  の docstring を整備
- services/valuation.py: 新発見1/2/5 履歴除去、
  compute_valuation_from_financials の fd: Any → "FinancialData" (TYPE_CHECKING)、
  ValuationService 全 method を Google 化
- 既存 unit tests 無変更で全 PASS、ruff clean

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: ingestion/ + cli/ + 追加 5 件 (cluster A)

**Files:**
- Modify: `src/stock_analyze_system/ingestion/sec_edgar.py` (L84 `新発見4修正` コメント除去、`SecEdgarClient` 全 public method docstring Google 化)
- Modify: `src/stock_analyze_system/cli/valuation.py` (L1 module docstring + L28 inline コメント履歴除去、docstring 整備。型注釈は Task 3)
- Modify: `src/stock_analyze_system/cli/jobs.py` (L2 module docstring + L20 inline コメント履歴除去、docstring 整備)
- Modify: `src/stock_analyze_system/cli/watchlist.py` (L2 module docstring + L42 method docstring の履歴除去)
- Modify: `src/stock_analyze_system/cli/serve.py` (L1 module docstring の履歴除去)
- Modify: `src/stock_analyze_system/web/app.py` (L51 関数 docstring の履歴除去)
- Test: 全て無変更で PASS を確認するのみ

---

- [ ] **Step 2.1: Baseline green 確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/ingestion/test_sec_edgar.py tests/unit/cli/test_valuation_cli.py tests/unit/cli/test_jobs_cli.py tests/unit/cli/test_watchlist_cli.py tests/unit/cli/test_serve_cli.py tests/unit/web/test_app.py -q
```
Expected: 全 PASS。

---

- [ ] **Step 2.2: `ingestion/sec_edgar.py` — 履歴コメント除去 + `SecEdgarClient` Google 化**

L84 の inline コメント削除:

Before (L82-85):
```python
        results = []

        # zip で安全にイテレート（新発見4修正）
        for form, filing_date, report_date, acc_no, primary_doc, desc in zip(
```

After:
```python
        results = []

        for form, filing_date, report_date, acc_no, primary_doc, desc in zip(
```

`SecEdgarClient` の public method (`get_company_facts` / `list_filings` / `download_submission` / `search_efts` 等) の既存 1 行 docstring を Google 化する。**対象は public method のみ**。`_install_pypdf_compat` 等の `_` prefix private helper は既存 1 行 docstring を維持。

各 method の具体 docstring 文面は実装時に現行の振る舞いを読んで決定する (本 plan では行文字数の節約のため省略)。最低要件は `Args:` / `Returns:` / `Raises:` セクションを含めること。

**注**: `search_efts` (L114) に現存する `"""EFTS全文検索（C2修正: 仕様書で定義済みのメソッド）"""` の `C2修正` は design §成功条件 grep の対象文字列 (`Bug #N` / `新発見N` / `Bug#N`) には含まれないため **履歴として除去しない** (履歴除去の対象外パターン)。docstring は Google 化のみ行う。

---

- [ ] **Step 2.3: `cli/valuation.py` — module docstring + inline コメント履歴除去**

L1:

Before:
```python
"""バリュエーションサブコマンド (Bug #16修正: argparse自動ヘルプ)"""
```

After:
```python
"""バリュエーションサブコマンド (show / compare / range / deviation)"""
```

L27-28:

Before:
```python
async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    # Bug #16修正: no manual usage string. argparse auto-generates help including deviation.
    if not getattr(args, "action", None):
        sys.exit(1)
```

After:
```python
async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    if not getattr(args, "action", None):
        sys.exit(1)
```

docstring 整備: `register_parser` / `handle` / `_handle_*` / `_valuation_to_row` に簡潔な 1 行ないし Args/Returns docstring を付与 (型注釈は Task 3)。

---

- [ ] **Step 2.4: `cli/jobs.py` — module docstring + inline コメント履歴除去**

L1-2:

Before:
```python
# src/stock_analyze_system/cli/jobs.py
"""ジョブサブコマンド (Bug #3修正: --type削除, sync/daily分離)"""
```

After:
```python
"""ジョブサブコマンド (sync / daily)"""
```

L19-21:

Before:
```python
    sub.required = True

    # Bug #3修正: sync と daily を明確に分離。--type は削除。
    sync_p = sub.add_parser("sync", help="単一企業のデータ同期")
```

After:
```python
    sub.required = True

    sync_p = sub.add_parser("sync", help="単一企業のデータ同期")
```

`register_parser` / `handle` / `_handle_sync` / `_handle_daily` の docstring を Google 化 (`handle` / `_handle_*` は 1 行で十分)。

---

- [ ] **Step 2.5: `cli/watchlist.py` — 履歴 tail 除去**

L2:

Before:
```python
"""ウォッチリストサブコマンド (Bug #17修正: 全ハンドラ統一署名)"""
```

After:
```python
"""ウォッチリストサブコマンド"""
```

L42 (`handle` 関数):

Before:
```python
async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    """Bug #17修正: 全ハンドラが (args, services) を受け取る"""
```

After:
```python
async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    """`watchlist` サブコマンドのディスパッチ。"""
```

同ファイル他 method の Google 化は design 対象外のため **変更しない**。

---

- [ ] **Step 2.6: `cli/serve.py` — 履歴 tail 除去**

L1:

Before:
```python
"""Webサーバー起動サブコマンド (Bug #15修正: port is not None, 新1修正: 範囲検証)"""
```

After:
```python
"""Webサーバー起動サブコマンド"""
```

---

- [ ] **Step 2.7: `web/app.py` — 履歴 tail 除去**

L51 (関数 docstring):

Before:
```python
    """Bug #8: session_secret/password必須。空ならConfigErrorで起動を止める。"""
```

After:
```python
    """session_secret と admin password が設定済みか検証する。

    未設定・空文字列の場合は `ConfigError` を送出して起動を停止する。
    """
```

---

- [ ] **Step 2.8: Task 2 検証 — tests / ruff / grep**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/ingestion/ tests/unit/cli/ tests/unit/web/test_app.py -q
scripts/infisical-run uv run ruff check src/stock_analyze_system/ingestion/sec_edgar.py src/stock_analyze_system/cli/valuation.py src/stock_analyze_system/cli/jobs.py src/stock_analyze_system/cli/watchlist.py src/stock_analyze_system/cli/serve.py src/stock_analyze_system/web/app.py
grep -rn '新発見\|Bug #[0-9]\|Bug#[0-9]' src/
```
Expected:
- pytest: 全 PASS
- ruff: clean
- grep: **0 件** (src/ 全体から Bug#/新発見 が全消去 — design §成功条件 1 達成)

---

- [ ] **Step 2.9: Task 2 commit**

```bash
git add src/stock_analyze_system/ingestion/sec_edgar.py src/stock_analyze_system/cli/valuation.py src/stock_analyze_system/cli/jobs.py src/stock_analyze_system/cli/watchlist.py src/stock_analyze_system/cli/serve.py src/stock_analyze_system/web/app.py
git commit -m "$(cat <<'EOF'
refactor(ingestion,cli,web): apply Google-style docstrings (Phase B cluster 2)

- ingestion/sec_edgar.py: 新発見4 履歴コメント除去、SecEdgarClient 全 public
  method docstring を Google 化
- cli/valuation.py: L1 module / L28 inline の Bug #16 履歴除去、docstring 整備
  (型注釈は Task 3)
- cli/jobs.py: L2 module / L20 inline の Bug #3 履歴除去、docstring を Google 化
- cli/watchlist.py: L2 module / L42 method の Bug #17 履歴除去 (design 拡張)
- cli/serve.py: L1 module の Bug #15 / 新1 履歴除去 (design 拡張)
- web/app.py: L51 関数 docstring の Bug #8 履歴除去 (design 拡張)
- src/ 全体で grep 'Bug #N|新発見N|Bug#N' が 0 件
- 既存 tests 無変更で全 PASS、ruff clean

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: CLI `_handle_*` 型注釈統一 (cluster C)

**Files:**
- Modify: `src/stock_analyze_system/cli/company.py` (`_handle_register` / `_handle_search` / `_handle_show` に型注釈)
- Modify: `src/stock_analyze_system/cli/financial.py` (`_handle_show` / `_handle_metrics` に型注釈)
- Modify: `src/stock_analyze_system/cli/rag.py` (`_handle_health` / `_handle_index` / `_handle_analyze` / `_handle_ask` / `_handle_status` / `_handle_show` に型注釈)
- Modify: `src/stock_analyze_system/cli/valuation.py` (`_handle_show` / `_handle_compare` / `_handle_range` / `_handle_deviation` / `_valuation_to_row` に型注釈)

---

- [ ] **Step 3.1: Baseline green 確認**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/cli/test_company_cli.py tests/unit/cli/test_financial_cli.py tests/unit/cli/test_rag_cli.py tests/unit/cli/test_valuation_cli.py -q
```
Expected: 全 PASS。

---

- [ ] **Step 3.2: `cli/company.py` — `_handle_*` 型注釈追加**

既存の `TYPE_CHECKING` ガードで `ServiceContainer` が import 済 (L9-10)。`argparse` は L3 で import 済。

Before (L42):
```python
async def _handle_register(args, services):
```
After:
```python
async def _handle_register(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
```

同様に L58 `_handle_search`, L69 `_handle_show` に `args: argparse.Namespace, services: ServiceContainer, -> None` を付与。

---

- [ ] **Step 3.3: `cli/financial.py` — `_handle_*` 型注釈追加**

既存の `TYPE_CHECKING` ガードで `ServiceContainer` が import 済。`argparse` は L4 で import 済。

L56 `_handle_show`, L77 `_handle_metrics` に型注釈追加:

```python
async def _handle_show(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
```
```python
async def _handle_metrics(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
```

ヘルパー `_fmt_metric` (L22) は既に型注釈済。

---

- [ ] **Step 3.4: `cli/rag.py` — `_handle_*` 型注釈追加 (rag 先頭形)**

`cli/rag.py` は他 CLI と異なり `rag` (RagService) を第一引数に取る特殊形。既存の `TYPE_CHECKING` ガードで `ServiceContainer` が import 済 (L14-15)。追加で `RagService` の import が必要。

L14-15 を以下に差し替え:
```python
if TYPE_CHECKING:
    from stock_analyze_system.cli.helpers import ServiceContainer
    from stock_analyze_system.services.rag_service import RagService
```

各 `_handle_*` に型注釈:

- L85 `_handle_health(rag, args) -> None` → `_handle_health(rag: "RagService", args: argparse.Namespace) -> None`
- L100 `_handle_index(rag, services, args) -> None` → `_handle_index(rag: "RagService", services: ServiceContainer, args: argparse.Namespace) -> None`
- L140 `_handle_analyze(rag, services, args) -> None` → 同上
- L172 `_handle_ask(rag, services, args) -> None` → 同上
- L193 `_handle_status(rag, args) -> None` → `_handle_status(rag: "RagService", args: argparse.Namespace) -> None`
- L210 `_handle_show(rag, services, args) -> None` → `_handle_show(rag: "RagService", services: ServiceContainer, args: argparse.Namespace) -> None`

**注**: `rag` と `services` は TYPE_CHECKING ガード下の import のため、アノテーションは文字列形式 (`"RagService"` / `ServiceContainer`) で書く。現行 3 関数 (`_handle_index` 等) の `ServiceContainer` 参照は既に文字列不要 (将来評価。`from __future__ import annotations` のため)。

---

- [ ] **Step 3.5: `cli/valuation.py` — `_handle_*` 型注釈追加**

既存の `TYPE_CHECKING` ガードで `ServiceContainer` が import 済 (L9-10)。

- L37 `_handle_show(args, services)` → `_handle_show(args: argparse.Namespace, services: ServiceContainer) -> None`
- L50 `_handle_compare(args, services)` → 同上
- L66 `_handle_range(args, services)` → 同上
- L84 `_handle_deviation(args, services)` → 同上
- L108 `_valuation_to_row(v) -> dict` → 現行のまま (`v` は SQLAlchemy モデルで `Valuation` 型。TYPE_CHECKING で import して `v: "Valuation"` に精緻化可能だが、design の対象外のため **触らない**)

---

- [ ] **Step 3.6: Task 3 検証 — tests / ruff**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit/cli/ -q
scripts/infisical-run uv run ruff check src/stock_analyze_system/cli/company.py src/stock_analyze_system/cli/financial.py src/stock_analyze_system/cli/rag.py src/stock_analyze_system/cli/valuation.py
```
Expected:
- pytest: 全 PASS (型注釈追加は実行時 noop)
- ruff: clean

---

- [ ] **Step 3.7: Task 3 commit**

```bash
git add src/stock_analyze_system/cli/company.py src/stock_analyze_system/cli/financial.py src/stock_analyze_system/cli/rag.py src/stock_analyze_system/cli/valuation.py
git commit -m "$(cat <<'EOF'
refactor(cli): align _handle_* type annotations (Phase B cluster 3)

- cli/company.py / cli/financial.py / cli/valuation.py の _handle_* 関数に
  args: argparse.Namespace, services: ServiceContainer, -> None を付与
- cli/rag.py の _handle_* は rag: "RagService" を先頭で受ける特殊形。
  TYPE_CHECKING ガードに RagService を追加
- 既存テスト無変更で全 PASS、ruff clean

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: docs update + Codex 追跡用 change-log

**Files:**
- Modify: `docs/superpowers/refactoring-2026-04-18/master.md` (Phase 進捗表 + Backlog)
- Create: `docs/superpowers/refactoring-2026-04-18/phase-b-readability/report.md`

---

- [ ] **Step 4.1: master.md の Phase 進捗表を更新**

`docs/superpowers/refactoring-2026-04-18/master.md` の Phase 進捗表 (L10-18) で Phase B の行を:

Before:
```markdown
| 4 | B — 可読性・命名 | 関数名・引数・コメント精査、スタイル統一 | ⚪ Pending | — | — | — |
```

After:
```markdown
| 4 | B — 可読性・命名 | 関数名・引数・コメント精査、スタイル統一 | ✅ **Done** | [design.md](phase-b-readability/design.md) | [plan.md](phase-b-readability/plan.md) | [report.md](phase-b-readability/report.md) |
```

同ファイルの Backlog セクション内 `**Phase B (可読性) 候補:**` を以下で書き換え:

Before:
```markdown
**Phase B (可読性) 候補:**
- 現時点では追加候補なし。
```

After:
```markdown
**Phase B (可読性):**
- 2026-04-24 完了。services/ingestion/cli/web 横断で履歴コメント 11 件を除去、
  対象 3 クラスタ (docstring Google 化 / fd: Any → "FinancialData" / CLI
  `_handle_*` 型注釈統一) を 3 実装 commit に集約。
- 消費した項目:
  Bug #7 / Bug #4 / 新発見3 / 新発見1 / 新発見2 / 新発見5 / 新発見4 /
  Bug #16 / Bug #3 / Bug #17 / Bug #15 + 新1 / Bug #8 の 11 件履歴除去、
  `compute_valuation_from_financials` の `fd: Any → FinancialData`、
  `cli/{company,financial,rag,valuation}.py` の `_handle_*` 型注釈統一。
```

---

- [ ] **Step 4.2: phase-b-readability/report.md を新規作成**

以下のテンプレートで作成 (Task 1/2/3 の実 commit hash は Task 4 着手時点で `git log --oneline -5` から取得して差し込む):

```markdown
# Phase B: 可読性・命名 — 実施記録

**Status**: ✅ Done (2026-04-24)

各 Task 完了時に追記。記録項目: 変更ファイル / commit hash / 除去した履歴 /
追加した型注釈 / 備考。

---

## Task 記録

### Task 1: services/ 層 — ✅ Done (2026-04-24)

- 変更:
  - `src/stock_analyze_system/services/company.py` (Bug #7 履歴除去 +
    `build_company_id` の Args/Returns/Raises、`CompanyService` 全 method Google 化)
  - `src/stock_analyze_system/services/job.py` (Bug #4 / 新発見3 履歴除去、
    `sync_company` / `run_daily_update` docstring 整備)
  - `src/stock_analyze_system/services/valuation.py` (新発見1/2/5 履歴除去、
    `fd: Any → "FinancialData"`、`ValuationService` 全 method Google 化)
- 結果: `tests/unit/services/` green、ruff clean、services/ 配下の
  `Bug #N` / `新発見N` grep が 0 件。
- commit: `<TASK_1_SHA>`

### Task 2: ingestion/ + cli/ + web/ 層 — ✅ Done (2026-04-24)

- 変更:
  - `src/stock_analyze_system/ingestion/sec_edgar.py` (新発見4 除去 +
    `SecEdgarClient` Google 化)
  - `src/stock_analyze_system/cli/valuation.py` (Bug #16 除去 x2、docstring 整備)
  - `src/stock_analyze_system/cli/jobs.py` (Bug #3 除去 x2、docstring 整備)
  - `src/stock_analyze_system/cli/watchlist.py` (Bug #17 除去 x2 — design 拡張)
  - `src/stock_analyze_system/cli/serve.py` (Bug #15 + 新1 除去 — design 拡張)
  - `src/stock_analyze_system/web/app.py` (Bug #8 除去 — design 拡張)
- 結果: `tests/unit/ingestion/`, `tests/unit/cli/`, `tests/unit/web/test_app.py`
  green、ruff clean、**src/ 全体の `Bug #N` / `新発見N` / `Bug#N` grep が 0 件**
  (design §成功条件 1 達成)。
- commit: `<TASK_2_SHA>`

### Task 3: CLI `_handle_*` 型注釈統一 — ✅ Done (2026-04-24)

- 変更:
  - `src/stock_analyze_system/cli/company.py` (3 関数に型注釈)
  - `src/stock_analyze_system/cli/financial.py` (2 関数に型注釈)
  - `src/stock_analyze_system/cli/rag.py` (6 関数に型注釈、`rag` 先頭形)
  - `src/stock_analyze_system/cli/valuation.py` (4 関数に型注釈)
- 結果: `tests/unit/cli/` green、ruff clean。
- commit: `<TASK_3_SHA>`

### Task 4: Docs update — ✅ Done (2026-04-24)

- 変更:
  - `docs/superpowers/refactoring-2026-04-18/master.md`
    (Phase B 進捗表を ✅ Done に更新、Backlog を消費済み項目へ書き換え)
  - 本ファイル `report.md` 新規作成
- commit: `<TASK_4_SHA>`

---

## 変更箇所 change-log (Codex 追跡用)

### 除去した履歴コメント (11 件)

| # | ファイル:行 | 除去前文字列 | 状態 |
|---|---|---|---|
| 1 | services/company.py:60 | `Bug #7 修正: 未知市場で ValueError。` | docstring tail 除去 + Google 化 |
| 2 | services/job.py:68 | `Bug #4 修正: カウントを正しく追跡。` | docstring tail 除去 + Google 化 |
| 3 | services/job.py:141 | `新発見3修正: 具体的な例外のみ捕捉。` | docstring tail 除去 + Google 化 |
| 4 | services/valuation.py:80 | `新発見5修正: 新しいリストを返す。` | docstring tail 除去 + Google 化 |
| 5 | services/valuation.py:115 | `新発見1修正: stock_price が None の場合は安全に処理。` | docstring 全書換 + Google 化 |
| 6 | services/valuation.py:116 | `新発見2修正: shares_outstanding の明示的 None チェック。` | docstring 全書換 (5 と同時) |
| 7 | ingestion/sec_edgar.py:84 | `# zip で安全にイテレート（新発見4修正）` | inline コメント除去 |
| 8 | cli/valuation.py:1 | `(Bug #16修正: argparse自動ヘルプ)` | module docstring tail 除去 |
| 9 | cli/valuation.py:28 | `# Bug #16修正: no manual usage string. ...` | inline コメント除去 |
| 10 | cli/jobs.py:2 | `(Bug #3修正: --type削除, sync/daily分離)` | module docstring tail 除去 |
| 11 | cli/jobs.py:20 | `# Bug #3修正: sync と daily を明確に分離。--type は削除。` | inline コメント除去 |
| 12 | cli/watchlist.py:2 | `(Bug #17修正: 全ハンドラ統一署名)` | module docstring tail 除去 |
| 13 | cli/watchlist.py:42 | `Bug #17修正: 全ハンドラが (args, services) を受け取る` | method docstring 全書換 |
| 14 | cli/serve.py:1 | `(Bug #15修正: port is not None, 新1修正: 範囲検証)` | module docstring tail 除去 |
| 15 | web/app.py:51 | `Bug #8: session_secret/password必須。空ならConfigErrorで起動を止める。` | docstring 全書換 |

※ 正確なカウント: grep マッチ数としては 11 行だが、docstring 内の `Bug #7` のように
  1 行に 1 件含まれる箇所をエントリ単位で数えた結果は 15 entry となる。
  最終的な grep `src/` 全体 0 件が受入条件。

### Google スタイル docstring に書き換えた関数

| ファイル | 関数 | 種別 |
|---|---|---|
| services/company.py | build_company_id | 履歴除去 + Args/Returns/Raises |
| services/company.py | register_company | Google 化 |
| services/company.py | resolve_yf_ticker | Google 化 |
| services/company.py | get_company / search_companies / find_by_identifier / list_companies / is_us_market | 1 行 docstring 追加 |
| services/job.py | sync_company | 履歴除去 + Args/Returns/Raises |
| services/job.py | run_daily_update | 履歴除去 + Args/Returns |
| services/valuation.py | compute_group_deviation | 履歴除去 + Args/Returns |
| services/valuation.py | compute_valuation_from_financials | 履歴除去 + `fd: Any → "FinancialData"` + Args/Returns |
| services/valuation.py | upsert_valuation / compare_valuations / compute_per_range | Google 化 |
| services/valuation.py | get_history / get_latest | 1 行 docstring 追加 |
| ingestion/sec_edgar.py | SecEdgarClient 全 public method | Google 化 |
| cli/valuation.py | register_parser / handle / _handle_* / _valuation_to_row | docstring 整備 |
| cli/jobs.py | register_parser / handle / _handle_sync / _handle_daily | docstring 整備 |
| cli/watchlist.py | handle | docstring 全書換 |
| web/app.py | (L51 の関数) | docstring 全書換 |

### 追加した型注釈

| ファイル | 関数 | パラメータ | 追加型 |
|---|---|---|---|
| services/valuation.py | compute_valuation_from_financials | fd | `"FinancialData"` (TYPE_CHECKING) |
| cli/company.py | _handle_register / _handle_search / _handle_show | args, services, -> | argparse.Namespace, ServiceContainer, None |
| cli/financial.py | _handle_show / _handle_metrics | args, services, -> | argparse.Namespace, ServiceContainer, None |
| cli/rag.py | _handle_health / _handle_status | rag, args, -> | "RagService", argparse.Namespace, None |
| cli/rag.py | _handle_index / _handle_analyze / _handle_ask / _handle_show | rag, services, args, -> | "RagService", ServiceContainer, argparse.Namespace, None |
| cli/valuation.py | _handle_show / _handle_compare / _handle_range / _handle_deviation | args, services, -> | argparse.Namespace, ServiceContainer, None |

---

## サマリー

| 指標 | Before (`9fb37d3`) | After (Phase B 完了) | 差分 |
|---|---|---|---|
| 全 unit tests 件数 | 773 (Phase E 完了直後) | 773 | 0 |
| 全 unit tests 結果 | green | green | — |
| ruff (touched layer) | clean | clean | — |
| 履歴コメント残数 (src/ grep) | 15 | **0** | -15 |
| Google docstring 化した関数 | 0 | 25+ | +25+ |
| `_handle_*` 型注釈済み CLI ファイル | 3/7 | **7/7** | +4 |

---

## スコープ外 (次 Phase)

- `pageindex_service.py` (514 行) の分割 → Phase A で扱う
- 対象外ファイルの docstring Google 化 (cli/watchlist.py の method 全体、
  cli/serve.py / web/app.py の周辺関数) → 次回 follow-up
- `_valuation_to_row(v)` の `v: "Valuation"` 精緻化 → Phase A で型層整備と合わせて検討
- TypedDict 化 (valuation dict / metrics dict) → Phase A
- `mypy` / `pyright` 導入 → Phase A 後

---

## Phase B 完了 (2026-04-24)

- Task 1〜4 すべて完了
- 全 unit tests 773 PASS (削除テスト 0 件、追加テスト 0 件 — 振る舞い不変)
- ruff clean (Phase B 範囲で新規 error 0)
- `grep -rn '新発見\|Bug #[0-9]\|Bug#[0-9]' src/` が 0 件
- 次 Phase: A (構造改善)
```

---

- [ ] **Step 4.3: Task 4 検証**

Run:
```bash
grep -rn '新発見\|Bug #[0-9]\|Bug#[0-9]' src/
scripts/infisical-run uv run pytest -q
```
Expected:
- grep: 0 件
- pytest: 全 PASS

実 commit hash で `<TASK_1_SHA>` 〜 `<TASK_4_SHA>` を置換することを忘れない (Task 4 commit の直前に `git log --oneline -5` で確認)。

---

- [ ] **Step 4.4: Task 4 commit**

```bash
git add docs/superpowers/refactoring-2026-04-18/master.md docs/superpowers/refactoring-2026-04-18/phase-b-readability/report.md
git commit -m "$(cat <<'EOF'
docs(phase-b): mark Phase B done in master + add report with change-log

- master.md: Phase B を ✅ Done に更新、design/plan/report リンクを追加。
  Backlog の "Phase B 候補" を "消費した項目" 一覧へ書き換え。
- phase-b-readability/report.md 新規作成:
  - 3 実装 commit (services / ingestion+cli+web / cli 型注釈) を Task 単位で記録
  - 除去した履歴コメント 15 entry、書き換えた docstring 25+ 件、
    追加した型注釈 15+ 件を Codex 追跡可能な table 形式で列挙
  - 全 unit tests 773 PASS / ruff clean / grep src/ 0 件を確認
- 次 Phase は A (構造改善)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## テスト & 受け入れ基準 (全 Task 完了時)

- 全 unit tests 773 PASS (変更なし)
- `scripts/infisical-run uv run pytest -q` が緑
- `scripts/infisical-run uv run ruff check src/` が clean
- `scripts/infisical-run uv run python scripts/verify_refactoring_phase.py` が green
- design.md §成功条件 1〜5 をすべて満たす
- Task 1〜4 が独立した 4 commit に分離されている
- `phase-b-readability/report.md` に 4 Task の commit hash が記録されている
