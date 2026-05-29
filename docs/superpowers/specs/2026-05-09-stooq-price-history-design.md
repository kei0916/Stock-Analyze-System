# Stooq Price History Ingestion — Design & Context for AI Review

> <meta>
> <version>1.0</version>
> <created>2026-05-09</created>
> <author>Stock Analyze System AI Agent</author>
> <status>Ready for implementation review</status>
> <goal>SEC全登録企業（~10,376社）の直近10年分株価データをstooq.comから取得し、SQLite `price_history` テーブルに保存するCLIコマンドを実装する</goal>
> </meta>

---

## <section name="project-overview">

### プロジェクト概要

本システムは米国・日本株式の財務分析を行うPython製CLI/Webアプリケーションです。
既存のデータソースとしてSEC EDGAR（財務データ）、Yahoo Finance（リアルタイム株価）、Google Sheets（スクリーニング指標）を持ちます。

今回の追加要件は、**stooq.comから無料で提供される日次終値（EOD）の履歴データを一括取得し、分析基盤に統合**することです。

### 重要な制約

- **実行頻度**: 初回のみ（1回限り）
- **処理時間許容**: 3〜4時間
- **対象銘柄数**: DB内 `US_*` 企業 10,376社
- **保存期間**: 直近10年分（~2,520営業日/社）
- **総レコード見積**: 約2,600万行
- **エラー処理**: スキップしてログ保存（リトライなし）

</section>

---

## <section name="existing-infrastructure">

### 既存インフラ構成

#### <file path="src/stock_analyze_system/models/base.py" role="ORM基盤">

```python
# キー要素
class Base(DeclarativeBase):
    pass

async def create_db_engine(db_path: str) -> AsyncEngine:
    return create_async_engine(f"sqlite+aiosqlite:///{db_path}")

async def get_session(engine: AsyncEngine) -> AsyncSession:
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
```

**ポイント**: `PriceHistory`モデルはこの`Base`を継承する。DBはSQLite（aiosqlite）。

</file>

#### <file path="src/stock_analyze_system/models/company.py" role="企業マスタ">

```python
class Company(Base):
    __tablename__ = "companies"
    
    id: Mapped[str] = mapped_column(primary_key=True)      # e.g. "US_AAPL"
    ticker: Mapped[str | None]
    name: Mapped[str]
    market: Mapped[str | None]
    cik: Mapped[str | None]
    sector: Mapped[str | None]
    # ...
```

**ポイント**: `US_*` で `ticker IS NOT NULL` の企業が対象。現在10,376社該当。

</file>

#### <file path="src/stock_analyze_system/repositories/base.py" role="リポジトリ基底">

```python
class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model_class: type[T]):
        self._session = session
        self._model = model_class
    
    async def upsert(self, filters: dict, data: dict) -> T:
        # INSERT ... ON CONFLICT DO UPDATE
```

**ポイント**: `PriceHistoryRepository`はこれを継承し、`upsert_many`を追加する。

</file>

#### <file path="src/stock_analyze_system/ingestion/base.py" role="HTTPクライアント基盤">

```python
class AsyncRateLimiter:
    """Token-bucket async rate limiter."""
    def __init__(self, rate: float, *, burst: int = 1):
        # rate = requests per second
        
    async def acquire(self) -> None:
        # Wait if necessary to respect rate limit

class BaseClient:
    """httpx.AsyncClient wrapper with retry logic."""
    def __init__(self, rate: float, headers: dict | None = None):
        self._client = httpx.AsyncClient()
        self._rate_limiter = AsyncRateLimiter(rate)
```

**ポイント**: `StooqPriceClient`は`AsyncRateLimiter`を直接使用（`YahooFinanceClient`と同様）。

</file>

#### <file path="src/stock_analyze_system/ingestion/yahoo_finance.py" role="既存株価クライアント">

```python
class YahooFinanceClient:
    def __init__(self, rate: float = 2.0):
        self._rate_limiter = AsyncRateLimiter(rate=rate)
    
    async def get_stock_price(self, ticker: str) -> dict | None:
        # asyncio.to_thread(yfinance.Ticker(ticker).info)
    
    async def get_price_history(self, ticker: str, period: str = "10y") -> list[dict]:
        # Returns list of {"date", "close", "volume"}
```

**ポイント**: `get_price_history`は存在するが、現在どこからも呼ばれていない（未使用）。

</file>

#### <file path="src/stock_analyze_system/cli/app.py" role="CLIルート">

```python
from stock_analyze_system.cli import (
    company, filings, financial, jobs, quotes, rag, screening, serve, target,
    valuation, watchlist,
)

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock-analyze")
    subparsers = parser.add_subparsers(dest="command")
    company.register_parser(subparsers)
    # ... stooq.register_parser(subparsers) を追加
```

**ポイント**: 新しい`stooq`サブコマンドをここに登録する。

</file>

#### <file path="src/stock_analyze_system/cli/container.py" role="サービスコンテナ">

```python
@dataclass
class ServiceContainer:
    company_service: CompanyService
    financial_service: FinancialService
    valuation_service: ValuationService
    filing_service: FilingService
    # ...
    screening_universe_service: ScreeningUniverseService | None = None
    screening_service: ScreeningService | None = None
    screening_metrics_service: ScreeningMetricsService | None = None
```

**ポイント**: `session`へのアクセス方法が未確定。`services._session`が存在するか、別の方法が必要か要確認。

</file>

#### <file path="src/stock_analyze_system/repositories/company.py" role="企業リポジトリ">

```python
class CompanyRepository(BaseRepository[Company]):
    async def find_existing_ids(self, ids: list[str]) -> set[str]:
        # ...
    
    async def list_all(self) -> list[Company]:
        # All companies query
```

**ポイント**: `list_all`または同等のメソッドでUS企業一覧を取得できる。

</file>

</section>

---

## <section name="stooq-api-spec">

### stooq.com API仕様（調査済み）

#### エンドポイント

```http
GET https://stooq.com/q/d/l/?s={ticker}.us&i=d&apikey={api_key}
```

| パラメータ | 説明 | 例 |
|-----------|------|-----|
| `s` | stooqシンボル | `aapl.us` |
| `i` | 間隔 | `d` (daily) |
| `apikey` | APIキー | `LynVgRC4ch2Ev8eMPF1kabHrqXJ0ZptI` |

#### レスポンス形式

```csv
Date,Open,High,Low,Close,Volume
2026-05-08,290.01,294.76,290.01,293.745,13288825
2026-05-07,289.27,292.13,285.78,287.44,45224300
...
```

#### データ特性

| 特性 | 値 |
|------|-----|
| **提供データ** | 全歴史（IPO以来） |
| **AAPL行数** | 10,499行（1984-09-07 〜 2026-05-08） |
| **MSFT行数** | 10,116行（1986-03-13 〜 2026-05-08） |
| **遅延** | T+1（前営業日終値、米国市場クローズ後約4〜8時間） |
| **認証** | APIキー必要（CAPTCHAで取得） |
| **レート制限** | 不明（安全のため2秒間隔を設定） |
| **利用規約** | §5.3「再配布禁止」、§6.1 S&Pデータ「非商業利用」 |

#### シンボル変換ルール

```python
def to_stooq_symbol(db_ticker: str) -> str:
    """DB ticker (e.g. 'AAPL') -> stooq symbol (e.g. 'aapl.us')"""
    return f"{db_ticker.lower()}.us"
```

</section>

---

## <section name="database-design">

### DBスキーマ設計

#### 新規テーブル: `price_history`

```sql
CREATE TABLE price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id TEXT NOT NULL,        -- e.g. "US_AAPL"
    ticker TEXT NOT NULL,            -- e.g. "AAPL"
    date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    source TEXT DEFAULT 'stooq',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, date)
);

CREATE INDEX idx_price_history_company_date 
    ON price_history(company_id, date);
CREATE INDEX idx_price_history_date 
    ON price_history(date);
```

#### 設計意図

| 要素 | 理由 |
|------|------|
| `company_id + date` UNIQUE | 同じ企業・同日の重複を排除 |
| `ticker` カラム | stooqシンボルとの対応を追跡 |
| `source` カラム | 将来のYahoo Finance等追加に備える |
| `volume` をREAL | 大きな数値（億単位）でも問題ない |
| 日付降順インデックス | 時系列クエリのパフォーマンス |

</section>

---

## <section name="architecture">

### アーキテクチャ・データフロー

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   companies     │────▶│ StooqDownloader  │────▶│ price_history   │
│  (US_*, ticker) │     │  (1並列・2秒間隔) │     │   (SQLite)      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌──────────────┐
                        │ error_log    │
                        │ (JSONファイル)│
                        └──────────────┘
```

#### 処理フロー詳細

1. **企業一覧取得**: `companies`テーブルから `US_*` かつ `ticker IS NOT NULL` をSELECT
2. **シーケンシャルダウンロード**: 1社ずつ、2秒間隔でstooq APIを呼び出し
3. **CSVパース**: レスポンスを`csv.DictReader`でパース
4. **期間フィルタ**: 直近10年分（`date >= today - 10years`）のみ抽出
5. **DB書き込み**: 1銘柄ごとに`upsert_many` + `COMMIT`
6. **エラーハンドリング**: 例外発生時はスキップしてJSONエラーログに記録

#### 制御パラメータ

| 項目 | 値 | 理由 |
|------|-----|------|
| 同時接続数 | **1（シーケンシャル）** | stooqサーバー負荷最小化 |
| レート制限 | **2秒間隔**（0.5 req/sec） | 安全側に倒す |
| タイムアウト | 30秒 | 長期ハング防止 |
| リトライ | なし | 初回実行なので手動再試行で十分 |
| COMMIT単位 | 1銘柄ごと | メモリ節約・エラー分離 |

#### 見積処理時間

```
10,376社 × 2秒 = 20,752秒 ≒ 5.8時間（理論値）
実測ではCSV展開・DB書き込みで短縮され、3〜4時間見込み
```

</section>

---

## <section name="implementation-plan">

### 実装計画（タスク一覧）

#### Task 0: ADR作成
- **ファイル**: `docs/adr/001-stooq-historical-price-source.md`
- **内容**: stooq採用理由、代替案比較、影響

#### Task 1: PriceHistoryモデル
- **新規**: `src/stock_analyze_system/models/price_history.py`
- **テスト**: `tests/unit/models/test_price_history.py`
- **内容**: SQLAlchemyモデル定義

#### Task 2: PriceHistoryリポジトリ
- **新規**: `src/stock_analyze_system/repositories/price_history.py`
- **テスト**: `tests/unit/repositories/test_price_history_repo.py`
- **内容**: `upsert_many`メソッド（SQLite `ON CONFLICT DO UPDATE`）

#### Task 3: StooqPriceClient
- **新規**: `src/stock_analyze_system/ingestion/stooq.py`
- **テスト**: `tests/unit/ingestion/test_stooq.py`
- **内容**: CSVダウンロード、パース、期間フィルタ、レート制限

#### Task 4: CLIコマンド
- **新規**: `src/stock_analyze_system/cli/stooq.py`
- **テスト**: `tests/unit/cli/test_stooq_cli.py`
- **内容**: `stooq download --years 10 --apikey KEY` サブコマンド

#### Task 5: app.py統合
- **修正**: `src/stock_analyze_system/cli/app.py`
- **内容**: `stooq.register_parser(subparsers)` を追加

#### Task 6: 統合テスト
- **新規**: `tests/integration/test_stooq_download.py`
- **内容**: 実際のAPIキーを使ったE2Eテスト（`STOOQ_API_KEY`環境変数必要）

</section>

---

## <section name="error-handling">

### エラーハンドリング仕様

#### エラーカテゴリ

| コード | 説明 | 例 |
|--------|------|-----|
| `NOT_FOUND` | HTTP 404 | stooqに存在しないティッカー（ADR、上場廃止等） |
| `TIMEOUT` | 30秒経過 | サーバー応答なし |
| `PARSE_ERROR` | CSVフォーマット異常 | 空レスポンス、ヘッダー欠落 |
| `EMPTY` | パース後0行 | 期間フィルタですべて除外 |
| `UNKNOWN` | その他例外 | ネットワークエラー等 |

#### エラーログ出力

```json
[
  {"ticker": "XYZ", "company_id": "US_XYZ", "reason": "NOT_FOUND", "timestamp": "2026-05-09T12:00:00Z"},
  {"ticker": "ABC", "company_id": "US_ABC", "reason": "TIMEOUT", "timestamp": "2026-05-09T12:01:00Z"}
]
```

**保存先**: `data/stooq_errors_2026-05-09.json`

#### 最終レポート（標準出力）

```
Download Summary
========================================
Total companies: 10376
Success: 9500
Failed: 876
Elapsed: 3h 45m 12s
Errors saved to: data/stooq_errors_2026-05-09.json
```

</section>

---

## <section name="cli-spec">

### CLI仕様

```bash
python -m stock_analyze_system.cli.app stooq download --years 10 --apikey $STOOQ_API_KEY
```

#### オプション

| オプション | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `--years` | int | 10 | 保存する期間（年） |
| `--apikey` | str | 必須 | stooq APIキー |
| `--limit` | int | None | 処理する企業数上限（テスト用） |
| `--dry-run` | flag | False | DB書き込みをスキップして件数確認のみ |

#### 使用例

```bash
# 本番実行（全10,376社）
python -m stock_analyze_system.cli.app stooq download --years 10 --apikey "YOUR_KEY"

# テスト実行（100社のみ）
python -m stock_analyze_system.cli.app stooq download --years 10 --apikey "YOUR_KEY" --limit 100

# ドライラン（DBに書き込まない）
python -m stock_analyze_system.cli.app stooq download --years 10 --apikey "YOUR_KEY" --dry-run
```

</section>

---

## <section name="open-questions">

### 未解決・要確認ポイント

以下はCodexまたは開発者レビューで解決すべき項目です：

#### 1. ServiceContainerからのsessionアクセス方法
```
現状: ServiceContainerはdataclassで各serviceを持つが、sessionは直接持たない可能性あり
要確認: services._session が存在するか、services.company_service._session のように間接アクセスが必要か
```

#### 2. マイグレーション方法
```
要確認: 本システムはAlembic等のマイグレーションツールを使用しているか
もしない場合: SQLiteファイル削除＆再作成で対応するか、手動ALTER TABLEが必要か
```

#### 3. APIキーの管理方針
```
オプションA: 環境変数 STOOQ_API_KEY のみ（推奨：セキュリティ）
オプションB: config/settings.yaml に追加（利便性）
オプションC: 両方（優先順位：環境変数 > configファイル）
```

#### 4. 中断・再開戦略
```
初回実行なのでresume機能は不要と決定済みだが、
10,376社処理中にクラッシュした場合の手動再開手順はドキュメント化すべき
（例：--limitとoffsetで範囲指定、またはprocessed_tickersログ）
```

#### 5. CSVパースの実装方針
```
オプションA: 標準ライブラリ csv.DictReader（軽量・依存なし）
オプションB: pandas.read_csv（機能豊富だがオーバーヘッド大）
推奨: Option A（10,376ファイル × 2,520行 = 軽量処理で十分）
```

#### 6. 利用規約対応
```
stooq.com Terms of Service §5.3「再配布禁止」に抵触するリスク
対応策:
  - ダウンロード間隔を2秒以上に設定（サーバー負荷軽減）
  - User-Agentに連絡先を記載
  - 生データの再配布は行わず、社内分析用途に限定
  - 有料APIへの移行を中長期で検討
```

</section>

---

## <section name="existing-file-snippets">

### 参考：既存ファイルのキー実装パターン

#### `AsyncRateLimiter` の使用例（`yahoo_finance.py`）

```python
class YahooFinanceClient:
    def __init__(self, rate: float = 2.0):
        self._rate_limiter = AsyncRateLimiter(rate=rate)
    
    async def get_stock_price(self, ticker: str) -> dict | None:
        await self._rate_limiter.acquire()
        # ... HTTP request
```

**ポイント**: `StooqPriceClient`も同様に`AsyncRateLimiter`を使う。

#### `BaseRepository.upsert` の実装パターン（`screening.py`）

```python
class ScreeningRepository(BaseRepository[ScreeningCache]):
    async def upsert_cache(self, company_id: str, data: dict) -> ScreeningCache:
        normalized = normalize_screening_cache_payload(data)
        return await self.upsert({"company_id": company_id}, normalized)
```

**ポイント**: `PriceHistoryRepository`では`upsert_many`を新設し、SQLiteの`ON CONFLICT DO UPDATE`を使う。

#### CLIの登録パターン（`screening.py`）

```python
def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("screening", help="スクリーニング")
    sub = parser.add_subparsers(dest="action", required=True)
    
    ur = sub.add_parser("refresh", help="SEC から universe を取り込み")
    ur.add_argument("--source", default="sec", choices=["sec"])
    
    parser.set_defaults(handler=handle)

async def handle(args: argparse.Namespace, services: "ServiceContainer") -> None:
    if args.action == "refresh":
        # ...
```

**ポイント**: `stooq.py`も同じパターンで実装する。

</section>

---

## <section name="test-strategy">

### テスト戦略

#### ユニットテスト（httpx_mock使用）

```python
# StooqPriceClient.fetch_history のテスト
@pytest.mark.asyncio
async def test_fetch_history_parses_csv(httpx_mock):
    csv_body = "Date,Open,High,Low,Close,Volume\n2021-05-08,100,105,99,104,1000000"
    httpx_mock.add_response(url="...", text=csv_body)
    
    client = StooqPriceClient(api_key="test", rate=1000)
    rows = await client.fetch_history("AAPL")
    assert len(rows) == 1
    assert rows[0]["close"] == 104.0
```

#### 統合テスト（実ネットワーク）

```python
@pytest.mark.asyncio
async def test_stooq_client_fetch_aapl_real():
    import os
    api_key = os.getenv("STOOQ_API_KEY")
    if not api_key:
        pytest.skip("STOOQ_API_KEY not set")
    
    client = StooqPriceClient(api_key=api_key, rate=0.5)
    rows = await client.fetch_history("AAPL", years=1)
    assert len(rows) > 200  # ~1年分
```

</section>

---

## <section name="appendix">

### 参考リンク・リソース

| リソース | URL |
|---------|-----|
| stooq.com トップ | https://stooq.com/ |
| stooq.com Terms | https://stooq.com/terms.html |
| AAPLデータページ | https://stooq.com/q/d/?s=aapl.us |
| CSVダウンロードURL | `https://stooq.com/q/d/l/?s=aapl.us&i=d&apikey=KEY` |
| 一括データページ | https://stooq.com/db/h/ |

### 既存の類似実装

| 機能 | ファイル | 参考ポイント |
|------|---------|-------------|
| HTTPクライアント+レート制限 | `ingestion/base.py` | `AsyncRateLimiter` |
| CSVデータ取得+パース | `ingestion/yahoo_finance.py` | `get_quarterly_financials` |
| サブコマンド追加 | `cli/screening.py` | パーサー登録パターン |
| DB一括UPSERT | `repositories/screening.py` | `upsert_cache` |
| エラーハンドリング+ログ | `services/screening_universe.py` | `enrich_with_yahoo` |

</section>