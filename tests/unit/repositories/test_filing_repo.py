"""FilingRepository のテスト"""
from datetime import date

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.document_index import DocumentIndex
from stock_analyze_system.models.enums import FilingSource
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.filing import FilingRepository


async def test_get_latest_filing(session):
    """最新ファイリングを filing_type 指定で取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2023,
    ))
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
    ))
    await session.flush()
    repo = FilingRepository(session)
    result = await repo.get_latest_filing("US_AAPL", "10-K")
    assert result is not None
    assert result.fiscal_year == 2024


async def test_list_filings(session):
    """企業のファイリング一覧を取得できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
    ))
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-Q",
        period_type="quarterly", fiscal_year=2024,
    ))
    await session.flush()
    repo = FilingRepository(session)
    results = await repo.list_filings("US_AAPL")
    assert len(results) == 2


async def test_list_by_recency_orders_by_period_and_filed_dates(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    older = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024, period_end=date(2024, 9, 28),
    )
    newer = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-Q",
        period_type="quarterly", fiscal_year=2025, period_end=date(2025, 3, 29),
    )
    fallback = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2023, filed_at=date(2024, 1, 1),
    )
    session.add_all([older, fallback, newer])
    await session.flush()

    repo = FilingRepository(session)
    results = await repo.list_by_recency("US_AAPL")

    assert [f.id for f in results] == [newer.id, older.id, fallback.id]


async def test_get_company_identifiers_returns_cik_and_edinet_code(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
        cik="0000320193", edinet_code="E00001",
    ))
    await session.flush()

    repo = FilingRepository(session)

    assert await repo.get_company_identifiers("US_AAPL") == (
        "0000320193", "E00001",
    )
    assert await repo.get_company_identifiers("US_MISSING") == (None, None)


async def test_find_existing_accessions(session):
    """指定 accession のうち既存分のみ返すこと"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000320193-24-000123",
    ))
    await session.flush()
    repo = FilingRepository(session)
    existing = await repo.find_existing_accessions(
        "US_AAPL",
        ["0000320193-24-000123", "0000320193-25-000001"],
    )
    assert existing == {"0000320193-24-000123"}


async def test_find_existing_accessions_empty(session):
    repo = FilingRepository(session)
    assert await repo.find_existing_accessions("US_AAPL", []) == set()


async def test_find_existing_doc_ids(session):
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        market="TSE_PRIME", accounting_standard="IFRS",
    ))
    session.add(Filing(
        company_id="JP_7203", source="EDINET", filing_type="annual_report",
        period_type="annual", fiscal_year=2024, doc_id="S100AAAA",
    ))
    await session.flush()
    repo = FilingRepository(session)
    existing = await repo.find_existing_doc_ids(
        "JP_7203", ["S100AAAA", "S100BBBB"],
    )
    assert existing == {"S100AAAA"}


async def test_bulk_upsert_filings_sec(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FilingRepository(session)
    rows = [
        {
            "source": "SEC", "filing_type": "10-K", "period_type": "annual",
            "fiscal_year": 2024, "accession_no": "A-1",
        },
        {
            "source": "SEC", "filing_type": "10-Q", "period_type": "quarterly",
            "fiscal_year": 2024, "accession_no": "A-2",
        },
    ]
    count = await repo.bulk_upsert("US_AAPL", rows, source=FilingSource.SEC)
    assert count == 2
    assert await repo.count(company_id="US_AAPL") == 2


async def test_bulk_upsert_filings_rejects_unknown_source(session):
    repo = FilingRepository(session)
    import pytest

    class _Fake:
        def __str__(self):
            return "OTHER"

    with pytest.raises(ValueError, match="unknown source"):
        await repo.bulk_upsert(
            "US_AAPL",
            [{"filing_type": "10-K"}],
            source=_Fake(),  # type: ignore[arg-type]
        )


async def test_update_storage_sets_path_and_hash(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    f = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
    )
    session.add(f)
    await session.flush()

    repo = FilingRepository(session)
    await repo.update_storage(
        f.id, storage_path="/data/filings/SEC/US_AAPL/2024/annual/10-K/AC-1",
        content_hash="abc123",
    )
    await session.refresh(f)
    assert f.storage_path == "/data/filings/SEC/US_AAPL/2024/annual/10-K/AC-1"
    assert f.content_hash == "abc123"


async def test_get_latest_with_content_returns_latest_with_storage(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2023,
        storage_path="/data/old", period_end=date(2023, 9, 30),
    ))
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        storage_path=None, period_end=date(2024, 9, 28),
    ))
    session.add(Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-Q",
        period_type="quarterly", fiscal_year=2024,
        storage_path="/data/q1", period_end=date(2024, 6, 30),
    ))
    await session.flush()

    repo = FilingRepository(session)
    result = await repo.get_latest_with_content("US_AAPL")
    assert result is not None
    # 期末日が新しい /data/q1 (2024-06-30) > /data/old (2023-09-30)
    assert result.storage_path == "/data/q1"


async def test_get_latest_with_content_returns_none_when_empty(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FilingRepository(session)
    assert await repo.get_latest_with_content("US_AAPL") is None


async def test_get_latest_indexed_returns_latest_with_index(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    f1 = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2023,
        period_end=date(2023, 9, 30),
    )
    f2 = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        period_end=date(2024, 9, 28),
    )
    session.add_all([f1, f2])
    await session.flush()
    # f1 のみ index あり
    session.add(DocumentIndex(
        filing_id=f1.id, company_id="US_AAPL",
        index_json="{}", model_name="m", page_count=10, node_count=5,
    ))
    await session.flush()

    repo = FilingRepository(session)
    result = await repo.get_latest_indexed("US_AAPL")
    assert result is not None
    assert result.id == f1.id


async def test_get_latest_indexed_returns_none_when_no_indices(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = FilingRepository(session)
    assert await repo.get_latest_indexed("US_AAPL") is None
