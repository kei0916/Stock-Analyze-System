# バックグラウンドLLM分析キュー Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** RAG 定型分析をバックグラウンドキューで実行し、ブラウザを閉じても分析を継続できるようにする。

**Architecture:** SQLite 上の `analysis_jobs` テーブル + `asyncio.Task` ワーカー + `RagService.run_full_analysis_stream` のイベント消費。partial unique index と原子的 dequeue で並行性を担保。

**Tech Stack:** Python 3.x / FastAPI / SQLAlchemy 2.x async / aiosqlite / pytest-asyncio / Vanilla JS

**設計仕様:** `docs/superpowers/specs/2026-05-10-background-analysis-queue-design.md`

---

## File Structure

### 新規ファイル

| パス | 責務 |
|---|---|
| `src/stock_analyze_system/models/analysis_job.py` | `AnalysisJob` モデル + `JobStatus` enum + partial unique index |
| `src/stock_analyze_system/repositories/analysis_job.py` | `AnalysisJobRepository`（atomic dequeue を含む） |
| `src/stock_analyze_system/services/analysis_queue.py` | `AnalysisQueueService` + `AnalysisFailedError` + `now_utc()` |
| `src/stock_analyze_system/web/routes/analysis_jobs.py` | API ルータ（5 エンドポイント） |
| `tests/unit/repositories/test_analysis_job_repo.py` | リポジトリの単体テスト |
| `tests/unit/services/test_analysis_queue.py` | キューサービスの単体テスト |
| `tests/unit/web/test_analysis_jobs.py` | Web API テスト |

### 改修ファイル

| パス | 内容 |
|---|---|
| `src/stock_analyze_system/models/__init__.py` | `AnalysisJob` の import 追加 |
| `tests/conftest.py` | `AnalysisJob` の `noqa: F401` 追加 |
| `src/stock_analyze_system/web/dependencies.py` | `AppState` に `session_factory`/`analysis_queue` 追加 |
| `src/stock_analyze_system/web/app.py` | lifespan で `analysis_queue.start/stop`、ルータ include |
| `src/stock_analyze_system/web/routes/api.py` | 旧 `POST /rag/analyze` に deprecation warning + OpenAPI flag |
| `src/stock_analyze_system/web/templates/dashboard.html` | 「LLM分析」→「LLM分析キュー」パネル |
| `src/stock_analyze_system/web/static/app.js` | ダッシュボード キューポーリング、分析タブ復帰検出、再実行/キャンセル/dismiss |
| `src/stock_analyze_system/web/templates/stocks/_tab_analysis.html` | 「再実行」ボタン |

---

## 共通: テスト実行コマンド

すべてのテストは `pytest -p no:cacheprovider` を base に走らせる。各タスクで具体的な対象を指定する。

ユニットテストは `infisical` 不要（環境変数を読まない）。Web テストもインメモリ DB で完結。

---

## Task 1: `AnalysisJob` モデル + `JobStatus` enum

**Files:**
- Create: `src/stock_analyze_system/models/analysis_job.py`
- Modify: `src/stock_analyze_system/models/__init__.py`
- Modify: `tests/conftest.py`
- Test: `tests/unit/models/test_analysis_job.py` (Create)

### Step 1: テストファイルを作成（失敗するテスト）

- [ ] `tests/unit/models/test_analysis_job.py` を作成

```python
"""AnalysisJob モデル単体テスト"""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing


@pytest.fixture
async def sample_filing(session, sample_company):
    filing = Filing(
        company_id=sample_company.id,
        source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000320193-24-000123",
    )
    session.add(filing)
    await session.flush()
    return filing


class TestJobStatus:
    def test_enum_values(self):
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        assert JobStatus.COMPLETED.value == "completed"
        assert JobStatus.FAILED.value == "failed"
        assert JobStatus.CANCELLED.value == "cancelled"


class TestAnalysisJobModel:
    async def test_create_with_defaults(self, session, sample_filing):
        job = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        session.add(job)
        await session.flush()

        assert job.id is not None
        assert job.status == JobStatus.PENDING.value
        assert job.progress_current == 0
        assert job.progress_total == 4
        assert job.current_analysis_type is None
        assert job.error_details is None
        assert job.created_at is not None
        assert job.started_at is None
        assert job.completed_at is None
        assert job.dismissed_at is None

    async def test_partial_unique_index_blocks_duplicate_pending(
        self, session, sample_filing,
    ):
        """同 (company_id, filing_id) で pending 2 件は不可"""
        job1 = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.PENDING.value,
        )
        session.add(job1)
        await session.flush()

        job2 = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.PENDING.value,
        )
        session.add(job2)
        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_partial_unique_index_allows_completed_plus_pending(
        self, session, sample_filing,
    ):
        """completed が既存でも、新しい pending は作成できる"""
        completed = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.COMPLETED.value,
        )
        session.add(completed)
        await session.flush()

        new_pending = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.PENDING.value,
        )
        session.add(new_pending)
        await session.flush()

        result = await session.execute(
            select(AnalysisJob).where(
                AnalysisJob.company_id == sample_filing.company_id,
            )
        )
        assert len(list(result.scalars().all())) == 2
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/models/test_analysis_job.py -v`
- [ ] Expected: ImportError（`analysis_job` モジュールが存在しない）

### Step 3: モデルファイルを作成

- [ ] `src/stock_analyze_system/models/analysis_job.py` を作成

```python
"""バックグラウンド LLM 分析ジョブモデル"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from stock_analyze_system.models.base import Base


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
    status: Mapped[str] = mapped_column(
        String(20), default=JobStatus.PENDING.value,
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

    __table_args__ = (
        Index(
            "uq_analysis_jobs_active",
            "company_id", "filing_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
    )
```

### Step 4: モデル登録 + テストフィクスチャ更新

- [ ] `src/stock_analyze_system/models/__init__.py` に追記

```python
# 末尾に追加
from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus  # noqa: F401
```

- [ ] `tests/conftest.py` の冒頭 import セクションに追記（既存の `# noqa: F401` 群と同じ位置）

```python
from stock_analyze_system.models.analysis_job import AnalysisJob  # noqa: F401
```

### Step 5: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/models/test_analysis_job.py -v`
- [ ] Expected: 4 tests PASSED

### Step 6: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/models/analysis_job.py \
        src/stock_analyze_system/models/__init__.py \
        tests/conftest.py \
        tests/unit/models/test_analysis_job.py
git commit -m "feat(model): add AnalysisJob with partial unique index"
```

---

## Task 2: `AnalysisJobRepository` - create / find_active / get / list

**Files:**
- Create: `src/stock_analyze_system/repositories/analysis_job.py`
- Test: `tests/unit/repositories/test_analysis_job_repo.py` (Create)

### Step 1: テストファイル作成

- [ ] `tests/unit/repositories/test_analysis_job_repo.py` を作成

```python
"""AnalysisJobRepository 単体テスト"""
from __future__ import annotations

import pytest

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.analysis_job import AnalysisJobRepository


@pytest.fixture
async def sample_filing(session, sample_company):
    filing = Filing(
        company_id=sample_company.id,
        source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000320193-24-000123",
    )
    session.add(filing)
    await session.flush()
    return filing


@pytest.fixture
async def sample_filing_2(session, sample_company):
    filing = Filing(
        company_id=sample_company.id,
        source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2023,
        accession_no="0000320193-23-000999",
    )
    session.add(filing)
    await session.flush()
    return filing


class TestAnalysisJobRepoBasics:
    async def test_create_returns_pending_job(self, session, sample_filing):
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        assert job.id is not None
        assert job.status == JobStatus.PENDING.value
        assert job.company_id == sample_filing.company_id
        assert job.filing_id == sample_filing.id

    async def test_get_returns_job_by_id(self, session, sample_filing):
        repo = AnalysisJobRepository(session)
        created = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        fetched = await repo.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    async def test_get_returns_none_for_missing_id(self, session):
        repo = AnalysisJobRepository(session)
        assert await repo.get(99999) is None

    async def test_find_active_returns_pending(self, session, sample_filing):
        repo = AnalysisJobRepository(session)
        created = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        found = await repo.find_active_by_company_filing(
            sample_filing.company_id, sample_filing.id,
        )
        assert found is not None
        assert found.id == created.id

    async def test_find_active_returns_none_when_completed(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.COMPLETED.value,
        )
        session.add(job)
        await session.flush()

        found = await repo.find_active_by_company_filing(
            sample_filing.company_id, sample_filing.id,
        )
        assert found is None

    async def test_list_filters_by_status(
        self, session, sample_filing, sample_filing_2,
    ):
        repo = AnalysisJobRepository(session)
        await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        running = AnalysisJob(
            company_id=sample_filing_2.company_id,
            filing_id=sample_filing_2.id,
            status=JobStatus.RUNNING.value,
        )
        session.add(running)
        await session.flush()

        pending_only = await repo.list(statuses=[JobStatus.PENDING])
        assert len(pending_only) == 1
        assert pending_only[0].status == JobStatus.PENDING.value

        all_active = await repo.list(
            statuses=[JobStatus.PENDING, JobStatus.RUNNING],
        )
        assert len(all_active) == 2

    async def test_list_filters_by_company_filing(
        self, session, sample_filing, sample_filing_2,
    ):
        repo = AnalysisJobRepository(session)
        await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await repo.create(
            company_id=sample_filing_2.company_id,
            filing_id=sample_filing_2.id,
        )

        only_first = await repo.list(filing_id=sample_filing.id)
        assert len(only_first) == 1
        assert only_first[0].filing_id == sample_filing.id

    async def test_list_excludes_dismissed_by_default(
        self, session, sample_filing,
    ):
        from datetime import datetime, timezone
        repo = AnalysisJobRepository(session)
        dismissed = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.FAILED.value,
            dismissed_at=datetime.now(timezone.utc),
        )
        session.add(dismissed)
        await session.flush()

        result = await repo.list(statuses=[JobStatus.FAILED])
        assert result == []

        with_dismissed = await repo.list(
            statuses=[JobStatus.FAILED], include_dismissed=True,
        )
        assert len(with_dismissed) == 1
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/repositories/test_analysis_job_repo.py -v`
- [ ] Expected: ImportError

### Step 3: リポジトリ実装

- [ ] `src/stock_analyze_system/repositories/analysis_job.py` を作成

```python
"""AnalysisJob リポジトリ"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus


class AnalysisJobRepository:
    """AnalysisJob ドメインリポジトリ"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(self, *, company_id: str, filing_id: int) -> AnalysisJob:
        job = AnalysisJob(
            company_id=company_id,
            filing_id=filing_id,
            status=JobStatus.PENDING.value,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def get(self, job_id: int) -> AnalysisJob | None:
        return await self._session.get(AnalysisJob, job_id)

    async def find_active_by_company_filing(
        self, company_id: str, filing_id: int,
    ) -> AnalysisJob | None:
        stmt = select(AnalysisJob).where(
            AnalysisJob.company_id == company_id,
            AnalysisJob.filing_id == filing_id,
            AnalysisJob.status.in_(
                [JobStatus.PENDING.value, JobStatus.RUNNING.value],
            ),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        company_id: str | None = None,
        filing_id: int | None = None,
        statuses: list[JobStatus] | None = None,
        include_dismissed: bool = False,
        limit: int = 20,
    ) -> list[AnalysisJob]:
        stmt = select(AnalysisJob)
        if company_id is not None:
            stmt = stmt.where(AnalysisJob.company_id == company_id)
        if filing_id is not None:
            stmt = stmt.where(AnalysisJob.filing_id == filing_id)
        if statuses is not None:
            stmt = stmt.where(
                AnalysisJob.status.in_([s.value for s in statuses]),
            )
        if not include_dismissed:
            stmt = stmt.where(AnalysisJob.dismissed_at.is_(None))
        stmt = stmt.order_by(AnalysisJob.created_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/repositories/test_analysis_job_repo.py -v`
- [ ] Expected: 8 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/repositories/analysis_job.py \
        tests/unit/repositories/test_analysis_job_repo.py
git commit -m "feat(repo): add AnalysisJobRepository with create/get/find_active/list"
```

---

## Task 3: `AnalysisJobRepository` - 原子的 dequeue

**Files:**
- Modify: `src/stock_analyze_system/repositories/analysis_job.py`
- Modify: `tests/unit/repositories/test_analysis_job_repo.py`

### Step 1: 失敗テスト追加

- [ ] `tests/unit/repositories/test_analysis_job_repo.py` の末尾に追加

```python
class TestAnalysisJobRepoDequeue:
    async def test_dequeue_next_returns_oldest_pending_and_marks_running(
        self, session, sample_filing, sample_filing_2,
    ):
        repo = AnalysisJobRepository(session)
        first = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await repo.create(
            company_id=sample_filing_2.company_id,
            filing_id=sample_filing_2.id,
        )
        await session.commit()  # commit to make created_at deterministic

        dequeued = await repo.dequeue_next()
        assert dequeued is not None
        assert dequeued.id == first.id
        assert dequeued.status == JobStatus.RUNNING.value
        assert dequeued.started_at is not None

    async def test_dequeue_next_returns_none_when_empty(self, session):
        repo = AnalysisJobRepository(session)
        result = await repo.dequeue_next()
        assert result is None

    async def test_dequeue_next_skips_running(
        self, session, sample_filing,
    ):
        """既に running のジョブは取らない"""
        running = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.RUNNING.value,
        )
        session.add(running)
        await session.flush()

        repo = AnalysisJobRepository(session)
        result = await repo.dequeue_next()
        assert result is None

    async def test_dequeue_next_atomic_no_double_take(
        self, session, sample_filing,
    ):
        """同じ pending を 2 回 dequeue しても 2 回目は None"""
        repo = AnalysisJobRepository(session)
        await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()

        first = await repo.dequeue_next()
        second = await repo.dequeue_next()

        assert first is not None
        assert second is None
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/repositories/test_analysis_job_repo.py::TestAnalysisJobRepoDequeue -v`
- [ ] Expected: AttributeError（`dequeue_next` メソッドなし）

### Step 3: 実装追加

- [ ] `src/stock_analyze_system/repositories/analysis_job.py` の末尾に追加

```python
    async def dequeue_next(self) -> AnalysisJob | None:
        """最古の pending を原子的に running に遷移させ、ジョブを返す。

        rowcount を見ることで複数ワーカー間の競合に耐性を持つ。
        他ワーカーが先に取った場合は None を返す。
        """
        from datetime import datetime, timezone
        from sqlalchemy import update

        stmt = (
            select(AnalysisJob.id)
            .where(AnalysisJob.status == JobStatus.PENDING.value)
            .order_by(AnalysisJob.created_at.asc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        candidate_id = result.scalar_one_or_none()
        if candidate_id is None:
            return None

        now = datetime.now(timezone.utc)
        update_stmt = (
            update(AnalysisJob)
            .where(
                AnalysisJob.id == candidate_id,
                AnalysisJob.status == JobStatus.PENDING.value,
            )
            .values(
                status=JobStatus.RUNNING.value,
                started_at=now,
            )
        )
        update_result = await self._session.execute(update_stmt)
        await self._session.commit()

        if update_result.rowcount == 0:
            return None

        # commit 後に再取得（最新値を確実に返す）
        return await self._session.get(AnalysisJob, candidate_id)
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/repositories/test_analysis_job_repo.py -v`
- [ ] Expected: 12 tests PASSED（既存 8 + 新規 4）

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/repositories/analysis_job.py \
        tests/unit/repositories/test_analysis_job_repo.py
git commit -m "feat(repo): add atomic dequeue_next to AnalysisJobRepository"
```

---

## Task 4: `AnalysisJobRepository` - update_status / update_progress

**Files:**
- Modify: `src/stock_analyze_system/repositories/analysis_job.py`
- Modify: `tests/unit/repositories/test_analysis_job_repo.py`

### Step 1: 失敗テスト追加

- [ ] `tests/unit/repositories/test_analysis_job_repo.py` の末尾に追加

```python
class TestAnalysisJobRepoUpdate:
    async def test_update_status_to_completed(self, session, sample_filing):
        from datetime import datetime, timezone
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()
        completed_at = datetime.now(timezone.utc)
        await repo.update_status(
            job.id, JobStatus.COMPLETED, completed_at=completed_at,
        )

        fetched = await repo.get(job.id)
        assert fetched.status == JobStatus.COMPLETED.value
        assert fetched.completed_at is not None

    async def test_update_status_with_error_details(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()

        await repo.update_status(
            job.id, JobStatus.FAILED,
            error_details={"failed_types": [
                {"type": "mda", "message": "timeout"},
            ]},
        )
        fetched = await repo.get(job.id)
        assert fetched.status == JobStatus.FAILED.value
        assert fetched.error_details["failed_types"][0]["type"] == "mda"

    async def test_update_progress_partial_fields(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = await repo.create(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
        )
        await session.commit()

        await repo.update_progress(
            job.id, current=2, current_type="mda",
        )
        fetched = await repo.get(job.id)
        assert fetched.progress_current == 2
        assert fetched.current_analysis_type == "mda"
        assert fetched.progress_total == 4  # 未指定なら維持

        await repo.update_progress(job.id, current_type=None)
        fetched = await repo.get(job.id)
        assert fetched.current_analysis_type is None
        assert fetched.progress_current == 2  # 未指定なら維持
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/repositories/test_analysis_job_repo.py::TestAnalysisJobRepoUpdate -v`
- [ ] Expected: AttributeError

### Step 3: 実装追加

- [ ] `src/stock_analyze_system/repositories/analysis_job.py` の末尾に追加

```python
    async def update_status(
        self,
        job_id: int,
        status: JobStatus,
        *,
        completed_at=None,
        error_details: dict | None = None,
    ) -> None:
        """ジョブの status を遷移させる。指定された付随フィールドのみ更新。"""
        from sqlalchemy import update

        values: dict = {"status": status.value}
        if completed_at is not None:
            values["completed_at"] = completed_at
        if error_details is not None:
            values["error_details"] = error_details

        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def update_progress(
        self,
        job_id: int,
        *,
        current: int | None = None,
        current_type: str | None = ...,
        total: int | None = None,
    ) -> None:
        """進捗を更新。`current_type` は明示的に None も許容するため sentinel `...` を使う。"""
        from sqlalchemy import update

        values: dict = {}
        if current is not None:
            values["progress_current"] = current
        if current_type is not ...:
            values["current_analysis_type"] = current_type
        if total is not None:
            values["progress_total"] = total
        if not values:
            return

        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.commit()
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/repositories/test_analysis_job_repo.py -v`
- [ ] Expected: 15 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/repositories/analysis_job.py \
        tests/unit/repositories/test_analysis_job_repo.py
git commit -m "feat(repo): add update_status and update_progress"
```

---

## Task 5: `AnalysisJobRepository` - dismiss / reset_running

**Files:**
- Modify: `src/stock_analyze_system/repositories/analysis_job.py`
- Modify: `tests/unit/repositories/test_analysis_job_repo.py`

### Step 1: 失敗テスト追加

- [ ] `tests/unit/repositories/test_analysis_job_repo.py` の末尾に追加

```python
class TestAnalysisJobRepoDismissReset:
    async def test_dismiss_marks_dismissed_at(
        self, session, sample_filing,
    ):
        repo = AnalysisJobRepository(session)
        job = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.FAILED.value,
        )
        session.add(job)
        await session.commit()

        await repo.dismiss(job.id)
        fetched = await repo.get(job.id)
        assert fetched.dismissed_at is not None

    async def test_dismiss_past_for_filing_marks_failed_and_cancelled(
        self, session, sample_filing,
    ):
        """同 filing の failed/cancelled をまとめて dismiss"""
        failed = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.FAILED.value,
        )
        cancelled = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.CANCELLED.value,
        )
        completed = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.COMPLETED.value,  # completed は対象外
        )
        session.add_all([failed, cancelled, completed])
        await session.commit()

        repo = AnalysisJobRepository(session)
        count = await repo.dismiss_past_for_filing(
            sample_filing.company_id, sample_filing.id,
        )
        assert count == 2

        for job in [failed, cancelled]:
            await session.refresh(job)
            assert job.dismissed_at is not None
        await session.refresh(completed)
        assert completed.dismissed_at is None

    async def test_reset_running_to_failed_records_reason(
        self, session, sample_filing,
    ):
        running = AnalysisJob(
            company_id=sample_filing.company_id,
            filing_id=sample_filing.id,
            status=JobStatus.RUNNING.value,
        )
        session.add(running)
        await session.commit()

        repo = AnalysisJobRepository(session)
        count = await repo.reset_running_to_failed(
            reason="Server restarted while running",
        )
        assert count == 1

        await session.refresh(running)
        assert running.status == JobStatus.FAILED.value
        assert running.error_details == {
            "reason": "Server restarted while running",
        }
        assert running.completed_at is not None
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/repositories/test_analysis_job_repo.py::TestAnalysisJobRepoDismissReset -v`
- [ ] Expected: AttributeError

### Step 3: 実装追加

- [ ] `src/stock_analyze_system/repositories/analysis_job.py` の末尾に追加

```python
    async def dismiss(self, job_id: int) -> None:
        from datetime import datetime, timezone
        from sqlalchemy import update

        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id)
            .values(dismissed_at=datetime.now(timezone.utc))
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def dismiss_past_for_filing(
        self, company_id: str, filing_id: int,
    ) -> int:
        """同 filing の failed/cancelled (未 dismiss) を dismiss する。"""
        from datetime import datetime, timezone
        from sqlalchemy import update

        stmt = (
            update(AnalysisJob)
            .where(
                AnalysisJob.company_id == company_id,
                AnalysisJob.filing_id == filing_id,
                AnalysisJob.status.in_(
                    [JobStatus.FAILED.value, JobStatus.CANCELLED.value],
                ),
                AnalysisJob.dismissed_at.is_(None),
            )
            .values(dismissed_at=datetime.now(timezone.utc))
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount

    async def reset_running_to_failed(self, *, reason: str) -> int:
        """running を failed にリセット（起動時復旧用）。"""
        from datetime import datetime, timezone
        from sqlalchemy import update

        stmt = (
            update(AnalysisJob)
            .where(AnalysisJob.status == JobStatus.RUNNING.value)
            .values(
                status=JobStatus.FAILED.value,
                error_details={"reason": reason},
                completed_at=datetime.now(timezone.utc),
            )
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/repositories/test_analysis_job_repo.py -v`
- [ ] Expected: 18 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/repositories/analysis_job.py \
        tests/unit/repositories/test_analysis_job_repo.py
git commit -m "feat(repo): add dismiss and reset_running_to_failed"
```

---

## Task 6: `AnalysisQueueService` skeleton + `now_utc` + `AnalysisFailedError`

**Files:**
- Create: `src/stock_analyze_system/services/analysis_queue.py`
- Test: `tests/unit/services/test_analysis_queue.py` (Create)

### Step 1: テストファイル作成（最小スキャフォールド検証）

- [ ] `tests/unit/services/test_analysis_queue.py` を作成

```python
"""AnalysisQueueService 単体テスト"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from stock_analyze_system.services.analysis_queue import (
    AnalysisFailedError,
    AnalysisQueueService,
    now_utc,
)


def test_now_utc_returns_aware_datetime():
    n = now_utc()
    assert isinstance(n, datetime)
    assert n.tzinfo is not None
    assert n.tzinfo.utcoffset(n) == timezone.utc.utcoffset(n)


def test_analysis_failed_error_carries_failed_types():
    err = AnalysisFailedError([
        {"type": "mda", "message": "timeout"},
    ])
    assert err.failed_types[0]["type"] == "mda"
    assert "mda" in str(err)


def test_analysis_queue_service_can_be_instantiated():
    svc = AnalysisQueueService(
        session_factory=lambda: None,
        config=None,
        clients=None,
    )
    assert svc is not None
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/services/test_analysis_queue.py -v`
- [ ] Expected: ImportError

### Step 3: スキャフォールド実装

- [ ] `src/stock_analyze_system/services/analysis_queue.py` を作成

```python
"""バックグラウンド LLM 分析キューサービス"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.repositories.analysis_job import AnalysisJobRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from stock_analyze_system.config import AppConfig
    from stock_analyze_system.web.dependencies import ClientBundle

logger = logging.getLogger(__name__)


def now_utc() -> datetime:
    """タイムゾーン付きの現在時刻 (UTC) を返す。"""
    return datetime.now(timezone.utc)


class AnalysisFailedError(Exception):
    """分析タイプの一部または全てが失敗したことを示す例外。"""

    def __init__(self, failed_types: list[dict]):
        self.failed_types = failed_types
        types = ", ".join(f["type"] for f in failed_types if f.get("type"))
        super().__init__(f"Analysis failed for: {types}")


class AnalysisQueueService:
    """LLM 分析ジョブのバックグラウンド実行を管理するサービス。"""

    def __init__(
        self,
        session_factory,
        config,
        clients,
    ):
        self._session_factory = session_factory
        self._config = config
        self._clients = clients
        self._worker_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._wakeup_event = asyncio.Event()
        self._running_tasks: dict[int, asyncio.Task] = {}
        self._enqueue_lock = asyncio.Lock()
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/services/test_analysis_queue.py -v`
- [ ] Expected: 3 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/services/analysis_queue.py \
        tests/unit/services/test_analysis_queue.py
git commit -m "feat(service): add AnalysisQueueService skeleton with now_utc and AnalysisFailedError"
```

---

## Task 7: `AnalysisQueueService.enqueue` (ロック + 自動 dismiss + 重複防止)

**Files:**
- Modify: `src/stock_analyze_system/services/analysis_queue.py`
- Modify: `tests/unit/services/test_analysis_queue.py`

**設計ノート:** テストでは実 SQLite (in-memory) を使う。`session_factory` には `async_sessionmaker(engine, expire_on_commit=False)` を渡す。

### Step 1: テスト用ヘルパフィクスチャを追加

- [ ] `tests/unit/services/test_analysis_queue.py` 末尾に追加

```python
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing


@pytest.fixture
async def session_factory(async_engine):
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
async def seed_company_and_filing(session_factory):
    async with session_factory() as s:
        company = Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc.",
            market="NASDAQ", accounting_standard="US-GAAP",
        )
        s.add(company)
        await s.flush()
        filing = Filing(
            company_id=company.id,
            source="SEC", filing_type="10-K",
            period_type="annual", fiscal_year=2024,
            accession_no="0000320193-24-000123",
        )
        s.add(filing)
        await s.commit()
        return company.id, filing.id


@pytest.fixture
def queue_service(session_factory):
    return AnalysisQueueService(
        session_factory=session_factory,
        config=None,
        clients=None,
    )


class TestEnqueue:
    async def test_enqueue_creates_pending_job(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        company_id, filing_id = seed_company_and_filing
        job = await queue_service.enqueue(company_id, filing_id)
        assert job.id is not None
        assert job.status == JobStatus.PENDING.value

        async with session_factory() as s:
            fetched = await s.get(AnalysisJob, job.id)
            assert fetched is not None

    async def test_enqueue_returns_existing_for_duplicate_pending(
        self, queue_service, seed_company_and_filing,
    ):
        company_id, filing_id = seed_company_and_filing
        first = await queue_service.enqueue(company_id, filing_id)
        second = await queue_service.enqueue(company_id, filing_id)
        assert first.id == second.id

    async def test_enqueue_dismisses_past_failed(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        company_id, filing_id = seed_company_and_filing
        async with session_factory() as s:
            failed = AnalysisJob(
                company_id=company_id,
                filing_id=filing_id,
                status=JobStatus.FAILED.value,
            )
            s.add(failed)
            await s.commit()
            failed_id = failed.id

        await queue_service.enqueue(company_id, filing_id)

        async with session_factory() as s:
            updated = await s.get(AnalysisJob, failed_id)
            assert updated.dismissed_at is not None

    async def test_enqueue_sets_wakeup_event(
        self, queue_service, seed_company_and_filing,
    ):
        company_id, filing_id = seed_company_and_filing
        queue_service._wakeup_event.clear()
        await queue_service.enqueue(company_id, filing_id)
        assert queue_service._wakeup_event.is_set()
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/services/test_analysis_queue.py::TestEnqueue -v`
- [ ] Expected: AttributeError on `enqueue`

### Step 3: 実装追加

- [ ] `src/stock_analyze_system/services/analysis_queue.py` 末尾に追加（`AnalysisQueueService` クラスのメソッドとして）

```python
    async def enqueue(self, company_id: str, filing_id: int) -> AnalysisJob:
        """ジョブを enqueue。重複時は既存 pending/running を返却。"""
        from sqlalchemy.exc import IntegrityError

        async with self._enqueue_lock:
            async with self._session_factory() as session:
                repo = AnalysisJobRepository(session)

                existing = await repo.find_active_by_company_filing(
                    company_id, filing_id,
                )
                if existing is not None:
                    self._wakeup_event.set()
                    return existing

                # 同 filing の過去 failed/cancelled を自動 dismiss
                await repo.dismiss_past_for_filing(company_id, filing_id)

                try:
                    job = await repo.create(
                        company_id=company_id, filing_id=filing_id,
                    )
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    existing = await repo.find_active_by_company_filing(
                        company_id, filing_id,
                    )
                    if existing is not None:
                        self._wakeup_event.set()
                        return existing
                    raise

        self._wakeup_event.set()
        return job
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/services/test_analysis_queue.py -v`
- [ ] Expected: 7 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/services/analysis_queue.py \
        tests/unit/services/test_analysis_queue.py
git commit -m "feat(service): add enqueue with lock + dismiss past failed + IntegrityError fallback"
```

---

## Task 8: `AnalysisQueueService` - cancel / dismiss / get_status / list_jobs

**Files:**
- Modify: `src/stock_analyze_system/services/analysis_queue.py`
- Modify: `tests/unit/services/test_analysis_queue.py`

### Step 1: 失敗テスト追加

- [ ] `tests/unit/services/test_analysis_queue.py` 末尾に追加

```python
class TestCancelDismiss:
    async def test_cancel_pending_marks_cancelled(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        company_id, filing_id = seed_company_and_filing
        job = await queue_service.enqueue(company_id, filing_id)
        cancelled = await queue_service.cancel(job.id)

        assert cancelled is not None
        assert cancelled.status == JobStatus.CANCELLED.value
        assert cancelled.completed_at is not None

    async def test_cancel_running_calls_task_cancel(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        """running ジョブのキャンセルは _running_tasks の Task を cancel する"""
        company_id, filing_id = seed_company_and_filing
        async with session_factory() as s:
            running = AnalysisJob(
                company_id=company_id,
                filing_id=filing_id,
                status=JobStatus.RUNNING.value,
            )
            s.add(running)
            await s.commit()
            job_id = running.id

        # ダミーの実行中 Task を登録
        async def _sleeping():
            await asyncio.sleep(60)

        task = asyncio.create_task(_sleeping())
        queue_service._running_tasks[job_id] = task
        try:
            await queue_service.cancel(job_id)
            assert task.cancelled() or task.cancelling() > 0
        finally:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, BaseException):
                pass

    async def test_cancel_returns_none_for_missing(self, queue_service):
        result = await queue_service.cancel(99999)
        assert result is None

    async def test_dismiss_marks_dismissed_at(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        company_id, filing_id = seed_company_and_filing
        async with session_factory() as s:
            failed = AnalysisJob(
                company_id=company_id,
                filing_id=filing_id,
                status=JobStatus.FAILED.value,
            )
            s.add(failed)
            await s.commit()
            job_id = failed.id

        result = await queue_service.dismiss(job_id)
        assert result is not None
        assert result.dismissed_at is not None

    async def test_dismiss_rejects_running(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        """pending/running の dismiss は ValueError"""
        company_id, filing_id = seed_company_and_filing
        async with session_factory() as s:
            running = AnalysisJob(
                company_id=company_id,
                filing_id=filing_id,
                status=JobStatus.RUNNING.value,
            )
            s.add(running)
            await s.commit()
            job_id = running.id

        with pytest.raises(ValueError):
            await queue_service.dismiss(job_id)

    async def test_get_status_returns_job(
        self, queue_service, seed_company_and_filing,
    ):
        company_id, filing_id = seed_company_and_filing
        job = await queue_service.enqueue(company_id, filing_id)
        fetched = await queue_service.get_status(job.id)
        assert fetched is not None
        assert fetched.id == job.id

    async def test_list_jobs_passes_filters(
        self, queue_service, seed_company_and_filing,
    ):
        company_id, filing_id = seed_company_and_filing
        await queue_service.enqueue(company_id, filing_id)
        result = await queue_service.list_jobs(
            statuses=[JobStatus.PENDING],
        )
        assert len(result) == 1
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/services/test_analysis_queue.py::TestCancelDismiss -v`
- [ ] Expected: AttributeError

### Step 3: 実装追加

- [ ] `src/stock_analyze_system/services/analysis_queue.py` 末尾の `AnalysisQueueService` クラスに追加

```python
    async def cancel(self, job_id: int) -> AnalysisJob | None:
        """ジョブをキャンセル。pending → 直接 cancelled、running → Task.cancel()。"""
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            job = await repo.get(job_id)
            if job is None:
                return None

            if job.status == JobStatus.PENDING.value:
                await repo.update_status(
                    job_id, JobStatus.CANCELLED, completed_at=now_utc(),
                )
                return await repo.get(job_id)

            if job.status == JobStatus.RUNNING.value:
                task = self._running_tasks.get(job_id)
                if task is not None:
                    task.cancel()
                # ステータス更新はワーカーループ側
                return await repo.get(job_id)

            return job  # 既に終了状態

    async def dismiss(self, job_id: int) -> AnalysisJob | None:
        """完了状態のジョブを UI から非表示にする。"""
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            job = await repo.get(job_id)
            if job is None:
                return None
            allowed = {
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
                JobStatus.COMPLETED.value,
            }
            if job.status not in allowed:
                raise ValueError(
                    f"Cannot dismiss job in status: {job.status}",
                )
            await repo.dismiss(job_id)
            return await repo.get(job_id)

    async def get_status(self, job_id: int) -> AnalysisJob | None:
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            return await repo.get(job_id)

    async def list_jobs(
        self,
        *,
        company_id: str | None = None,
        filing_id: int | None = None,
        statuses: list[JobStatus] | None = None,
        include_dismissed: bool = False,
        limit: int = 20,
    ) -> list[AnalysisJob]:
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            return await repo.list(
                company_id=company_id,
                filing_id=filing_id,
                statuses=statuses,
                include_dismissed=include_dismissed,
                limit=limit,
            )
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/services/test_analysis_queue.py -v`
- [ ] Expected: 14 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/services/analysis_queue.py \
        tests/unit/services/test_analysis_queue.py
git commit -m "feat(service): add cancel/dismiss/get_status/list_jobs"
```

---

## Task 9: `AnalysisQueueService._run_job` - RagService イベント消費

**Files:**
- Modify: `src/stock_analyze_system/services/analysis_queue.py`
- Modify: `tests/unit/services/test_analysis_queue.py`

**設計ノート:** `_run_job` は内部で `setup_services` を呼ぶが、テストではモック化する。`setup_services` の差し替えは monkeypatch で行う。

### Step 1: 失敗テスト追加

- [ ] `tests/unit/services/test_analysis_queue.py` 末尾に追加

```python
class TestRunJob:
    async def test_run_job_consumes_event_stream_and_updates_progress(
        self, queue_service, seed_company_and_filing,
        session_factory, monkeypatch,
    ):
        from unittest.mock import AsyncMock, MagicMock
        company_id, filing_id = seed_company_and_filing
        job = await queue_service.enqueue(company_id, filing_id)

        async def fake_stream(filing):
            yield {"event": "fetching", "filing_id": filing.id}
            yield {"event": "indexing"}
            yield {"event": "started", "total": 4}
            yield {"event": "phase", "index": 0, "total": 4,
                   "analysis_type": "business_summary", "label": "事業概要"}
            yield {"event": "done", "index": 0, "analysis_type": "business_summary"}
            yield {"event": "phase", "index": 1, "total": 4,
                   "analysis_type": "mda", "label": "MD&A"}
            yield {"event": "cached", "index": 1, "analysis_type": "mda"}
            yield {"event": "phase", "index": 2, "total": 4,
                   "analysis_type": "risk_factors", "label": "リスク"}
            yield {"event": "done", "index": 2, "analysis_type": "risk_factors"}
            yield {"event": "phase", "index": 3, "total": 4,
                   "analysis_type": "business_outlook", "label": "見通し"}
            yield {"event": "done", "index": 3, "analysis_type": "business_outlook"}
            yield {"event": "complete"}

        fake_rag = MagicMock()
        fake_rag.run_full_analysis_stream = fake_stream
        fake_filing = MagicMock(id=filing_id)
        fake_filing_svc = MagicMock()
        fake_filing_svc.get_filing_by_id = AsyncMock(return_value=fake_filing)
        fake_container = MagicMock(
            rag_service=fake_rag,
            filing_service=fake_filing_svc,
        )

        async def fake_setup_services(session, config, *, clients=None):
            return fake_container

        monkeypatch.setattr(
            "stock_analyze_system.services.analysis_queue.setup_services",
            fake_setup_services,
        )

        await queue_service._run_job(job)

        async with session_factory() as s:
            fetched = await s.get(AnalysisJob, job.id)
        assert fetched.progress_current == 4
        assert fetched.current_analysis_type is None

    async def test_run_job_raises_on_partial_failure(
        self, queue_service, seed_company_and_filing,
        session_factory, monkeypatch,
    ):
        from unittest.mock import AsyncMock, MagicMock
        company_id, filing_id = seed_company_and_filing
        job = await queue_service.enqueue(company_id, filing_id)

        async def fake_stream(filing):
            yield {"event": "started", "total": 4}
            yield {"event": "phase", "index": 0, "total": 4,
                   "analysis_type": "mda", "label": "MD&A"}
            yield {"event": "error", "index": 0,
                   "analysis_type": "mda", "message": "request timeout"}
            yield {"event": "phase", "index": 1, "total": 4,
                   "analysis_type": "risk_factors", "label": "リスク"}
            yield {"event": "done", "index": 1, "analysis_type": "risk_factors"}
            yield {"event": "complete"}

        fake_rag = MagicMock()
        fake_rag.run_full_analysis_stream = fake_stream
        fake_filing = MagicMock(id=filing_id)
        fake_container = MagicMock(
            rag_service=fake_rag,
            filing_service=MagicMock(
                get_filing_by_id=AsyncMock(return_value=fake_filing),
            ),
        )
        monkeypatch.setattr(
            "stock_analyze_system.services.analysis_queue.setup_services",
            lambda s, c, *, clients=None: _wrap_async(fake_container),
        )

        with pytest.raises(AnalysisFailedError) as exc_info:
            await queue_service._run_job(job)
        assert exc_info.value.failed_types[0]["type"] == "mda"
        assert exc_info.value.failed_types[0]["message"] == "request timeout"

    async def test_run_job_raises_value_error_when_filing_missing(
        self, queue_service, seed_company_and_filing, monkeypatch,
    ):
        from unittest.mock import AsyncMock, MagicMock
        company_id, filing_id = seed_company_and_filing
        job = await queue_service.enqueue(company_id, filing_id)

        fake_container = MagicMock(
            rag_service=MagicMock(),
            filing_service=MagicMock(
                get_filing_by_id=AsyncMock(return_value=None),
            ),
        )
        monkeypatch.setattr(
            "stock_analyze_system.services.analysis_queue.setup_services",
            lambda s, c, *, clients=None: _wrap_async(fake_container),
        )

        with pytest.raises(ValueError):
            await queue_service._run_job(job)


async def _wrap_async(value):
    return value
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/services/test_analysis_queue.py::TestRunJob -v`
- [ ] Expected: AttributeError on `_run_job` または `setup_services` 未 import

### Step 3: 実装追加

- [ ] `src/stock_analyze_system/services/analysis_queue.py` の冒頭 import 群に追加

```python
from stock_analyze_system.cli.container import setup_services
```

- [ ] `AnalysisQueueService` クラスに追加

```python
    async def _run_job(self, job: AnalysisJob) -> None:
        """単一ジョブを実行。RagService.run_full_analysis_stream を消費する。"""
        failed_types: list[dict] = []
        progress_index = 0

        async with self._session_factory() as session:
            container = await setup_services(
                session, self._config, clients=self._clients,
            )
            rag = container.rag_service
            if rag is None:
                raise RuntimeError("RAG service is not enabled")
            filing = await container.filing_service.get_filing_by_id(
                job.filing_id,
            )
            if filing is None:
                raise ValueError(f"filing_id={job.filing_id} not found")

            repo = AnalysisJobRepository(session)

            async for event in rag.run_full_analysis_stream(filing):
                etype = event.get("event")
                if etype == "started":
                    await repo.update_progress(
                        job.id, total=event["total"],
                    )
                elif etype == "phase":
                    progress_index = event["index"]
                    await repo.update_progress(
                        job.id,
                        current=progress_index,
                        current_type=event["analysis_type"],
                    )
                elif etype in ("done", "cached"):
                    progress_index = event["index"] + 1
                    await repo.update_progress(
                        job.id, current=progress_index,
                    )
                elif etype == "error":
                    failed_types.append({
                        "type": event.get("analysis_type"),
                        "message": event.get("message", ""),
                    })

            await repo.update_progress(
                job.id, current=progress_index, current_type=None,
            )

        if failed_types:
            raise AnalysisFailedError(failed_types)
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/services/test_analysis_queue.py -v`
- [ ] Expected: 17 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/services/analysis_queue.py \
        tests/unit/services/test_analysis_queue.py
git commit -m "feat(service): add _run_job that consumes RagService event stream"
```

---

## Task 10: `AnalysisQueueService` - worker loop / start / stop

**Files:**
- Modify: `src/stock_analyze_system/services/analysis_queue.py`
- Modify: `tests/unit/services/test_analysis_queue.py`

**設計ノート:** ワーカーループは実時間 sleep を含む。テストでは `_run_job` をモック化し、短時間で完結させる。

### Step 1: 失敗テスト追加

- [ ] `tests/unit/services/test_analysis_queue.py` 末尾に追加

```python
class TestWorkerLifecycle:
    async def test_start_resets_running_jobs_to_failed(
        self, queue_service, seed_company_and_filing, session_factory,
    ):
        """start() で running ジョブが failed にリセットされる"""
        company_id, filing_id = seed_company_and_filing
        async with session_factory() as s:
            running = AnalysisJob(
                company_id=company_id,
                filing_id=filing_id,
                status=JobStatus.RUNNING.value,
            )
            s.add(running)
            await s.commit()
            job_id = running.id

        await queue_service.start()
        try:
            async with session_factory() as s:
                fetched = await s.get(AnalysisJob, job_id)
            assert fetched.status == JobStatus.FAILED.value
            assert fetched.error_details["reason"].startswith("Server restarted")
        finally:
            await queue_service.stop(timeout=2.0)

    async def test_worker_executes_pending_via_run_job(
        self, queue_service, seed_company_and_filing,
        session_factory, monkeypatch,
    ):
        """enqueue → ワーカーが拾って _run_job を呼ぶ → completed"""
        from unittest.mock import AsyncMock
        company_id, filing_id = seed_company_and_filing

        called = asyncio.Event()
        original_run_job = queue_service._run_job

        async def fake_run_job(job):
            called.set()
            # 実装はノーオペで完了扱い
            return None

        from sqlalchemy import select
        monkeypatch.setattr(queue_service, "_run_job", fake_run_job)
        await queue_service.start()
        try:
            job = await queue_service.enqueue(company_id, filing_id)
            await asyncio.wait_for(called.wait(), timeout=3.0)
            # ワーカーループ側が completed に遷移するまで少し待つ
            for _ in range(40):
                async with session_factory() as s:
                    fetched = await s.get(AnalysisJob, job.id)
                if fetched is not None and fetched.status == JobStatus.COMPLETED.value:
                    break
                await asyncio.sleep(0.05)
        finally:
            await queue_service.stop(timeout=2.0)

        async with session_factory() as s:
            fetched = await s.get(AnalysisJob, job.id)
        assert fetched.status == JobStatus.COMPLETED.value

    async def test_worker_marks_failed_on_analysis_failed_error(
        self, queue_service, seed_company_and_filing,
        session_factory, monkeypatch,
    ):
        company_id, filing_id = seed_company_and_filing

        async def failing_run_job(job):
            raise AnalysisFailedError([
                {"type": "mda", "message": "fail"},
            ])

        monkeypatch.setattr(queue_service, "_run_job", failing_run_job)
        await queue_service.start()
        try:
            job = await queue_service.enqueue(company_id, filing_id)
            for _ in range(40):
                async with session_factory() as s:
                    fetched = await s.get(AnalysisJob, job.id)
                if fetched.status in (
                    JobStatus.FAILED.value, JobStatus.COMPLETED.value,
                ):
                    break
                await asyncio.sleep(0.05)
        finally:
            await queue_service.stop(timeout=2.0)

        async with session_factory() as s:
            fetched = await s.get(AnalysisJob, job.id)
        assert fetched.status == JobStatus.FAILED.value
        assert fetched.error_details["failed_types"][0]["type"] == "mda"

    async def test_stop_graceful_within_timeout(
        self, queue_service, seed_company_and_filing,
        monkeypatch,
    ):
        """timeout 内に終わる _run_job なら stop() がそのまま完了"""
        company_id, filing_id = seed_company_and_filing

        async def quick_run_job(job):
            await asyncio.sleep(0.1)

        monkeypatch.setattr(queue_service, "_run_job", quick_run_job)
        await queue_service.start()
        await queue_service.enqueue(company_id, filing_id)
        await asyncio.sleep(0.2)
        await queue_service.stop(timeout=2.0)
        # 例外なく完了すれば OK

    async def test_stop_timeout_cancels_running(
        self, queue_service, seed_company_and_filing,
        session_factory, monkeypatch,
    ):
        """timeout 超過で running が cancelled になる"""
        company_id, filing_id = seed_company_and_filing

        long_running = asyncio.Event()

        async def long_run_job(job):
            long_running.set()
            await asyncio.sleep(60)

        monkeypatch.setattr(queue_service, "_run_job", long_run_job)
        await queue_service.start()
        try:
            job = await queue_service.enqueue(company_id, filing_id)
            await asyncio.wait_for(long_running.wait(), timeout=3.0)
            await queue_service.stop(timeout=0.3)
        except Exception:
            pass

        async with session_factory() as s:
            fetched = await s.get(AnalysisJob, job.id)
        assert fetched.status == JobStatus.CANCELLED.value
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/services/test_analysis_queue.py::TestWorkerLifecycle -v`
- [ ] Expected: AttributeError on `start`/`stop`/`_worker_loop`

### Step 3: 実装追加

- [ ] `src/stock_analyze_system/services/analysis_queue.py` の `AnalysisQueueService` クラスに追加

```python
    async def start(self) -> None:
        """ワーカー起動 + running ジョブ復旧。"""
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            await repo.reset_running_to_failed(
                reason="Server restarted while running",
            )
        self._shutdown_event.clear()
        self._wakeup_event.clear()
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self, timeout: float = 30.0) -> None:
        """graceful shutdown。timeout 超過で強制キャンセル。"""
        self._shutdown_event.set()
        self._wakeup_event.set()
        if self._worker_task is None:
            return
        try:
            await asyncio.wait_for(self._worker_task, timeout=timeout)
        except asyncio.TimeoutError:
            self._worker_task.cancel()
            for task in list(self._running_tasks.values()):
                task.cancel()
            await asyncio.gather(
                self._worker_task, *self._running_tasks.values(),
                return_exceptions=True,
            )
            # 残った running を cancelled にマーク
            async with self._session_factory() as session:
                from sqlalchemy import update
                await session.execute(
                    update(AnalysisJob)
                    .where(AnalysisJob.status == JobStatus.RUNNING.value)
                    .values(
                        status=JobStatus.CANCELLED.value,
                        completed_at=now_utc(),
                    )
                )
                await session.commit()
        finally:
            self._worker_task = None

    async def _worker_loop(self) -> None:
        while not self._shutdown_event.is_set():
            job = await self._dequeue_next()
            if job is None:
                self._wakeup_event.clear()
                wakeup_task = asyncio.create_task(self._wakeup_event.wait())
                shutdown_task = asyncio.create_task(
                    self._shutdown_event.wait(),
                )
                _, pending = await asyncio.wait(
                    {wakeup_task, shutdown_task},
                    timeout=1.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                continue

            task = asyncio.create_task(self._execute_with_status(job))
            self._running_tasks[job.id] = task
            try:
                await task
            except asyncio.CancelledError:
                pass  # _execute_with_status 内で cancelled へ遷移済み
            finally:
                self._running_tasks.pop(job.id, None)

    async def _dequeue_next(self) -> AnalysisJob | None:
        async with self._session_factory() as session:
            repo = AnalysisJobRepository(session)
            return await repo.dequeue_next()

    async def _execute_with_status(self, job: AnalysisJob) -> None:
        """_run_job を実行し、結果を status に反映する。"""
        try:
            await self._run_job(job)
        except asyncio.CancelledError:
            async with self._session_factory() as session:
                repo = AnalysisJobRepository(session)
                await repo.update_status(
                    job.id, JobStatus.CANCELLED, completed_at=now_utc(),
                )
            raise
        except AnalysisFailedError as exc:
            async with self._session_factory() as session:
                repo = AnalysisJobRepository(session)
                await repo.update_status(
                    job.id, JobStatus.FAILED,
                    completed_at=now_utc(),
                    error_details={"failed_types": exc.failed_types},
                )
        except Exception as exc:
            logger.exception("job %d failed", job.id)
            async with self._session_factory() as session:
                repo = AnalysisJobRepository(session)
                await repo.update_status(
                    job.id, JobStatus.FAILED,
                    completed_at=now_utc(),
                    error_details={"reason": str(exc)},
                )
        else:
            async with self._session_factory() as session:
                repo = AnalysisJobRepository(session)
                await repo.update_status(
                    job.id, JobStatus.COMPLETED, completed_at=now_utc(),
                )
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/services/test_analysis_queue.py -v`
- [ ] Expected: 22 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/services/analysis_queue.py \
        tests/unit/services/test_analysis_queue.py
git commit -m "feat(service): add worker loop with start/stop/cancel handling"
```

---

## Task 11: `AppState` 統合 + lifespan

**Files:**
- Modify: `src/stock_analyze_system/web/dependencies.py`
- Modify: `src/stock_analyze_system/web/app.py`

**設計ノート:** `AppState` に `session_factory` と `analysis_queue` を追加する。lifespan では `start/stop` を呼ぶ。AppState 起動時に session_factory を作る必要があり、`async_sessionmaker(engine, expire_on_commit=False)` を使う。

### Step 1: `web/dependencies.py` の AppState を改修

- [ ] `src/stock_analyze_system/web/dependencies.py` を編集

`AppState` データクラスに `session_factory` と `analysis_queue` フィールドを追加し、`AppState.create` 内で組み立てる。`AppState.dispose` で `analysis_queue` は触らない（lifespan 側で start/stop する責務分離）。

具体的には以下のような形に変更：

```python
# import セクションに追加
from sqlalchemy.ext.asyncio import async_sessionmaker
from stock_analyze_system.services.analysis_queue import AnalysisQueueService


@dataclass
class AppState:
    """Application-wide state held on app.state."""

    config: AppConfig
    engine: AsyncEngine
    clients: ClientBundle
    session_factory: async_sessionmaker
    analysis_queue: AnalysisQueueService

    @classmethod
    async def create(cls, config: AppConfig) -> "AppState":
        # ... 既存の処理 ...
        engine = await create_db_engine(config.database.path)
        bundle = ClientBundle(...)  # 既存
        if config.pageindex.enabled:
            # 既存の bundle.llm / bundle.pdf_converter 設定
            ...

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        analysis_queue = AnalysisQueueService(
            session_factory=session_factory,
            config=config,
            clients=bundle,
        )
        return cls(
            config=config,
            engine=engine,
            clients=bundle,
            session_factory=session_factory,
            analysis_queue=analysis_queue,
        )
```

`dispose` メソッドは既存のまま（engine/clients の close のみ）。

### Step 2: `web/app.py` の lifespan を改修

- [ ] `src/stock_analyze_system/web/app.py` の `lifespan` 関数を編集

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    state = await AppState.create(config)
    app.state.app_state = state
    await state.analysis_queue.start()
    try:
        yield
    finally:
        await state.analysis_queue.stop(timeout=30.0)
        await state.dispose()
```

### Step 3: 既存テストが通ることを確認

- [ ] Run: `pytest tests/unit/web/ -v`
- [ ] Expected: 既存テスト全て PASSED（AppState の追加フィールドが既存テストを破壊しないことの確認）

エラーが出る場合は `tests/unit/web/conftest.py` の `client` フィクスチャが lifespan を起動するため、`config.pageindex.enabled = False` でも `AnalysisQueueService` が作れることを確認。

### Step 4: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/web/dependencies.py \
        src/stock_analyze_system/web/app.py
git commit -m "feat(web): wire AnalysisQueueService into AppState and lifespan"
```

---

## Task 12: API ルート - `POST /api/analysis-jobs`

**Files:**
- Create: `src/stock_analyze_system/web/routes/analysis_jobs.py`
- Modify: `src/stock_analyze_system/web/app.py`
- Test: `tests/unit/web/test_analysis_jobs.py` (Create)

### Step 1: テストファイル作成

- [ ] `tests/unit/web/test_analysis_jobs.py` を作成

```python
"""Web API テスト: /api/analysis-jobs"""
from __future__ import annotations

import pytest

from stock_analyze_system.models.analysis_job import AnalysisJob, JobStatus
from stock_analyze_system.models.filing import Filing


@pytest.fixture
async def seeded_filing(seeded_aapl_client, db_writer):
    filing = Filing(
        company_id="US_AAPL",
        source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000320193-24-000123",
    )
    await db_writer(filing)
    # filing.id は autoincrement なので 1 と仮定
    return {"company_id": "US_AAPL", "filing_id": 1}


class TestCreateJob:
    def test_create_returns_201_with_pending_job(
        self, seeded_aapl_client, seeded_filing,
    ):
        resp = seeded_aapl_client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_filing["company_id"],
                "filing_id": seeded_filing["filing_id"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["company_id"] == "US_AAPL"
        assert data["filing_id"] == 1
        assert "job_id" in data

    def test_create_returns_200_for_duplicate(
        self, seeded_aapl_client, seeded_filing,
    ):
        first = seeded_aapl_client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_filing["company_id"],
                "filing_id": seeded_filing["filing_id"],
            },
        )
        assert first.status_code == 201
        first_id = first.json()["job_id"]

        second = seeded_aapl_client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_filing["company_id"],
                "filing_id": seeded_filing["filing_id"],
            },
        )
        assert second.status_code == 200
        assert second.json()["job_id"] == first_id

    def test_create_requires_auth(self, client, seeded_filing):
        resp = client.post(
            "/api/analysis-jobs",
            json={"company_id": "US_AAPL", "filing_id": 1},
        )
        assert resp.status_code in (401, 403)
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/web/test_analysis_jobs.py -v`
- [ ] Expected: 404 (route not registered)

### Step 3: ルート実装

- [ ] `src/stock_analyze_system/web/routes/analysis_jobs.py` を作成

```python
"""バックグラウンド分析ジョブ API"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from stock_analyze_system.models.analysis_job import JobStatus
from stock_analyze_system.services.analysis_queue import AnalysisQueueService
from stock_analyze_system.web.dependencies import AppState, get_app_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis-jobs")


class CreateJobRequest(BaseModel):
    company_id: str
    filing_id: int


def _job_to_dict(job) -> dict:
    return {
        "job_id": job.id,
        "company_id": job.company_id,
        "filing_id": job.filing_id,
        "status": job.status,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "current_analysis_type": job.current_analysis_type,
        "error_details": job.error_details,
        "created_at": (
            job.created_at.isoformat() if job.created_at else None
        ),
        "started_at": (
            job.started_at.isoformat() if job.started_at else None
        ),
        "completed_at": (
            job.completed_at.isoformat() if job.completed_at else None
        ),
        "dismissed_at": (
            job.dismissed_at.isoformat() if job.dismissed_at else None
        ),
    }


def _get_queue(state: AppState = Depends(get_app_state)) -> AnalysisQueueService:
    return state.analysis_queue


def _enforce_heavy_request_limit(request: Request, scope: str) -> None:
    """既存の heavy_rate_limiter パターンに準拠。"""
    from stock_analyze_system.web.auth import get_client_key
    limiter = request.app.state.heavy_rate_limiter
    key = f"{scope}:{get_client_key(request)}"
    if not limiter.allow(key):
        raise HTTPException(status_code=429, detail="Too many requests")


@router.post("")
async def create_job(
    request: Request,
    body: CreateJobRequest,
    response: Response,
    queue: AnalysisQueueService = Depends(_get_queue),
):
    _enforce_heavy_request_limit(
        request, scope=f"analysis-jobs:{body.company_id}",
    )
    # 重複検知のため、enqueue 前に find しておく
    existing = await queue.list_jobs(
        company_id=body.company_id,
        filing_id=body.filing_id,
        statuses=[JobStatus.PENDING, JobStatus.RUNNING],
        limit=1,
    )
    job = await queue.enqueue(body.company_id, body.filing_id)
    response.status_code = 200 if existing else 201
    return _job_to_dict(job)
```

### Step 4: ルータを登録

- [ ] `src/stock_analyze_system/web/app.py` の `create_app` 内 import セクションに追加

```python
from stock_analyze_system.web.routes import analysis_jobs as analysis_jobs_routes
```

- [ ] `app.include_router(api_routes.router)` の前に追加

```python
app.include_router(analysis_jobs_routes.router)
```

### Step 5: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/web/test_analysis_jobs.py::TestCreateJob -v`
- [ ] Expected: 3 tests PASSED

### Step 6: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/web/routes/analysis_jobs.py \
        src/stock_analyze_system/web/app.py \
        tests/unit/web/test_analysis_jobs.py
git commit -m "feat(api): add POST /api/analysis-jobs endpoint"
```

---

## Task 13: API - `GET /api/analysis-jobs/{id}` + `GET /api/analysis-jobs`

**Files:**
- Modify: `src/stock_analyze_system/web/routes/analysis_jobs.py`
- Modify: `tests/unit/web/test_analysis_jobs.py`

### Step 1: 失敗テスト追加

- [ ] `tests/unit/web/test_analysis_jobs.py` 末尾に追加

```python
class TestGetJob:
    def test_get_returns_job_details(
        self, seeded_aapl_client, seeded_filing,
    ):
        created = seeded_aapl_client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_filing["company_id"],
                "filing_id": seeded_filing["filing_id"],
            },
        ).json()
        resp = seeded_aapl_client.get(
            f"/api/analysis-jobs/{created['job_id']}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == created["job_id"]
        assert data["status"] == "pending"

    def test_get_returns_404_for_missing(self, seeded_aapl_client):
        resp = seeded_aapl_client.get("/api/analysis-jobs/99999")
        assert resp.status_code == 404


class TestListJobs:
    def test_list_default_returns_empty(self, seeded_aapl_client):
        resp = seeded_aapl_client.get("/api/analysis-jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_returns_pending(
        self, seeded_aapl_client, seeded_filing,
    ):
        seeded_aapl_client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_filing["company_id"],
                "filing_id": seeded_filing["filing_id"],
            },
        )
        resp = seeded_aapl_client.get(
            "/api/analysis-jobs?status=pending",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["status"] == "pending"

    def test_list_filters_by_company_filing(
        self, seeded_aapl_client, seeded_filing,
    ):
        seeded_aapl_client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_filing["company_id"],
                "filing_id": seeded_filing["filing_id"],
            },
        )
        resp = seeded_aapl_client.get(
            f"/api/analysis-jobs"
            f"?company_id={seeded_filing['company_id']}"
            f"&filing_id={seeded_filing['filing_id']}"
            f"&status=pending,running",
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/web/test_analysis_jobs.py::TestGetJob tests/unit/web/test_analysis_jobs.py::TestListJobs -v`
- [ ] Expected: 404 全部

### Step 3: ルート実装追加

- [ ] `src/stock_analyze_system/web/routes/analysis_jobs.py` 末尾に追加

```python
@router.get("/{job_id}")
async def get_job(
    job_id: int,
    queue: AnalysisQueueService = Depends(_get_queue),
):
    job = await queue.get_status(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)


@router.get("")
async def list_jobs(
    company_id: str | None = None,
    filing_id: int | None = None,
    status: str | None = None,
    include_dismissed: bool = False,
    limit: int = 20,
    queue: AnalysisQueueService = Depends(_get_queue),
):
    statuses: list[JobStatus] | None = None
    if status:
        try:
            statuses = [JobStatus(s.strip()) for s in status.split(",") if s.strip()]
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid status: {exc}",
            )
    jobs = await queue.list_jobs(
        company_id=company_id,
        filing_id=filing_id,
        statuses=statuses,
        include_dismissed=include_dismissed,
        limit=limit,
    )
    return [_job_to_dict(j) for j in jobs]
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/web/test_analysis_jobs.py -v`
- [ ] Expected: 8 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/web/routes/analysis_jobs.py \
        tests/unit/web/test_analysis_jobs.py
git commit -m "feat(api): add GET /api/analysis-jobs/{id} and GET /api/analysis-jobs"
```

---

## Task 14: API - `DELETE /api/analysis-jobs/{id}` (キャンセル)

**Files:**
- Modify: `src/stock_analyze_system/web/routes/analysis_jobs.py`
- Modify: `tests/unit/web/test_analysis_jobs.py`

### Step 1: 失敗テスト追加

- [ ] `tests/unit/web/test_analysis_jobs.py` 末尾に追加

```python
class TestCancelJob:
    def test_delete_cancels_pending(
        self, seeded_aapl_client, seeded_filing,
    ):
        created = seeded_aapl_client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_filing["company_id"],
                "filing_id": seeded_filing["filing_id"],
            },
        ).json()
        resp = seeded_aapl_client.delete(
            f"/api/analysis-jobs/{created['job_id']}",
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_delete_returns_404_for_missing(self, seeded_aapl_client):
        resp = seeded_aapl_client.delete("/api/analysis-jobs/99999")
        assert resp.status_code == 404
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/web/test_analysis_jobs.py::TestCancelJob -v`
- [ ] Expected: 405 Method Not Allowed

### Step 3: 実装追加

- [ ] `src/stock_analyze_system/web/routes/analysis_jobs.py` 末尾に追加

```python
@router.delete("/{job_id}")
async def cancel_job(
    job_id: int,
    queue: AnalysisQueueService = Depends(_get_queue),
):
    job = await queue.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/web/test_analysis_jobs.py -v`
- [ ] Expected: 10 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/web/routes/analysis_jobs.py \
        tests/unit/web/test_analysis_jobs.py
git commit -m "feat(api): add DELETE /api/analysis-jobs/{id} for cancellation"
```

---

## Task 15: API - `POST /api/analysis-jobs/{id}/dismiss`

**Files:**
- Modify: `src/stock_analyze_system/web/routes/analysis_jobs.py`
- Modify: `tests/unit/web/test_analysis_jobs.py`

### Step 1: 失敗テスト追加

- [ ] `tests/unit/web/test_analysis_jobs.py` 末尾に追加

```python
class TestDismissJob:
    async def test_dismiss_marks_dismissed_at(
        self, seeded_aapl_client, seeded_filing, web_config,
    ):
        from stock_analyze_system.models.base import (
            create_db_engine, get_session,
        )
        engine = await create_db_engine(web_config.database.path)
        try:
            async with get_session(engine) as s:
                failed = AnalysisJob(
                    company_id=seeded_filing["company_id"],
                    filing_id=seeded_filing["filing_id"],
                    status=JobStatus.FAILED.value,
                )
                s.add(failed)
                await s.flush()
                job_id = failed.id
        finally:
            await engine.dispose()

        resp = seeded_aapl_client.post(
            f"/api/analysis-jobs/{job_id}/dismiss",
        )
        assert resp.status_code == 200
        assert resp.json()["dismissed_at"] is not None

    def test_dismiss_rejects_pending_with_400(
        self, seeded_aapl_client, seeded_filing,
    ):
        created = seeded_aapl_client.post(
            "/api/analysis-jobs",
            json={
                "company_id": seeded_filing["company_id"],
                "filing_id": seeded_filing["filing_id"],
            },
        ).json()
        resp = seeded_aapl_client.post(
            f"/api/analysis-jobs/{created['job_id']}/dismiss",
        )
        assert resp.status_code == 400
```

### Step 2: テスト実行（失敗確認）

- [ ] Run: `pytest tests/unit/web/test_analysis_jobs.py::TestDismissJob -v`
- [ ] Expected: 404 (route not found)

### Step 3: 実装追加

- [ ] `src/stock_analyze_system/web/routes/analysis_jobs.py` 末尾に追加

```python
@router.post("/{job_id}/dismiss")
async def dismiss_job(
    job_id: int,
    queue: AnalysisQueueService = Depends(_get_queue),
):
    try:
        job = await queue.dismiss(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_dict(job)
```

### Step 4: テスト実行（成功確認）

- [ ] Run: `pytest tests/unit/web/test_analysis_jobs.py -v`
- [ ] Expected: 12 tests PASSED

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/web/routes/analysis_jobs.py \
        tests/unit/web/test_analysis_jobs.py
git commit -m "feat(api): add POST /api/analysis-jobs/{id}/dismiss"
```

---

## Task 16: 旧 NDJSON エンドポイントを deprecated にマーク

**Files:**
- Modify: `src/stock_analyze_system/web/routes/api.py`

### Step 1: deprecation warning + OpenAPI フラグを追加

- [ ] `src/stock_analyze_system/web/routes/api.py:232-264` の `@router.post("/{company_id}/rag/analyze")` デコレータと関数本体を編集

デコレータを変更：
```python
@router.post(
    "/{company_id}/rag/analyze",
    deprecated=True,
)
```

関数本体冒頭（`rag = _get_rag_service(services)` の直前）に追加：
```python
    logger.warning(
        "DEPRECATED: POST /api/stocks/%s/rag/analyze is deprecated. "
        "Use POST /api/analysis-jobs instead.",
        company_id,
    )
```

### Step 2: 既存テストが通ることを確認

- [ ] Run: `pytest tests/unit/web/ -v`
- [ ] Expected: すべての既存テスト PASSED

### Step 3: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/web/routes/api.py
git commit -m "feat(api): mark POST /api/stocks/{id}/rag/analyze as deprecated"
```

---

## Task 17: ダッシュボード UI - 「LLM分析キュー」パネル

**Files:**
- Modify: `src/stock_analyze_system/web/templates/dashboard.html`
- Modify: `src/stock_analyze_system/web/static/app.js`

**設計ノート:** UI 変更は手動検証が中心。タスク完了前にローカルで `infisical run -- python -m stock_analyze_system.web` を起動し、ブラウザで動作確認する。

### Step 1: 既存「LLM分析」パネルを特定

- [ ] `src/stock_analyze_system/web/templates/dashboard.html` を Read で確認
- [ ] 「LLM分析」パネルの HTML ブロックを探す（`id="llm-analysis-panel"` などの目印）
- [ ] `src/stock_analyze_system/web/static/app.js` の対応する初期化関数を Read で確認

### Step 2: HTML を「LLM分析キュー」に置き換え

- [ ] `dashboard.html` のパネルブロックを以下に置換（既存 ID を保持しつつ中身を変える）

```html
<section class="panel" id="llm-queue-panel">
  <header class="panel__header">
    <h2 class="panel__title">LLM分析キュー</h2>
  </header>
  <div class="panel__body">
    <div id="llm-queue-list">
      <p class="muted" id="llm-queue-empty">実行中の分析はありません</p>
    </div>
  </div>
</section>
```

### Step 3: JS でキューポーリング + キャンセル/dismiss

- [ ] `src/stock_analyze_system/web/static/app.js` に追加（ダッシュボード初期化セクション内）

```javascript
const STATUS_BADGE = {
  pending: { label: "PENDING", cls: "badge--mono" },
  running: { label: "RUNNING", cls: "badge--up" },
  failed: { label: "FAILED", cls: "badge--down" },
};

function formatElapsed(createdAtIso) {
  const ms = Date.now() - new Date(createdAtIso).getTime();
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function renderQueueRow(job) {
  const badge = STATUS_BADGE[job.status] ?? { label: job.status, cls: "" };
  const action = (job.status === "failed")
    ? `<button class="btn btn--icon" data-action="dismiss" data-job-id="${job.job_id}">×</button>`
    : `<button class="btn btn--icon" data-action="cancel" data-job-id="${job.job_id}">×</button>`;
  return `
    <div class="queue-row">
      <span class="badge ${badge.cls}">${badge.label}</span>
      <a class="queue-row__company" href="/stocks/${job.company_id}">${job.company_id}</a>
      <span class="queue-row__type">${job.current_analysis_type ?? "—"}</span>
      <span class="queue-row__progress">${job.progress_current}/${job.progress_total}</span>
      <span class="queue-row__elapsed">${formatElapsed(job.created_at)}</span>
      ${action}
    </div>
  `;
}

async function fetchQueue() {
  const resp = await fetch(
    "/api/analysis-jobs?status=pending,running,failed&include_dismissed=false&limit=20",
  );
  if (!resp.ok) return;
  const jobs = await resp.json();
  const listEl = document.getElementById("llm-queue-list");
  const emptyEl = document.getElementById("llm-queue-empty");
  if (!listEl) return;
  if (jobs.length === 0) {
    listEl.innerHTML = `<p class="muted" id="llm-queue-empty">実行中の分析はありません</p>`;
    return;
  }
  listEl.innerHTML = jobs.map(renderQueueRow).join("");
}

function initQueuePanel() {
  const root = document.getElementById("llm-queue-panel");
  if (!root) return;
  root.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const jobId = btn.dataset.jobId;
    const action = btn.dataset.action;
    if (action === "cancel") {
      await fetch(`/api/analysis-jobs/${jobId}`, { method: "DELETE" });
    } else if (action === "dismiss") {
      await fetch(`/api/analysis-jobs/${jobId}/dismiss`, { method: "POST" });
    }
    await fetchQueue();
  });
  fetchQueue();
  setInterval(fetchQueue, 5000);
}

// 既存のダッシュボード初期化フックに initQueuePanel() を追加
document.addEventListener("DOMContentLoaded", initQueuePanel);
```

### Step 4: 手動検証

- [ ] Run: `infisical run -- python -m stock_analyze_system.web` を起動
- [ ] ブラウザで `http://localhost:8501` を開きログイン
- [ ] 任意の企業の分析タブで「決算分析🔍」を押し、ダッシュボードに戻ってキューに表示されることを確認
- [ ] キャンセル `×` ボタンが pending を消すことを確認

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/web/templates/dashboard.html \
        src/stock_analyze_system/web/static/app.js
git commit -m "feat(ui): replace LLM analysis panel with queue panel on dashboard"
```

---

## Task 18: 分析タブ UI - キュー化 + タブ復帰検出 + 再実行ボタン

**Files:**
- Modify: `src/stock_analyze_system/web/static/app.js`
- Modify: `src/stock_analyze_system/web/templates/stocks/_tab_analysis.html`

### Step 1: 既存「決算分析🔍」のクリックハンドラを特定

- [ ] `app.js` で `POST /api/stocks/.../rag/analyze` を呼んでいる箇所を Grep で探す

```bash
grep -n "rag/analyze" src/stock_analyze_system/web/static/app.js
```

- [ ] 該当のハンドラ関数を Read で確認（NDJSON ストリームを処理する `applyEvent` 等）

### Step 2: ハンドラをジョブベースに置換

- [ ] `app.js` の該当箇所を以下のような形に変更

既存の NDJSON ストリーム処理の代わりに、enqueue + ポーリング処理を実装。`applyEvent(prevApplyEventArgs)` は再利用する。

```javascript
async function startAnalysisJob(companyId, filingId) {
  const resp = await fetch("/api/analysis-jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company_id: companyId, filing_id: filingId }),
  });
  if (!resp.ok) {
    showAnalysisError(`enqueue 失敗: ${resp.status}`);
    return;
  }
  const job = await resp.json();
  pollAnalysisJob(job.job_id, companyId);
}

function jobToEvents(job, prevStatus) {
  const events = [];
  if (job.status === "pending") {
    events.push({ event: "fetching" });
  } else if (job.status === "running") {
    if (prevStatus === "pending") {
      events.push({ event: "started", total: job.progress_total });
    }
    if (job.current_analysis_type) {
      events.push({
        event: "phase",
        index: job.progress_current,
        total: job.progress_total,
        analysis_type: job.current_analysis_type,
        label: ANALYSIS_TYPE_LABELS[job.current_analysis_type] ?? job.current_analysis_type,
      });
    } else if (job.progress_current === 0) {
      events.push({ event: "indexing" });
    }
  } else if (job.status === "completed") {
    events.push({ event: "complete" });
  } else if (job.status === "failed") {
    const failed = job.error_details?.failed_types ?? [];
    for (const f of failed) {
      events.push({
        event: "error",
        analysis_type: f.type,
        message: f.message,
      });
    }
    events.push({ event: "complete" });
    showRerunButton(job);
  } else if (job.status === "cancelled") {
    events.push({ event: "cancelled" });
    events.push({ event: "complete" });
    showRerunButton(job);
  }
  return events;
}

function pollAnalysisJob(jobId, companyId) {
  let prevStatus = null;
  const interval = setInterval(async () => {
    const resp = await fetch(`/api/analysis-jobs/${jobId}`);
    if (!resp.ok) {
      clearInterval(interval);
      return;
    }
    const job = await resp.json();
    const events = jobToEvents(job, prevStatus);
    for (const ev of events) {
      applyEvent(ev);  // 既存ハンドラ流用
    }
    prevStatus = job.status;
    if (["completed", "failed", "cancelled"].includes(job.status)) {
      clearInterval(interval);
      if (job.status === "completed") {
        loadAnalyses();  // 既存関数を呼ぶ
      }
    }
  }, 5000);
}

function showRerunButton(job) {
  const container = document.getElementById("analysis-rerun");
  if (!container) return;
  container.innerHTML = `
    <button class="btn" id="rerun-analysis-btn">再実行</button>
  `;
  document.getElementById("rerun-analysis-btn").addEventListener(
    "click",
    () => {
      container.innerHTML = "";
      startAnalysisJob(job.company_id, job.filing_id);
    },
  );
}

// タブ復帰時の自動検出
async function detectInProgressJob(companyId, filingId) {
  const resp = await fetch(
    `/api/analysis-jobs?company_id=${companyId}`
    + `&filing_id=${filingId}&status=pending,running&limit=1`,
  );
  if (!resp.ok) return;
  const jobs = await resp.json();
  if (jobs.length > 0) {
    pollAnalysisJob(jobs[0].job_id, companyId);
  }
}
```

- [ ] 既存の「決算分析🔍」ボタンハンドラを `startAnalysisJob(companyId, filingId)` を呼ぶ形に置換
- [ ] 分析タブが開かれた時のフック（既存の `loadAnalyses()` 等を呼んでいる箇所）に `detectInProgressJob(companyId, filingId)` を追加

### Step 3: 「再実行」ボタンのコンテナを追加

- [ ] `src/stock_analyze_system/web/templates/stocks/_tab_analysis.html` のプログレスバー近辺に以下のコンテナを追加

```html
<div id="analysis-rerun" class="analysis-rerun"></div>
```

### Step 4: 手動検証

- [ ] Run: `infisical run -- python -m stock_analyze_system.web` を起動
- [ ] ブラウザで企業ページ → 分析タブ → 「決算分析🔍」をクリック
- [ ] **検証 1:** プログレスバーが進む
- [ ] **検証 2:** タブを閉じて再度開く → 進行中ジョブが自動検出されてポーリング再開
- [ ] **検証 3:** ダッシュボードでキャンセル → 分析タブで「再実行」ボタンが表示される
- [ ] **検証 4:** 「再実行」を押すと新規ジョブが enqueue される

### Step 5: Commit

- [ ] Commit

```bash
git add src/stock_analyze_system/web/static/app.js \
        src/stock_analyze_system/web/templates/stocks/_tab_analysis.html
git commit -m "feat(ui): switch analysis tab to queue-based polling with auto-detect and re-run"
```

---

## Task 19: 統合スモークテスト + 設計仕様書のクロスチェック

**Files:**
- なし（手動検証のみ）

### Step 1: 全テスト実行

- [ ] Run: `pytest tests/unit -v`
- [ ] Expected: 全テスト PASSED

### Step 2: 既存 RAG テストへの影響確認

- [ ] Run: `pytest tests/unit/services/test_rag_service.py tests/unit/web/ -v`
- [ ] Expected: 既存テスト全て PASSED（旧 NDJSON エンドポイントの動作不変）

### Step 3: 仕様書クロスチェック

- [ ] 仕様書 §1.2 の確定要求 1〜10 がすべて実装されたか確認
- [ ] §5（モデル）、§6（サービス）、§7（リポジトリ）、§8（API）、§9（UI）、§10（lifespan）、§11（エラー処理）が実装されたか確認

### Step 4: 手動 E2E シナリオ

以下のシナリオを実行：

1. ログイン → 任意の企業の分析タブ → 「決算分析🔍」
2. ダッシュボードに移動 → キューに `RUNNING` 表示
3. ブラウザタブを閉じる
4. 5秒後に新しいタブで同企業を開く → 進行中ジョブが復帰してプログレスバー表示
5. ダッシュボードでキャンセル → 分析タブが「再実行」状態
6. 再実行 → 新規ジョブが起動
7. 完了まで待つ → ダッシュボードからジョブが消え、分析タブに結果が表示

### Step 5: 最終 commit（必要なら）

- [ ] 修正があれば commit

---

## Definition of Done

- [ ] 全 19 タスクの commit が完了
- [ ] `pytest tests/unit -v` がすべて PASSED
- [ ] 手動 E2E シナリオが成功
- [ ] 仕様書 §1.2 の要求 1〜10 をすべて実装
- [ ] 旧 `POST /api/stocks/{id}/rag/analyze` のテストが破壊されていない
- [ ] OpenAPI ドキュメントで旧エンドポイントが deprecated 表示
