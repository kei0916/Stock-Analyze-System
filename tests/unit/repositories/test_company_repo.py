"""CompanyRepository のテスト"""
from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.company import CompanyRepository


async def test_find_by_identifier_ticker(session):
    """ticker で企業を検索できること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple Inc.",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    result = await repo.find_by_identifier("AAPL")
    assert result is not None
    assert result.id == "US_AAPL"


async def test_find_by_identifier_security_code(session):
    """security_code で企業を検索できること"""
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        market="TSE_PRIME", accounting_standard="IFRS",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    result = await repo.find_by_identifier("7203")
    assert result is not None
    assert result.id == "JP_7203"


async def test_find_by_identifier_company_id(session):
    """company_id のサフィックスで検索できること"""
    session.add(Company(
        id="US_MSFT", ticker="MSFT", name="Microsoft",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    result = await repo.find_by_identifier("US_MSFT")
    assert result is not None
    assert result.id == "US_MSFT"


async def test_find_by_identifier_not_found(session):
    """存在しない識別子で None が返ること"""
    repo = CompanyRepository(session)
    result = await repo.find_by_identifier("NONEXIST")
    assert result is None


async def test_search(session):
    """部分一致検索が動作すること"""
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple Inc.",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="US_MSFT", ticker="MSFT", name="Microsoft Corp.",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    results = await repo.search("apple")
    assert len(results) == 1
    assert results[0].id == "US_AAPL"


async def test_search_japanese_name(session):
    """日本語名での部分一致検索が動作すること"""
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        name_ja="トヨタ自動車", market="TSE_PRIME", accounting_standard="IFRS",
    ))
    await session.flush()
    repo = CompanyRepository(session)
    results = await repo.search("トヨタ")
    assert len(results) == 1
