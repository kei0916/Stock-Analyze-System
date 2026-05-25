"""データベースエンジン・セッション管理 (async)"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    pass


async def _company_analyses_unique_columns(conn) -> list[list[str]]:
    result = await conn.execute(text("PRAGMA index_list('company_analyses')"))
    indexes = result.fetchall()
    unique_columns: list[list[str]] = []
    for row in indexes:
        if not row[2]:
            continue
        index_name = str(row[1]).replace('"', '""')
        info = await conn.execute(text(f'PRAGMA index_info("{index_name}")'))
        columns = [str(info_row[2]) for info_row in info.fetchall()]
        unique_columns.append(columns)
    return unique_columns


async def _rebuild_company_analyses_pipeline_key(conn) -> None:
    """Rebuild company_analyses to add `pipeline` to uq_analysis_key.

    SQLite's "Making Other Kinds Of Table Schema Changes" recipe
    (https://www.sqlite.org/lang_altertable.html) suggests disabling
    `foreign_keys` around table rebuilds. Here we cannot: this migration
    runs inside `engine.begin()`'s transaction, and
    `PRAGMA foreign_keys=OFF` is documented to be a no-op when issued
    inside a pending transaction. Toggling the pragma here would either
    silently fail (best case) or leak an unintended OFF state to pooled
    connections (worst case).

    We rely on two project-specific invariants instead:
      1. No other table FK-references `company_analyses` (`grep -n
         'company_analyses' src/.../models` — the only entries are this
         model itself), so DROP/RENAME under FK enforcement cannot
         dangle any child rows.
      2. After the rebuild we run `PRAGMA foreign_key_check` so that if
         invariant 1 is ever broken by a future model, this code raises
         instead of silently leaving the DB inconsistent.
    """

    await conn.execute(text("""
        CREATE TABLE company_analyses_new (
            id INTEGER NOT NULL,
            company_id VARCHAR NOT NULL,
            filing_id INTEGER NOT NULL,
            analysis_type VARCHAR(30) NOT NULL,
            result_json TEXT NOT NULL,
            model_name VARCHAR(100) NOT NULL,
            pipeline VARCHAR(20),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            CONSTRAINT uq_analysis_key UNIQUE (
                company_id, filing_id, analysis_type, pipeline
            ),
            FOREIGN KEY(company_id) REFERENCES companies (id),
            FOREIGN KEY(filing_id) REFERENCES filings (id)
        )
    """))
    await conn.execute(text("""
        INSERT INTO company_analyses_new (
            id, company_id, filing_id, analysis_type, result_json,
            model_name, pipeline, created_at
        )
        SELECT
            id, company_id, filing_id, analysis_type, result_json,
            model_name, pipeline, created_at
          FROM company_analyses
    """))
    await conn.execute(text("DROP TABLE company_analyses"))
    await conn.execute(text(
        "ALTER TABLE company_analyses_new RENAME TO company_analyses",
    ))
    await conn.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_company_analyses_company_id
            ON company_analyses (company_id)
    """))

    violations = (
        await conn.execute(text("PRAGMA foreign_key_check"))
    ).fetchall()
    if violations:
        raise RuntimeError(
            "company_analyses pipeline-key rebuild left "
            f"{len(violations)} foreign-key violations: {violations!r}",
        )


async def _ensure_company_analyses_pipeline_schema(conn) -> None:
    result = await conn.execute(text(
        "SELECT 1 FROM pragma_table_info('company_analyses') "
        "WHERE name='pipeline'"
    ))
    if not result.scalar():
        await conn.execute(text(
            "ALTER TABLE company_analyses ADD COLUMN pipeline TEXT"
        ))

    unique_columns = await _company_analyses_unique_columns(conn)
    desired = ["company_id", "filing_id", "analysis_type", "pipeline"]
    legacy = ["company_id", "filing_id", "analysis_type"]
    if desired in unique_columns:
        return
    if legacy in unique_columns:
        await _rebuild_company_analyses_pipeline_key(conn)


async def create_db_engine(db_path: str) -> AsyncEngine:
    """AsyncSQLiteエンジンを作成し、WALモード・外部キーを有効化する"""
    import stock_analyze_system.models  # noqa: F401 — 全モデルをBase.metadataに登録

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all does not ALTER existing tables — migrate legacy DBs in place.
        await _ensure_company_analyses_pipeline_schema(conn)

    return engine


@asynccontextmanager
async def get_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """AsyncSessionのコンテキストマネージャ"""
    from sqlalchemy.exc import PendingRollbackError

    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        try:
            await session.commit()
        except PendingRollbackError:
            await session.rollback()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
