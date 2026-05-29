# Stock Analyze System - 設計仕様書

**バージョン**: 1.0.0
**作成日**: 2026-03-21
**対象リポジトリ**: `<repo-root>`
**参考プロジェクト**: `<legacy-stock-analyzer-repo>`

---

## 1. プロジェクト概要

### 1.1 目的

米国株・日本株を対象とした包括的な財務分析プラットフォーム。SEC EDGAR、EDINET、Yahoo Finance、FMP（補完的）から財務データを自動収集し、バリュエーション計算、スクリーニング、PageIndex RAGによるLLM分析を行う。

参考プロジェクト（Stock_Analyzer）と同等の仕様を持つが、以下を改善目標とする：

- 全面async/await化
- Repository層の導入によるテスト容易性向上
- 既知バグ全20件の設計段階での解消
- TDD（テスト駆動開発）による品質保証
- PageIndex RAGへのLLM分析一本化

### 1.2 参考コード参照方針

実装にあたり参考プロジェクト（Stock_Analyzer）のコードを参照する場合、以下のプロセスを必須とする：

1. **各Phase開始時**に対応するStock_Analyzerのモジュールを精読
2. **潜在バグの洗い出し** — 既知バグ（要件定義書記載）に加え、コードレビューで未発見のバグを探索
3. **発見した問題を仕様に反映** — 新プロジェクトの設計で回避する
4. **テストケースを先に書く** — 潜在バグが再発しないことを保証するテストを含める（TDDの一環）

### 1.3 技術スタック

| カテゴリ | 技術 |
|---------|------|
| 言語 | Python 3.10+ |
| ORM/DB | SQLAlchemy 2.0+ (AsyncSession) / SQLite (WAL mode) / aiosqlite |
| HTTP | httpx 0.27+ (AsyncClient) |
| Web | FastAPI 0.115+ / Uvicorn / Jinja2 |
| フロントエンド | Tailwind CSS (CDN) / Alpine.js / HTMX / Chart.js |
| CLI | argparse (標準ライブラリ) |
| LLM | Ollama (ローカル推論) / litellm (マルチプロバイダー) |
| RAG | PageIndex (vendoring) / weasyprint (HTML→PDF) / pymupdf |
| データ | yfinance 0.2+, PyYAML |
| テスト | pytest 8.0+ / pytest-asyncio / pytest-httpx / pytest-cov |
| Lint | Ruff (line-length=100, target=py310) |
| 環境管理 | Nix (flake.nix) + pyproject.toml |

### 1.4 インターフェース構成

2つのインターフェース（CLI / Web）がサービス層を共有する設計。Discord Botはスコープ外。

```
┌──────────┐  ┌──────────┐
│  CLI     │  │   Web    │
│(argparse)│  │(FastAPI) │
└────┬─────┘  └────┬─────┘
     │             │
     └──────┬──────┘
            │
   ┌────────────────────────────────────┐
   │          Services Layer           │
   │            (async)                │
   │                                    │
   │  ┌─────────────┐ ┌────────────┐  │
   │  │ Domain      │ │ Sync/Orch  │  │
   │  │ Services    │ │ Services   │  │
   │  │(pure logic) │ │(bridging)  │  │
   │  └──────┬──────┘ └──┬────┬────┘  │
   └─────────┼───────────┼────┼───────┘
             │           │    │
   ┌─────────┴────┐     │    │
   │ Repositories │     │    │
   │ (async CRUD) │     │    │
   └───────┬──────┘     │    │
           │            │    │
   ┌───────┼────────────┼────┘
   │       │            │
┌──┴──┐ ┌──┴──┐ ┌───┴───┐
│Model│ │Metr.│ │Inges- │
│(ORM)│ │(Pure│ │tion   │
└─────┘ └─────┘ └───────┘
```

---

## 2. プロジェクト構成

### 2.1 ディレクトリ構造

```
Stock_Analyze_System/
├── flake.nix
├── pyproject.toml
├── config/
│   ├── settings.yaml.example
│   ├── us_gaap_mapping.yaml
│   ├── ifrs_mapping.yaml
│   └── edinet_taxonomy_mapping.yaml
├── data/                              # git管理外
│   ├── stock_analyze.db
│   ├── filings/
│   └── logs/
├── docs/
│   └── superpowers/specs/
├── src/stock_analyze_system/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py
│   ├── exceptions.py
│   ├── logging_config.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py                    # DeclarativeBase + AsyncEngine
│   │   ├── company.py
│   │   ├── financial_data.py
│   │   ├── valuation.py
│   │   ├── filing.py
│   │   ├── company_analysis.py
│   │   ├── watchlist.py
│   │   ├── analysis_target.py
│   │   ├── screening.py
│   │   ├── competitor_group.py
│   │   └── document_index.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py                    # BaseRepository (generic CRUD)
│   │   ├── company_repo.py
│   │   ├── financial_repo.py
│   │   ├── valuation_repo.py
│   │   ├── filing_repo.py
│   │   ├── analysis_repo.py
│   │   ├── watchlist_repo.py
│   │   ├── screening_repo.py
│   │   ├── target_repo.py
│   │   └── document_index_repo.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── company_service.py
│   │   ├── financial_service.py
│   │   ├── financial_sync.py
│   │   ├── valuation_service.py
│   │   ├── filing_service.py
│   │   ├── filing_sync.py
│   │   ├── watchlist_service.py
│   │   ├── analysis_target_service.py
│   │   ├── screening_service.py
│   │   ├── screening_universe.py
│   │   ├── job_service.py
│   │   ├── metrics.py                 # 純粋関数（同期）
│   │   ├── pdf_converter.py
│   │   ├── pageindex_service.py
│   │   └── rag_service.py
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── base.py                    # AsyncRateLimiter + BaseClient
│   │   ├── sec_edgar.py
│   │   ├── sec_xbrl_parser.py
│   │   ├── edinet.py
│   │   ├── edinet_xbrl_parser.py
│   │   ├── yahoo_finance.py
│   │   └── fmp.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── company.py
│   │   ├── financial.py
│   │   ├── valuation.py
│   │   ├── filings.py
│   │   ├── rag.py
│   │   ├── jobs.py
│   │   ├── screen.py
│   │   ├── watchlist.py
│   │   ├── target.py
│   │   ├── serve.py
│   │   ├── helpers.py
│   │   └── formatters.py
│   ├── web/
│   │   ├── __init__.py
│   │   ├── app.py
│   │   ├── auth.py
│   │   ├── dependencies.py
│   │   ├── routes/
│   │   │   ├── dashboard.py
│   │   │   ├── stocks.py
│   │   │   ├── watchlists.py
│   │   │   ├── jobs.py
│   │   │   ├── screening.py
│   │   │   ├── targets.py
│   │   │   ├── rag.py
│   │   │   └── api.py
│   │   ├── static/
│   │   └── templates/
│   ├── shared/
│   │   └── formatters.py
│   └── vendor/
│       └── pageindex/                 # vendoring
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── repositories/
    │   ├── services/
    │   ├── ingestion/
    │   ├── cli/
    │   └── web/
    └── integration/
```

---

## 3. 基盤層の設計

### 3.1 設定管理 (`config.py`)

設定ロード階層:
1. `config/settings.yaml` をベースにロード
2. `.env` ファイルから環境変数を読み込み（軽量自前実装）
3. 環境変数でシークレットを上書き

**設定データクラス:**

```python
@dataclass
class AppConfig:
    database: DatabaseConfig
    sec_edgar: SecEdgarConfig
    edinet: EdinetConfig
    fmp: FmpConfig
    yahoo_finance: YahooFinanceConfig
    llm: LlmConfig
    filings: FilingsConfig
    logging: LoggingConfig
    web: WebConfig
    pageindex: PageIndexConfig
```

**環境変数マッピング:**

| 環境変数 | 設定フィールド |
|---------|---------------|
| `SEC_EDGAR_EMAIL` | `sec_edgar.email` |
| `EDINET_API_KEY` | `edinet.api_key` |
| `FMP_API_KEY` | `fmp.api_key` |
| `WEB_PASSWORD` | `web.password` |
| `WEB_SESSION_SECRET` | `web.session_secret` |
| `PAGEINDEX_API_KEY` | `pageindex.api_key` |
| `OLLAMA_API_BASE` | litellm用（Ollama URL） |

**既存バグ修正:**
- 設定ファイルの相対パス依存 → パッケージルート基準で解決
- LLMモデル名不一致 → デフォルト値を `settings.yaml.example` と統一
- SEC EDGARメールの環境変数上書き未対応 → `SEC_EDGAR_EMAIL` 追加

### 3.2 データベース基盤 (`models/base.py`)

```python
from sqlalchemy.ext.asyncio import (
    create_async_engine, async_sessionmaker, AsyncSession, AsyncAttrs,
)
from sqlalchemy.orm import DeclarativeBase

class Base(AsyncAttrs, DeclarativeBase):
    pass

async def create_db_engine(db_path: str) -> AsyncEngine:
    """WALモード + 外部キー有効化 + async (aiosqlite)"""

@asynccontextmanager
async def get_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """セッション管理（コミット/ロールバック）"""
```

### 3.3 共有フォーマッタ (`shared/formatters.py`)

既存と同一の純粋関数群: `fmt_number`, `fmt_pct`, `fmt_large`, `fmt_ratio`

### 3.4 テスト基盤 (`tests/conftest.py`)

- `pytest-asyncio` + `asyncio_mode = "auto"`
- インメモリAsyncSession（`sqlite+aiosqlite:///:memory:`）
- 各テストでロールバック
- `mock_config` fixture

---

## 4. データベースモデル

### 4.1 テーブル一覧

既存Stock_Analyzerと同一スキーマ + `document_indices` を新規追加。

| テーブル | 用途 |
|---------|------|
| `companies` | 企業マスタ (US_{ticker} / JP_{code}) |
| `financial_data` | 財務データ (annual/quarterly) |
| `valuations` | バリュエーション履歴 (月次) |
| `filings` | 有価証券報告書メタデータ |
| `company_analyses` | LLM/RAG分析結果 |
| `watchlists` | ウォッチリスト |
| `watchlist_items` | ウォッチリストアイテム |
| `analysis_targets` | 分析対象企業 |
| `screening_cache` | Yahoo Finance enrichmentキャッシュ |
| `competitor_groups` / `_members` | 競合企業グループ |
| `document_indices` | PageIndexツリーインデックス (**NEW**) |

### 4.2 新規テーブル: `document_indices`

| カラム | 型 | NULL | 備考 |
|--------|-----|------|------|
| id | Integer | NO | PK |
| filing_id | Integer | NO | FK(filings.id), UNIQUE |
| company_id | String(20) | NO | FK(companies.id) |
| index_json | Text | NO | PageIndex生成のツリーJSON |
| model_name | String(50) | NO | インデックス生成に使用したモデル |
| page_count | Integer | NO | PDF総ページ数 |
| node_count | Integer | NO | ツリーノード数 |
| created_at | DateTime | NO | server_default |
| last_queried_at | DateTime | YES | 最終クエリ日時 |

### 4.3 マイグレーション方針

初期は `Base.metadata.create_all()` でテーブル作成。スキーマ変更が頻繁になった段階でAlembic導入を検討。

---

## 5. データ取得層 (Ingestion)

### 5.1 共通基盤 (`ingestion/base.py`)

```python
class AsyncRateLimiter:
    """asyncio.sleep ベースのトークンバケットレートリミッター"""
    def __init__(self, rate: float, interval: float = 1.0)
    async def acquire(self) -> None

class BaseClient:
    """全APIクライアントの基底クラス"""
    def __init__(self, rate_limiter: AsyncRateLimiter)
    # httpx.AsyncClient セッション再利用
    # 共通GET: リトライ + 指数バックオフ (429/503: 2s→4s→8s→最大60s)
    async def _get(self, url: str, **kwargs) -> httpx.Response
    async def close(self) -> None
    async def __aenter__(self) / __aexit__
```

### 5.2 SEC EDGAR (`ingestion/sec_edgar.py`)

```python
class SecEdgarClient(BaseClient):
    # User-Agent: "Stock-Analyze-System {email}"
    # レートリミット: 5 req/s (安全マージン)
    async def get_company_facts(self, cik: str) -> dict
    async def get_submissions(self, cik: str) -> dict  # ページネーション対応
    async def get_filing_html(self, url: str) -> str
    async def search_efts(self, query: str) -> dict
```

既存バグ修正: ファイリングページネーション未対応 → `filings.files` の追加ページも取得

### 5.3 SEC XBRL パーサー (`ingestion/sec_xbrl_parser.py`)

```python
class SecXbrlParser:
    """XBRL Company Facts → 正規化財務レコード（同期、I/O不要）"""
    def parse_company_facts(self, facts: dict, period_type: str) -> list[dict]
    def resolve_tag(self, facts, tag_candidates, ...) -> dict[str, float]
```

既存修正済みロジック継承:
- 全フォーム型への四半期期間フィルタ (duration <= 120日)
- 同一end_dateの最短期間優先
- `_merge_near_dates()` ±3日クラスタリング
- `_CORE_FIELDS` によるゴーストレコード防止

### 5.4 EDINET (`ingestion/edinet.py`, `edinet_xbrl_parser.py`)

```python
class EdinetClient(BaseClient):
    # レートリミット: 1 req/5s
    async def get_document_list(self, date: str) -> list[dict]
    async def download_xbrl_zip(self, doc_id: str, save_dir: Path) -> Path
    async def search_company_filings(self, edinet_code: str, ...) -> list[dict]
```

既存バグ修正:
- APIキー未設定時の無通知スキップ → WARNING ログ + スキップ理由を返却
- XBRLパーサーのコンテキスト未考慮 → 期間・連結/単体を判別、連結優先

### 5.5 Yahoo Finance (`ingestion/yahoo_finance.py`)

```python
class YahooFinanceClient(BaseClient):
    # レートリミット: 2 req/s, バッチサイズ20
    # yfinance は同期API → asyncio.to_thread() でラップ
    async def get_stock_price(self, ticker: str) -> dict
    async def get_price_history(self, ticker: str, period: str) -> list[dict]
    async def get_screening_info(self, ticker: str) -> dict
    async def get_quarterly_financials(self, ticker: str) -> list[dict]
```

### 5.6 FMP (`ingestion/fmp.py`)

```python
class FmpClient(BaseClient):
    # 無料プラン: 250 req/day, 5 req/s
    # 補完的データソースとして活用
    async def get_financial_statements(self, ticker: str) -> dict
    async def get_company_profile(self, ticker: str) -> dict
    async def get_stock_news(self, ticker: str, limit: int = 10) -> list[dict]
    async def is_available(self) -> bool
```

---

## 6. Repository層

### 6.1 BaseRepository

```python
class BaseRepository[T]:
    def __init__(self, session: AsyncSession, model: type[T])
    async def get_by_id(self, id: Any) -> T | None
    async def list_all(self, **filters) -> list[T]
    async def upsert(self, filters: dict, data: dict, label: str = "") -> T
    async def delete(self, id: Any) -> bool
    async def count(self, **filters) -> int
```

### 6.2 ドメイン固有リポジトリ

**CompanyRepository:**
- `find_by_identifier(query)` — ticker/security_code/company_id いずれでも検索
- `search(query, limit)` — 部分一致検索
- `list_by_market(market)` — 市場別一覧

**FinancialRepository:**
- `get_timeseries(company_id, period_type, years)` — 時系列取得
- `get_latest(company_id, period_type)` — 最新レコード
- `bulk_upsert(company_id, records)` — 一括upsert

**ValuationRepository:**
- `get_history(company_id, years)` — 履歴取得
- `get_latest(company_id)` — 最新
- `bulk_upsert(company_id, records)` — 一括upsert

**FilingRepository:**
- `get_latest_filing(company_id, filing_type)` — 最新ファイリング
- `list_filings(company_id)` — 一覧
- `find_by_accession(accession_no)` / `find_by_doc_id(doc_id)` — 個別検索

**AnalysisRepository:**
- `get_analyses(company_id, filing_id)` — 分析結果一覧
- `get_by_type(company_id, filing_id, analysis_type)` — タイプ別取得

**WatchlistRepository:**
- `get_by_name(name)` — 名前検索
- `list_items(watchlist_id)` — アイテム一覧
- `find_item(watchlist_id, company_id)` — アイテム検索

**ScreeningRepository:**
- `get_cache(company_id)` / `upsert_cache(company_id, data)` — キャッシュ管理
- `list_stale(hours)` — 古いキャッシュ一覧

**TargetRepository:**
- `list_targets()` / `find_by_company(company_id)` / `bulk_add(records)`

**DocumentIndexRepository:**
- `get_by_filing(filing_id)` / `save_index(filing_id, company_id, data)`

### 6.3 サービス層との関係

サービスはリポジトリをコンストラクタで受け取る（DI）。テスト時はAsyncMockで差し替え。

---

## 7. サービス層

### 7.1 CompanyService

```python
class CompanyService:
    def __init__(self, company_repo: CompanyRepository)
    async def register_company(self, data: dict) -> Company
    async def get_company(self, company_id: str) -> Company | None
    async def search_companies(self, query: str, limit: int = 20) -> list[Company]
    async def find_by_identifier(self, query: str) -> Company | None
    @staticmethod
    def build_company_id(ticker, security_code, market) -> str
```

既存バグ修正: 市場分類ロジック → 不明な市場はエラー

### 7.2 FinancialService

```python
class FinancialService:
    def __init__(self, financial_repo: FinancialRepository)
    async def upsert_financial_data(self, company_id: str, data: dict) -> FinancialData
    async def get_timeseries(self, company_id, period_type, years=10) -> list[FinancialData]
    async def compute_metrics(self, fd: FinancialData) -> dict
    async def compute_timeseries_metrics(self, records: list[FinancialData]) -> list[dict]
```

### 7.3 FinancialSyncService

```python
class FinancialSyncService:
    def __init__(self, financial_repo, sec_client, edinet_client, yahoo_client, fmp_client)
    async def run_financial_update(self, config, company_id) -> SyncResult
    # データフロー: SEC/EDINET → パース → FCF導出 → upsert → Yahoo FB → FMP補完 → Q4導出
```

既存バグ修正: `financials_count` を正しく集計

> **注:** `FinancialSyncService`, `FilingSyncService`, `JobService`, `ScreeningService` は
> Repository層とIngestion層の両方に依存する「Sync/Orchestration」サービス。
> ドメインサービス（CompanyService等）とは異なり、外部APIとDBの橋渡しを担う。
> アーキテクチャ図のセクション1.4を参照。

> **注:** 既存の `services/upsert.py` (`generic_upsert` 関数) は `BaseRepository.upsert()` に統合されたため、
> 新プロジェクトでは作成しない。

### 7.4 ValuationService

```python
class ValuationService:
    def __init__(self, valuation_repo: ValuationRepository)
    async def upsert_valuation(self, company_id, data) -> Valuation
    async def get_history(self, company_id, years=10) -> list[Valuation]
    async def compute_per_range(self, valuations) -> dict
    async def compare_valuations(self, company_ids) -> list[dict]
    async def compute_group_deviation(self, comparisons) -> list[dict]  # 新リスト返却
    async def build_chart_data(self, valuations) -> dict
```

### 7.5 FilingService / FilingSyncService

```python
class FilingService:
    def __init__(self, filing_repo: FilingRepository)
    async def upsert_filing / get_latest_filing / list_filings

class FilingSyncService:
    def __init__(self, filing_repo, sec_client, edinet_client)
    async def run_filing_update(self, config, company_id) -> SyncResult
```

### 7.6 WatchlistService

```python
class WatchlistService:
    def __init__(self, watchlist_repo: WatchlistRepository)
    async def create_watchlist / list_watchlists / get_watchlist
    async def add_item / remove_item / update_item
```

### 7.7 AnalysisTargetService

```python
class AnalysisTargetService:
    def __init__(self, target_repo: TargetRepository)
    async def add_target / remove_target / list_targets / add_from_screening
```

### 7.8 ScreeningService

```python
class ScreeningService:
    def __init__(self, screening_repo, yahoo_client, fmp_client)
    async def run_screen(self, filters, sector, exchange, sort_by, limit, descending) -> ScreeningResult
    @staticmethod
    def parse_condition(value_str) -> tuple[str, float]
    async def _enrich_fcf_yield(self, results, fcf_filter) -> list[dict]
    # asyncio.gather() で並列enrichment
```

既存バグ修正:
- 境界値マッピング → 境界値を含むように修正
- FCF enrichment → async並列化

### 7.9 ScreeningUniverseService

```python
class ScreeningUniverseService:
    def __init__(self, company_repo, screening_repo, yahoo_client)
    async def refresh_universe(self) -> int
    async def enrich_with_yahoo(self, limit=100, skip_recent_hours=24) -> int
    # asyncio.Semaphore(8) で同時リクエスト制御
```

既存バグ修正:
- 空market → `"UNKNOWN"` を設定
- 逐次処理 → async並列化

### 7.10 JobService

```python
@dataclass
class SyncResult:
    company_id: str
    financials_count: int
    filings_count: int
    valuations_count: int
    errors: list[str]
    skipped_reasons: list[str]

@dataclass
class DailyUpdateResult:
    market: str
    total_companies: int
    results: list[SyncResult]
    started_at: datetime
    finished_at: datetime

class JobService:
    def __init__(self, financial_sync, filing_sync, valuation_service, yahoo_client, fmp_client)
    async def sync_company(self, config, company_id) -> SyncResult
    async def run_daily_update(self, config, market) -> DailyUpdateResult
```

### 7.11 metrics.py

25個の純粋関数（同期）。`float | None` を返す安全な設計。変更なし。

---

## 8. LLM分析 + PageIndex RAG

### 8.1 アーキテクチャ

```
SEC/EDINET Filing (HTML)
    ↓
weasyprint (HTML → PDF変換)
    ↓
PageIndex (PDF → ツリーインデックス構築)
    ↓ litellm経由 Ollama
┌───────────────────────────────────────┐
│         RAG Engine                     │
│  ├─ 定型分析（4タイプ）                  │
│  │   business_summary / risk_factors   │
│  │   mda / competitors                │
│  └─ 自由質問（ユーザーQ&A）              │
└───────────────────────────────────────┘
    ↓
構造化JSON → DB保存
```

既存の正規表現セクション抽出 (`llm_extraction.py`) とOllama直接呼び出し (`llm_service.py`) は廃止。
全LLM呼び出しをlitellm経由に統一。

> **注: 要件定義書との差異について**
> 参考プロジェクトの要件定義書（セクション13.3.6）では既存のセクション抽出+Ollama分析を維持しつつPageIndex RAGを追加する併存方式を記述しているが、本プロジェクトではブレインストーミングで合意した通りRAG一本化を採用する。正規表現ベースのセクション抽出は精度に限界があり、PageIndex RAGの推論ベース探索で完全に代替可能なため。

### 8.2 PdfConverter (`services/pdf_converter.py`)

```python
class PdfConverter:
    async def convert(self, html_path: Path, output_path: Path) -> Path
        # weasyprint (asyncio.to_thread)
    async def get_or_convert(self, filing: Filing, config: FilingsConfig) -> Path
        # キャッシュ付き変換
```

**PDF保存パス規約:**
```
data/filings/{source}/{company_id}/{fiscal_year}/{period_type}/{filing_type}/{accession_or_doc_id}/
  raw/           # 取得したHTML原本（既存）
  converted.pdf  # weasyprint変換後のPDF（NEW）
  analysis/      # RAG分析結果JSON
```

- `converted.pdf` が既に存在する場合はスキップ（冪等）
- 変換失敗時: `ParsingError` を送出し、ログにHTML URLを記録。該当ファイリングのRAG分析はスキップされるが他のファイリング処理には影響しない
- 既存HTMLファイリングのバッチ変換: `stock-analyze rag index --all` で未変換ファイリングを一括変換可能

### 8.3 PageIndexService (`services/pageindex_service.py`)

```python
class PageIndexService:
    def __init__(self, document_index_repo, pdf_converter, config: PageIndexConfig)
    async def build_index(self, pdf_path: Path) -> dict
    async def get_or_create_index(self, filing, config) -> dict
    async def query(self, index, question, pdf_path) -> QueryResult

@dataclass
class QueryResult:
    answer: str
    source_pages: list[int]
    source_sections: list[str]
    confidence: float
    model: str
```

### 8.4 RagService (`services/rag_service.py`)

```python
class RagService:
    def __init__(self, pageindex_service, analysis_repo, filing_repo)

    # 定型分析
    async def run_full_analysis(self, config, company_id, filing_id=None) -> list[AnalysisResult]
    async def run_analysis(self, config, company_id, filing_id, analysis_type) -> AnalysisResult

    # 自由質問
    async def ask_question(self, config, company_id, filing_id, question) -> QueryResult
    async def ask_questions(self, config, company_id, filing_id, questions) -> list[QueryResult]

@dataclass
class AnalysisResult:
    analysis_type: str
    result_json: dict
    query_result: QueryResult
```

### 8.5 定型分析プロンプト

4タイプ: `business_summary`, `risk_factors`, `mda`, `competitors`
各プロンプトは構造化JSON出力を指示（日本語）。

### 8.6 litellm連携

- Ollama使用時: `model = "ollama/hf.co/unsloth/Qwen3.5-27B-GGUF:Q8_0"`
- LM Studio使用時: `model = "lm_studio/qwen3.5-27b"` + `lm_studio_base_url`
- 環境変数: `OLLAMA_API_BASE=http://localhost:11434`

**PageIndexConfig のLLM設定継承:**
`PageIndexConfig` の `model`, `backend` が未設定（空文字）の場合、`LlmConfig` の対応する値をフォールバックとして使用する。ユーザーが `LlmConfig` のみ設定すれば、PageIndexも同じモデルを使用する。明示的に設定すればPageIndex固有のモデルを指定可能。

### 8.7 GPU メモリ拡張 (nvidia_greenboost)

本プロジェクトは RTX 4090 (VRAM 24GB) + 92GB DDR 環境で Qwen3.5-27B を動作させるため、[nvidia_greenboost](https://gitlab.com/IsolatedOctopi/nvidia_greenboost) を前提とする。

**なぜ必要か:**
モデル重みだけでなくKVキャッシュ（長文コンテキスト処理時 8-16GB+）とアクティベーションバッファ（1-2GB）を加えると、Q8_0でも合計40-47GB、UD-Q8_K_XLでは47-54GBが必要。VRAM単体では動作不可。

**メモリ階層:**

| Tier | ソース | 帯域 | 用途 |
|------|--------|------|------|
| T1 | GPU VRAM 24GB | ~1,008 GB/s | ホットレイヤー・アクティブ計算 |
| T2 | System DDR pool | ~32 GB/s (PCIe 4.0) | コールドウェイト・KVキャッシュ |
| T3 | NVMe swap | ~1.8 GB/s | 安全弁（通常未使用） |

**導入時の必須対策:**

1. **Swap拡張**: 2GB → 32GB（NVMe上に作成。GreenBoost T3としても機能）
2. **Ollama設定**: `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`（T2帯域競合防止）
3. **OOM保護**: Ollama/Pythonプロセスの `oom_score_adj` 設定（-1000/-500）

**コード側の必須対策（本Phase実装時）:**

4. `LlmConfig.request_timeout` 追加（300秒以上。T2アクセスによるレイテンシ増大に対応）
5. PageIndex構築の進捗表示（1文書あたり10-25分かかる可能性。CLIおよびWeb UIで進捗フィードバック必須）
6. `/sys/class/greenboost/greenboost/pool_info` をヘルスチェックAPIで公開（Web UI Phase 7）

**推奨対策:**

7. 導入前後で `rag index` / `rag analyze` の処理時間をベンチマーク計測
8. GreenBoost watchdogカーネルスレッドのログ監視

**ブートパラメータ変更の影響:**
- `transparent_hugepage=always`: SQLite WAL+小規模DBなら軽微
- `vm.swappiness=10`: swap拡張(32GB)が前提
- CPU governor → performance: 推論性能に好影響

### 8.8 モデル切替アーキテクチャ

Qwen3.5-27B-GGUF を2種の量子化レベルで提供し、用途に応じてUI/CLI から切替可能とする:

| モデル | サイズ | 重み+KV+バッファ | T2使用量 | 用途 |
|--------|--------|-----------------|----------|------|
| Q8_0 | 28.6 GB | ~40-47 GB | ~16-23 GB | バッチ処理・インデックス構築（速度優先） |
| UD-Q8_K_XL | 35.5 GB | ~47-54 GB | ~23-30 GB | 対話的Q&A・重要分析（精度優先） |

**LlmConfig 拡張:**

```python
@dataclass
class LlmConfig:
    backend: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "ollama/hf.co/unsloth/Qwen3.5-27B-GGUF:Q8_0"                # 高速モード（デフォルト）
    model_quality: str = "ollama/hf.co/unsloth/Qwen3.5-27B-GGUF:UD-Q8_K_XL"  # 高精度モード
    temperature: float = 0.1
    max_tokens: int = 32768
    request_timeout: int = 300  # GreenBoost T2レイテンシ対応
```

**用途別モデル自動選択:**

| 処理 | 使用モデル | 理由 |
|------|-----------|------|
| `rag index` (PageIndex構築) | `model` (Q8_0) | 数十〜数百回のLLM呼び出し。速度が律速 |
| `rag analyze` (定型分析バッチ) | `model` (Q8_0) | 複数分析タイプを逐次実行。速度優先 |
| `rag ask` (対話的Q&A) | `model_quality` (UD-Q8_K_XL) | 1-3回の呼び出し。精度が重要 |
| Web UI 分析表示 | `model_quality` (UD-Q8_K_XL) | ユーザー対面。品質優先 |

**CLI/Web UIでのモデル切替:**

```bash
# CLI: --quality フラグで高精度モデルを明示使用
stock-analyze rag ask US_AAPL "競合優位性は？" --quality

# CLI: デフォルトは用途に応じた自動選択
stock-analyze rag index US_AAPL          # → Q8_0（自動）
stock-analyze rag analyze US_AAPL        # → Q8_0（自動）
stock-analyze rag ask US_AAPL "..."      # → UD-Q8_K_XL（自動）

# CLI: 明示的モデル指定（上級者向け）
stock-analyze rag ask US_AAPL "..." --model "ollama/hf.co/unsloth/Qwen3.5-27B-GGUF:Q8_0"
```

**RagService での実装:**

```python
class RagService:
    def _resolve_model(self, config: AppConfig, quality: bool = False) -> str:
        """用途に応じたモデルを解決"""
        if quality and config.llm.model_quality:
            return config.llm.model_quality
        return config.llm.model

    async def build_index(self, config, company_id, filing_id):
        model = self._resolve_model(config, quality=False)  # 速度優先
        ...

    async def ask_question(self, config, company_id, filing_id, question):
        model = self._resolve_model(config, quality=True)   # 精度優先
        ...
```

**モデル切替時の注意:**
- Ollamaは `OLLAMA_MAX_LOADED_MODELS=1` のため、モデル切替時にアンロード→ロードが発生（10-30秒）
- 同一セッションで頻繁な切替は避ける設計とする（バッチ処理はQ8_0で一括、対話はUD-Q8_K_XLで一括）
- `OLLAMA_KEEP_ALIVE=30m` で不要なアンロードを防止

### 8.9 PageIndex LLM呼び出しの同時実行制御

インデックス構築は1文書あたり数十回のLLM呼び出しが発生するため、ローカルGPUリソースの競合を防止する:

- `asyncio.Semaphore(1)` でインデックス構築を逐次化（同時に1文書のみ）
- RAGクエリ（`query()`）は軽量なため同時実行可（制限なし）
- バッチインデックス構築（`rag index --all`）は逐次処理
- **daily update（JobService）と RAG を同時実行しない**: メモリ競合リスク。CLI/Web UIで排他制御を設ける

---

## 9. CLIインターフェース

### 9.1 エントリポイント

```python
# __main__.py: asyncio.run(main())
# cli/app.py: argparse + 各モジュールのサブコマンド登録
```

### 9.2 サブコマンド一覧

| サブコマンド | ファイル | 機能 |
|-------------|---------|------|
| `company register/search/show` | cli/company.py | 企業管理 |
| `financial show/metrics` | cli/financial.py | 財務データ |
| `valuation show/compare/range/deviation` | cli/valuation.py | バリュエーション |
| `filings list/download` | cli/filings.py | ファイリング |
| `rag analyze/ask/index/status/health/show` | cli/rag.py | RAG分析 (**NEW**) |
| `jobs sync/daily` | cli/jobs.py | ジョブ管理 |
| `screen run/add-targets` | cli/screen.py | スクリーニング |
| `watchlist create/list/show/add/remove` | cli/watchlist.py | ウォッチリスト |
| `target list/add/remove` | cli/target.py | 分析ターゲット |
| `serve` | cli/serve.py | Webサーバー起動 |

**既存から削除したコマンド:**
- `filings extract` → PageIndex RAGに置き換え（手動セクション抽出不要）
- `llm analyze/show/health` → `rag` サブコマンドに統合
- `bot` → Discord Botスコープ外

### 9.3 既存バグ修正

- `jobs --type` 未使用 → オプション削除
- `serve` ポート0問題 → `args.port is not None` チェック
- `valuation` 使用法の deviation 未記載 → argparse自動生成に委ねる
- `watchlist` ハンドラ署名不整合 → 全ハンドラ `async def handler(args, config)` に統一

### 9.4 共通ヘルパー

- `require_company()` / `require_latest_filing()` — エラー時 sys.exit(1)
- 全コマンド `--json` オプション対応（デフォルト: tabulateテーブル出力、`--json` 指定時: JSON辞書/配列を標準出力）

### 9.5 DI組み立て (`cli/helpers.py: setup_services`)

```python
async def setup_services(session: AsyncSession, config: AppConfig) -> ServiceContainer:
    """CLI/Web共通のリポジトリ・サービス依存グラフを組み立て"""
    # 1. API クライアント生成
    sec_client = SecEdgarClient(config.sec_edgar)
    edinet_client = EdinetClient(config.edinet)
    yahoo_client = YahooFinanceClient(config.yahoo_finance)
    fmp_client = FmpClient(config.fmp)

    # 2. リポジトリ生成
    company_repo = CompanyRepository(session, Company)
    financial_repo = FinancialRepository(session, FinancialData)
    valuation_repo = ValuationRepository(session, Valuation)
    filing_repo = FilingRepository(session, Filing)
    analysis_repo = AnalysisRepository(session, CompanyAnalysis)
    watchlist_repo = WatchlistRepository(session, Watchlist)
    screening_repo = ScreeningRepository(session, ScreeningCache)
    target_repo = TargetRepository(session, AnalysisTarget)
    doc_index_repo = DocumentIndexRepository(session, DocumentIndex)

    # 3. ドメインサービス生成
    company_service = CompanyService(company_repo)
    financial_service = FinancialService(financial_repo)
    valuation_service = ValuationService(valuation_repo)
    filing_service = FilingService(filing_repo)
    watchlist_service = WatchlistService(watchlist_repo)
    target_service = AnalysisTargetService(target_repo)

    # 4. Sync/Orchestrationサービス生成（Repository + Ingestion を橋渡し）
    financial_sync = FinancialSyncService(financial_repo, sec_client, edinet_client, yahoo_client, fmp_client)
    filing_sync = FilingSyncService(filing_repo, sec_client, edinet_client)
    screening_service = ScreeningService(screening_repo, yahoo_client, fmp_client)
    job_service = JobService(financial_sync, filing_sync, valuation_service, yahoo_client, fmp_client)

    # 5. RAGサービス生成
    pdf_converter = PdfConverter()
    pageindex_service = PageIndexService(doc_index_repo, pdf_converter, config.pageindex)
    rag_service = RagService(pageindex_service, analysis_repo, filing_repo)

    return ServiceContainer(
        company_service=company_service,
        financial_service=financial_service,
        valuation_service=valuation_service,
        filing_service=filing_service,
        watchlist_service=watchlist_service,
        target_service=target_service,
        screening_service=screening_service,
        job_service=job_service,
        rag_service=rag_service,
        financial_sync=financial_sync,
        filing_sync=filing_sync,
    )
```

Web層の `get_services()` (FastAPI Depends) もこの関数を内部で使用し、DI組み立てロジックを一元管理する。

---

## 10. Web UIインターフェース

### 10.1 アプリケーション構成

FastAPI + Jinja2テンプレート + SSR。HTMX で部分更新、Alpine.js でクライアントサイド状態管理、Chart.js でグラフ描画。

### 10.2 認証

セッションベース認証 (itsdangerous URLSafeTimedSerializer)。

既存バグ修正:
- セッションシークレット未設定 → アプリ起動をエラーで停止
- `require_auth()` デッドコード → 廃止、AuthMiddleware に一本化

### 10.3 依存性注入

```python
@dataclass
class ServiceContainer:
    company_service / financial_service / valuation_service / filing_service
    watchlist_service / target_service / screening_service / job_service / rag_service

async def get_services(session = Depends(get_session)) -> ServiceContainer
```

### 10.4 ルート一覧

| パス | メソッド | 機能 |
|-----|---------|------|
| `/` | GET | ダッシュボード |
| `/login`, `/logout` | GET/POST, GET | 認証 |
| `/stocks/search` | GET | 企業検索 (HTMX) |
| `/stocks/{company_id}` | GET | 企業詳細ページ |
| `/watchlists` 系 | GET/POST | ウォッチリスト管理 |
| `/jobs`, `/jobs/sync`, `/jobs/daily` | GET/POST | ジョブ管理 |
| `/screening` | GET/POST | スクリーニング |
| `/targets` 系 | GET/POST | ターゲット管理 |
| `/rag/{company_id}` | GET | RAG Q&Aページ (**NEW**) |
| `/api/stocks/{id}/valuations` | GET | バリュエーションJSON |
| `/api/stocks/{id}/financials/{period}` | GET | 財務データJSON |
| `/api/stocks/{id}/rag/ask` | POST | RAG質問 (**NEW**) |
| `/api/stocks/{id}/rag/index` | POST | インデックス構築 (**NEW**) |
| `/api/stocks/{id}/rag/analyses` | GET | 保存済み分析 (**NEW**) |

### 10.5 企業詳細ページ タブ構成

1. **財務** — 売上・利益推移グラフ + EPS折れ線 + 通期/四半期切替
2. **バリュエーション** — PER/PBR/PSR 個別折れ線グラフ
3. **指標** — 財務指標テーブル
4. **RAG分析** — 定型分析結果 + 自由質問Q&A (**統合**)
5. **ファイリング** — ファイリング一覧

### 10.6 既存バグ修正

- スクリーニング結果のCompany IDハードコード → サーバー側でID解決
- Tailwind動的クラス名 → 完全なクラス名を直接記述
- ナビゲーション活性化 → `startswith` プレフィックスマッチ（`/` は完全一致維持）

---

## 11. エラーハンドリング・ロギング

### 11.1 例外階層

```
StockAnalyzeError (基底)
├── ConfigError
├── IngestionError
│   ├── RateLimitError
│   ├── ApiConnectionError
│   └── ApiResponseError
├── ParsingError
├── LlmError
│   ├── LlmConnectionError
│   ├── LlmResponseError
│   └── IndexBuildError
├── NotFoundError
└── DuplicateError
```

### 11.2 レイヤー別方針

| レイヤー | 方針 |
|---------|------|
| Ingestion | BaseClientで指数バックオフリトライ。上限超過時にIngestionError |
| Repository | IntegrityError → DuplicateError。該当なしはNone返却 |
| Service | ビジネスルール違反は適切な例外。Ingestion例外はログ後伝播 |
| CLI | 全例外キャッチ → ユーザー向けメッセージ + sys.exit(1) |
| Web | FastAPI exception_handler で HTTPレスポンスに変換 |

### 11.3 ロギング

- ファイル出力: `data/logs/stock_analyze.log`
- モジュール別ログレベル設定
- API呼び出し: INFO、リトライ: WARNING、APIキー未設定: WARNING、エラー: ERROR + スタックトレース

---

## 12. テスト戦略

### 12.1 テストピラミッド

```
        ╱╲          統合テスト (E2E フロー)
       ╱  ╲
      ╱────╲        サービステスト (リポジトリモック)
     ╱      ╲
    ╱────────╲      ユニットテスト (純粋関数・パーサー・リポジトリ)
   ╱──────────╲
```

テスト数は実装進行に伴い決定する。具体的な目標はカバレッジ率（12.3節）で管理する。

### 12.2 TDDプロセス

各Phase: 参考コード精読 → 潜在バグ洗い出し → テストケース設計 → RED → GREEN → REFACTOR

### 12.3 カバレッジ目標

| レイヤー | 目標 |
|---------|------|
| repositories/ | 90%+ |
| services/ | 85%+ |
| ingestion/ | 80%+ |
| metrics.py | 100% |
| cli/ | 70%+ |
| web/ | 70%+ |
| **全体** | **80%+** |

### 12.4 既存テストカバレッジ不足の全解消

Yahoo Finance全メソッド、financial_service/valuation_service主要関数、LLM API、CLI統合テストを追加。

---

## 13. 環境構築・依存関係

### 13.1 pyproject.toml 主要依存

**ランタイム:**
sqlalchemy, aiosqlite, httpx, fastapi, uvicorn, jinja2, python-multipart, itsdangerous, yfinance, pyyaml, tabulate, litellm, pymupdf, weasyprint

**開発:**
pytest, pytest-asyncio, pytest-httpx, pytest-cov, ruff

### 13.2 PageIndex取り込み

vendoring方式: `src/stock_analyze_system/vendor/pageindex/` に配置。ローカルLLM対応パッチ適用可能。

### 13.3 日次バッチ (cron)

- 米国株: JST 6:00 `stock-analyze jobs daily --market us`
- 日本株: JST 17:00 `stock-analyze jobs daily --market jp`

---

## 14. ビルド順序

| Phase | サブプロジェクト | 内容 |
|-------|-----------------|------|
| 1 | 基盤層 | 設定, DB, Repository基盤, 例外, ロギング, 共通ユーティリティ |
| 2 | データ取得層 | SEC EDGAR, EDINET, Yahoo Finance, FMP クライアント + パーサー |
| 3 | サービス層 | 企業, 財務, バリュエーション, ファイリング, ウォッチリスト, ターゲット, ジョブ, metrics |
| 4 | CLI | 全サブコマンド |
| 5 | スクリーニング | ScreeningService, UniverseService |
| 6 | LLM/RAG | PdfConverter, PageIndexService, RagService, モデル切替 (Q8_0/UD-Q8_K_XL), GreenBoost前提設計 |
| 7 | Web UI | FastAPI, テンプレート, HTMX, Chart.js |

---

## 15. 修正する既知バグ一覧

| # | バグ | 修正方法 | Phase |
|---|------|---------|-------|
| 1 | スクリーニングCompany IDハードコード | サーバー側でID解決 | 7 |
| 2 | Tailwind動的クラス名 | 完全クラス名直接記述 | 7 |
| 3 | CLI jobs --type 未使用 | オプション削除 | 4 |
| 4 | financials_count 常に0 | SyncResult正しく集計 | 3 |
| 5 | screening境界値除外 | 境界値を含むマッピング | 5 |
| 6 | refresh_universe空market | "UNKNOWN"設定 | 5 |
| 7 | 市場分類ロジック不正 | 不明市場をエラー化 | 3 |
| 8 | セッションシークレット自動生成 | 未設定で起動エラー | 7 |
| 9 | ナビゲーション活性化 | startswithマッチ | 7 |
| 10 | EDINET APIキー無通知スキップ | WARNINGログ出力 | 2 |
| 11 | competitors到達不能 | RAG統合で全タイプ実行 | 6 |
| 12 | LLMモデル名不一致 | デフォルト値統一 | 1 |
| 13 | StockAnalyzerBotデッドコード | Bot未実装（スコープ外） | - |
| 14 | require_authデッドコード | 廃止 | 7 |
| 15 | serve ポート0問題 | is not Noneチェック | 4 |
| 16 | valuation使用法deviation未記載 | argparse自動生成 | 4 |
| 17 | watchlistハンドラ署名不整合 | 全ハンドラ統一 | 4 |
| 18 | filingページネーション未対応 | files追加ページ取得 | 2 |
| 19 | EDINET XBRLコンテキスト未考慮 | 期間・連結/単体判別 | 2 |
| 20 | SEC EDGARメール環境変数未対応 | SEC_EDGAR_EMAIL追加 | 1 |
