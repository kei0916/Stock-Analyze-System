"""/api/screening/* JSON API テスト."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException, status

from stock_analyze_system.services.screening import (
    AddToTargetsResult,
    Bucket,
    Distribution,
    ScreenResult,
    ScreenResultItem,
    ScreenSpec,
)
from stock_analyze_system.web.routes import screening as screening_routes


class TestScreeningApi:
    def test_fields_returns_metadata(self, auth_client):
        resp = auth_client.get("/api/screening/fields")
        assert resp.status_code == 200
        body = resp.json()
        assert any(f["field"] == "trailing_per" for f in body["numeric"])
        assert any(f["field"] == "sector" for f in body["categorical"])

    def test_run_returns_400_on_validation_error(self, monkeypatch, auth_client):
        mock_svc = MagicMock()
        mock_svc.run_screen = AsyncMock(side_effect=ValueError("unknown field: 'company_id'"))
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)
        resp = auth_client.post(
            "/api/screening/run",
            json={"filters": [{"field": "company_id", "op": "gte", "value": 0}]},
        )
        assert resp.status_code == 400

    def test_run_returns_503_when_service_unavailable(self, monkeypatch, auth_client):
        def _raise(_services):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="screening_service unavailable",
            )
        monkeypatch.setattr(screening_routes, "_require_service", _raise)
        resp = auth_client.post("/api/screening/run", json={})
        assert resp.status_code == 503

    def test_run_sanitizes_non_finite_metrics(self, monkeypatch, auth_client):
        mock_svc = MagicMock()
        mock_svc.run_screen = AsyncMock(return_value=ScreenResult(
            items=[
                ScreenResultItem(
                    company_id="US_CETX",
                    ticker="CETX",
                    name="Cemtrex",
                    sector="Technology",
                    market="NASDAQ",
                    metrics={
                        "pbr": float("nan"),
                        "psr": float("inf"),
                        "roe": 1.2,
                    },
                ),
            ],
            total_matched=1,
            spec=ScreenSpec(),
            limit=100,
            offset=0,
        ))
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)

        resp = auth_client.post("/api/screening/run", json={})

        assert resp.status_code == 200
        metrics = resp.json()["items"][0]["metrics"]
        assert metrics["pbr"] is None
        assert metrics["psr"] is None
        assert metrics["roe"] == 1.2

    def test_distributions_returns_field_payload(self, monkeypatch, auth_client):
        mock_svc = MagicMock()
        mock_svc.get_distribution = AsyncMock(return_value=Distribution(
            field="trailing_per", min=10.0, max=30.0,
            null_count=2, finite_count=8, non_finite_count=0,
            buckets=[Bucket(10.0, 30.0, 8)],
        ))
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)
        resp = auth_client.get("/api/screening/distributions/trailing_per")
        assert resp.status_code == 200
        body = resp.json()
        assert body["field"] == "trailing_per"
        assert body["finite_count"] == 8
        assert body["non_finite_count"] == 0

    def test_distributions_400_on_categorical_field(self, monkeypatch, auth_client):
        mock_svc = MagicMock()
        mock_svc.get_distribution = AsyncMock(side_effect=ValueError("numeric only"))
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)
        resp = auth_client.get("/api/screening/distributions/sector")
        assert resp.status_code == 400

    def test_targets_returns_added_count(self, monkeypatch, auth_client):
        mock_svc = MagicMock()
        mock_svc.add_to_targets = AsyncMock(return_value=AddToTargetsResult(
            requested=2, added=2, already_present=0, skipped=0,
        ))
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)
        resp = auth_client.post(
            "/api/screening/targets",
            json={"company_ids": ["US_AAPL", "US_MSFT"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["added"] == 2

    def test_targets_400_on_empty_list(self, monkeypatch, auth_client):
        mock_svc = MagicMock()
        mock_svc.add_to_targets = AsyncMock(
            side_effect=ValueError("company_ids must be non-empty"),
        )
        monkeypatch.setattr(screening_routes, "_require_service", lambda services: mock_svc)
        resp = auth_client.post("/api/screening/targets", json={"company_ids": []})
        assert resp.status_code == 400
