# Phase C: DRY / 重複排除 — Design

**Status**: Draft (2026-04-19)

**前提**: Phase D (性能改善) 完了直後。master.md の Phase 進捗表では Phase C は次順位。Phase D の /simplify レビューで 3 件の duplication / public API 二重化が Backlog に積まれている。本 spec はそれら 3 件を 1 つの Phase C サイクルで消費する。

---

## Goal

Phase D で新設した API 群に付随する重複と、新旧 API の二重化を、**後方互換を保ちつつ** 最小限の helper/adapter/enum 追加で解消する。

**成功条件:**

1. `FinancialRepository.bulk_upsert` と `ValuationRepository.bulk_upsert` が「1 行 delegate」に縮む
2. `FilingSyncService.update_from_sec` / `update_from_edinet` が共通 `_sync(adapter, ...)` に集約され、差分は adapter 定義だけに局所化
3. `WatchlistService.get_watchlist` / `list_items` が削除され、CLI も Web と同じく `get_with_items` 経由で watchlist + items を 1 クエリで取得
4. 既存テスト (718+) 全て PASS + 新規 unit test で helper / adapter を個別に検証
5. 外部から観測できる public API の挙動に regression がない (ベンチ含め)

---

## Non-Goals

- repo/service の巨大ファイル分割 — Phase A 範囲
- 未使用の関数 (`FilingRepository.find_by_accession` / `find_by_doc_id` など) の削除 — Phase E 範囲
- 命名・docstring の精査 (Phase D 範囲で明らかにおかしいものだけは /simplify で修正済) — Phase B 範囲
- `run_daily_update` の並列化 — out-of-scope (LLM デッドロック回避で意図的に直列)

---

## Master rule 例外の明示

master.md §ルール §4 で「public API は Phase D〜B では不変」を定めている。Task 3 で `WatchlistService.get_watchlist` / `list_items` を削除するため、**Phase C に限って次の例外を追加する**:

> Phase D で新 API (例: `get_with_items`) に置換された旧 method は、全 caller (src/tests 含む) が移行済みであれば Phase C で削除可。削除対象は本 spec で明示する。

- 削除対象: `WatchlistService.get_watchlist`, `WatchlistService.list_items`
- **非削除**: `WatchlistRepository.list_items` / `WatchlistRepository.get_by_id` (他 service から呼ばれる可能性があるため Phase E で棚卸し)
- **非削除**: `FilingRepository.find_by_accession` / `find_by_doc_id` (現状 caller 0 件だが public API → Phase E で棚卸し)

---

## Architecture

3 Task クラスタ、独立に TDD サイクルを回す。Task 間の依存は無い (順序任意)。本 spec は Task 1 → Task 2 → Task 3 の順を推奨。

```
┌──────────────┐  ┌──────────────────────┐  ┌──────────────┐
│  Task 1      │  │  Task 2              │  │  Task 3      │
│  Repo 層 DRY │  │  Service 層 DRY      │  │  Watchlist   │
│              │  │                      │  │  API 整理    │
│ BaseRepo     │  │ FilingSource (enum)  │  │ CLI 移行     │
│ +_bulk_upsert│  │ FilingSourceAdapter  │  │ +旧 method   │
│ _by_natural  │  │ FilingSyncService    │  │  削除        │
│  _key        │  │ ._sync               │  │              │
└──────────────┘  └──────────────────────┘  └──────────────┘
     ↓                    ↓                        ↓
Financial/        update_from_sec /            cli/watchlist
Valuation         update_from_edinet           Web route
.bulk_upsert      → adapter 組立 + 1 行 delegate は現状維持
→ 1 行 delegate
```

---

## Task 1: Repo 層 DRY — `_bulk_upsert_by_natural_key`

### 動機

`FinancialRepository.bulk_upsert` と `ValuationRepository.bulk_upsert` は同形の 5 行:

```python
rows = [{"company_id": company_id, **r} for r in records]
natural_key_cols = ("company_id", <DOMAIN_KEYS>)
update_cols = [c for c in rows[0].keys() if c not in natural_key_cols]
await self._bulk_upsert_native(rows, index_elements=list(natural_key_cols), update_columns=update_cols)
return len(records)
```

違うのは `natural_key_cols` の値 (`FINANCIAL_NATURAL_KEY` vs `("date",)`) だけ。

### 新規 helper (`BaseRepository`)

```python
async def _bulk_upsert_by_natural_key(
    self,
    records: list[dict],
    natural_key_cols: Sequence[str],
    *,
    scope_key: str | None = None,
    scope_value: Any = None,
) -> int:
    """自然キーで一括 UPSERT。scope_key 指定時は各 row に {scope_key: scope_value} を前置し、
    index_elements にも含める。空入力で 0、非空で len(records) を返す。"""
    if not records:
        return 0
    if scope_key is not None:
        rows = [{scope_key: scope_value, **r} for r in records]
        index_elements = [scope_key, *natural_key_cols]
    else:
        rows = list(records)
        index_elements = list(natural_key_cols)
    update_columns = [c for c in rows[0].keys() if c not in index_elements]
    await self._bulk_upsert_native(
        rows, index_elements=index_elements, update_columns=update_columns,
    )
    return len(records)
```

### 縮小後 (Financial/Valuation)

```python
# financial.py
async def bulk_upsert(self, company_id: str, records: list[dict]) -> int:
    return await self._bulk_upsert_by_natural_key(
        records, FINANCIAL_NATURAL_KEY,
        scope_key="company_id", scope_value=company_id,
    )

# valuation.py
async def bulk_upsert(self, company_id: str, records: list[dict]) -> int:
    return await self._bulk_upsert_by_natural_key(
        records, ("date",),
        scope_key="company_id", scope_value=company_id,
    )
```

### 適用範囲の明示

- **適用**: `FinancialRepository`, `ValuationRepository` の `bulk_upsert`
- **非適用**: `FilingRepository.bulk_upsert` — accession_no / doc_id はグローバル一意で `index_elements` に company_id を含めない (scope 概念に合わない)。現状の `_bulk_upsert_native` 直呼びを維持。
- **非適用**: `TargetRepository.bulk_add` — 「追加件数のみ返す」semantic のため事前 SELECT が必要、本 helper の「UPSERT」pattern に合わない。

### テスト計画 (TDD)

`tests/unit/repositories/test_base_repo.py` に `TestBulkUpsertByNaturalKey` クラス追加 (4 ケース):

1. **scope なし + update あり**: index_elements が natural_key_cols 一致、update_cols に残り全カラム
2. **scope あり + update あり**: 全 row に scope_key が前置、index_elements が [scope_key, *natural_key]
3. **空入力**: 即 return 0 (no SQL)
4. **`update_columns` が空になる**: natural_key が row 全カラムを覆う場合 → `_bulk_upsert_native` が `on_conflict_do_nothing` に分岐 (Phase D Task 2 で実装済)

Financial / Valuation の既存テストは API 不変で無変更 PASS。

### Commit

```
refactor(repo): introduce _bulk_upsert_by_natural_key helper

- BaseRepository に _bulk_upsert_by_natural_key を追加
- FinancialRepository / ValuationRepository の bulk_upsert を 1 行 delegate に縮小
- 新規 4 tests (scope 有/無 x update 有/無)
- 既存テスト無変更で PASS
```

(必要なら docs commit 別途)

---

## Task 2: Service 層 DRY — `FilingSource` + Adapter + `_sync`

### 動機

`FilingSyncService.update_from_sec` / `update_from_edinet` は同形のパイプライン (fetch → key 収集 → existing 検出 → map → bulk_upsert)。差分は client / key_field / find_existing 関数 / mapping ロジック / source タグの 5 箇所のみ。

### 2-1. `FilingSource` enum (`models/enums.py`)

```python
class FilingSource(StrEnum):
    SEC = "SEC"
    EDINET = "EDINET"
```

既存 `FilingType` / `AccountingStandard` と同じファイルに配置。**Phase B 候補だった「FilingRepository.bulk_upsert の stringly-typed」の解消を Phase C でついでに済ませる** (adapter で enum を要求するため、先に repo 側を enum 対応にする必要がある)。

### 2-2. `FilingRepository.bulk_upsert` signature 変更

```python
async def bulk_upsert(
    self, company_id: str, records: list[dict], *, source: FilingSource,
) -> int:
    if source is FilingSource.SEC:
        key_col = "accession_no"
    elif source is FilingSource.EDINET:
        key_col = "doc_id"
    ...
```

**破壊的変更**: source param は `str` → `FilingSource`。caller は `FilingSyncService` のみ (src/内) なので影響範囲は限定的。テストの `source="SEC"` 文字列は `source=FilingSource.SEC` に置換。

### 2-3. `FilingSourceAdapter` + `_sync` (`services/filing_sync.py`)

```python
@dataclass(frozen=True)
class FilingSourceAdapter:
    source: FilingSource
    fetch: Callable[[str], Awaitable[list[dict]]]
    key_field: str
    find_existing: Callable[[str, list[str]], Awaitable[set[str]]]
    map_record: Callable[[dict], dict]


def _map_sec_record(raw: dict) -> dict:
    """SEC filing raw dict → Filing row dict (update_from_sec 内のインライン mapping を抽出)"""
    ...


def _map_edinet_record(raw: dict) -> dict:
    """EDINET document raw dict → Filing row dict"""
    ...


class FilingSyncService:
    async def _sync(
        self, adapter: FilingSourceAdapter,
        company_id: str, external_id: str,
    ) -> int:
        try:
            raw = await adapter.fetch(external_id)
        except Exception as e:
            logger.warning(
                "filing fetch failed: source=%s id=%s err=%s",
                adapter.source, external_id, e,
            )
            return 0
        if not raw:
            return 0
        keys = [d[adapter.key_field] for d in raw]
        existing = await adapter.find_existing(company_id, keys)
        new_rows = [
            adapter.map_record(d) for d in raw
            if d[adapter.key_field] not in existing
        ]
        if not new_rows:
            return 0
        return await self._repo.bulk_upsert(
            company_id, new_rows, source=adapter.source,
        )

    async def update_from_sec(self, company_id: str, cik: str) -> int:
        adapter = FilingSourceAdapter(
            source=FilingSource.SEC,
            fetch=self._sec_client.list_filings,
            key_field="accessionNumber",
            find_existing=self._repo.find_existing_accessions,
            map_record=_map_sec_record,
        )
        return await self._sync(adapter, company_id, cik)

    async def update_from_edinet(self, company_id: str, edinet_code: str) -> int:
        adapter = FilingSourceAdapter(
            source=FilingSource.EDINET,
            fetch=self._edinet_client.list_documents,
            key_field="docID",
            find_existing=self._repo.find_existing_doc_ids,
            map_record=_map_edinet_record,
        )
        return await self._sync(adapter, company_id, edinet_code)
```

### テスト計画 (TDD)

**新規**: `TestFilingSyncInternal` クラスを `tests/unit/services/test_filing_sync.py` に追加。fake adapter + mock repo で `_sync` を単体検証 (5 ケース):

1. **happy path**: fetch 3 件、existing 1 件 → 2 件 bulk_upsert に渡す
2. **fetch 空**: 0 件 → 即 return 0、bulk_upsert 未呼び出し
3. **全件 existing**: fetch 3 件、existing 3 件 → new_rows 空 → return 0
4. **fetch 例外**: Exception → logger.warning + return 0
5. **map_record 呼び出し回数**: new_rows = raw - existing 件数と一致

**既存**: `update_from_sec` / `update_from_edinet` の behavioral test は API 不変で無変更 PASS (source アサート箇所のみ `FilingSource.SEC` に更新)。

### Commit

- (2a) `refactor(filing): introduce FilingSource enum`  
  enum 追加 + `FilingRepository.bulk_upsert(source=)` 型変更 + 既存テスト `source=FilingSource.SEC` に更新
- (2b) `refactor(filing_sync): unify source sync via adapter pattern`  
  Adapter + `_sync` + mapping 抽出 + 新規 5 unit tests

---

## Task 3: Watchlist API 整理 — CLI 移行 + 旧 method 削除

### 動機 / 現状

Phase D で `get_with_items` を追加して Web 側は移行済。CLI + tests はまだ `get_watchlist` + `list_items` の 2-call pattern。Phase C で:

1. CLI を `get_with_items` に移行 (Web と統一)
2. `WatchlistService.get_watchlist` / `list_items` を削除 (public API から除去)

### 残 caller 棚卸し (Phase C 着手時点)

- `src/stock_analyze_system/cli/watchlist.py:88,93` — `_handle_show`
- `tests/unit/cli/test_watchlist_cli.py` — 3 tests (`get_watchlist` / `list_items` mock)
- `tests/integration/test_service_assembly.py:91` — `list_items` 使用

### 3-1. CLI 書き換え (`cli/watchlist.py:87-109`)

```python
async def _handle_show(args, services):
    wl = await services.watchlist_service.get_with_items(args.watchlist_id)
    if wl is None:
        print(f"Watchlist {args.watchlist_id} not found.", file=sys.stderr)
        sys.exit(1)
    rows = [
        {"Company": item.company_id, "Status": item.status}
        for item in wl.items
    ]
    ...
```

### 3-2. `WatchlistService` cleanup (`services/watchlist.py`)

削除:
```python
async def get_watchlist(self, watchlist_id: int): ...
async def list_items(self, watchlist_id: int): ...
```

`WatchlistRepository` 側は触らない (`list_items` / `get_by_id` に他 service 経由の caller がある可能性。Phase E で棚卸し)。

### 3-3. テスト更新

- `tests/unit/cli/test_watchlist_cli.py`: 3 test の mock を `get_with_items` に統合。戻り値 wl mock に `.items` 属性を設定
- `tests/integration/test_service_assembly.py:91`: `list_items` 呼出しを `get_with_items(wl.id).items` に
- `tests/unit/services/test_watchlist_service.py`: `get_watchlist` / `list_items` の個別テストが残れば削除

### 3-4. master.md 追補

§ルール §4 に例外追加 (本 spec 「Master rule 例外の明示」節を master.md にも反映):

```markdown
4. **後方互換**: public API (service/repository 外部メソッド) は Phase D〜B では不変。
   **例外** (Phase C で適用済): Phase D で新 API (例: `get_with_items`) に置換された
   旧 method は、全 caller (src/tests 含む) が移行済みであれば削除可。
   削除対象は Phase C spec で明示する。
5. **Phase A** のみ自由な API 変更許容 (spec で明示)。
```

### Commit

- (3a) `refactor(cli): migrate watchlist show to get_with_items`  
  `cli/watchlist.py` + `tests/unit/cli/test_watchlist_cli.py` + `tests/integration/test_service_assembly.py`
- (3b) `refactor(watchlist): drop superseded service methods`  
  `services/watchlist.py` から `get_watchlist` / `list_items` 削除 + `tests/unit/services/test_watchlist_service.py` 更新 + `master.md` ルール追補

---

## テスト & 受け入れ

- **全 unit tests PASS**: 現 737 → +9 (Task 1: 4 / Task 2: 5 / Task 3: 0 新規、既存更新のみ) = **746 PASS 見込み**
- **全 integration tests PASS**: 現状維持 (Task 3 で 1 test の書き換えのみ)
- **benchmark**: 変更なし (API 不変)、デフォルト除外 (Phase D Task 9 で整備済)
- **coverage**: 96% 維持 (新 helper / adapter に unit test を付けるため低下しない見込み)
- **ruff clean**: Phase D 末時点で既存 8 errors、Phase C で新規 0 を目標

---

## 作業順序 (推奨)

1. **Task 1** — 独立、副作用なし。BaseRepository helper → Financial → Valuation の順。
2. **Task 2** — Task 1 と独立だが先に FilingSource enum commit を切る (repo signature 変更)。続けて adapter/sync commit。
3. **Task 3** — Task 1/2 と独立。CLI 移行 commit → method 削除 commit。
4. **最終 commit** — master.md 進捗表で Phase C 行 🔵 → ✅、Phase C report.md に完了サマリ。

全 Task 終了後、Phase D の /simplify と同等のレビューを 1 回走らせ Phase D の backlog 残余を再評価する。

---

## 参照

- Phase D design: `../phase-d-performance/design.md`
- Phase D report: `../phase-d-performance/report.md`
- master tracker: `../master.md`
