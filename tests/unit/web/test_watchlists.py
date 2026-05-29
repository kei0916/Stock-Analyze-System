"""Watchlist routes tests"""


class TestWatchlistList:
    def test_get_list_authenticated(self, auth_client):
        resp = auth_client.get("/watchlists")
        assert resp.status_code == 200
        assert "ウォッチリスト" in resp.text

    def test_get_list_unauthenticated_redirects(self, client):
        resp = client.get("/watchlists", follow_redirects=False)
        assert resp.status_code == 303

    def test_create_watchlist(self, auth_client):
        resp = auth_client.post(
            "/watchlists",
            data={"name": "Tech", "description": "技術株"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        # 作成したリストが一覧に現れる
        resp = auth_client.get("/watchlists")
        assert "Tech" in resp.text
        assert "技術株" in resp.text


class TestWatchlistDetail:
    def test_detail_for_existing(self, auth_client):
        # まず1件作る
        auth_client.post(
            "/watchlists",
            data={"name": "Detail Test", "description": ""},
            follow_redirects=False,
        )
        # 一覧でIDは見えないので、最初の1件=ID 1を叩く
        resp = auth_client.get("/watchlists/1")
        assert resp.status_code == 200
        assert "Detail Test" in resp.text

    def test_detail_unknown_returns_404(self, auth_client):
        resp = auth_client.get("/watchlists/99999")
        assert resp.status_code == 404


class TestWatchlistDuplicate:
    def test_create_duplicate_name_returns_409(self, auth_client):
        """同名ウォッチリスト作成時 DuplicateError → 409 Conflict"""
        auth_client.post(
            "/watchlists",
            data={"name": "Unique", "description": ""},
            follow_redirects=False,
        )
        resp = auth_client.post(
            "/watchlists",
            data={"name": "Unique", "description": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 409
