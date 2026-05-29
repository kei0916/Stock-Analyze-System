"""create_db_engine のテスト"""
import inspect
import sqlite3
from pathlib import Path

from sqlalchemy import text

from stock_analyze_system.models.base import create_db_engine


class TestCreateDbEngine:
    async def test_creates_engine_and_tables(self, tmp_path):
        """エンジン作成とテーブル作成が正常に動作すること"""
        db_path = str(tmp_path / "subdir" / "test.db")
        engine = await create_db_engine(db_path)
        try:
            assert engine is not None
            assert Path(db_path).exists()
            assert (tmp_path / "subdir").is_dir()
        finally:
            await engine.dispose()

    async def test_wal_mode_enabled(self, tmp_path):
        """WALモードが有効化されること"""
        db_path = str(tmp_path / "wal_test.db")
        engine = await create_db_engine(db_path)
        try:
            async with engine.connect() as conn:
                result = await conn.exec_driver_sql("PRAGMA journal_mode")
                mode = result.scalar()
                assert mode == "wal"
        finally:
            await engine.dispose()

    async def test_foreign_keys_enabled(self, tmp_path):
        """外部キー制約が有効化されること"""
        db_path = str(tmp_path / "fk_test.db")
        engine = await create_db_engine(db_path)
        try:
            async with engine.connect() as conn:
                result = await conn.exec_driver_sql("PRAGMA foreign_keys")
                fk = result.scalar()
                assert fk == 1
        finally:
            await engine.dispose()

    async def test_tables_created(self, tmp_path):
        """メタデータのテーブルが作成されること"""
        db_path = str(tmp_path / "tables_test.db")
        engine = await create_db_engine(db_path)
        try:
            async with engine.connect() as conn:
                result = await conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                tables = [row[0] for row in result.fetchall()]
                assert "companies" in tables
                assert "financial_data" in tables
        finally:
            await engine.dispose()


async def test_busy_timeout_pragma_applied(pragma_async_engine):
    """PRAGMA busy_timeout=5000 が接続時に適用される。

    値コントラクト検証のみ — aiosqlite はデフォルトで 5000ms を返すため、
    PRAGMA 行が削除されても通過する。リグレッション検出は下の
    test_create_db_engine_source_includes_busy_timeout_pragma で行う。
    """
    async with pragma_async_engine.connect() as conn:
        result = await conn.execute(text("PRAGMA busy_timeout"))
        value = result.scalar()
    assert value == 5000


def test_create_db_engine_source_includes_busy_timeout_pragma():
    """Static guard: PRAGMA busy_timeout=5000 must remain in the listener.

    aiosqlite happens to default to 5000ms, so the runtime PRAGMA-readback
    test above is a value-contract assertion only. This source-level test
    catches accidental removal of the explicit PRAGMA statement.
    """
    from stock_analyze_system.models import base
    src = inspect.getsource(base.create_db_engine)
    assert "PRAGMA busy_timeout=5000" in src, (
        "PRAGMA busy_timeout=5000 missing from create_db_engine — "
        "multi-process write contention will fail fast instead of waiting."
    )


async def test_journal_mode_wal_applied(pragma_async_engine):
    """PRAGMA journal_mode=WAL が接続時に適用される。"""
    async with pragma_async_engine.connect() as conn:
        result = await conn.execute(text("PRAGMA journal_mode"))
        value = result.scalar()
    assert value == "wal"


async def test_foreign_keys_pragma_applied(pragma_async_engine):
    """PRAGMA foreign_keys=ON が接続時に適用される。"""
    async with pragma_async_engine.connect() as conn:
        result = await conn.execute(text("PRAGMA foreign_keys"))
        value = result.scalar()
    assert value == 1

async def test_create_db_engine_migrates_company_analyses_pipeline_key(tmp_path):
    """Legacy 3-column unique key must be widened so extractor rows do not overwrite NULL rows."""
    db_path = tmp_path / "legacy_analysis_key.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE companies (
                id VARCHAR(20) NOT NULL PRIMARY KEY,
                ticker VARCHAR(10),
                security_code VARCHAR(10),
                name VARCHAR(200) NOT NULL,
                name_ja VARCHAR(200),
                market VARCHAR(20) NOT NULL,
                sector VARCHAR(100),
                accounting_standard VARCHAR(10) NOT NULL,
                cik VARCHAR(20),
                edinet_code VARCHAR(20),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE filings (
                id INTEGER NOT NULL PRIMARY KEY,
                company_id VARCHAR NOT NULL,
                source VARCHAR(10) NOT NULL,
                filing_type VARCHAR(10) NOT NULL,
                period_type VARCHAR(10) NOT NULL,
                fiscal_year INTEGER NOT NULL,
                period_end DATE,
                filed_at DATE,
                accession_no VARCHAR(30),
                doc_id VARCHAR(30),
                storage_path TEXT,
                content_hash VARCHAR(64),
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );
            CREATE TABLE company_analyses (
                id INTEGER NOT NULL PRIMARY KEY,
                company_id VARCHAR NOT NULL,
                filing_id INTEGER NOT NULL,
                analysis_type VARCHAR(30) NOT NULL,
                result_json TEXT NOT NULL,
                model_name VARCHAR(100) NOT NULL,
                pipeline VARCHAR(20),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_analysis_key UNIQUE (company_id, filing_id, analysis_type),
                FOREIGN KEY(company_id) REFERENCES companies(id),
                FOREIGN KEY(filing_id) REFERENCES filings(id)
            );
            INSERT INTO companies (id, ticker, name, market, accounting_standard)
            VALUES ('US_AAPL', 'AAPL', 'Apple', 'NASDAQ', 'US-GAAP');
            INSERT INTO filings (id, company_id, source, filing_type, period_type, fiscal_year)
            VALUES (1, 'US_AAPL', 'SEC', '10-K', 'annual', 2025);
            INSERT INTO company_analyses (
                company_id, filing_id, analysis_type, result_json, model_name, pipeline
            ) VALUES ('US_AAPL', 1, 'business_summary', '{"summary":"legacy"}', 'legacy', NULL);
            """,
        )
        conn.commit()
    finally:
        conn.close()

    engine = await create_db_engine(str(db_path))
    try:
        async with engine.begin() as db:
            await db.execute(text(
                """
                INSERT INTO company_analyses (
                    company_id, filing_id, analysis_type, result_json, model_name, pipeline
                ) VALUES (
                    'US_AAPL', 1, 'business_summary', '{"summary":"extractor"}',
                    'extractor-model', 'extractor'
                )
                """,
            ))
            result = await db.execute(text(
                """
                SELECT pipeline, result_json
                  FROM company_analyses
                 WHERE company_id='US_AAPL'
                   AND filing_id=1
                   AND analysis_type='business_summary'
                 ORDER BY pipeline IS NOT NULL, pipeline
                """,
            ))
            rows = result.fetchall()
    finally:
        await engine.dispose()

    assert rows == [
        (None, '{"summary":"legacy"}'),
        ("extractor", '{"summary":"extractor"}'),
    ]


async def test_pipeline_key_rebuild_runs_foreign_key_check(tmp_path):
    """rebuild 後に foreign_key_check が走り、既存 FK (filings.company_id
    → companies.id 等) の violation が 0 件である事を確認する。

    rebuild 自体は `engine.begin()` 内 (transaction) で走るため
    `PRAGMA foreign_keys=OFF` は no-op になる。代わりに rebuild 末尾の
    `PRAGMA foreign_key_check` で defense-in-depth を確保する設計のため、
    pragma 値そのものではなく check の結果を観測する。"""

    db_path = tmp_path / "legacy_fk_intact.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE companies (
                id VARCHAR(20) NOT NULL PRIMARY KEY,
                ticker VARCHAR(10),
                security_code VARCHAR(10),
                name VARCHAR(200) NOT NULL,
                name_ja VARCHAR(200),
                market VARCHAR(20) NOT NULL,
                sector VARCHAR(100),
                accounting_standard VARCHAR(10) NOT NULL,
                cik VARCHAR(20),
                edinet_code VARCHAR(20),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE filings (
                id INTEGER NOT NULL PRIMARY KEY,
                company_id VARCHAR NOT NULL,
                source VARCHAR(10) NOT NULL,
                filing_type VARCHAR(10) NOT NULL,
                period_type VARCHAR(10) NOT NULL,
                fiscal_year INTEGER NOT NULL,
                period_end DATE,
                filed_at DATE,
                accession_no VARCHAR(30),
                doc_id VARCHAR(30),
                storage_path TEXT,
                content_hash VARCHAR(64),
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );
            CREATE TABLE company_analyses (
                id INTEGER NOT NULL PRIMARY KEY,
                company_id VARCHAR NOT NULL,
                filing_id INTEGER NOT NULL,
                analysis_type VARCHAR(30) NOT NULL,
                result_json TEXT NOT NULL,
                model_name VARCHAR(100) NOT NULL,
                pipeline VARCHAR(20),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_analysis_key UNIQUE (company_id, filing_id, analysis_type),
                FOREIGN KEY(company_id) REFERENCES companies(id),
                FOREIGN KEY(filing_id) REFERENCES filings(id)
            );
            INSERT INTO companies (id, ticker, name, market, accounting_standard)
            VALUES ('US_AAPL', 'AAPL', 'Apple', 'NASDAQ', 'US-GAAP');
            INSERT INTO filings (id, company_id, source, filing_type, period_type, fiscal_year)
            VALUES (1, 'US_AAPL', 'SEC', '10-K', 'annual', 2025);
            INSERT INTO company_analyses (
                company_id, filing_id, analysis_type, result_json, model_name, pipeline
            ) VALUES ('US_AAPL', 1, 'business_summary', '{"summary":"legacy"}', 'legacy', NULL);
            """,
        )
        conn.commit()
    finally:
        conn.close()

    engine = await create_db_engine(str(db_path))
    try:
        async with engine.begin() as db:
            violations = (await db.execute(text("PRAGMA foreign_key_check"))).fetchall()
            assert violations == [], (
                f"rebuild left foreign-key violations: {violations!r}"
            )
    finally:
        await engine.dispose()
