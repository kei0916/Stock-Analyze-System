"""JSON API endpoint tests"""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from stock_analyze_system.models.enums import FilingType
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.document_index import DocumentIndex
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.models.valuation import Valuation


@pytest.fixture
async def seeded_financials(auth_client, db_writer):
    await db_writer(
        Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        ),
        FinancialData(
            company_id="US_AAPL",
            accounting_standard="US-GAAP",
            currency="USD",
            period_type="annual",
            fiscal_year_end=date(2024, 9, 30),
            revenue=391000.0,
            cogs=210000.0,
            net_income=93700.0,
            operating_income=123000.0,
            eps=6.11,
            operating_cf=110000.0,
            capex=-9500.0,
            ebitda=130000.0,
            fcf=100500.0,
        ),
    )
    return auth_client


@pytest.fixture
async def seeded_no_cogs_client(auth_client, db_writer):
    """gross_profit None 検証用。cogs を欠落させる。"""
    await db_writer(
        Company(
            id="US_X", ticker="X", name="X Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        ),
        FinancialData(
            company_id="US_X",
            accounting_standard="US-GAAP",
            currency="USD",
            period_type="annual",
            fiscal_year_end=date(2024, 12, 31),
            revenue=100.0,
            cogs=None,
        ),
    )
    return auth_client


class TestFinancialsApi:
    def test_returns_annual_records(self, seeded_financials):
        resp = seeded_financials.get("/api/stocks/US_AAPL/financials/annual")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        row = data[0]
        assert row["revenue"] == 391000.0
        assert row["fiscal_year_end"] == "2024-09-30"
        assert row["eps"] == 6.11
        # チャート複数選択用に追加されたフィールド
        assert row["operating_cf"] == 110000.0
        assert row["capex"] == -9500.0
        assert row["ebitda"] == 130000.0
        assert row["fcf"] == 100500.0
        assert row["cogs"] == 210000.0
        # gross_profit = revenue - cogs
        assert row["gross_profit"] == 391000.0 - 210000.0

    def test_gross_profit_is_none_when_cogs_missing(self, seeded_no_cogs_client):
        resp = seeded_no_cogs_client.get("/api/stocks/US_X/financials/annual")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["gross_profit"] is None
        assert data[0]["cogs"] is None
        assert data[0]["revenue"] == 100.0

    def test_unknown_period_422(self, seeded_financials):
        resp = seeded_financials.get("/api/stocks/US_AAPL/financials/yearly")
        assert resp.status_code == 422

    def test_unknown_company_returns_empty_list(self, auth_client):
        resp = auth_client.get("/api/stocks/US_NOPE/financials/annual")
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.fixture
async def seeded_valuations(auth_client, db_writer):
    await db_writer(
        Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        ),
        Valuation(
            company_id="US_AAPL",
            currency="USD",
            date=date(2024, 10, 1),
            stock_price=220.5,
            market_cap=3_300_000.0,
            per=28.4,
            pbr=45.1,
            ev_ebitda=22.0,
            psr=7.6,
            fcf_yield=0.03,
            last_updated=datetime(2026, 4, 29, 8, 30, 0),
        ),
    )
    return auth_client


@pytest.fixture
async def seeded_two_valuations_client(auth_client, db_writer):
    """5年枠の境界(古い1件 + 新しい1件)を seed"""
    from datetime import timedelta
    today = date.today()
    await db_writer(
        Company(
            id="US_FOO", ticker="FOO", name="Foo Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        ),
        Valuation(
            company_id="US_FOO", currency="USD",
            date=today - timedelta(days=6 * 365), per=10.0,
        ),
        Valuation(
            company_id="US_FOO", currency="USD",
            date=today - timedelta(days=30), per=20.0,
        ),
    )
    return auth_client


class TestValuationsApi:
    def test_returns_valuation_history(self, seeded_valuations):
        resp = seeded_valuations.get("/api/stocks/US_AAPL/valuations")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["per"] == 28.4
        assert data[0]["date"] == "2024-10-01"
        assert data[0]["stock_price"] == 220.5
        assert data[0]["last_updated"] == "2026-04-29T08:30:00"

    def test_unknown_company_returns_empty_list(self, auth_client):
        resp = auth_client.get("/api/stocks/US_NOPE/valuations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_years_param_accepted_within_range(self, seeded_valuations):
        resp = seeded_valuations.get("/api/stocks/US_AAPL/valuations?years=5")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_years_param_out_of_range_returns_400(self, seeded_valuations):
        resp = seeded_valuations.get("/api/stocks/US_AAPL/valuations?years=0")
        assert resp.status_code == 400
        resp = seeded_valuations.get("/api/stocks/US_AAPL/valuations?years=21")
        assert resp.status_code == 400

    def test_years_filters_out_records_older_than_window(self, seeded_two_valuations_client):
        resp = seeded_two_valuations_client.get("/api/stocks/US_FOO/valuations?years=5")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["per"] == 20.0
        # 10年だと両方ヒット
        resp = seeded_two_valuations_client.get("/api/stocks/US_FOO/valuations?years=10")
        assert len(resp.json()) == 2


@pytest.fixture
async def seeded_metrics(auth_client, db_writer):
    # ROE/ROA/marginを計算可能なデータを持つ1期分
    await db_writer(
        Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        ),
        FinancialData(
            company_id="US_AAPL",
            accounting_standard="US-GAAP",
            currency="USD",
            period_type="annual",
            fiscal_year_end=date(2024, 9, 30),
            revenue=391000.0,
            operating_income=120000.0,
            net_income=93700.0,
            total_assets=352000.0,
            equity=65000.0,
        ),
    )
    return auth_client


class TestMetricsApi:
    def test_returns_metrics_for_annual(self, seeded_metrics):
        resp = seeded_metrics.get("/api/stocks/US_AAPL/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        row = data[0]
        assert row["fiscal_year_end"] == "2024-09-30"
        # ROE = 93700 / 65000 ≈ 1.4415
        assert row["roe"] is not None
        assert abs(row["roe"] - (93700.0 / 65000.0)) < 1e-6
        # net_margin = 93700 / 391000 ≈ 0.2396
        assert row["net_margin"] is not None
        assert abs(row["net_margin"] - (93700.0 / 391000.0)) < 1e-6

    def test_unknown_company_returns_empty_list(self, auth_client):
        resp = auth_client.get("/api/stocks/US_NOPE/metrics")
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.fixture
async def seeded_filing(auth_client, db_writer):
    """Apple + 10-K filing 1件をseed"""
    await db_writer(
        Company(
            id="US_AAPL", ticker="AAPL", name="Apple Inc",
            market="NASDAQ", accounting_standard="US-GAAP",
        ),
        Filing(
            company_id="US_AAPL",
            source="SEC",
            filing_type="10-K",
            period_type="annual",
            fiscal_year=2024,
            period_end=date(2024, 9, 30),
            filed_at=date(2024, 11, 1),
            accession_no="0000320193-24-000123",
            storage_path="/tmp/test",
        ),
    )
    return auth_client


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

    def test_get_pageindex_rag_service_returns_when_pageindex_enabled(self):
        """ADR-004 amendment §B: pageindex_available=True なら 503 を投げず通過する.
        Issue 2 (Round 8 code review): 既存 3 件は disabled 経路ばかりで、enabled 時の
        通過が helper-direct には verified されていなかった。境界条件カバーの完成形."""
        from stock_analyze_system.web.routes.api import _get_pageindex_rag_service

        fake_rag = SimpleNamespace(pageindex_available=True)
        services = SimpleNamespace(rag_service=fake_rag)
        result = _get_pageindex_rag_service(services)
        assert result is fake_rag


class TestRagApi:
    def test_ask_request_accepts_edinet_filing_type(self):
        from stock_analyze_system.web.routes.api import AskRequest

        payload = AskRequest(
            question="売上は？",
            filing_id=123,
            filing_type="annual_report",
        )

        assert payload.filing_id == 123
        assert payload.filing_type == FilingType.ANNUAL_REPORT

    def test_ask_returns_answer_when_rag_enabled(
        self, monkeypatch, seeded_filing,
    ):
        """RAGサービスが存在する場合、ask_questionが呼ばれて回答が返る"""
        mock_rag = AsyncMock()
        mock_rag.ask_question.return_value = SimpleNamespace(
            answer="AAPL 2024年度の売上は391Bドルです",
            source_pages=[12, 13],
            source_sections=["Item 7. MD&A"],
        )
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_pageindex_rag_service", lambda services: mock_rag,
        )
        resp = seeded_filing.post(
            "/api/stocks/US_AAPL/rag/ask",
            json={"question": "売上は？", "filing_type": "10-K"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "AAPL 2024年度の売上は391Bドルです"
        assert data["source_pages"] == [12, 13]
        assert data["source_sections"] == ["Item 7. MD&A"]

    def test_ask_returns_503_when_rag_disabled(self, seeded_filing):
        """RAGサービスが無効の場合503を返す"""
        # デフォルトweb_configはpageindex.enabled=Falseのため
        # rag_service は non-None だが pageindex_available=False → 503
        resp = seeded_filing.post(
            "/api/stocks/US_AAPL/rag/ask",
            json={"question": "売上は？"},
        )
        assert resp.status_code == 503

    def test_ask_returns_404_when_no_filing(self, monkeypatch, auth_client):
        """filing未登録の場合404を返す(RAGは有効化)"""
        mock_rag = AsyncMock()
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_pageindex_rag_service", lambda services: mock_rag,
        )
        resp = auth_client.post(
            "/api/stocks/US_NOPE/rag/ask",
            json={"question": "売上は？"},
        )
        assert resp.status_code == 404

    async def test_ask_missing_filing_does_not_consume_rate_limit(
        self, monkeypatch, seeded_aapl_client, db_writer,
    ):
        mock_rag = AsyncMock()
        mock_rag.ask_question.return_value = SimpleNamespace(
            answer="ok",
            source_pages=[],
            source_sections=[],
        )
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_pageindex_rag_service", lambda services: mock_rag,
        )

        for _ in range(3):
            resp = seeded_aapl_client.post(
                "/api/stocks/US_AAPL/rag/ask",
                json={"question": "売上は？", "filing_type": "10-K"},
            )
            assert resp.status_code == 404

        await db_writer(
            Filing(
                company_id="US_AAPL",
                source="SEC",
                filing_type="10-K",
                period_type="annual",
                fiscal_year=2024,
                period_end=date(2024, 9, 30),
                filed_at=date(2024, 11, 1),
                accession_no="0000320193-24-000123",
                storage_path="/tmp/test",
            ),
        )

        resp = seeded_aapl_client.post(
            "/api/stocks/US_AAPL/rag/ask",
            json={"question": "売上は？", "filing_type": "10-K"},
        )

        assert resp.status_code == 200
        mock_rag.ask_question.assert_called_once()

    def test_ask_rate_limited_after_repeated_requests(
        self, monkeypatch, seeded_filing,
    ):
        mock_rag = AsyncMock()
        mock_rag.ask_question.return_value = SimpleNamespace(
            answer="ok",
            source_pages=[],
            source_sections=[],
        )
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_pageindex_rag_service", lambda services: mock_rag,
        )

        for _ in range(3):
            resp = seeded_filing.post(
                "/api/stocks/US_AAPL/rag/ask",
                json={"question": "売上は？", "filing_type": "10-K"},
            )
            assert resp.status_code == 200

        resp = seeded_filing.post(
            "/api/stocks/US_AAPL/rag/ask",
            json={"question": "売上は？", "filing_type": "10-K"},
        )

        assert resp.status_code == 429

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

    def test_index_builds_tree_when_rag_enabled(
        self, monkeypatch, seeded_filing,
    ):
        """rag_index: build_index を呼び node_count を返す"""
        mock_rag = AsyncMock()
        mock_rag.build_index.return_value = {
            "structure": [{"page": 1}, {"page": 2}, {"page": 3}],
        }
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_pageindex_rag_service", lambda services: mock_rag,
        )
        resp = seeded_filing.post(
            "/api/stocks/US_AAPL/rag/index",
            params={"filing_type": "10-K"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"node_count": 3}

    def test_index_returns_zero_when_tree_has_no_structure(
        self, monkeypatch, seeded_filing,
    ):
        """tree に structure キーが無い場合 node_count=0"""
        mock_rag = AsyncMock()
        mock_rag.build_index.return_value = {}
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_pageindex_rag_service", lambda services: mock_rag,
        )
        resp = seeded_filing.post(
            "/api/stocks/US_AAPL/rag/index",
        )
        assert resp.status_code == 200
        assert resp.json() == {"node_count": 0}

    def test_index_rag_disabled_does_not_consume_rate_limit(
        self, monkeypatch, seeded_filing,
    ):
        for _ in range(3):
            resp = seeded_filing.post(
                "/api/stocks/US_AAPL/rag/index",
                params={"filing_type": "10-K"},
            )
            assert resp.status_code == 503

        mock_rag = AsyncMock()
        mock_rag.build_index.return_value = {"structure": [{"page": 1}]}
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_pageindex_rag_service", lambda services: mock_rag,
        )

        resp = seeded_filing.post(
            "/api/stocks/US_AAPL/rag/index",
            params={"filing_type": "10-K"},
        )

        assert resp.status_code == 200
        assert resp.json() == {"node_count": 1}

    def test_analyze_streams_progress_events(
        self, monkeypatch, seeded_filing,
    ):
        """rag_analyze: NDJSON で各タイプの進捗イベントをストリームする"""
        events = [
            {"event": "extracting"},
            {"event": "started", "total": 2},
            {"event": "phase", "index": 0, "total": 2,
             "analysis_type": "business_summary", "label": "事業概要"},
            {"event": "done", "index": 0, "analysis_type": "business_summary"},
            {"event": "phase", "index": 1, "total": 2,
             "analysis_type": "risk_factors", "label": "リスク要因"},
            {"event": "cached", "index": 1, "analysis_type": "risk_factors"},
            {"event": "complete"},
        ]

        async def fake_stream(filing):
            for evt in events:
                yield evt

        mock_rag = SimpleNamespace(run_full_analysis_stream=fake_stream)
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_rag_service", lambda services: mock_rag,
        )
        resp = seeded_filing.post(
            "/api/stocks/US_AAPL/rag/analyze",
            params={"filing_type": "10-K"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/x-ndjson")
        lines = [line for line in resp.text.split("\n") if line.strip()]
        decoded = [__import__("json").loads(line) for line in lines]
        assert decoded[0] == {"event": "extracting"}
        assert decoded[1] == {"event": "started", "total": 2}
        assert decoded[-1] == {"event": "complete"}
        # phase イベントが2回(タイプ数ぶん)
        phases = [e for e in decoded if e.get("event") == "phase"]
        assert len(phases) == 2
        assert phases[0]["analysis_type"] == "business_summary"
        assert phases[1]["analysis_type"] == "risk_factors"

    async def test_analyze_rejects_unsupported_filing_before_streaming(
        self, auth_client, db_writer,
    ):
        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=701, company_id="US_AAPL", source="EDINET",
                filing_type="annual_report", period_type="annual",
                fiscal_year=2025, doc_id="S100UNSUP",
                period_end=date(2025, 3, 31),
            ),
        )

        resp = auth_client.post(
            "/api/stocks/US_AAPL/rag/analyze",
            params={"filing_id": 701},
        )

        assert resp.status_code == 422
        assert "SEC" in resp.json()["detail"]

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

    async def test_history_returns_records_even_when_pageindex_disabled(
        self, seeded_filing, db_writer,
    ):
        """ADR-004 amendment §B 回帰ガード: PageIndex 無効状態でも
        rag/history は過去の Q&A を返す (履歴閲覧は PageIndex 非依存).

        旧実装は `pageindex_available=False` を guard にしており、設定変更
        だけで既存履歴が UI から消える regression があった (`RagService.
        get_qa_history` は `_qa_history_repo` のみ判定し PageIndex に依存
        しないため、API 側で guard する正当性なし)."""
        from stock_analyze_system.models.rag_qa_history import RagQaHistory
        await db_writer(
            RagQaHistory(
                company_id="US_AAPL",
                filing_id=None,
                question="過去ログ閲覧テスト",
                answer="PageIndex 無効でも返る",
            )
        )

        # default web_config は pageindex.enabled=False (= pageindex_available
        # も False) で動く.
        resp = seeded_filing.get("/api/stocks/US_AAPL/rag/history")
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload) == 1
        assert payload[0]["question"] == "過去ログ閲覧テスト"

    def test_analyze_stream_catches_unexpected_exception(
        self, monkeypatch, seeded_filing,
    ):
        """ストリーム途中で例外が起きても error+complete に変換される"""
        async def boom_stream(filing):
            yield {"event": "extracting"}
            raise RuntimeError("LLM offline")

        mock_rag = SimpleNamespace(run_full_analysis_stream=boom_stream)
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_rag_service", lambda services: mock_rag,
        )
        resp = seeded_filing.post(
            "/api/stocks/US_AAPL/rag/analyze",
            params={"filing_type": "10-K"},
        )
        assert resp.status_code == 200
        import json as _json
        decoded = [
            _json.loads(line) for line in resp.text.split("\n") if line.strip()
        ]
        assert decoded[0] == {"event": "extracting"}
        assert decoded[-1] == {"event": "complete"}
        errors = [e for e in decoded if e.get("event") == "error"]
        assert len(errors) == 1
        assert "LLM offline" in errors[0]["message"]


class TestRagFilingId:
    async def test_analyze_uses_filing_id_when_provided(
        self, auth_client, db_writer, monkeypatch,
    ):
        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=42, company_id="US_AAPL", source="SEC",
                filing_type="10-K", period_type="annual",
                fiscal_year=2023, accession_no="A-OLD",
                storage_path="/tmp/old", period_end=date(2023, 9, 30),
            ),
            Filing(
                company_id="US_AAPL", source="SEC",
                filing_type="10-Q", period_type="quarterly",
                fiscal_year=2024, accession_no="A-Q1",
                period_end=date(2024, 6, 30),
            ),
        )
        called_with: dict[str, int] = {}

        async def fake_stream(filing):
            called_with["filing_id"] = filing.id
            yield {"event": "complete"}

        mock_rag = SimpleNamespace(run_full_analysis_stream=fake_stream)
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_rag_service", lambda services: mock_rag,
        )

        resp = auth_client.post(
            "/api/stocks/US_AAPL/rag/analyze",
            params={"filing_id": 42},
        )

        assert resp.status_code == 200
        assert called_with["filing_id"] == 42

    async def test_analyze_returns_404_for_other_company_filing_id(
        self, auth_client, db_writer, monkeypatch,
    ):
        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Company(
                id="US_MSFT", ticker="MSFT", name="Microsoft",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=99, company_id="US_MSFT", source="SEC",
                filing_type="10-K", period_type="annual", fiscal_year=2024,
                accession_no="MSFT-1",
            ),
        )
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_rag_service", lambda services: AsyncMock(),
        )

        resp = auth_client.post(
            "/api/stocks/US_AAPL/rag/analyze",
            params={"filing_id": 99},
        )

        assert resp.status_code == 404

    async def test_ask_uses_filing_id_when_provided(
        self, auth_client, db_writer, monkeypatch,
    ):
        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=77, company_id="US_AAPL", source="SEC",
                filing_type="10-K", period_type="annual", fiscal_year=2023,
                accession_no="A-OLD", storage_path="/tmp/old",
            ),
            Filing(
                company_id="US_AAPL", source="SEC",
                filing_type="10-Q", period_type="quarterly", fiscal_year=2024,
                accession_no="A-Q1",
            ),
        )
        mock_rag = AsyncMock()
        mock_rag.ask_question.return_value = SimpleNamespace(
            answer="ok", source_pages=[], source_sections=[],
        )
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_pageindex_rag_service", lambda services: mock_rag,
        )

        resp = auth_client.post(
            "/api/stocks/US_AAPL/rag/ask",
            json={"question": "売上は？", "filing_id": 77},
        )

        assert resp.status_code == 200
        assert mock_rag.ask_question.await_args.args[0].id == 77

    async def test_index_uses_filing_id_when_provided(
        self, auth_client, db_writer, monkeypatch,
    ):
        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=88, company_id="US_AAPL", source="SEC",
                filing_type="10-K", period_type="annual", fiscal_year=2023,
                accession_no="A-OLD", storage_path="/tmp/old",
            ),
        )
        mock_rag = AsyncMock()
        mock_rag.build_index.return_value = {"structure": [{"page": 1}]}
        from stock_analyze_system.web.routes import api as api_module
        monkeypatch.setattr(
            api_module, "_get_pageindex_rag_service", lambda services: mock_rag,
        )

        resp = auth_client.post(
            "/api/stocks/US_AAPL/rag/index",
            params={"filing_id": 88},
        )

        assert resp.status_code == 200
        assert mock_rag.build_index.await_args.args[0].id == 88


class TestFilingOptionsDefault:
    async def test_options_include_quarterly_filings(
        self, auth_client, db_writer,
    ):
        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=11, company_id="US_AAPL", source="SEC",
                filing_type="10-K", period_type="annual",
                fiscal_year=2023, accession_no="A-K",
                period_end=date(2023, 9, 30),
            ),
            Filing(
                id=12, company_id="US_AAPL", source="SEC",
                filing_type="10-Q", period_type="quarterly",
                fiscal_year=2024, accession_no="A-Q",
                period_end=date(2024, 6, 30),
            ),
        )

        resp = auth_client.get("/api/stocks/US_AAPL/rag/filing_options")

        assert resp.status_code == 200
        body = resp.json()
        option_ids = [f["id"] for f in body["annual_options"]]
        assert option_ids == [12, 11]

    async def test_options_exclude_annual_report_and_non_sec(
        self, auth_client, db_writer,
    ):
        """ADR-004 amendment §A: rag_filing_options は SEC source の
        10-K / 10-Q / 20-F / 6-K だけを annual_options に返す."""
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

    async def test_default_prefers_indexed_filing(
        self, auth_client, db_writer, tmp_path,
    ):
        auth_client.app.state.app_state.config.pageindex.enabled = True
        indexed_path = tmp_path / "idx"
        (indexed_path / "raw").mkdir(parents=True)
        (indexed_path / "raw" / "filing.htm").write_text("indexed")
        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=1, company_id="US_AAPL", source="SEC",
                filing_type="10-K", period_type="annual",
                fiscal_year=2023, accession_no="A-1",
                storage_path=str(indexed_path), period_end=date(2023, 9, 30),
            ),
            Filing(
                id=2, company_id="US_AAPL", source="SEC",
                filing_type="10-Q", period_type="quarterly",
                fiscal_year=2024, accession_no="A-2",
                period_end=date(2024, 6, 30),
            ),
            DocumentIndex(
                filing_id=1, company_id="US_AAPL",
                index_json="{}", model_name="m",
                page_count=1, node_count=1,
            ),
        )

        resp = auth_client.get("/api/stocks/US_AAPL/rag/filing_options")

        assert resp.status_code == 200
        body = resp.json()
        assert body["default"]["id"] == 1
        assert body["default"]["content_available"] is True
        assert body["default"]["is_fallback_default"] is False

    async def test_default_treats_sec_pdf_only_as_content_unavailable(
        self, auth_client, db_writer, tmp_path,
    ):
        pdf_only_path = tmp_path / "pdf-only"
        pdf_only_path.mkdir()
        (pdf_only_path / "converted.pdf").write_text("pdf bytes")
        raw_path = tmp_path / "raw-html"
        (raw_path / "raw").mkdir(parents=True)
        (raw_path / "raw" / "filing.htm").write_text("html")

        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=31, company_id="US_AAPL", source="SEC",
                filing_type="10-K", period_type="annual",
                fiscal_year=2025, accession_no="A-PDF",
                storage_path=str(pdf_only_path), period_end=date(2025, 9, 30),
            ),
            Filing(
                id=32, company_id="US_AAPL", source="SEC",
                filing_type="10-K", period_type="annual",
                fiscal_year=2024, accession_no="A-RAW",
                storage_path=str(raw_path), period_end=date(2024, 9, 30),
            ),
        )

        resp = auth_client.get("/api/stocks/US_AAPL/rag/filing_options")

        assert resp.status_code == 200
        body = resp.json()
        assert body["default"]["id"] == 32
        pdf_only_option = next(f for f in body["annual_options"] if f["id"] == 31)
        assert pdf_only_option["content_available"] is False

    async def test_default_prefers_content_when_no_index(
        self, auth_client, db_writer, tmp_path,
    ):
        content_path = tmp_path / "content"
        (content_path / "raw").mkdir(parents=True)
        (content_path / "raw" / "filing.htm").write_text("content")
        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=3, company_id="US_AAPL", source="SEC",
                filing_type="10-K", period_type="annual",
                fiscal_year=2023, accession_no="A-3",
                storage_path=str(content_path), period_end=date(2023, 9, 30),
            ),
            Filing(
                id=4, company_id="US_AAPL", source="SEC",
                filing_type="10-Q", period_type="quarterly",
                fiscal_year=2024, accession_no="A-4",
                period_end=date(2024, 6, 30),
            ),
        )

        resp = auth_client.get("/api/stocks/US_AAPL/rag/filing_options")

        assert resp.status_code == 200
        body = resp.json()
        assert body["default"]["id"] == 3
        assert body["default"]["content_available"] is True
        assert body["default"]["is_fallback_default"] is False

    async def test_default_skips_stale_storage_path(
        self, auth_client, db_writer, tmp_path,
    ):
        stale_path = tmp_path / "stale"
        stale_path.mkdir()
        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=5, company_id="US_AAPL", source="SEC",
                filing_type="10-K", period_type="annual",
                fiscal_year=2023, accession_no="A-5",
                storage_path=str(stale_path), period_end=date(2023, 9, 30),
            ),
            Filing(
                id=6, company_id="US_AAPL", source="SEC",
                filing_type="10-Q", period_type="quarterly",
                fiscal_year=2024, accession_no="A-6",
                period_end=date(2024, 6, 30),
            ),
        )

        resp = auth_client.get("/api/stocks/US_AAPL/rag/filing_options")

        assert resp.status_code == 200
        body = resp.json()
        assert body["default"]["id"] == 6
        assert body["default"]["content_available"] is False
        assert body["default"]["is_fallback_default"] is True
        stale_option = next(f for f in body["annual_options"] if f["id"] == 5)
        assert stale_option["content_available"] is False

    async def test_default_falls_back_to_unfetched_latest(
        self, auth_client, db_writer,
    ):
        await db_writer(
            Company(
                id="US_AAPL", ticker="AAPL", name="Apple",
                market="NASDAQ", accounting_standard="US-GAAP",
            ),
            Filing(
                id=10, company_id="US_AAPL", source="SEC",
                filing_type="10-Q", period_type="quarterly",
                fiscal_year=2024, accession_no="A-Q",
                period_end=date(2024, 6, 30),
            ),
        )

        resp = auth_client.get("/api/stocks/US_AAPL/rag/filing_options")

        assert resp.status_code == 200
        body = resp.json()
        assert body["default"]["id"] == 10
        assert body["default"]["content_available"] is False
        assert body["default"]["is_fallback_default"] is True


class TestRagServiceStream:
    async def test_storage_path_missing_yields_error_then_complete(self):
        """filing.storage_path が None なら早期に error + complete を yield"""
        from types import SimpleNamespace as NS
        from stock_analyze_system.services.rag_service import RagService

        rag = RagService(
            pageindex_service=NS(),
            analysis_repo=NS(),
            llm_client=NS(),
        )
        filing = NS(id=1, company_id="US_X", storage_path=None)
        events = [evt async for evt in rag.run_full_analysis_stream(filing)]
        assert len(events) == 2
        assert events[0]["event"] == "error"
        assert "filings download" in events[0]["message"]
        assert events[1] == {"event": "complete"}
