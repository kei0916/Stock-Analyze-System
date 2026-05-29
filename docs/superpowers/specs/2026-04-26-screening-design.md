# スクリーニング機能 設計 (2026-04-26)

## 1. 目的とスコープ

SEC に 10-K もしくは 20-F を提出する全企業 (US 企業 + ADR) を universe とし、PER / PBR / ROE 等の財務指標で候補銘柄を絞り込み、analysis_targets へ追加するためのバックエンド機能。Web UI (filter スライダー) はユーザーが別実装するため、本 spec の対象は **Service / Repository / JSON API / CLI / テスト** のみ。

### 1.1 確認済み要件

| 項目 | 内容 |
|---|---|
| ユースケース | 広い銘柄プールの初期スクリーニング → analysis_targets 投入 |
| Universe | SEC `company_tickers_exchange.json` から取得 (US + ADR、Phase 1 では EDINET 除外) |
| Filter スコープ | `ScreeningCache` の全 numeric 18 項目 + categorical 3 項目 (sector/industry/exchange) |
| Filter 入力 UI | **本 spec 対象外** (ユーザーがヒストグラム付き range slider を別途実装) |
| バックエンド | `ScreeningUniverseService` (write) と `ScreeningService` (read-only query) の二層 |
| 投入手段 | CLI (`stock-analyze screening universe refresh` / `... refresh`) |
| 結果出力 | JSON API + CLI の表 / `--json` / analysis_targets への追加 |
| エラー方針 | 1 ticker の Yahoo 失敗は warn + skip (R7 パターン) |

### 1.2 既存資産の流用

現時点で scaffolding は揃っている:

- `models/screening.py` の `ScreeningCache` (PK=company_id、 18 numeric + 3 categorical + メタ列)
- `repositories/screening.py` の `ScreeningRepository` (`get_cache` / `upsert_cache` / `list_stale`)
- `ingestion/sec_edgar.py` の `SecEdgarClient` (拡張で `list_universe()` を追加)
- `ingestion/yahoo_finance.py` の `YahooFinanceClient.get_screening_info(ticker)`
- `services/analysis_target.py` の `AnalysisTargetService.add_from_screening(company_ids)`
- `cli/container.py` の `screening_service: object | None = None` placeholder

placeholder の `web/routes/screening.py` (GET `/screening` で `placeholder.html` を返す) と `web/templates/screening/placeholder.html` は本 Phase で削除し、JSON API ルーターに置き換える。

---

## 2. アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────────┐
│ CLI (cli/screening.py)                                              │
│  universe refresh / refresh / run / add-targets / fields            │
└──────┬───────────────┬──────────────────────────────┬───────────────┘
       │               │                              │
┌──────▼─────┐  ┌──────▼─────┐               ┌────────▼──────────┐
│ JSON API   │  │            │               │                   │
│ /api/scre  │  │ Screening  │               │ ScreeningService  │
│ ening/     │──│ Universe   │               │ (read-only query) │
│  run       │  │ Service    │               │  - run_screen     │
│  distrib   │  │ (write)    │               │  - get_dist...    │
│  fields    │  │ - refresh_ │               │  - parse_filter   │
│  targets   │  │  universe  │               │  - add_to_targets │
└──────┬─────┘  │ - enrich_  │               └────────┬──────────┘
       │        │  with_yahoo│                        │
       │        └─┬──────┬───┘                        │
       │          │      │                            │
       │   ┌──────▼─┐  ┌─▼──────────┐                 │
       │   │ SEC    │  │ Yahoo      │                 │
       │   │ Edgar  │  │ Finance    │                 │
       │   │ Client │  │ Client     │                 │
       │   └────┬───┘  └─────┬──────┘                 │
       │        │            │                        │
       │   ┌────▼────────────▼──────────┐             │
       └──▶│ ScreeningRepository        │◀────────────┘
           │  + CompanyRepository       │
           │  + AnalysisTargetService   │
           └────────────────────────────┘
```

### 2.1 コンポーネント責務

| コンポーネント | 責務 |
|---|---|
| `ScreeningUniverseService` (新規) | universe / enrichment の write 系。`refresh_universe()` (SEC → companies bulk upsert) と `enrich_with_yahoo()` (Yahoo → ScreeningCache) |
| `ScreeningService` (新規) | filter / sort / distribution の read-only。 `run_screen(spec)` / `get_distribution(field, buckets)` / `add_to_targets(ids)` (`AnalysisTargetService` への薄ラッパー) |
| `SecEdgarClient.list_universe()` (新規メソッド) | `https://www.sec.gov/files/company_tickers_exchange.json` から `[{ticker, cik, name, exchange}]` を返す |
| `YahooFinanceClient.get_screening_info()` | 既存。 ticker → 18 numeric + 3 categorical の dict |
| `ScreeningRepository.list_eligible_for_enrich()` (新規メソッド) | enrich 対象 (`ScreeningCache` 未登録 OR `updated_at < now() - stale_hours`) の `[(company_id, ticker), ...]` を 1 query で返す |
| `CompanyRepository.find_existing_ids()` (新規メソッド) | `add_to_targets` の skipped 計上に使う、 `[id, ...]` → 存在する id の `set[str]` |
| `AnalysisTargetService.add_from_screening()` | 既存 (signature 変更なし)。 ScreeningService から valid な id list で呼ばれる |

### 2.2 container 配線

```python
# cli/container.py の差分
@dataclass
class ServiceContainer:
    ...
    screening_universe_service: ScreeningUniverseService | None = None
    screening_service: ScreeningService | None = None

# setup_services() の差分
async def setup_services(session, config, *, clients):
    ...
    screening_repo = ScreeningRepository(session)
    company_repo = CompanyRepository(session)
    target_repo = TargetRepository(session)
    target_service = AnalysisTargetService(target_repo)
    screening_universe_service = ScreeningUniverseService(
        screening_repo=screening_repo,
        company_repo=company_repo,
        sec_client=clients.sec,
        yahoo_client=clients.yahoo,
    )
    screening_service = ScreeningService(
        screening_repo=screening_repo,
        company_repo=company_repo,
        target_service=target_service,
    )
    return ServiceContainer(
        ...,
        screening_universe_service=screening_universe_service,
        screening_service=screening_service,
    )
```

依存はすべて確実に揃うため `pageindex` のような `enabled` フラグは持たせない。

---

## 3. Universe 登録 (SEC → companies)

### 3.1 データ源

`https://www.sec.gov/files/company_tickers_exchange.json` (`company_tickers.json` と異なり exchange を含むため、これを使う)。ペイロード形式:

```json
{
  "fields": ["cik", "name", "ticker", "exchange"],
  "data": [
    [320193, "Apple Inc.", "AAPL", "Nasdaq"],
    [1067983, "BERKSHIRE HATHAWAY INC", "BRK-A", "NYSE"],
    [1067983, "BERKSHIRE HATHAWAY INC", "BRK-B", "NYSE"],
    ...
  ]
}
```

`SecEdgarClient.list_universe()` を新規追加し、 `[{"ticker": str, "cik": str, "name": str, "exchange": str}]` を返す。同 CIK 別 ticker (BRK-A / BRK-B、 GOOGL / GOOG) は **両方が独立 entry として返される** (multi-class shares は別 company として扱う)。

### 3.2 Company レコード生成ルール

| Company 列 | 値 |
|---|---|
| `id` | `f"US_{ticker.upper()}"` (BRK-A → `US_BRK-A`、ダッシュは保持) |
| `ticker` | `ticker.upper()` |
| `cik` | 10 桁 zero-pad の文字列 |
| `name` | response の `name` |
| `name_ja` | `None` |
| `market` | response の `exchange`、空は `"UNKNOWN"` |
| `sector` | `None` (Yahoo enrichment で `screening_cache.sector` に投入) |
| `accounting_standard` | `"US-GAAP"` (新規挿入時のみ。**既存行は上書きしない**) |
| `security_code` | `None` |
| `edinet_code` | `None` |

`accounting_standard` の上書き禁止: 既存 company が手動またはfiling ingestion 経由で `IFRS` に正されている可能性があるため、 upsert 時は **新規 insert にのみ default 値を使い、 既存行の `accounting_standard` には触れない**。`bulk_upsert` の `update_columns` から `accounting_standard` を除外する。

### 3.3 処理フロー (`refresh_universe()`)

1. `SecEdgarClient.list_universe()` で entry list を取得 (1 HTTP request、 5xx は raise)
2. response から `Company` インスタンスを構築 (`ticker=""` / `name=""` の entry は skip + warn)
3. `CompanyRepository.bulk_upsert()` で `id` 衝突は `ticker / name / market / cik` を更新 (`accounting_standard` を除く)
4. 戻り値:

```python
@dataclass
class RefreshUniverseResult:
    fetched: int       # SEC が返した entry 数
    inserted: int      # 新規 insert 件数
    updated: int       # upsert 衝突件数
    skipped: int       # ticker / name 空などで skip した件数
```

### 3.4 冪等性とエラー方針

| シナリオ | 振る舞い |
|---|---|
| 同 payload で 2 回実行 | 2 回目は inserted=0、updated=N (name 等が同一なら upsert noop) |
| SEC 503 / timeout | raise `IngestionError` (universe ロード失敗は致命) |
| 1 entry の field 欠落 | warn + skip カウンタ + 後続継続 |
| ticker が delisted | **削除しない**。historical financial / filing が残るため。次回 universe payload に出てこなくても DB に残る |

---

## 4. Enrichment (Yahoo → ScreeningCache)

### 4.1 処理フロー (`enrich_with_yahoo(limit=None, stale_hours=24, max_concurrency=8)`)

1. **対象選定** — `ScreeningRepository.list_eligible_for_enrich(stale_hours, limit)` で `[(company_id, ticker), ...]` を 1 query で取得:
   - `ScreeningCache` 未登録 (`LEFT JOIN` で `cache.company_id IS NULL`)
   - または `cache.updated_at < now() - stale_hours`
   - `ticker IS NOT NULL` の条件で fetch 不可な行 (DEFUNCT) を除外
   - `limit` 指定があれば `LIMIT N`
2. **並列 fetch** — `asyncio.Semaphore(max_concurrency)` で同時 in-flight 数を制限。各 ticker で `YahooFinanceClient.get_screening_info(ticker)` を呼ぶ
3. **upsert** — Yahoo response が `dict` なら `ScreeningRepository.upsert_cache(company_id, data)` に投入。**1 ticker = 1 commit** で隔離 (中盤 cancel しても先行分は永続化)
4. **エラー捕捉** — `try/except Exception` で吸収、`logger.warning("yahoo enrich %s failed: %s", ticker, exc, exc_info=exc)`。`failed` カウンタを +1
5. **結果集計**:

```python
@dataclass
class EnrichResult:
    eligible: int      # selection で得た件数
    attempted: int     # limit truncate 後の実 fetch 件数
    succeeded: int     # upsert 成功
    failed: int        # 例外で skip
    skipped: int       # Yahoo が None / 空 dict を返した件数
    elapsed_seconds: float
```

### 4.2 並列度設計

- `max_concurrency=8` を default、CLI `--concurrency` で override 可
- `YahooFinanceClient` は内部に `_rate_limiter.acquire()` を持つ (per-call rate limiting)。Semaphore はそれと独立に「同時 in-flight 数」を制限する補完 throttle
- 全件 (≈10k) で `asyncio.gather` を一発で投げると memory が膨らむため、Semaphore + `asyncio.gather(*[task() for ...])` で OK (Future を保持するだけ)

### 4.3 stale 判定

| `stale_hours` | 動作 |
|---|---|
| `None` | 全件再取得 (cache 整合性確認用) |
| `0` | 全件 eligible (`updated_at < now()` は常に真) |
| `24` (default) | 24 時間以上古い行のみ再取得 |

### 4.4 数値特殊値の扱い

Yahoo response の `pbr=NaN` / `psr=inf` のような特殊値は **そのまま ScreeningCache に保存** (拒否しない)。run_screen の SQL 比較で自然に false 評価される。実運用で観測された値を test fixture (`CETX`) で再現。

---

## 5. Query API (ScreeningService)

### 5.1 中央スキーマ宣言

```python
# services/screening.py
SCREENING_NUMERIC_FIELDS: tuple[str, ...] = (
    "stock_price", "market_cap", "trailing_per", "eps",
    "forward_per", "pbr", "psr", "ev_ebitda",
    "dividend_yield", "roe", "operating_margin", "net_margin",
    "revenue_growth", "earnings_growth", "de_ratio",
    "peg_ratio", "fcf_yield", "beta", "volume",
)
SCREENING_CATEGORICAL_FIELDS: tuple[str, ...] = ("sector", "industry", "exchange")

@dataclass(frozen=True)
class FieldMetadata:
    field: str
    label: str
    format: Literal["ratio", "currency", "percent", "count", "string"]

FIELD_METADATA: tuple[FieldMetadata, ...] = (
    FieldMetadata("trailing_per", "PER (trailing)", "ratio"),
    FieldMetadata("forward_per",  "PER (forward)",  "ratio"),
    FieldMetadata("pbr",          "PBR",            "ratio"),
    FieldMetadata("psr",          "PSR",            "ratio"),
    FieldMetadata("ev_ebitda",    "EV/EBITDA",      "ratio"),
    FieldMetadata("market_cap",   "時価総額",        "currency"),
    FieldMetadata("eps",          "EPS",            "currency"),
    FieldMetadata("stock_price",  "株価",            "currency"),
    FieldMetadata("dividend_yield","配当利回り",     "percent"),
    FieldMetadata("roe",          "ROE",            "percent"),
    FieldMetadata("operating_margin", "営業利益率",  "percent"),
    FieldMetadata("net_margin",   "純利益率",        "percent"),
    FieldMetadata("revenue_growth", "売上成長率",    "percent"),
    FieldMetadata("earnings_growth","利益成長率",    "percent"),
    FieldMetadata("de_ratio",     "負債資本倍率",    "ratio"),
    FieldMetadata("peg_ratio",    "PEG",            "ratio"),
    FieldMetadata("fcf_yield",    "FCF利回り",      "percent"),
    FieldMetadata("beta",         "β",             "ratio"),
    FieldMetadata("volume",       "出来高",          "count"),
    FieldMetadata("sector",       "セクター",        "string"),
    FieldMetadata("industry",     "業種",            "string"),
    FieldMetadata("exchange",     "市場",            "string"),
)
```

### 5.2 Filter spec dataclass

```python
@dataclass(frozen=True)
class FilterClause:
    field: str
    op: Literal["gte", "lte", "between", "eq", "in"]
    value: float | tuple[float, float] | str | list[str]

@dataclass(frozen=True)
class SortSpec:
    field: str
    desc: bool = True

@dataclass(frozen=True)
class ScreenSpec:
    filters: list[FilterClause] = field(default_factory=list)
    sort: SortSpec | None = None       # None = market_cap desc default
    limit: int = 100                    # API default。 1..1000 (validate)。 CLI は --limit N (default 50)
    offset: int = 0                     # >= 0
    include_null: bool = False
```

### 5.3 Validation

`ScreeningService._validate(spec)` で以下を raise `ValueError`:

| 異常 | 例 |
|---|---|
| `field` whitelist 外 | `"company_id"`, `"trailing_per; DROP TABLE companies"` |
| numeric field に `eq` / `in` | `field="trailing_per", op="eq"` |
| categorical field に `gte` / `lte` / `between` | `field="sector", op="gte"` |
| `between` の value が 2-tuple でない | `value=(15,)` |
| `between` で `lower > upper` | `value=(15, 5)` |
| `in` の value が list/tuple でない | `value="Nasdaq"` |
| `limit` 範囲外 | `0` or `1001` |
| `offset` 負 | `-1` |
| sort field whitelist 外 | 同上 |

### 5.4 SQL 生成

```python
async def run_screen(self, spec: ScreenSpec) -> ScreenResult:
    self._validate(spec)
    base = (
        select(ScreeningCache, Company)
        .join(Company, Company.id == ScreeningCache.company_id)
    )
    where_clauses = []
    for clause in spec.filters:
        col = self._resolve_column(clause.field)
        match clause.op:
            case "gte":     where_clauses.append(col >= clause.value)
            case "lte":     where_clauses.append(col <= clause.value)
            case "between": lo, hi = clause.value
                            where_clauses.append(col.between(lo, hi))
            case "eq":      where_clauses.append(col == clause.value)
            case "in":      where_clauses.append(col.in_(clause.value))
        if clause.field in SCREENING_NUMERIC_FIELDS and not spec.include_null:
            where_clauses.append(col.is_not(None))
    base = base.where(*where_clauses)

    sort_field = spec.sort.field if spec.sort else "market_cap"
    sort_desc = spec.sort.desc if spec.sort else True
    sort_col = self._resolve_column(sort_field)
    # NULLS LAST 互換 (SQLite)
    null_first = sort_col.is_(None)
    order = (null_first, sort_col.desc() if sort_desc else sort_col.asc())
    stmt = base.order_by(*order).limit(spec.limit).offset(spec.offset)

    items = (await self._session.execute(stmt)).all()

    count_stmt = select(func.count()).select_from(
        select(ScreeningCache).join(Company, ...).where(*where_clauses).subquery()
    )
    total_matched = (await self._session.execute(count_stmt)).scalar() or 0

    return ScreenResult(items=[...], total_matched=total_matched, spec=spec)
```

`_resolve_column(field)` は **whitelist 確認後に `getattr(ScreeningCache, field)` で `Column` を返す**。生文字列を SQL 内に挿入しない (Phase A の SQL injection ガード規約準拠)。

### 5.5 結果型

```python
@dataclass
class ScreenResultItem:
    company_id: str
    ticker: str | None
    name: str
    sector: str | None
    market: str
    metrics: dict[str, float | int | None]   # 全 numeric 18 列を含む

@dataclass
class ScreenResult:
    items: list[ScreenResultItem]
    total_matched: int
    spec: ScreenSpec
```

### 5.6 `get_distribution(field, buckets=20)`

`inf` / `NaN` は finite 値の min/max を歪めるため、 stat 計算と bucket 分割の対象から除外する。除外件数は `non_finite_count` として返し、 UI 側で表示させる。

```python
async def get_distribution(self, field: str, buckets: int = 20) -> Distribution:
    if field not in SCREENING_NUMERIC_FIELDS:
        raise ValueError(...)
    if not 1 <= buckets <= 100:
        raise ValueError(...)
    col = getattr(ScreeningCache, field)
    # inf / NaN は SQL の比較で常に false 評価され、 BETWEEN -inf..inf にも入らないため
    # 自動的に除外される。 ただし min/max 計算は SQL 側で inf を返しうるので、
    # finite filter (col != float('inf') AND col != float('-inf') AND col == col)
    # を明示的にかける。 SQLite は IEEE 754 比較を実装、 col == col は NaN だけ false。
    finite = and_(col.is_not(None),
                  col != float('inf'), col != float('-inf'),
                  col == col)
    stat_stmt = select(
        func.min(col).filter(finite),
        func.max(col).filter(finite),
        func.count().filter(col.is_(None)),
        func.count().filter(finite),
        func.count().filter(and_(col.is_not(None), not_(finite))),
    )
    lo, hi, null_count, non_null, non_finite = (
        await self._session.execute(stat_stmt)
    ).one()
    if non_null == 0:
        return Distribution(field=field, min=None, max=None,
                            null_count=null_count, non_null_count=0,
                            non_finite_count=non_finite, buckets=[])
    if lo == hi:
        return Distribution(field=field, min=lo, max=hi,
                            null_count=null_count, non_null_count=non_null,
                            non_finite_count=non_finite,
                            buckets=[Bucket(lower=lo, upper=hi, count=non_null - non_finite)])
    width = (hi - lo) / buckets
    case_args = [
        (and_(col >= lo + i * width,
              col <  lo + (i + 1) * width if i < buckets - 1 else col <= hi), i)
        for i in range(buckets)
    ]
    bucket_idx = case(*case_args).label("idx")
    bucket_stmt = (select(bucket_idx, func.count())
                   .where(finite).group_by(bucket_idx))
    rows = (await self._session.execute(bucket_stmt)).all()
    counts = {idx: cnt for idx, cnt in rows}
    return Distribution(
        field=field, min=lo, max=hi,
        null_count=null_count, non_null_count=non_null,
        non_finite_count=non_finite,
        buckets=[Bucket(lower=lo + i * width,
                        upper=lo + (i + 1) * width if i < buckets - 1 else hi,
                        count=counts.get(i, 0)) for i in range(buckets)],
    )
```

戻り型:

```python
@dataclass
class Bucket:
    lower: float
    upper: float
    count: int

@dataclass
class Distribution:
    field: str
    min: float | None        # finite のみの min (inf/NaN 除外)
    max: float | None        # finite のみの max (inf/NaN 除外)
    null_count: int          # NULL の件数
    non_null_count: int      # NULL でない件数 (inf / NaN を含む)
    non_finite_count: int    # NULL でない && (inf / -inf / NaN) の件数
    buckets: list[Bucket]    # finite 値のみで分割
```

### 5.7 `add_to_targets(company_ids)`

入力検証 (空 / 100 件超 / 重複 dedup) 後、 不在 company_id を pre-check で除外してから `AnalysisTargetService.add_from_screening(valid_ids)` に委譲。

```python
@dataclass
class AddToTargetsResult:
    requested: int
    added: int            # bulk_add で実 insert された件数
    already_present: int  # 既に analysis_targets に存在 (CONFLICT で skip された件数)
    skipped: int          # companies テーブルに存在しない id

async def add_to_targets(self, company_ids: list[str]) -> AddToTargetsResult:
    if not company_ids:
        raise ValueError("company_ids must be non-empty")
    if len(company_ids) > 100:
        raise ValueError("max 100 ids per call")
    unique = list(dict.fromkeys(company_ids))                  # dedupe + 順序保存
    existing_ids = await self._company_repo.find_existing_ids(unique)
    valid = [cid for cid in unique if cid in existing_ids]
    skipped = len(unique) - len(valid)
    added = await self._target_service.add_from_screening(valid)
    already_present = len(valid) - added
    return AddToTargetsResult(
        requested=len(company_ids),
        added=added,
        already_present=already_present,
        skipped=skipped,
    )
```

`AnalysisTargetService.add_from_screening(list[str]) -> int` の既存 signature は **変更しない**。 ScreeningService 側で bookkeeping を完結させることで、 既存 callers (`tests/unit/services/test_analysis_target_service.py`) を破壊しない。

`CompanyRepository.find_existing_ids(ids: list[str]) -> set[str]` を新規メソッドとして追加 (1 SELECT IN(...) query)。

---

## 6. JSON API endpoints

prefix: `/api/screening`。`web/routes/screening.py` を JSON router に置換、`web/templates/screening/placeholder.html` を削除。

### 6.1 `POST /api/screening/run`

**Request body:**

```json
{
  "filters": [
    {"field": "trailing_per", "op": "between", "value": [0, 15]},
    {"field": "roe", "op": "gte", "value": 0.15},
    {"field": "exchange", "op": "in", "value": ["Nasdaq", "NYSE"]}
  ],
  "sort": {"field": "market_cap", "desc": true},
  "limit": 50,
  "offset": 0,
  "include_null": false
}
```

**Response (200):**

```json
{
  "items": [
    {
      "company_id": "US_AAPL", "ticker": "AAPL", "name": "Apple Inc",
      "sector": "Technology", "market": "Nasdaq",
      "metrics": {"trailing_per": 28.4, "roe": 1.45, "market_cap": 3.5e12, ...}
    }
  ],
  "total_matched": 87,
  "limit": 50,
  "offset": 0
}
```

**Errors:**

| Status | 条件 |
|---|---|
| `400` | spec validation 失敗 (whitelist 外 / op 不整合 / between 逆順) |
| `401` | 未認証 |
| `429` | heavy rate limit 超過 |
| `503` | screening_service が None (container wiring 不全) |

### 6.2 `GET /api/screening/distributions/{field}?buckets=20`

**Response (200):**

```json
{
  "field": "trailing_per",
  "min": -45.2, "max": 1840.0,
  "null_count": 312, "non_null_count": 9530,
  "buckets": [
    {"lower": -45.2, "upper": 49.0, "count": 7821},
    ...
  ]
}
```

**Errors:** field whitelist 外 → `400`、 buckets 範囲外 → `400`

### 6.3 `GET /api/screening/fields`

**Response (200):**

```json
{
  "numeric": [
    {"field": "trailing_per", "label": "PER (trailing)", "format": "ratio"},
    ...
  ],
  "categorical": [
    {"field": "sector", "label": "セクター", "format": "string"},
    ...
  ]
}
```

`FIELD_METADATA` を 1 中央定義から生成。

### 6.4 `POST /api/screening/targets`

**Request:** `{"company_ids": ["US_AAPL", "US_MSFT"]}`

**Response (200):**

```json
{"requested": 2, "added": 2, "already_present": 0, "skipped": 0}
```

**Errors:** 空 list / 100 件超 → `400`

### 6.5 認証 / rate limit

- 全 endpoint が `Depends(get_services)` 経由 (auth middleware が global 適用済の前提)
- `/run` および `/targets` に `_enforce_heavy_request_limit(scope=...)` 適用
- `/distributions/*` および `/fields` には rate limit を当てない (cache 寄り読み取り)
- scope 名: `f"screening-run:{client_key}"`, `f"screening-targets:{client_key}"`

---

## 7. CLI commands

`cli/screening.py` (新規) に argparse-based subcommand を実装。

### 7.1 `stock-analyze screening universe refresh [--source sec]`

`ScreeningUniverseService.refresh_universe()` を呼ぶ。`--source` は将来 EDINET 拡張用に予約 (Phase 1 では `sec` のみ受理)。

```
$ stock-analyze screening universe refresh
Universe refresh (source=sec)
  fetched: 9842 entries
  inserted: 187, updated: 9655, skipped: 0
  elapsed: 4.2s
```

### 7.2 `stock-analyze screening refresh [--limit N] [--stale-hours H] [--concurrency C]`

`ScreeningUniverseService.enrich_with_yahoo()` を呼ぶ。

```
$ stock-analyze screening refresh --limit 1000 --stale-hours 24 --concurrency 8
Enrichment (eligible=412, attempted=412, concurrency=8)
  succeeded: 398, failed: 11, skipped: 3
  elapsed: 87.3s
```

### 7.3 `stock-analyze screening run [filters...] [--sort F] [--desc/--asc] [--limit N] [--offset N] [--include-null] [--json]`

`ScreeningService.run_screen()` を呼ぶ。

```bash
$ stock-analyze screening run \
    --gte roe=0.15 --lte trailing_per=15 \
    --between market_cap=1e9,1e12 \
    --in exchange=Nasdaq,NYSE \
    --sort market_cap --desc --limit 20
```

| flag | 用途 |
|---|---|
| `--gte FIELD=V` (繰り返し) | 数値 `>=` |
| `--lte FIELD=V` (繰り返し) | 数値 `<=` |
| `--between FIELD=LO,HI` (繰り返し) | 数値範囲 |
| `--eq FIELD=V` (繰り返し) | categorical 等値 |
| `--in FIELD=V1,V2,...` (繰り返し) | categorical 集合 |
| `--sort FIELD` | 単一指定 (default: market_cap) |
| `--desc / --asc` | sort 方向 (default: desc) |
| `--limit N` | default 50 |
| `--offset N` | default 0 |
| `--include-null` | numeric filter で null も結果に含める |
| `--json` | API response を stdout に raw JSON で出力 (pipe 用) |

### 7.4 `stock-analyze screening add-targets ID [ID...]`

stdin / argv から company_ids を受けて `ScreeningService.add_to_targets()` に投入。pipe 用途想定:

```bash
$ stock-analyze screening run --gte roe=0.15 --json \
    | jq -r '.items[].company_id' \
    | xargs stock-analyze screening add-targets
analysis_targets: requested=12 added=10 already_present=2 skipped=0
```

### 7.5 `stock-analyze screening fields`

`FIELD_METADATA` を表形式で出力 (filter で指定可能な field の reference)。

### 7.6 ServiceContainer 未配線時の挙動

`screening_universe_service` / `screening_service` が `None` の場合、 CLI はスタックトレースを吐かず以下を出して exit 1:

```
ERROR: screening service is unavailable. Check container wiring.
```

---

## 8. エラー / ログ

### 8.1 エラー分類

| 場所 | エラー | 振る舞い |
|---|---|---|
| `refresh_universe` | SEC HTTP 失敗 | raise `IngestionError` |
| `refresh_universe` | 1 entry の field 欠落 | warn + skip カウンタ |
| `enrich_with_yahoo` | 1 ticker の Yahoo 失敗 | warn (`exc_info=exc`) + `failed` カウンタ |
| `enrich_with_yahoo` | DB upsert 失敗 | rollback + warn + skip カウンタ |
| `run_screen` | spec validation | `ValueError` → API 層で `400` |
| `run_screen` | DB query 失敗 | propagate (FastAPI 500) |
| `get_distribution` | field whitelist 外 | `ValueError` → `400` |
| `add_to_targets` | 一部 company_id 不在 | skip カウンタ (raise しない) |

### 8.2 ログ規約

- `refresh_universe`: 開始 / 完了 INFO 各 1 行、 entry skip は WARNING
- `enrich_with_yahoo`: 開始 INFO `"enrich start: eligible=%d limit=%d"`、 各失敗 WARNING `"yahoo enrich %s failed"` (`exc_info=exc`)、 完了 INFO で集計
- `run_screen`: spec 内容は DEBUG、 `INFO` で `matched=%d` 程度 (production noise 抑制)
- `get_distribution`: production では DEBUG のみ

---

## 9. テスト戦略

### 9.1 共通フィクスチャ — universe seeds

`tests/fixtures/screening_universe.py` に以下 16 行の `Company` + `ScreeningCache` の seed を提供:

| # | id | ticker | exchange | accounting_std | 用途 / 異常露出 |
|---|---|---|---|---|---|
| 1 | `US_AAPL` | AAPL | Nasdaq | US-GAAP | 大型 US ベースライン |
| 2 | `US_MSFT` | MSFT | Nasdaq | US-GAAP | 大型 US (sort 検証) |
| 3 | `US_BRK-A` | BRK-A | NYSE | US-GAAP | ticker ダッシュ、 multi-class 親 |
| 4 | `US_BRK-B` | BRK-B | NYSE | US-GAAP | 同 CIK 別 ticker |
| 5 | `US_GOOGL` | GOOGL | Nasdaq | US-GAAP | dual class B |
| 6 | `US_GOOG` | GOOG | Nasdaq | US-GAAP | dual class C |
| 7 | `US_TSLA` | TSLA | Nasdaq | US-GAAP | 極端 PER / 高 beta |
| 8 | `US_TSM` | TSM | NYSE | **IFRS** | ADR 台湾 (overwrite 禁止 test) |
| 9 | `US_SAP` | SAP | NYSE | **IFRS** | ADR ドイツ |
| 10 | `US_SONY` | SONY | NYSE | **IFRS** | ADR 日本 (`sector="技術"` で unicode test) |
| 11 | `US_JPM` | JPM | NYSE | US-GAAP | 銀行 (DE_ratio 極大) |
| 12 | `US_O` | O | NYSE | US-GAAP | REIT (`dividend_yield=0.058`) |
| 13 | `US_IZEA` | IZEA | Nasdaq | US-GAAP | 小型 (mc=18M)、 多くの null |
| 14 | `US_PLTR` | PLTR | NYSE | US-GAAP | 赤字 (`trailing_per=None`, `roe=-0.12`) |
| 15 | `US_CETX` | CETX | Nasdaq | US-GAAP | penny、 `pbr=NaN` / `psr=inf` 注入 |
| 16 | `US_DEFUNCT` | (None) | DELISTED | US-GAAP | ticker None で enrich skip、 universe overwrite 禁止 |

```python
# tests/fixtures/screening_universe.py
class _ScreenSeed(NamedTuple):
    company: dict        # Company 行
    cache: dict | None   # None = キャッシュ未生成 (enrich 対象)

def screening_universe_seeds() -> list[_ScreenSeed]: ...
def aapl_seed() -> _ScreenSeed: ...
def adr_seeds() -> list[_ScreenSeed]: ...   # #8 #9 #10
def edge_value_seeds() -> list[_ScreenSeed]: ...   # #13 #14 #15
def delisted_seed() -> _ScreenSeed: ...   # #16
```

### 9.2 SEC mock payload

`tests/fixtures/sec_company_tickers_payload.py` に 16 ticker (DEFUNCT 除く) + 異常 4 entry を含む payload を用意:

| 異常 entry | 内容 |
|---|---|
| `ticker=""` | skip + warn |
| `name=""` | skip + warn |
| `exchange=""` | `market="UNKNOWN"` で insert (warn なし) |
| 同 CIK 2 entry (BRK-A / BRK-B、 GOOGL / GOOG) | 別 company として両方 insert |

### 9.3 Yahoo mock シナリオ

`tests/fixtures/yahoo_screening_responses.py`:

| ticker | response | test 用途 |
|---|---|---|
| AAPL〜JPM | 完全 dict | 正常系 |
| O | dividend_yield 含む完全 dict | 高配当 filter |
| IZEA | 半数の field が None | null 許容 |
| PLTR | `trailing_per=None`, `roe=-0.12` | 負値 / null 共存 |
| CETX | `pbr=float('nan'), psr=float('inf')` | NaN / inf 注入 |
| `_TIMEOUT` | `httpx.ReadTimeout` raise | エラー分離 |
| `_RATELIMIT` | `httpx.HTTPStatusError(429)` raise | rate limit エラー時 skip |
| `_EMPTY` | `None` | Yahoo 失敗 (skip カウンタ) |

### 9.4 テスト一覧 (8 カテゴリ)

#### A. 機能正常系

| Test | 検証 | 対象 ticker |
|---|---|---|
| `test_refresh_universe_inserts_new_companies` | 空 DB → 全 inserted、集計が正 | 16 全件 |
| `test_refresh_universe_updates_existing_company_name` | 既存 AAPL (name 旧) → 新 name で update | AAPL |
| `test_enrich_with_yahoo_fills_all_18_numeric_fields` | 完全 dict → 全 18 numeric + 3 categorical 入る | AAPL |
| `test_run_screen_returns_full_metrics_dict` | 結果 item の `metrics` に 19 列 | 全件 |
| `test_run_screen_default_sort_is_market_cap_desc` | sort 未指定 → mc desc 順 | AAPL > MSFT > GOOGL > BRK-A > GOOG > TSM > JPM > SAP > O > SONY > TSLA > PLTR > IZEA > CETX |
| `test_get_distribution_buckets_partition_correctly` | seed 既知分布 / buckets=10 → 正しい bucket count | 全件 |
| `test_add_to_targets_calls_analysis_target_service` | mock target_service が正しい id list で呼ばれる | AAPL, MSFT |

#### B. 部分失敗の分離

| Test | 検証 | 対象 ticker |
|---|---|---|
| `test_enrich_with_yahoo_one_ticker_raise_others_continue` | 5 ticker のうち 3 番目で `_TIMEOUT` raise → 残り 4 は upsert 成功 | AAPL, MSFT, _TIMEOUT, TSLA, JPM |
| `test_enrich_with_yahoo_yahoo_returns_none_skips_silently` | `_EMPTY` → skip カウンタ +1、 warn なし | _EMPTY |
| `test_enrich_with_yahoo_db_upsert_failure_isolated` | 1 ticker で `IntegrityError` → rollback、 後続成功 | AAPL, (faulty), MSFT |
| `test_enrich_with_yahoo_warn_log_carries_exc_info` | warn record に `exc_info` がある (`_RATELIMIT`) | _RATELIMIT |
| `test_refresh_universe_skip_entry_missing_ticker` | SEC payload の `ticker=""` entry → skip + warn | (合成 entry) |
| `test_refresh_universe_skip_entry_missing_name` | `name=""` → skip + warn | (合成 entry) |
| `test_refresh_universe_does_not_overwrite_accounting_standard` | 既存 TSM (IFRS) → refresh 後も IFRS 維持 | TSM |
| `test_refresh_universe_does_not_overwrite_delisted_market` | 既存 DEFUNCT (market=DELISTED) → refresh 対象外 (payload に無い)、 そのまま残る | DEFUNCT |
| `test_add_to_targets_skips_unknown_company_ids` | `["US_AAPL", "US_NONEXISTENT"]` → added=1、 skipped=1 | AAPL + 不在 id |
| `test_add_to_targets_counts_already_present_correctly` | 既に target に登録済の AAPL を再 add → added=0、 already_present=1 | AAPL |

#### C. 並列・同時実行

| Test | 検証 | 対象 |
|---|---|---|
| `test_enrich_with_yahoo_respects_max_concurrency` | `max_concurrency=2` で 10 ticker、 同時 in-flight 最大 2 | 16 中 10 |
| `test_enrich_with_yahoo_default_concurrency_is_8` | default 引数 8、 CLI flag override が反映 | — |
| `test_enrich_with_yahoo_uses_independent_db_writes_per_ticker` | CancelledError を中盤で raise → 先行分は永続化 | 16 |
| `test_run_screen_concurrent_calls_share_session_correctly` | 同 session で並走 → 結果混入なし | 全件 |

#### D. Validation / SQL injection

| Test | 検証 | 入力 |
|---|---|---|
| `test_run_screen_rejects_unknown_field` | 400 | `field="company_id"` |
| `test_run_screen_rejects_sql_injection_in_field` | 400 | `field="trailing_per; DROP TABLE companies"` |
| `test_run_screen_rejects_eq_on_numeric_field` | 400 | `field="trailing_per", op="eq"` |
| `test_run_screen_rejects_in_on_numeric_field` | 400 | 同上 (`in`) |
| `test_run_screen_rejects_gte_on_categorical_field` | 400 | `field="sector", op="gte"` |
| `test_run_screen_rejects_between_with_inverted_range` | 400 | `value=(15, 5)` |
| `test_run_screen_rejects_between_with_single_value` | 400 | `value=(15,)` |
| `test_run_screen_rejects_in_with_non_list_value` | 400 | `value="Nasdaq"` |
| `test_run_screen_rejects_limit_over_1000` | 400 | `limit=1001` |
| `test_run_screen_rejects_limit_zero` | 400 | `limit=0` |
| `test_run_screen_rejects_negative_offset` | 400 | `offset=-1` |
| `test_get_distribution_rejects_categorical_field` | 400 | `field="sector"` |
| `test_get_distribution_rejects_buckets_outside_1_to_100` | 400 | 0 / 101 |
| `test_add_to_targets_rejects_empty_list` | 400 | `[]` |
| `test_add_to_targets_rejects_over_100_company_ids` | 400 | 101 件 |
| `test_add_to_targets_dedupes_duplicate_ids` | 重複は 1 回のみ count | `["US_AAPL", "US_AAPL"]` |

#### E. 境界値 / NULL / 数値特殊値

| Test | 検証 | 対象 ticker |
|---|---|---|
| `test_run_screen_excludes_null_by_default_for_numeric_filter` | filter `roe>=0` で `roe IS NULL` 行を除外 | PLTR (roe=-0.12 は含む)、 IZEA (null は除外) |
| `test_run_screen_includes_null_when_include_null_true` | `include_null=True` で null 含む | IZEA |
| `test_run_screen_between_inclusive_at_boundaries` | `between(10,20)` → 10.0 / 20.0 両方含まれる (BETWEEN inclusive) | 合成 |
| `test_run_screen_handles_inf_values_consistently` | `psr=inf` の row は filter `psr<=10` で除外、 distribution で max=最大有限値 | CETX |
| `test_run_screen_handles_nan_values_consistently` | `pbr=NaN` は filter で常に false (除外) | CETX |
| `test_run_screen_limit_is_one_minimum` | `limit=1` で 1 件取得、total_matched は別計算 | — |
| `test_run_screen_offset_beyond_total_returns_empty` | offset>total → items=[]、 エラーにしない | 全件 |
| `test_get_distribution_all_null_column_returns_zero_count_buckets` | 全 null column → null_count=N、 buckets=[] | (合成) |
| `test_get_distribution_constant_column_collapses_to_single_bucket` | min==max → 1 bucket、 divide-by-zero しない | (合成) |
| `test_get_distribution_excludes_inf_from_min_max` | `psr=inf` を含む CETX が混在 → min/max は finite のみ | CETX |
| `test_run_screen_categorical_eq_is_case_sensitive` | `exchange="nasdaq"` (lowercase) → 0 件 (既存は "Nasdaq") | 全件 |
| `test_run_screen_market_cap_extreme_values` | 1e18 / -1e18 を SQL で誤差なく扱える | (合成) |
| `test_run_screen_unicode_sector_filter` | `sector="技術"` で SONY が hit | SONY |
| `test_run_screen_negative_roe_passes_gte_negative_threshold` | filter `roe>=-0.5` で PLTR (roe=-0.12) が hit | PLTR |
| `test_run_screen_zero_volume_excluded_by_volume_gte_1` | volume=0 の行を `volume>=1` で除外 | (合成) |
| `test_run_screen_dash_in_ticker_does_not_break_response` | id `US_BRK-A` がそのまま response に出る | BRK-A |

#### F. 冪等性 / 再実行

| Test | 検証 |
|---|---|
| `test_refresh_universe_idempotent` | 2 回連続実行 → 2 回目 inserted=0 |
| `test_enrich_with_yahoo_idempotent_within_stale_window` | enrich → stale_hours=24 で 2 回目 eligible=0 |
| `test_enrich_with_yahoo_zero_stale_hours_re_fetches_all` | `stale_hours=0` → 全件 eligible |
| `test_enrich_with_yahoo_none_stale_hours_re_fetches_all` | `stale_hours=None` → 全件 eligible (cache 整合性確認モード) |
| `test_enrich_with_yahoo_limit_truncates_eligible_set` | eligible=100, `limit=10` → 10 ticker のみ呼ばれる |
| `test_enrich_with_yahoo_excludes_ticker_none_companies` | DEFUNCT は eligible に出ない | DEFUNCT |

#### G. 統合 / end-to-end (薄く)

| Test | 検証 |
|---|---|
| `test_full_flow_universe_then_enrich_then_run_screen` | SEC mock → universe → Yahoo mock → enrich → run_screen で seed の絞込が動く 1 本 |
| `test_api_run_endpoint_full_request_response_cycle` | `POST /api/screening/run` で 200、Pydantic schema validation |
| `test_api_run_rejects_unauthenticated` | auth ない → 401 |
| `test_api_run_consumes_heavy_rate_limit` | 同 client から 10 連打 → 429 を踏む |
| `test_api_distributions_does_not_consume_rate_limit` | distribution endpoint は重制限を踏まない |
| `test_api_targets_consumes_heavy_rate_limit` | targets は重制限を踏む |
| `test_api_run_503_when_screening_service_none` | container 不全 → 503 |
| `test_cli_run_pipes_to_add_targets` | `screening run --json | screening add-targets` 相当を subprocess で 1 本 (smoke) |
| `test_cli_screening_service_none_exits_1_with_message` | container 不全 → exit 1、 stack trace 出ない |

#### H. 観測可能性 (ログ)

| Test | 検証 |
|---|---|
| `test_enrich_with_yahoo_emits_start_and_completion_info_logs` | 開始 / 完了の INFO が各 1 行のみ (進捗 spam なし) |
| `test_enrich_with_yahoo_warning_log_includes_ticker_and_exception` | warn record に ticker と exception class 名 |
| `test_run_screen_does_not_log_at_info_in_hot_path` | log level INFO 以下 (production noise 防止) |
| `test_refresh_universe_logs_per_entry_skip_at_warning` | skip 1 entry につき 1 warning |

### 9.5 テストファイル配置

| File | 内容 |
|---|---|
| `tests/fixtures/screening_universe.py` | 16 ticker seeds + helper |
| `tests/fixtures/sec_company_tickers_payload.py` | SEC mock payload |
| `tests/fixtures/yahoo_screening_responses.py` | Yahoo mock |
| `tests/unit/services/test_screening_service.py` | カテゴリ A, D (一部), E, G の service 層 |
| `tests/unit/services/test_screening_universe_service.py` | カテゴリ A (一部), B, C, F, H |
| `tests/unit/web/test_screening_api.py` | カテゴリ G の API 層 |
| `tests/unit/cli/test_screening_cli.py` | カテゴリ D (CLI), G の CLI 層 |
| `tests/unit/repositories/test_other_repos.py` (追記) | `list_eligible_for_enrich` query + `CompanyRepository.find_existing_ids` を単体検証 |

総追加テスト数の目安: ≈ 75 件 (Phase A 完了時 778 件 → 合計 ≈ 853 件、 warnings-as-errors 緑保持)。

---

## 10. 既存 placeholder の処遇

| 対象 | 処遇 |
|---|---|
| `web/routes/screening.py` (placeholder GET) | JSON router (§6) に置換 |
| `web/templates/screening/placeholder.html` | 削除 (Web UI はユーザー実装) |
| `web/app.py` の `screening_routes` import / `include_router` | JSON router を指す (パスは `/api/screening` になる) |
| `cli/container.py:36` の `screening_service: object \| None` | `screening_universe_service` と `screening_service` の 2 つに置換 |

---

## 11. 後方互換 / 影響範囲

### 11.1 既存 API への影響

なし。`/api/screening/*` は新規 prefix。既存 `/api/stocks/*` は無変更。

### 11.2 既存 CLI への影響

なし。`stock-analyze screening` は新規サブコマンド。

### 11.3 DB schema 変更

なし。`ScreeningCache` テーブルは既に存在。新規 index も追加しない (既存 `ix_screening_cache_updated_at`、 `ix_screening_cache_roe` が `list_eligible_for_enrich` を支える)。

### 11.4 `CompanyRepository.find_existing_ids` の追加

`add_to_targets` の skipped 計上のため、 `CompanyRepository.find_existing_ids(ids: list[str]) -> set[str]` を 1 SELECT IN(...) query で追加。 `AnalysisTargetService.add_from_screening` の signature は **変更しない** (既存 caller test を破壊しない)。

---

## 12. 段階的実装の指針 (writing-plans へ渡すヒント)

実装順は次を推奨:

1. **Repository 拡張** — `ScreeningRepository.list_eligible_for_enrich` を TDD で追加
2. **Universe 取り込み** — `SecEdgarClient.list_universe()` + `ScreeningUniverseService.refresh_universe()`
3. **Enrichment** — `ScreeningUniverseService.enrich_with_yahoo()` (semaphore + 部分失敗テスト含む)
4. **Read-only Service** — `ScreeningService.run_screen / get_distribution / add_to_targets` (validation 込み)
5. **JSON API** — `web/routes/screening.py` を JSON router に置換 + `_tab_*` 不要 (UI 別実装)
6. **CLI** — `cli/screening.py` で 5 サブコマンド
7. **container 配線 + placeholder 削除** — wiring 完成 + placeholder.html / placeholder route 削除

各ステップで unit test 緑、 ruff clean、 warnings-as-errors 緑を保つ。

---

## 13. 確定済みの out-of-scope

| 項目 | 理由 |
|---|---|
| Web UI (filter スライダー / results table / Jinja template) | ユーザー側で別実装 |
| EDINET universe (日本企業) | Phase 1 では SEC のみ |
| Filter preset の保存 / 共有 | YAGNI、 必要になれば別 Phase |
| daily cron への組み込み | CLI 手動運用で十分、 必要になれば別 Phase |
| `--export csv` の CLI オプション | `--json` で代替可能 |
| Yahoo response の retry queue | 1 回 attempt の warn + skip で十分 (R7) |
| Universe のサイズ制限 / pagination | universe size ≈ 10k 想定で問題なし、 必要になれば別 Phase |
