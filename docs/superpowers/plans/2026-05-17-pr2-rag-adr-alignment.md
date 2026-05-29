# PR2: align ADR-004 scope and PageIndex lifecycle — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ADR-004 の暗黙仕様 2 点 (対象 filing が SEC 限定であること、定型分析が `pageindex.enabled` から独立すること) を ADR amendment で明文化し、API / DI / RagService / worker / runbook を amendment 内容に揃える。

**Architecture:** 4 commits (C1 = ADR amendment、C2 = API/UI を SEC 4 filing type に固定、C3 = DI を再構成して `RagService` を常時構築・`PageIndexService` だけ条件付きに、C4 = runbook 表とコマンドを ADR-004 検証済み構成に揃え、worker に `ERROR_DETAILS_KEYS` 定数を追加して runbook と static check で同期)。設計境界が変わるのは C3 だけだが、それは ADR amendment の正本に基づくため新規 ADR は作らない。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, pytest (`scripts/infisical-run uv run pytest`)、ADR/runbook は Markdown

**ADR:** `docs/adr/004-sec-filing-section-extractor.md` (本 PR の C1 で末尾に Amendment 2026-05-17 を追記)

**Spec reference:** `docs/superpowers/specs/2026-05-17-additional-refactoring-a1-a17-design.md` §4 (Amendment 文面) / §6 (PR2 詳細)

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `docs/adr/004-sec-filing-section-extractor.md` | **Modify** (C1) | 末尾に `### Amendment 2026-05-17 — Scope clarification and PageIndex independence` を追記し、(A) SEC 限定方針 と (B) 定型分析を `pageindex.enabled` から独立化する仕様を明文化 |
| `src/stock_analyze_system/web/routes/api.py` | **Modify** (C2 + C3) | C2: (a) `ANALYSIS_FILING_TYPES` から `FilingType.ANNUAL_REPORT` を除外し、`FilingType.SIX_K` を含める。(b) module-level に `_is_adr004_target(filing)` helper を追加 (`source == "SEC"` かつ filing_type が 4 種に含まれる)。(c) `rag_filing_options` の `annual_options` と `default` の両経路を helper で post-filter する (default 探索条件は C3 で `pageindex_available` に再調整)。<br>C3: helper を 2 系統に分割 — `_get_rag_service` は `rag_service is None` だけ確認 (defense-in-depth、`rag_analyze` で使用)、`_get_pageindex_rag_service` は `pageindex_available` を確認 (`rag_ask` / `rag_index` で使用、rate limit より前に 503 で early return)。`rag_analyses` は ADR amendment §B 通り `pageindex.enabled=false` でも保存済み結果を返す (PageIndex 非依存)。`rag_history` は ask_question 副産物のため `pageindex_available=False` 時に空リスト。`rag_filing_options.default` の indexed lookup gate を `pageindex_available` に揃える |
| `src/stock_analyze_system/web/routes/analysis_jobs.py` | **Modify** (C2) | `create_job` の ownership check 直後に「`filing.source == "SEC"` かつ `filing.filing_type` が ADR-004 サポート 4 種に含まれる」ことを 422 で validate |
| `src/stock_analyze_system/shared/clients.py` | **Modify** (C3) | `build_client_bundle` で `LlmClient` を常に構築 (`pageindex.enabled` から切り離す)、`PdfConverter` だけ条件付き |
| `src/stock_analyze_system/cli/container.py` | **Modify** (C3) | `setup_services` 内の RAG 構築ブロックを (a) `RagService` 常時構築、(b) `PageIndexService` だけ `config.pageindex.enabled` 条件下に、(c) `pageindex_service=None` を `RagService` 引数として渡せる形に再構成 |
| `src/stock_analyze_system/services/rag_service.py` | **Modify** (C3) | (a) `PageIndexDisabledError` を module-level に追加、(b) `__init__` で `pageindex_service: PageIndexService \| None` を許容、(c) `build_index` / `ask_question` / `get_index_status` を `_pageindex is None` でガード、(d) `pageindex_available: bool` property を追加 (web route が rate limit より前に 503 判定するため) |
| `src/stock_analyze_system/services/analysis_worker.py` | **Modify** (C3 / C4) | C3: `rag is None` ガードを削除 (常時構築前提に)。C4: module-level `ERROR_DETAILS_KEYS: frozenset[str] = frozenset({"extraction_error", "failed_types"})` を追加 |
| `src/stock_analyze_system/cli/rag.py` | **Modify** (C3) | `handle()` dispatch 全体を `try / except PageIndexDisabledError` でラップ。ask / index / status は明示 exit 1 (Web 側の 503 と等価)、analyze は ADR amendment §B 通り disabled でも動作。defense-in-depth で `services.rag_service is None` の旧 guard も残す |
| `docs/analysis-jobs-runbook.md` | **Modify** (C4) | (A4) llama-server 起動コマンドを `--ctx-size 131072 --parallel 1 --jinja --n-gpu-layers 99` に更新、`--parallel` と slot ctx の関係を 1 行で説明。(A15) §2.1 `error_details` 表を `extraction_error` / `failed_types` / legacy `index_build_error` の 3 系統に分離し直す |
| `tests/unit/web/test_api.py` | **Modify** (C2 + C3) | C2: `rag_filing_options` が `annual_report` を annual_options からも default からも返さない test を追加 (EDINET annual_report が `converted.pdf` 持ち + SEC 10-Q が古い fixture で default が SEC 側を選ぶこと)。C3: `test_ask_returns_503_when_rag_disabled` / `test_index_rag_disabled_does_not_consume_rate_limit` は維持 (`_get_pageindex_rag_service` 経由で 503)、`test_analyze_returns_503_when_rag_disabled` / `test_analyses_returns_empty_when_rag_disabled` は **削除** し新仕様 test (`test_analyze_streams_when_pageindex_disabled` / `test_analyses_returns_persisted_results_when_pageindex_disabled`) に置換 (ADR amendment §B の「定型分析は pageindex.enabled から独立」を表現)。既存 PageIndex 経路 test 9 件 (TestRagApi 7 件 + TestRagFilingId 2 件) の `monkeypatch.setattr(..., "_get_rag_service", ...)` を `_get_pageindex_rag_service` に切り替え (Step 3.8e の table 参照、rag_analyze 系 4 件は据え置き) |
| `tests/unit/web/test_analysis_jobs.py` | **Modify** (C2) | `create_job` が `annual_report` / 非 SEC を 422 で拒否し、`6-K` を 201 で受理する test を追加 |
| `tests/unit/services/test_rag_service.py` | **Modify** (C3) | (a) `pageindex_service=None` で `run_full_analysis_stream` が完走する test を追加、(b) `ask_question` / `build_index` / `get_index_status` が `PageIndexDisabledError` を投げる test を追加 |
| `tests/unit/services/test_analysis_worker.py` | **Modify** (C3 / C4) | C3: 既存 `test_run_one_job_rag_disabled` を削除 (rag_service=None は到達しなくなる設計)。C4: `ERROR_DETAILS_KEYS` と runbook の key 名が同期している static check を 1 件追加 |
| `tests/unit/cli/test_helpers.py` | **Modify** (C3) | `setup_services` が `pageindex.enabled=False` でも `container.rag_service is not None` を返す test を追加 |
| `tests/unit/cli/test_rag_cli.py` | **Modify** (C3) | CLI `rag` の disabled 経路 test 4 件追加: `rag ask` / `rag index` / `rag status` が `PageIndexDisabledError` で exit 1、`rag analyze` は disabled でも動作 (ADR amendment §B) |
| `tests/unit/characterization/test_container_assembly.py` | **Modify** (C3) | `test_rag_service_none_when_pageindex_disabled` を `test_rag_service_constructed_when_pageindex_disabled` にリネームし、`assert rag_service is None` を `is not None` + `pageindex_available is False` に書き換え (ADR amendment §B 新契約) |
| `tests/integration/test_service_assembly.py` | **Modify** (C3) | `TestRagAssembly::test_non_rag_features_work_when_rag_disabled` をリネーム + 新契約 (`rag_service is not None` + `pageindex_available is False`) に書き換え |

`config/settings.yaml.example` は変更不要 (既に `pageindex.enabled: false`)。`config/settings.yaml` ユーザ設定にも触らない (ADR amendment で「false でも定型分析が動く」と明文化するだけ)。

---

## Tasks

### Task 1: ADR-004 amendment を末尾に追加 (C1)

**Files:**
- Modify: `docs/adr/004-sec-filing-section-extractor.md`

C1 を先頭 commit に置く理由: ADR amendment が C2 / C3 の仕様根拠なので、レビュー時に「なぜこの修正が正しいか」を ADR で先に提示できる。

- [ ] **Step 1.1: 現在の ADR-004 末尾位置を確認**

Run:
```bash
wc -l docs/adr/004-sec-filing-section-extractor.md
tail -10 docs/adr/004-sec-filing-section-extractor.md
```

Expected: 最終行が `### Known limitations explicitly left out of scope` 配下の `Step 3 reasoning_content runaway:` 段落 (line 128 付近、`overflow that slot and produce ...` で終わる)。Amendment はそのさらに下に追加する。

- [ ] **Step 1.2: Amendment セクションを末尾に追記**

`Edit` ツールで ADR-004 の最終行 (`overflow that slot and produce \`BadRequestError\` instead of useful output.`) の直後に、空行 1 行を挟んで以下のブロックを追加:

```markdown

### Amendment 2026-05-17 — Scope clarification and PageIndex independence

ADR-004 適用後の運用で 2 点の暗黙仕様が混乱を招いていたため、明文化する。

#### A. 対象 filing は SEC のみ

`FilingType` enum (`10-K` / `10-Q` / `20-F` / `6-K` / `annual_report` / `quarterly_report`) のうち、本 ADR の `FilingSectionExtractor` は **SEC source の HTML 入力 4 種 (`10-K` / `10-Q` / `20-F` / `6-K`) のみ** を扱う。EDINET の `annual_report` / `quarterly_report` は `converted.pdf` のみ保存され `_SECTION_KEY_MAP` のいずれにも該当しないため、UI / API の分析候補からも除外する。EDINET PDF への対応は別 ADR で扱う。

- `web/routes/api.py` の `ANALYSIS_FILING_TYPES` から `FilingType.ANNUAL_REPORT` を削除し、`FilingType.SIX_K` を追加する
- `POST /api/analysis-jobs` は filing が `source == "SEC"` かつ ADR-004 サポート 4 種であることを 422 で validate する

#### B. 定型分析は `pageindex.enabled` から独立

定型分析の章抽出は LLM 非依存・PageIndex 非依存。`pageindex.enabled` の意味を以下に再定義:

| 機能 | `pageindex.enabled=true` | `pageindex.enabled=false` |
|---|---|---|
| 定型分析 (`run_full_analysis` / `run_full_analysis_stream` / `run_analysis`) | 動く | **動く (本 amendment による)** |
| `preflight` (step-3 LLM probe) | 動く | 動く (LlmClient 直叩き、PageIndex 非依存) |
| `ask_question` (自由質問) | 動く | `PageIndexDisabledError` を返す |
| `build_index` / `get_index_status` | 動く | `PageIndexDisabledError` を返す |

- `RagService` は `setup_services` で常に構築される。シグネチャは `pageindex_service: PageIndexService | None`
- worker の `rag_service is None` ガードは削除する (常時構築前提のため、失敗状態として捕捉する意味がない)
- `ClientBundle.llm` も常に構築する。`PdfConverter` は `ask_question` 経路でのみ必要なので引き続き条件付き
```

`Edit` の `old_string` は ADR-004 の最終 1 行を含めれば一意に決まる (Known limitations セクション末尾の `produce \`BadRequestError\` instead of useful output.`)。実装前に該当行を Read で確認し、句読点まで完全一致させること。

- [ ] **Step 1.3: 文法 / リンク確認**

Run:
```bash
git diff docs/adr/004-sec-filing-section-extractor.md | head -80
```

Expected: 末尾に Amendment ブロックが追加されただけ。既存セクション (Situation / Complication / Question / Answer / Status / Known limitations) は無変更。

- [ ] **Step 1.4: commit (C1)**

```bash
git add docs/adr/004-sec-filing-section-extractor.md
git commit -m "$(cat <<'EOF'
docs(adr): amend ADR-004 to scope filings to SEC and decouple from pageindex.enabled

ADR-004 適用後の運用で見つかった 2 点の暗黙仕様を明文化する:

A. FilingSectionExtractor の対象は SEC source の HTML 4 種 (10-K / 10-Q /
   20-F / 6-K) に固定。EDINET annual_report は別 ADR の範囲。
B. 定型分析は pageindex.enabled から独立。RagService は常に構築し、
   PageIndex 経路 (ask_question / build_index / get_index_status) のみ
   PageIndexDisabledError でガードする。

実装の追従は本 PR の C2 (API/UI 候補制限) / C3 (DI 再構成) / C4 (runbook
更新) で行う。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: A2 — analysis 候補を SEC 4 filing type に制限 (C2)

**Files:**
- Modify: `src/stock_analyze_system/web/routes/api.py`
- Modify: `src/stock_analyze_system/web/routes/analysis_jobs.py`
- Modify: `tests/unit/web/test_api.py`
- Modify: `tests/unit/web/test_analysis_jobs.py`

ADR amendment §A の実装。`Filing.source` 列は既存 (`src/stock_analyze_system/models/filing.py:13` で `source: Mapped[str] = mapped_column(String(10))`、未確定事項 1 を解決済み)。

**Scope clarification (Round 6 Finding 2)**: ADR amendment §A の SEC 4 種制限は **`POST /api/analysis-jobs` (推奨経路、新規 enqueue の正規入口) と `rag_filing_options` (UI 候補) の 2 経路のみ** で enforce する。以下 2 経路は本 PR で **意図的に validation を入れない** (out of scope、Self-review §6.9 にも記載):

- **deprecated `POST /api/stocks/{id}/rag/analyze`** (`src/stock_analyze_system/web/routes/api.py:241-282`): 既に `@router.post(..., deprecated=True)` で次回リリース削除予定 (line 252)。新規利用は `POST /api/analysis-jobs` への誘導 (logger.warning) が出ている。validation を後付けすると削除予定 route の延命コードが増えるため避ける。`annual_report` / `quarterly_report` を流した場合の挙動 (Round 7 Finding 4 + Round 8 Finding 1 補正): 本 route は **AnalysisJob を作らず**、`run_full_analysis_stream` の NDJSON をそのまま返す (line 267-282)。`failed_types` は worker 側 (`analysis_worker.py`) の集約概念であって stream には現れない。実際の per-type 挙動は `_process_one` (`src/stock_analyze_system/services/rag_service.py:368-377`) が章テキストを抽出できなかった analysis_type ごとに `_PerTypeOutcome(kind="error", message="ファイリングから章テキストを抽出できませんでした")` を返し、stream へは analysis_type 単位の **error event** が流れて、最後に `{"event": "complete"}` で締める。DB の `analysis_jobs` テーブルには行を作らない。soft fail でデータ破壊なし、UI から呼ばれた場合は呼び出し元 JS が NDJSON の error / complete event を読んで表示する責務。
- **CLI `stock-analyze rag analyze`** (`src/stock_analyze_system/cli/rag.py:154-188`): operator が手動で叩く debug 経路。CLI 利用者は filing_type を明示指定するので誤用の余地が低い。誤用時は `_handle_analyze` (line 154-188) が `rag.run_full_analysis(filing)` を直接呼び、stdout に空結果 (`AnalysisResult` の `result_json` が `{"raw_answer": ""}` 等の placeholder) を 4 種印字 + 警告ログ。job 経由ではないため `analysis_jobs` テーブルへの記録なし。

両経路を真に塞ぐ案 (extractor 側で `source != "SEC"` を判定して `ExtractionInputMissingError` を投げる、または `_resolve_filing` 後段で `_is_adr004_target` を共通呼び出しする) は **PR3 の A5 (`ExtractionInputMissingError` 導入) と同一ファイル touch のため、PR3 に寄せる** 方が衝突なく扱える (spec §3 マージ順表で PR3 が `rag_service.py` / `filing_section_extractor.py` を modify する想定なので、PR3 で `_is_adr004_target` 相当の判定を extractor 入口に置けば全経路を 1 箇所で塞げる)。本 PR では soft fail を許容する。

- [ ] **Step 2.1: 失敗テストを test_analysis_jobs.py に追加**

`tests/unit/web/test_analysis_jobs.py` の `class TestCreateJob` 内 (`test_create_rejects_unknown_filing` の直後あたり) に以下 3 件を追加:

```python
def test_create_rejects_annual_report_filing(
    self, seeded_filing, db_writer,
):
    """ADR-004 amendment §A: EDINET annual_report は extractor 非対応のため
    422 で拒否する (UI から enqueue されないように API 境界で守る)."""
    from stock_analyze_system.models.company import Company
    from stock_analyze_system.models.filing import Filing

    import asyncio
    asyncio.get_event_loop().run_until_complete(db_writer(
        Company(
            id="JP_7203", ticker="7203", name="Toyota Motor",
            market="TSE", accounting_standard="IFRS",
        ),
        Filing(
            id=999,
            company_id="JP_7203",
            source="EDINET",
            filing_type="annual_report",
            period_type="annual", fiscal_year=2024,
            doc_id="S100ABCD",
        ),
    ))

    client = seeded_filing["client"]
    resp = client.post(
        "/api/analysis-jobs",
        json={"company_id": "JP_7203", "filing_id": 999},
    )
    assert resp.status_code == 422, resp.text
    assert "ADR-004" in resp.json()["detail"] or "annual_report" in resp.json()["detail"]


def test_create_rejects_non_sec_source(self, seeded_filing, db_writer):
    """`source != 'SEC'` の filing は 422. defense-in-depth として
    filing_type が SEC と被っていても (将来的に EDINET 側で 10-K 風 type を
    入れたケース等) 拒否する."""
    from stock_analyze_system.models.company import Company
    from stock_analyze_system.models.filing import Filing

    import asyncio
    asyncio.get_event_loop().run_until_complete(db_writer(
        Company(
            id="JP_OTHER", ticker="9999", name="Other",
            market="TSE", accounting_standard="IFRS",
        ),
        Filing(
            id=998,
            company_id="JP_OTHER",
            source="EDINET",
            filing_type="10-K",  # type は被るが source が SEC でない
            period_type="annual", fiscal_year=2024,
            doc_id="S100ABCE",
        ),
    ))

    client = seeded_filing["client"]
    resp = client.post(
        "/api/analysis-jobs",
        json={"company_id": "JP_OTHER", "filing_id": 998},
    )
    assert resp.status_code == 422, resp.text


def test_create_accepts_six_k_filing(self, seeded_filing, db_writer):
    """ADR-004 amendment §A: 6-K は `_FULL_TEXT_FALLBACK` で best-effort
    扱いだが UI / API 候補には含める."""
    from stock_analyze_system.models.filing import Filing

    import asyncio
    asyncio.get_event_loop().run_until_complete(db_writer(
        Filing(
            id=997,
            company_id="US_AAPL",
            source="SEC",
            filing_type="6-K",
            period_type="other", fiscal_year=2024,
            accession_no="0000320193-24-006K01",
        ),
    ))

    client = seeded_filing["client"]
    resp = client.post(
        "/api/analysis-jobs",
        json={"company_id": "US_AAPL", "filing_id": 997},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["filing_id"] == 997
```

実装上の注意: `seeded_filing` fixture が既に `id=1` の SEC 10-K を作るため、新規 filing は id 衝突しない番号 (997-999) を使う。`db_writer` の使い方は同ファイル冒頭の fixture と一致させる (async fixture 直接呼び出しの代替として `asyncio.get_event_loop().run_until_complete` を使うか、`async def` 化する。同ファイル既存 test の `TestDismissJob.test_dismiss_marks_dismissed_at` が `async def` パターンなのでそちらを踏襲)。

- [ ] **Step 2.2: 失敗テストを test_api.py に追加**

`tests/unit/web/test_api.py` の `class TestFilingOptionsDefault` 内 (`test_options_include_quarterly_filings` の隣) に 2 件追加:

```python
async def test_options_exclude_annual_report_and_non_sec(
    self, auth_client, db_writer,
):
    """ADR-004 amendment §A: rag_filing_options は SEC source の
    10-K / 10-Q / 20-F / 6-K だけを annual_options に返す."""
    from datetime import date
    from stock_analyze_system.models.company import Company
    from stock_analyze_system.models.filing import Filing

    await db_writer(
        Company(
            id="US_AAPL", ticker="AAPL", name="Apple",
            market="NASDAQ", accounting_standard="US-GAAP",
        ),
        # SEC 4 種 — すべて annual_options に出るべき
        Filing(id=11, company_id="US_AAPL", source="SEC",
               filing_type="10-K", period_type="annual",
               fiscal_year=2023, accession_no="A-K",
               period_end=date(2023, 9, 30)),
        Filing(id=12, company_id="US_AAPL", source="SEC",
               filing_type="10-Q", period_type="quarterly",
               fiscal_year=2024, accession_no="A-Q",
               period_end=date(2024, 6, 30)),
        Filing(id=13, company_id="US_AAPL", source="SEC",
               filing_type="20-F", period_type="annual",
               fiscal_year=2023, accession_no="A-F",
               period_end=date(2023, 12, 31)),
        Filing(id=14, company_id="US_AAPL", source="SEC",
               filing_type="6-K", period_type="other",
               fiscal_year=2024, accession_no="A-6K",
               period_end=date(2024, 3, 31)),
        # 除外されるべき 2 件
        Filing(id=15, company_id="US_AAPL", source="EDINET",
               filing_type="annual_report", period_type="annual",
               fiscal_year=2024, doc_id="S100ABCD",
               period_end=date(2024, 3, 31)),
        Filing(id=16, company_id="US_AAPL", source="EDINET",
               filing_type="10-K",  # type 偶発被り
               period_type="annual", fiscal_year=2024,
               doc_id="S100ABCE", period_end=date(2024, 3, 31)),
    )

    resp = auth_client.get("/api/stocks/US_AAPL/rag/filing_options")

    assert resp.status_code == 200
    option_ids = [f["id"] for f in resp.json()["annual_options"]]
    assert set(option_ids) == {11, 12, 13, 14}
    assert 15 not in option_ids and 16 not in option_ids


async def test_options_default_falls_back_to_sec_filing_when_latest_is_edinet(
    self, auth_client, db_writer, tmp_path,
):
    """ADR-004 amendment §A: rag_filing_options.default も SEC 4 種に絞る.

    UI は default を annual_options の先頭に追加するため (web/static/app.js
    の rag タブ初期化)、default が EDINET annual_report のままだと結局
    分析タブから enqueue できてしまい A2 が成立しない. EDINET annual_report
    が period_end / content 的に「最新」でも、default は次に新しい SEC filing
    を選ぶこと.
    """
    from datetime import date
    from stock_analyze_system.models.company import Company
    from stock_analyze_system.models.filing import Filing

    # filing_content_exists() は converted.pdf または raw/*.htm|*.html を見る
    # (services/filing_content.py:24-)。EDINET 側は converted.pdf を作って
    # 「content あり」と扱わせ、現行実装で SEC 側が default に来ない (= 真の
    # default bug) ことを再現する.
    edinet_path = tmp_path / "edinet"
    edinet_path.mkdir(parents=True)
    (edinet_path / "converted.pdf").write_text("pdf bytes")
    sec_path = tmp_path / "sec"
    (sec_path / "raw").mkdir(parents=True)
    (sec_path / "raw" / "filing.htm").write_text("html")

    await db_writer(
        Company(
            id="US_AAPL", ticker="AAPL", name="Apple",
            market="NASDAQ", accounting_standard="US-GAAP",
        ),
        # 最新 + content あり (が EDINET annual_report) — default に出てはダメ
        Filing(id=21, company_id="US_AAPL", source="EDINET",
               filing_type="annual_report", period_type="annual",
               fiscal_year=2025, doc_id="S100LATEST",
               storage_path=str(edinet_path),
               period_end=date(2025, 3, 31)),
        # 古い + content あり (の SEC 10-Q) — default に来るべき
        Filing(id=22, company_id="US_AAPL", source="SEC",
               filing_type="10-Q", period_type="quarterly",
               fiscal_year=2024, accession_no="A-Q",
               storage_path=str(sec_path),
               period_end=date(2024, 6, 30)),
    )

    resp = auth_client.get("/api/stocks/US_AAPL/rag/filing_options")

    assert resp.status_code == 200
    body = resp.json()
    assert body["default"] is not None
    assert body["default"]["id"] == 22, (
        f"default は SEC 4 種から選ばれるべき: actual={body['default']}"
    )
    # annual_options も同様
    option_ids = [f["id"] for f in body["annual_options"]]
    assert 21 not in option_ids
    assert 22 in option_ids
```

- [ ] **Step 2.3: テストを実行して fail を確認**

Run:
```bash
scripts/infisical-run uv run pytest \
  tests/unit/web/test_analysis_jobs.py::TestCreateJob::test_create_rejects_annual_report_filing \
  tests/unit/web/test_analysis_jobs.py::TestCreateJob::test_create_rejects_non_sec_source \
  tests/unit/web/test_analysis_jobs.py::TestCreateJob::test_create_accepts_six_k_filing \
  tests/unit/web/test_api.py::TestFilingOptionsDefault::test_options_exclude_annual_report_and_non_sec \
  tests/unit/web/test_api.py::TestFilingOptionsDefault::test_options_default_falls_back_to_sec_filing_when_latest_is_edinet \
  -q
```

Expected: 5 件中少なくとも 4 件 fail。
- `test_create_rejects_annual_report_filing` / `test_create_rejects_non_sec_source`: 現状 validation 無しで 201 を返すため fail
- `test_options_exclude_annual_report_and_non_sec`: `annual_options` に `id=15` / `id=16` が混入して fail
- `test_options_default_falls_back_to_sec_filing_when_latest_is_edinet`: `default.id == 21` (EDINET annual_report) になって fail (`get_latest_indexed` は DocumentIndex が無いので None、`list_by_recency` が period_end 順で id=21 を選ぶ)
- `test_create_accepts_six_k_filing`: ADR-004 適用前は `create_job` に filing_type validation が無いため 201 で受理され **pass する可能性がある**。validation 追加後も 201 を維持できることの回帰確認用

- [ ] **Step 2.4: `api.py` の `ANALYSIS_FILING_TYPES` を SEC 4 種に置換**

`src/stock_analyze_system/web/routes/api.py` line 23-31 を以下に書き換える:

```python
# ADR-004 amendment 2026-05-17 §A:
# FilingSectionExtractor が対応するのは SEC source の HTML 4 種のみ。
# annual_report (EDINET PDF) を分析候補から外す。
ANNUAL_FILING_TYPES = [
    FilingType.TEN_K,
    FilingType.TWENTY_F,
    FilingType.ANNUAL_REPORT,
]
ANALYSIS_FILING_TYPES = [
    FilingType.TEN_K,
    FilingType.TWENTY_F,
    FilingType.TEN_Q,
    FilingType.SIX_K,
]
```

`ANNUAL_FILING_TYPES` は `annual_report` を残したまま (この名前の constant は別文脈 — 年次決算判定 — で使われる可能性があるため、本 PR では `ANALYSIS_FILING_TYPES` だけを SEC 4 種に絞る)。実装前に `git grep ANNUAL_FILING_TYPES src/` で他の caller がいないことを確認すること。caller が他にあれば、その挙動を変えないよう注意。

- [ ] **Step 2.5: `_is_adr004_target` helper を導入し、`rag_filing_options` の default / annual_options 両経路を SEC 4 種に絞る**

(a) `api.py` の module-level (`ANALYSIS_FILING_TYPES` 定義の直後) に helper を追加:

```python
# ADR-004 amendment §A: FilingSectionExtractor の対象は SEC 4 種のみ.
# rag_filing_options の default / annual_options 両経路でこの helper を使う.
_ADR004_TARGET_FILING_TYPES: frozenset[str] = frozenset(
    str(t) for t in ANALYSIS_FILING_TYPES
)


def _is_adr004_target(filing) -> bool:
    return (
        filing is not None
        and filing.source == "SEC"
        and filing.filing_type in _ADR004_TARGET_FILING_TYPES
    )
```

(b) **C2 commit 用の `rag_filing_options` 書き換え** (`pageindex_available` property はまだ存在しないため、既存の `services.rag_service is not None` 表記をそのまま使う):

```python
@router.get("/{company_id}/rag/filing_options")
async def rag_filing_options(
    company_id: str,
    years: int = 10,
    services: ServiceContainer = Depends(get_services),
):
    """RAG タブの定型分析切り替え用 filing リスト.

    ADR-004 amendment §A: `default` / `annual_options` ともに SEC source の
    10-K / 10-Q / 20-F / 6-K のみを返す. EDINET annual_report は extractor
    非対応のため最新であっても出さない.

    - `default`: ADR-004 対象のうち、インデックス済み → 本体取得済み → 最新 の優先順
    - `annual_options`: 過去 `years` 年分の ADR-004 対象を新しい順
    """
    since_year = date.today().year - years
    analysis_filings = await services.filing_service.list_by_types(
        company_id,
        [str(t) for t in ANALYSIS_FILING_TYPES],
        since_year=since_year,
    )
    # defense-in-depth: list_by_types は filing_type だけで filter するため
    # source != "SEC" の偶発被りを再フィルタする.
    analysis_filings = [f for f in analysis_filings if _is_adr004_target(f)]

    default_filing = None
    if services.rag_service is not None:
        candidate = await services.filing_service.get_latest_indexed(company_id)
        if _is_adr004_target(candidate):
            default_filing = candidate
    if default_filing is None:
        for filing in await services.filing_service.list_by_recency(company_id):
            if _is_adr004_target(filing) and filing_content_exists(filing.storage_path):
                default_filing = filing
                break
    fallback_used = False
    if default_filing is None:
        # ADR-004 対象の中だけで「最新の何か」を探す: list_by_recency を再利用し
        # content の有無を問わず最初の対象 filing を返す.
        for filing in await services.filing_service.list_by_recency(company_id):
            if _is_adr004_target(filing):
                default_filing = filing
                fallback_used = True
                break
    return {
        "default": (
            _filing_to_option(default_filing, fallback=fallback_used) if default_filing else None
        ),
        "annual_options": [_filing_to_option(f) for f in analysis_filings],
    }
```

注意点:
- 既存の `get_latest_any_type` 呼び出しは削除する (型を問わず最新を返すため、ADR-004 amendment §A と相容れない)。代わりに `list_by_recency` を再利用し、`_is_adr004_target` で最初の hit を取る。これは O(N) だが N は通常 1 桁なのでパフォーマンス的に問題なし
- `services.rag_service is not None` 条件は C3 commit (Step 3.8c) で `services.rag_service is not None and services.rag_service.pageindex_available` に置き換える。本 step ではまだ `pageindex_available` property を導入していないため、`is not None` のまま commit して既存 `test_default_prefers_indexed_filing` を壊さない

事前確認:

```bash
git grep -n 'get_latest_any_type' -- src/ tests/
```

他に caller が居る場合は本 PR では削除せず、`rag_filing_options` 側だけ呼ばない形に留める。

- [ ] **Step 2.6: `analysis_jobs.py` の `create_job` に validation を追加**

`src/stock_analyze_system/web/routes/analysis_jobs.py` を編集:

```python
# 既存 import に追加
from stock_analyze_system.models.enums import FilingType

# module-level に追加 (ファイル上部、_job_to_dict の直前)
ADR004_SUPPORTED_FILING_TYPES = frozenset({
    FilingType.TEN_K,
    FilingType.TEN_Q,
    FilingType.TWENTY_F,
    FilingType.SIX_K,
})

# create_job 内、existing ownership check の直後に追加:
@router.post("")
async def create_job(
    request: Request,
    body: CreateJobRequest,
    response: Response,
    queue: AnalysisQueueService = Depends(_get_queue),
    services: ServiceContainer = Depends(get_services),
):
    # filing が company_id に属することを境界で検証 (旧API同等)。
    filing = await services.filing_service.get_filing_by_id(body.filing_id)
    if filing is None or filing.company_id != body.company_id:
        raise HTTPException(
            status_code=404,
            detail=f"filing_id={body.filing_id} not found for {body.company_id}",
        )

    # ADR-004 amendment §A: FilingSectionExtractor の対象は SEC 4 種のみ.
    if (
        filing.source != "SEC"
        or filing.filing_type not in ADR004_SUPPORTED_FILING_TYPES
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"filing_type={filing.filing_type} (source={filing.source}) "
                "is not supported by ADR-004 extractor"
            ),
        )

    # 既存 pending/running は重複として早期返却。重い rate limit は
    # 新規作成時のみ消費する (再試行・複数タブの cheap な POST を 429 で
    # 拒否しないため)。
    ...
```

注意: `filing.filing_type` は DB から `String(10)` で来る (`models/filing.py:14`) ため、`FilingType` enum との比較は `StrEnum` (`models/enums.py:12`) のおかげで等価 (`"10-K" == FilingType.TEN_K` が True)。`frozenset` メンバシップも問題なく動く。

- [ ] **Step 2.7: テストを実行して pass を確認**

Run:
```bash
scripts/infisical-run uv run pytest \
  tests/unit/web/test_analysis_jobs.py::TestCreateJob \
  tests/unit/web/test_api.py::TestFilingOptionsDefault \
  -q
```

Expected: `TestCreateJob` 全件 + `TestFilingOptionsDefault` 全件 pass。

- [ ] **Step 2.8: 回帰確認**

Run:
```bash
scripts/infisical-run uv run pytest \
  tests/unit/web/test_analysis_jobs.py \
  tests/unit/web/test_api.py \
  -q
```

Expected: 既存 test 全件 + 新規 4 件が pass。

- [ ] **Step 2.9: commit (C2)**

```bash
git add src/stock_analyze_system/web/routes/api.py \
        src/stock_analyze_system/web/routes/analysis_jobs.py \
        tests/unit/web/test_api.py \
        tests/unit/web/test_analysis_jobs.py
git commit -m "$(cat <<'EOF'
fix(api): restrict analysis candidates to SEC filings (A2)

ADR-004 amendment §A に従い、FilingSectionExtractor が対応する SEC 4 種
(10-K / 10-Q / 20-F / 6-K) 以外を分析候補から除外する:

- `ANALYSIS_FILING_TYPES` から `annual_report` を外し、`6-K` を追加
- `_is_adr004_target(filing)` helper を導入し、`rag_filing_options` の
  annual_options と default の両経路で SEC 4 種だけを返すように filter
  (UI は default を annual_options の先頭に追加するため、default も
  filter しないと EDINET annual_report が分析タブに出てしまう)
- `get_latest_any_type` 呼び出しを廃し、`list_by_recency` を再利用して
  ADR-004 対象の最初の hit を default にする
- `POST /api/analysis-jobs` で非 SEC source または非サポート filing_type を
  422 で拒否

C3 で導入する `pageindex_available` への切り替えは C3 commit に持ち越し
(本 commit では `services.rag_service is not None` 表記のまま)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: A3 — `RagService` を `pageindex.enabled` から独立させる (C3)

**Files:**
- Modify: `src/stock_analyze_system/shared/clients.py`
- Modify: `src/stock_analyze_system/cli/container.py`
- Modify: `src/stock_analyze_system/services/rag_service.py`
- Modify: `src/stock_analyze_system/services/analysis_worker.py`
- Modify: `src/stock_analyze_system/web/routes/api.py`
- Modify: `tests/unit/services/test_rag_service.py`
- Modify: `tests/unit/services/test_analysis_worker.py`
- Modify: `tests/unit/cli/test_helpers.py`
- Modify: `tests/unit/web/test_api.py`

ADR amendment §B の実装。RagService を常に構築し、PageIndex 経路 (ask_question / build_index / get_index_status) だけを `PageIndexDisabledError` でガードする。

- [ ] **Step 3.1: 失敗テストを test_rag_service.py に追加**

`tests/unit/services/test_rag_service.py` の末尾 (またはクラス境界の隣) に以下を追加:

```python
class TestPageIndexIndependence:
    """ADR-004 amendment §B: pageindex_service=None でも定型分析は動く。
    PageIndex 経路は明示的なエラーで disabled を伝える."""

    @pytest.fixture
    def service_no_pageindex(
        self,
        analysis_repo,
        llm_client,
        filing_content_service,
        section_extractor_default,
    ):
        return RagService(
            pageindex_service=None,
            analysis_repo=analysis_repo,
            llm_client=llm_client,
            qa_history_repo=None,
            filing_content_service=filing_content_service,
            section_extractor=section_extractor_default,
        )

    async def test_run_full_analysis_works_without_pageindex(
        self, service_no_pageindex,
    ):
        # pageindex_available property は Step 3.4 で追加. 実装前は AttributeError
        # で fail し、test が red になることを保証する (定型分析自体は _pageindex を
        # 触らないので、property assertion 無しだと現行実装で偶発 pass する).
        assert service_no_pageindex.pageindex_available is False

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/auto/fetched"
        filing.filing_type = "10-K"

        results = await service_no_pageindex.run_full_analysis(filing)
        # extractor は 4 種すべて返す fixture なので 4 件返る
        assert len(results) == 4
        types = {r.analysis_type for r in results}
        assert types == {"business_summary", "risk_factors", "mda", "competitors"}

    async def test_run_full_analysis_stream_works_without_pageindex(
        self, service_no_pageindex,
    ):
        assert service_no_pageindex.pageindex_available is False

        filing = MagicMock()
        filing.id = 1
        filing.company_id = "US_AAPL"
        filing.storage_path = "/data/auto/fetched"
        filing.filing_type = "10-K"

        events = [e async for e in service_no_pageindex.run_full_analysis_stream(filing)]
        # 最後が complete、途中に extracting / started / phase / done が出る
        assert events[-1] == {"event": "complete"}
        assert any(e.get("event") == "extracting" for e in events)
        assert any(e.get("event") == "done" for e in events)

    async def test_ask_question_raises_when_pageindex_disabled(
        self, service_no_pageindex,
    ):
        from stock_analyze_system.services.rag_service import PageIndexDisabledError
        filing = MagicMock()
        filing.storage_path = "/data/auto/fetched"
        with pytest.raises(PageIndexDisabledError):
            await service_no_pageindex.ask_question(filing, "What is the revenue?")

    async def test_build_index_raises_when_pageindex_disabled(
        self, service_no_pageindex,
    ):
        from stock_analyze_system.services.rag_service import PageIndexDisabledError
        filing = MagicMock()
        filing.storage_path = "/data/auto/fetched"
        with pytest.raises(PageIndexDisabledError):
            await service_no_pageindex.build_index(filing)

    async def test_get_index_status_raises_when_pageindex_disabled(
        self, service_no_pageindex,
    ):
        from stock_analyze_system.services.rag_service import PageIndexDisabledError
        with pytest.raises(PageIndexDisabledError):
            await service_no_pageindex.get_index_status("US_AAPL")
```

注意: `service_no_pageindex` fixture は既存 `service` fixture と同じ引数構成だが `pageindex_service=None` を渡す。既存 `service` fixture が `pageindex_service` 引数を必須 positional として受けている形なら、Task 3.4 の `__init__` 変更後に default を渡せるようになる。**現状 (実装変更前)** はこの fixture も `RagService(...)` が `pageindex_service=None` を受け取れずに `AttributeError` で fail することが期待動作。

- [ ] **Step 3.2: 失敗テストを test_helpers.py に追加**

`tests/unit/cli/test_helpers.py` の `class TestSetupServices` 内 (`test_returns_container` の隣) に追加:

```python
async def test_constructs_rag_service_when_pageindex_disabled(self):
    """ADR-004 amendment §B: pageindex.enabled=false でも RagService は
    常に構築される (定型分析が PageIndex 非依存になったため)."""
    from stock_analyze_system.config import AppConfig
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    config = AppConfig()
    config.pageindex.enabled = False  # 明示的に無効
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        container = await setup_services(session, config)
        assert container.rag_service is not None
        # PageIndex 経路だけが disabled になっている
        from stock_analyze_system.services.rag_service import PageIndexDisabledError
        with pytest.raises(PageIndexDisabledError):
            await container.rag_service.get_index_status("US_AAPL")
    await engine.dispose()
```

なお `test_helpers.py` 冒頭に `import pytest` が既にあるか Read で確認し、無ければ追加すること。

- [ ] **Step 3.3: テストを実行して fail を確認**

Run:
```bash
scripts/infisical-run uv run pytest \
  tests/unit/services/test_rag_service.py::TestPageIndexIndependence \
  tests/unit/cli/test_helpers.py::TestSetupServices::test_constructs_rag_service_when_pageindex_disabled \
  -q
```

Expected: 6 件 fail。実装前の現行 `RagService.__init__` は `pageindex_service: PageIndexService` を **型ヒントだけ** で受けるため、`None` を渡しても TypeError にはならず fixture は成立する (Round 5 Finding 2 で指摘の通り、PageIndex 非依存メソッドは現行実装でも偶発 pass し得る)。本 step で確実に fail を取るための内訳:

- `TestPageIndexIndependence` 5 件:
  - `test_run_full_analysis_works_without_pageindex` / `test_run_full_analysis_stream_works_without_pageindex` (2 件): Step 3.1 で先頭に追加した `assert service_no_pageindex.pageindex_available is False` が **`AttributeError: Mock object has no attribute 'pageindex_available'`** または `RagService` instance に `pageindex_available` property が無いことから fail。Step 3.4 (b2) で property を追加すると pass する
  - `test_ask_question_raises_when_pageindex_disabled` / `test_build_index_raises_when_pageindex_disabled` / `test_get_index_status_raises_when_pageindex_disabled` (3 件): 現行実装で `self._pageindex.get_or_create_index(...)` 等を呼ぶため `AttributeError: 'NoneType' object has no attribute 'get_or_create_index'` で fail。test 側は `pytest.raises(PageIndexDisabledError)` を期待するので「期待する例外と違う例外が出た」で fail (`ImportError` の場合は import 時点で fail)
- `test_constructs_rag_service_when_pageindex_disabled` (1 件): `pageindex.enabled=False` で `container.rag_service is None` のため `assert container.rag_service is not None` で fail

`assert pageindex_available is False` の追加 (Step 3.1) によって、定型分析 2 件が「実装側の修正なしでも偶発 pass する」という Round 5 Finding 2 のリスクが消える。

- [ ] **Step 3.4: `rag_service.py` に `PageIndexDisabledError` / `pageindex_available` / `__init__` / 3 メソッドを修正**

`src/stock_analyze_system/services/rag_service.py` で以下を編集:

(a) module-level (RagService クラス定義の直前、既存 `_EMPTY_LLM_REASON` や `_FakeRagService` の例外群の近く) に追加:

```python
class PageIndexDisabledError(RuntimeError):
    """PageIndex 経路 (ask_question / build_index / get_index_status) が
    config.pageindex.enabled=False のため無効化されているときに送出される。

    定型分析 (run_full_analysis / run_full_analysis_stream / run_analysis) は
    PageIndex 非依存なので、これらは pageindex_service=None でも動く."""
```

(b) `__init__` シグネチャを `PageIndexService | None` 許容に変更 (line 110-118):

```python
def __init__(
    self,
    pageindex_service: PageIndexService | None,
    analysis_repo: AnalysisRepository,
    llm_client: LlmClient,
    qa_history_repo: RagQaHistoryRepository | None = None,
    filing_content_service: FilingContentService | None = None,
    section_extractor: FilingSectionExtractor | None = None,
):
    self._pageindex = pageindex_service
    ...
```

(b2) `__init__` の直後に `pageindex_available` property を追加:

```python
@property
def pageindex_available(self) -> bool:
    """PageIndex 経路 (ask_question / build_index / get_index_status / get_qa_history) が
    使えるかどうか. web route が rate limit を消費する前に 503 で
    早期 return するために参照する."""
    return self._pageindex is not None
```

(c) `build_index` (line 130-133) を以下に書き換え:

```python
async def build_index(self, filing) -> dict:
    """インデックスを構築または取得する。PageIndex 無効時は明示エラー."""
    if self._pageindex is None:
        raise PageIndexDisabledError(
            "pageindex.enabled=false; build_index は無効化されています"
        )
    filing = await self._ensure_filing_content(filing)
    return await self._pageindex.get_or_create_index(filing)
```

(d) `ask_question` (line 448-464) の先頭にガードを追加:

```python
async def ask_question(self, filing, question: str) -> QueryResult:
    """自由質問を実行し、結果を Q&A 履歴に永続化する"""
    if self._pageindex is None:
        raise PageIndexDisabledError(
            "pageindex.enabled=false; ask_question は無効化されています"
        )
    logger.info("RAG Q&A for filing %d: %s", filing.id, question[:50])
    ...
```

(e) `get_index_status` (line 503-515) の先頭にガードを追加:

```python
async def get_index_status(self, company_id: str) -> list[dict]:
    """企業のインデックス構築状態を返す"""
    if self._pageindex is None:
        raise PageIndexDisabledError(
            "pageindex.enabled=false; get_index_status は無効化されています"
        )
    indices = await self._pageindex.get_indices_for_company(company_id)
    ...
```

定型分析メソッド (`run_full_analysis` / `run_full_analysis_stream` / `run_analysis` / `preflight` / `_analyze_section` / `_ensure_filing_content` / `_save_analysis` / `_persist`) は PageIndex を一切参照していないため変更なし。

- [ ] **Step 3.5: `shared/clients.py` で `LlmClient` を常に構築**

`src/stock_analyze_system/shared/clients.py` line 35-63 を以下に書き換え:

```python
def build_client_bundle(config: AppConfig) -> ClientBundle:
    """全外部 API クライアントを構築する.

    `LlmClient` は ADR-004 amendment §B により定型分析でも必要なため常に構築する。
    `PdfConverter` は PageIndex (ask_question 経路) でのみ使うため
    `pageindex.enabled` 条件で構築する。"""
    from stock_analyze_system.ingestion.edinet import EdinetClient
    from stock_analyze_system.ingestion.fmp import FmpClient
    from stock_analyze_system.ingestion.sec_edgar import SecEdgarClient
    from stock_analyze_system.ingestion.yahoo_finance import YahooFinanceClient
    from stock_analyze_system.services.llm_client import LlmClient

    bundle = ClientBundle(
        sec=SecEdgarClient(
            email=config.sec_edgar.email,
            rate=config.sec_edgar.rate_limit_rps,
        ),
        edinet=EdinetClient(
            api_key=config.edinet.api_key,
            base_url=config.edinet.base_url,
        ),
        yahoo=YahooFinanceClient(rate=config.yahoo_finance.rate_limit_rps),
        fmp=FmpClient(
            api_key=config.fmp.api_key,
            base_url=config.fmp.base_url,
        ),
        llm=LlmClient(config.llm),
    )
    if config.pageindex.enabled:
        from stock_analyze_system.services.pdf_converter import PdfConverter
        bundle.pdf_converter = PdfConverter()
    return bundle
```

- [ ] **Step 3.6: `cli/container.py` の `setup_services` を再構成**

`src/stock_analyze_system/cli/container.py` line 146-176 を以下に書き換える:

```python
# RAG services (ADR-004 amendment §B: RagService は常に構築する。
# PageIndexService だけが config.pageindex.enabled 条件下。)
from stock_analyze_system.repositories.rag_qa_history import RagQaHistoryRepository
from stock_analyze_system.services.filing_section_extractor import (
    FilingSectionExtractor,
)
from stock_analyze_system.services.llm_client import LlmClient
from stock_analyze_system.services.rag_service import RagService

qa_history_repo = RagQaHistoryRepository(session)
llm_client = llm_client_pre or LlmClient(config.llm)

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

注意: 既存コードでは `llm_client_pre` を `clients.llm` から取得しているが (line 99)、Task 3.5 で `bundle.llm` が常に構築されるようになったため、`pageindex.enabled=false` で `clients` を渡されたケースでも `llm_client_pre` は non-None になる。`llm_client_pre or LlmClient(...)` で両方のケースを統一的に扱える。

- [ ] **Step 3.7: `analysis_worker.py` の `rag is None` ガードを削除**

`src/stock_analyze_system/services/analysis_worker.py` line 186-188 を以下に書き換え:

```python
            rag = container.rag_service
            # ADR-004 amendment §B: rag_service は常に構築されるため None ガードは不要。
            filing = await container.filing_service.get_filing_by_id(
                job.filing_id,
            )
```

つまり `if rag is None: raise RuntimeError(...)` の 2 行を削除する。

- [ ] **Step 3.8: 既存 `test_run_one_job_rag_disabled` を削除**

`tests/unit/services/test_analysis_worker.py` line 506-517 の `test_run_one_job_rag_disabled` 関数を完全に削除する。理由: `rag_service` が `None` になるシナリオが設計上消滅したため、テストの前提が成立しない。

- [ ] **Step 3.8b: web helper を 2 系統に分け、PageIndex 経路だけ 503 にする (Finding 1 対応の中核)**

ADR-004 amendment §B の核は「定型分析は `pageindex.enabled` から独立」。そのため `pageindex_available` で 503 / 空リスト返しを適用するのは PageIndex 経路 (`ask_question` / `build_index` / `get_index_status` / `get_qa_history`) **だけ**。定型分析 (`run_full_analysis_stream` を呼ぶ deprecated `rag_analyze`、保存結果を返す `rag_analyses`) は `pageindex.enabled=false` でも動くようにする。

これは前回案 (`_get_rag_service` を一括で `pageindex_available` 判定に変える) が ADR amendment §B と矛盾していたため、helper を 2 系統に分割する。

(a) `api.py` line 144-150 を以下に置換:

```python
def _get_rag_service(services: ServiceContainer):
    """ADR-004 amendment §B: 定型分析 (rag_analyze) で使う. rag_service は
    常時 non-None だが、defense-in-depth で None ガードを残す
    (将来 setup_services が失敗するケース、monkeypatch で None を入れる test との互換用)."""
    if services.rag_service is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service is not available.",
        )
    return services.rag_service


def _get_pageindex_rag_service(services: ServiceContainer):
    """ADR-004 amendment §B: PageIndex 経路 (ask_question / build_index /
    get_index_status / get_qa_history) で使う. pageindex.enabled=false 時は
    rate limit を消費する前に 503 で early return する."""
    rag = services.rag_service
    if rag is None or not rag.pageindex_available:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PageIndex is disabled. Set pageindex.enabled=true to use ask/index.",
        )
    return rag
```

(b) endpoint 切り替え:

| endpoint | helper | 理由 |
|---|---|---|
| `rag_ask` (line 194) | `_get_pageindex_rag_service` | `ask_question` は PageIndex 経路 (`tree = await self._pageindex.get_or_create_index(...)`) |
| `rag_index` (line 221) | `_get_pageindex_rag_service` | `build_index` が PageIndex 経路 |
| `rag_analyze` (line 241, deprecated) | `_get_rag_service` | `run_full_analysis_stream` は ADR-004 後 PageIndex 非依存 |

`rag_ask` / `rag_index` の `rag = _get_rag_service(services)` を `rag = _get_pageindex_rag_service(services)` に書き換える。`rag_analyze` は既存どおり `_get_rag_service` を呼ぶだけ (helper 動作が「rag_service is None ガードのみ」に縮んだので、disabled でも 503 にならず 200 で stream を返すようになる)。

(c) `rag_analyses` (line 285-311) と `rag_history` (line 352-361) の書き換え:

```python
@router.get("/{company_id}/rag/analyses")
async def rag_analyses(
    company_id: str,
    filing_id: int | None = None,
    filing_type: FilingType = FilingType.TEN_K,
    services: ServiceContainer = Depends(get_services),
):
    """保存済み定型分析を返す.

    ADR-004 amendment §B: 定型分析は PageIndex 非依存のため、
    pageindex.enabled=false でも保存済み結果を返す.
    """
    if services.rag_service is None:
        return []  # defense-in-depth (rag_service 常時 non-None 想定)
    if filing_id is not None:
        filing = await services.filing_service.get_filing_by_id(filing_id)
        if filing is None or filing.company_id != company_id:
            return []
        return await services.rag_service.get_analyses(company_id, filing.id)
    filing = await services.filing_service.get_latest_filing(
        company_id,
        filing_type,
    )
    if filing is None:
        return []
    return await services.rag_service.get_analyses(company_id, filing.id)
```

`rag_analyses` は本質的に変更なし (既存の `services.rag_service is None: return []` だけ残す)。`rag_service` 常時 non-None になった結果、`pageindex.enabled=false` 環境でも `get_analyses` が呼ばれて保存済み結果が返るようになる — これが ADR amendment §B の意図。

```python
@router.get("/{company_id}/rag/history")
async def rag_history(
    company_id: str,
    limit: int = 50,
    services: ServiceContainer = Depends(get_services),
):
    """過去の自由質問 Q&A 履歴を新しい順で返す.

    ADR-004 amendment §B: Q&A 履歴は ask_question (PageIndex 経路) の副産物
    なので、PageIndex 無効時は空リスト. ask_question 自体が 503 で実行不能.
    """
    if services.rag_service is None or not services.rag_service.pageindex_available:
        return []
    return await services.rag_service.get_qa_history(company_id, limit=limit)
```

`rag_history` だけは PageIndex 経路の副産物として空リストを返す (UX 整合性: ask が 503 なら history も「無い」のが自然)。

(d) helper を直接呼ぶ単体 test を 3 件追加 (Round 6 Finding 3 対応):

`tests/unit/web/test_api.py` の `class TestRagApi` の直前 (新規クラス) に以下を追加:

```python
class TestRagHelperSplit:
    """ADR-004 amendment §B + helper 2 系統分割の helper 単体 test.

    monkeypatch で _get_rag_service / _get_pageindex_rag_service 自体を
    差し替えると helper 本体の挙動が検証されないため、helper を直接呼んで
    503 / 通過の境界を固定する."""

    def test_get_rag_service_returns_when_pageindex_disabled(self):
        """_get_rag_service は ADR amendment §B 通り disabled でも 503 投げず
        rag_service を返す (rag_analyze 用)."""
        from stock_analyze_system.web.routes.api import _get_rag_service

        fake_rag = SimpleNamespace(pageindex_available=False)
        services = SimpleNamespace(rag_service=fake_rag)

        result = _get_rag_service(services)
        assert result is fake_rag  # 503 を投げず通過

    def test_get_rag_service_raises_503_when_rag_service_none(self):
        """_get_rag_service の defense-in-depth: rag_service=None なら 503."""
        from fastapi import HTTPException
        from stock_analyze_system.web.routes.api import _get_rag_service

        services = SimpleNamespace(rag_service=None)
        with pytest.raises(HTTPException) as exc_info:
            _get_rag_service(services)
        assert exc_info.value.status_code == 503

    def test_get_pageindex_rag_service_raises_503_when_pageindex_disabled(self):
        """_get_pageindex_rag_service は pageindex_available=False で 503
        (rate limit を消費する前に early return)."""
        from fastapi import HTTPException
        from stock_analyze_system.web.routes.api import _get_pageindex_rag_service

        fake_rag = SimpleNamespace(pageindex_available=False)
        services = SimpleNamespace(rag_service=fake_rag)

        with pytest.raises(HTTPException) as exc_info:
            _get_pageindex_rag_service(services)
        assert exc_info.value.status_code == 503
        assert "PageIndex is disabled" in exc_info.value.detail
```

理由: Step 3.8c で追加する `test_analyze_streams_when_pageindex_disabled` は `monkeypatch.setattr(api_module, "_get_rag_service", lambda services: mock_rag)` で helper 自体を差し替えるため、helper が旧仕様 (`rag_service is None or not pageindex_available` を一括判定) のままでも test は pass する偽 green になる。本 step の 3 件は helper を直接呼んで境界 (503 を投げる条件) を固定し、helper 分割が確実に効くことを保証する。

import について (Round 7 Finding 2 対応):
- `SimpleNamespace` と `pytest` は `tests/unit/web/test_api.py:3,6` で既存 import 済みなのでそのまま使える
- `MagicMock` は test_api.py で **未 import** (line 4 で `from unittest.mock import AsyncMock` のみ)。本 step では `MagicMock` を使わず `SimpleNamespace(pageindex_available=False)` で代替。`pageindex_available` は 1 個の attribute だけなので `SimpleNamespace` で十分かつ依存が増えない
- `HTTPException` は test_api.py 既存 import なし。本 step の関数内で `from fastapi import HTTPException` を都度 import (test 内のローカル import は Step 3.1 fixture と同じ pattern)

実行:

```bash
scripts/infisical-run uv run pytest \
  tests/unit/web/test_api.py::TestRagHelperSplit -q
```

Expected: Step 3.8b (a) (b) (c) の実装変更後、3 件すべて pass。実装前なら `_get_pageindex_rag_service` 未定義で `ImportError`、または `_get_rag_service` が `pageindex_available` を見て 503 を投げる旧案だと `test_get_rag_service_returns_when_pageindex_disabled` が `HTTPException` で fail。

- [ ] **Step 3.8c: 既存 test の仕様変更を反映する (`analyze` / `analyses` の disabled 旧契約を撤廃)**

ADR amendment §B により以下 2 件の test は **旧仕様を表現しており、新仕様と矛盾する** ため削除し、新仕様向け test を追加する:

(a) `tests/unit/web/test_api.py:494` 付近の `test_analyze_returns_503_when_rag_disabled` (`TestRagApi` クラス内) を削除し、新規 test を追加:

```python
def test_analyze_streams_when_pageindex_disabled(
    self, monkeypatch, seeded_filing,
):
    """ADR-004 amendment §B: deprecated rag/analyze は pageindex.enabled=false
    でも動作する (定型分析は PageIndex 非依存)."""
    mock_rag = AsyncMock()
    # pageindex_available=False を simulate (RagService.pageindex_available は
    # property だが MagicMock では値を直接 set してよい)
    mock_rag.pageindex_available = False

    async def fake_stream(filing):
        yield {"event": "started", "total": 1}
        yield {"event": "done", "index": 0, "analysis_type": "business_summary"}
        yield {"event": "complete"}

    mock_rag.run_full_analysis_stream = fake_stream
    from stock_analyze_system.web.routes import api as api_module
    monkeypatch.setattr(
        api_module, "_get_rag_service", lambda services: mock_rag,
    )

    resp = seeded_filing.post(
        "/api/stocks/US_AAPL/rag/analyze",
        params={"filing_type": "10-K"},
    )

    assert resp.status_code == 200, resp.text
    # NDJSON: 3 行 (started / done / complete) が含まれる
    body = resp.content.decode("utf-8")
    assert '"event": "started"' in body
    assert '"event": "complete"' in body
```

(b) `tests/unit/web/test_api.py:387` 付近の `test_analyses_returns_empty_when_rag_disabled` を削除し、新規 test を追加:

```python
async def test_analyses_returns_persisted_results_when_pageindex_disabled(
    self, seeded_aapl_client, db_writer,
):
    """ADR-004 amendment §B: pageindex.enabled=false でも保存済み定型分析を返す.
    rag_analyses は PageIndex 非依存 (_analysis_repo.get_analyses を呼ぶだけ)."""
    from datetime import date
    from stock_analyze_system.models.company_analysis import (
        CompanyAnalysis,
        PIPELINE_EXTRACTOR,
    )
    from stock_analyze_system.models.filing import Filing

    await db_writer(
        Filing(
            id=31, company_id="US_AAPL", source="SEC",
            filing_type="10-K", period_type="annual",
            fiscal_year=2024, accession_no="A-31",
            period_end=date(2024, 9, 30),
        ),
        CompanyAnalysis(
            company_id="US_AAPL",
            filing_id=31,
            analysis_type="business_summary",
            result_json='{"summary": "persisted"}',
            model_name="test-model",
            pipeline=PIPELINE_EXTRACTOR,
        ),
    )

    resp = seeded_aapl_client.get(
        "/api/stocks/US_AAPL/rag/analyses",
        params={"filing_id": 31},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["analysis_type"] == "business_summary"
    assert data[0]["result_json"] == {"summary": "persisted"}
```

`PIPELINE_EXTRACTOR` / `CompanyAnalysis` の正本は `src/stock_analyze_system/models/company_analysis.py` (line 8 / 11)。

これら 2 件の削除・追加は新仕様の中核なので **削除のまま放置すると ADR amendment §B が言葉だけ** になる。PR review でも説明が必要なので、commit message と PR body に「test_analyze_returns_503_when_rag_disabled / test_analyses_returns_empty_when_rag_disabled は ADR amendment §B により旧仕様、新仕様 test に置き換え」と明記する。

- [ ] **Step 3.8d: `rag_filing_options` の default 探索条件を pageindex_available に揃える (Step 2.5 のフォローアップ)**

C2 commit 時点では `if services.rag_service is not None:` で書いた default 探索を、C3 で `pageindex_available` 条件に置き換える。`get_latest_indexed` は DocumentIndex を join した最新を返すクエリだが、`pageindex.enabled=false` で DocumentIndex に rows がある可能性 (legacy データ等) を考えると、「indexed filing を default にする」のは PageIndex が有効なときだけにする方が UX として自然 (disabled なら build/ask ができないので、indexed filing を default にしても意味がない):

```python
# rag_filing_options 内
default_filing = None
if services.rag_service is not None and services.rag_service.pageindex_available:
    candidate = await services.filing_service.get_latest_indexed(company_id)
    if _is_adr004_target(candidate):
        default_filing = candidate
```

C3 commit に含める。

- [ ] **Step 3.8e: 既存 PageIndex 経路 test の monkeypatch 対象を `_get_pageindex_rag_service` に切り替える**

`tests/unit/web/test_api.py` の `_get_rag_service` monkeypatch 箇所を **single-line grep** で正確に列挙する (`monkeypatch.setattr(` が複数行に分かれているケースを取りこぼさないため、引数文字列で grep する):

```bash
git grep -n '"_get_rag_service"' -- tests/unit/web/test_api.py
```

plan 作成時の HEAD (`742eec2`) では 13 箇所がヒット。`rag_ask` / `rag_index` が `_get_pageindex_rag_service` に切り替わると、これらのうち PageIndex 経路 (ask / index) を打つ test では monkeypatch が効かなくなり、`web_config` の `pageindex.enabled=False` の影響で 503 のまま落ちる (特に `rag/index` の rate-limit-free 契約 test は期待 200 が 503 に化ける)。

各 line の所属クラス・所属 endpoint を URL (`/rag/ask` / `/rag/index` / `/rag/analyze`) で分類した結果:

| line | class | URL の endpoint | 新 monkeypatch 対象 |
|---|---|---|---|
| 281 | `TestRagApi` | rag/ask | `_get_pageindex_rag_service` |
| 308 | `TestRagApi` | rag/ask | `_get_pageindex_rag_service` |
| 327 | `TestRagApi` | rag/ask | `_get_pageindex_rag_service` |
| 370 | `TestRagApi` | rag/ask | `_get_pageindex_rag_service` |
| 402 | `TestRagApi` | rag/index | `_get_pageindex_rag_service` |
| 419 | `TestRagApi` | rag/index | `_get_pageindex_rag_service` |
| 441 | `TestRagApi` | rag/index | `_get_pageindex_rag_service` |
| 475 | `TestRagApi` | rag/analyze | **据え置き** `_get_rag_service` |
| 512 | `TestRagApi` | rag/analyze | **据え置き** `_get_rag_service` |
| 561 | `TestRagFilingId` | rag/analyze | **据え置き** `_get_rag_service` |
| 592 | `TestRagFilingId` | rag/analyze | **据え置き** `_get_rag_service` |
| 627 | `TestRagFilingId` | rag/ask | `_get_pageindex_rag_service` |
| 656 | `TestRagFilingId` | rag/index | `_get_pageindex_rag_service` |

合計 13 箇所のうち:
- **切り替え 9 件**: ask 5 件 (281 / 308 / 327 / 370 / 627) + index 4 件 (402 / 419 / 441 / 656)
- **据え置き 4 件**: analyze 4 件 (475 / 512 / 561 / 592)

Step 3.8c で新規追加する `test_analyze_streams_when_pageindex_disabled` も `_get_rag_service` を monkeypatch するため、本 step 完了時の総計は **14 箇所 (切り替え 9 / 据え置き 5)** になる。

行番号は plan 作成時 HEAD (`742eec2`) のもの。実装時には上記 grep コマンドで再確認し、各 line の上下数行を読んで URL の path (`/rag/ask` / `/rag/index` / `/rag/analyze`) を直接確認する。

判定ルール:
- URL が `/rag/ask` を含む → `_get_pageindex_rag_service`
- URL が `/rag/index` を含む → `_get_pageindex_rag_service`
- URL が `/rag/analyze` を含む → `_get_rag_service` のまま (rag_analyze は定型分析、ADR amendment §B により disabled でも動く)

書き換えは `_get_rag_service` → `_get_pageindex_rag_service` の 1 行差分のみ:

```python
# Before
monkeypatch.setattr(
    api_module, "_get_rag_service", lambda services: mock_rag,
)

# After (rag_ask / rag_index 系のみ)
monkeypatch.setattr(
    api_module, "_get_pageindex_rag_service", lambda services: mock_rag,
)
```

- [ ] **Step 3.8f: 切り替えた既存 test 9 件 + PageIndex 503 test 2 件 + 新仕様 2 件が pass することを確認**

`test_ask_returns_503_when_rag_disabled` (test_api.py:293, `TestRagApi` クラス内) と `test_index_rag_disabled_does_not_consume_rate_limit` (test_api.py:427, 同) は **削除せず維持** (Step 3.8e で monkeypatch 対象を切り替え済み)。`TestRagFilingId::test_ask_uses_filing_id_when_provided` (line 627) と `TestRagFilingId::test_index_uses_filing_id_when_provided` (line 656) も Step 3.8e で切り替えた 9 件に含まれるため、本 step で **`TestRagApi` だけでなく `TestRagFilingId` も含めて** 走らせる:

```bash
scripts/infisical-run uv run pytest \
  tests/unit/web/test_api.py::TestRagApi \
  tests/unit/web/test_api.py::TestRagFilingId \
  -q
```

Expected: 両クラス全件 pass。重点項目:
- `TestRagApi::test_ask_returns_503_when_rag_disabled` / `TestRagApi::test_index_rag_disabled_does_not_consume_rate_limit`: `_get_pageindex_rag_service` 経由で 503 / rate-limit-free 契約維持
- `TestRagApi::test_ask_*` / `TestRagApi::test_index_*` の monkeypatch あり test 7 件 (281 / 308 / 327 / 370 / 402 / 419 / 441): 新 monkeypatch 対象で mock_rag が注入され 200 / 404 / 429 が正しく出る
- `TestRagFilingId::test_ask_uses_filing_id_when_provided` (627) / `TestRagFilingId::test_index_uses_filing_id_when_provided` (656): 上記と同じく `_get_pageindex_rag_service` 経由で mock_rag が注入され 200 を返す (TestRagFilingId の切り替え漏れがあると本 step でしか fail を捕捉できない)
- `TestRagApi::test_analyze_streams_when_pageindex_disabled` (新規) / `TestRagApi::test_analyses_returns_persisted_results_when_pageindex_disabled` (新規): ADR amendment §B の正の新仕様
- `TestRagApi::test_analyze_*` (475 / 512) と `TestRagFilingId::test_analyze_*` (561 / 592): monkeypatch 対象を `_get_rag_service` で据え置きしたため引き続き pass
- 旧 `test_analyze_returns_503_when_rag_disabled` / `test_analyses_returns_empty_when_rag_disabled` (Step 3.8c で削除済み) が collection から消えていること

fail する場合の典型原因:
- `_get_pageindex_rag_service` が `rag_index` / `rag_ask` に正しく繋がっていない (Step 3.8b (b) 漏れ)
- monkeypatch 対象の切り替え漏れ (Step 3.8e の table から外れている test がある — 特に TestRagFilingId の 627 / 656)
- `RagService.pageindex_available` property が `_pageindex is None` 判定を逆にしている (Step 3.4 (b2) のバグ)
- `setup_services` が `pageindex.enabled=False` で `pageindex_service=None` を `RagService` に渡せていない (Step 3.6 のバグ)

- [ ] **Step 3.8g: CLI `rag` サブコマンドの disabled 経路を `PageIndexDisabledError` catch + 明示 exit に揃える (Round 5 Finding 1 対応)**

CLI `cli/rag.py` は `services.rag_service is None` のときに「RAG service is not configured.」と stderr 出力して `sys.exit(1)` する既存 guard (line 64-67) を持つ。PR2 の C3 で `rag_service` が常時 non-None になると、この guard は到達不能になり、代わりに `_handle_ask` (line 201) / `_handle_index` (line 126 + 142) / `_handle_status` (line 217) が `PageIndexDisabledError` を未捕捉のまま投げる。CLI 利用者は意味不明な traceback を見て止まる。

修正方針: `handle()` dispatch 全体を `try / except PageIndexDisabledError` でラップし、Web 側の 503 と等価な明示 exit に揃える。`PageIndex` 非依存の action (`health` / `analyze` / `show`) は問題なく動作する (ADR amendment §B の挙動)。

(a) `cli/rag.py:64-83` の `handle()` を以下に置換:

```python
async def handle(args: argparse.Namespace, services: ServiceContainer) -> None:
    from stock_analyze_system.services.rag_service import PageIndexDisabledError

    if services.rag_service is None:
        # defense-in-depth: ADR-004 amendment §B では rag_service は常時 non-None.
        # setup_services が失敗した稀ケースのみ到達.
        print("RAG service is not configured.", file=sys.stderr)
        sys.exit(1)

    rag = services.rag_service
    action = args.action

    try:
        if action == "health":
            await _handle_health(rag, args)
        elif action == "index":
            await _handle_index(rag, services, args)
        elif action == "analyze":
            await _handle_analyze(rag, services, args)
        elif action == "ask":
            await _handle_ask(rag, services, args)
        elif action == "status":
            await _handle_status(rag, args)
        elif action == "show":
            await _handle_show(rag, services, args)
    except PageIndexDisabledError as exc:
        # ADR-004 amendment §B: ask/index/status は PageIndex 経路.
        # pageindex.enabled=false 時は明示 exit (Web 側の 503 と等価).
        print(f"PageIndex is disabled: {exc}", file=sys.stderr)
        print(
            "Set pageindex.enabled=true in config/settings.yaml to use this command.",
            file=sys.stderr,
        )
        sys.exit(1)
```

(b) CLI test 追加 — `tests/unit/cli/test_rag_cli.py` に以下 4 件を追加。既存 test の patch パターン (`MagicMock` で `services` を差し替える形) を踏襲:

```python
import argparse
from unittest.mock import AsyncMock, MagicMock

import pytest

from stock_analyze_system.cli import rag as rag_cli
from stock_analyze_system.services.rag_service import PageIndexDisabledError


async def test_rag_ask_exits_when_pageindex_disabled(monkeypatch, capsys):
    """ADR-004 amendment §B: pageindex.enabled=false で `rag ask` を実行すると
    明示エラー + exit 1 (Web 側の 503 と等価)."""
    services = MagicMock()
    services.rag_service = MagicMock()
    services.rag_service.ask_question = AsyncMock(
        side_effect=PageIndexDisabledError(
            "pageindex.enabled=false; ask_question は無効化されています"
        ),
    )
    company_mock = MagicMock(); company_mock.id = "US_AAPL"
    filing_mock = MagicMock(); filing_mock.storage_path = "/data/auto/fetched"
    from stock_analyze_system.cli import helpers as cli_helpers
    monkeypatch.setattr(
        cli_helpers, "require_company_and_filing",
        AsyncMock(return_value=(company_mock, filing_mock)),
    )

    args = argparse.Namespace(
        action="ask",
        company_id="US_AAPL",
        filing_type="10-K",
        question="What is the revenue?",
        json=False,
    )

    with pytest.raises(SystemExit) as exc_info:
        await rag_cli.handle(args, services)
    assert exc_info.value.code == 1
    assert "PageIndex is disabled" in capsys.readouterr().err


async def test_rag_index_exits_when_pageindex_disabled(monkeypatch, capsys):
    """`rag index` も同じ exit 経路."""
    services = MagicMock()
    services.rag_service = MagicMock()
    services.rag_service.build_index = AsyncMock(
        side_effect=PageIndexDisabledError(
            "pageindex.enabled=false; build_index は無効化されています"
        ),
    )
    company_mock = MagicMock(); company_mock.id = "US_AAPL"
    filing_mock = MagicMock(); filing_mock.storage_path = "/data/auto/fetched"
    from stock_analyze_system.cli import helpers as cli_helpers
    monkeypatch.setattr(
        cli_helpers, "require_company",
        AsyncMock(return_value=company_mock),
    )
    monkeypatch.setattr(
        cli_helpers, "require_latest_filing",
        AsyncMock(return_value=filing_mock),
    )

    args = argparse.Namespace(
        action="index",
        company_id="US_AAPL",
        filing_type="10-K",
        all_companies=False,
        json=False,
    )

    with pytest.raises(SystemExit) as exc_info:
        await rag_cli.handle(args, services)
    assert exc_info.value.code == 1
    assert "PageIndex is disabled" in capsys.readouterr().err


async def test_rag_status_exits_when_pageindex_disabled(capsys):
    """`rag status` も同じ exit 経路."""
    services = MagicMock()
    services.rag_service = MagicMock()
    services.rag_service.get_index_status = AsyncMock(
        side_effect=PageIndexDisabledError(
            "pageindex.enabled=false; get_index_status は無効化されています"
        ),
    )

    args = argparse.Namespace(
        action="status",
        company_id="US_AAPL",
        json=False,
    )

    with pytest.raises(SystemExit) as exc_info:
        await rag_cli.handle(args, services)
    assert exc_info.value.code == 1
    assert "PageIndex is disabled" in capsys.readouterr().err


async def test_rag_analyze_works_when_pageindex_disabled(monkeypatch):
    """ADR-004 amendment §B: 定型分析 (analyze) は PageIndex 非依存のため、
    pageindex.enabled=false でも動く."""
    from stock_analyze_system.services.rag_service import AnalysisResult
    from stock_analyze_system.services.pageindex import QueryResult

    services = MagicMock()
    services.rag_service = MagicMock()
    services.rag_service.pageindex_available = False
    fake_result = AnalysisResult(
        analysis_type="business_summary",
        result_json={"summary": "ok"},
        query_result=QueryResult(
            answer='{"summary": "ok"}', source_pages=[],
            source_sections=["business_summary"], confidence=1.0,
            model="test-model",
        ),
    )
    services.rag_service.run_full_analysis = AsyncMock(return_value=[fake_result])

    company_mock = MagicMock(); company_mock.id = "US_AAPL"
    filing_mock = MagicMock(); filing_mock.storage_path = "/data/auto/fetched"
    from stock_analyze_system.cli import helpers as cli_helpers
    monkeypatch.setattr(
        cli_helpers, "require_company_and_filing",
        AsyncMock(return_value=(company_mock, filing_mock)),
    )

    args = argparse.Namespace(
        action="analyze",
        company_id="US_AAPL",
        filing_type="10-K",
        type=None,
        json=True,
    )

    # SystemExit が出ない = pass.
    await rag_cli.handle(args, services)
    services.rag_service.run_full_analysis.assert_awaited_once()
```

`AnalysisResult` / `QueryResult` の signature や `to_dict` 系の戻り値が出力 path で参照されるため、実装前に `_handle_analyze` の `args.json=True` 経路 (line 175-176) を読み返して、`r.to_dict()` の呼び出しに耐える fixture か確認する。stub が不足するなら `AsyncMock` を `__getattr__` でカバーする形に変える。

(c) 実行:

```bash
scripts/infisical-run uv run pytest tests/unit/cli/test_rag_cli.py -q
```

Expected: 新規 4 件 + 既存 test 全件 pass。注意: `_handle_ask` / `_handle_index` / `_handle_status` を直接呼ぶのではなく `rag_cli.handle(...)` 経由で呼ぶことで try/except wrapper が効くことを同時に検証する (直接呼ぶ test だと wrapper を bypass して SystemExit を検出できない)。

- [ ] **Step 3.8h: characterization / integration 層の `rag_service is None` 期待を新仕様に置換 (Round 6 Finding 1 対応)**

`tests/unit/characterization/test_container_assembly.py` と `tests/integration/test_service_assembly.py` は ADR-004 amendment §B 以前の旧契約 (`pageindex.enabled=false` で `services.rag_service is None`) を固定している。C3 後はいずれも `is not None` が新仕様なので、本 step で更新する。漏らすと **`pytest tests/unit/characterization` および `pytest tests/integration/test_service_assembly.py` が必ず fail** する。

(a) `tests/unit/characterization/test_container_assembly.py:33-36` の `test_rag_service_none_when_pageindex_disabled` を、ADR-004 amendment §B の新契約に合わせて以下に置換:

```python
async def test_rag_service_constructed_when_pageindex_disabled(self, session):
    """ADR-004 amendment §B: pageindex.enabled=false でも RagService は
    常に構築される. 旧契約 (`rag_service is None`) は廃止."""
    config = build_test_config(pageindex_enabled=False)
    services = await setup_services(session, config)
    assert services.rag_service is not None
    assert type(services.rag_service).__name__ == "RagService"
    # PageIndex 経路だけが disabled になっている
    assert services.rag_service.pageindex_available is False
```

注意: 元 test 名 (`test_rag_service_none_when_pageindex_disabled`) は契約名が逆になっているため、リネーム前提で `Edit` の `old_string` に「`async def test_rag_service_none_when_pageindex_disabled(self, session):` から `assert services.rag_service is None` まで」を含めて完全置換する。

(b) `tests/integration/test_service_assembly.py:114-125` の `test_non_rag_features_work_when_rag_disabled` (`TestRagAssembly` クラス内) を新契約に合わせて修正:

```python
async def test_non_rag_features_work_when_pageindex_disabled(self, session):
    """ADR-004 amendment §B: pageindex.enabled=false でも RagService は構築される.
    旧 test 名 `test_non_rag_features_work_when_rag_disabled` から rename
    (rag_service は disabled でも non-None になったため)."""
    services = await setup_services(session, build_test_config(pageindex_enabled=False))
    assert services.rag_service is not None
    assert services.rag_service.pageindex_available is False
    assert services.company_service is not None

    await services.company_service.register_company({
        "ticker": "X", "name": "X Corp",
        "market": "NASDAQ", "accounting_standard": "US-GAAP",
    })
    company = await services.company_service.get_company("US_X")
    assert company is not None
    assert company.ticker == "X"
```

`assert services.rag_service is None` を `assert services.rag_service is not None` + `pageindex_available is False` に書き換え、関数名も新契約に揃える。

(c) 実行 (回帰確認):

```bash
scripts/infisical-run uv run pytest \
  tests/unit/characterization/test_container_assembly.py \
  tests/integration/test_service_assembly.py::TestRagAssembly \
  -q
```

Expected:
- `test_rag_service_constructed_when_pageindex_disabled` (リネーム後): pass (Step 3.5 / 3.6 で `setup_services` が `RagService` を常時構築するように変えてあるため)
- `test_rag_service_created_when_pageindex_enabled`: 引き続き pass (既存挙動)
- `test_non_rag_features_work_when_pageindex_disabled` (リネーム後): pass
- `test_rag_service_wired_when_pageindex_enabled`: 引き続き pass
- `test_rag_qa_history_round_trips_via_assembled_service`: 引き続き pass (`pageindex_enabled=True` 経路は無変更)

注意: integration test の `pageindex_enabled=True` 経路 (`test_rag_service_wired_when_pageindex_enabled` / `test_rag_qa_history_round_trips_via_assembled_service`) は本 step で touch しない。`PageIndexService` 構築前提は維持。

(d) 件数: characterization 1 件 修正 (rename) + integration 1 件 修正 (rename) — 新規追加・削除はゼロなので Step 5.1 の合計 (`21 件追加 / 3 件削除`、Round 6 Finding 3 で helper 直接 test 3 件追加して 18 → 21) は変わらないが、Step 3.11 commit には対象ファイルを含める。

- [ ] **Step 3.9: テストを実行して pass を確認**

Run:
```bash
scripts/infisical-run uv run pytest \
  tests/unit/services/test_rag_service.py \
  tests/unit/services/test_analysis_worker.py \
  tests/unit/cli/test_helpers.py \
  tests/unit/cli/test_rag_cli.py \
  tests/unit/web/test_api.py \
  -q
```

Expected: 全件 pass。
- 新規 6 件 (service / cli): `TestPageIndexIndependence` 5 件 + `test_constructs_rag_service_when_pageindex_disabled` 1 件
- 新規 4 件 (CLI): `test_rag_ask_exits_when_pageindex_disabled` / `test_rag_index_exits_when_pageindex_disabled` / `test_rag_status_exits_when_pageindex_disabled` / `test_rag_analyze_works_when_pageindex_disabled`
- 新規 2 件 (web): `test_analyze_streams_when_pageindex_disabled` + `test_analyses_returns_persisted_results_when_pageindex_disabled` (Step 3.8c)
- 新規 3 件 (web、Round 6 Finding 3): `TestRagHelperSplit::test_get_rag_service_returns_when_pageindex_disabled` / `test_get_rag_service_raises_503_when_rag_service_none` / `test_get_pageindex_rag_service_raises_503_when_pageindex_disabled` (Step 3.8b (d) — helper 直接 test)
- 既存 9 件 (web、Step 3.8e): rag_ask / rag_index 系の monkeypatch 対象が `_get_pageindex_rag_service` に切り替わり、引き続き pass (TestRagApi 7 件 + TestRagFilingId 2 件)
- 既存 4 件据え置き (web、Step 3.8e): rag_analyze 系の monkeypatch は `_get_rag_service` のまま (TestRagApi 2 件 + TestRagFilingId 2 件)
- 削除 3 件: `test_run_one_job_rag_disabled` (worker) + `test_analyze_returns_503_when_rag_disabled` (web) + `test_analyses_returns_empty_when_rag_disabled` (web)
- 維持 2 件 (web): `test_ask_returns_503_when_rag_disabled` + `test_index_rag_disabled_does_not_consume_rate_limit` が `_get_pageindex_rag_service` 経由で引き続き 503 / rate-limit-free 契約を維持 (Step 3.8f で個別検証済み)
- 既存 PageIndex 経路 test 9 件 (TestRagApi 7 件 + TestRagFilingId 2 件) は Step 3.8e で `monkeypatch.setattr` の対象が `_get_pageindex_rag_service` に切り替わり引き続き pass
- 既存 `test_rag_service.py` の他 test (`service` fixture を使うもの) は `pageindex_service` 引数の型変更 (`PageIndexService | None`) でも互換のため引き続き pass
- Task 2 で追加した `test_options_default_falls_back_to_sec_filing_when_latest_is_edinet` が、Step 3.8d の `rag_filing_options` 修正後に pass する (C2 commit 時点では default が `services.rag_service is not None` を見るが、C3 で `pageindex_available` 条件に変えると、無効化時の `get_latest_indexed` を skip して `list_by_recency` 経路に落ちる結果、SEC 10-Q を選ぶようになる)

- [ ] **Step 3.10: 周辺 caller の grep verify**

Run:
```bash
# (a1) web route に残す defense-in-depth guard が想定どおり 4 箇所だけであること
git grep -nE 'rag_service\s+is\s+None|rag\s+is\s+None' \
  -- src/stock_analyze_system/web/routes/api.py

# (a2) worker の terminal lifecycle から rag is None ガードが消えていること
git grep -nE 'rag\s+is\s+None' \
  -- src/stock_analyze_system/services/analysis_worker.py || test $? -eq 1

# (b) pageindex_available が web 側で正しく参照されていること
git grep -n 'pageindex_available' -- src/stock_analyze_system/web/

# (c) PageIndexDisabledError が test 側で import されていること
git grep -n 'PageIndexDisabledError' -- src/ tests/ || test $? -eq 1
```

Expected:
- (a1): `web/routes/api.py` で 4 箇所のヒット:
  - `_get_rag_service` 内: `if services.rag_service is None: raise 503` (defense-in-depth、`rag_analyze` で使用)
  - `_get_pageindex_rag_service` 内: `if rag is None or not rag.pageindex_available: raise 503` (`rag_ask` / `rag_index` で使用)
  - `rag_analyses` 冒頭: `if services.rag_service is None: return []` (defense-in-depth)
  - `rag_history` 冒頭: `if services.rag_service is None or not services.rag_service.pageindex_available: return []`
  - `rag_filing_options.default` の `if services.rag_service is not None and services.rag_service.pageindex_available:` は `is not None` なので (a1) ではヒットせず、(b) の `pageindex_available` grep で確認する
- (a2): no match (`test $? -eq 1` により command 全体は exit 0)。`analysis_worker.py` の `rag is None` ガードは Step 3.7 で削除済み
- (b): `web/routes/api.py` で `_get_pageindex_rag_service` / `rag_history` / `rag_filing_options` の 3+ 箇所がヒット
- (c): `services/rag_service.py` (定義) / `src/stock_analyze_system/cli/rag.py` (catch) / `tests/unit/services/test_rag_service.py` (raises) / `tests/unit/cli/test_helpers.py` (raises) / `tests/unit/cli/test_rag_cli.py` (CLI exit) がヒット

- [ ] **Step 3.11: commit (C3)**

```bash
git add src/stock_analyze_system/shared/clients.py \
        src/stock_analyze_system/cli/container.py \
        src/stock_analyze_system/services/rag_service.py \
        src/stock_analyze_system/services/analysis_worker.py \
        src/stock_analyze_system/web/routes/api.py \
        src/stock_analyze_system/cli/rag.py \
        tests/unit/services/test_rag_service.py \
        tests/unit/services/test_analysis_worker.py \
        tests/unit/cli/test_helpers.py \
        tests/unit/cli/test_rag_cli.py \
        tests/unit/web/test_api.py \
        tests/unit/characterization/test_container_assembly.py \
        tests/integration/test_service_assembly.py
git commit -m "$(cat <<'EOF'
fix(rag): construct RagService independent of pageindex.enabled (A3)

ADR-004 amendment §B に従い、定型分析を pageindex.enabled から独立させる:

- `RagService.__init__` の `pageindex_service` 引数を `PageIndexService | None`
  に変更し、`build_index` / `ask_question` / `get_index_status` に
  `PageIndexDisabledError` ガードを追加
- `RagService.pageindex_available` property を導入 (web route が rate limit
  より前に 503 を返すための判定子)
- `shared/clients.py` で `LlmClient` を常時構築 (PdfConverter のみ条件付き)
- `cli/container.py` で `RagService` を常時構築、`PageIndexService` だけ
  `config.pageindex.enabled` 条件下に
- `web/routes/api.py` の helper を 2 系統に分割:
  * `_get_rag_service`: `rag_service is None` だけ確認 (defense-in-depth)、
    deprecated `rag_analyze` で使用
  * `_get_pageindex_rag_service`: `pageindex_available` を確認、`rag_ask` /
    `rag_index` で使用 (rate limit より前に 503 で early return)
- `rag_analyses` は pageindex.enabled=false でも保存済み結果を返す
  (ADR amendment §B: 定型分析は PageIndex 非依存)。旧 test
  `test_analyses_returns_empty_when_rag_disabled` を削除し、新仕様 test
  `test_analyses_returns_persisted_results_when_pageindex_disabled` に置換
- `rag_history` は `pageindex_available=False` 時に空リスト (ask 副産物)
- `rag_filing_options.default` の indexed lookup gate を
  `pageindex_available` に揃え、disabled 時は indexed lookup を skip する
- 旧 test `test_analyze_returns_503_when_rag_disabled` を削除し、新仕様 test
  `test_analyze_streams_when_pageindex_disabled` に置換
- 既存 PageIndex 経路 test 9 件 (TestRagApi 7 件 + TestRagFilingId 2 件) の
  `monkeypatch.setattr(..., "_get_rag_service", ...)` を
  `_get_pageindex_rag_service` に切り替え (helper 分割の追従)。
  rag_analyze 系 4 件 (TestRagApi 2 件 + TestRagFilingId 2 件) は据え置き
- `cli/rag.py` の `handle()` を `try / except PageIndexDisabledError` でラップし、
  ask / index / status の disabled 時に明示 exit 1 (Web 側の 503 と等価)。
  analyze は ADR amendment §B 通り disabled でも動く。test_rag_cli.py に
  4 件追加
- `analysis_worker.py` の `rag is None` ガードを削除
- `test_run_one_job_rag_disabled` を削除 (rag_service=None は設計上消滅)
- pageindex.enabled=false 下で定型分析 (run_full_analysis / stream) が動作し、
  PageIndex 経路 3 メソッドが `PageIndexDisabledError` を投げる test を追加
- 既存 web test のうち `ask` 503 / `index` rate-limit-free は
  `_get_pageindex_rag_service` 経由で維持し、`analyze` / `analyses` は
  ADR amendment §B の新契約 (disabled でも動作 / 保存済み結果を返す) に置換

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: A4 + A15 — runbook 修正 と `ERROR_DETAILS_KEYS` static check (C4)

**Files:**
- Modify: `docs/analysis-jobs-runbook.md`
- Modify: `src/stock_analyze_system/services/analysis_worker.py`
- Modify: `tests/unit/services/test_analysis_worker.py`

- [ ] **Step 4.1: 失敗テストを test_analysis_worker.py に追加**

`tests/unit/services/test_analysis_worker.py` の末尾に以下を追加:

```python
def test_runbook_error_details_keys_match_worker_constants():
    """ADR-004 §A15: runbook の error_details 表が worker の実装定数と同期
    していることを検査. ERROR_DETAILS_KEYS を変更したら runbook も更新する."""
    from pathlib import Path
    from stock_analyze_system.services.analysis_worker import (
        ERROR_DETAILS_KEYS,
    )

    runbook = Path("docs/analysis-jobs-runbook.md").read_text(encoding="utf-8")

    for key in ERROR_DETAILS_KEYS:
        assert f'"{key}"' in runbook, (
            f"runbook missing error_details key: {key}; "
            "update docs/analysis-jobs-runbook.md §2.1 table"
        )
    # legacy 行は明示的に残す (ADR-004 前のジョブ識別のため)
    assert '"index_build_error"' in runbook, (
        "runbook must document legacy index_build_error key for older jobs"
    )
```

- [ ] **Step 4.2: テストを実行して fail を確認**

Run:
```bash
scripts/infisical-run uv run pytest \
  tests/unit/services/test_analysis_worker.py::test_runbook_error_details_keys_match_worker_constants \
  -q
```

Expected: `ImportError: cannot import name 'ERROR_DETAILS_KEYS' from 'stock_analyze_system.services.analysis_worker'` で fail。

- [ ] **Step 4.3: `analysis_worker.py` に `ERROR_DETAILS_KEYS` を追加**

`src/stock_analyze_system/services/analysis_worker.py` の module-level (imports の直後、class 定義の前あたり) に追加:

```python
# ADR-004 §A15: runbook (docs/analysis-jobs-runbook.md §2.1) と
# error_details の key 名を同期するための単一情報源。
# 追加・改名するときは runbook の表も同時に更新する
# (`test_runbook_error_details_keys_match_worker_constants` が同期を検査)。
ERROR_DETAILS_KEYS: frozenset[str] = frozenset({
    "extraction_error",  # FilingSectionExtractor / preflight 失敗
    "failed_types",      # 特定 analysis_type の step-3 LLM 失敗
})
```

`"index_build_error"` は **入れない** (現行 worker は emit しない。legacy ジョブ向けの runbook 記述として残す)。`"reason"` (worker の `except Exception` 経路) は test の対象外 — 当 frozenset は「ADR-004 後の主要 error_details 構造を runbook と同期する」スコープに限定する。

- [ ] **Step 4.4: テストを実行 — 依然 fail を確認 (runbook が未更新のため)**

Run:
```bash
scripts/infisical-run uv run pytest \
  tests/unit/services/test_analysis_worker.py::test_runbook_error_details_keys_match_worker_constants \
  -q
```

Expected: **依然 fail**。`ImportError` は解消するが、現行 runbook §2.1 (line 56-62) は `index_build_error` 系の表記のみで `"extraction_error"` 文字列を含まないため、assertion `f'"{key}"' in runbook` が `extraction_error` で fail する。`"failed_types"` は現行 runbook の line 61-62 に既に存在するため fail しないが、最初の key (frozenset の iteration 順は不定) で fail することもある。実装手順は意図的に「定数追加 → 依然 fail → runbook 更新 → pass」の順なので、ここで fail することが想定。

事前確認:
```bash
grep -c '"extraction_error"' docs/analysis-jobs-runbook.md
```
Expected: `0` (置換前)。Step 4.6 後に `3` 以上になる。

- [ ] **Step 4.5: runbook §1 の llama-server 起動コマンドを更新 (A4)**

`docs/analysis-jobs-runbook.md` line 24-38 (`# 端末3: LLM バックエンド (llama-server)` から `--parallel 4 \` 以降の説明段落) を以下に置換:

````markdown
# 端末3: LLM バックエンド (llama-server)
# 重要: enable_thinking=false を chat template に効かせるため --jinja が必須.
# Qwen3.6 / Qwen3.5 の chat template は jinja 評価器なしでは
# `enable_thinking` パラメータを無視するため、思考トークン暴走の温床になる.
llama-server \
  --model /path/to/Qwen3.6-27B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 \
  --jinja \
  --ctx-size 131072 \
  --n-gpu-layers 99 \
  --parallel 1 \
  > data/logs/llama-server.log 2>&1
```

`--parallel N` は `--ctx-size` を slot 数で分割するため、ADR-004 step 3 の `risk_factors` (RXRX で ~58K prompt tokens) を 1 slot に収めるには `--parallel 1` (= slot ctx 131072) が必須。より小さい ctx-size や多い parallel slot に下げると実 10-K セクションが context overflow するため、ADR-004 検証済み構成 (`docs/adr/004-sec-filing-section-extractor.md` Known limitations 参照) から外れる設定にしないこと。

`--jinja` を付けない場合、`extra_body.chat_template_kwargs.enable_thinking=false` を送っても効かず、Qwen3 系は `<think>...` を出力する。これが PageIndex 経路で TOC 抽出が空応答になる既知経路。**ADR-004 適用後の定型分析では section 抽出に LLM を呼ばないためこの経路は発火しないが、`ask_question` 経路では引き続き発火するため `--jinja` は必須**。
````

注意:
- 既存 line 38 にある「これが `generate_toc_init` の `max_tokens=32768` を使い切り `Processing failed` に至る既知経路。」は ADR-004 後の挙動と齟齬が出るため、上記置換に合わせて差し替え (`ask_question` 経路でも `generate_toc_init` は使われるが、`Processing failed` は ADR-004 前の症状)。
- 既存 line 32-35 を `--ctx-size 131072 --parallel 1` に置換、`--parallel N` 説明文を追加、最後の解説段落も書き換える、というのが本 step の要点。

- [ ] **Step 4.6: runbook §2.1 の `error_details` 表を更新 (A15)**

`docs/analysis-jobs-runbook.md` line 54-63 の表 (現状 `index_build_error` 系 4 行 + `failed_types` 系 2 行 + 旧形式 1 行) を以下に書き換える:

````markdown
`error_details` の形で原因層が判別できる (ADR-004 以後):

| 形 | 意味 | 次の手 |
|---|---|---|
| `{"extraction_error": {"message": "preflight failed (error): ...", "diagnostic": {...}}}` | step-3 LLM probe が失敗 (`rag.preflight()` がエラー) | llama-server 状態確認、§3.1 |
| `{"extraction_error": {"message": "preflight failed (empty): ...", "diagnostic": {...}}}` | step-3 LLM probe が空文字列で返った | chat template / `--jinja` 確認、§3.2 |
| `{"extraction_error": {"message": "..."}}` (diagnostic 無し) | `FilingSectionExtractor` が parse 例外を投げた (HTML 破損 / 解凍失敗 等) | `data/logs/stock_analyze.log` の `section extraction failed for filing N` を grep、`<storage_path>/raw/` を確認 |
| `{"failed_types": [{"type": "mda", "message": "..."}]}` | extractor は成功、特定タイプの step-3 LLM 呼び出し失敗 | §3.3 |
| `{"failed_types": [{"type": "business_summary", "message": "ファイリングに該当章がありません"}]}` | 10-Q `business_summary`/`competitors`、6-K `risk_factors`/`competitors` 等、filing 種別の構造上章が存在しないケース。正常仕様 (UI 側で「該当章なし」表示が望ましい) | 対処不要 |
| `{"index_build_error": {...}}` | **legacy (ADR-004 以前)** PageIndex 経路で失敗したジョブ。現在の worker は emit しない | 再 enqueue すれば新形式 (`extraction_error` または `failed_types`) で再記録される |
| `{"reason": "..."}` (旧 unexpected) | worker の `except Exception` 経路。スタックトレースは `data/logs/stock_analyze.log` を確認 | log を grep |
````

ポイント:
- `extraction_error` は preflight 系 / extractor 系 / per-type 系の 3 行に分割
- legacy `index_build_error` は 1 行に集約し「現在の worker は emit しない」を明記
- `reason` (unexpected exception 経路) も 1 行追加
- 旧 `failed_types: [{type: null, ...}]` 行は legacy `index_build_error` 行に吸収

未確定事項 (spec §6.8 (3)) の「legacy `index_build_error` データの再 enqueue 運用判断」は runbook 表の「次の手」欄に「再 enqueue すれば新形式で再記録される」と書き切る (能動的な migration script は本 PR 範囲外)。

- [ ] **Step 4.7: runbook §3.2 の文言を確認**

Run:
```bash
grep -n "本手順の有効範囲" docs/analysis-jobs-runbook.md
```

Expected: line 114 付近に `本手順の有効範囲: 本節 (§3.2) は ask_question (自由質問) 経路専用` 等の既存記述があるはず。これは Step 4.5 / 4.6 の変更で齟齬が出ないため touch 不要。Step 4.5 の段落書き換えで「ADR-004 適用後は ask_question 経路でのみ」と記載することで §3.2 と整合する。

未確定事項 (spec §6.8 (2)) の「runbook §3.1 / §3.2 の参照が ADR-004 amendment 後も適切な指示になっているか」は: §3.1 (curl による llama-server 接続確認) は ADR-004 後も有効 (step-3 LLM probe failure の復旧手順そのまま)、§3.2 (jinja / chat template) も `ask_question` 経路では依然必要。これらは本 PR で変更しない。

- [ ] **Step 4.7b: runbook §3.3 の「step 3 でも reasoning_content 暴走」記述を ADR-004 適用後に整合 (Round 6 Finding 6 対応)**

現行 `docs/analysis-jobs-runbook.md:120` の `ADR-004 §4.5 のリスク` 段落は **「Qwen3.6 が step 3 でも `reasoning_content` 暴走で `content` を空にする可能性がある」** と書いているが、これは ADR-004 step 3 検証 (`--ctx-size 131072 --parallel 1 --jinja` 構成で実機検証済み、`docs/step3-reasoning-runaway-verification.md` 参照) と矛盾する。Round 8 Finding 2 補正: 本 PR の amendment §B が言うのは「**章抽出段** が LLM 非依存になった」ことであって、step 3 (`_analyze_section`) は引き続き LLM を呼ぶ。したがって新文言では (a) 章抽出段では `reasoning_content` 暴走自体が起こり得ない (LLM を通らない)、(b) step 3 は LLM 呼び出しなので検証済み構成 (`--ctx-size 131072 --parallel 1 --jinja`) と `_is_empty_llm_response` ガード (`rag_service.py:215-218`) の 2 層で扱う、という構造を明示する。§3.3 内で「定型分析でも step 3 で暴走しうる」と読める表現が残ると、検証済み構成・空応答ガード・§3.4 (定型分析で章が空)・§1 の `--ctx-size 131072 --parallel 1` 構成と齟齬する。

`Edit` で line 120 の段落を以下に置換 (旧文の `**ADR-004 §4.5 のリスク**:` から段落末尾 `別 ADR で扱う。` までを一括差し替え):

````markdown
**ADR-004 §4.5 のリスク**: `risk_factors` / `mda` の章テキストは数千〜数万文字 (RXRX 10-K Item 1A は ~32 万字)。**定型分析の章抽出自体は LLM 非依存 (extractor が HTML から決め打ちで取る) だが、step 3 (`_analyze_section`) は抽出済み章本文を `LlmClient.completion` に prompt として連結して LLM に渡す** (`src/stock_analyze_system/services/rag_service.py:210-214`)。ADR-004 検証済み構成 (`--ctx-size 131072 --parallel 1 --jinja`、`docs/step3-reasoning-runaway-verification.md` 参照) では `reasoning_content` 暴走は再現せず、`_is_empty_llm_response` ガード (`rag_service.py:215-218`) が空応答を `ValueError` に変換して `failed_types[].message` に出すため fail を隠さない。`ask_question` 経路は `response_format` を渡さない + PageIndex-selected context (tree search で選ばれたノード群、`src/stock_analyze_system/services/pageindex/service.py:445-470` の `selected_nodes`) を context に積む構造で、章丸ごとではないものの選定ノード次第で同等のトークン規模に膨らみ得るため同じ症状が出やすい。

`failed_types[].message` に `JSONDecodeError` や空応答が頻発したら:
- **定型分析の per-type 失敗**: §1 の llama-server 起動コマンドが `--ctx-size 131072 --parallel 1 --jinja` 構成と一致しているか確認 (ctx を絞ったり parallel slot を増やすと章 + prompt が overflow して空応答 / `BadRequestError` になる)。一致していれば `services/prompts.py` の prompt と spec のミスマッチを疑う
- **`ask_question` 経路の失敗**: §3.2 の jinja / chat template 手順を踏む。ADR-004 適用後も `ask_question` は LLM 経路を残しているため §3.2 の有効範囲内
````

ポイント:
- 「定型分析の章抽出は LLM 非依存」と「step 3 は抽出済み章本文を LLM に渡す」を分けて書く (前者は extractor、後者は `_analyze_section` の責務)
- ADR-004 step 3 検証済み構成下では runaway が再現しないことを `docs/step3-reasoning-runaway-verification.md` 参照付きで明示
- 空応答 guard (`_is_empty_llm_response` → `ValueError`) が fail を隠さないことを明記 (現行 `rag_service.py:215-218` の挙動)
- 失敗時切り分けを「定型分析 = ctx-size 構成、prompt mismatch」「ask_question = §3.2」に分離

実行:

```bash
# 旧文言が消えていること
grep -n 'step 3 でも `reasoning_content` 暴走' docs/analysis-jobs-runbook.md || test $? -eq 1
echo "old §3.3 text removed exit=$?"

# 新文言が入っていること (step 3 が章本文を LLM に渡す事実を明示)
grep -nE '抽出済み章本文を .*LlmClient\.completion|step 3 \(`_analyze_section`\)' docs/analysis-jobs-runbook.md
echo "new §3.3 text exit=$?"

# 検証済み構成への参照が新文言に含まれていること
grep -n 'step3-reasoning-runaway-verification' docs/analysis-jobs-runbook.md
echo "verification doc reference exit=$?"
```

Expected: 旧文言は no match (`test $? -eq 1` で exit 0)、新文言は 1 件 hit、検証 doc 参照も 1 件 hit。

注意: 本 step も commit C4 (Step 4.10) に含める (runbook 修正 1 commit に集約)。

- [ ] **Step 4.8: テストを再実行 — pass を確認**

Run:
```bash
scripts/infisical-run uv run pytest \
  tests/unit/services/test_analysis_worker.py::test_runbook_error_details_keys_match_worker_constants \
  -q
```

Expected: **pass**。Step 4.6 で書き換えた runbook §2.1 表に `"extraction_error"` / `"failed_types"` / `"index_build_error"` の 3 文字列がすべて含まれている (`extraction_error` は preflight 系 / extractor 系 / per-type 系の 3 行に出現、`failed_types` は 2 行に出現、`index_build_error` は legacy 行に 1 回出現)。事前確認:

```bash
grep -c '"extraction_error"' docs/analysis-jobs-runbook.md
grep -c '"failed_types"' docs/analysis-jobs-runbook.md
grep -c '"index_build_error"' docs/analysis-jobs-runbook.md
```

Expected: それぞれ 3 / 2 / 1 (以上)。

- [ ] **Step 4.9: runbook の git diff を目視確認**

Run:
```bash
git diff docs/analysis-jobs-runbook.md
```

Expected: 以下 3 箇所だけが変更されていること:
- §1 の llama-server コマンド (`--ctx-size 131072 --parallel 1`、Step 4.5)
- §2.1 の error_details 表 (Step 4.6)
- §3.3 の `ADR-004 §4.5 のリスク` 段落 (Step 4.7b、Round 8 Finding 3 補正後): 定型分析の **章抽出段は LLM 非依存** だが **step 3 (`_analyze_section`) は抽出済み章本文を LLM に渡す**、検証済み構成 + `_is_empty_llm_response` ガードで扱う、という構造を明示。`ask_question` は PageIndex-selected context を context に積むので同等のトークン規模に膨らみ得る、と切り分ける。失敗時の切り分け先を「定型分析 per-type 失敗 = ctx-size 構成 + prompt mismatch」「`ask_question` = §3.2 (jinja / chat template)」の 2 系統に分離

他のセクション (§2.2 diagnostic / §3.1 / §3.2 / §3.4 / §4 既知の制約 / §5 関連 docs) は無変更。

- [ ] **Step 4.10: commit (C4)**

```bash
git add docs/analysis-jobs-runbook.md \
        src/stock_analyze_system/services/analysis_worker.py \
        tests/unit/services/test_analysis_worker.py
git commit -m "$(cat <<'EOF'
docs(runbook): align llama-server config and error_details keys with ADR-004 (A4 + A15)

A4 (runbook §1): llama-server 起動コマンドを ADR-004 検証済み構成
`--ctx-size 131072 --parallel 1 --jinja --n-gpu-layers 99` に更新し、
`--parallel N` と slot ctx の関係を 1 行で明記。旧 `--ctx-size 32768
--parallel 4` (= slot ctx 8192) では実 10-K の risk_factors が context
overflow する。

A15 (runbook §2.1): error_details 表を ADR-004 後の形 (`extraction_error`
3 形 + `failed_types` 2 形 + legacy `index_build_error` + 旧 `reason`) に
分離し直す。`extraction_error` は preflight failure / extractor exception /
per-type LLM error の 3 サブパターンを記述。

A15 static check: `analysis_worker.ERROR_DETAILS_KEYS` 定数を導入し、
runbook 表と key 名が同期していることを `pytest` で検査
(`test_runbook_error_details_keys_match_worker_constants`)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: PR2 全体の merge gate 検証

ここまでで 4 commits (C1-C4) が積み上がっている。PR を出す前に spec §6.7 の merge gate 全項を満たすことを確認する。

- [ ] **Step 5.1: unit test 全領域を実行**

Run:
```bash
scripts/infisical-run uv run pytest \
  tests/unit/services/test_rag_service.py \
  tests/unit/services/test_analysis_worker.py \
  tests/unit/services/test_filing_section_extractor.py \
  tests/unit/web/test_api.py \
  tests/unit/web/test_analysis_jobs.py \
  tests/unit/cli/test_helpers.py \
  tests/unit/cli/test_rag_cli.py \
  tests/unit/characterization/test_container_assembly.py \
  -q

# integration 層は marker 経由でフィルタしてまとめて走らせる:
scripts/infisical-run uv run pytest \
  tests/integration/test_service_assembly.py::TestRagAssembly \
  -q
```

Expected: 全件 pass。新規追加した test:
- `test_create_rejects_annual_report_filing` / `test_create_rejects_non_sec_source` / `test_create_accepts_six_k_filing` (test_analysis_jobs.py)
- `test_options_exclude_annual_report_and_non_sec` / `test_options_default_falls_back_to_sec_filing_when_latest_is_edinet` (test_api.py)
- `test_analyze_streams_when_pageindex_disabled` / `test_analyses_returns_persisted_results_when_pageindex_disabled` (test_api.py — ADR amendment §B 新仕様)
- `TestPageIndexIndependence` 5 件 (test_rag_service.py)
- `test_constructs_rag_service_when_pageindex_disabled` (test_helpers.py)
- `test_runbook_error_details_keys_match_worker_constants` (test_analysis_worker.py)
- `test_rag_ask_exits_when_pageindex_disabled` / `test_rag_index_exits_when_pageindex_disabled` / `test_rag_status_exits_when_pageindex_disabled` / `test_rag_analyze_works_when_pageindex_disabled` (test_rag_cli.py — Step 3.8g 新規 CLI 対応)
- `TestRagHelperSplit::test_get_rag_service_returns_when_pageindex_disabled` / `test_get_rag_service_raises_503_when_rag_service_none` / `test_get_pageindex_rag_service_raises_503_when_pageindex_disabled` (test_api.py — Step 3.8b (d) Round 6 Finding 3 対応: helper 直接 test)

合計 **21 件追加 / 3 件削除** (`test_run_one_job_rag_disabled` / `test_analyze_returns_503_when_rag_disabled` / `test_analyses_returns_empty_when_rag_disabled`)。後者 2 件は ADR amendment §B により旧仕様、新仕様 test 2 件で置換済み。

内訳: tests/unit/web/test_analysis_jobs.py 3 件 (annual_report rejection 系) + tests/unit/web/test_api.py 7 件 (options 2 + analyze/analyses 新仕様 2 + helper 直接 test 3) + tests/unit/services/test_rag_service.py 5 件 (TestPageIndexIndependence) + tests/unit/cli/test_helpers.py 1 件 + tests/unit/services/test_analysis_worker.py 1 件 (runbook static check) + tests/unit/cli/test_rag_cli.py 4 件 (Step 3.8g: rag ask/index/status exit + analyze works) = 21 件。

別途、characterization/integration 層で **2 件 modify** (rename + assertion 反転): `tests/unit/characterization/test_container_assembly.py::test_rag_service_constructed_when_pageindex_disabled` (旧 `_none_when_pageindex_disabled`)、`tests/integration/test_service_assembly.py::TestRagAssembly::test_non_rag_features_work_when_pageindex_disabled` (旧 `_when_rag_disabled`)。Round 6 Finding 1 対応、新規・削除ではないため合計には含めない。

- [ ] **Step 5.2: 既存全体 unit test を実行 (回帰確認)**

Run:
```bash
scripts/infisical-run uv run pytest tests/unit -q --ignore=tests/integration
```

Expected: 全件 pass (本 PR の範囲外で偶発的に回帰していないことを確認)。失敗が出たら本 PR の変更による副作用を疑い、特に `PIPELINE_EXTRACTOR` / `rag_service` 周辺の他テストを再確認すること。

- [ ] **Step 5.2b: `npm test` (frontend smoke、Round 6 Finding 5 対応)**

spec §1 line 30 (`PR ごとに「関連 unit + npm test + git diff --check」`) と spec §10 line 1136 の最終 regression 要求に従い、PR2 でも `npm test` を gate に含める。本 PR は JS を直接 touch しないが、`rag_filing_options` のレスポンス契約 (annual_options から annual_report が消える、default 探索ロジック変更) と `pageindex_available` 経由の 503 切り替えが UI 表示に波及する可能性があるため、最低限の smoke として実行する。

Run:
```bash
npm test
```

Expected: `tests/js/*.test.mjs` の全件 pass。`package.json` の `scripts.test` は `node --test tests/js/*.test.mjs` (Node 標準テストランナー、jsdom ベース)。失敗が出たら本 PR の API 契約変更が UI 側の期待を破っていないか (特に `rag/analyses` レスポンスや `rag/filing-options` の `default.is_fallback_default` 周り) を確認する。

注意: `npm` を別環境で動かす場合は `package.json` 直下で `npm install` を 1 度実行しておく (`jsdom@^25.0.0` だけが devDependency)。

- [ ] **Step 5.3: ADR / runbook と worker 定数の static 整合性を grep gate**

Run:
```bash
# (a) ADR-004 末尾に Amendment 2026-05-17 が存在すること
grep -nE '^### Amendment 2026-05-17' docs/adr/004-sec-filing-section-extractor.md
echo "ADR amendment exit=$?"

# (b) runbook の llama-server コマンドが ADR-004 検証済み構成と一致
#     llama-server コマンドは複数行 (各 flag が別行) なので、grep は 1 flag ずつ別個に当てる
grep -n -- '--ctx-size 131072' docs/analysis-jobs-runbook.md
echo "runbook ctx-size exit=$?"
grep -n -- '--parallel 1' docs/analysis-jobs-runbook.md
echo "runbook parallel exit=$?"
grep -n -- '--jinja' docs/analysis-jobs-runbook.md
echo "runbook jinja exit=$?"
grep -n -- '--n-gpu-layers 99' docs/analysis-jobs-runbook.md
echo "runbook n-gpu-layers exit=$?"

# (c) 旧 ctx-size 32768 / parallel 4 が runbook に残っていないこと
grep -nE 'ctx-size\s+32768' docs/analysis-jobs-runbook.md || test $? -eq 1
echo "no old ctx-size exit=$?"
grep -nE 'parallel\s+4' docs/analysis-jobs-runbook.md || test $? -eq 1
echo "no old parallel exit=$?"

# (d) ANALYSIS_FILING_TYPES から ANNUAL_REPORT が消えていること
grep -nE 'ANALYSIS_FILING_TYPES\s*=' -A 6 src/stock_analyze_system/web/routes/api.py
```

Expected:
- (a): line 1 ヒット (`ADR amendment exit=0`)
- (b): 4 つの grep がすべて line 1 以上ヒット (`runbook ctx-size exit=0` / `runbook parallel exit=0` / `runbook jinja exit=0` / `runbook n-gpu-layers exit=0`)
- (c): 2 つの grep がいずれも no match (`no old ctx-size exit=0` / `no old parallel exit=0`)
- (d): `ANALYSIS_FILING_TYPES` が `TEN_K, TWENTY_F, TEN_Q, SIX_K` の 4 種で構成され、`ANNUAL_REPORT` が含まれていないこと

何か外れたら該当 Task に戻って修正する。

- [ ] **Step 5.4: 整合性確認 — helper 2 系統と `pageindex_available` の使い分けが正しいこと**

Run:
```bash
# (a) _get_pageindex_rag_service が ask / index の 2 endpoint で使われていること
git grep -nE '_get_pageindex_rag_service\(' -- src/stock_analyze_system/web/

# (b) _get_rag_service は rag_analyze のみで使われていること (ask / index で残っていたら誤用)
git grep -nE '_get_rag_service\(' -- src/stock_analyze_system/web/

# (c) ADR amendment §B の正の挙動: rag_analyses は disabled でも保存結果を返すため、
#     pageindex_available の gate が rag_analyses 内に残っていないこと
git grep -nE 'rag_analyses|get_analyses' -- src/stock_analyze_system/web/routes/api.py \
  | head -20
```

Expected:
- (a): 3 箇所 — `def _get_pageindex_rag_service(` (定義 1) + `rag_ask` / `rag_index` 内の呼び出し 2
- (b): 2 箇所 — `def _get_rag_service(` (定義 1) + `rag_analyze` 内の呼び出し 1。`rag_ask` / `rag_index` 内に `_get_rag_service(` の呼び出しが残っていたら Step 3.8b (b) の置換漏れ
- (c): `rag_analyses` 内に `pageindex_available` が出現しないこと (Finding 1 round 2 対応)。`if services.rag_service is None: return []` の defense-in-depth 1 行のみ。`get_analyses` 呼び出しが disabled gate 無しで実行されていること

endpoint 呼び出しだけを検出したい場合は `git grep -nE '^\s*rag\s*=\s*_get_(pageindex_)?rag_service'` のように代入パターンで grep する。

- [ ] **Step 5.5: integration / E2E (手動 verification)**

spec §6.7 の追加 gate:

1. **`pageindex.enabled=false` 構成での `run_full_analysis_stream` integration**:

`config/settings.yaml` (またはユーザ環境変数) で `pageindex.enabled: false` に切り替え、worker を起動して seed されている `US_AAPL 10-K` で enqueue → 完走を確認:

```bash
# (a) settings.yaml をバックアップ後 pageindex.enabled=false に切り替え
cp config/settings.yaml /tmp/settings.yaml.bak
# pageindex.enabled の値を false に書き換え (エディタ手作業 OR sed)

# (b) worker と llama-server を別端末で起動 (runbook §1 手順)
scripts/infisical-run uv run stock-analyze worker

# (c) Web で /api/analysis-jobs を POST して US_AAPL 10-K を enqueue
# (auth_client 経由か curl + cookie で)

# (d) ジョブが pending → running → completed まで進むこと、4/4 done を確認
# (data/stock_analyze.db を sqlite3 で確認、または Web UI を見る)

# (e) `pageindex.enabled=false` 設定で `rag ask` 系の API を叩き、
# 503 / PageIndexDisabledError 相当のエラーが返ることを確認

# (f) 終了後 settings.yaml を元に戻す
cp /tmp/settings.yaml.bak config/settings.yaml
```

Expected:
- 定型分析 4/4 が `pipeline='extractor'`、`status='completed'`、`error_details IS NULL` で完了
- `rag ask` 系は **503** が固定 (Round 6 Finding 4 + Round 7 Finding 3 対応): 本 PR で `_get_pageindex_rag_service` と `PageIndexDisabledError` を導入し、`/api/stocks/{id}/rag/ask` および `/api/stocks/{id}/rag/index` は rate limit 消費前に 503 を返す契約。500 が返った場合は実装 bug (helper 切り替え漏れ、または `PageIndexDisabledError` の早期 raise 漏れ) として **失敗扱い**。

  **判定方法 (どちらか 1 つ)**:

  (i) ブラウザ: `WEB_PASSWORD` (infisical 経由、`config/settings.yaml` の `web.port` は 8501 が default — `src/stock_analyze_system/config.py:91`) でログイン後、開発者ツールの Network タブで `POST /api/stocks/US_AAPL/rag/ask` を発火 (例: `/stocks/US_AAPL` 画面で `ask` フォーム送信)。ステータス 503 を確認。

  (ii) curl + session cookie (CLI で済ませたい場合):
  ```bash
  # default port は 8501 (config.py:91)。auth 必須 (auth.py:215 で未認証は 303 で /login)
  PORT=${STOCK_ANALYZE_WEB_PORT:-8501}
  # (a) ログインして session cookie を保存。WEB_PASSWORD は infisical 管理
  scripts/infisical-run sh -c '
    curl -s -c /tmp/sa-cookie.txt -X POST http://127.0.0.1:'"$PORT"'/login \
      -F "password=$WEB_PASSWORD" -o /dev/null -w "login=%{http_code}\n"
  '
  # 期待: login=303 (成功時 / に redirect)

  # (b) 認証済み cookie で /rag/ask を叩く. 期待: HTTP/1.1 503 Service Unavailable
  curl -i -b /tmp/sa-cookie.txt -X POST \
    http://127.0.0.1:"$PORT"/api/stocks/US_AAPL/rag/ask \
    -H 'Content-Type: application/json' \
    -d '{"question":"test","filing_type":"10-K"}' | head -1
  # 結果が 303 (login redirect) なら (a) の cookie 取得に失敗、500 なら本 PR の実装 bug
  ```

  (iii) `tests/unit/web/test_api.py::TestRagApi::test_ask_returns_503_when_rag_disabled` は本 PR で維持される自動 test なので、unit 段階で 503 を確実に固定しておけば手動確認は (i)/(ii) のどちらでも十分。

  500 が返ったら Step 3.8b (a) (b) と Step 3.4 (c) (d) を再点検し、本 PR を blocker 扱いで修正する

2. **E2E filing 1 件で extractor regression なし**:

`pageindex.enabled` を元の値 (例: `true`) に戻した状態で、US_AAPL 2025 10-K の analysis を 1 件流して 4/4 completed を確認 (上記 (b)-(d) と同じ手順)。

Expected: 本 PR 適用前と同じく 4/4 completed、`pipeline='extractor'`、`current_analysis_type IS NULL` で終了。

注意: 本 step は手動 verify が必須。subagent-driven execution の場合は user に依頼する形でよい (LLM サーバが必要なため CI には乗らない)。

- [ ] **Step 5.6: `git diff --check` (whitespace) と commit 順序確認**

Run:
```bash
git diff --check $(git merge-base master HEAD)..HEAD
git log --oneline 742eec2..HEAD
```

Expected:
- `git diff --check`: exit 0 (no whitespace errors)
- `git log`: C1 (`docs(adr)`) → C2 (`fix(api)`) → C3 (`fix(rag)`) → C4 (`docs(runbook)`) の順で 4 commits が並ぶこと

- [ ] **Step 5.7: PR 作成 (オプション、user 指示時のみ)**

PR タイトル: `fix(rag): align ADR-004 scope and PageIndex lifecycle`

PR body の Test plan:

```markdown
## Summary
- ADR-004 末尾に Amendment 2026-05-17 を追記: (A) extractor の対象を SEC 4 種に固定、(B) 定型分析を `pageindex.enabled` から独立化
- `POST /api/analysis-jobs` が非 SEC source / `annual_report` を 422 で拒否、`rag_filing_options` も `_is_adr004_target` helper で default / annual_options の両経路を SEC のみに絞る (A2)
- `RagService` を `pageindex_service: None` 許容に変更し、PageIndex 経路 3 メソッドを `PageIndexDisabledError` でガード。`pageindex_available` property を導入し、web helper を 2 系統 (`_get_rag_service` = `rag_analyze` / `_get_pageindex_rag_service` = `rag_ask` / `rag_index`) に分割。`rag_analyses` は ADR amendment §B のとおり pageindex.enabled=false でも保存済み結果を返す。CLI `cli/rag.py` も `PageIndexDisabledError` を catch して明示 exit (ask/index/status のみ、analyze は disabled でも動作)。`setup_services` / `build_client_bundle` も常時構築に再構成 (A3)
- runbook §1 の llama-server コマンドを ADR-004 検証済み構成 (`--ctx-size 131072 --parallel 1`) に更新、§2.1 の `error_details` 表を `extraction_error` / `failed_types` / legacy `index_build_error` の 3 系統に整理 (A4 + A15)
- worker に `ERROR_DETAILS_KEYS` 定数を導入し、runbook と key 名が同期していることを pytest で static check (A15)

## Test plan
- [x] `pytest tests/unit/{services,web,cli}` (新規 21 件追加 / 3 件削除 + characterization/integration 2 件 modify — 内 2 件は ADR amendment §B の旧仕様で、新仕様 test に置換)
- [x] `pytest tests/unit/characterization tests/integration/test_service_assembly.py::TestRagAssembly` (旧 `rag_service is None` 期待を新契約に置換、Round 6 Finding 1)
- [x] `npm test` (frontend smoke、Round 6 Finding 5)
- [x] `pytest tests/unit` 全体で回帰なし
- [x] 既存 web monkeypatch 13 箇所のうち 9 件 (TestRagApi 7 + TestRagFilingId 2、URL が `/rag/ask` / `/rag/index`) を `_get_pageindex_rag_service` に切り替え、4 件 (TestRagApi 2 + TestRagFilingId 2、URL が `/rag/analyze`) は据え置き
- [x] 維持される 503 契約 2 件 (`test_ask_returns_503_when_rag_disabled` / `test_index_rag_disabled_does_not_consume_rate_limit`) が `_get_pageindex_rag_service` 経由で引き続き pass
- [x] 新仕様 2 件 (`test_analyze_streams_when_pageindex_disabled` / `test_analyses_returns_persisted_results_when_pageindex_disabled`) で disabled 時の定型分析動作を回帰防止
- [x] grep gate: ADR amendment 存在 / runbook の `--ctx-size 131072` `--parallel 1` `--jinja` `--n-gpu-layers 99` 各別の grep / 旧 `ctx-size 32768` `parallel 4` literal 不在 / `ANALYSIS_FILING_TYPES` から `ANNUAL_REPORT` 不在
- [x] `git diff --check` clean
- [ ] **手動 E2E**: `pageindex.enabled=false` で US_AAPL 10-K の 4/4 analysis 完走 + `rag_analyses` で保存済み結果が見える + `rag ask` が 503
- [ ] **手動 E2E**: `pageindex.enabled=true` で US_AAPL 10-K の 4/4 analysis regression なし

## ADR
`docs/adr/004-sec-filing-section-extractor.md` に Amendment 2026-05-17 として追記 (新規 ADR は作らない)。
```

PR 作成は user の指示があれば実施。それまでは local branch に commit 4 件積んだ状態で待機。

---

## Self-review checklist

- **Spec coverage** (spec §6):
  - ✅ §6.3 C1 (ADR amendment): Task 1 で `### Amendment 2026-05-17` セクションを追記
  - ✅ §6.4 C2 (A2 — API/UI `annual_report` 除外): Task 2.4-2.6 で `ANALYSIS_FILING_TYPES` 変更 + `_is_adr004_target` helper + `rag_filing_options` の default / annual_options 両 filter + `create_job` validation
  - ✅ §6.5 C3 (A3 — `pageindex.enabled=false` でも RagService 構築): Task 3.4-3.8h で `PageIndexDisabledError` + `pageindex_available` property、`build_index` / `ask_question` / `get_index_status` ガード、`build_client_bundle` / `setup_services` 再構成、worker の `rag is None` 削除、web helper 2 系統分割 (`_get_rag_service` = analyze、`_get_pageindex_rag_service` = ask / index) + helper 直接 test 3 件 (Step 3.8b (d) Round 6 Finding 3)、`rag_analyses` を ADR amendment §B 通り disabled でも保存結果を返す形に、`rag_history` / `rag_filing_options.default` を `pageindex_available` 判定に揃え、旧 test 2 件を新仕様 test 2 件で置換、CLI `cli/rag.py` の `handle()` を `try / except PageIndexDisabledError` でラップして ask/index/status の明示 exit + analyze は disabled でも動作 (Step 3.8g 新規)、`test_rag_cli.py` に 4 件追加、Step 3.8h で characterization/integration の旧契約 test 2 件を rename + 反転 (Round 6 Finding 1)
  - ✅ §6.6 C4 (A4 + A15 — runbook + static check): Task 4.3 で `ERROR_DETAILS_KEYS`、Task 4.5 で runbook §1、Task 4.6 で runbook §2.1、Task 4.7b で runbook §3.3 整合 (Round 6 Finding 6)、Task 4.1 で test
  - ✅ §6.7 merge gate (unit + integration + E2E + npm test): Task 5.1-5.6 でカバー。Step 5.2b で `npm test` を gate に追加 (Round 6 Finding 5)
- **Review findings (2026-05-18 round 1) の反映**:
  - ✅ Finding 1 (default も SEC filter): Task 2.2 に `test_options_default_falls_back_to_sec_filing_when_latest_is_edinet`、Step 2.5 で `_is_adr004_target` を default 探索全段 (`get_latest_indexed` / `list_by_recency` / fallback) に適用、`get_latest_any_type` 廃止
  - ✅ Finding 2 (PageIndex 503 変換を PR2 内で): `pageindex_available` property + 2 系統の web helper + `rag_analyses` / `rag_history` 書き換えを C3 commit に含める (Step 3.4 / 3.8b-e)
  - ✅ Finding 3 (Task 4.4 の expected が成立しない): Step 4.4 を「依然 fail を確認」に書き換え、Step 4.6 の runbook 更新後に Step 4.8 で pass を確認する 4 step フロー
  - ✅ Finding 4 (Step 5.3 grep multi-line 非対応): `--ctx-size` / `--parallel` / `--jinja` / `--n-gpu-layers` を別 grep に分割
- **Review findings (2026-05-18 round 8) の反映**:
  - ✅ Finding 1 (deprecated /rag/analyze 説明が stream 実装とズレ): Task 2 冒頭 Scope clarification を再訂正。`failed_types` は worker 集約概念で stream には現れない事実に合わせ、実際の per-type 失敗時は `_process_one` (`rag_service.py:368-377`) が `_PerTypeOutcome(kind="error", message="ファイリングから章テキストを抽出できませんでした")` を返し、stream へは analysis_type 単位の **error event** が流れる + 最後に `{"event": "complete"}` で締める、と書き直し
  - ✅ Finding 2 (Step 4.7b 導入説明の古い誤りが残る): 導入段落から「step 3 の `reasoning_content` 暴走自体が定型分析経路で起こり得ない」を削除し、(a) 章抽出段では LLM を通らないので暴走しない、(b) step 3 は LLM 呼び出しなので検証済み構成 + `_is_empty_llm_response` ガードの 2 層で扱う、という構造を明示する説明に置換
  - ✅ Finding 3 (Step 4.9 期待文が旧方針): §3.3 の変更内容を「`ask_question 経路のみ に限定`」から「定型分析の章抽出段は LLM 非依存 + step 3 は LLM 呼び出し」「ask_question は PageIndex-selected context」「失敗時切り分けは ctx-size + prompt mismatch / §3.2 の 2 系統」に展開
  - ✅ Finding 4 補足 (ask_question の context 表現が強すぎ): Step 4.7b 新本文の「章丸ごとを context に積む」を「PageIndex-selected context (tree search で選ばれたノード群、`pageindex/service.py:445-470` の `selected_nodes`)」に弱め、選定ノード次第で同等のトークン規模に膨らみ得る、と表現を実装に整合
- **Review findings (2026-05-18 round 7) の反映**:
  - ✅ Finding 1 (runbook §3.3 新文言が実装と矛盾): Step 4.7b の段落を「定型分析の章抽出は LLM 非依存だが step 3 (`_analyze_section`) は抽出済み章本文を LLM に prompt 連結して渡す」「ADR-004 検証済み構成 (`--ctx-size 131072 --parallel 1 --jinja`) では runaway 再現せず、`_is_empty_llm_response` ガードが fail を隠さない」に書き直し。失敗時切り分けも「定型分析 per-type 失敗 = ctx-size 構成 + prompt mismatch」「`ask_question` = §3.2」に分離。grep verification も新文言にあわせて更新 (`抽出済み章本文を .*LlmClient\.completion` と `step3-reasoning-runaway-verification` 参照)
  - ✅ Finding 2 (TestRagHelperSplit の MagicMock import 前提が間違い): test_api.py line 4 が `AsyncMock` のみ import している事実に合わせ、Step 3.8b (d) の snippet を `SimpleNamespace(pageindex_available=False)` ベースに書き換え (`SimpleNamespace` は test_api.py line 3 で既存 import)。import 注意書きも「`MagicMock` は test_api.py で未 import」「`HTTPException` は関数内ローカル import (fixture と同じパターン)」に更新
  - ✅ Finding 3 (curl 例の port/auth が抜けている): Step 5.5 Expected の判定方法を 3 案併記に拡張 — (i) ブラウザ + DevTools、(ii) `scripts/infisical-run` 経由で session cookie を取得して curl、(iii) 自動 test (`test_ask_returns_503_when_rag_disabled`) のみで済ます。port は `config/settings.yaml` default の 8501 (`config.py:91`) + 環境変数 `STOCK_ANALYZE_WEB_PORT` を使い、auth.py:215 の 303 redirect を踏まえた cookie 取得手順を明示
  - ✅ Finding 4 (F2 の「UI 上は失敗ジョブ」が deprecated /rag/analyze には当たらない): Task 2 冒頭の Scope clarification ブロックを訂正。deprecated route は AnalysisJob を作らず NDJSON stream を直接返す事実 (`api.py:267-282`) に合わせ、「stream に done/complete event が並ぶ + UI 呼び出し元 JS が読む責務」「CLI は stdout に空結果 + 警告ログ」と弱めた表現に更新
- **Review findings (2026-05-18 round 6) の反映**:
  - ✅ Finding 1 (characterization/integration test の旧契約残り): 新規 Step 3.8h を追加し、`tests/unit/characterization/test_container_assembly.py::test_rag_service_none_when_pageindex_disabled` と `tests/integration/test_service_assembly.py::TestRagAssembly::test_non_rag_features_work_when_rag_disabled` をリネーム + assertion 反転 (`is None` → `is not None` + `pageindex_available is False`)。Step 3.11 commit の git add 対象に追加、Step 5.1 / 5.2 にも反映、Files table にも 2 行追加
  - ✅ Finding 2 (deprecated rag/analyze と CLI rag analyze の SEC 4 種 validation): Task 2 冒頭に Scope clarification ブロックを追加し、deprecated route と CLI の validation は本 PR では out-of-scope として明文化 (PR3 の A5 `ExtractionInputMissingError` 導入と同時に extractor 入口で `_is_adr004_target` 判定を入れる方針)。Self-review §6.9 out-of-scope にも明示
  - ✅ Finding 3 (新仕様 test が helper の実挙動を検証できていない): Step 3.8b に (d) 節を追加し、`TestRagHelperSplit` クラスで `_get_rag_service` / `_get_pageindex_rag_service` を **直接呼ぶ** 単体 test を 3 件追加。Step 3.8c の `monkeypatch.setattr(api_module, "_get_rag_service", ...)` 経由 test だけだと helper 本体が旧仕様のまま (`pageindex_available` を見て 503 を投げる) でも偽 pass する穴を塞ぐ。合計 18 → 21 件追加に更新
  - ✅ Finding 4 (Step 5.5 の 500 許容が C3 契約と矛盾): Step 5.5 Expected の `rag ask` 系記述を「500 は失敗扱い、503 が固定契約」に書き換え、curl 例と回帰時の再点検手順 (Step 3.8b (a)(b) と Step 3.4 (c)(d)) を追加
  - ✅ Finding 5 (npm test が PR2 gate から抜けている): Step 5.2b を追加し `npm test` を unit gate に組み込み。spec §1 line 30 (PR ごとに npm test 要求) と spec §10 line 1136 の最終 regression に整合
  - ✅ Finding 6 (runbook §3.3 の旧説明が残る): 新規 Step 4.7b を追加し、`docs/analysis-jobs-runbook.md:120` の `ADR-004 §4.5 のリスク` 段落を「ask_question 経路のみ発火、定型分析側は extractor 経由で per-type prompt 限定なので非該当」に書き換え。Step 4.9 git diff 期待にも §3.3 を 3 箇所目として追加
- **Review findings (2026-05-18 round 5) の反映**:
  - ✅ Finding 1 (CLI rag.py の disabled 経路が未対応): 新規 Step 3.8g を追加し、`cli/rag.py:64-83` の `handle()` を `try / except PageIndexDisabledError` でラップ。ask / index / status は明示 exit 1 (Web 側の 503 と等価)、analyze は ADR amendment §B 通り disabled でも動作。`tests/unit/cli/test_rag_cli.py` に 4 件追加。Step 3.11 commit に `cli/rag.py` / `test_rag_cli.py` を含める
  - ✅ Finding 2 (Step 3.3 expected が現実と不一致): Step 3.1 の `test_run_full_analysis_works_without_pageindex` / `test_run_full_analysis_stream_works_without_pageindex` の先頭に `assert service_no_pageindex.pageindex_available is False` を追加し、property 未実装時に確実に red になるようにした。Step 3.3 expected を「型ヒントだけなので `RagService(pageindex_service=None)` は構築できるが、property が無い / `_pageindex.get_or_create_index` 呼び出しで AttributeError」と書き直し、定型分析 2 件が偶発 pass する Round 5 のリスクを排除
  - ✅ Finding 3 (件数不整合): CLI test 4 件追加を反映して **18 件追加 / 3 件削除** に統一 (Step 5.1 / PR body / Step 3.8e 直下の合計欄)
- **Review findings (2026-05-18 round 4) の反映**:
  - ✅ Finding 1 (monkeypatch 数の前提が実コードと不一致): Step 3.8e の table を 13 箇所に更新し、`TestRagFilingId` の 3 件 (line 561 analyze 据え置き / 627 ask 切り替え / 656 index 切り替え) を表に追加。切り替え 9 件 (ask 5 + index 4) / 据え置き 4 件 → Step 3.8c の新規 analyze test 1 件追加後は 14 箇所 (据え置き 5 件) として明示
  - ✅ Finding 2 (Step 3.8f が TestRagFilingId をカバーしない): Step 3.8f のコマンドに `tests/unit/web/test_api.py::TestRagFilingId` を追加。検証文言に「TestRagFilingId の切り替え漏れがあると本 step でしか fail を捕捉できない」と注記
  - ✅ Finding 3 (grep が multi-line monkeypatch.setattr を拾えない): Step 3.8e の grep を `git grep -n '"_get_rag_service"' -- tests/unit/web/test_api.py` (引数文字列で grep) に置換。これにより複数行に分かれた `monkeypatch.setattr(\n    api_module, "_get_rag_service", ...)` も漏れなく検出できる
- **Review findings (2026-05-18 round 3) の反映**:
  - ✅ Finding 1 (Step 3.8e で既存 test の monkeypatch 切り替えが必要): Step 3.8e / 3.8f で endpoint 別の monkeypatch 切り替えと検証を明示。初期案の 10 箇所 / TestRagApi のみ検証は Round 4 で supersede し、現行 13 箇所 (切り替え 9 / 据え置き 4、Step 3.8c 後は 14 箇所) + `TestRagFilingId` 検証に更新済み
  - ✅ Finding 2 (新規 test の import パスが placeholder): `from stock_analyze_system.models.company_analysis import CompanyAnalysis, PIPELINE_EXTRACTOR` で確定 (正本は line 8 / 11)
  - ✅ Finding 3 (Step 5.4 grep 期待値が定義行も拾う): 期待値を 3 / 2 に修正、定義 + 呼び出しの内訳を明記、endpoint 呼び出しのみを grep する代替コマンドも追加
  - ✅ Finding 4 (ADR amendment §A の "5 種" 表記が enum と不一致): 6 種 (`10-K` / `10-Q` / `20-F` / `6-K` / `annual_report` / `quarterly_report`) として明示、EDINET 側の除外対象に `quarterly_report` も含めた
- **Review findings (2026-05-18 round 2) の反映**:
  - ✅ Finding 1 (pageindex_available gate が広すぎ): web helper を 2 系統に分割 (`_get_rag_service` = `rag_analyze`、`_get_pageindex_rag_service` = `rag_ask` / `rag_index`)。`rag_analyses` は ADR amendment §B 通り disabled でも保存結果を返す。旧 test 2 件 (`test_analyze_returns_503_when_rag_disabled` / `test_analyses_returns_empty_when_rag_disabled`) を削除、新仕様 test 2 件 (`test_analyze_streams_when_pageindex_disabled` / `test_analyses_returns_persisted_results_when_pageindex_disabled`) で置換 (Step 3.8b / 3.8c / 3.8e)
  - ✅ Finding 2 (default fallback test が偽 pass): EDINET 側 fixture を `raw/filing.pdf` から `converted.pdf` 直配置に修正 (Step 2.2、`filing_content_exists` が `converted.pdf` を見るため)
  - ✅ Finding 3 (Step 2.5 の code/注意 矛盾): Step 2.5 code block を C2 commit 用 (`services.rag_service is not None`) に明示、C3 差分は Step 3.8d でのみ pageindex_available に置換すると明示。Step 3.14 への誤参照 (存在しない step) を Step 3.8d に修正
  - ✅ Finding 4 (runbook grep と Step 4.5 本文 矛盾): Step 4.5 の説明文から旧構成の literal flag 値 (`--ctx-size 32768 --parallel 4`) を削除し、「より小さい ctx-size や多い parallel slot」という説明に変更
  - ✅ Finding 5 (Step 3.8e の test class 名が不正): `TestRagAsk` / `TestRagIndex` / `TestRagAnalyze` は架空クラス。実際は `TestRagApi::...` (test_api.py:256) のみ。node id を `TestRagApi::test_xxx` 形式に修正
  - ✅ Finding 6 (件数の不整合): Step 5.1 / PR body / Self-review checklist の追加件数を 18 件、削除件数を 3 件に統一 (Round 5 の CLI test 4 件追加を含む)
- **Placeholder scan**: 各 step に具体的なファイルパス・行番号・コード・コマンド・期待出力を記載。TBD / `add appropriate ...` / 「以下と同様」のような placeholder なし
- **Type consistency**: `PageIndexDisabledError` / `pageindex_available: bool` (property) / `ERROR_DETAILS_KEYS: frozenset[str]` / `ADR004_SUPPORTED_FILING_TYPES: frozenset[FilingType]` / `_ADR004_TARGET_FILING_TYPES: frozenset[str]` / `_is_adr004_target(filing) -> bool` の 6 シンボルが新規。`_ADR004_TARGET_FILING_TYPES` は web/routes/api.py で `_is_adr004_target` 内のみ使用、`ADR004_SUPPORTED_FILING_TYPES` は web/routes/analysis_jobs.py で `create_job` validation のみ使用 — 2 つの定数は別ファイルで同等内容を保持するが、参照範囲が異なるため重複しない (DRY を破るほどではない)
- **ADR compliance**: 本 PR の C1 が ADR amendment そのもの。C2 / C3 / C4 の挙動変更はすべて amendment §A / §B の文面に直接対応する (新たな architectural decision を導入していない)
- **Out of scope (spec §6.9 + 本 plan Round 6 追加分) の遵守**:
  - EDINET PDF 用 extractor 実装は触らない ✓
  - `pipeline='extractor'` filter の read model 側適用 (PR5 の A12) は触らない ✓
  - worker の `current_analysis_type` clear (PR3 の A14) は触らない ✓
  - **deprecated `POST /api/stocks/{id}/rag/analyze` と CLI `rag analyze` の filing_type validation** (Round 6 Finding 2): 削除予定 route の延命と extractor/CLI への touch 範囲拡大を避けるため、本 PR では入れず PR3 の A5 (`ExtractionInputMissingError` 導入) と同時に extractor 入口で `_is_adr004_target` 判定を入れる方針。soft fail (`failed_types` 4 件) で済むためデータ破壊リスクなし ✓
- **未確定事項 (spec §6.8) の解決**:
  - (1) `Filing.source` 列の存在 → 既存 (`models/filing.py:13`)。本 plan は `source` 列を前提に組む
  - (2) runbook §3.1 / §3.2 の指示妥当性 → Task 4.7 で確認、本 PR では touch 不要と判断
  - (3) legacy `index_build_error` の再 enqueue 運用判断 → runbook 表に「再 enqueue で新形式に再記録」と書き切り、migration script は本 PR 範囲外
- **Commit order**: C1 (ADR amendment) → C2 (API) → C3 (RagService DI + web `pageindex_available` 切替 + `rag_filing_options.default` の `pageindex_available` 条件化) → C4 (runbook + static check) の順序が spec §6.2 と一致。C3 で削除した `test_run_one_job_rag_disabled` は C3 commit と同一に含める (実装と test の同期維持)。C2 で書いた `services.rag_service is not None` 表記は C3 commit で `pageindex_available` 条件に書き換える (Step 3.8c) — C2 commit 単独でも test は pass する (pageindex_available property がまだ無い段階)
- **PR1 から得た知見 (prompt §)**:
  - pytest 起動は `scripts/infisical-run uv run pytest <files> -q` ✓
  - merge gate の grep は `git grep ... || test $? -eq 1` パターン ✓
  - commit message は HEREDOC + `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>` trailer ✓
  - TDD 粒度 (失敗テスト → fail 確認 → 最小実装 → pass 確認 → 追加 → pass → commit) を Task 2 / 3 / 4 で踏襲 ✓
  - レビュー minor (stale 行番号 / 履歴コメント) を含めない: Task 3.4 / 3.6 の rag_service / container 変更コメントは「ADR-004 amendment §B により」のような **永続的に意味を持つ理由付け** に統一し、「PR2 C3 で変更」「2026-05-17 の amendment 後」のような refactoring-finding 由来の語は避けた
