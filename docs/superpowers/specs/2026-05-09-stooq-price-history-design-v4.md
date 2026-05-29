# Stooq Price History Ingestion - Design & Context for AI Review (v4)

> <meta>
> <version>4.0</version>
> <created>2026-05-09</created>
> <author>Stock Analyze System AI Agent</author>
> <status>Ready for implementation (revised)</status>
> <goal>SEC全登録企業（~10,376社）の直近10年分株価データをstooq.comから取得し、SQLite `price_history` テーブルに保存するCLIコマンドを実装する</goal>
> <revision>
>   - v1 initial design
>   - v2 fixes: session access, SQLite bind params chunking, __init__.py import,
>               processing time estimate, error handling scope, User-Agent
>   - v3 fixes: date generation in tests, row ordering consistency, env fallback test,
>               created_at type, StooqAuthError alignment, explicit TIMEOUT/DB_ERROR
>   - v4 fixes: auth fail-fast (StooqAuthError exits immediately), handler-level env fallback,
>               UNKNOWN vs ERROR naming alignment, data/ directory creation
> </revision>
> </meta>

---

## <section name="project-overview">

### プロジェクト概要

本システムは米国・日本株式の財務分析を行うPython製CLI/Webアプリケーションです。
既存のデータソースとしてSEC EDGAR（財務データ）、Yahoo Finance（リアルタイム株価）、Google Sheets（スクリーニング指標）を持ちます。

今回の追加要件は、**stooq.comから無料で提供される日次終値（EOD）の履歴データを一括取得し、分析基盤に統合**することです。

### 重要な制約

- **実行頻度**: 初回のみ（1回限り）
- **処理時間許容**: ~2.9時間（1.0 req/sec設定）
- **対象銘柄数**: DB内 `US_*` 企業 10,376社
- **保存期間**: 直近10年分（~2,520営業日/社）
- **総レコード見積**: 約2,600万行
- **エラー処理**: スキップしてログ保存（リトライなし）

### 前回からの変更点（v3 → v4）

| 項目 | v3 | v4 |
|------|-----|-----|
| **StooqAuthError処理** | ループ継続（全銘柄で2.9h無駄） | **即座にexit(1)でfail-fast** |
| **env fallback** | parser defaultのみ | **handler内でも再確認**（.envロード順対策） |
| **UNKNOWN vs ERROR** | 実装はERROR、specはUNKNOWN | **統一してUNKNOWN** |
| **data/ディレクトリ** | 存在確認なし | **mkdir(parents=True, exist_ok=True)** |

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
**マイグレーション**: Alembicなし。`Base.metadata.create_all()` で自動作成（`models/__init__.py` にimportが必要）。

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

#### <file path="src/stock_analyze_system/models/__init__.py" role="モデル登録（要修正）">

```python
# 現状（要修正）
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.financial_data import FinancialData
# ...

# 修正後（PriceHistory追加）
from stock_analyze_system.models.price_history import PriceHistory  # ADD
```

**ポイント**: `PriceHistory` を `__init__.py` に import しないと `Base.metadata.create_all()` に登録されない。

</file>

#### <file path="src/stock_analyze_system/repositories/base.py" role="リポジトリ基底">

```python
class BaseRepository(Generic[T]):
    def __init__(self, session: AsyncSession, model_class: type[T]):
        self._session = session
        self._model = model_class
    
    async def upsert(self, filters: dict, data: dict) -> T:
        # INSERT ... ON CONFLICT DO UPDATE
        # 900 bind parameters で分割する実装あり
```

**ポイント**: `PriceHistoryRepository`はこれを継承。`upsert_many` でSQLite bind parameter上限（999）を考慮してチャンク分割する。

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

#### <file path="src/stock_analyze_system/cli/container.py" role="サービスコンテナ（要修正）">

```python
# 現状
@dataclass
class ServiceContainer:
    company_service: CompanyService
    financial_service: FinancialService
    # ...
    screening_universe_service: ScreeningUniverseService | None = None

# 修正後（session追加）
@dataclass
class ServiceContainer:
    company_service: CompanyService
    financial_service: FinancialService
    # ...
    screening_universe_service: ScreeningUniverseService | None = None
    session: AsyncSession | None = None  # ADD
```

**ポイント**: `setup_services` で `container.session = session` を注入する。使用時はNone guardが必要。

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

#### 異常レスポンスパターン

| パターン | 例 | 対応 |
|---------|-----|------|
| **正常CSV** | `Date,Open,High,...` | そのままパース |
| **APIキー無効** | `Get your apikey:...` | `StooqAuthError`（**fail-fast**） |
| **ティッカー不在** | 404 Not Found | `StooqNotFoundError` |
| **HTMLページ** | `<html>...` | `StooqParseError` |
| **空レスポンス** | ` ` | `StooqParseError` |

#### データ特性

| 特性 | 値 |
|------|-----|
| **提供データ** | 全歴史（IPO以来） |
| **AAPL行数** | 10,499行（1984-09-07 〜 2026-05-08） |
| **MSFT行数** | 10,116行（1986-03-13 〜 2026-05-08） |
| **遅延** | T+1（前営業日終値、米国市場クローズ後約4〜8時間） |
| **認証** | APIキー必要（CAPTCHAで取得） |
| **レート制限** | 不明（安全のため1.0 req/secを設定） |
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

#### SQLite Bind Parameter 上限対策

```python
_CHUNK_SIZE = 100  # 100行 × 7カラム = 700 bind params < 999上限

def upsert_many_chunked(rows: list[dict]):
    for i in range(0, len(rows), _CHUNK_SIZE):
        chunk = rows[i:i + _CHUNK_SIZE]
        # INSERT ... ON CONFLICT DO UPDATE
```

</section>

---

## <section name="architecture">

### アーキテクチャ・データフロー

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   companies     │────▶│ StooqDownloader  │────▶│ price_history   │
│  (US_*, ticker) │     │  (1並列・1秒間隔) │     │   (SQLite)      │
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
2. **既存スキップ（オプション）**: `--skip-existing` 指定時は `price_history` に既存の企業を除外
3. **シーケンシャルダウンロード**: 1社ずつ、1秒間隔でstooq APIを呼び出し
4. **CSVパース**: レスポンスを`csv.DictReader`でパース、異常パターン検出
5. **期間フィルタ**: 直近10年分（`date >= today - 10years`）のみ抽出
6. **DB書き込み**: 1銘柄ごとにチャンク分割 `upsert_many` + `COMMIT`
7. **エラーハンドリング**: 例外発生時は`rollback` + JSONエラーログに記録

#### 制御パラメータ

| 項目 | 値 | 理由 |
|------|-----|------|
| 同時接続数 | **1（シーケンシャル）** | stooqサーバー負荷最小化 |
| レート制限 | **1秒間隔**（1.0 req/sec） | 2.9時間で完了、BANリスク抑制 |
| タイムアウト | 30秒 | 長期ハング防止 |
| リトライ | なし | 初回実行なので手動再試行で十分 |
| COMMIT単位 | 1銘柄ごと | メモリ節約・エラー分離 |
| チャンクサイズ | 100行 | SQLite bind parameter上限（999）対策 |

#### 見積処理時間

```
10,376社 × 1秒 = 10,376秒 ≒ 2.9時間（理論値）
+ CSV展開・DB書き込み：+10〜20%
実測：約2.9〜3.5時間見込み
```

</section>

---

## <section name="implementation-plan">

### 実装計画（タスク一覧）

#### Task 0: ADR作成
- **ファイル**: `docs/adr/001-stooq-historical-price-source.md`
- **内容**: stooq採用理由、代替案比較、影響

#### Task 1: PriceHistoryモデル + __init__.py登録
- **新規**: `src/stock_analyze_system/models/price_history.py`
- **修正**: `src/stock_analyze_system/models/__init__.py`（import追加）
- **テスト**: `tests/unit/models/test_price_history.py`
- **内容**: SQLAlchemyモデル定義 + `Base.metadata.create_all()` 登録

#### Task 2: PriceHistoryリポジトリ（チャンク分割）
- **新規**: `src/stock_analyze_system/repositories/price_history.py`
- **テスト**: `tests/unit/repositories/test_price_history_repo.py`
- **内容**: `upsert_many`メソッド（SQLite `ON CONFLICT DO UPDATE` + 100行チャンク）

#### Task 3: StooqPriceClient（User-Agent + 異常検出）
- **新規**: `src/stock_analyze_system/ingestion/stooq.py`
- **テスト**: `tests/unit/ingestion/test_stooq.py`
- **内容**: CSVダウンロード、パース、期間フィルタ、レート制限、HTML/CAPTCHA/Auth検出

#### Task 4: CLIコマンド（session対応 + skip-existing + auth fail-fast）
- **新規**: `src/stock_analyze_system/cli/stooq.py`
- **テスト**: `tests/unit/cli/test_stooq_cli.py`
- **内容**: `stooq download` サブコマンド、session利用、rollback、auth即exit

#### Task 5: app.py統合 + container.py修正
- **修正**: `src/stock_analyze_system/cli/app.py`（パーサー登録）
- **修正**: `src/stock_analyze_system/cli/container.py`（sessionフィールド追加）
- **内容**: `stooq.register_parser(subparsers)`、setup_servicesでsession注入

#### Task 6: 統合テスト
- **新規**: `tests/integration/test_stooq_download.py`
- **内容**: 実際のAPIキーを使ったE2Eテスト（`STOOQ_API_KEY`環境変数必要）

</section>

---

## <section name="error-handling">

### エラーハンドリング仕様

#### エラーカテゴリ

| コード | 説明 | 例 | 例外クラス | 処理 |
|--------|------|-----|-----------|------|
| `NOT_FOUND` | HTTP 404 | stooqに存在しないティッカー（ADR、上場廃止等） | `StooqNotFoundError` | スキップ、ログ保存 |
| `AUTH_ERROR` | APIキー無効 | `Get your apikey` レスポンス | `StooqAuthError` | **Fail-fast: exit(1)** |
| `TIMEOUT` | 30秒経過 | サーバー応答なし | `httpx.TimeoutException` | スキップ、ログ保存 |
| `PARSE_ERROR` | CSVフォーマット異常 | HTMLレスポンス、空レスポンス、ヘッダー欠落 | `StooqParseError` | スキップ、ログ保存 |
| `EMPTY` | パース後0行 | 期間フィルタですべて除外 | （スキップ、エラーログ） |
| `DB_ERROR` | DB書き込み失敗 | upsert_many/commit失敗 | `SQLAlchemyError` | rollback、スキップ、ログ保存 |
| `UNKNOWN` | その他例外 | ネットワークエラー等 | `Exception` | rollback、スキップ、ログ保存 |

#### Auth Fail-fast 動作

```python
except StooqAuthError as exc:
    # Auth error is global (not ticker-specific): fail-fast
    await client.close()
    error_msg = f"Authentication failed for stooq API key: {exc}"
    logger.error(error_msg)
    print(f"ERROR: {error_msg}", file=sys.stderr)
    errors.append({...})
    _write_errors(errors)
    sys.exit(1)
```

**理由**: 無効なAPIキーは**全銘柄共通**の問題であり、ループ継続すると10,376社すべてで同じエラーが出て2.9h無駄になる。

#### エラーログ出力

```json
[
  {"ticker": "XYZ", "company_id": "US_XYZ", "reason": "NOT_FOUND", "timestamp": "2026-05-09T12:00:00Z"},
  {"ticker": "ABC", "company_id": "US_ABC", "reason": "DB_ERROR: IntegrityError", "timestamp": "2026-05-09T12:01:00Z"},
  {"ticker": "DEF", "company_id": "US_DEF", "reason": "TIMEOUT", "timestamp": "2026-05-09T12:02:00Z"},
  {"ticker": "GHI", "company_id": "US_GHI", "reason": "UNKNOWN: SomeException", "timestamp": "2026-05-09T12:03:00Z"}
]
```

**保存先**: `data/stooq_errors_2026-05-09.json`
**ディレクトリ作成**: `Path("data").mkdir(parents=True, exist_ok=True)` で確実に作成

#### 最終レポート（標準出力）

```
Download Summary
========================================
Total companies: 10376
Success: 9500
Failed: 876
Elapsed: 2h 55m 30s
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
| `--apikey` | str | `STOOQ_API_KEY` env | stooq APIキー（環境変数fallback） |
| `--limit` | int | None | 処理する企業数上限（テスト用） |
| `--skip-existing` | flag | False | 既存データがある企業をスキップ |
| `--dry-run` | flag | False | DB書き込みをスキップして件数確認のみ |

#### 使用例

```bash
# 本番実行（全10,376社）
python -m stock_analyze_system.cli.app stooq download --years 10 --apikey "YOUR_KEY"

# 環境変数からAPIキー取得
export STOOQ_API_KEY="YOUR_KEY"
python -m stock_analyze_system.cli.app stooq download --years 10

# テスト実行（100社のみ）
python -m stock_analyze_system.cli.app stooq download --years 10 --apikey "YOUR_KEY" --limit 100

# ドライラン（DBに書き込まない）
python -m stock_analyze_system.cli.app stooq download --years 10 --apikey "YOUR_KEY" --dry-run

# 再実行（既存スキップ）
python -m stock_analyze_system.cli.app stooq download --years 10 --apikey "YOUR_KEY" --skip-existing
```

</section>

---

## <section name="resolved-questions">

### 解決済み Open Questions

#### 1. ServiceContainer/sessionアクセス
**解決**: `ServiceContainer` に `session: AsyncSession | None = None` を追加。`setup_services` で `container.session = session` を注入。CLIハンドラは `services.session` を使用し、None guardを入れる。

#### 2. マイグレーション
**解決**: Alembicなし。`Base.metadata.create_all()` で自動作成。`models/__init__.py` に `PriceHistory` import を追加するタスクを計画に含める。

#### 3. APIキー管理
**解決**: `--apikey` オプション + `STOOQ_API_KEY` 環境変数fallback。parser defaultで読み取るが、`.env`ロード順の問題を避けるためhandler内でも `os.getenv("STOOQ_API_KEY")` で再確認。

#### 4. 再開戦略
**解決**: `--skip-existing` オプション追加。`UNIQUE(company_id, date)` により全体再実行は冪等だが、既存企業スキップで時間短縮可能。

#### 5. CSVパース
**解決**: `csv.DictReader` を使用。HTML/CAPTCHA/Auth/No data レスポンスのテストを追加。

#### 6. 利用規約対応
**解決**: User-Agentに `Stock-Analyze-System/1.0 (research-only)` を設定。1.0 req/secで低負荷。生データの再配布は行わず社内分析用途に限定。

#### 7. Authエラー処理
**解決**: `StooqAuthError` は **fail-fast**（即座にexit(1)）。無効なAPIキーは全銘柄共通の問題なので、ループ継続は無意味。

#### 8. エラーログ保存
**解決**: `Path("data").mkdir(parents=True, exist_ok=True)` でディレクトリを確実に作成してから書き込み。

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

**ポイント**: `PriceHistoryRepository`では`upsert_many`を新設し、SQLiteの`ON CONFLICT DO UPDATE`を使う。bind parameter上限対策で100行チャンクに分割。

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

**ポイント**: `stooq.py`も同じパターンで実装する。`services.session` でDBアクセス。

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

@pytest.mark.asyncio
async def test_fetch_history_rejects_auth_error(httpx_mock):
    httpx_mock.add_response(url="...", text="Get your apikey:")
    
    client = StooqPriceClient(api_key="invalid", rate=1000)
    with pytest.raises(StooqAuthError):
        await client.fetch_history("AAPL")
```

#### 統合テスト（実ネットワーク）

```python
@pytest.mark.asyncio
async def test_stooq_client_fetch_aapl_real():
    import os
    api_key = os.getenv("STOOQ_API_KEY")
    if not api_key:
        pytest.skip("STOOQ_API_KEY not set")
    
    client = StooqPriceClient(api_key=api_key, rate=1.0)
    rows = await client.fetch_history("AAPL", years=1)
    assert len(rows) > 200  # ~1 year分
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