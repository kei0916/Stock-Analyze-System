# 決算分析失敗の根本解決 — Filing 本体取得パイプラインと UI 整合化 設計

- **作成日**: 2026-05-04
- **ステータス**: ドラフト (ブレインストーミング承認後)
- **対象**: `RagService`, `FilingService`, `FilingSyncService`, `cli/filings.py`, `web/routes/api.py`, `web/static/app.js`, 新規 `FilingContentService`

---

## 1. 背景・問題定義

Web UI から「決算分析🔍」を押すと、ほぼ全ての filing で `"ファイリングの PDF が未取得です。先に stock-analyze rag index を実行してください"` エラーが返る。実データでは `filings` テーブル 167 件中 163 件が `storage_path = NULL` で、選択中の filing も無視される。さらに案内文のとおり `rag index` を実行しても storage_path が前提なので状況は変わらない。

### 1.1 観察された 2 つの故障

1. **Web UI が選択中の `filing_id` を分析 API へ送っていない**
   - `app.js:1014` 付近で `analyzeButton` のクリック時に `filing_type` のみクエリに付与。
   - `web/routes/api.py:212-244` の `rag_analyze` は `_require_latest_filing` 経由で「最新 filing」を取り直す。
   - ⇒ 画面でインデックス済みの古い filing を選んでも、実際の解析対象は未取得の最新 filing にずれる。

2. **DB 上の Filing メタデータは登録されるが、本体 (HTML/PDF) を fetch して `storage_path` を埋める経路が一度も実装されていない**
   - `FilingSyncService` (`services/filing_sync.py`) は SEC submissions / EDINET 一覧から **メタデータのみ** upsert。
   - `cli/filings.py download` は `update_from_sec` / `update_from_edinet` を呼ぶだけ。
   - `SecEdgarClient.get_filing_html` / `EdinetClient.download_xbrl_zip` は実装済みだが **どこからも呼ばれていない**。
   - その結果、`RagService.run_full_analysis_stream` は `filing.storage_path` チェックで即時 error イベントを返す (`rag_service.py:116-125`)。

### 1.2 影響

- AAPL の RAG タブのデフォルトは最新 10-Q になり得るが、その 10-Q の `storage_path = None` で分析失敗。分析可能なのはたまたま既存インデックスがある 3 件のみ。
- TSM の 2024 20-F (インデックス済み) を選んでも、API は 2025 20-F の最新を取り直して `storage_path = None` で落ちる。
- エラーメッセージの `先に stock-analyze rag index` 案内も、`rag index` 自体が `storage_path` 前提なので misleading。

---

## 2. ゴールとスコープ

採用方針 (ブレインストーミングで合意した **案 C**)：

> **UI バグ修正 + HTML/PDF 取得パイプライン実装 + UX 整備**

含めるもの：

- フロント: 選択中 `filing_id` を analyze / index / ask へ送信。`fetching` 進捗イベントの表示。未取得 filing の選択肢に flag を出して注記表示。
- バック: `filing_id` を受け取れる API 改修。`/rag/filing_options` の default 選定をインデックス済み or 取得済み優先に。
- 取得経路: 新規 `FilingContentService` で SEC HTML / EDINET PDF を fetch → 階層ストレージへ保存 → DB の `storage_path` / `content_hash` を更新。
- CLI: `filings download` を「メタデータ sync + 本体取得」のフルセットに拡張。
- on-demand: `RagService` 各メソッドに「未取得なら自動 fetch」ガードを追加 (CLI と Web から共通利用)。
- エラー文言の刷新。

含めないもの：

- Alembic マイグレーション (既存カラムのみ使用)。
- WeasyPrint 大型 10-K の OOM 対策 (既存挙動を維持)。
- content_hash を PageIndex 再構築のトリガーに使う仕組み (記録のみ。将来拡張)。
- `rag analyze` などの並列バッチ化 (memory: `sync_company`/`run_daily_update` は意図的に直列、本機能も同様)。

---

## 3. アーキテクチャ概観

### 3.1 修正後フロー

```
[Web UI] -- POST /rag/analyze?filing_id=42 --> [API]
                                                ├─ get_filing_by_id(42) (company オーナーシップ検証)
                                                └─ rag.run_full_analysis_stream(filing)
                                                   ├─ if not filing.storage_path:
                                                   │     yield {"event": "fetching", "filing_id": 42}
                                                   │     filing = await content_service.ensure_content(filing)
                                                   ├─ yield {"event": "indexing"}
                                                   ├─ pageindex.get_or_create_index(filing)
                                                   └─ 4 タイプ分析を yield phase/done/...

[CLI] stock-analyze filings download AAPL
        ├─ filing_sync.update_from_sec(...)        (既存: メタデータのみ)
        └─ filing_content_service.fetch_for_company(company_id)  (新規: 本体取得)
```

### 3.2 責務分担サマリ

| コンポーネント | 役割 | 種別 |
|---|---|---|
| `FilingContentService` | 個別 filing の HTML/PDF を fetch → 階層ストレージ保存 → DB の `storage_path` / `content_hash` 更新。SEC は HTML 保存、EDINET は PDF 直接取得 (type=2)。 | 新規 |
| `FilingRepository.update_storage` / `get_latest_with_content` / `get_latest_indexed` | storage 更新 / 取得済み判定 / インデックス済み判定。 | 新規 |
| `cli/filings.py download` | sync の後に `FilingContentService.fetch_for_company` を呼ぶ。1 件でも fetch 失敗で exit 1。 | 改修 |
| `RagService` の 4 メソッド (`run_full_analysis_stream`, `run_full_analysis`, `run_analysis`, `ask_question`, `build_index`) | `_ensure_filing_content` ガードを通す。ストリーム系のみ NDJSON `fetching` イベント発火。 | 改修 |
| `web/routes/api.py` | `/rag/analyze` `/rag/index` `/rag/ask` に `filing_id` を追加。`_resolve_filing` ヘルパで company オーナーシップ検証。 | 改修 |
| `web/routes/api.py` `/rag/filing_options` | default の選定を「インデックス済 → 取得済 → fallback (未取得最新)」順に。filing オプションに `content_available` / `is_fallback_default` を含める。 | 改修 |
| `web/static/app.js` 分析・Q&A | `filing_id` を送る。`fetching` イベント表示。未取得 filing の注記。 | 改修 |
| `SecEdgarClient.get_primary_document_url` | submissions JSON から該当 accession の primaryDocument の完全 URL を返す。 | 新規 |
| `EdinetClient.download_pdf` | type=2 PDF 本文のバイト列を返す。 | 新規 |

`PdfConverter` は変更なし。`FilingContentService` は HTML/PDF を所定レイアウトに置くだけで、PDF 化は既存パイプラインに任せる。

---

## 4. ストレージレイアウト & データモデル

### 4.1 ファイルシステム階層 (既存 `FilingService.get_storage_path` 規則を踏襲)

```
{filings.base_path}/{source}/{company_id}/{fiscal_year}/{period_type}/{filing_type}/{key}/
   ├─ raw/                    # SEC: HTML を *.html で保存 (primaryDocument の filename 流用)
   │   └─ aapl-20240928.htm
   └─ converted.pdf            # SEC: PdfConverter.get_or_convert で生成
                              # EDINET: type=2 PDF を直接保存
```

- `key` = SEC は `accession_no`、EDINET は `doc_id`
- `base_path` = `config.filings.base_path` (デフォルト `data/filings`)
- 既存 storage_path がすでに DB にあって整合する場合は触らない。

### 4.2 Filing テーブル

DDL 変更なし。既存カラムを使う：

- `storage_path: str | None` — `FilingContentService` が確定したディレクトリパス (上記の `{key}/` まで) を書き込む。
- `content_hash: str | None` — 保存した HTML / PDF の SHA-256 を書き込む (記録目的。当面は再構築トリガに使わない)。

### 4.3 EDINET の取得形式

採用: **`type=2` (PDF 本文) を直接取得し `converted.pdf` として保存**。

理由:

- HTML→PDF 変換 (weasyprint) の数十秒〜数分のオーバーヘッド・font 解決失敗リスクを排除。
- EDINET PDF は元々ページ番号・目次が整備されているので PageIndex の精度に有利。
- XBRL は `financial_sync` の関心事なので兼用しない。

---

## 5. `FilingContentService` 詳細設計

### 5.1 インターフェース

```python
class FilingContentService:
    def __init__(
        self,
        filing_repo: FilingRepository,
        sec_client: SecEdgarClient,
        edinet_client: EdinetClient,
        config: FilingsConfig,
    ): ...

    async def ensure_content(self, filing: Filing) -> Filing:
        """filing.storage_path が空 (もしくはファイル不在) なら fetch & save & DB 更新。
        既に揃っていれば no-op。常に最新の Filing を返す。"""

    async def fetch_for_company(self, company_id: str) -> FetchSummary:
        """その企業の storage_path 未設定 filing を全件 fetch。エラーは部分継続。"""


@dataclass
class FetchSummary:
    fetched: int
    skipped: int
    failed: list[tuple[int, str]]  # (filing_id, error_message)
```

### 5.2 `ensure_content` のロジック

```
1. filing.storage_path があり、その配下に converted.pdf or raw/*.html or raw/*.htm が実在
   → そのまま filing を返す (no-op)。
   path 設定済みでもファイルが見つからない場合 (ディスク掃除・破損) は no-op を抜けて
   ステップ 2 以降で再 fetch する。

2. 期待ストレージパスを FilingService.get_storage_path で算出:
   - SEC:    key = filing.accession_no  (欠落 → ValueError)
   - EDINET: key = filing.doc_id        (欠落 → ValueError)
   - その他 source → NotImplementedError

3. mkdir(parents=True, exist_ok=True)

4. ソース別 fetch & save:
   - SEC:    await _fetch_sec(filing, target_dir)
   - EDINET: await _fetch_edinet(filing, target_dir)

5. 保存ファイル本体の SHA-256 を計算し
   filing_repo.update_storage(filing.id, storage_path=str(target_dir), content_hash=...)

6. ORM の filing オブジェクトに storage_path / content_hash を反映し返す。
```

### 5.3 SEC 取得 (`_fetch_sec`)

```
1. company の cik を Company リポジトリから引く (filing.company から relationship 経由)。
2. sec_client.get_primary_document_url(cik, filing.accession_no) で URL を引く。
3. sec_client.get_filing_html(url) で HTML を取得。
4. raw/<sanitized-filename> に保存 (../ 排除、拡張子保持)。
5. SHA-256 計算 → update_storage。
※ HTML→PDF 変換は呼ばない。後段の PdfConverter.get_or_convert が走る。
```

### 5.4 EDINET 取得 (`_fetch_edinet`)

```
1. edinet_client.download_pdf(filing.doc_id) で PDF バイト列を取得。
2. target_dir / "converted.pdf" に書き込み。
3. SHA-256 計算 → update_storage。
※ type=2 が無い書類は EDINET が 404 を返す → ContentNotFoundError として上位へ。
```

### 5.5 `fetch_for_company` のロジック

```
1. filing_repo.list_filings(company_id) で全件取得。
2. storage_path が None or 空のものだけ対象。
3. 直列で ensure_content を呼ぶ (rate limiter は SEC=10rps, EDINET=5s 間隔で既存)。
4. 各結果を集計し FetchSummary を返す。
5. 個別失敗は failed に積み、ループ継続。
```

並列化しない理由:

- SEC はトークンバケットがあるため複数 task の `gather` は実質直列化。
- EDINET は 5 秒間隔で並列化不可。
- 1 件のセッション例外で他を巻き込まないよう `try/except` で囲む。

### 5.6 エラー処理ポリシー

| 事象 | 振る舞い |
|---|---|
| 4xx (404 等) | `ContentNotFoundError` → 1 件 fail として次へ |
| 5xx / Network | 既存 `BaseClient` retry に委譲。尽きたら 1 件 fail |
| Disk full / OS Error | raise (致命的) |
| accession_no/doc_id 欠落 | `ValueError`、UI 経由なら NDJSON `error` |
| 既存ファイル名と衝突 | 上書き (再取得で content_hash 更新) |

### 5.7 新規例外

`stock_analyze_system.exceptions` に追加:

```python
class ContentFetchError(Exception):
    """Filing 本体取得時の汎用エラー。"""

class ContentNotFoundError(ContentFetchError):
    """対象 filing の本体が source 側に存在しない (404 等)。"""
```

---

## 6. RAG パイプライン統合

### 6.1 DI

```python
RagService.__init__(
    pageindex_service: PageIndexService,
    analysis_repo: AnalysisRepository,
    llm_client: LlmClient,
    qa_history_repo: RagQaHistoryRepository | None = None,
    filing_content_service: FilingContentService | None = None,  # ★ 追加
)
```

`Optional` でテスト容易性を確保。`setup_services` は実体を必須注入する。

### 6.2 `_ensure_filing_content` ヘルパ

```python
async def _ensure_filing_content(self, filing):
    if filing.storage_path:
        return filing
    if self._content_service is None:
        raise FileNotFoundError(
            "Filing content not available; run filings download first."
        )
    return await self._content_service.ensure_content(filing)
```

`run_analysis`, `ask_question`, `build_index` の冒頭で呼ぶ。

### 6.3 `run_full_analysis_stream` の改修

ストリーム系は raise の代わりに NDJSON イベントで通知:

```python
async def run_full_analysis_stream(self, filing):
    if not filing.storage_path:
        if self._content_service is None:
            yield {"event": "error", "analysis_type": None,
                   "message": ("ファイリング本体の自動取得に失敗しました。"
                               "`stock-analyze filings download <company_id>` を実行してください。")}
            yield {"event": "complete"}
            return
        yield {"event": "fetching", "filing_id": filing.id}
        try:
            filing = await self._content_service.ensure_content(filing)
        except Exception as exc:  # noqa: BLE001
            logger.exception("content fetch failed for filing %d", filing.id)
            yield {"event": "error", "analysis_type": None,
                   "message": f"本体取得に失敗しました: {exc}"}
            yield {"event": "complete"}
            return
    # ...既存の indexing → started → phase → done/cached/error → complete...
```

### 6.4 NDJSON イベント追加

| event | フィールド | 意味 |
|---|---|---|
| `fetching` | `filing_id: int` | 本体ダウンロード開始 (`indexing` の前段で 1 回) |

既存イベントは変更なし。

### 6.5 排他制御

- `PageIndexService._build_semaphore = asyncio.Semaphore(1)` で index 構築は既に直列。
- `ensure_content` の HTTP fetch は SEC/EDINET の rate limiter で実質直列。
- 同一 filing への並走 fetch は最後勝ちで OK (内容が決定的、hash が一致)。

---

## 7. CLI / DI 配線変更

### 7.1 `cli/filings.py` の `download` ハンドラ

```python
async def _handle_download(args, services):
    company = await require_company(services.company_service, args.company_id)

    if company.cik:
        synced = await services.filing_sync.update_from_sec(args.company_id, company.cik)
    elif company.edinet_code:
        synced = await services.filing_sync.update_from_edinet(args.company_id, company.edinet_code)
    else:
        print(f"No CIK or EDINET code for '{args.company_id}'. Cannot download filings.", file=sys.stderr)
        sys.exit(1)
    print(f"Synced {synced} filing metadata record(s) for '{args.company_id}'.")

    summary = await services.filing_content_service.fetch_for_company(args.company_id)
    print(f"Fetched content: {summary.fetched} new, "
          f"{summary.skipped} already-present, {len(summary.failed)} failed.")
    if summary.failed:
        for filing_id, msg in summary.failed:
            print(f"  filing_id={filing_id}: {msg}", file=sys.stderr)
        sys.exit(1)
```

`--metadata-only` フラグは導入しない (シンプル維持)。

### 7.2 `cli/rag.py` の影響

ハンドラのコード変更は不要 (RagService 側のガードで自動 fetch される)。CLI は長時間沈黙を避けるため進捗ログを 1 行追加:

```python
if not filing.storage_path:
    print(f"Filing content not present; fetching from {filing.source}...", flush=True)
```

### 7.3 DI 配線

`cli/container.py` `setup_services`:

```python
from stock_analyze_system.services.filing_content import FilingContentService

filing_content_service = FilingContentService(
    filing_repo=filing_repo,
    sec_client=sec_client,
    edinet_client=edinet_client,
    config=config.filings,
)

return ServiceContainer(
    ...
    filing_content_service=filing_content_service,  # 必須
    ...
)
```

`ServiceContainer` dataclass にフィールドを追加 (`filing_content_service: FilingContentService`、必須)。`web/dependencies.py` 経由でも同じインスタンスが行き渡る (`setup_services` を共有)。

### 7.4 新規 / 変更クライアントメソッド

```python
# SecEdgarClient
async def get_primary_document_url(self, cik: str, accession_no: str) -> str:
    """submissions JSON から該当 accession の primaryDocument の完全 URL を返す。
    accession 不在 → ValueError。
    submissions JSON は短期メモ化 (per-call キャッシュ)。"""

# EdinetClient
async def download_pdf(self, doc_id: str) -> bytes:
    """type=2 (PDF本文) を取得してバイト列を返す。
    API key 欠落 → ValueError。404 は呼び出し側で ContentNotFoundError に変換。"""
```

### 7.5 `filings.base_path` の解決

`FilingContentService.__init__` で `Path(filings_config.base_path)` を保持。相対パスはプロセス CWD 基準 (既存パターンと一致)。Web/CLI ともにリポジトリルートで起動する前提。

---

## 8. Web API / フロントエンド改修

### 8.1 API シグネチャ

```python
@router.post("/{company_id}/rag/analyze")
async def rag_analyze(
    request: Request,
    company_id: str,
    filing_id: int | None = None,
    filing_type: FilingType = FilingType.TEN_K,  # 後方互換
    services: ServiceContainer = Depends(get_services),
):
    rag = _get_rag_service(services)
    filing = await _resolve_filing(services, company_id, filing_id, filing_type)
    _enforce_heavy_request_limit(...)
    ...

@router.post("/{company_id}/rag/index")
async def rag_index(
    request: Request, company_id: str,
    filing_id: int | None = None,
    filing_type: FilingType = FilingType.TEN_K,
    services: ServiceContainer = Depends(get_services),
):
    ...

class AskRequest(BaseModel):
    question: str
    filing_id: int | None = None
    filing_type: FilingType = FilingType.TEN_K  # 後方互換

@router.post("/{company_id}/rag/ask")
async def rag_ask(
    request: Request, company_id: str,
    payload: AskRequest,
    services: ServiceContainer = Depends(get_services),
):
    rag = _get_rag_service(services)
    filing = await _resolve_filing(services, company_id, payload.filing_id, payload.filing_type)
    _enforce_heavy_request_limit(...)
    ...
```

ヘルパ:

```python
async def _resolve_filing(services, company_id, filing_id, filing_type):
    if filing_id is not None:
        filing = await services.filing_service.get_filing_by_id(filing_id)
        if filing is None or filing.company_id != company_id:
            raise HTTPException(404, f"filing_id={filing_id} not found for {company_id}")
        return filing
    filing = await services.filing_service.get_latest_filing(company_id, filing_type)
    if filing is None:
        raise HTTPException(404, f"No {filing_type} filings for {company_id}")
    return filing
```

`_require_latest_filing` は `_resolve_filing` で代替可能なので削除。

### 8.2 `/rag/filing_options` の default 選定

優先順位: **(1) インデックス済み → (2) 取得済み (storage_path 設定済み) → (3) fallback (未取得最新)**

```python
@router.get("/{company_id}/rag/filing_options")
async def rag_filing_options(company_id, years: int = 10, services = Depends(get_services)):
    since_year = date.today().year - years
    annuals = await services.filing_service.list_by_types(
        company_id, [str(t) for t in ANNUAL_FILING_TYPES], since_year=since_year,
    )

    default_filing = None
    if services.rag_service is not None:
        default_filing = await services.filing_service.get_latest_indexed(company_id)
    if default_filing is None:
        default_filing = await services.filing_service.get_latest_with_content(company_id)
    fallback_used = False
    if default_filing is None:
        default_filing = await services.filing_service.get_latest_any_type(company_id)
        fallback_used = True

    return {
        "default": _filing_to_option(default_filing, fallback=fallback_used) if default_filing else None,
        "annual_options": [_filing_to_option(f) for f in annuals],
    }
```

`_filing_to_option` を拡張:

```python
def _filing_to_option(filing, *, fallback: bool = False) -> dict:
    return {
        "id": filing.id,
        "filing_type": filing.filing_type,
        "period_type": filing.period_type,
        "fiscal_year": filing.fiscal_year,
        "period_end": filing.period_end.isoformat() if filing.period_end else None,
        "filed_at": filing.filed_at.isoformat() if filing.filed_at else None,
        "content_available": bool(filing.storage_path),
        "is_fallback_default": fallback,
    }
```

### 8.3 新規 Filing リポジトリメソッド

```python
async def get_latest_with_content(self, company_id: str) -> Filing | None:
    """storage_path が NULL でない filing のうち period_end / filed_at / fiscal_year 降順で最新を返す。"""

async def get_latest_indexed(self, company_id: str) -> Filing | None:
    """document_index テーブルと JOIN し、登録がある filing のうち最新を返す。
    Filing 状態のクエリは FilingRepository に集約する (DocumentIndexRepository には置かない)。"""
```

### 8.4 `app.js` の改修ポイント

**分析ボタン** (`analyzeButton`):

```js
const url = analyzeButton.dataset.analyzeUrl;
const filingId = filingSelect ? filingSelect.value : "";
const fullUrl = filingId ? `${url}?filing_id=${encodeURIComponent(filingId)}` : url;
```

`filing_type` クエリは送らない。

**Q&A ボタン**:

```js
const askPayload = { question: value };
const filingId = filingSelect ? filingSelect.value : "";
if (filingId) askPayload.filing_id = Number(filingId);
```

**選択肢ラベル** (`formatFilingOptionLabel`):

- `content_available === false` → 末尾に `[本体未取得]` を付与。
- `is_fallback_default === true` → 更に `（取得待ち）` を付与。

**未取得注記の表示**:

- 選択中 filing が `!content_available` のとき、分析ボタン下に注記を 1 行表示。
  > ⚠ この決算は本体未取得です。「決算分析🔍」を押すと自動取得しますが時間がかかる場合があります。
- `selectedFiling()` ヘルパ (新規) で filing オブジェクトを引いて出し分け。

**`fetching` イベント対応** (`applyEvent`):

```js
} else if (evt.event === "fetching") {
    showIndeterminate("決算本体をダウンロード中…");
}
```

`indexing` で上書きされる前提。

### 8.5 エラー文言の刷新

`rag_service.py` 内で発火する error イベントのメッセージを以下に統一:

- 自動取得不能 (`filing_content_service is None`):
  > ファイリング本体の自動取得に失敗しました。`stock-analyze filings download <company_id>` を実行してください。
- 取得失敗 (例外):
  > 本体取得に失敗しました: `<exc>`

---

## 9. テスト方針

| レイヤ | テスト | 観点 |
|---|---|---|
| 単体: `FilingContentService` | 新規 `tests/unit/services/test_filing_content_service.py` | (a) SEC HTML 保存 + SHA-256 + update_storage (b) EDINET PDF を converted.pdf に保存 (c) accession/doc_id 欠落 → ValueError (d) 4xx → ContentNotFoundError, 1 件 fail (e) `fetch_for_company` の partial-failure 集計 (f) 既に揃っていれば no-op |
| 単体: `EdinetClient.download_pdf` | 既存 `tests/unit/ingestion/test_edinet.py` 追記 | type=2 リクエスト・404・API key 欠落 |
| 単体: `SecEdgarClient.get_primary_document_url` | 既存 `tests/unit/ingestion/test_sec_edgar.py` 追記 | submissions のページネーション結合済み構造から URL 構築・accession 不在で ValueError |
| 単体: `FilingRepository` 新メソッド | 既存 `tests/unit/repositories/test_filing.py` 追記 | UPDATE が 1 行 idempotent / セレクタ正しさ |
| 単体: `RagService` 改修 | 既存 `tests/unit/services/test_rag_service.py` 追記 | (a) `_ensure_filing_content` が storage_path 設定後に既存パイプラインへ進む (b) ストリームの `fetching` → `indexing` → `started` 順序 (c) `filing_content_service=None` のとき error イベントで終了 (d) Q&A も同じガード経由 |
| 単体: Web API | 既存 `tests/unit/web/test_api.py` 追記 | (a) `?filing_id=` で `get_filing_by_id` が呼ばれ company オーナーシップ検証 404 (b) filing_id 未指定で従来挙動 (c) Q&A AskRequest に filing_id を含めた解決 (d) `/rag/filing_options` の default が「インデックス済 → 取得済 → fallback」順 |
| 統合: CLI `filings download` E2E | 既存 `tests/integration/` 追加 (httpx mock) | sync → fetch → DB の `storage_path` 更新の一連を SQLite + モック HTTP で検証。partial-failure で exit 1 |
| 手動 (スペックに明記) | フロントエンド + 実 SEC AAPL 10-K | (1) `filings download US_AAPL` で raw/*.html 生成 (2) `rag index US_AAPL` で converted.pdf 生成 (3) Web で FY2024 10-K 選択 → 4 タイプ完走 (4) FY2025 10-Q 選択 → fetching → indexing → done のイベント順 |

---

## 10. リスクと緩和策

| リスク | 影響 | 緩和策 |
|---|---|---|
| 大容量 HTML の取得タイムアウト | UI ストリーム停滞 | `BaseClient` の既存 timeout を継承。Web 経由は heavy_rate_limiter で同時 1 リクエスト |
| EDINET PDF が無い書類 (中間配信等) | `download_pdf` が 404 | `ContentNotFoundError` で 1 件失敗。CLI は exit 1 で通知 |
| 同一 filing への並走 fetch (Web + CLI) | 上書き競合 | 内容が決定的なので最後勝ちで OK。明示ロックは入れない |
| 既存 storage_path が壊れている (path 設定済みだが file 不在) | PageIndex で FileNotFound | `ensure_content` の no-op 判定で「path 設定 + raw/*.html or converted.pdf 実在」両方チェック |
| submissions JSON のキャッシュ | 古い primaryDocument を引く | 1 リクエスト内のみメモ化。永続キャッシュは持たない |
| WeasyPrint 変換失敗 (既存リスク) | SEC 大型 10-K で OOM | 本 PR スコープ外。既存挙動維持 |
| サーバ起動時にディスク権限なし | `filings/<source>/...` の mkdir 失敗 | `OSError` を raise。ログに失敗 path を含める |
| content_hash 不整合 (再取得で hash 変化) | 既存 PageIndex キャッシュとの食い違い | 当面は記録のみ。再構築トリガには未使用 (将来拡張) |

---

## 11. 互換性

- Alembic マイグレーション不要 (既存カラムのみ使用)。
- 既存の filing_type デフォルト経路は残るので、UI 以外の旧クライアントの `/rag/analyze`, `/rag/index`, `/rag/ask` 呼び出しも動く。
- `/rag/analyses` (GET) は既に filing_id を受け取っているので変更なし。
- 既存 `data/filings/` の既存ファイルは触らず、unset の filing から順に追加されていく。

---

## 12. 段階分け / 実装順序

1 PR で完結させる前提で、コミット単位を以下のとおり分ける：

1. `EdinetClient.download_pdf` / `SecEdgarClient.get_primary_document_url` 追加 + 単体テスト
2. `FilingRepository` の `update_storage` / `get_latest_with_content` / `get_latest_indexed` 追加 + 単体テスト
3. 例外クラス (`ContentFetchError`, `ContentNotFoundError`) 追加 + `FilingContentService` 新規 + 単体テスト
4. `cli/container.py` / `web/dependencies.py` に DI 配線
5. `cli/filings.py download` 拡張 + 統合テスト
6. `RagService` の `_ensure_filing_content` 改修 + 単体テスト
7. `web/routes/api.py` の `filing_id` 対応 + `/rag/filing_options` 改修 + テスト
8. `web/static/app.js` の filing_id 送信 + `fetching` イベント表示 + 未取得注記
9. 手動 E2E (本スペックの「手動検証」シナリオ)

---

## 13. ブレインストーミング合意事項 (記録)

- スコープは **C 案** (UI バグ修正 + 取得パイプライン + UX 整備)。
- 取得方法は **IV** (CLI `filings download` 拡張 + on-demand `rag index/analyze`)。
- EDINET 取得形式は **PDF 直接 (type=2)**。HTML→PDF 変換は SEC のみ既存パイプラインで実施。
- ストレージは **`raw/` と `converted.pdf` の二段構成**。
- `ensure_content` の責務は **HTML/PDF を所定レイアウトに置くまで**。weasyprint 変換は `PdfConverter` に残す。
- `SecEdgarClient.get_primary_document_url` を新設し、submissions JSON から URL 構築。
- `--metadata-only` フラグは **不要** (シンプル維持)。
- `filing_content_service` は **必須注入** (RAG 無効時も CLI で使うため)。
- Web の `fetching` イベントは **1 回だけ** 流す方式。
- `/rag/ask` も **filing_id 受け取り対応**。
- 未取得 filing は選択肢から除外せず、**flag 付きで表示 + 自動取得注記**。
