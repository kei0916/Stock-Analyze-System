# バックグラウンドLLM分析キュー設計

## 1. ユーザー意図・背景

### 1.1 要望の背景
ユーザーはWeb UI上で「決算分析🔍」ボタンを押してRAG定型分析を実行している。現状、`POST /api/stocks/{company_id}/rag/analyze` はNDJSONストリーミングで進捗を返す。分析にはLLM推論が複数回走り時間がかかる（数分〜十数分）ため、ブラウザのタブを閉じたり、スマートフォンアプリをバックグラウンドに回したりするとHTTP接続が切断され、分析が中断される。

### 1.2 ユーザー要求
> 「定型分析を実行したらappを落としても分析を止めずに続けて欲しい。」

具体的な要求（対話で確定した内容）：

| # | 要求 | 確定内容 |
|---|---|---|
| 1 | 「appを落とす」の定義 | (a) ブラウザのタブを閉じる・ページを移動する |
| 2 | 進捗確認方法 | ダッシュボードのLLM分析キューで簡易表示でポーリング確認。分析タブでも従来どおり進捗を確認可能とする |
| 3 | 並列実行 | 重い処理は単一実行で順次処理。複数社をキューイングして順次実行 |
| 4 | 分析タブのポーリング間隔 | 5秒 |
| 5 | ダッシュボードのポーリング間隔 | 5秒 |
| 6 | 同じ企業・決算の重複enqueue | 既存 `pending`/`running` があればその `job_id` を返す（重複防止） |
| 7 | マルチユーザー想定 | 単一ユーザー前提（自分・身内のみ）。`created_by` は持たない |
| 8 | キャンセル機能 | 今回スコープに含める。`pending` / `running` 両方キャンセル可能 |
| 9 | 部分失敗の扱い | `failed` で統一。UI に「再実行」ボタンを表示。再実行時はキャッシュ済みタイプはスキップ |
| 10 | タブ復帰時の挙動 | ページ読込時に対象 filing の進行中ジョブを自動検出してポーリング再開 |

---

## 2. 現状の問題

### 2.1 技術的制約
現在の `POST /api/stocks/{company_id}/rag/analyze`（`web/routes/api.py:232-264`）は `StreamingResponse` でNDJSONを返却する。これはHTTP接続を維持し続ける必要があるため：

- ブラウザタブを閉じるとTCP接続が切断され、FastAPI側の非同期ジェネレータも終了する
- スマートフォンでブラウザをバックグラウンドに回すと、OSが接続を切断する場合がある
- 中継器（リバースプロキシ）がタイムアウトで接続を切る場合がある

### 2.2 影響
- 長時間のLLM推論（4タイプ × 1〜3分 = 数分〜十数分）が途中で中断される
- ユーザーは中断された分析を最初からやり直す必要がある
- 1社の分析完了までブラウザを開き続ける必要がある

---

## 3. 設計目標

1. **ブラウザを閉じても分析が継続する**: HTTP接続に依存しないバックグラウンド実行
2. **進捗が確認できる**: ダッシュボードと分析タブの両方で実行中ジョブの状態を確認
3. **リソース制御**: 重いLLM処理は同時1件で順次実行（サーバー負荷・LLMレート制限対策）
4. **既存機能との共存**: 既存 `POST /rag/analyze` は **deprecated として維持**（次回リリースで削除予告）
5. **インフラ追加なし**: SQLite上のテーブル＋`asyncio.Task` で完結（Redis/Celery不要）
6. **DRY**: `RagService.run_full_analysis_stream` をそのまま再利用し、二重実装を避ける

---

## 4. アーキテクチャ

```
┌─────────────────┐     POST /api/analysis-jobs      ┌──────────────────┐
│  ブラウザ        │ ───────────────────────────────→ │  AnalysisJob     │
│  (分析タブ)      │                                    │  APIエンドポイント │
│                 │ ← {job_id, status: "pending"}     └────────┬─────────┘
│                 │                                               │
│  5秒ポーリング   │ ← GET /api/analysis-jobs/{job_id}             │
│                 │                                               │
│                 │                              ┌────────────────▼─────────┐
│                 │                              │   AnalysisQueueService   │
│                 │                              │   ┌─────────────────┐   │
│  キャンセル      │ DELETE /api/analysis-jobs/   │   │  _worker_loop() │   │
│  / dismiss      │ ────────────{job_id}───────→ │   │  (asyncio.Task) │   │
└─────────────────┘                              │   └────────┬────────┘   │
                                                 │            │ asyncio    │
┌─────────────────┐                              │            │ .Event     │
│  ブラウザ        │ ← GET /api/analysis-jobs     │   ┌────────▼────────┐   │
│  (ダッシュボード) │  (5秒ポーリング)              │   │ SQLite          │   │
│                 │                              │   │ analysis_jobs   │   │
│  LLM分析キュー   │                              │   └─────────────────┘   │
│  パネル         │                              └─────────────────────────┘
└─────────────────┘                                        │
                                                          │ 専用DBセッション＋
                                                          │ ServiceContainer構築
                                                          ▼
                                                 ┌──────────────────┐
                                                 │ RagService       │
                                                 │ run_full_analysis│
                                                 │ _stream() を消費  │
                                                 └──────────────────┘
```

---

## 5. データモデル

### 5.1 `AnalysisJob` テーブル

```python
import enum
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(String(30), index=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"))
    status: Mapped[JobStatus] = mapped_column(
        String(20), default=JobStatus.PENDING,
    )
    progress_current: Mapped[int] = mapped_column(default=0)
    progress_total: Mapped[int] = mapped_column(default=4)
    current_analysis_type: Mapped[str | None] = mapped_column(
        String(30), default=None,
    )
    error_details: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None,
    )
```

#### カラム詳細

| カラム | 型 | デフォルト | 説明 |
|---|---|---|---|
| `id` | int PK | auto | ジョブID。APIで `{job_id}` として参照 |
| `company_id` | str(30), index | — | 企業ID（例: `US_AAPL`） |
| `filing_id` | int, FK→filings | — | 対象決算 |
| `status` | str(20) | `"pending"` | `JobStatus` enum |
| `progress_current` | int | `0` | 完了した分析タイプ数。`0`〜`4` |
| `progress_total` | int | `4` | 定型分析タイプ数（固定`4`） |
| `current_analysis_type` | str(30) \| None | `None` | 現在実行中のタイプ |
| `error_details` | JSON \| None | `None` | 失敗時の構造化エラー（後述） |
| `created_at` | datetime(tz=True) | `func.now()` | ジョブ作成時刻（UTC） |
| `started_at` | datetime(tz=True) \| None | `None` | 実行開始時刻（UTC） |
| `completed_at` | datetime(tz=True) \| None | `None` | 完了・失敗・キャンセル時刻（UTC） |
| `dismissed_at` | datetime(tz=True) \| None | `None` | UI から非表示にした時刻。NULLなら表示対象 |

#### `error_details` のスキーマ

```json
{
  "failed_types": [
    {"type": "mda", "message": "request timeout after 120s"},
    {"type": "risk_factors", "message": "JSON parse error: ..."}
  ],
  "reason": "Server restarted while running"
}
```

- 通常の分析失敗は `failed_types` 配列に追記される
- 起動時リセットの場合は `reason` フィールドに理由を記録（`failed_types` は省略）

#### インデックス

| インデックス | カラム | 制約 | 用途 |
|---|---|---|---|
| `ix_analysis_jobs_company_id` | `(company_id)` | — | 一覧取得 |
| `uq_analysis_jobs_active` | `(company_id, filing_id)` | UNIQUE WHERE `status IN ('pending','running')` | enqueue 重複防止（partial unique index） |

partial unique index は SQLite 3.8.0+ でサポートされる。`Index(..., sqlite_where=text("status IN ('pending','running')"))` で定義する。

### 5.2 マイグレーション戦略

- 既存の `Base.metadata.create_all`（`models/base.py:42`）が起動時に呼ばれるため、新テーブルとインデックスは自動作成される
- Alembic は本プロジェクトでは導入されていない。既存テーブルは触らないので追加マイグレーションは不要

---

## 6. サービス設計

### 6.1 `AnalysisQueueService`

```python
class AnalysisQueueService:
    def __init__(self, session_factory, config, clients):
        self._session_factory = session_factory  # async_sessionmaker
        self._config = config
        self._clients = clients
        self._worker_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._wakeup_event = asyncio.Event()
        self._running_tasks: dict[int, asyncio.Task] = {}  # job_id -> Task
        self._enqueue_lock = asyncio.Lock()  # 補助的な直列化（DB制約と二重防御）

    # --- 公開API ---
    async def start(self) -> None:
        """起動時に呼び出し。runningジョブをfailedに復旧 + ワーカー起動"""

    async def stop(self, timeout: float = 30.0) -> None:
        """停止時に呼び出し。graceful shutdown（タイムアウト後はキャンセル）"""

    async def enqueue(self, company_id: str, filing_id: int) -> AnalysisJob:
        """ジョブをenqueue。重複時は既存pending/runningを返却"""

    async def cancel(self, job_id: int) -> AnalysisJob | None:
        """ジョブをキャンセル。pending→直接cancelled、running→Task.cancel()"""

    async def dismiss(self, job_id: int) -> AnalysisJob | None:
        """failed/cancelled ジョブを UI から非表示にする"""

    async def get_status(self, job_id: int) -> AnalysisJob | None:
        """ジョブ状態を取得"""

    async def list_jobs(
        self,
        *,
        company_id: str | None = None,
        filing_id: int | None = None,
        statuses: list[JobStatus] | None = None,
        include_dismissed: bool = False,
        limit: int = 20,
    ) -> list[AnalysisJob]:
        """フィルタ付きジョブ一覧（新しい順）"""

    # --- 内部 ---
    async def _worker_loop(self) -> None: ...
    async def _run_job(self, job: AnalysisJob) -> None: ...
    async def _dequeue_next(self) -> AnalysisJob | None: ...
    async def _reset_running_jobs(self) -> None: ...
```

### 6.2 ワーカーループ

```python
async def _worker_loop(self):
    while not self._shutdown_event.is_set():
        job = await self._dequeue_next()
        if job is None:
            self._wakeup_event.clear()
            # Event 即時起床 + 1秒タイムアウト poll の両立
            # asyncio.wait で wakeup または shutdown のいずれかを待ち、
            # 1 秒経っても何も起きなければ再ポーリングする。
            wakeup_task = asyncio.create_task(self._wakeup_event.wait())
            shutdown_task = asyncio.create_task(self._shutdown_event.wait())
            done, pending = await asyncio.wait(
                {wakeup_task, shutdown_task},
                timeout=1.0,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            continue

        # _run_job を Task として起動（cancel 用に保持）
        task = asyncio.create_task(self._execute_with_status(job))
        self._running_tasks[job.id] = task
        try:
            await task
        except asyncio.CancelledError:
            await self._update_status(
                job.id, JobStatus.CANCELLED, completed_at=now_utc(),
            )
        finally:
            self._running_tasks.pop(job.id, None)
```

### 6.3 原子的 dequeue

```python
async def _dequeue_next(self) -> AnalysisJob | None:
    """SQLite で原子的に pending → running に遷移させる。

    複数ワーカーが立ち上がっても二重実行されないことを保証する。
    """
    async with self._session_factory() as session:
        # 最も古い pending ジョブを 1 件選択
        stmt = (
            select(AnalysisJob.id)
            .where(AnalysisJob.status == JobStatus.PENDING)
            .order_by(AnalysisJob.created_at.asc())
            .limit(1)
        )
        result = await session.execute(stmt)
        candidate_id = result.scalar_one_or_none()
        if candidate_id is None:
            return None

        # 条件付き UPDATE で running に遷移（rowcount チェック）
        update_stmt = (
            update(AnalysisJob)
            .where(
                AnalysisJob.id == candidate_id,
                AnalysisJob.status == JobStatus.PENDING,
            )
            .values(
                status=JobStatus.RUNNING,
                started_at=now_utc(),
            )
        )
        result = await session.execute(update_stmt)
        await session.commit()

        if result.rowcount == 0:
            # 他ワーカーが先に取った
            return None

        return await session.get(AnalysisJob, candidate_id)
```

### 6.4 ジョブ実行 (`_run_job`) — RagService イベント消費

`RagService.run_full_analysis_stream` をそのまま `async for` で消費し、進捗を AnalysisJob に反映する。**自前のキャッシュチェック・filing 取得・index 構築は行わない**（RagService 側の最適化を享受）。

```python
async def _run_job(self, job: AnalysisJob) -> None:
    failed_types: list[dict] = []
    progress_index = 0

    async with self._session_factory() as session:
        container = await setup_services(
            session, self._config, clients=self._clients,
        )
        rag = container.rag_service
        if rag is None:
            raise RuntimeError("RAG service is not enabled")
        filing = await container.filing_service.get_filing_by_id(job.filing_id)
        if filing is None:
            raise ValueError(f"filing_id={job.filing_id} not found")

        async for event in rag.run_full_analysis_stream(filing):
            etype = event.get("event")
            if etype == "started":
                await self._update_progress(
                    job.id, total=event["total"],
                )
            elif etype == "phase":
                progress_index = event["index"]
                await self._update_progress(
                    job.id,
                    current=progress_index,
                    current_type=event["analysis_type"],
                )
            elif etype in ("done", "cached"):
                progress_index = event["index"] + 1
                await self._update_progress(
                    job.id, current=progress_index,
                )
            elif etype == "error":
                failed_types.append({
                    "type": event.get("analysis_type"),
                    "message": event.get("message", ""),
                })
            elif etype == "complete":
                pass  # ループ終了

        # ストリーム終了後の最終判定
        await self._update_progress(
            job.id, current=progress_index, current_type=None,
        )
        if failed_types:
            raise AnalysisFailedError(failed_types)
```

ワーカーループ側 (`_execute_with_status`) で `AnalysisFailedError` をキャッチして `failed` に遷移し、`error_details = {"failed_types": [...]}` を保存する。

### 6.5 enqueue（重複防止 + 自動 dismiss）

```python
async def enqueue(self, company_id: str, filing_id: int) -> AnalysisJob:
    async with self._enqueue_lock:
        async with self._session_factory() as session:
            # 既存 pending/running があれば返却
            existing = await self._find_active(
                session, company_id, filing_id,
            )
            if existing is not None:
                return existing

            # 同 filing の過去 failed/cancelled を自動 dismiss
            await session.execute(
                update(AnalysisJob)
                .where(
                    AnalysisJob.company_id == company_id,
                    AnalysisJob.filing_id == filing_id,
                    AnalysisJob.status.in_(
                        [JobStatus.FAILED, JobStatus.CANCELLED],
                    ),
                    AnalysisJob.dismissed_at.is_(None),
                )
                .values(dismissed_at=now_utc())
            )

            # 新規作成（partial unique index で最終防衛）
            job = AnalysisJob(
                company_id=company_id, filing_id=filing_id,
                status=JobStatus.PENDING,
            )
            session.add(job)
            try:
                await session.commit()
            except IntegrityError:
                # レース時の最終フォールバック
                await session.rollback()
                existing = await self._find_active(
                    session, company_id, filing_id,
                )
                if existing is not None:
                    return existing
                raise

    self._wakeup_event.set()  # ワーカー即時起床
    return job
```

`_enqueue_lock` と partial unique index の二重防御により、複数プロセス・複数タブ同時送信どちらにも安全。

### 6.6 キャンセル

```python
async def cancel(self, job_id: int) -> AnalysisJob | None:
    async with self._session_factory() as session:
        job = await session.get(AnalysisJob, job_id)
        if job is None:
            return None

        if job.status == JobStatus.PENDING:
            # 直接 cancelled に遷移
            job.status = JobStatus.CANCELLED
            job.completed_at = now_utc()
            await session.commit()
            return job

        if job.status == JobStatus.RUNNING:
            task = self._running_tasks.get(job_id)
            if task is not None:
                task.cancel()
            # ステータス更新は _worker_loop 側の except CancelledError で行う
            return await session.get(AnalysisJob, job_id)

        return job  # 既に完了状態
```

### 6.7 dismiss

```python
async def dismiss(self, job_id: int) -> AnalysisJob | None:
    async with self._session_factory() as session:
        stmt = (
            update(AnalysisJob)
            .where(
                AnalysisJob.id == job_id,
                AnalysisJob.status.in_(
                    [JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.COMPLETED],
                ),
            )
            .values(dismissed_at=now_utc())
        )
        await session.execute(stmt)
        await session.commit()
        return await session.get(AnalysisJob, job_id)
```

### 6.8 起動時の復旧 / 停止時の graceful shutdown

```python
async def start(self) -> None:
    await self._reset_running_jobs()
    self._worker_task = asyncio.create_task(self._worker_loop())

async def _reset_running_jobs(self) -> None:
    async with self._session_factory() as session:
        await session.execute(
            update(AnalysisJob)
            .where(AnalysisJob.status == JobStatus.RUNNING)
            .values(
                status=JobStatus.FAILED,
                error_details={"reason": "Server restarted while running"},
                completed_at=now_utc(),
            )
        )
        await session.commit()

async def stop(self, timeout: float = 30.0) -> None:
    self._shutdown_event.set()
    self._wakeup_event.set()  # 起床させて shutdown を検知させる
    if self._worker_task is None:
        return
    try:
        await asyncio.wait_for(self._worker_task, timeout=timeout)
    except asyncio.TimeoutError:
        # タイムアウト: 強制キャンセル
        self._worker_task.cancel()
        for task in list(self._running_tasks.values()):
            task.cancel()
        await asyncio.gather(
            self._worker_task, *self._running_tasks.values(),
            return_exceptions=True,
        )
        # 残った running を cancelled としてマーク
        async with self._session_factory() as session:
            await session.execute(
                update(AnalysisJob)
                .where(AnalysisJob.status == JobStatus.RUNNING)
                .values(
                    status=JobStatus.CANCELLED,
                    completed_at=now_utc(),
                )
            )
            await session.commit()
```

---

## 7. リポジトリ設計

### 7.1 `AnalysisJobRepository`

| メソッド | 用途 |
|---|---|
| `create(company_id, filing_id) -> AnalysisJob` | 新規 enqueue |
| `find_active_by_company_filing(company_id, filing_id) -> AnalysisJob \| None` | pending/running 検索 |
| `dequeue_next() -> AnalysisJob \| None` | 原子的 dequeue（§6.3） |
| `update_status(job_id, status, **fields) -> None` | ステータス遷移 |
| `update_progress(job_id, *, current=None, current_type=None, total=None) -> None` | 進捗更新（指定フィールドのみ） |
| `dismiss_past_for_filing(company_id, filing_id) -> int` | 同 filing の failed/cancelled を dismiss |
| `dismiss(job_id) -> None` | 単一ジョブを dismiss |
| `reset_running_to_failed() -> int` | 起動時復旧 |
| `list(filters, limit) -> list[AnalysisJob]` | フィルタ付き一覧 |
| `get(job_id) -> AnalysisJob \| None` | 単一取得 |

---

## 8. API設計

### 8.1 エンドポイント一覧

| メソッド | パス | 説明 |
|---|---|---|
| `POST` | `/api/analysis-jobs` | ジョブを enqueue |
| `GET` | `/api/analysis-jobs/{job_id}` | ジョブ状態取得（ポーリング用） |
| `GET` | `/api/analysis-jobs` | ジョブ一覧（フィルタ可能） |
| `DELETE` | `/api/analysis-jobs/{job_id}` | ジョブをキャンセル |
| `POST` | `/api/analysis-jobs/{job_id}/dismiss` | 完了/失敗/キャンセル済みジョブを非表示化 |

### 8.2 `POST /api/analysis-jobs`

**Request Body:**
```json
{"company_id": "US_AAPL", "filing_id": 42}
```

**Response 201（新規作成時）:**
```json
{
  "job_id": 7,
  "status": "pending",
  "company_id": "US_AAPL",
  "filing_id": 42,
  "created_at": "2026-05-10T12:34:56Z"
}
```

**Response 200（既存 pending/running 返却時）:**
新規 INSERT が発生せず既存ジョブを返した場合は 200 で返す。レスポンスボディ形式は同じ。

### 8.3 `GET /api/analysis-jobs/{job_id}`

**Response 200:**
```json
{
  "job_id": 7,
  "company_id": "US_AAPL",
  "filing_id": 42,
  "status": "running",
  "progress_current": 2,
  "progress_total": 4,
  "current_analysis_type": "mda",
  "error_details": null,
  "created_at": "2026-05-10T12:34:56Z",
  "started_at": "2026-05-10T12:34:57Z",
  "completed_at": null,
  "dismissed_at": null
}
```

**Response 404:** ジョブが存在しない

### 8.4 `GET /api/analysis-jobs`

**Query Parameters:**

| 名前 | 型 | デフォルト | 説明 |
|---|---|---|---|
| `company_id` | str | — | 企業IDで絞込（タブ復帰時の検索用） |
| `filing_id` | int | — | filing IDで絞込 |
| `status` | str (CSV) | — | 状態で絞込（例: `pending,running`） |
| `include_dismissed` | bool | `false` | dismiss 済みも含めるか |
| `limit` | int | `20` | 上限件数 |

**Response 200:**
```json
[
  {
    "job_id": 7,
    "company_id": "US_AAPL",
    "filing_id": 42,
    "status": "running",
    "progress_current": 2,
    "progress_total": 4,
    "current_analysis_type": "mda",
    "error_details": null,
    "created_at": "2026-05-10T12:34:56Z",
    "started_at": "2026-05-10T12:34:57Z",
    "completed_at": null,
    "dismissed_at": null
  }
]
```

**ダッシュボードの呼び出し例:**
`GET /api/analysis-jobs?status=pending,running,failed&include_dismissed=false&limit=20`

**分析タブのタブ復帰時呼び出し例:**
`GET /api/analysis-jobs?company_id=US_AAPL&filing_id=42&status=pending,running&limit=1`

### 8.5 `DELETE /api/analysis-jobs/{job_id}`

**Response 200:**
```json
{"job_id": 7, "status": "cancelled", ...}
```

- `pending` → 直接 `cancelled`
- `running` → 実行 Task を `cancel()`、最終的に `cancelled`
- 既に終了状態（`completed`/`failed`/`cancelled`）→ 現状を返す（冪等）

**Response 404:** ジョブが存在しない

### 8.6 `POST /api/analysis-jobs/{job_id}/dismiss`

**Response 200:**
```json
{"job_id": 7, "status": "failed", "dismissed_at": "2026-05-10T12:50:00Z", ...}
```

- 対象は `failed` / `cancelled` / `completed`
- `pending` / `running` には適用不可（400 を返す）

### 8.7 既存エンドポイントの扱い

`POST /api/stocks/{company_id}/rag/analyze`（NDJSONストリーミング）は **deprecated として維持** する：

- ハンドラ冒頭で `logger.warning("DEPRECATED: ...")` を出力
- OpenAPI に `deprecated=True` を設定
- ドキュメント（README/CHANGELOG）に削除予告を明記
- 旧APIは新キューとは独立に動作（LLM 負荷制御の協調はしない）

---

## 9. UI設計

### 9.1 分析タブ (`stocks/_tab_analysis.html` + `app.js`)

**初期化フロー（タブ復帰時の自動検出）:**
1. ページ読込時、現在の `company_id` / `filing_id` で `GET /api/analysis-jobs?company_id=X&filing_id=Y&status=pending,running&limit=1` を1回叩く
2. ヒットすれば、その `job_id` でポーリングを自動開始（プログレスバー表示）

**「決算分析🔍」クリック時のフロー:**
1. `fetch(POST /api/analysis-jobs, {company_id, filing_id})` で `job_id` を取得
2. 5秒間隔で `fetch(GET /api/analysis-jobs/{job_id})` をポーリング
3. レスポンスを既存 `applyEvent` 互換形式に変換してプログレスバー更新
4. `status === "completed"` / `"failed"` / `"cancelled"` でポーリング停止
5. 完了後 `loadAnalyses()` で保存済み分析を再読込

#### ポーリングレスポンス → UIイベント変換

```javascript
function jobToEvents(job, prevStatus) {
    const events = [];
    if (job.status === "pending") {
        events.push({event: "fetching"});
    } else if (job.status === "running") {
        if (prevStatus === "pending") {
            events.push({event: "started", total: job.progress_total});
        }
        if (job.current_analysis_type) {
            events.push({
                event: "phase",
                index: job.progress_current,
                total: job.progress_total,
                analysis_type: job.current_analysis_type,
                label: ANALYSIS_TYPE_LABELS[job.current_analysis_type],
            });
        } else if (job.progress_current === 0) {
            events.push({event: "indexing"});
        }
    } else if (job.status === "completed") {
        events.push({event: "complete"});
    } else if (job.status === "failed") {
        const failed = job.error_details?.failed_types ?? [];
        for (const f of failed) {
            events.push({event: "error", analysis_type: f.type, message: f.message});
        }
        events.push({event: "complete"});
    } else if (job.status === "cancelled") {
        events.push({event: "cancelled"});
        events.push({event: "complete"});
    }
    return events;
}
```

**`failed` 時の追加UI:** プログレスバー横に「再実行」ボタンを表示。クリックで `POST /api/analysis-jobs` を再送信（既存 failed は `enqueue` 時に自動 dismiss される）。

**`cancelled` 時の追加UI:** プログレスバーは消去。「分析がキャンセルされました」とメッセージ表示。「再実行」ボタンも併せて表示。

### 9.2 ダッシュボード (`dashboard.html` + `app.js`)

**変更前:** 右下パネル「LLM分析」— 直近5件の `completed` 分析結果を表示

**変更後:** 右下パネル「LLM分析キュー」— `pending`/`running`/`failed` ジョブ（`dismissed_at IS NULL`）のみ表示。`completed` と `cancelled` は表示しない（`completed` は分析タブで結果を見る、`cancelled` はユーザー意図的なので表示不要）

**表示内容:**
```
┌─ LLM分析キュー ──────────────────────────┐
│  [RUNNING]  US_AAPL  mda  2/4  01:23 [×]│
│  [PENDING]  US_MSFT  —    0/4  00:05 [×]│
│  [FAILED]   JP_7203  —    1/4  05:42 [×]│
└──────────────────────────────────────────┘
```

- **Statusバッジ**: `running`(`badge--up`緑) / `pending`(`badge--mono`灰) / `failed`(`badge--down`赤)
- **Company ID**: リンク（`/stocks/{company_id}` へ遷移）
- **Current type**: `running` の場合のみ
- **Progress**: `progress_current / progress_total`
- **Elapsed**: `created_at` からの経過時間（UTC基準で計算しブラウザローカルで `HH:MM` 表示）
- **`[×]` ボタン**:
  - `pending` / `running` → キャンセル（`DELETE /api/analysis-jobs/{job_id}`）
  - `failed` → dismiss（`POST /api/analysis-jobs/{job_id}/dismiss`）
- 空の場合: 「実行中の分析はありません」と表示

**ポーリング:** 5秒間隔で `GET /api/analysis-jobs?status=pending,running,failed&include_dismissed=false&limit=20`

---

## 10. Lifespan統合

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    state = await AppState.create(config)
    app.state.app_state = state
    await state.analysis_queue.start()  # ワーカー起動 + running復旧
    try:
        yield
    finally:
        await state.analysis_queue.stop(timeout=30.0)  # graceful shutdown
        await state.dispose()
```

---

## 11. エラー処理

### 11.1 タイプ単位の失敗
`RagService.run_full_analysis_stream` が `{"event": "error", "analysis_type": ..., "message": ...}` を yield した場合、`failed_types` に蓄積する。ストリーム終了後に `failed_types` が非空ならジョブ全体を `failed` とする。

**`error_details`:**
```json
{"failed_types": [{"type": "mda", "message": "request timeout"}]}
```

再実行時はキャッシュ済みタイプ（成功した3/4）が `RagService` 内のキャッシュチェックでスキップされ、失敗したタイプのみが再試行される。

### 11.2 致命的エラー（filing 不在・index 構築失敗）
`run_full_analysis_stream` のストリーム外で例外が発生した場合（`filing_id` 不正など）、`failed` に遷移し `error_details = {"reason": "..."}` を記録する。

### 11.3 サーバー再起動
起動時 `_reset_running_jobs` で `status="running"` を `failed` にリセット、`error_details = {"reason": "Server restarted while running"}`。`pending` はそのまま残し、ワーカー起動後に順次実行される。

### 11.4 キャンセル
- `pending` → 直接 `cancelled` に遷移
- `running` → `asyncio.Task.cancel()` で `CancelledError` を発生させ、ワーカーが `cancelled` に遷移

---

## 12. テスト計画

### 12.1 ユニットテスト: `AnalysisQueueService`

| テストケース | 内容 |
|---|---|
| `test_enqueue_creates_pending_job` | enqueue で pending ジョブが作成される |
| `test_enqueue_returns_existing_for_duplicate` | 同じ company_id+filing_id の pending/running があれば重複作成しない |
| `test_enqueue_concurrent_duplicate` | 並行 enqueue で partial unique index が二重 INSERT を防ぐ |
| `test_enqueue_dismisses_past_failed` | 同 filing の過去 failed が再 enqueue で自動 dismiss される |
| `test_worker_executes_job_sequentially` | ワーカーが pending を 1 件ずつ順次実行する |
| `test_worker_consumes_rag_event_stream` | RagService イベントが progress に反映される |
| `test_worker_marks_failed_on_partial_failure` | 1/4 タイプ失敗で全体 failed・error_details に記録 |
| `test_worker_marks_failed_on_fatal_error` | filing_id 不正など致命的例外で failed |
| `test_dequeue_atomic_no_double_execution` | 並行 dequeue で同じジョブが二重実行されない |
| `test_wakeup_event_triggers_worker` | enqueue 直後にワーカーが即起床する |
| `test_cancel_pending_job` | pending を直接 cancelled に遷移 |
| `test_cancel_running_job` | running を Task.cancel() で cancelled に遷移 |
| `test_dismiss_failed_job` | failed の dismissed_at が更新される |
| `test_dismiss_rejects_running_job` | pending/running への dismiss は不可 |
| `test_start_resets_running_jobs` | 起動時 running が failed にリセットされる + reason 記録 |
| `test_stop_graceful_shutdown` | stop() が timeout 内なら running を待つ |
| `test_stop_timeout_cancels_running` | timeout 超過で running が cancelled になる |
| `test_run_job_uses_dedicated_session` | _run_job が専用セッションを使う |

### 12.2 Web APIテスト: `test_analysis_jobs.py`

| テストケース | 内容 |
|---|---|
| `test_create_job` | POST で 201、pendingジョブ作成 |
| `test_create_job_returns_existing_with_200` | 重複時は 200 + 既存job_id返却 |
| `test_get_job_status` | GET /{id} で各フィールド返却 |
| `test_get_job_404` | 存在しないIDで 404 |
| `test_list_jobs` | GET / で一覧（上限20件） |
| `test_list_jobs_with_filters` | company_id/filing_id/status フィルタが効く |
| `test_list_jobs_excludes_dismissed_by_default` | dismissed が除外される |
| `test_delete_job_cancels_pending` | DELETE で pending → cancelled |
| `test_delete_job_cancels_running` | DELETE で running → cancelled |
| `test_dismiss_endpoint_marks_dismissed` | POST /dismiss で dismissed_at 更新 |
| `test_create_job_requires_auth` | 未認証で 403 |

### 12.3 ダッシュボードテスト

既存のダッシュボードテストがあれば、右下パネルの表示内容を「LLM分析キュー」に更新。`dismiss` ボタンと `cancel` ボタンの存在を検証。

### 12.4 既存テストへの影響

- `POST /api/stocks/{company_id}/rag/analyze` のテストは **そのまま維持**（deprecated だが動作は変えない）
- 新規ファイル `test_analysis_jobs.py` を追加

---

## 13. 実装ファイル一覧

### 新規ファイル

| パス | 内容 |
|---|---|
| `src/stock_analyze_system/models/analysis_job.py` | `AnalysisJob` モデル + `JobStatus` enum + partial unique index |
| `src/stock_analyze_system/repositories/analysis_job.py` | `AnalysisJobRepository` |
| `src/stock_analyze_system/services/analysis_queue.py` | `AnalysisQueueService` + `AnalysisFailedError` |
| `src/stock_analyze_system/web/routes/analysis_jobs.py` | APIエンドポイント5件 |
| `tests/unit/services/test_analysis_queue.py` | キューサービスユニットテスト |
| `tests/unit/web/test_analysis_jobs.py` | Web APIテスト |

### 改修ファイル

| パス | 内容 |
|---|---|
| `src/stock_analyze_system/models/__init__.py` | 新モデル登録 |
| `src/stock_analyze_system/web/dependencies.py` | `AppState` に `analysis_queue` + `session_factory` 追加 |
| `src/stock_analyze_system/web/app.py` | lifespan で start/stop 呼び出し |
| `src/stock_analyze_system/web/routes/api.py` | `analysis_jobs` ルータ include + 旧エンドポイントに deprecated warning |
| `src/stock_analyze_system/web/routes/dashboard.py` | キューデータ取得（必要なら） |
| `src/stock_analyze_system/web/templates/dashboard.html` | 「LLM分析」→「LLM分析キュー」パネルに変更 |
| `src/stock_analyze_system/web/static/app.js` | 分析タブの自動検出ポーリング・ダッシュボードのキューポーリング・dismiss/cancel ボタン |
| `src/stock_analyze_system/web/templates/stocks/_tab_analysis.html` | 「再実行」ボタン追加 |

---

## 14. 制約・留意事項

### 14.1 単一ユーザー前提
本 Web アプリは単一ユーザー（自分・身内のみ）で運用される。そのため：

- `created_by` カラムは持たない
- ジョブは全員から見える（dismiss スコープも単一）
- 認可は「ログイン済みかどうか」のみ

将来マルチユーザー化する場合は `created_by` カラム追加と dismiss スコープの再設計が必要。

### 14.2 スケーリング
- 同時実行数は **1件固定**。複数社の分析はキューイングして順次実行する
- SQLite 上のテーブルなので、ジョブ数が数千件を超えると一覧取得が遅くなる可能性（現状は分析頻度が低いため問題なし）

### 14.3 ワーカーの隔離
- `_run_job` 内で専用の `AsyncSession` と `ServiceContainer` を構築する
- これにより、ワーカーのDBセッションとWebリクエストのセッションが混在しない
- `PageIndexService` は内部的に `asyncio.Semaphore` を持つが、本キューと旧 NDJSON エンドポイントは独立して動作するため、両方が同時実行される時間帯では LLM 推論が並走する可能性あり（許容）

### 14.4 ワーカー単一性の前提
- `_dequeue_next` は原子的 UPDATE で実装されており、複数ワーカーが立ち上がっても二重実行は防げる
- ただし運用上は uvicorn `workers=1` で起動することを想定（複数ワーカー時のキャンセル機能は `_running_tasks` がプロセスローカルなため不完全になる）

### 14.5 キャッシュの再利用
- `RagService.run_full_analysis_stream` 内部でキャッシュチェックが行われる
- `failed` ジョブの再実行時、成功したタイプはキャッシュヒットでスキップされ、失敗したタイプのみ再試行される

### 14.6 タイムゾーン
- 新テーブル `analysis_jobs` のすべての datetime カラムは `DateTime(timezone=True)` で UTC 保存
- API レスポンスは ISO8601 UTC（末尾 `Z`）
- UI 側で UTC → ブラウザローカル時刻に変換して表示

### 14.7 セキュリティ
- `POST /api/analysis-jobs` は認証必須（既存 `AuthMiddleware` の対象）
- `DELETE` / `POST /dismiss` も認証必須
- レートリミットは `heavy_rate_limiter` を `POST /api/analysis-jobs` に適用

---

## 15. 将来拡張（今回はスコープ外）

- **ジョブ履歴ダッシュボード**: completed ジョブの履歴を長期保持し、分析実行回数の統計を出す
- **優先度キュー**: 重要企業の分析を優先実行
- **並列実行数の設定可能化**: 設定ファイルで `max_concurrent_analysis` を変更可能にする
- **マルチユーザー化**: `created_by` 追加・ジョブ可視性スコープ再設計
- **WebSocket / SSE による push 通知**: 5 秒ポーリングを置き換え
