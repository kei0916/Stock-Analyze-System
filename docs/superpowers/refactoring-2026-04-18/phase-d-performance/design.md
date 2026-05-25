# Phase D: パフォーマンス改善 Design

**Date**: 2026-04-18 起草 / 2026-04-19 承認
**Scope**: プロジェクト全体のパフォーマンス改善 (第 1 フェーズ)
**Parent tracker**: [../master.md](../master.md)

---

## 1. Goal

Web hot path と bulk write の不要な I/O を削減し、体感速度とバッチ処理速度を改善する。

**成功条件**
- 全テスト (718+) PASS
- カバレッジ 96% 以上維持
- ruff `tests/` `src/` clean
- `tests/benchmarks/` で before/after の数値が `report.md` に記録済み
- `run_daily_update` の直列性が維持されている

---

## 2. 背景と前提

- 2026-04-18 の test-coverage-strengthening で全体 97% カバレッジを確保済み
- DB は SQLite のみ (`sqlite+aiosqlite`)、native UPSERT (`ON CONFLICT DO UPDATE`) 使用可
- プロジェクトは 1 人ユーザー環境。backward compatibility の制約は spec 内で明示した範囲のみ

---

## 3. Scope

### 3-1. 対象 (In scope)

| # | 領域 | 内容 |
|---|---|---|
| #1 | Web hot path | 外部 API クライアント (SEC/EDINET/Yahoo/FMP/LlmClient/PdfConverter) の app.state シングルトン化 |
| #3 | DB write 根本 | `BaseRepository` に SQLite native UPSERT メソッドを追加 |
| #4 | Financial bulk | `FinancialRepository.bulk_upsert` を native 版に差し替え |
| #5 | Target bulk | `TargetRepository.bulk_upsert` を native 版に差し替え |
| #6 | Valuation bulk | `ValuationRepository.bulk_upsert` を native 版に差し替え |
| #7 | Filing sync | `FilingSyncService.update_from_sec/edinet` の逐次 loop を bulk 化 |
| #8 | Web eager load | Watchlist detail の 2 round-trip を `selectinload` 1 round-trip 化 |

### 3-2. 対象外 (Out of scope)

| 項目 | 理由 |
|---|---|
| #2 `run_daily_update` の並列化 | LLM + SEC filings デッドロック回避のため意図的に直列維持。将来タスク (`llama-server` の context budget / unified KV / prompt サイズ見直しとセット。2026-04-19 検証では GreenBoost 予約量は主因でない) |
| 単発 `upsert()` の native 化 | hot path ではない、big bang 変更になる |
| CLI 側のクライアント singleton 化 | CLI は 1 コマンド 1 プロセスなので効果なし |
| DB スキーマの大規模変更 | モデル変更は最小 (unique index の追加のみ、必要時) |
| 他 Phase (C/E/B/A) の先取り | 各 Phase は独立 cycle |

### 3-3. 非目標 (Non-goals)

- service/repository の **public API 変更** (戻り値型・引数) は行わない
- テストの大幅書き換えは避ける (97% カバレッジを最大限活用)

---

## 4. 選択したアプローチ: "Incremental fix" (案 C)

既存 `bulk_upsert()` メソッドの **実装のみ** を native UPSERT に差し替え。API と単発 `upsert()` は無変更。

**理由**:
- N+1 の 4 箇所 (#3, #4, #5, #6) を 1 箇所の実装変更で同時解消
- 変更差分が小さいため 97% カバレッジを最大限活かせる
- 単発 `upsert()` の 2-query は残るが hot path ではない

**却下した案**
- **案 A (base.upsert 全書き換え)**: 単発パスも native 化するため big bang、影響範囲大
- **案 B (新 API `bulk_upsert` を新規追加)**: API が増える、移行箇所多い

---

## 5. 詳細設計

### 5-1. クライアント singleton 化 (#1)

**問題**: `web/dependencies.py:52` `get_services()` が FastAPI dependency として毎リクエスト `setup_services()` を呼び、その中で以下を new する:
- `SecEdgarClient`, `EdinetClient`, `YahooFinanceClient`, `FmpClient`
- RAG 有効時: `LlmClient`, `PdfConverter`, `PageIndexService`

`YahooFinanceClient` は `AsyncRateLimiter` を保持するが、リクエストごとリセットされると実質レート制限が効かない。

**設計**

`AppState` (dependencies.py) に singleton を追加:

```python
@dataclass
class ClientBundle:
    sec: SecEdgarClient
    edinet: EdinetClient
    yahoo: YahooFinanceClient
    fmp: FmpClient
    llm: LlmClient | None = None
    pdf_converter: PdfConverter | None = None

@dataclass
class AppState:
    config: AppConfig
    engine: AsyncEngine
    clients: ClientBundle

    @classmethod
    async def create(cls, config: AppConfig) -> "AppState":
        engine = await create_db_engine(config.database.path)
        clients = ClientBundle(
            sec=SecEdgarClient(email=config.sec_edgar.email),
            edinet=EdinetClient(api_key=config.edinet.api_key, base_url=config.edinet.base_url),
            yahoo=YahooFinanceClient(rate=config.yahoo_finance.rate_limit_rps),
            fmp=FmpClient(api_key=config.fmp.api_key, base_url=config.fmp.base_url),
        )
        if config.pageindex.enabled:
            clients.llm = LlmClient(config.llm)
            clients.pdf_converter = PdfConverter()
        return cls(config=config, engine=engine, clients=clients)

    async def dispose(self) -> None:
        # BaseClient 継承クライアントのみ close (YahooFinanceClient は継承しないため close 不要)
        await self.clients.sec.close()
        await self.clients.edinet.close()
        await self.clients.fmp.close()
        await self.engine.dispose()
```

既存の `web/app.py:49` lifespan で `state.dispose()` を呼んでいるため、追加のフック不要。

`setup_services()` に optional 引数を追加:

```python
async def setup_services(
    session: AsyncSession,
    config: AppConfig,
    *,
    clients: ClientBundle | None = None,  # 省略時は従来通り new
) -> ServiceContainer:
    if clients is None:
        # 従来パス (CLI / tests)
        sec_client = SecEdgarClient(email=config.sec_edgar.email)
        ...
    else:
        # 新パス (Web)
        sec_client = clients.sec
        ...
```

Web の `get_services()`:

```python
async def get_services(
    session: AsyncSession = Depends(get_session_dep),
    state: AppState = Depends(get_app_state),
) -> ServiceContainer:
    return await setup_services(session, state.config, clients=state.clients)
```

**後方互換**: `setup_services(session, config)` の 2 引数呼び出しは全て維持。CLI / integration test / characterization test 無変更。

**テスト**
- 新規 `tests/unit/web/test_singleton_clients.py`: 2 回 request を送って同じ `sec_client` インスタンスが再利用されることを ID 比較で検証
- `tests/integration/test_service_assembly.py` は無変更 (下位互換 2 引数 API を使用)

---

### 5-2. Native bulk_upsert (#3〜#6)

**問題**: `BaseRepository.upsert()` は `find_one` → `setattr` or `add` → `flush` で **2 クエリ / record**。N 件を loop すると 2N クエリ + N flush。

**設計**

`BaseRepository` に protected メソッドを追加:

```python
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

async def _bulk_upsert_native(
    self,
    rows: list[dict],
    *,
    index_elements: list[str],
    update_columns: list[str],
) -> None:
    """SQLite native UPSERT (INSERT ... ON CONFLICT DO UPDATE)。
    単一 statement で N 件を処理。戻り値は None (batch 用途)。
    呼び出し側は件数のみ別途管理する。
    """
    if not rows:
        return
    stmt = sqlite_insert(self._model).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=index_elements,
        set_={col: stmt.excluded[col] for col in update_columns},
    )
    await self._session.execute(stmt)
    await self._session.flush()
```

**前提**: 各 natural key に unique index が必要。Task 1 (モデル棚卸し) で以下を検査:

| Model | Natural key | 確認事項 |
|---|---|---|
| `FinancialData` | `(company_id, period_type, fiscal_year, fiscal_year_end)` | 既存 UniqueConstraint の有無 |
| `Valuation` | `(company_id, date)` | 同 |
| `AnalysisTarget` | `(company_id,)` | 同 |
| `Filing` (SEC) | `(company_id, accession_no)` | 同 |
| `Filing` (EDINET) | `(company_id, doc_id)` | 同 (複合または別) |

無ければ `UniqueConstraint` を追加 (schema change, ただし `CREATE UNIQUE INDEX` で既存データ保持)。

**各 repository の書き換え**

`FinancialRepository.bulk_upsert` (例):
```python
async def bulk_upsert(self, company_id: str, records: list[dict]) -> int:
    rows = [{"company_id": company_id, **r} for r in records]
    if not rows:
        return 0
    update_cols = [
        c for c in rows[0].keys()
        if c not in ("company_id", *FINANCIAL_NATURAL_KEY)
    ]
    await self._bulk_upsert_native(
        rows,
        index_elements=["company_id", *FINANCIAL_NATURAL_KEY],
        update_columns=update_cols,
    )
    return len(records)
```

API (引数・戻り値) 無変更。サービス層・テスト無変更。

**クエリ数**
- before: 2N (SELECT + INSERT/UPDATE per record) + N flush
- after: 1 (native UPSERT) + 1 flush

---

### 5-3. Filing sync 一括化 (#7)

**問題**: `services/filing_sync.py:42-72` `update_from_sec` は filing ごとに `find_by_accession` → `upsert` (= 3 クエリ / filing)。

**設計**

`FilingRepository` に追加:
```python
async def find_existing_accessions(
    self, company_id: str, accessions: list[str],
) -> set[str]:
    """指定 accession_no のうち既存のものだけ返す。"""
    if not accessions:
        return set()
    stmt = select(Filing.accession_no).where(
        Filing.company_id == company_id,
        Filing.accession_no.in_(accessions),
    )
    result = await self._session.execute(stmt)
    return set(result.scalars().all())

async def find_existing_doc_ids(
    self, company_id: str, doc_ids: list[str],
) -> set[str]:
    """EDINET 用。同パターン。"""
    ...

async def bulk_upsert(
    self, company_id: str, records: list[dict], *, source: str,
) -> int:
    """native UPSERT で一括書き込み。
    source="SEC" なら natural key = (company_id, accession_no)
    source="EDINET" なら natural key = (company_id, doc_id)
    """
    if source == "SEC":
        keys = ["company_id", "accession_no"]
    elif source == "EDINET":
        keys = ["company_id", "doc_id"]
    else:
        raise ValueError(f"unknown source: {source}")
    # _bulk_upsert_native に委譲
    ...
```

**Filing モデルの natural key 要件**: `Filing` テーブルは source 別に独立した natural key を持つ。設計上 `accession_no` と `doc_id` は別カラムのため、それぞれに partial unique index または (source, key) 複合 unique を設定できる。Task 1 で現状の制約を確認し、`_bulk_upsert_native` の `index_elements` で source 別に切替可能なことを確認する。

`FilingSyncService.update_from_sec` を書き換え:
```python
async def update_from_sec(self, company_id, cik):
    filing_list = await self._sec.list_filings(cik, max_years=2)
    accessions = [e["accessionNumber"] for e in filing_list if e.get("accessionNumber")]
    existing = await self._repo.find_existing_accessions(company_id, accessions)

    new_rows = []
    for entry in filing_list:
        accession = entry.get("accessionNumber")
        if not accession or accession in existing:
            continue
        # ... row 組み立て (現状ロジック踏襲)
        new_rows.append(row)

    if new_rows:
        await self._repo.bulk_upsert(company_id, new_rows)

    logger.info("Filing update for %s: %d new filings", company_id, len(new_rows))
    return len(new_rows)
```

`update_from_edinet` も同パターンで書き換え。

**クエリ数**
- before (N filing): 1 + 3N
- after (N filing): 1 + 1 + 1 = 3

**API 互換**: `update_from_sec(company_id, cik) -> int` / `update_from_edinet(company_id, edinet_code) -> int` 無変更。

**挙動保存**: 現状の「既存 filing はスキップ (更新しない)」を維持するため、`new_rows` に入れない時点でスキップ。bulk_upsert には新規分のみ渡す。

---

### 5-4. Watchlist eager load (#8)

**問題**: `web/routes/watchlists.py:detail_page` が `get_watchlist` + `list_items` の 2 await round-trip。

**設計**

Step 1: `Watchlist` モデルの relationship 確認 (未定義なら追加)
```python
class Watchlist(Base):
    items: Mapped[list[WatchlistItem]] = relationship(back_populates="watchlist")
```

Step 2: `WatchlistRepository.get_with_items()`:
```python
async def get_with_items(self, watchlist_id: int) -> Watchlist | None:
    stmt = (
        select(Watchlist)
        .where(Watchlist.id == watchlist_id)
        .options(selectinload(Watchlist.items))
    )
    result = await self._session.execute(stmt)
    return result.scalar_one_or_none()
```

Step 3: `WatchlistService.get_with_items()` (薄い wrapper)

Step 4: `detail_page` route を書き換え:
```python
wl = await services.watchlist_service.get_with_items(watchlist_id)
if wl is None: raise HTTPException(404, ...)
return render(request, "watchlists/detail.html", {"watchlist": wl, "items": wl.items})
```

既存 `get_watchlist()` / `list_items()` は **他の呼び出し箇所が残る可能性があるため削除しない**。

**改善**: Web hot path での Python↔DB 間 await 往復が 2 → 1 に半減。

---

### 5-5. ベンチマーク

**配置**: `tests/benchmarks/test_bulk_upsert_perf.py` (新規ディレクトリ)

```python
@pytest.mark.benchmark
@pytest.mark.parametrize("n", [50, 500])
async def test_financial_bulk_upsert_wallclock(session, n):
    repo = FinancialRepository(session)
    records = [_make_record(fy=2000 + i) for i in range(n)]
    t0 = time.perf_counter()
    await repo.bulk_upsert("US_BENCH", records)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\nbulk_upsert N={n}: {elapsed_ms:.1f} ms")
```

**マーカー登録と default 除外** (`pyproject.toml [tool.pytest.ini_options]`):
```toml
markers = [
    ...既存...,
    "benchmark: 性能計測テスト (デフォルト除外)",
]
addopts = ["-m", "not benchmark"]   # 新規 (既存 addopts は未設定)
```

`pytest` 通常実行では benchmark マーク付きテストは自動除外される。手動実行時は `pytest -m benchmark tests/benchmarks/ -s --override-ini="addopts="` または明示的に `-m benchmark` で上書き。

**測定対象**

| 計測 | Before | After 期待 |
|---|---|---|
| FinancialRepository.bulk_upsert N=50 | 実測 | 10x 以上 |
| FinancialRepository.bulk_upsert N=500 | 実測 | 30x 以上 |
| FilingSyncService.update_from_sec N=100 | 実測 (mock SEC) | 5x 以上 |
| ValuationRepository.bulk_upsert N=50 | 実測 | 10x 以上 |

結果は `report.md` に記録。

**注意**: SQLite in-memory ベンチはディスク I/O を反映しない。本番 (ファイル DB) は更に効く想定。

---

## 6. 実装順 (Task 骨格)

```
Task 1: モデル unique index 棚卸し (+ 必要なら UniqueConstraint 追加)
  ↓
Task 2: BaseRepository._bulk_upsert_native 追加 + 単体テスト
  ↓
Task 3: FinancialRepository.bulk_upsert 差し替え (#4)
  ↓
Task 4: ValuationRepository.bulk_upsert 差し替え (#6)
  ↓
Task 5: TargetRepository.bulk_upsert 差し替え (#5)
  ↓
Task 6: FilingRepository.bulk_upsert 新規 + FilingSyncService 一括化 (#7)
  ↓
Task 7: ClientBundle + AppState singleton 化 (#1)
  ↓
Task 8: Watchlist selectinload (#8)
  ↓
Task 9: ベンチマーク測定 & report.md 記録
  ↓
Task 10: 全テスト通過 + カバレッジ維持 + 最終 commit
```

各 Task は TDD 1 cycle (failing test → 実装 → green → commit)。完了ごとに `report.md` へ追記。

---

## 7. リスクと緩和

| リスク | 緩和策 |
|---|---|
| unique index が無いモデル | Task 1 で棚卸し、無ければ `UniqueConstraint` 追加を同タスク内で実施 |
| `update_columns` が空になるケース (全列が natural key) | `_bulk_upsert_native` で assert、空なら `on_conflict_do_nothing` にフォールバック |
| `_bulk_upsert_native` は ORM オブジェクトを返さない | 既存 `bulk_upsert` の戻り値が件数 `int` であることを Task 2 で再確認 |
| singleton 化でテストの fixture isolation が壊れる | pytest の `app` fixture を function scope に留め、`AppState.create` を毎テストで呼ぶ |
| singleton 化で httpx client が shutdown 時に close されない | `AppState.dispose()` で `await client.close()` を追加、FastAPI lifespan で呼ぶ |

---

## 8. 完了の定義 (Definition of Done)

- [ ] Task 1-10 すべて完了
- [ ] 全テスト PASS (718+)
- [ ] カバレッジ 96% 以上
- [ ] ruff clean (`tests/` `src/`)
- [ ] `tests/benchmarks/` 実測値が `report.md` 記録済み、改善目標達成
- [ ] `run_daily_update` の直列性維持 (integration test or code review)
- [ ] `master.md` の Phase D ステータスを ✅ Done に更新

**Status**: 2026-04-19 設計承認済み、次は writing-plans で `plan.md` 生成
