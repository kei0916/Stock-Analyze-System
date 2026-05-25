# 定型分析ワーカーの別プロセス分離 — 設計仕様

- **日付**: 2026-05-11
- **対象ブランチ**: `feat/background-analysis-queue`
- **背景**: 定型分析実行中に Web UI のナビゲーションが長時間ブロックされる問題の根本対処。

## 1. 問題と原因

定型分析（`POST /api/analysis-jobs` → `AnalysisQueueService._worker_loop` → `RagService.run_full_analysis_stream`）が走ると、他画面への遷移や API ポーリングがすべて停止する。

調査の結果、PageIndex ライブラリ (`<pageindex-repo>/pageindex/page_index.py`) の `tree_parser` (async) が、内部で **同期関数** を `await` なしで直接呼んでいる:

- `check_toc(page_list, opt)` (line 1168) — sync。内部で `toc_extractor` → `llm_completion` (sync `litellm.completion`)。
- `process_toc_with_page_numbers(...)` (line 1073) / `process_no_toc(...)` (line 1077) / `process_toc_no_page_numbers(...)` (line 1075) — いずれも sync。
- これらの中で `toc_transformer`、`toc_index_extractor`、`generate_toc_init`、`generate_toc_continue`、`add_page_number_to_toc`、`process_none_page_numbers` (全 sync) が `llm_completion` を複数回呼び、その間 **asyncio イベントループを丸ごとブロック**。

`request_timeout=600` (settings.yaml) のため 1 呼び出しで最長 10 分の停止。シングルワーカー uvicorn 構成のため、Web ハンドラもキューワーカーも同一イベントループにいて、停止が UI に直撃する。

「キュー化」しても根本解決にはならない（同一プロセス・同一ループのため）。同プロセスでの修正は PageIndex 内部の同期コード排除が必要だが、これは上流依存が多く影響範囲が広いため、**今回はプロセス分離による隔離を採用**する。

## 2. アーキテクチャ

```
┌──────────────────────┐       ┌────────────────────────┐
│  stock-analyze serve │       │  stock-analyze worker  │
│  (web プロセス)       │       │  (worker daemon)       │
│                      │       │                        │
│  FastAPI + uvicorn   │       │  AnalysisWorker        │
│  - 既存ルート全部     │       │  - poll DB every 2s    │
│  - AnalysisQueue     │       │  - run_one_job()       │
│    (enqueue/list/    │       │    -> RagService       │
│     cancel-pending/  │       │       .run_full_       │
│     dismiss のみ)    │       │        analysis_stream │
│                      │       │                        │
│  worker_loop は除去  │       │  signal handler:       │
│                      │       │  SIGTERM/SIGINT で      │
│                      │       │  in-flight job 完了    │
│                      │       │  待機後に exit         │
└────────┬─────────────┘       └────────┬───────────────┘
         │                              │
         │   read/write                 │   read/write
         └──────────────┬───────────────┘
                        ▼
               ┌──────────────────┐
               │ data/stock_      │
               │ analyze.db       │
               │ (SQLite + WAL +  │
               │  busy_timeout)   │
               │                  │
               │ - analysis_jobs  │
               │ - analyses       │
               │ - document_      │
               │   indices        │
               │ - rag_qa_history │
               └──────────────────┘
```

### 設計原則

- **既存 SQLite DB をそのまま IPC 兼キューとして使用**（追加ブローカーなし）。WAL は既設、`PRAGMA busy_timeout=5000` を追加。
- **Web プロセスはジョブを enqueue するだけ**。LLM/PageIndex を import すらしない経路にする。
- **新設 `stock-analyze worker` CLI が常駐デーモン**。手動起動。起動時に `reset_running_to_failed` でクラッシュ復旧、その後 2 秒ポーリングでジョブを取り、`RagService.run_full_analysis_stream` を消費する。
- **キャンセルは pending のみ**（既存挙動）。running 中はキャンセル不可、ワーカーが SIGTERM を受けても in-flight ジョブを完了させてから exit。

## 3. コンポーネント分割

### 3-1. `AnalysisQueueService`(`services/analysis_queue.py`) — 薄化

責務: **Web プロセスが触る範囲のみ**。

**残す**:
- `enqueue(company_id, filing_id) -> (job, is_new)`
- `cancel(job_id)` — pending → cancelled のみ。running 分岐は削除。
- `dismiss(job_id)`
- `get_status(job_id)`
- `list_jobs(...)`
- `_enqueue_lock` フィールド（同一プロセス内の race 防止）

**削除**:
- `start()` / `stop()`
- `_worker_loop` / `_dequeue_next` / `_run_job` / `_execute_with_status`
- `_worker_task` / `_shutdown_event` / `_wakeup_event` / `_running_tasks`
- `_clients` フィールド（ワーカー専用）

`cancel(running)` は API 仕様維持のため `job` 返却（クライアントには「変化なし」として見える）。

### 3-2. `AnalysisWorker`(`services/analysis_worker.py`) — 新規

責務: **CLI ワーカー専用**。

```python
class AnalysisWorker:
    def __init__(
        self,
        session_factory,
        config,
        clients: ClientBundle,
        *,
        poll_interval: float = 2.0,
    ):
        ...

    async def run_forever(self) -> None:
        """起動時 reset_running_to_failed → ポーリング → run_one_job ループ。
        SIGTERM/SIGINT で _shutdown 立てて in-flight 完了後 exit。"""

    async def run_one_job(self) -> bool:
        """dequeue_next で1件取り、_run_job + status反映。取得できなければ False。
        テストから直接呼べる単位。"""

    async def _run_job(self, job: AnalysisJob) -> None:
        """既存の _run_job をそのまま移設。"""
```

**シャットダウン挙動**:
- `signal.signal(SIGTERM/SIGINT, ...)` で `_shutdown` フラグを立てる。
- ポーリングループはフレーム冒頭で `_shutdown` をチェック、立っていたら exit。
- in-flight ジョブはキャンセルしない。完了まで待ち、status 反映後に exit。
- 強制 kill された場合は running のまま残り、次回起動時の `reset_running_to_failed` で failed に倒す。

### 3-3. `cli/worker.py` — 新規

```python
def register_parser(subparsers):
    p = subparsers.add_parser("worker", help="バックグラウンド分析ワーカー起動")
    p.add_argument("--poll-interval", type=float, default=2.0)
    p.set_defaults(handler=handle)

async def handle(args, config: AppConfig):
    engine = await create_db_engine(config.database.path)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    clients = build_client_bundle(config)
    worker = AnalysisWorker(session_factory, config, clients,
                            poll_interval=args.poll_interval)
    try:
        await worker.run_forever()
    finally:
        await dispose_clients(clients)
        await engine.dispose()
```

### 3-4. `shared/clients.py` — 新規

`web/dependencies.py:AppState.create` / `dispose` 内のクライアント構築/破棄を切り出し、Web と Worker の両方が使う:

- `build_client_bundle(config) -> ClientBundle`
- `dispose_clients(bundle) -> None`

### 3-5. Web 側の変更

- `web/app.py` の `lifespan` から `state.analysis_queue.start()` / `stop()` 呼び出しを削除。
- `web/dependencies.py:AppState.create` で `AnalysisQueueService` 構築は残すが `clients` 引数を不要に。
- 既存 `/api/analysis-jobs` ルート (POST/GET/DELETE/dismiss) は **無変更**。

### 3-6. `models/base.py` の補強

```python
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()
```

両プロセスからの並行ライト時の即 lock エラーを最大 5 秒の待機に変換する。

## 4. データフローとエラーハンドリング

### 4-1. 正常系フロー

1. ユーザーが「決算分析🔍」押下
2. ブラウザ → `POST /api/analysis-jobs` (Web プロセス)
3. Web: `AnalysisJobRepository.create` で pending INSERT → 201 + `job_id` 返却 (数 ms)
4. ブラウザ: 5 秒間隔で `GET /api/analysis-jobs/{id}` をポーリング (`pollJob`)
5. 別プロセスの worker: 2 秒間隔で DB ポーリング → 最古の pending を `dequeue_next` で `running` に
6. worker: `RagService.run_full_analysis_stream(filing)` を消費しつつ `update_progress` で `progress_current` / `current_analysis_type` を更新
7. worker: 完了時に `update_status(completed)`、失敗時に `update_status(failed, error_details=...)`
8. ブラウザ: ポーリングで `completed` 検知 → `GET /api/stocks/{id}/rag/analyses` で結果取得 → 表示

**初動遅延**: 最大 2 秒（ワーカー idle 時）。連続ジョブ間遅延: 0 秒。

### 4-2. エラーハンドリング

**(1) ワーカー未起動**
- pending が `started_at=NULL` のまま 30 秒経過 → トップバーバッジを赤系トーン + テキスト「分析ワーカーが応答していません」に切り替え (詳細はセクション 5)。
- 強制ではない。`running` が 1 件でもあれば警告を出さない。

**(2) ジョブ実行中の例外**
- `AnalysisFailedError` (一部タイプの失敗) → `status=failed`, `error_details.failed_types`
- 他の `Exception` → `status=failed`, `error_details.reason`
- `asyncio.CancelledError` → `status=cancelled` (worker 強制終了時の安全網)

**(3) ワーカー強制終了 (SIGKILL/クラッシュ)**
- 該当ジョブは `status=running` のまま残置。
- 次回 `stock-analyze worker` 起動時の `reset_running_to_failed("Worker restarted while running")` で failed に倒す。
- UI から「失敗 → 再実行」で復帰可能（既存の rerun ボタン）。

**(4) SQLite write contention**
- WAL モードで read は競合しない。
- write は `busy_timeout=5000` で 5 秒待機 → タイムアウト時のみ `OperationalError`。
- 既存の `IntegrityError` ハンドリング (`enqueue` の race 対応) は維持。

**(5) 古い pending ジョブ**
- 制限なし。FIFO で順次消化。TTL は今回未実装。

### 4-3. 観測性

- ワーカーは既存 `logger` 経由で `logger.info("job %d completed in %.1fs", ...)` 等を吐く。
- 既存 `data/logs/stock_analyze.log` に流れるよう `logging_config.py` を両プロセスで共有。

## 5. 「分析中」可視化 UI

### 5-1. トップバーバッジ（常時表示）

`templates/_topbar.html` に追加:

```html
<a class="topbar__badge" href="/" id="analysis-status-badge" hidden
   aria-live="polite">
  <span class="topbar__badge-dot"></span>
  <span class="topbar__badge-text">—</span>
</a>
```

- **配置**: トップバー右側。
- **挙動**: pending/running 1 件以上で表示。
- **文言**:
  - pending のみ: `待機中 1件`
  - running あり: `分析中 1件 · 3分48秒` (最古 running の経過時間)
  - 複数: `分析中 2件 · 最長 5分12秒`
- **アニメーション**: `topbar__badge-dot` に CSS `@keyframes pulse` (1.6s 周期)。
- **クリック先**:
  - 件数 = 1 → `/stocks/{company_id}#tab=analysis`
  - 件数 ≥ 2 → `/`（ダッシュボードのキューパネル）

### 5-2. ブラウザタブタイトル

`document.title` 先頭に `(N) ` を付与。ベースタイトルを初回保存 (`window.__baseTitle`)、ポーリング毎に更新、0 件で復帰。

### 5-3. 完了通知 (Browser Notification API)

**許可フロー**:
- 「決算分析🔍」ボタンクリックハンドラ内で **`POST /api/analysis-jobs` を発火する前に** `Notification.permission === "default"` であれば `Notification.requestPermission()` を呼ぶ（ブラウザの user-gesture 要件を確実に満たすため、fetch の Promise resolve 後ではなく click frame 中に同期的にトリガする）。
- ページロード時には聞かない。
- `denied` 時は二度と聞かない（`sessionStorage.notification_denied=true`）、バッジ + タイトルのみで動作続行。

**発火フロー**:
- 共通 `analysisQueueState` モジュールが「前回 running だったジョブ ID 集合」を保持。
- 今回ポーリングで `completed` / `failed` に遷移した job_id があれば `Notification` 発火:
  - 成功: `{company_name} の決算分析が完了しました`
  - 失敗: `{company_name} の決算分析が失敗しました`
- `onclick`: `window.focus()` 後に `/stocks/{company_id}#tab=analysis` に遷移。
- 同一 job_id は **1 度だけ発火**（`sessionStorage` で「通知済み job_id」を保持）。

**フォールバック**:
- `Notification.permission !== "granted"` の場合は何もしない。
- `window.Notification` 未定義の古いブラウザでも壊れない。

### 5-4. 既存実装との関係

- ダッシュボードのキューパネル (`#llm-queue-panel`) はそのまま残す。
- 重複ポーリングを避けるため、両者は **共通の `pollAnalysisJobs()` モジュール** から状態を購読する形にリファクタ。
- 個別ジョブの詳細ポーリング (`pollJob`) は引き続きジョブ詳細を 5 秒間隔で叩く（別経路）。

### 5-5. ワーカー未稼働バナー

共通 `analysisQueueState` から判定:
- pending の最古 `created_at` から 30 秒経過 + `started_at` がすべて NULL → バッジ赤化、ダッシュボードのキューパネル下に詳細メッセージ。

## 6. テスト戦略

### 6-1. テストピラミッドと範囲

```
                  Manual QA Checklist (UI/Notification API)
                /
              E2E / Acceptance      (3-5 ケース、TestClient + worker タスク)
            /
       Integration                  (10-15 ケース、実 SQLite + worker lifecycle)
     /
Unit + Property tests               (50+ ケース、in-memory SQLite + mock)
```

CI で自動化する範囲は **Unit / Integration / E2E まで**。Manual QA は本仕様の checklist を PR description で結果報告。

### 6-2. テストインベントリ

#### `tests/unit/services/test_analysis_queue.py` (改修)

| # | テスト名 | 検証内容 |
|---|---|---|
| Q01 | `test_enqueue_creates_pending_when_no_active` | 新規 enqueue → pending、is_new=True |
| Q02 | `test_enqueue_returns_existing_pending` | 同 (company, filing) 2 回目 → 既存返却、is_new=False |
| Q03 | `test_enqueue_returns_existing_running` | running 中 → 既存返却 |
| Q04 | `test_enqueue_dismisses_past_failed` | 過去 failed が auto-dismiss、新 pending 作成 |
| Q05 | `test_enqueue_dismisses_past_cancelled` | 過去 cancelled も auto-dismiss |
| Q06 | `test_enqueue_integrity_error_returns_existing` | INSERT race を `IntegrityError` でシミュレート |
| Q07 | `test_enqueue_concurrent_calls_serialize` | 同 (company, filing) を gather で 10 並行 → pending 1 件のみ |
| Q08 | `test_cancel_pending_transitions_to_cancelled` | pending → cancelled |
| Q09 | `test_cancel_running_returns_unchanged` | running → 変更なし |
| Q10 | `test_cancel_completed_returns_unchanged` | terminal は no-op |
| Q11 | `test_cancel_nonexistent_returns_none` | 不在 → None |
| Q12 | `test_dismiss_failed` / `test_dismiss_cancelled` / `test_dismiss_completed` | 各 terminal で `dismissed_at` セット |
| Q13 | `test_dismiss_pending_raises_value_error` | pending dismiss は ValueError |
| Q14 | `test_dismiss_running_raises_value_error` | running も ValueError |
| Q15 | `test_dismiss_nonexistent_returns_none` | 不在 → None |
| Q16 | `test_get_status_returns_latest` | UPDATE 後の populate_existing 値 |
| Q17 | `test_list_jobs_filters_combinations` | parametrize 8 ケース |
| Q18 | `test_list_jobs_respects_limit_and_order` | created_at DESC + limit |

#### `tests/unit/services/test_analysis_worker.py` (新規)

| # | テスト名 | 検証内容 |
|---|---|---|
| W01 | `test_run_one_job_returns_false_when_no_pending` | キュー空 → False |
| W02 | `test_run_one_job_dequeues_oldest_pending` | FIFO 順 |
| W03 | `test_run_one_job_completes_successfully` | 全タイプ done → status=completed |
| W04 | `test_run_one_job_handles_cached_event` | 全タイプ cached → completed (LLM 呼び出し 0) |
| W05 | `test_run_one_job_partial_failure` | 1 件 error → status=failed、failed_types に該当 |
| W06 | `test_run_one_job_total_failure` | 全 error → status=failed、failed_types 4 件 |
| W07 | `test_run_one_job_raises_when_filing_missing` | filing None → status=failed、reason 含む |
| W08 | `test_run_one_job_raises_when_rag_disabled` | rag_service None → status=failed |
| W09 | `test_run_one_job_unexpected_exception` | RuntimeError → status=failed、reason |
| W10 | `test_run_one_job_progress_persisted_between_events` | 中間スナップショット可能 |
| W11 | `test_run_one_job_session_commits_per_event` | phase 毎に commit (長時間 read tx 回避保証) |
| W12 | `test_init_with_custom_poll_interval` | poll_interval が sleep 間隔に反映 |

#### `tests/integration/test_analysis_worker_lifecycle.py` (新規)

| # | テスト名 | 検証内容 |
|---|---|---|
| L01 | `test_run_forever_resets_stale_running_at_startup` | 起動前 RUNNING 2 件 → 両方 failed |
| L02 | `test_run_forever_processes_queued_jobs_in_order` | pending 3 件 → FIFO で 3 件 completed |
| L03 | `test_run_forever_picks_up_new_job_after_idle` | idle 後 enqueue → poll_interval 内に running |
| L04 | `test_run_forever_sigterm_when_idle_exits_quickly` | idle で SIGTERM → 1 秒以内 exit |
| L05 | `test_run_forever_sigterm_during_job_finishes_first` | 5 秒 job 中 SIGTERM → completed まで待機 → exit |
| L06 | `test_run_forever_sigint_treated_as_sigterm` | SIGINT も graceful |
| L07 | `test_two_pending_then_sigterm_completes_first_skips_second` | 1 件目処理中 SIGTERM → 1 件目 completed、2 件目 pending 残置 |
| L08 | `test_busy_timeout_pragma_applied` | `PRAGMA busy_timeout` が 5000 |
| L09 | `test_journal_mode_wal_applied` | `PRAGMA journal_mode` が `wal` |
| L10 | `test_worker_does_not_block_concurrent_db_reads` | fake job 実行中の `list_jobs` 10 並行 → 200ms 以内 |

#### `tests/unit/web/test_analysis_jobs_routes.py` (既存・回帰)

| # | テスト名 | 検証内容 |
|---|---|---|
| R01 | `test_create_job_returns_201_for_new` | 新規 → 201、body に job_id |
| R02 | `test_create_job_returns_200_for_existing` | 既存 pending → 200、同 job_id |
| R03 | `test_get_job_404_for_unknown` | 不在 → 404 |
| R04 | `test_list_jobs_status_filter` | `?status=pending,running` 該当のみ |
| R05 | `test_list_jobs_invalid_status_400` | 不正 status → 400 |
| R06 | `test_delete_job_cancels_pending` | pending DELETE → cancelled |
| R07 | `test_delete_job_running_returns_running` | running DELETE → 変更なし返却 |
| R08 | `test_dismiss_completed` | completed dismiss → dismissed_at |
| R09 | `test_dismiss_pending_400` | pending dismiss → 400 |
| R10 | `test_heavy_rate_limit_429` | 規定回数超で 429 |

#### `tests/unit/cli/test_worker_cli.py` (新規)

| # | テスト名 | 検証内容 |
|---|---|---|
| C01 | `test_register_parser_adds_worker_subcommand` | argparse 登録確認 |
| C02 | `test_handle_creates_worker_and_calls_run_forever` | run_forever await 確認 |
| C03 | `test_handle_disposes_clients_on_exit` | finally で dispose 呼び出し |
| C04 | `test_handle_passes_poll_interval_arg` | `--poll-interval` 伝搬 |

#### `tests/unit/shared/test_clients.py` (新規)

| # | テスト名 | 検証内容 |
|---|---|---|
| S01 | `test_build_client_bundle_no_pageindex` | pageindex 無効 → bundle.llm is None |
| S02 | `test_build_client_bundle_with_pageindex` | 有効時 → llm/pdf_converter 構築 |
| S03 | `test_dispose_clients_calls_close_on_each` | 各 close() 呼ばれる |
| S04 | `test_dispose_clients_swallows_exceptions` | 個別例外でも全 client 試行 (warning ログ) |

#### `tests/e2e/test_analysis_queue_end_to_end.py` (新規)

| # | テスト名 | 検証内容 |
|---|---|---|
| E01 | `test_full_lifecycle_via_http` | POST → ポーリング → completed → `/rag/analyses` で 4 件 |
| E02 | `test_pending_to_cancelled_via_http` | ワーカー起動前 DELETE → cancelled、起動後も実行されない |
| E03 | `test_failed_job_retains_error_details` | 全タイプ error → failed_types 取得 |

#### 静的チェック

| # | テスト名 | 検証内容 |
|---|---|---|
| ST01 | `test_pageindex_async_helpers_required` | `_HAS_PAGEINDEX_ASYNC_HELPERS is True` (sync `page_index()` 経由の deadlock 防止) |
| ST02 | `test_web_app_lifespan_does_not_start_worker` | `lifespan` に `analysis_queue.start()` が含まれない |
| ST03 | `test_analysis_queue_service_has_no_worker_methods` | リファクタ後 `start`/`stop`/`_worker_loop`/`_run_job` 不在 |

#### Regression テスト（最重要）

| # | テスト名 | 検証内容 |
|---|---|---|
| RG01 | `test_web_event_loop_unaffected_by_worker_subprocess` | サブプロセスで worker 起動 → 親で 100 リクエスト並列 → p99 < 200ms。fake LLM で `asyncio.sleep(0.1)` ×4 ループ |
| RG02 | `test_run_full_analysis_stream_uses_async_path_only` | `pageindex.page_index_main` (内部で `asyncio.run`) を呼ばないことを mock spy で確認 |

### 6-3. Fixtures とモック戦略

```python
# tests/conftest.py に追加

@pytest.fixture
async def in_memory_engine() -> AsyncEngine:
    """関数スコープのインメモリ SQLite。PRAGMA / metadata 作成済み。"""

@pytest.fixture
async def session_factory(in_memory_engine) -> async_sessionmaker:
    """expire_on_commit=False の async_sessionmaker。"""

@pytest.fixture
def fake_rag_service():
    """run_full_analysis_stream を返す AsyncMock。events パターン差し替え可能。"""

@pytest.fixture
def fake_clients(fake_llm_client, fake_pdf_converter):
    """ClientBundle の fake。close() は AsyncMock。"""

@pytest.fixture
async def worker(session_factory, fake_clients, fake_rag_service, monkeypatch):
    """AnalysisWorker 組み立て。setup_services を fake_rag_service 注入版に差し替え。"""

@pytest.fixture
async def seeded_jobs(session_factory):
    """request.param で事前投入。"""

@pytest.fixture
def tmp_db(tmp_path) -> Path:
    """ファイル SQLite for integration tests。"""

@pytest.fixture
async def background_worker(tmp_db, fake_clients):
    """create_task で run_forever 起動。yield 後に shutdown 信号送って待機。"""
```

**モック原則**:
- LLM は **CI で絶対に呼ばない**。`fake_llm_client` は `AsyncMock`、応答は固定 JSON。
- PDF 変換も呼ばない。`fake_pdf_converter.get_or_convert` は `tmp_path/dummy.pdf` を返す。
- `RagService.run_full_analysis_stream` のフェイク化が **メインのテストハンドル**。

### 6-4. カバレッジ目標

| 対象ファイル | line | branch |
|---|---|---|
| `services/analysis_worker.py` (新規) | ≥95% | ≥90% |
| `services/analysis_queue.py` (薄化後) | ≥95% | ≥90% |
| `cli/worker.py` (新規) | ≥90% | ≥85% |
| `shared/clients.py` (新規) | ≥90% | ≥85% |
| `web/routes/analysis_jobs.py` (無変更) | 既存維持 (≥85%) | 既存維持 |
| `web/app.py` (lifespan 修正) | 既存維持 | 既存維持 |

CI: `uv run pytest --cov=src/stock_analyze_system --cov-branch --cov-fail-under=85 --cov-report=term-missing tests/`

### 6-5. プロパティ/並行テスト

| # | テスト名 | 検証内容 |
|---|---|---|
| P01 | `test_concurrent_enqueue_same_filing_idempotent` | gather 20 並行 → pending 件数常に 1 |
| P02 | `test_concurrent_enqueue_different_filings_all_created` | 異 filing 20 並行 → 全 20 pending |
| P03 | `test_dequeue_then_cancel_race` | dequeue と cancel 並行 → 最終状態 running か cancelled、不整合なし |
| P04 | `test_two_workers_dont_pick_same_job` | 2 worker で 100 件 → 各ジョブ正確に 1 回完了 |

### 6-6. UI/JS の検証戦略

- **自動化**: `static/app.js` の新規モジュール (`pollAnalysisJobs`, `analysisQueueState`) は ESM 互換に書き直し、`node:test` + `jsdom` ベースのテストを `tests/js/` 配下に新設。
  - JST01: badge 状態遷移 (empty → pending → running → empty) が `setBadge` 関数で正しく出る
  - JST02: completed transition 検出 (前回 running、今回 completed) → 通知発火 1 回のみ
  - JST03: `sessionStorage` キー重複時は通知発火しない
  - JST04: タブタイトル `(N) ` プレフィックス付与・除去
- **TestClient による HTML レンダ確認**: `_topbar.html` の badge 要素が認証済みページに含まれる (dashboard / watchlists / screening / stocks 各テンプレートで snapshot)。

**Manual QA Checklist** (PR description に貼る):

- [ ] 分析ボタン押下後、トップバーバッジに「分析中 1件」が現れる
- [ ] バッジクリックで該当銘柄の分析タブに遷移する
- [ ] タブタイトル先頭に `(1)` が付く
- [ ] 完了時に OS 通知が出る (許可済み環境のみ)
- [ ] 通知クリックでウィンドウが focus され該当銘柄へ遷移
- [ ] 拒否環境では通知なしでもバッジ/タイトルは正常更新
- [ ] ワーカー停止後 30 秒で「ワーカー未稼働」赤バッジに切り替わる
- [ ] ワーカー再起動後、自動で通常表示に戻る
- [ ] 複数ブラウザタブ間で同期更新 (同一ジョブが両方で running 表示)

### 6-7. CI 実行プラン

| ステージ | 内容 | 想定時間 |
|---|---|---|
| 1. lint | `ruff check`, `ruff format --check` | < 10s |
| 2. unit | `pytest tests/unit -q --cov` | 30-60s |
| 3. integration | `pytest tests/integration -q` | 60-120s |
| 4. e2e | `pytest tests/e2e -q` | 60-90s |
| 5. js | `node --test tests/js/*.test.js` | 10-20s |
| 6. coverage gate | `coverage report --fail-under=85` | < 5s |

flaky を許容しない設計 (`asyncio.wait_for` でタイムアウト明示、`asyncio.sleep` は最小限)。

### 6-8. 受け入れ基準（PR マージ条件）

1. 新規テスト 77 ケース（Q18 + W12 + L10 + R10 + C4 + S4 + E3 + ST3 + RG2 + P4 + JST4）が全てグリーン
2. 既存テスト 1120+ ケースが 1 件も赤化していない（マージ前に `pytest tests/` 全体実行で確認）
3. カバレッジ目標達成（6-4）
4. `RG01` リグレッションテスト合格 (イベントループ非ブロッキング数値確認、p99 < 200ms)
5. Manual QA Checklist 全項目 ✅（PR description に結果を貼る）
6. 移行手順（セクション 7）をコミット粒度で分割 (最低 7 コミット) → 各段階で revertable

### 6-9. 非対象（明示の除外）

- **Q&A エンドポイント (`/api/stocks/{id}/rag/ask`) のワーカー移行** — 別 PR。Q&A は短時間 LLM 1 呼び出しなので継続的 UI ブロッキングなし。
- **PageIndex 内部の同期 LLM 呼び出しを async 化する PR** — 上流 (`<pageindex-repo>`) への変更は別 PR。今回はプロセス分離で隔離。
- **複数ワーカーの並列稼働** — `dequeue_next` 自体は競合耐性があるが、llama-server スロット 4 がボトルネックのため運用上の利得なし。P04 で「重複なし」だけ保証。
- **Web 側からのキャンセル通知** — pending のみ cancel 可能、running は完了待ち。

## 7. 移行手順

依存関係を壊さない順で:

1. **モデル/PRAGMA 層の準備**
   - `models/base.py` に `PRAGMA busy_timeout=5000` 追加。
   - DB スキーマ変更なし。

2. **クライアントブートストラップの共有化**
   - `shared/clients.py` 新規。`build_client_bundle` / `dispose_clients` 切り出し。
   - `web/dependencies.py:AppState.create` / `dispose` を新ヘルパに置換。

3. **`AnalysisWorker` の新規追加**
   - `services/analysis_worker.py` 新規。
   - 既存 `AnalysisQueueService._worker_loop` / `_dequeue_next` / `_run_job` / `_execute_with_status` のロジックをコピーし、`AnalysisWorker` に移植。signal handler と `run_one_job` 追加。
   - この段階では `AnalysisQueueService` 側は手付かず（二重存在）。

4. **`AnalysisQueueService` の薄化**
   - 移植済みメソッド・フィールドを削除。
   - `cancel` の running 分岐 (`task.cancel()`) を削除。

5. **Web の lifespan 修正**
   - `web/app.py` の `state.analysis_queue.start()` / `stop()` 呼び出し削除。
   - `web/dependencies.py:AppState.analysis_queue` フィールドは維持（API ルートが参照）。

6. **CLI `worker` サブコマンド追加**
   - `cli/worker.py` 新規。
   - `cli/app.py` に `worker.register_parser(subparsers)` 登録。

7. **UI 改修**
   - `templates/_topbar.html` にバッジ要素追加。
   - `static/app.css` に `topbar__badge` / `topbar__badge-dot` / `pulse` キーフレーム追加。
   - `static/app.js` に共通 `pollAnalysisJobs` モジュール / `analysisQueueState` / 通知ロジック追加。既存 `fetchQueue` / `initQueuePanel` を購読者形式に書き換え。

8. **動作確認**
   - Web 単体起動 → 分析ボタン押下 → pending 残置を確認、ワーカー未稼働バナー表示。
   - 別ターミナルで worker 起動 → pending → running → completed 遷移、UI 同期、完了 OS 通知。
   - SIGINT で graceful exit、in-flight があれば完了待ち。

### 運用手順の変更

```bash
# 端末1: web
infisical run -- stock-analyze serve

# 端末2: worker（必須・別ターミナル）
infisical run -- stock-analyze worker
```

systemd 化サンプル（README に Tips として記載、今回はファイル作成しない）:

```ini
[Service]
ExecStart=/usr/bin/infisical run -- <user-local>/bin/stock-analyze worker
Restart=on-failure
RestartSec=5
```

### ロールバック手順

- `git revert` 1 コミットで戻る粒度でコミット分割（最低 7 コミット）。
- DB スキーマ変更なしのためデータ移行不要。

## 8. 想定外リスクと緩和

| リスク | 緩和 |
|---|---|
| Web のみ起動でワーカー未起動を放置 → 分析が永久に走らない | トップバーバッジ赤化（30 秒経過判定）+ ダッシュボードキューパネル下に説明文 |
| Worker クラッシュで running ジョブ放置 | 次回起動時の `reset_running_to_failed` で自動 failed 化、UI で「再実行」可能 |
| 並行 write による SQLite lock | `PRAGMA busy_timeout=5000` で 5 秒待機。それでも超える場合は `OperationalError` をログに出力、UI には failed として伝播 |
| PageIndex を別バージョンに上げて sync 経路が増える | 静的テスト ST01 で `_HAS_PAGEINDEX_ASYNC_HELPERS` を検査、RG02 で `page_index_main` 不使用を確認 |
| 通知 API 拒否環境での体験劣化 | バッジ + タイトルプレフィックスは Notification API に依存しないため UX 維持 |
| 複数の人が同時に同一銘柄分析を押す | `enqueue` の `find_active_by_company_filing` + `IntegrityError` ハンドリングで 1 件に集約 |
