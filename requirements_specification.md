# Stock Analyzer 要件定義書

**バージョン**: 0.1.0
**最終更新**: 2026-03-21
**対象リポジトリ**: `<repo-root>`

---

## 1. プロジェクト概要

### 1.1 目的

米国株・日本株を対象とした包括的な財務分析プラットフォーム。SEC EDGAR、EDINET、Yahoo Financeから財務データを自動収集し、バリュエーション計算、スクリーニング、LLM分析を行う。

### 1.2 技術スタック

| カテゴリ | 技術 |
|---------|------|
| 言語 | Python 3.10+ |
| ORM/DB | SQLAlchemy 2.0+ / SQLite (WAL mode) |
| HTTP | httpx 0.27+ |
| Web | FastAPI 0.115+ / Uvicorn / Jinja2 |
| フロントエンド | Tailwind CSS (CDN) / Alpine.js / HTMX / Chart.js |
| CLI | argparse (標準ライブラリ) |
| Discord Bot | discord.py 2.3+ |
| LLM | Ollama (ローカル推論) |
| データ | yfinance 0.2+, PyYAML |
| テスト | pytest 8.0+ / pytest-httpx |
| Lint | Ruff (line-length=100, target=py310) |

### 1.3 インターフェース構成

3つのインターフェースがサービス層を共有する設計:

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│  CLI     │  │ Discord  │  │   Web    │
│(argparse)│  │  Bot     │  │(FastAPI) │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │             │
     └─────────────┼─────────────┘
                   │
          ┌────────┴────────┐
          │  Services Layer │
          └────────┬────────┘
                   │
     ┌─────────────┼─────────────┐
     │             │             │
┌────┴────┐  ┌────┴────┐  ┌────┴────┐
│Ingestion│  │ Models  │  │ Metrics │
│ Layer   │  │  (ORM)  │  │  (Pure) │
└─────────┘  └─────────┘  └─────────┘
```

### 1.4 コード規模

| カテゴリ | ファイル数 | 行数 |
|---------|-----------|------|
| ソースコード (Python) | 62 | ~12,148 |
| HTMLテンプレート | 14 | ~1,191 |
| テスト | 20 | ~3,500 |
| 設定ファイル (YAML) | 4 | ~100 |
| **テスト数** | — | **358** |

---

## 2. 設定管理

### 2.1 設定ファイル (`config/settings.yaml`)

```yaml
database:
  path: data/stock_analyzer.db
sec_edgar:
  email: "user@example.com"
  rate_limit_rps: 5
edinet:
  base_url: "https://api.edinet-fsa.go.jp/api/v2"
  rate_limit_interval: 5
fmp:
  api_key: ""
  rate_limit_rps: 5
  daily_limit: 250
yahoo_finance:
  rate_limit_rps: 2
  batch_size: 20
llm:
  backend: ollama
  base_url: "http://localhost:11434"
  model: "clore/gpt-oss-20b-Q8_0:latest"
  temperature: 0.1
  max_tokens: 32768
discord:
  command_prefix: "!"
filings:
  base_path: "data/filings"
logging:
  level: INFO
  file: "data/logs/stock_analyzer.log"
```

### 2.2 設定ロード階層 (`src/stock_analyzer/config.py`)

1. `config/settings.yaml` をベースにロード
2. `.env` ファイルから環境変数を読み込み（軽量自前実装、外部ライブラリ不要）
3. 環境変数でシークレットを上書き

**環境変数マッピング:**

| 環境変数 | 設定フィールド |
|---------|---------------|
| `EDINET_API_KEY` | `edinet.api_key` |
| `DISCORD_TOKEN` | `discord.token` |
| `DISCORD_WEBHOOK_URL` | `discord.webhook_url` |
| `DISCORD_USERNAME` | `discord.username` |
| `FMP_API_KEY` | `fmp.api_key` |
| `WEB_PASSWORD` | `web.password` |
| `WEB_SESSION_SECRET` | `web.session_secret` |

### 2.3 設定データクラス一覧

`AppConfig` (ルート) が以下のサブ設定を集約:

- `DatabaseConfig` — path
- `SecEdgarConfig` — email, rate_limit_rps
- `EdinetConfig` — base_url, rate_limit_interval, api_key
- `FmpConfig` — api_key, base_url, rate_limit_rps, daily_limit
- `YahooFinanceConfig` — rate_limit_rps, batch_size
- `LlmConfig` — backend, base_url, model, temperature, max_tokens
- `DiscordConfig` — command_prefix, token, webhook_url, username
- `FilingsConfig` — base_path
- `LoggingConfig` — level, file
- `WebConfig` — host(0.0.0.0), port(8501), password, session_secret

---

## 3. データベース設計

### 3.1 概要

SQLite + WAL mode + 外部キー有効化。`sqlalchemy.orm.DeclarativeBase` を使用。
DB初期化は `create_db_engine(db_path)` で行い、`get_session()` コンテキストマネージャでセッション管理。

### 3.2 テーブル定義

#### 3.2.1 companies

企業マスタ。米国株は `US_{ticker}`、日本株は `JP_{security_code}` のID体系。

| カラム | 型 | NULL | 備考 |
|--------|-----|------|------|
| id | String(20) | NO | PK, 例: "US_AAPL", "JP_7203" |
| ticker | String(10) | YES | 米国株ティッカー |
| security_code | String(10) | YES | 日本株証券コード |
| name | String(200) | NO | 企業名（英語） |
| name_ja | String(200) | YES | 企業名（日本語） |
| market | String(20) | NO | 市場コード |
| sector | String(100) | YES | セクター |
| accounting_standard | String(10) | NO | "US-GAAP" / "IFRS" / "JP-GAAP" |
| cik | String(20) | YES | SEC CIK番号 (10桁ゼロ埋め) |
| edinet_code | String(20) | YES | EDINET企業コード |
| created_at | DateTime | NO | server_default |
| updated_at | DateTime | NO | server_default, onupdate |

#### 3.2.2 financial_data

財務データ。通期 (annual) と四半期 (quarterly) の2種類。

| カラム | 型 | NULL | 備考 |
|--------|-----|------|------|
| id | Integer | NO | PK |
| company_id | String | NO | FK(companies.id) |
| accounting_standard | String(10) | NO | |
| currency | String(3) | NO | "USD", "JPY", "TWD" 等 |
| period_type | String(10) | NO | "annual" / "quarterly" |
| fiscal_year_end | Date | NO | 決算期末日 |
| revenue | Float | YES | 売上高 |
| operating_income | Float | YES | 営業利益 |
| net_income | Float | YES | 純利益 |
| total_assets | Float | YES | 総資産 |
| equity | Float | YES | 株主資本 |
| current_assets | Float | YES | 流動資産 |
| current_liabilities | Float | YES | 流動負債 |
| total_debt | Float | YES | 総負債 |
| cash | Float | YES | 現金及び現金同等物 |
| inventory | Float | YES | 棚卸資産 |
| cogs | Float | YES | 売上原価 |
| operating_cf | Float | YES | 営業キャッシュフロー |
| capex | Float | YES | 設備投資 |
| fcf | Float | YES | フリーキャッシュフロー |
| ebitda | Float | YES | EBITDA |
| eps | Float | YES | 1株当たり利益 |
| dps | Float | YES | 1株当たり配当 |
| tax_expense | Float | YES | 税金費用 |
| income_before_tax | Float | YES | 税引前利益 |
| shares_outstanding | Float | YES | 発行済株式数 |
| dividends_paid | Float | YES | 配当金支払額 |
| share_repurchases | Float | YES | 自社株買い額 |
| last_updated | DateTime | NO | server_default |

**一意制約**: (company_id, period_type, fiscal_year_end, accounting_standard)
**インデックス**: (company_id, fiscal_year_end)

#### 3.2.3 valuations

バリュエーション履歴（月次10年分）。

| カラム | 型 | NULL | 備考 |
|--------|-----|------|------|
| id | Integer | NO | PK |
| company_id | String | NO | FK(companies.id) |
| currency | String(3) | NO | |
| date | Date | NO | 評価日 |
| stock_price | Float | YES | 株価 |
| market_cap | Float | YES | 時価総額 |
| per | Float | YES | 株価収益率 |
| pbr | Float | YES | 株価純資産倍率 |
| ev_ebitda | Float | YES | EV/EBITDA |
| psr | Float | YES | 株価売上高倍率 |
| fcf_yield | Float | YES | FCF利回り |
| last_updated | DateTime | NO | server_default |

**一意制約**: (company_id, date)

#### 3.2.4 filings

有価証券報告書メタデータ。

| カラム | 型 | NULL | 備考 |
|--------|-----|------|------|
| id | Integer | NO | PK |
| company_id | String | NO | FK(companies.id) |
| source | String(10) | NO | "SEC" / "EDINET" |
| filing_type | String(10) | NO | "10-K", "10-Q", "20-F", "6-K" 等 |
| period_type | String(10) | NO | "annual" / "quarterly" |
| fiscal_year | Integer | NO | |
| period_end | Date | YES | |
| filed_at | Date | YES | |
| accession_no | String(30) | YES | SEC accession number (UNIQUE) |
| doc_id | String(30) | YES | EDINET doc_id (UNIQUE) |
| storage_path | Text | YES | ローカル保存パス |
| content_hash | String(64) | YES | コンテンツハッシュ |
| last_updated | DateTime | NO | server_default |

#### 3.2.5 company_analyses

LLM分析結果。

| カラム | 型 | NULL | 備考 |
|--------|-----|------|------|
| id | Integer | NO | PK |
| company_id | String | NO | FK(companies.id) |
| filing_id | Integer | NO | FK(filings.id) |
| analysis_type | String(30) | NO | "business_summary", "risk_factors", "mda", "competitors" |
| result_json | Text | NO | JSON文字列 |
| model_name | String(50) | NO | LLMモデル名 |
| created_at | DateTime | NO | server_default |

**一意制約**: (company_id, filing_id, analysis_type)

#### 3.2.6 watchlists / watchlist_items

ウォッチリスト管理。

**watchlists**: id, name(UNIQUE), description, created_at
**watchlist_items**: id, watchlist_id(FK), company_id(FK), status(default="monitoring"), investment_thesis, tags, added_at

**一意制約**: (watchlist_id, company_id)

#### 3.2.7 analysis_targets

分析対象企業。スクリーニング結果から追加可能。

| カラム | 型 | NULL | 備考 |
|--------|-----|------|------|
| id | Integer | NO | PK |
| company_id | String | NO | FK(companies.id), UNIQUE |
| source | String(20) | NO | default="manual" |
| criteria | Text | YES | スクリーニング条件等 |
| added_at | DateTime | NO | server_default |

#### 3.2.8 screening_cache

Yahoo Finance enrichmentデータのキャッシュ。

company_id(PK/FK), updated_at, stock_price, market_cap, trailing_per, eps, forward_per, pbr, psr, ev_ebitda, dividend_yield, roe, operating_margin, net_margin, revenue_growth, earnings_growth, de_ratio, peg_ratio, fcf_yield, sector, industry, exchange, beta, volume, most_recent_quarter, last_fiscal_year_end, trailing_eps_date

#### 3.2.9 competitor_groups / competitor_group_members

競合企業グループ管理。

**competitor_groups**: id, name, accounting_standard, created_at
**competitor_group_members**: id, group_id(FK), company_id(FK)

---

## 4. データ取得層 (Ingestion)

### 4.1 共通基盤 (`ingestion/base.py`)

`RateLimiter` クラス: `time.sleep()` ベースのレートリミッタ。各APIクライアントが使用。

### 4.2 SEC EDGAR (`ingestion/sec_edgar.py`)

**クラス**: `SecEdgarClient`

| メソッド | 機能 | API URL |
|---------|------|---------|
| `get_company_facts(cik)` | XBRL Company Facts取得 | `data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` |
| `get_submissions(cik)` | ファイリング一覧取得 | `data.sec.gov/submissions/CIK{cik}.json` |
| `get_filing_html(url)` | 10-K/10-Q HTML取得 | 各ファイリングURL |
| `search_efts(query)` | EFTS全文検索 | `efts.sec.gov/LATEST/search-index` |

**レートリミット**: 10 req/sec (SEC制限)
**User-Agent**: `Stock-Analyzer {email}` (SEC要件)

### 4.3 SEC XBRL パーサー (`ingestion/sec_xbrl_parser.py`)

**クラス**: `SecXbrlParser`

**主要メソッド**:
- `parse_company_facts(facts_json, period_type)` → `list[dict]`
- `resolve_tag(facts, tag_candidates, unit, forms, ...)` → `dict[str, float]`

**タクソノミー自動検出**: `us-gaap` と `ifrs-full` をタグ数で判別
**通貨検出**: IFRS企業の場合、Revenue/Assets/ProfitLossタグから非USD通貨を検出

**タグマッピングファイル**:
- `config/us_gaap_mapping.yaml` — 22フィールド × 各1-3候補タグ
- `config/ifrs_mapping.yaml` — IFRS対応マッピング

**期間フィルタリング**:
- Annual: duration >= 300日
- Quarterly: duration <= 120日 (全フォーム型に適用)

**重要なロジック**:
- **最短期間優先**: 同一end_dateに複数エントリ（累積YTD + スタンドアロン四半期）がある場合、最短期間を優先。10-QのYTD累積値の誤取り込みを防止。
- **近接日付マージ** (`_merge_near_dates`): ±3日以内の日付をクラスタリングし、最もデータが多い日付を正規化。SEC XBRLの概念間で微妙に異なるend_dateを統一。
- **ゴーストレコード防止** (`_CORE_FIELDS`): revenue, operating_income, net_income, total_assets, equity, ebitda, operating_cf, epsのいずれかにデータがないレコードは出力しない。配当支払日など非決算日のエントリによるゴーストレコードを防止。
- **ヘルパー** (`_days_between`): ISO日付文字列間の日数計算。パース失敗時は `_DURATION_UNKNOWN`(99999) を返す。

**フォームマッピング**:
```python
_FORM_MAP = {
    "annual": [
        {"form": "10-K", "fp": "FY"},
        {"form": "20-F", "fp": "FY"},
    ],
    "quarterly": [
        {"form": "10-Q", "fp": None},   # Q1, Q2, Q3
        {"form": "6-K", "fp": None},     # 外国企業
        {"form": "10-K", "fp": None},    # Q4 (年次報告書に埋め込み)
        {"form": "20-F", "fp": None},
    ],
}
```

### 4.4 EDINET (`ingestion/edinet.py`, `edinet_xbrl_parser.py`)

日本株向け。EDINET API v2を使用。
- `EdinetClient`: 書類一覧取得、XBRL ZIPダウンロード
- `EdinetXbrlParser`: EDINET XBRL → 正規化財務レコード
- タクソノミーマッピング: `config/edinet_taxonomy_mapping.yaml`

### 4.5 Yahoo Finance (`ingestion/yahoo_finance.py`)

**クラス**: `YahooFinanceClient`

| メソッド | 機能 |
|---------|------|
| `get_stock_price(ticker)` | 現在株価・時価総額・通貨取得 |
| `get_price_history(ticker, period)` | 過去株価履歴 (10y等) |
| `get_screening_info(ticker)` | スクリーニング用詳細指標（ROE, マージン, FCF利回り等）|
| `get_quarterly_financials(ticker)` | 四半期財務データ (Yahoo Finance経由) |

**FCF利回り計算**: `freeCashflow / marketCap` (`get_screening_info` 内で計算)
**レートリミット**: 設定可能 (デフォルト 2 req/sec)

### 4.6 FMP (`ingestion/fmp.py`)

Financial Modeling Prep API (現在は非推奨、Yahoo Finance に移行済み)。
APIキーが設定されていない場合は機能しない。

---

## 5. サービス層

### 5.1 汎用Upsert (`services/upsert.py`)

`generic_upsert(session, model, filters, data, label)`: フィルタ条件で既存レコードを検索し、存在すれば更新、なければ挿入。全サービスで共通使用。

`get_column_names(model)`: モデルのカラム名一覧取得。

### 5.2 企業サービス (`services/company_service.py`)

- `register_company(session, data)` → Company
- `get_company(session, company_id)` → Company | None
- `search_companies(session, query, limit)` → list[Company]
- `is_us_market(company_id)` → bool (ID接頭辞で判定)
- `find_company_by_identifier(session, query)` → Company | None (ticker/security_code/idで完全一致)

### 5.3 財務データサービス (`services/financial_service.py`)

- `upsert_financial_data(session, company_id, data)` → FinancialData
- `get_financial_timeseries(session, company_id, period_type, years)` → list[FinancialData]
- `compute_metrics(fd)` → dict (単一レコードから財務指標計算)
- `compute_timeseries_metrics(records)` → list[dict] (時系列指標計算 + 成長率)

### 5.4 財務データ同期 (`services/financial_sync.py`)

**主要関数**: `run_financial_update(session, config, company_id)` → bool

**データフロー**:
1. SEC EDGAR から Company Facts JSON 取得
2. `SecXbrlParser` で annual/quarterly をパース
3. FCF を operating_cf - capex から導出（未設定時）
4. `upsert_financial_data` で DB に保存
5. Yahoo Finance フォールバック: SEC 四半期データがない場合
6. Q4 fill: Yahoo Finance 8-K データ + Annual - Q3 YTD 減算

**Q4導出戦略** (2層):
- Layer 1 (優先): Yahoo Finance 四半期データ (8-K由来の実績Q4値)
- Layer 2 (フォールバック): Annual − Q3_YTD 減算 (フロー項目のみ)
  - **減算不可フィールド**: eps, dps, shares_outstanding (株式数変動で不正確)

**Yahoo Finance ティッカー解決**: BRK-B → BRK-B, 日本株は `{ticker}.T`

### 5.5 バリュエーションサービス (`services/valuation_service.py`)

- `upsert_valuation(session, company_id, data)` → Valuation
- `get_valuation_history(session, company_id, years)` → list[Valuation]
- `compute_per_range(valuations)` → dict (PER high/median/low)
- `compare_valuations(session, company_ids)` → list[dict] (複数社比較)
- `compute_group_deviation(comparisons)` → None (z-score偏差追加)
- `build_chart_data(valuations)` → dict (labels, stock_price, per, pbr, ev_ebitda, psr)

### 5.6 ファイリングサービス (`services/filing_service.py`, `filing_sync.py`)

**filing_service.py**:
- `upsert_filing(session, company_id, data)` → Filing
- `get_latest_filing(session, company_id, filing_type)` → Filing | None
- `list_filings(session, company_id)` → list[Filing]

**filing_sync.py** (`run_filing_update`):
- SEC: submissions API → ファイリングメタデータ登録 + HTML保存 + セクション抽出
- EDINET: 書類一覧 → XBRL ZIP ダウンロード + 保存

### 5.7 ジョブサービス (`services/job_service.py`)

**主要関数**:
- `run_daily_update(session, config, market)` → DailyUpdateResult
- `sync_company(session, config, company_id)` → SyncResult

**sync_company フロー**:
1. `run_financial_update` (SEC/EDINET)
2. `run_filing_update` (ファイリング取得)
3. Yahoo Finance から現在株価取得
4. `_compute_valuation_from_financials` で現在バリュエーション計算
5. `_build_historical_valuations` で過去10年月次バリュエーション構築

**過去バリュエーション構築** (`_build_historical_valuations`):
- Yahoo Finance 10年価格履歴 → 月次サンプリング（月初営業日）
- 各月の株価 × その時点の最新年次財務データ → PER, PBR, PSR, EV/EBITDA, FCF利回り計算
- 既存レコード >= 100件でスキップ

**バリュエーション計算** (`_compute_valuation_from_financials`):
- PER: stock_price / eps (フォールバック: market_cap / net_income)
- PBR: market_cap / equity (フォールバック: stock_price / BVPS)
- EV/EBITDA: (market_cap + total_debt - cash) / ebitda
- PSR: market_cap / revenue
- FCF利回り: fcf / market_cap

### 5.8 財務指標 (`services/metrics.py`)

25個の純粋関数。全て `float | None` を返す安全な設計。

**収益性**: operating_margin, net_margin, roe, roa, roic
**効率性**: asset_turnover, inventory_turnover
**財務安全性**: equity_ratio, current_ratio, de_ratio
**成長性**: revenue_growth, eps_growth, fcf_growth
**株主還元**: dividend_payout_ratio, total_payout_ratio
**バリュエーション**: per, pbr, ev_ebitda, psr, peg_ratio
**その他**: cagr, is_anomaly

### 5.9 LLMサービス (`services/llm_service.py`, `llm_extraction.py`, `llm_orchestration.py`)

**llm_extraction.py** — HTMLからのセクション抽出:
- `extract_sections(html_content)` → dict[str, str]
- 10-K: Business (Item 1), Risk Factors (Item 1A), MD&A (Item 7)
- 20-F: Business (Item 4), Key Information (Item 3), Operating Review (Item 5)
- 最長セクションを選択してToC参照をスキップ
- `bisect.bisect_right` でO(log n)のヘッディング位置検索

**llm_service.py** — Ollama API呼び出し:
- `analyze_filing(config, text, analysis_type)` → dict
- 4種類の分析: business_summary, risk_factors, mda, competitors
- JSON Schema による構造化出力 (Ollama `format` パラメータ)
- プロンプトは全て日本語で出力指示
- `save_analysis_to_db` でDB保存

**llm_orchestration.py** — 分析オーケストレーション:
- `run_llm_analysis(session, config, company_id)` → 分析実行管理

### 5.10 スクリーニングサービス (`services/screening_service.py`, `screening_universe.py`)

**screening_service.py** — Yahoo Finance Screener API:
- `run_screen(session, filters, sector, exchange, sort_by, limit, descending)` → dict
- `parse_condition(value_str)` → (operator, float) — 例: ">15%", "<20", ">=1B"
- サーバーサイドフィルタ: `yfinance.EquityQuery` + `yfinance.screener.screen`
- ポストフィルタ: forward_per, pbr 等 (quote応答で利用可能なフィールド)
- **FCF利回りフィルタ**: Yahoo Screener APIに非対応のため、結果取得後に`YahooFinanceClient.get_screening_info()`で個別enrichment。`ThreadPoolExecutor(max_workers=8)` で並列化。

**サフィックス対応**: %, k/K, m/M, b/B, t/T
**オペレータ**: <, >, <=, >=

**screening_universe.py** — ユニバース管理:
- `refresh_universe(session)` → int — SEC EDGAR一括インポート
- `enrich_with_yahoo(session, yf_client, limit, skip_recent_hours)` → int — Yahoo Finance enrichment

### 5.11 ウォッチリストサービス (`services/watchlist_service.py`)

- `create_watchlist(session, name, description)` → Watchlist
- `list_watchlists(session)` → list[Watchlist]
- `get_watchlist(session, watchlist_id)` → Watchlist | None
- `add_item(session, watchlist_id, company_id, ...)` → WatchlistItem
- `remove_item(session, watchlist_id, company_id)` → bool
- `update_item(session, item_id, ...)` → WatchlistItem

### 5.12 分析ターゲットサービス (`services/analysis_target_service.py`)

- `add_target(session, company_id, source, criteria)` → AnalysisTarget
- `remove_target(session, company_id)` → bool
- `list_targets(session)` → list[AnalysisTarget]
- `add_from_screening(session, results, criteria)` → int — スクリーニング結果から一括追加

---

## 6. CLI インターフェース

エントリポイント: `stock-analyzer` (`src/stock_analyzer/__main__.py`)

### 6.1 サブコマンド一覧

| サブコマンド | ファイル | 機能 |
|-------------|---------|------|
| `company register` | cli/company.py | 企業登録 |
| `company search` | cli/company.py | 企業検索 |
| `company show` | cli/company.py | 企業詳細表示 |
| `financial show` | cli/financial.py | 財務データ表示 (通期/四半期) |
| `financial metrics` | cli/financial.py | 財務指標計算・表示 |
| `valuation show` | cli/valuation.py | バリュエーション履歴 |
| `valuation compare` | cli/valuation.py | 複数社バリュエーション比較 |
| `valuation range` | cli/valuation.py | PER高値/中央値/安値 |
| `valuation deviation` | cli/valuation.py | グループ内z-score偏差 |
| `filings list` | cli/filings.py | ファイリング一覧 |
| `filings download` | cli/filings.py | ファイリングダウンロード |
| `filings extract` | cli/filings.py | セクション抽出 |
| `llm analyze` | cli/llm.py | LLM分析実行 |
| `llm show` | cli/llm.py | 分析結果表示 |
| `llm health` | cli/llm.py | Ollamaサーバー疎通確認 |
| `jobs sync` | cli/jobs.py | 単一企業の完全同期 |
| `jobs daily` | cli/jobs.py | 日次一括更新 |
| `screen run` | cli/screen.py | スクリーニング実行 |
| `screen add-targets` | cli/screen.py | スクリーニング結果→分析ターゲット |
| `watchlist create` | cli/watchlist.py | ウォッチリスト作成 |
| `watchlist list` | cli/watchlist.py | ウォッチリスト一覧 |
| `watchlist show` | cli/watchlist.py | ウォッチリスト詳細 |
| `watchlist add` | cli/watchlist.py | アイテム追加 |
| `watchlist remove` | cli/watchlist.py | アイテム削除 |
| `target list` | cli/target.py | 分析ターゲット一覧 |
| `target add` | cli/target.py | ターゲット追加 |
| `target remove` | cli/target.py | ターゲット削除 |
| `serve` | cli/serve.py | Webサーバー起動 |
| `bot` | cli/bot.py | Discord Bot起動 |

### 6.2 共通ヘルパー (`cli/helpers.py`)

- `require_company(session, company_id)` → Company — 見つからなければ `sys.exit(1)`
- `require_latest_filing(session, company_id, filing_id)` → Filing

### 6.3 フォーマッタ (`cli/formatters.py`, `shared/formatters.py`)

**shared/formatters.py** (共有):
- `fmt_number(val, decimals)` — 数値フォーマット
- `fmt_pct(val, decimals)` — パーセンテージ
- `fmt_large(val)` — 大きい数値 (B/M/K)
- `fmt_ratio(val, decimals)` — 比率

**cli/formatters.py**: `shared.formatters` を re-export + CLI固有のテーブルフォーマット

---

## 7. Web インターフェース

### 7.1 アプリケーション構成

FastAPI + Jinja2テンプレート + SSR (サーバーサイドレンダリング)
HTMX で部分更新、Alpine.js でクライアントサイド状態管理
Chart.js でグラフ描画

### 7.2 認証 (`web/auth.py`)

- セッションベース認証 (itsdangerous の URLSafeTimedSerializer)
- パスワード認証 (`WEB_PASSWORD` 環境変数)
- `require_auth(request)` → RedirectResponse | None
- `/login`, `/logout`, `/static` は認証スキップ

### 7.3 ルート一覧

| パス | メソッド | ファイル | 機能 |
|-----|---------|---------|------|
| `/` | GET | dashboard.py | ダッシュボード |
| `/login` | GET/POST | dashboard.py | ログイン |
| `/logout` | GET | dashboard.py | ログアウト |
| `/stocks/search` | GET | stocks.py | 企業検索 (HTMX) |
| `/stocks/{company_id}` | GET | stocks.py | 企業詳細ページ |
| `/watchlists` | GET | watchlists.py | ウォッチリスト一覧 |
| `/watchlists/create` | POST | watchlists.py | ウォッチリスト作成 |
| `/watchlists/{id}` | GET | watchlists.py | ウォッチリスト詳細 |
| `/watchlists/{id}/add` | POST | watchlists.py | アイテム追加 |
| `/watchlists/{id}/remove/{company_id}` | POST | watchlists.py | アイテム削除 |
| `/jobs` | GET | jobs.py | ジョブ管理 |
| `/jobs/sync` | POST | jobs.py | 同期実行 |
| `/jobs/daily` | POST | jobs.py | 日次更新実行 |
| `/screening` | GET/POST | screening.py | スクリーニング |
| `/targets` | GET | targets.py | 分析ターゲット一覧 |
| `/targets/add` | POST | targets.py | ターゲット追加 |
| `/targets/remove/{company_id}` | POST | targets.py | ターゲット削除 |
| `/api/stocks/{id}/valuations` | GET | api.py | バリュエーションJSON |
| `/api/stocks/{id}/financials/{period}` | GET | api.py | 財務データJSON |

### 7.4 企業詳細ページ (stock_detail.html)

**タブ構成**:
1. **財務** — 売上高・利益推移 (棒グラフ) + EPS推移 (折れ線) + 個別指標グラフ (棒+成長率折れ線)
   - 通期/四半期切り替え
   - 指標選択: revenue, operating_income, net_income, ebitda, operating_cf, capex, fcf
2. **バリュエーション** — PER推移、PBR推移、PSR推移 (各個別折れ線グラフ)
3. **指標** — 財務指標テーブル (tabulate形式)
4. **分析** — LLM分析結果表示
5. **ファイリング** — ファイリング一覧テーブル

### 7.5 スクリーニングページ (screening.html)

**フィルタキー**: per, forward_per, pbr, psr, ev_ebitda, roe, operating_margin, net_margin, revenue_growth, earnings_growth, dividend_yield, de_ratio, market_cap, peg_ratio, fcf_yield

**HTMX部分更新**: フォーム送信 → screening_results.html コンポーネントを差し替え

---

## 8. Discord Bot

### 8.1 構成

- `bot/client.py` — `StockAnalyzerBot(commands.Bot)` クラス
- `bot/commands.py` — コマンドハンドラー

### 8.2 コマンド一覧

| コマンド | 機能 |
|---------|------|
| `!sync <company_id>` | 企業同期 |
| `!analyze <company_id>` | 財務分析表示 |
| `!financial <company_id>` | 財務データ表示 |
| `!valuation <company_id>` | バリュエーション表示 |
| `!watchlist [name]` | ウォッチリスト操作 |
| `!help` | ヘルプ |

---

## 9. XBRLタグマッピング

### 9.1 US-GAAP (`config/us_gaap_mapping.yaml`)

| フィールド | 候補タグ (優先順) |
|-----------|------------------|
| revenue | Revenues, SalesRevenueNet, RevenueFromContractWithCustomerExcludingAssessedTax |
| operating_income | OperatingIncomeLoss |
| net_income | NetIncomeLoss, ProfitLoss |
| total_assets | Assets |
| equity | StockholdersEquity, StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest |
| current_assets | AssetsCurrent |
| current_liabilities | LiabilitiesCurrent |
| total_debt | Debt, LongTermDebt, DebtCurrent |
| cash | CashAndCashEquivalentsAtCarryingValue, CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents |
| inventory | InventoryNet |
| cogs | CostOfGoodsAndServicesSold, CostOfRevenue |
| operating_cf | NetCashProvidedByUsedInOperatingActivities |
| capex | PaymentsToAcquirePropertyPlantAndEquipment, PaymentsToAcquireProductiveAssets |
| ebitda | EarningsBeforeInterestTaxesDepreciationAmortization |
| eps | EarningsPerShareDiluted, EarningsPerShareBasic |
| dps | CommonStockDividendsPerShareDeclared, CommonStockDividendsPerShareCashPaid |
| tax_expense | IncomeTaxExpenseBenefit |
| income_before_tax | IncomeLossFromContinuingOperationsBeforeIncomeTaxes..., IncomeBeforeIncomeTaxes |
| shares_outstanding | WeightedAverageNumberOfDilutedSharesOutstanding, WeightedAverageNumberOfSharesOutstandingBasic, CommonStockSharesOutstanding |
| dividends_paid | PaymentsOfDividends, PaymentsOfDividendsCommonStock |
| share_repurchases | PaymentsForRepurchaseOfCommonStock, TreasuryStockPurchased |

### 9.2 IFRS (`config/ifrs_mapping.yaml`)

IFRSタクソノミ (ifrs-full) 用。Revenue, ProfitLoss, Assets, Equity 等の対応。

### 9.3 EDINET (`config/edinet_taxonomy_mapping.yaml`)

日本基準(JP-GAAP)タクソノミ用マッピング。

---

## 10. テスト

### 10.1 テスト構成

- **ユニットテスト** (20ファイル, ~340テスト): 各サービス・モジュール単位
- **統合テスト** (2ファイル, ~18テスト): CLI, ウォッチリストフロー

### 10.2 テストインフラ (`tests/conftest.py`)

- インメモリSQLite (`sqlite:///:memory:`)
- `session` fixture: 各テストでロールバック
- `mock_config` fixture: テスト用AppConfig

### 10.3 テストカバレッジ

| テストファイル | テスト対象 | テスト数 |
|--------------|-----------|---------|
| test_config.py | 設定ロード | ~5 |
| test_company_service.py | 企業サービス | ~15 |
| test_financial_service.py | 財務サービス | ~20 |
| test_valuation_service.py | バリュエーション | ~15 |
| test_filing_service.py | ファイリング | ~10 |
| test_job_service.py | ジョブサービス | ~25 |
| test_llm_service.py | LLM | ~15 |
| test_metrics.py | 財務指標 | ~60 |
| test_screening_service.py | スクリーニング | ~30 |
| test_sec_xbrl_parser.py | XBRLパーサー | 19 |
| test_watchlist_service.py | ウォッチリスト | ~20 |
| test_analysis_target_service.py | 分析ターゲット | ~10 |
| test_upsert.py | 汎用Upsert | ~10 |
| test_formatters.py | CLIフォーマッタ | ~15 |
| test_shared_formatters.py | 共有フォーマッタ | ~10 |
| test_save_analysis.py | 分析結果保存 | ~5 |
| test_screen_add_targets.py | スクリーニング→ターゲット | ~5 |
| test_yahoo_finance.py | Yahoo Finance | ~10 |
| test_cli.py (統合) | CLI全体 | ~15 |
| test_watchlist_flow.py (統合) | ウォッチリストE2E | ~3 |

---

## 11. 本セッションでの修正履歴

### 11.1 SEC XBRLパーサー修正

**問題1: 10-QのYTD累積値の誤取り込み**
- 原因: `_duration_ok()` が10-K/20-Fのみに四半期期間フィルタを適用し、10-Qを除外していた
- 修正: 全フォーム型に `days <= 120` の四半期フィルタを適用
- 追加: `resolve_tag()` で同一end_dateに複数エントリがある場合、最短期間のエントリを優先

**問題2: 近接日付ゴーストレコード (MU 2018-08-30/31)**
- 原因: SEC XBRL概念が微妙に異なるend_dateを使用
- 修正: `_merge_near_dates()` で±3日以内の日付をクラスタリング

**問題3: 大規模ゴーストレコード (38,373件)**
- 原因: `dps` 等のマイナーフィールドが配当支払日(非決算日)のend_dateを持ち、空レコードが作成された
- 修正: `_CORE_FIELDS` チェック — 主要フィールドのいずれかにデータがないレコードは出力しない
- DB既存データ: quarterly 15,416件 + annual 22,957件を一括削除

### 11.2 コードリファクタリング

- `_duration_ok()` から `form` パラメータを削除、`days: int` を受け取る形に変更
- `_days_between()` ヘルパーを抽出、3箇所の重複日付計算を統一
- `_DURATION_UNKNOWN = 99999` 定数を導入
- `renderMetricChart` の重複呼び出しを削除

### 11.3 バリュエーションチャート

- PER/PBR/PSR を個別グラフに分離 (各1チャート)
- EV/EBITDA チャートを削除

### 11.4 FCF利回りスクリーニング修正

- 原因: Yahoo Screener APIにFCF利回りフィールドが存在せず、フィルタが完全無視されていた
- 修正: `_enrich_fcf_yield()` で結果取得後に `YahooFinanceClient.get_screening_info()` から個別enrichment
- `ThreadPoolExecutor(max_workers=8)` で並列化

### 11.5 モジュール分割

- `screening_service.py` → `screening_universe.py` を分離 (refresh_universe, enrich_with_yahoo)
- `llm_service.py` → `llm_extraction.py` を分離 (extract_sections, ヘッディングパターン)
- 各分割元に re-export で後方互換性維持

---

## 12. 既知の問題・制限事項

### 12.1 現存バグ（高優先度）

1. **スクリーニング結果のCompany IDハードコード** (`web/templates/components/screening_results.html`)
   - Company ID が `"US_" ~ row.ticker` にハードコードされており、JP市場の銘柄で不正なIDが生成される
   - 影響: JP銘柄をスクリーニング結果から詳細ページに遷移できない

2. **Tailwind CDN JIT で動的クラス名が未検出** (`web/routes/watchlists.py`)
   - `_render_sync_progress` が `bg-{color}-50` のような動的Tailwindクラスを生成
   - CDN JITモードでは動的クラス名を検出できず、同期プログレスバーのスタイルが崩れる
   - 修正: 完全なクラス名を直接記述する必要あり

3. **CLI `jobs --type` 引数が未使用** (`cli/jobs.py`)
   - `--type` (daily/weekly/full) を受け付けるが、常に `run_daily_update()` を実行
   - `weekly` と `full` はデッドオプション

4. **`sync_company` の `financials_count` が常に0** (`services/job_service.py`)
   - `result["financials_count"]` が初期化後にインクリメントされない
   - UI/CLIで同期結果の財務データ件数が常に0と表示される

5. **`screening_service._YF_OPS` の境界値除外** (`services/screening_service.py`)
   - `<=` が `lt` に、`>=` が `gt` にマッピング（Yahoo EquityQuery の制約）
   - `<=20` が `<20` として処理され、境界値が除外される

6. **`screening_universe.refresh_universe` の空market** (`services/screening_universe.py`)
   - 新規登録企業の `market` フィールドが空文字 `""` に設定される
   - `company.market` を参照する他のサービスで予期しない動作の可能性

### 12.1.1 現存バグ（中優先度）

7. **CLI `_make_company_id` の市場分類** (`cli/company.py`)
   - NYSE/NASDAQ以外の全市場をJPに分類する不正なロジック
   - 他市場（LSE等）の企業登録時に誤ったID接頭辞が付与される

8. **Web セッションシークレットの自動生成** (`web/__init__.py`)
   - `config.web.session_secret` 未設定時に `secrets.token_hex(32)` で自動生成
   - アプリ再起動時にシークレットが変わり、全既存セッションが無効化される

9. **ナビゲーションのアクティブ状態検出** (`web/templates/components/nav.html`)
   - 完全パスマッチ (`request.url.path == item.href`) を使用
   - 子ページ（例: `/watchlists/my-list`）でナビ項目がハイライトされない
   - 修正: `startswith` によるプレフィックスマッチに変更すべき

10. **EDINET API キー未設定時の無通知スキップ**
    - `_update_from_edinet` は API キーがない場合に静かにスキップするが、ユーザーへの通知がない

11. **LLM `competitors` 分析タイプが到達不能** (`services/llm_orchestration.py`)
    - `llm_service._PROMPTS` に `competitors` が定義されているが、`run_llm_analysis` の `analysis_type_map` に含まれない
    - CLI の `!llm competitors` コマンドからのみ呼び出し可能で、標準パイプラインでは到達不能

12. **設定ファイルのLLMモデル名不一致** (`config.py` vs `settings.yaml`)
    - Python デフォルト: `"gptoss20b:q8"` / YAML: `"clore/gpt-oss-20b-Q8_0:latest"`
    - YAML存在時は問題ないが、YAML欠損時にフォールバック値が異なる

### 12.1.2 現存バグ（低優先度）

13. **`StockAnalyzerBot` クラスがデッドコード** (`bot/client.py`)
    - `run_bot()` は `create_bot()` を呼び出し `commands.Bot` を使用。`StockAnalyzerBot` クラスは未使用

14. **`require_auth()` がデッドコード** (`web/dependencies.py`)
    - `AuthMiddleware` が全ルートの認証を処理するため、`require_auth()` 関数は不要

15. **CLI `serve` のポート0問題** (`cli/serve.py`)
    - `args.port or config.web.port` で port=0 が falsy として扱われ、設定値にフォールバック
    - 修正: `args.port if args.port is not None else config.web.port` に変更すべき

16. **CLI `valuation` の使用法表示** (`cli/valuation.py`)
    - 使用法文字列に `{show|compare|range}` と表示されるが、`deviation` アクションが未記載

17. **CLI `watchlist` ハンドラの署名不整合** (`cli/watchlist.py`)
    - ハンドラ関数が `(args)` のみ受け取り、他モジュールの `(args, config)` パターンと不整合

18. **SEC `list_filings` の履歴ページネーション未対応** (`ingestion/sec_edgar.py`)
    - `filings.recent` のみ処理し、古いファイリングへのページネーション (`filings.files`) を未取得
    - 長い上場歴の企業で古いファイリングが欠落する

19. **EDINET XBRLパーサーのコンテキスト未考慮** (`ingestion/edinet_xbrl_parser.py`)
    - XBRL要素の最後の出現値を採用するが、コンテキスト（期間・連結/単体）を区別しない
    - 異なる会計期間の値が混在する可能性

20. **SEC EDGAR メールアドレスの環境変数上書き未対応** (`config.py`)
    - `EDINET_API_KEY` 等は環境変数で上書きできるが、`sec_edgar.email` は不可
    - `settings.yaml` に実メールアドレスがハードコードされている

### 12.1.3 テストカバレッジの不足

21. **Bot モジュールのテストがゼロ**: `client.py` と `commands.py` にテストなし
22. **Yahoo Finance クライアント**: `_epoch_to_date` のみテスト。主要メソッド未テスト
23. **`financial_service`**: `get_financial_timeseries` と `compute_timeseries_metrics` が未テスト
24. **`valuation_service`**: `get_valuation_history` と `upsert_valuation` が未テスト
25. **LLM API呼び出し**: `analyze_filing` の実際のAPI呼び出し・エラー処理が未テスト
26. **CLI サブコマンド**: `financial`, `valuation`, `filings`, `llm`, `jobs`, `screen` の統合テストが `--help` のみ

### 12.2 アーキテクチャ上の制約

1. **SQLite単一ファイル**: 同時書き込みに制限あり。大規模運用にはPostgreSQL等への移行が必要
2. **LLM依存**: Ollama ローカルサーバーが必要。クラウドLLM API への切り替え未対応
3. **Yahoo Finance レート制限**: 大量のスクリーニングenrichment時にスロットリングの可能性
4. **スクリーニングのFCF利回りフィルタ**: 個別API呼び出しが必要なため、他のフィルタより遅い
5. **EDINET `search_company_filings` の低速性**: 日ごとにAPI呼び出し (5年検索 = ~1,825回 × 5秒間隔 = ~2.5時間)
6. **設定ファイルの相対パス依存**: `config/*.yaml` のマッピングファイルはCWDがプロジェクトルートでないと読み込み失敗
7. **`enrich_with_yahoo` の逐次処理**: 大規模ユニバース（10,000+銘柄）で数時間かかる可能性。並列処理未実装
8. **非同期未対応**: 全HTTPクライアントとレートリミッターが同期ブロッキング。FastAPI内で長時間ジョブがスレッドをブロック

### 12.3 未実装の計画機能 (リファクタリング計画より)

1. ~~共有フォーマッタの統一~~ → **完了**
2. ~~`find_company_by_identifier()` 追加~~ → **完了**
3. bot/commands.py のサービス層書き直し → **未実施**
4. Web認証ミドルウェア → **未実施**
5. ~~CLI共通ヘルパー抽出~~ → **完了**
6. ~~job_service.py の分割~~ → **部分完了** (financial_sync, filing_sync, llm_orchestration は分割済み)

---

## 13. PageIndex RAG統合 — 推論ベースSEC書類分析

### 13.1 概要

[PageIndex](https://github.com/VectifyAI/PageIndex) (VectifyAI) をStock AnalyzerのLLM分析パイプラインに統合し、SEC提出書類（10-K/10-Q/20-F/6-K）に対する推論ベースRAGシステムを構築する。

**従来のアプローチとの違い:**

| 項目 | 現行 (`llm_extraction.py`) | PageIndex RAG |
|------|---------------------------|---------------|
| 文書理解 | 正規表現ベースのセクション抽出 | 階層ツリーインデックス構築 |
| 検索方式 | パターンマッチ (Item 1, Item 7 等) | LLM推論による木探索 |
| ベクトルDB | なし | **不要** (vectorless) |
| チャンキング | なし (セクション単位) | **不要** (文書構造保持) |
| 精度 | セクション境界の誤検出あり | FinanceBench 98.7%精度 |
| Q&A機能 | なし (要約のみ) | 対話的質疑応答が可能 |

### 13.2 PageIndex技術詳細

**リポジトリ:** `https://github.com/VectifyAI/PageIndex` (22.5K stars, Python)

**依存パッケージ:**
- `litellm==1.82.0` — マルチプロバイダーLLM呼び出し (OpenAI/Anthropic/Ollama等)
- `pymupdf==1.26.4` — PDF解析
- `PyPDF2==3.0.1` — PDF解析 (フォールバック)
- `python-dotenv==1.1.0` — 環境変数管理 (既存と共通)
- `pyyaml==6.0.2` — YAML設定 (既存と共通)

**モジュール構成:**
```
pageindex/
├── __init__.py
├── config.yaml           # デフォルト設定
├── page_index.py         # PDF→ツリーインデックス構築 (メイン)
├── page_index_md.py      # Markdown→ツリー構築
└── utils.py              # LLM呼び出し、PDF操作、JSON/ツリーユーティリティ
```

**コア処理フロー (2段階):**

```
┌─────────────────────────────────────────────────────────┐
│  Stage 1: インデックス生成 (Index Generation)              │
│                                                         │
│  PDF → TOC検出 → セクション階層抽出 → 検証/修正            │
│      → 大ノード再帰分割 → ツリーインデックスJSON生成         │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 2: 推論ベース検索 (Reasoning-Based Retrieval)      │
│                                                         │
│  ユーザー質問 → LLMがツリーを探索 → 該当セクション特定       │
│             → ページ範囲のテキスト取得 → 回答生成           │
└─────────────────────────────────────────────────────────┘
```

**ツリーインデックス構造例:**
```json
{
  "title": "10-K Annual Report - Apple Inc.",
  "nodes": [
    {
      "title": "Business",
      "node_id": "0001",
      "start_index": 5,
      "end_index": 12,
      "summary": "Appleの主要事業セグメント...",
      "nodes": [
        {
          "title": "Products",
          "node_id": "0002",
          "start_index": 6,
          "end_index": 8,
          "summary": "iPhone, Mac, iPad..."
        },
        {
          "title": "Services",
          "node_id": "0003",
          "start_index": 9,
          "end_index": 12,
          "summary": "App Store, iCloud..."
        }
      ]
    },
    {
      "title": "Risk Factors",
      "node_id": "0004",
      "start_index": 13,
      "end_index": 28,
      "summary": "主要なリスク要因..."
    }
  ]
}
```

**設定パラメータ:**

| パラメータ | デフォルト値 | 説明 |
|-----------|------------|------|
| `model` | `gpt-4o-2024-11-20` (原版) → 本プロジェクトでは `ollama/gptoss20b:q8` | LLMモデル（litellm経由） |
| `toc_check_page_num` | `20` | TOC検出のスキャンページ数 |
| `max_page_num_each_node` | `10` | ノードあたり最大ページ数 |
| `max_token_num_each_node` | `20000` | ノードあたり最大トークン数 |
| `if_add_node_id` | `yes` | ノードID付与 |
| `if_add_node_summary` | `yes` | ノード要約生成 |
| `if_add_doc_description` | `no` | 文書全体の説明生成 |
| `if_add_node_text` | `no` | ノードに原文テキスト埋め込み |

**主要関数:**
- `page_index(doc, model, ...)` — PDF→ツリーインデックスのメインエントリポイント
- `page_index_main(doc, opt)` — 設定オブジェクト版エントリポイント
- `tree_parser(page_list, opt, doc, logger)` — ツリー構造パース・構築
- `meta_processor(page_list, mode, ...)` — TOC有無に応じた処理モード選択
- `process_large_node_recursively(node, ...)` — 大ノードの再帰分割
- `verify_toc(page_list, list_result, ...)` — LLMによるTOC検証
- `llm_completion(model, prompt, ...)` — 同期LLM呼び出し (10回リトライ)
- `llm_acompletion(model, prompt)` — 非同期LLM呼び出し

### 13.3 Stock Analyzerへの統合設計

#### 13.3.1 新規ファイル構成

```
src/stock_analyzer/
├── services/
│   ├── pageindex_service.py      # PageIndexラッパーサービス
│   └── rag_service.py            # RAG質疑応答サービス
├── models/
│   └── document_index.py         # ツリーインデックスDBモデル
├── cli/
│   └── rag.py                    # RAG CLIコマンド
└── web/
    ├── routes/
    │   └── rag.py                # RAG Webルート
    └── templates/pages/
        └── rag.html              # RAG質疑応答UI
```

#### 13.3.2 データベースモデル: `DocumentIndex`

```python
class DocumentIndex(Base):
    __tablename__ = "document_indices"

    id: int                    # PK
    filing_id: int             # FK → filings.id (1:1)
    company_id: str            # FK → companies.id
    index_json: Text           # PageIndex生成のツリーインデックスJSON
    model_name: str            # インデックス生成に使用したLLMモデル
    page_count: int            # PDF総ページ数
    node_count: int            # ツリーノード数
    created_at: datetime
    last_queried_at: datetime  # 最終クエリ日時（キャッシュ管理用）
```

**Unique制約:** `(filing_id,)` — ファイリングごとに1つのインデックス

#### 13.3.3 設定拡張: `PageIndexConfig`

`config.py` に追加:
```python
@dataclass
class PageIndexConfig:
    enabled: bool = False
    model: str = ""                    # 空=LlmConfig.modelを継承 (例: "ollama/gptoss20b:q8")
    backend: str = "ollama"            # ollama / lm_studio / openai / anthropic
    lm_studio_base_url: str = "http://localhost:1234/v1"  # LM Studio使用時
    api_key: str = ""                  # クラウドAPI使用時 (本プロジェクトでは通常不要)
    toc_check_pages: int = 20
    max_pages_per_node: int = 10
    max_tokens_per_node: int = 20000
    add_node_summary: bool = True
    add_node_text: bool = False
    cache_indices: bool = True         # インデックスをDB保存
```

`settings.yaml` に追加:
```yaml
pageindex:
  enabled: true
  model: "ollama/gptoss20b:q8"   # ローカルLLM (litellm形式)
  # model: "ollama/gptoss120b"   # 高精度版
  backend: ollama                 # ollama / lm_studio
  # lm_studio_base_url: "http://localhost:1234/v1"  # LM Studio使用時
  toc_check_pages: 20
  max_pages_per_node: 10
  max_tokens_per_node: 20000
  add_node_summary: true
  cache_indices: true
```

環境変数: `PAGEINDEX_API_KEY` (OpenAI/Anthropic API キー)

#### 13.3.4 サービス層: `pageindex_service.py`

```python
# 主要関数

def build_index(filing_path: Path, config: PageIndexConfig) -> dict:
    """SEC提出書類PDFからPageIndexツリーインデックスを生成。

    1. PDF/HTMLをPageIndexに渡す
    2. litellm経由で設定されたLLMモデルを使用
    3. 生成されたツリーインデックスを返す
    """

def get_or_create_index(
    session: Session, filing_id: int, config: AppConfig
) -> dict:
    """インデックスの取得または生成（キャッシュ付き）。

    1. DBに既存インデックスがあれば返す
    2. なければbuild_index()で生成しDB保存
    """

def query_document(
    index: dict, question: str, pdf_path: Path, config: PageIndexConfig
) -> dict:
    """ツリーインデックスを使って文書に質問。

    1. LLMがツリーを推論的に探索
    2. 該当ノードのページ範囲を特定
    3. 該当ページのテキストをコンテキストとしてLLMに渡す
    4. 回答を生成
    返す: {answer, source_pages, source_sections, confidence}
    """
```

#### 13.3.5 サービス層: `rag_service.py`

```python
def analyze_with_rag(
    session: Session, config: AppConfig,
    company_id: str, filing_id: int,
    questions: list[str] | None = None,
) -> dict:
    """RAGベースの包括的分析。

    questionsがNoneの場合、デフォルトの分析質問セットを使用:
    - 事業の主要な収益ドライバーは何ですか？
    - 最も重大なリスク要因を3つ挙げてください
    - 経営陣は今後の業績をどのように見通していますか？
    - 競合他社と比較した競争優位性は何ですか？
    - 直近の財務パフォーマンスの要約を提供してください
    """

def ask_question(
    session: Session, config: AppConfig,
    company_id: str, filing_id: int,
    question: str,
) -> dict:
    """単一の質問に対するRAG回答。

    返す: {
        answer: str,
        source_pages: list[int],
        source_sections: list[str],
        confidence: float,
        model: str,
    }
    """
```

#### 13.3.6 既存LLM分析との統合

現行の `llm_orchestration.py` の `run_llm_analysis()` を拡張:

```python
def run_llm_analysis(session, config, company_id, filing_id) -> bool:
    # ... 既存のセクション抽出 + Ollama分析 (変更なし) ...

    # PageIndex RAG分析を追加実行（有効時）
    if config.pageindex.enabled:
        try:
            rag_result = rag_service.analyze_with_rag(
                session, config, company_id, filing_id
            )
            llm_service.save_analysis_to_db(
                session, company_id, filing_id,
                "rag_summary", rag_result, config.pageindex.model or config.llm.model,
            )
        except Exception:
            logger.warning("PageIndex RAG analysis failed", exc_info=True)
            # RAG失敗は既存分析に影響させない
```

#### 13.3.7 CLIコマンド: `stock-analyzer rag`

| サブコマンド | 引数 | 説明 |
|-------------|------|------|
| `index` | `company_id`, `--filing-id` | ファイリングのPageIndexインデックスを生成 |
| `ask` | `company_id`, `question`, `--filing-id` | ファイリングに対する質問 |
| `analyze` | `company_id`, `--filing-id` | デフォルト質問セットで包括的RAG分析 |
| `status` | `company_id` | インデックス生成状況の確認 |

**使用例:**
```bash
# インデックス生成
stock-analyzer rag index US_AAPL --filing-id 42

# 質疑応答
stock-analyzer rag ask US_AAPL "Appleの主要なリスク要因は？"
stock-analyzer rag ask US_AAPL "売上成長の主要ドライバーは？" --filing-id 42

# 包括的分析
stock-analyzer rag analyze US_AAPL
```

#### 13.3.8 Web UI: RAGタブ

`stock_detail.html` の既存タブ（Overview / Financials / Valuation / LLM Analysis）に **RAG Q&A** タブを追加。

**UI構成:**
```
┌─────────────────────────────────────────────┐
│  RAG Q&A                                     │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  📄 インデックス状態: ✅ 構築済み        │  │
│  │     Filing: 10-K FY2024 (142ページ)     │  │
│  │     ノード数: 47 | モデル: gpt-4o       │  │
│  │     [🔄 再構築]                         │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  質問を入力:                                  │
│  ┌────────────────────────────────┐ [送信]   │
│  │ Appleの主要なリスク要因は？     │          │
│  └────────────────────────────────┘          │
│                                              │
│  ─── 回答 ───────────────────────────────── │
│  Appleの10-K (FY2024) によると、主要なリスク  │
│  要因は以下の通りです:                        │
│  1. サプライチェーンの集中リスク ...           │
│  2. 為替変動リスク ...                        │
│  3. 規制環境の変化 ...                        │
│                                              │
│  📍 出典: Item 1A (p.13-28)                  │
│  🎯 信頼度: 95%                              │
│                                              │
│  ─── プリセット質問 ─────────────────────── │
│  [事業概要] [リスク要因] [業績見通し]          │
│  [競争優位性] [財務パフォーマンス]             │
└─────────────────────────────────────────────┘
```

**HTMX連携:**
- 質問送信: `POST /api/stocks/{company_id}/rag/ask` → 回答HTML部分更新
- インデックス構築: `POST /api/stocks/{company_id}/rag/index` → プログレス表示
- プリセット質問: クリックで質問入力欄にプリフィル + 自動送信

#### 13.3.9 Discord Botコマンド

```
!rag ask <ticker> <質問>     — ファイリングに対する質疑応答
!rag analyze <ticker>        — デフォルト分析実行
```

#### 13.3.10 LLMバックエンド連携

**本プロジェクトの方針:** PageIndexのオリジナルはOpenAI API (GPT-4o) を使用しているが、本プロジェクトではローカルLLMを使用する。クラウドAPIへの依存を排除し、プライバシーとコスト管理を優先する。

**使用モデル:**

| モデル | パラメータ数 | 量子化 | 用途 |
|-------|------------|--------|------|
| `gpt-oss-20B` | 20B | Q8_0 | 標準分析（軽量・高速） |
| `Qwen3.5-27B` | 27B | — | 中規模・高バランス分析 |
| `gpt-oss-120B` | 120B | — | 高精度分析（複雑な文書向け） |

**対応LLMバックエンド:**

PageIndexは `litellm` 経由でLLM呼び出しを行うため、以下のバックエンドをサポート:

| バックエンド | litellm model指定 | 状態 | 備考 |
|-------------|------------------|------|------|
| **Ollama** (ローカル) | `ollama/gptoss20b:q8` | 既存環境 | 現行のLLM分析で使用中 |
| **LM Studio** (ローカル) | `lm_studio/gpt-oss-20b` | **検討中** | OpenAI互換APIを提供、GUIベースのモデル管理が容易 |
| OpenAI (クラウド) | `gpt-4o-2024-11-20` | 非推奨 | PageIndexオリジナルのデフォルト。本プロジェクトでは不使用 |
| Anthropic (クラウド) | `anthropic/claude-sonnet-4-6` | 非推奨 | 同上 |

**Ollama使用時の設定:**
```yaml
pageindex:
  enabled: true
  backend: ollama
  model: "ollama/gptoss20b:q8"   # 標準 (20B Q8)
  # model: "ollama/gptoss120b"   # 高精度 (120B)
```

**LM Studio使用時の設定 (検討中):**
```yaml
pageindex:
  enabled: true
  backend: lm_studio
  model: "lm_studio/gpt-oss-20b"
  lm_studio_base_url: "http://localhost:1234/v1"  # LM StudioのOpenAI互換エンドポイント
```

> **LM Studio検討理由:** GUIベースのモデル管理、OpenAI互換API、GGUF量子化モデルの簡易ロード、GPU割り当ての視覚的管理。Ollamaと比較してモデル切り替えや設定変更が容易。litellmは `openai/` プレフィクスで `base_url` を指定することでLM Studioに接続可能。

**モデル選択ガイドライン:**

| シナリオ | 推奨モデル | 理由 |
|---------|-----------|------|
| 日常的なインデックス生成・Q&A | gpt-oss-20B (Q8) | VRAM ~24GB、応答速度が速い |
| 中規模文書の分析・多言語Q&A | Qwen3.5-27B | 20Bと120Bの中間、日本語・英語の理解に優れる |
| 複雑な10-K (100ページ超) の深い分析 | gpt-oss-120B | 長文理解・推論能力が高い |
| TOC検出・セクション分類 | gpt-oss-20B / Qwen3.5-27B | 構造認識タスクには十分 |
| 財務数値の解釈・比較質問 | Qwen3.5-27B / gpt-oss-120B | 数値推論に強い |

### 13.4 実装上の考慮事項

1. **PDF取得**: 現行はSEC提出書類をHTMLで保存 (`raw.html`)。PageIndexはPDF入力を前提とするため、SEC EDGARからPDF版を別途取得するか、HTML→PDF変換が必要
2. **litellmとローカルLLMの互換性**: litellmはOllamaバックエンド (`ollama/model-name`) およびLM Studio (`openai/model-name` + `base_url`) をサポート。既存のOllama直接呼び出し (`httpx` + `/api/generate`) と共存可能
3. **ローカルLLMの性能考慮**: PageIndexオリジナルはGPT-4o (推定200B+パラメータ) を前提設計。gpt-oss-20Bでは精度低下の可能性があり、`max_pages_per_node` や `max_tokens_per_node` の調整、リトライ回数の増加が必要になる場合がある。Qwen3.5-27Bは20Bと120Bの中間として精度と速度のバランスが良い候補。高精度が必要な場合はgpt-oss-120Bを使用
4. **インデックス生成コスト**: 1文書あたり数十回のLLM呼び出しが発生。ローカルLLMのためAPI課金は不要だが、GPU時間とVRAMが制約。大量ファイリングの一括インデックス化には逐次処理が現実的
5. **非同期処理**: PageIndexの `page_index.py` は `async` 関数を多用。FastAPIとの統合で `asyncio.run()` のネスト問題に注意
6. **既存分析との共存**: 現行の正規表現ベースセクション抽出 (`llm_extraction.py`) とOllama分析 (`llm_service.py`) は維持。PageIndex RAGはオプショナルな追加機能として並行動作
7. **LM Studio統合時の注意**: LM StudioはOpenAI互換APIを提供するが、structured output (`response_format`) のサポート状況はモデル依存。litellmの `openai/` プレフィクスと `api_base` パラメータで接続

---

## 14. 環境構築手順 (※PageIndex追加後)

```bash
# 1. 仮想環境
python3 -m venv .venv
source .venv/bin/activate

# 2. パッケージインストール
pip install -e ".[dev]"

# 3. 設定
cp config/settings.yaml.example config/settings.yaml
# SEC EDGAR email を設定

# 4. 環境変数 (.env)
WEB_PASSWORD=your_password
WEB_SESSION_SECRET=your_secret
DISCORD_TOKEN=your_token (Discord Bot使用時)
EDINET_API_KEY=your_key (日本株使用時)
PAGEINDEX_API_KEY=your_key (PageIndex OpenAI/Anthropic使用時)

# 5. テスト
python -m pytest tests/ -q

# 6. 起動
stock-analyzer serve          # Webサーバー
stock-analyzer bot            # Discord Bot
stock-analyzer jobs sync US_AAPL  # 単一企業同期
```

---

## 15. ディレクトリ構造

```
Stock_Analyzer/
├── config/
│   ├── settings.yaml              # メイン設定
│   ├── us_gaap_mapping.yaml       # US-GAAPタグマッピング
│   ├── ifrs_mapping.yaml          # IFRSタグマッピング
│   └── edinet_taxonomy_mapping.yaml # EDINETマッピング
├── data/
│   ├── stock_analyzer.db          # SQLiteデータベース
│   ├── filings/                   # ダウンロード済みファイリング
│   └── logs/                      # ログファイル
├── docs/
│   └── requirements_specification.md  # 本ドキュメント
├── src/stock_analyzer/
│   ├── __init__.py
│   ├── __main__.py                # エントリポイント
│   ├── config.py                  # 設定管理
│   ├── logging_config.py          # ログ設定
│   ├── models/                    # SQLAlchemy モデル (9ファイル + 1ファイル)
│   │   └── document_index.py      # [新規] ツリーインデックスモデル
│   ├── ingestion/                 # データ取得 (7ファイル)
│   ├── services/                  # ビジネスロジック (17ファイル + RAG 2ファイル)
│   │   ├── pageindex_service.py   # [新規] PageIndexラッパー
│   │   └── rag_service.py         # [新規] RAG質疑応答
│   ├── cli/                       # CLIコマンド (15ファイル + RAG 1ファイル)
│   │   └── rag.py                 # [新規] RAG CLIコマンド
│   ├── bot/                       # Discord Bot (2ファイル)
│   ├── shared/                    # 共有ユーティリティ (1ファイル)
│   └── web/                       # FastAPI Web (10ファイル + テンプレート)
│       ├── auth.py
│       ├── dependencies.py
│       ├── routes/                # ルートハンドラ (7ファイル + RAG 1ファイル)
│       │   └── rag.py             # [新規] RAG Webルート
│       ├── static/                # CSS
│       └── templates/             # Jinja2テンプレート (14ファイル + RAG 1ファイル)
│           └── pages/rag.html     # [新規] RAG質疑応答UI
├── tests/
│   ├── conftest.py
│   ├── unit/                      # ユニットテスト (20ファイル)
│   └── integration/               # 統合テスト (2ファイル)
└── pyproject.toml                 # プロジェクト定義
```
