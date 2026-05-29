# `feat/sec-section-extractor` 追加リファクタリング A1-A17 修正プラン (2026-05-17)

## 1. 背景

`docs/additional-refactoring-candidates-2026-05-17.md` で列挙した A1-A17 を、
merge 前に修正するためのプラン。元ドキュメントの A-K と Skip 推奨はスコープ外。

A1-A17 は以下の 5 領域にまたがる:

- P0 Security: stored XSS (A1)
- P1 ADR-004 alignment: 対象 filing scope / PageIndex 独立 / runbook 整合性 (A2-A4 + A15)
- P1 Correctness / data integrity: extractor 全体失敗 / queue atomicity / worker ownership / lifecycle (A5-A7, A14)
- P2 UI Lifecycle: 分析タブ polling (A8-A10)
- P2 Diagnostics / Read models: PageIndex diagnostic / pipeline filter (A11-A12)
- P3 Hardening: API validation / CLI contracts (A13, A16, A17)

### 確定方針 (ブレスト合意済み)

| 項目 | 方針 |
|---|---|
| PR 分割 | 5 本 (P0 / ADR alignment / correctness / UI / hardening) |
| マージ順 | PR1 → PR2 → PR3 → PR4 → PR5 |
| A2 | 方針 1: ADR-004 を SEC 限定に明文化、`annual_report` を分析候補から除外。`6-K` は UI 候補に含める (`_FULL_TEXT_FALLBACK` で best-effort) |
| A6 | repo 内部の commit をやめ、service 側で 1 transaction に集約 |
| A12 | `list_recent` / `count` 両方に extractor filter を追加、legacy PageIndex-era rows は完全スルー |
| A15 | docs 修正 + worker fixture と runbook の key 名の static check を 1 件追加 |
| A16 | `screening run` parser に `--desc` を追加 (mutually-exclusive group) |
| A17 | `rag` subparser の `--json` default を `argparse.SUPPRESS` にし、root の値を尊重 |
| ADR | ADR-004 を amendment し、A2/A3 を明記する (新規 ADR は作らない) |
| 検証 | PR ごとに「関連 unit + npm test + git diff --check」+ PR2/PR3 の merge gate に integration / E2E |

---

## 2. PR 構成 (確定)

| # | PR タイトル案 | 含む候補 | 主要触るファイル | 依存 |
|---|---|---|---|---|
| 1 | `fix(web): prevent stored XSS in analysis queue rows` | A1 | `web/static/app.js`, 新規 `web/static/queue_panel.js`, `tests/js/` | 単独 |
| 2 | `fix(rag): align ADR-004 scope and PageIndex lifecycle` | A2 / A3 / A4 / A15 + ADR-004 amendment | `routes/api.py`, `routes/analysis_jobs.py`, `cli/container.py`, `shared/clients.py`, `services/rag_service.py`, `services/analysis_worker.py`, `docs/adr/004-...md`, `docs/analysis-jobs-runbook.md` | ADR amendment が先頭 commit |
| 3 | `fix(rag): harden analysis job execution invariants` | A5 / A6 / A7 / A14 | `services/filing_section_extractor.py`, `services/rag_service.py`, `services/analysis_queue.py`, `services/analysis_worker.py`, `repositories/analysis_job.py` | PR2 後推奨 (worker/repo 同ファイル touch 順序付け) |
| 4 | `fix(web): correct analysis tab polling lifecycle` | A8 / A9 / A10 | `web/static/app.js`, 新規 `web/static/analysis_tab.js`, `tests/js/` | 単独 |
| 5 | `fix: harden diagnostics, read models, API and CLI contracts` | A11 / A12 / A13 / A16 / A17 | `services/pageindex/diagnostics.py`, `repositories/analysis.py`, `services/analysis.py`, `routes/analysis_jobs.py`, `cli/screening.py`, `cli/rag.py`, `cli/app.py`, `HOW_TO_USE.md` | PR2 後推奨 (`routes/analysis_jobs.py` 同ファイル touch 順序付け) |

### マージ順

`PR1 → PR2 → PR3 → PR4 → PR5`

- PR1 (XSS) を最初に安全側に倒す
- PR2 は ADR amendment を含むためレビュー往復のバッファを取る
- PR3 は PR2 後 (`analysis_worker.py` / `analysis_job.py` の touch を順序付け)
- PR4 / PR5 は他 PR と独立 (異なるファイル群)。並列レビュー可

---

## 3. 共通検証戦略

各 PR で実行:

```bash
scripts/infisical-run uv run pytest <該当 unit> -q
npm test
git diff --check
```

**Merge gate (追加要件)**:

| PR | 追加 gate |
|---|---|
| PR1 | queue rendering XSS regression JS test (`company_id='<img src=x onerror=...>'` fixture が HTML として解釈されないこと) |
| PR2 | `pageindex.enabled=false` での `run_full_analysis_stream` integration test + E2E filing 1 件 (US_AAPL 2025 10-K) で extractor regression 確認 |
| PR3 | enqueue→worker completion integration test + ownership mismatch targeted test + phase 後 exception 時に `current_analysis_type is None` の targeted test + E2E filing 1 件で happy path regression |
| PR4 | polling lifecycle / persisted progress JS test |
| PR5 | (unit のみで十分) |
| 全 PR マージ後 | `pytest` 全体 + E2E filing 1 件で最終 regression |

---

## 4. ADR-004 Amendment (PR2 C1 で commit)

ADR-004 末尾に新規セクションを追加:

```markdown
### Amendment 2026-05-17 — Scope clarification and PageIndex independence

ADR-004 適用後の運用で 2 点の暗黙仕様が混乱を招いていたため、明文化する。

#### A. 対象 filing は SEC のみ
`FilingType` enum の 4 種 (`10-K` / `10-Q` / `20-F` / `6-K`) のうち、本 ADR の
`FilingSectionExtractor` は **SEC source の HTML 入力のみ** を扱う。EDINET の
`annual_report` は `converted.pdf` のみ保存され `_SECTION_KEY_MAP` のいずれにも
該当しないため、UI / API の分析候補からも除外する。EDINET PDF への対応は別 ADR で扱う。

- `ANALYSIS_FILING_TYPES` から `FilingType.ANNUAL_REPORT` を削除
- `POST /api/analysis-jobs` は filing が SEC source かつ ADR-004 サポート 4 種で
  あることを 422 で validate

#### B. 定型分析は `pageindex.enabled` から独立
定型分析の章抽出は LLM 非依存・PageIndex 非依存。`pageindex.enabled` の意味を
以下に再定義:

| 機能 | `pageindex.enabled=true` | `pageindex.enabled=false` |
|---|---|---|
| 定型分析 (`run_full_analysis` / `run_full_analysis_stream`) | 動く | **動く (本 amendment による)** |
| `preflight` (step-3 LLM probe) | 動く | 動く (LlmClient 直叩き、PageIndex 非依存) |
| `ask_question` (自由質問) | 動く | disabled error を返す |
| `build_index` / `get_index_status` | 動く | disabled error を返す |

- `RagService` は常に構築される。`pageindex_service: PageIndexService | None`
- worker の `rag_service is None` ガードは削除 (失敗状態として捕捉不要)
```

---

## 5. PR1 詳細: `fix(web): prevent stored XSS in analysis queue rows`

### 5.1 含む候補

- **A1**: ダッシュボード分析キューの stored XSS リスク (`app.js:1721-1740`, `app.js:1766`)

### 5.2 攻撃面

`renderQueueRow(job)` は以下 3 値を template literal で HTML 化し、
`listEl.innerHTML = jobs.map(renderQueueRow).join("")` に流す:

| 値 | 出所 | リスク |
|---|---|---|
| `job.company_id` | DB persisted (現状は `US_xxx`/`JP_xxx` だが ingest 経路次第で汚染) | `<a>` 子・`href` 両方に未エスケープ挿入 |
| `job.current_analysis_type` | DB persisted | `<span>` に未エスケープ挿入 |
| `job.status` | DB persisted (`QUEUE_BADGE` lookup と badge label 経由) | label は lookup 経由なので低 / class は `badge.cls` で外部由来 |
| `job.job_id` | DB int 主キー | data-job-id 属性、整数性は API 保証あるが defense-in-depth で escape |

### 5.3 採用アプローチ

`queue_panel.js` を新規 ES module に切り出し、DOM node 生成へ変更。
既存 `analysis_status.js` パターンと一致し、jsdom (devDependency 済み) で test 容易。

### 5.4 実装方針

**新規ファイル**: `src/stock_analyze_system/web/static/queue_panel.js` (ES module)

`app.js` から `QUEUE_BADGE`, `formatQueueElapsed`, `renderQueueRow` を移動:

```js
export const QUEUE_BADGE = { /* 既存 mapping を移動 */ };

export function formatQueueElapsed(createdAtIso, now = Date.now()) {
    /* 既存ロジック、now を引数化 (test 容易性) */
}

export function renderQueueRow(job, doc = document) {
    const li = doc.createElement("li");
    li.className = "event-row";

    const badge = QUEUE_BADGE[job.status] ?? { label: job.status, cls: "" };
    const badgeEl = doc.createElement("span");
    badgeEl.className = `badge ${badge.cls}`.trim();
    badgeEl.textContent = badge.label;
    li.appendChild(badgeEl);

    const link = doc.createElement("a");
    link.href = `/stocks/${encodeURIComponent(job.company_id)}`;
    link.className = "event-row__id";
    link.textContent = job.company_id;
    li.appendChild(link);

    const typeEl = doc.createElement("span");
    typeEl.className = "event-row__meta";
    typeEl.textContent = job.current_analysis_type ?? "—";
    li.appendChild(typeEl);

    const progressEl = doc.createElement("span");
    progressEl.className = "event-row__meta";
    progressEl.textContent = `${job.progress_current}/${job.progress_total}`;
    li.appendChild(progressEl);

    const timeEl = doc.createElement("span");
    timeEl.className = "event-row__time";
    timeEl.textContent = formatQueueElapsed(job.created_at);
    li.appendChild(timeEl);

    if (job.status === "failed" || job.status === "pending") {
        const btn = doc.createElement("button");
        btn.className = "btn-icon";
        btn.dataset.action = job.status === "failed" ? "dismiss" : "cancel";
        btn.dataset.jobId = String(job.job_id);
        btn.title = job.status === "failed" ? "非表示" : "キャンセル";
        btn.textContent = "×";
        li.appendChild(btn);
    }

    return li;
}
```

**`app.js` 側**:

```js
// fetchQueue() 内
listEl.replaceChildren();
if (jobs.length === 0) {
    if (emptyEl) emptyEl.style.display = "";
    if (countEl) countEl.textContent = "";
} else {
    for (const job of jobs) {
        listEl.appendChild(renderQueueRow(job));
    }
    if (emptyEl) emptyEl.style.display = "none";
    if (countEl) countEl.textContent = `${jobs.length} 件`;
}
```

### 5.5 Test gate

**新規** `tests/js/queue_panel.test.mjs` (4 件):

- `renderQueueRow escapes company_id HTML` — `<img src=x onerror=...>` が HTML として解釈されないこと
- `renderQueueRow escapes current_analysis_type` — `<script>` が `<script>` として解釈されないこと
- `renderQueueRow encodes company_id in href` — `US_A/B?C` → `/stocks/US_A%2FB%3FC`
- `renderQueueRow sets data-job-id via dataset` — `job_id: 42` → `dataset.jobId === "42"`

### 5.6 Merge gate (PR1)

- 既存 `tests/js/analysis_status.test.mjs` pass
- 新規 `tests/js/queue_panel.test.mjs` pass (4 件)
- `npm test` 全体 pass
- `git diff --check` clean
- 手動: dashboard 起動して queue panel が従来と同じ見た目で表示されること

### 5.7 未確定事項

- `app.js` (IIFE) から `queue_panel.js` (ES module) を呼ぶ方式。
  `base.html` の script tag を実装計画段階で確認し、(a) `<script type="module">`
  別途読み込み / (b) `app.js` 内で動的 `import()` / (c) `app.js` 全体 module 化
  のいずれかを採用。既存 `analysis_status.js` の参照方法に揃える。

### 5.8 Out of scope

- `app.js` 全体の module 化 (本 PR では `queue_panel.js` だけ切り出す)
- 他の `innerHTML` 使用箇所 (本ブランチ内で別箇所があれば実装計画段階で grep 確認)

---

## 6. PR2 詳細: `fix(rag): align ADR-004 scope and PageIndex lifecycle`

### 6.1 含む候補

- A2 / A3 / A4 / A15 + ADR-004 amendment

### 6.2 Commit 分割 (4 commits)

| commit | type | 主な変更ファイル |
|---|---|---|
| C1 | `docs(adr): amend ADR-004 to scope filings to SEC and decouple from pageindex.enabled` | `docs/adr/004-sec-filing-section-extractor.md` |
| C2 | `fix(api): restrict analysis candidates to SEC filings (A2)` | `web/routes/api.py`, `web/routes/analysis_jobs.py`, `tests/unit/web/test_analysis_jobs.py`, `tests/unit/web/test_api.py` |
| C3 | `fix(rag): construct RagService independent of pageindex.enabled (A3)` | `shared/clients.py`, `cli/container.py`, `services/rag_service.py`, `services/analysis_worker.py`, tests |
| C4 | `docs(runbook): align llama-server config and error_details keys with ADR-004 (A4 + A15)` | `docs/analysis-jobs-runbook.md`, `tests/unit/services/test_analysis_worker.py` (static check) |

C1 を先頭に置く理由: ADR が C2/C3 の仕様根拠なので、レビュー時に「なぜこの修正が正しいか」を ADR で先に提示できる。

### 6.3 C1: ADR-004 amendment

§4 に記載した内容を ADR-004 末尾に追加。

### 6.4 C2: A2 (API/UI annual_report 除外)

`web/routes/api.py:23-31`:

```python
# Before
ANNUAL_FILING_TYPES = [FilingType.TEN_K, FilingType.TWENTY_F, FilingType.ANNUAL_REPORT]
ANALYSIS_FILING_TYPES = [*ANNUAL_FILING_TYPES, FilingType.TEN_Q]

# After
ANNUAL_FILING_TYPES = [FilingType.TEN_K, FilingType.TWENTY_F, FilingType.ANNUAL_REPORT]  # 互換のため残す
ANALYSIS_FILING_TYPES = [FilingType.TEN_K, FilingType.TWENTY_F, FilingType.TEN_Q, FilingType.SIX_K]
```

`web/routes/api.py:314-349` (`rag_filing_options`):
- docstring を `10-K / 10-Q / 20-F / 6-K (SEC)` に更新
- `list_by_types` 後に `filing.source == "SEC"` で defense-in-depth filter (Filing model に `source` 列があれば)

`web/routes/analysis_jobs.py:56-92` (`create_job`):

```python
# 既存 ownership check の直後に追加
ADR004_SUPPORTED = {FilingType.TEN_K, FilingType.TEN_Q, FilingType.TWENTY_F, FilingType.SIX_K}
if filing.source != "SEC" or filing.filing_type not in ADR004_SUPPORTED:
    raise HTTPException(
        status_code=422,
        detail=f"filing_type={filing.filing_type} (source={filing.source}) is not supported by ADR-004 extractor",
    )
```

**test 追加**:
- `tests/unit/web/test_analysis_jobs.py`:
  - `test_create_job_rejects_annual_report`
  - `test_create_job_rejects_non_sec_source`
  - `test_create_job_accepts_six_k`
- `tests/unit/web/test_api.py`:
  - `test_rag_filing_options_excludes_annual_report`

### 6.5 C3: A3 (pageindex.enabled=false でも RagService 構築)

`shared/clients.py`:

```python
def build_client_bundle(config: AppConfig) -> ClientBundle:
    ...
    from stock_analyze_system.services.llm_client import LlmClient
    bundle.llm = LlmClient(config.llm)  # 常に構築
    if config.pageindex.enabled:
        from stock_analyze_system.services.pdf_converter import PdfConverter
        bundle.pdf_converter = PdfConverter()  # ask_question 経路でのみ使う
    return bundle
```

`cli/container.py:147-176`:

```python
# rag_service を常に構築、pageindex_service だけ条件付き
from stock_analyze_system.services.filing_section_extractor import FilingSectionExtractor
from stock_analyze_system.services.llm_client import LlmClient
from stock_analyze_system.services.rag_service import RagService
from stock_analyze_system.repositories.rag_qa_history import RagQaHistoryRepository

llm_client = llm_client_pre or LlmClient(config.llm)
qa_history_repo = RagQaHistoryRepository(session)

pageindex_service = None
if config.pageindex.enabled:
    from stock_analyze_system.repositories.document_index import DocumentIndexRepository
    from stock_analyze_system.services.pdf_converter import PdfConverter
    from stock_analyze_system.services.pageindex import PageIndexService
    doc_index_repo = DocumentIndexRepository(session)
    pdf_converter = pdf_converter_pre or PdfConverter()
    pageindex_service = PageIndexService(
        doc_index_repo=doc_index_repo,
        pdf_converter=pdf_converter,
        llm_client=llm_client,
        config=config.pageindex,
    )

rag_service = RagService(
    pageindex_service=pageindex_service,
    analysis_repo=analysis_repo,
    llm_client=llm_client,
    qa_history_repo=qa_history_repo,
    filing_content_service=filing_content_service,
    section_extractor=FilingSectionExtractor(),
)
```

`services/rag_service.py`:

```python
class PageIndexDisabledError(RuntimeError):
    """PageIndex 経路が config で無効化されているときの guard error."""

class RagService:
    def __init__(self, ..., pageindex_service: PageIndexService | None, ...):
        self._pageindex = pageindex_service
        ...

    async def ask_question(self, filing, question):
        if self._pageindex is None:
            raise PageIndexDisabledError("pageindex.enabled=false; この機能は無効です")
        ...

    async def build_index(self, filing):
        if self._pageindex is None:
            raise PageIndexDisabledError("pageindex.enabled=false; この機能は無効です")
        ...

    async def get_index_status(self, filing):
        if self._pageindex is None:
            raise PageIndexDisabledError("pageindex.enabled=false; この機能は無効です")
        ...
```

定型分析メソッド (`run_full_analysis`, `run_full_analysis_stream`, `run_analysis`, `preflight`) は変更なし。

`services/analysis_worker.py:184-188`:

```python
# Before
rag = container.rag_service
if rag is None:
    raise RuntimeError("RAG service is not enabled")

# After
rag = container.rag_service  # 常に構築される (PR2 C3 で None 廃止)
```

**test 更新**:
- `tests/unit/services/test_rag_service.py`:
  - 新規: `test_run_full_analysis_works_when_pageindex_disabled`
  - 新規: `test_ask_question_raises_when_pageindex_disabled`
  - 新規: `test_build_index_raises_when_pageindex_disabled`
- `tests/unit/services/test_analysis_worker.py`:
  - 既存 `test_worker_fails_when_rag_disabled` を削除
- `tests/unit/cli/test_container.py`:
  - 新規: `test_setup_services_constructs_rag_when_pageindex_disabled`

### 6.6 C4: A4 + A15 (runbook 修正)

**A4** — `docs/analysis-jobs-runbook.md:28-35` を ADR-004 検証済み構成に置換:

```bash
llama-server \
  --model /path/to/Qwen3.6-27B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 \
  --jinja \
  --ctx-size 131072 \
  --n-gpu-layers 99 \
  --parallel 1 \
  > data/logs/llama-server.log 2>&1
```

説明文に 1 行追加:

> `--parallel N` は `--ctx-size` を slot 数で分割する。ADR-004 step 3 の
> `risk_factors` (RXRX で ~58K prompt tokens) を slot に収めるため
> `--parallel 1` (= slot ctx 131072) が必須。旧 `--ctx-size 32768 --parallel 4`
> (= slot ctx 8192) は実 10-K で context overflow する
> (`docs/adr/004-sec-filing-section-extractor.md` §Known limitations 参照)。

**A15** — `docs/analysis-jobs-runbook.md:54-63` の表を以下に置換:

| 形 | 意味 | 次の手 |
|---|---|---|
| `{"extraction_error": {"message": "...", "diagnostic": {...}}}` | step-3 preflight 失敗 | §3.1 / §3.2 |
| `{"extraction_error": {"message": "..."}}` (diagnostic 無し) | FilingSectionExtractor が parse 例外 | log の `section extraction failed for filing N` を grep |
| `{"failed_types": [{"type": "mda", "message": "..."}]}` | extractor 成功、特定タイプの step-3 LLM 失敗 | §3.3 |
| `{"failed_types": [{"type": "business_summary", "message": "ファイリングに該当章がありません"}]}` | filing 種別の構造上空 | 対処不要 |
| `{"index_build_error": {...}}` | **legacy (ADR-004 以前)** PageIndex 経路の失敗 | 再 enqueue で新形式 (`extraction_error`) に記録 |

**A15 static check**:

`services/analysis_worker.py` に module-level 定数を追加:

```python
ERROR_DETAILS_KEYS: frozenset[str] = frozenset({"extraction_error", "failed_types"})
```

`tests/unit/services/test_analysis_worker.py` に 1 件追加:

```python
def test_runbook_error_details_keys_match_worker_constants():
    from stock_analyze_system.services.analysis_worker import ERROR_DETAILS_KEYS
    runbook = Path("docs/analysis-jobs-runbook.md").read_text(encoding="utf-8")
    for key in ERROR_DETAILS_KEYS:
        assert f'"{key}"' in runbook, f"runbook missing key: {key}"
    assert '"index_build_error"' in runbook  # legacy 行
```

### 6.7 Merge gate (PR2)

**unit**:

```bash
scripts/infisical-run uv run pytest \
  tests/unit/services/test_rag_service.py \
  tests/unit/services/test_analysis_worker.py \
  tests/unit/services/test_filing_section_extractor.py \
  tests/unit/web/test_api.py \
  tests/unit/web/test_analysis_jobs.py \
  tests/unit/cli/test_container.py \
  -q
```

**integration (必須)**:
- `pageindex.enabled=false` 構成で `run_full_analysis_stream` がフル完走する integration test
- `ask_question` が `PageIndexDisabledError` を返す integration test

**E2E (必須)**:
- US_AAPL 2025 10-K でフル analysis run。4/4 completed, `pipeline='extractor'`, 失敗ゼロを確認

### 6.8 未確定事項

1. `Filing.source` 列の存在確認 (なければ `filing_type` whitelist のみで判定)
2. runbook §3.1 / §3.2 の参照が ADR-004 amendment 後も適切な指示になっているか
3. legacy `index_build_error` データの「再 enqueue」運用判断確認

### 6.9 Out of scope

- EDINET PDF 用 extractor 実装 (別 ADR)
- `pipeline='extractor'` filter の read model 側適用 (PR5 の A12)
- worker の `current_analysis_type` clear (PR3 の A14)

---

## 7. PR3 詳細: `fix(rag): harden analysis job execution invariants`

### 7.1 含む候補

- A5 / A6 / A7 / A14

### 7.2 Commit 分割 (4 commits)

| commit | type | 主な変更 |
|---|---|---|
| C1 | `fix(extractor): raise when raw HTML is missing, distinguish from per-type structural absence (A5)` | `filing_section_extractor.py`, `rag_service.py`, tests |
| C2 | `fix(queue): make dismiss + create atomic in single transaction (A6)` | `repositories/analysis_job.py`, `services/analysis_queue.py`, tests |
| C3 | `fix(worker): verify filing.company_id matches job.company_id (A7)` | `services/analysis_worker.py`, tests |
| C4 | `fix(worker): clear current_analysis_type on all terminal transitions (A14)` | `repositories/analysis_job.py`, `services/analysis_worker.py`, tests |

### 7.3 C1: A5 — extractor 全体失敗と per-type 構造的欠如の分離

`filing_section_extractor.py` に新規 exception:

```python
class ExtractionInputMissingError(RuntimeError):
    """storage_path に raw/*.htm が無い等、章抽出の入力自体が欠落している."""
```

- `extract()` 冒頭で `_find_raw_html` が None なら raise (現在の「warning + 空 dict return」を置換)
- per-type の structural missing (10-Q `business_summary` 等) は raise せず空文字を返す (既存挙動)

`rag_service.py:284-348` (`run_full_analysis_stream`):

```python
try:
    sections = await self._section_extractor.extract(filing)
except ExtractionInputMissingError as exc:
    yield {
        "event": "error",
        "analysis_type": None,  # worker が extraction_error に積む既存経路に乗せる
        "message": str(exc),
        "diagnostic": None,
    }
    return
```

`rag_service.py:422-446` (`run_full_analysis`):
- 非 stream は extractor の例外をそのまま伝播 (CLI fail-fast)
- per-type loop の既存挙動は変更なし

**test**:
- `tests/unit/services/test_filing_section_extractor.py`:
  - `test_extract_raises_when_raw_html_missing`
  - `test_extract_returns_empty_for_structural_misses` (10-Q `business_summary` は空文字、raise しない)
- `tests/unit/services/test_rag_service.py`:
  - `test_run_full_analysis_raises_when_raw_html_missing` (非 stream)
  - `test_run_full_analysis_stream_yields_extraction_error_when_raw_html_missing` (stream)

### 7.4 C2: A6 — dismiss + create を 1 transaction に

`repositories/analysis_job.py:166-185` (`dismiss_past_for_filing`):

```python
async def dismiss_past_for_filing(self, company_id, filing_id) -> int:
    """同 filing の failed/cancelled (未 dismiss) を dismiss する。

    Note: commit は呼び出し側 (service) の責務。
    """
    stmt = (
        update(AnalysisJob)
        .where(...)
        .values(dismissed_at=now_utc())
    )
    result = await self._session.execute(stmt)
    # commit を削除
    return result.rowcount
```

`services/analysis_queue.py:28-55` (`enqueue`):

```python
async with self._enqueue_lock:
    async with self._session_factory() as session:
        repo = AnalysisJobRepository(session)
        existing = await repo.find_active_by_company_filing(company_id, filing_id)
        if existing is not None:
            return existing, False
        try:
            await repo.dismiss_past_for_filing(company_id, filing_id)
            job = await repo.create(company_id=company_id, filing_id=filing_id)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            existing = await repo.find_active_by_company_filing(company_id, filing_id)
            if existing is not None:
                return existing, False
            raise
return job, True
```

**test**:
- `tests/unit/services/test_analysis_queue.py`:
  - `test_enqueue_rollbacks_dismiss_when_create_fails`
- `tests/unit/repositories/test_analysis_job_repo.py`:
  - `dismiss_past_for_filing` の commit 削除に伴うシグネチャ確認

### 7.5 C3: A7 — worker の filing.company_id 検証

`services/analysis_worker.py:189-193`:

```python
filing = await container.filing_service.get_filing_by_id(job.filing_id)
if filing is None:
    raise ValueError(f"filing_id={job.filing_id} not found")
if filing.company_id != job.company_id:
    raise ValueError(
        f"filing_id={job.filing_id} belongs to {filing.company_id}, "
        f"not job.company_id={job.company_id}"
    )
```

既存 `Exception` ハンドラに落ち、`error_details={"reason": ...}` で記録される。

**test**:
- `tests/unit/services/test_analysis_worker.py`:
  - `test_run_job_fails_on_ownership_mismatch`

### 7.6 C4: A14 — current_analysis_type を terminal 遷移で必ず clear

`repositories/analysis_job.py:114-136` (`update_status`):

```python
async def update_status(
    self,
    job_id: int,
    status: JobStatus,
    *,
    completed_at=None,
    error_details: dict | None = None,
    clear_current_type: bool = False,
) -> None:
    values: dict = {"status": status.value}
    if completed_at is not None:
        values["completed_at"] = completed_at
    if error_details is not None:
        values["error_details"] = error_details
    if clear_current_type:
        values["current_analysis_type"] = None
    ...
```

`repositories/analysis_job.py:187-201` (`reset_running_to_failed`):

```python
.values(
    status=JobStatus.FAILED.value,
    error_details={"reason": reason},
    completed_at=now_utc(),
    current_analysis_type=None,  # ← 追加
)
```

`services/analysis_worker.py:157-172` (`_finalize`):

```python
await repo.update_status(
    job_id,
    status,
    completed_at=now_utc(),
    error_details=error_details,
    clear_current_type=True,
)
```

正常完了パスの `await repo.clear_current_type(job.id)` (line 235) は削除 (`_finalize` で 1 本化)。

**test**:
- `tests/unit/services/test_analysis_worker.py`:
  - `test_finalize_clears_current_type_on_failure`
  - `test_finalize_clears_current_type_on_cancelled`
  - `test_finalize_clears_current_type_on_completion` (二重 update なきこと)
- `tests/unit/repositories/test_analysis_job_repo.py`:
  - `test_reset_running_to_failed_clears_current_type`
  - `test_update_status_clears_current_type_when_flag_set`

### 7.7 Merge gate (PR3)

**unit**:

```bash
scripts/infisical-run uv run pytest \
  tests/unit/services/test_filing_section_extractor.py \
  tests/unit/services/test_rag_service.py \
  tests/unit/services/test_analysis_queue.py \
  tests/unit/services/test_analysis_worker.py \
  tests/unit/repositories/test_analysis_job_repo.py \
  -q
```

**integration / targeted (必須)**:
- `enqueue → worker completion` integration test (happy path)
- `enqueue → worker failure (extraction_error)` integration test (raw HTML 欠落 fixture)
- ownership mismatch targeted unit
- phase 後 exception での `current_analysis_type is None` targeted unit
- `enqueue` 中の `repo.create` 失敗で過去 dismiss が rollback される targeted unit

**E2E**:
- US_AAPL 2025 10-K で happy path regression。4/4 completed, `pipeline='extractor'`, `current_analysis_type IS NULL` 確認

### 7.8 未確定事項

1. `dismiss_past_for_filing` の他呼び出し箇所 (grep で確認、あれば caller commit 必須)
2. `update_status` の `clear_current_type` を default 変更にするか keyword 追加にするか (既存 caller の grep 結果次第)
3. `reset_running_to_failed` の `reason` 引数の UI 表示影響 (本 PR 範囲では確認のみ)

### 7.9 Out of scope

- runbook の `extraction_error` / `failed_types` / legacy `index_build_error` 表 (PR2 C4)
- `update_progress` の commit batch 化 (Round 1/2 Skip 対象)
- `AnalysisJob` モデルへの composite FK 制約 (影響範囲大、別 ADR レベル)
- UI 側の `current_analysis_type` 表示 (PR4 でカバー)

---

## 8. PR4 詳細: `fix(web): correct analysis tab polling lifecycle`

### 8.1 含む候補

- A8 / A9 / A10

### 8.2 Commit 分割 (4 commits)

| commit | type | 主な変更 |
|---|---|---|
| C1 | `refactor(web): extract analysis tab polling helpers to ES module` | 新規 `web/static/analysis_tab.js`、`app.js` から import |
| C2 | `fix(web): poll active job after filing options finish loading (A8)` | filing fetch の `.then` 内で `detectInProgress`、`queueMicrotask` 削除 |
| C3 | `fix(web): cancel stale polling on filing selector change (A9)` | `createPoller` で cancel 化、panel scope `activePoll`、selector change で abort |
| C4 | `fix(web): reflect persisted progress in status polling UI (A10)` | `applyEventToState` の phase handler で count/bar 更新、`jobToEvents` で running 中 `current_analysis_type=null` でも progress event |

### 8.3 C1: ES module への切り出し

**新規ファイル**: `src/stock_analyze_system/web/static/analysis_tab.js`

```js
// jobToEvents: pure function
export function jobToEvents(job, prevStatus) { /* 既存ロジック移植 */ }

// applyEventToState: pure state machine (DOM 操作なし)
export function applyEventToState(evt, state) {
    if (evt.event === "started") {
        state.total = evt.total || 0;
        state.completed = 0;
    } else if (evt.event === "phase") {
        if (typeof evt.index === "number") state.completed = evt.index;
        if (typeof evt.total === "number") state.total = evt.total;
    } else if (["done", "cached", "skipped"].includes(evt.event)) {
        state.completed = (evt.index ?? state.completed) + 1;
    } else if (evt.event === "error") {
        state.errored = true;
        state.error_messages = state.error_messages || [];
        state.error_messages.push(evt.message || "失敗");
    } else if (evt.event === "complete") {
        state.completed_event = true;
    }
    return state;
}

// createPoller: cancel 可能
export function createPoller({ jobId, intervalMs, fetchJob, onJob, onTerminal }) {
    let cancelled = false;
    let prevStatus = null;
    const interval = setInterval(async () => {
        try {
            const job = await fetchJob(jobId);
            if (cancelled || job === null) return;
            onJob(job, prevStatus);
            prevStatus = job.status;
            if (["completed", "failed", "cancelled"].includes(job.status)) {
                clearInterval(interval);
                if (!cancelled) onTerminal(job);
            }
        } catch (_) { /* transient */ }
    }, intervalMs);
    return {
        cancel() {
            cancelled = true;
            clearInterval(interval);
        },
        get cancelled() { return cancelled; },
    };
}
```

`app.js` 側は `applyEvent` (DOM 更新含む) を thin wrapper として残し、`applyEventToState` を呼んで state 更新、その後 DOM 反映。

### 8.4 C2: A8 — filing options fetch 完了後に detectInProgress

`app.js:844-873`:

```js
fetchJson(`/api/stocks/${companyId}/rag/filing_options`)
    .then((opts) => {
        ...
        filingSelect.value = String(def ? def.id : annuals[0].id);
        updateFilingMeta(filingSelect.value);
        loadAnalyses(filingSelect.value);
        // A8: filing.value がセットされた直後に detect
        detectInProgress(filingSelect.value);
    })
```

`app.js:1245-1247` の `queueMicrotask` ブロックを削除。

### 8.5 C3: A9 — selector change での stale poll cancel

```js
let activePoll = null;

async function pollJob(jobId, filingIdForReload) {
    if (activePoll) activePoll.cancel();
    const state = { total: 0, completed: 0, errored: false, completed_event: false };
    return new Promise((resolve) => {
        const poller = createPoller({
            jobId,
            intervalMs: 5000,
            fetchJob: async (id) => {
                const resp = await fetch(`/api/analysis-jobs/${id}`);
                return resp.ok ? resp.json() : null;
            },
            onJob: (job, prevStatus) => {
                const events = jobToEvents(job, prevStatus);
                for (const ev of events) applyEvent(ev, state);
            },
            onTerminal: async (job) => {
                if (job.status === "completed") {
                    if (filingSelect.value === String(filingIdForReload)) {
                        await loadAnalyses(filingIdForReload);
                    }
                }
                if (job.status === "failed" || job.status === "cancelled") {
                    if (rerunBox) rerunBox.hidden = false;
                }
                dispatchAnalysisJobsChanged();
                activePoll = null;
                resolve();
            },
        });
        activePoll = poller;
    });
}

filingSelect.addEventListener("change", () => {
    if (activePoll) {
        activePoll.cancel();
        activePoll = null;
    }
    detectInProgress(filingSelect.value);
});
```

### 8.6 C4: A10 — persisted progress の UI 反映

`applyEventToState` の phase handler (PR4 C1 で新規切り出し済み):

```js
} else if (evt.event === "phase") {
    if (typeof evt.index === "number") state.completed = evt.index;
    if (typeof evt.total === "number") state.total = evt.total;
}
```

`app.js` の `applyEvent` (DOM wrapper):

```js
} else if (evt.event === "phase") {
    setDeterminate();
    applyEventToState(evt, state);
    const lbl = evt.label || evt.analysis_type || "進行中";
    progressLabel.textContent = `${lbl} を実行中…`;
    progressCount.textContent = `${state.completed} / ${state.total}`;
    const pct = state.total
        ? Math.round((state.completed / state.total) * 100)
        : 0;
    progressBar.style.width = `${pct}%`;
}
```

`jobToEvents` の running 分岐:

```js
} else if (job.status === "running") {
    if (prevStatus !== "running") {
        events.push({ event: "started", total: job.progress_total });
    }
    events.push({
        event: "phase",
        index: job.progress_current,
        total: job.progress_total,
        analysis_type: job.current_analysis_type ?? null,
        label: job.current_analysis_type ?? "進行中",
    });
}
```

### 8.7 Merge gate (PR4)

**unit (新規)** `tests/js/analysis_tab.test.mjs`:
- `applyEventToState` 各 event 遷移 (5-7 件)
- `jobToEvents` status 分岐 (pending / running / completed / failed (extraction_error / index_build_error / failed_types) / cancelled、6-8 件)
- `createPoller` cancel 動作 (3 件)

**手動 verification (merge 前必須)**:
- active job がある状態で analysis タブを開く → in-progress 接続される (A8)
- job A polling 中に selector を B へ変更 → A 完了時に B の表示が上書きされない (A9)
- DB に running job `{progress_current: 2, progress_total: 4}` を seed → status polling のみで UI が `2 / 4`, 50% bar 表示 (A10)

### 8.8 未確定事項

1. module 化方式 (PR1 と統一: `base.html` の script tag 構造確認)
2. `applyEvent` DOM wrapper の test 範囲 (pure 関数中心か、jsdom DOM レベルも含めるか)
3. `detectInProgress` の二重呼び出し回避 (`activePoll` あれば skip するガード)

### 8.9 Out of scope

- `_tab_analysis.html:9` の `<option value="">読み込み中…</option>` 文言改善
- queue rendering / XSS (PR1)
- `analysis_status.js` の badge ロジック
- `app.js` 全体の module 化

---

## 9. PR5 詳細: `fix: harden diagnostics, read models, API and CLI contracts`

### 9.1 含む候補

- A11 / A12 / A13 / A16 / A17

### 9.2 Commit 分割 (4 commits)

| commit | type | 主な変更 |
|---|---|---|
| C1 | `fix(pageindex): record diagnostic even when wrapped LLM call raises (A11)` | `services/pageindex/diagnostics.py`, test |
| C2 | `fix(rag): filter list_recent and count by pipeline=extractor (A12)` | `repositories/analysis.py`, `services/analysis.py`, test |
| C3 | `fix(api): clamp /api/analysis-jobs limit to [1, 100] (A13)` | `web/routes/analysis_jobs.py`, test |
| C4 | `fix(cli): respect global --json from rag subcommand and accept screening --desc (A16 + A17)` | `cli/screening.py`, `cli/rag.py`, `HOW_TO_USE.md`, test |

### 9.3 C1: A11 — diagnostic を例外時にも記録

`services/pageindex/diagnostics.py:138-163` (`wrapped_llm_completion`):

```python
def wrapped_llm_completion(model, prompt, ...):
    from pageindex import utils as pi_utils

    max_tokens_effective = max_tokens
    if _max_tokens_clamp is not None and max_tokens is not None:
        max_tokens_effective = min(max_tokens, _max_tokens_clamp)

    base_diag = {
        "kind": "sync",
        "model": model,
        "max_tokens": max_tokens,
        "prompt_head": (prompt or "")[:200] if isinstance(prompt, str) else "",
    }
    if max_tokens_effective != max_tokens:
        base_diag["max_tokens_effective"] = max_tokens_effective

    try:
        result = pi_utils.llm_completion(
            model=model, prompt=prompt, ...,
            max_tokens=max_tokens_effective,
        )
    except Exception as exc:
        _record({
            **base_diag,
            "finish_reason": "error",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        })
        raise

    if return_finish_reason and isinstance(result, tuple) and len(result) == 2:
        content, finish_reason = result
    else:
        content, finish_reason = result, None
    _record({
        **base_diag,
        "finish_reason": finish_reason,
        "content_len": _coerce_content_len(content),
        "content_head": _coerce_content_head(content),
    })
    return result
```

`wrapped_llm_acompletion` も同様の try/except ラップ。

**test**:
- `test_wrapped_llm_completion_records_diagnostic_on_raise`
- `test_wrapped_llm_acompletion_records_diagnostic_on_raise`
- `test_wrapped_llm_completion_records_finish_reason_on_success` (既存 success path)
- `test_diagnostic_is_not_stale_after_failure`

### 9.4 C2: A12 — list_recent / count に pipeline filter

`repositories/analysis.py`:

```python
async def list_recent(self, limit: int = 5) -> list[CompanyAnalysis]:
    """最近作成された extractor pipeline 分析結果."""
    stmt = (
        select(CompanyAnalysis)
        .where(CompanyAnalysis.pipeline == PIPELINE_EXTRACTOR)
        .order_by(CompanyAnalysis.created_at.desc())
        .limit(limit)
    )
    result = await self._session.execute(stmt)
    return list(result.scalars().all())

async def count(self) -> int:
    """extractor pipeline 件数のみカウント (legacy PageIndex-era は除外)."""
    from sqlalchemy import func
    stmt = (
        select(func.count())
        .select_from(CompanyAnalysis)
        .where(CompanyAnalysis.pipeline == PIPELINE_EXTRACTOR)
    )
    result = await self._session.execute(stmt)
    return result.scalar_one()
```

`services/analysis.py`: `count_all` の docstring に「returns extractor pipeline count only」を追記。

**test**:
- `tests/unit/repositories/test_other_repos.py` (or `test_analysis_repo.py`):
  - `test_list_recent_filters_pipeline_extractor`
  - `test_count_filters_pipeline_extractor`
- `tests/unit/services/test_analysis.py`:
  - `test_count_all_returns_extractor_only`

### 9.5 C3: A13 — `/api/analysis-jobs` limit を [1, 100] に clamp

`web/routes/analysis_jobs.py:106-132`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

@router.get("")
async def list_jobs(
    company_id: str | None = None,
    filing_id: int | None = None,
    status: str | None = None,
    include_dismissed: bool = False,
    limit: int = Query(20, ge=1, le=100),
    queue: AnalysisQueueService = Depends(_get_queue),
):
    ...
```

**test**:
- `tests/unit/web/test_analysis_jobs.py`:
  - `test_list_jobs_rejects_negative_limit`
  - `test_list_jobs_rejects_zero_limit`
  - `test_list_jobs_rejects_overlimit`
  - `test_list_jobs_accepts_max_limit`

### 9.6 C4: A16 + A17 — CLI argparse 修正

**A16** — `cli/screening.py:46-48`:

```python
order_group = rn.add_mutually_exclusive_group()
order_group.add_argument(
    "--asc", action="store_false", dest="desc", help="昇順",
)
order_group.add_argument(
    "--desc", action="store_true", dest="desc", help="降順 (default)",
)
rn.set_defaults(desc=True)
```

**A17** — `cli/rag.py:21`:

```python
parser.add_argument(
    "--json", action="store_true", default=argparse.SUPPRESS,
    help="JSON出力 (root --json も尊重される)",
)
```

`cli/app.py` 内で `args.json` を読む箇所は `getattr(args, "json", False)` パターンに統一する補助変更 (必要なら C4 内に含める)。

`HOW_TO_USE.md`:
- screening run docs は parser 修正で動くようになるので変更不要
- `--json` のグローバル動作を 1 文で明記:
  > `--json` はグローバルオプション。`stock-analyze --json rag health` も `stock-analyze rag --json health` も同じく JSON 出力になる。

**test**:
- `tests/unit/cli/test_app.py`:
  - `test_global_json_is_respected_when_followed_by_rag`
  - `test_rag_subcommand_json_works_alone`
  - `test_rag_subcommand_no_json_default_false`
- `tests/unit/cli/test_screening_cli.py` (新規 or 既存):
  - `test_screening_run_accepts_desc`
  - `test_screening_run_asc_sets_desc_false`
  - `test_screening_run_mutually_exclusive`

### 9.7 Merge gate (PR5)

**unit**:

```bash
scripts/infisical-run uv run pytest \
  tests/unit/services/test_pageindex_diagnostics.py \
  tests/unit/services/test_pageindex_service.py \
  tests/unit/repositories/test_other_repos.py \
  tests/unit/services/test_analysis.py \
  tests/unit/web/test_analysis_jobs.py \
  tests/unit/cli/test_app.py \
  tests/unit/cli/test_screening_cli.py \
  -q
```

**手動 verification**:
- `uv run stock-analyze screening run --desc --gte roe=0.1 --sort roe` → exit 0、ROE 降順 (A16)
  - (旧版で `ROIC` を例示していたが、`SCREENING_NUMERIC_FIELDS` に `roic` は無いため `roe` で代替)
- `uv run stock-analyze screening run --asc --desc ...` → argparse の mutually exclusive group が `error: not allowed with argument --asc` を返し exit 2 (A16)
- `uv run stock-analyze --json rag health` → JSON 出力 (A17)
- `uv run stock-analyze rag --json health` → JSON 出力 (A17)
- `uv run stock-analyze rag health` → human text (A17)

### 9.8 未確定事項

1. `argparse.SUPPRESS` の subparser における実機挙動 (root の `args.json=True` が残るかを実機検証)
2. `cli/rag.py` ハンドラの `args.json` アクセスパターン (`getattr` か直接読みか) を grep で確認
3. `BaseRepository.count` の signature と他 caller 影響範囲
4. `tests/unit/cli/test_screening_cli.py` の有無

### 9.9 Out of scope

- dashboard 表示の「分析件数」文言変更
- `count_legacy` 等の追加 API
- `BaseRepository.count` 自体への filter 引数追加
- root parser から `--json` を廃止する案

---

## 10. 全体マージ後の最終 regression

```bash
scripts/infisical-run uv run pytest -q
npm test
git diff --check
```

E2E:
- US_AAPL 2025 10-K でフル analysis run
- 4/4 completed, `pipeline='extractor'`, `current_analysis_type IS NULL`, `raw_answer` fallback 0 件
- Round 1/2 の検証ログと同じプロセス (`docs/refactoring-candidates-2026-05-17.md` §7 と同手順)

---

## 11. 関連参照

- `docs/additional-refactoring-candidates-2026-05-17.md` — A1-A17 候補一覧
- `docs/refactoring-candidates-2026-05-17.md` — A-K 候補一覧 (Round 1/2 完了済み)
- `docs/extractor-pattern-verification-2026-05-17.md` — extractor pattern 検証
- `docs/adr/004-sec-filing-section-extractor.md` — ADR-004 (本 spec で amendment 追加)
- `docs/analysis-jobs-runbook.md` — 運用ランブック (A4 + A15 で更新)
- `docs/step3-reasoning-runaway-verification.md` — llama-server 検証済み構成
- `MEMORY/project_section_extractor_pivot.md` — ADR-004 移行メモ
