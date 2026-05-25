"""RAG Q&A history repository tests."""
from __future__ import annotations

from stock_analyze_system.models.company import Company
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.repositories.rag_qa_history import RagQaHistoryRepository


async def test_rag_qa_history_add_and_list_by_company(session):
    session.add(Company(
        id="US_AAPL",
        ticker="AAPL",
        name="Apple",
        market="NASDAQ",
        accounting_standard="US-GAAP",
    ))
    await session.flush()
    filing = Filing(
        company_id="US_AAPL",
        source="SEC",
        filing_type="10-K",
        period_type="annual",
        fiscal_year=2025,
    )
    session.add(filing)
    await session.flush()

    repo = RagQaHistoryRepository(session)
    row = await repo.add(
        company_id="US_AAPL",
        filing_id=filing.id,
        question="What are the risks?",
        answer="Competition.",
        source_pages=[1, 2],
        source_sections=["Risk Factors"],
        model_name="test-model",
        confidence=0.8,
    )

    rows = await repo.list_by_company("US_AAPL")
    payload = RagQaHistoryRepository.to_dict(rows[0])

    assert rows == [row]
    assert payload["question"] == "What are the risks?"
    assert payload["source_pages"] == [1, 2]
    assert payload["source_sections"] == ["Risk Factors"]
    assert payload["model_name"] == "test-model"
