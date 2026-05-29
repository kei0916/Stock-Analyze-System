"""AppState.clients が Web リクエスト間で singleton として再利用されることを確認する。"""
from __future__ import annotations

from fastapi import Depends


def test_app_state_clients_singleton_across_requests(app, auth_client):
    """2 回リクエストを送って ClientBundle の SEC クライアント id が一致すること"""
    observed_ids: list[int] = []

    from stock_analyze_system.web.dependencies import AppState, get_app_state

    @app.get("/__test_singleton")
    async def _probe(state: AppState = Depends(get_app_state)):
        observed_ids.append(id(state.clients.sec))
        return {"ok": True}

    assert auth_client.get("/__test_singleton").status_code == 200
    assert auth_client.get("/__test_singleton").status_code == 200

    assert len(observed_ids) == 2
    assert observed_ids[0] == observed_ids[1]
