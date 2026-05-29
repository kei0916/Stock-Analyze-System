"""web/auth.py のテスト"""
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from itsdangerous import BadSignature

from stock_analyze_system.config import AppConfig, WebConfig
from stock_analyze_system.web.auth import (
    InMemoryRateLimiter,
    SESSION_COOKIE,
    SessionSigner,
    get_client_key,
    hash_password,
    require_user,
    verify_password,
)
from stock_analyze_system.web.app import create_app

from tests.unit.web.conftest import TEST_PASSWORD, TEST_PASSWORD_HASH


SECRET = "test-secret-do-not-use-in-prod"


class TestSessionSigner:
    def test_sign_and_unsign_round_trip(self):
        signer = SessionSigner(SECRET)
        token = signer.sign("alice")
        payload = signer.unsign(token, max_age_seconds=3600)
        assert payload["u"] == "alice"
        assert payload["iat"] > 0

    def test_unsign_rejects_tampered_token(self):
        signer = SessionSigner(SECRET)
        token = signer.sign("alice") + "x"
        with pytest.raises(BadSignature):
            signer.unsign(token, max_age_seconds=3600)

    def test_different_secret_rejects(self):
        sig_a = SessionSigner("secret-a")
        sig_b = SessionSigner("secret-b")
        token = sig_a.sign("alice")
        with pytest.raises(BadSignature):
            sig_b.unsign(token, max_age_seconds=3600)


class TestVerifyPassword:
    def test_match(self):
        assert verify_password(TEST_PASSWORD, TEST_PASSWORD_HASH) is True

    def test_mismatch(self):
        assert verify_password("wrong", TEST_PASSWORD_HASH) is False

    def test_empty_hash_rejects(self):
        assert verify_password("anything", "") is False

    def test_corrupt_hash_rejects(self):
        assert verify_password("anything", "not-a-bcrypt-hash") is False

    def test_hash_password_round_trip(self):
        h = hash_password("hunter2")
        assert verify_password("hunter2", h) is True
        assert verify_password("wrong", h) is False


class TestWebDefaults:
    def test_default_host_is_local_only(self):
        assert AppConfig().web.host == "127.0.0.1"


class TestClientKey:
    def test_uses_direct_client_host_by_default(self):
        request = SimpleNamespace(
            client=SimpleNamespace(host="10.0.0.10"),
            headers={"x-forwarded-for": "203.0.113.9"},
            app=SimpleNamespace(
                state=SimpleNamespace(
                    app_state=SimpleNamespace(
                        config=SimpleNamespace(
                            web=SimpleNamespace(
                                trust_proxy_headers=False,
                                trusted_proxy_hosts=[],
                            )
                        )
                    )
                )
            ),
        )

        assert get_client_key(request, "login") == "login:10.0.0.10"

    def test_uses_forwarded_for_from_trusted_proxy(self):
        # trusted_proxy_hops=1 (default) — トラステッドは直接接続プロキシ 1 段のみ。
        # XFF "203.0.113.9, 10.0.0.10" は (client=203.0.113.9, proxy=10.0.0.10) の
        # 順なので「最も右の untrusted hop」= 10.0.0.10 を採用する (spoof耐性)。
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"x-forwarded-for": "203.0.113.9, 10.0.0.10"},
            app=SimpleNamespace(
                state=SimpleNamespace(
                    app_state=SimpleNamespace(
                        config=SimpleNamespace(
                            web=SimpleNamespace(
                                trust_proxy_headers=True,
                                trusted_proxy_hosts=["127.0.0.1"],
                                trusted_proxy_hops=1,
                            )
                        )
                    )
                )
            ),
        )

        assert get_client_key(request, "login") == "login:10.0.0.10"

    def test_forwarded_for_honors_trusted_proxy_hops(self):
        # hops=2 のとき XFF の右端 1 つを trusted proxy として skip し、
        # 次のエントリ (= 元のクライアント) を採用する。
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"x-forwarded-for": "203.0.113.9, 10.0.0.10"},
            app=SimpleNamespace(
                state=SimpleNamespace(
                    app_state=SimpleNamespace(
                        config=SimpleNamespace(
                            web=SimpleNamespace(
                                trust_proxy_headers=True,
                                trusted_proxy_hosts=["127.0.0.1"],
                                trusted_proxy_hops=2,
                            )
                        )
                    )
                )
            ),
        )

        assert get_client_key(request, "login") == "login:203.0.113.9"


class TestInMemoryRateLimiter:
    def test_try_acquire_is_atomic_under_parallel_callers(self):
        limiter = InMemoryRateLimiter(max_attempts=1, window_seconds=60)
        barrier = threading.Barrier(2)
        results: list[object | None] = []

        def _worker():
            barrier.wait()
            results.append(limiter.try_acquire("login:127.0.0.1"))

        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert sum(result is not None for result in results) == 1

    def test_release_prunes_empty_bucket(self):
        now = 100.0
        limiter = InMemoryRateLimiter(
            max_attempts=1,
            window_seconds=60,
            now_fn=lambda: now,
        )

        lease = limiter.try_acquire("login:127.0.0.1")

        assert lease is not None
        assert "login:127.0.0.1" in limiter._events

        limiter.release(lease)

        assert "login:127.0.0.1" not in limiter._events

    def test_try_acquire_prunes_expired_buckets_for_other_keys(self):
        now = 100.0
        limiter = InMemoryRateLimiter(
            max_attempts=1,
            window_seconds=60,
            now_fn=lambda: now,
        )

        lease_a = limiter.try_acquire("login:198.51.100.10")
        lease_b = limiter.try_acquire("login:198.51.100.11")

        assert lease_a is not None
        assert lease_b is not None
        assert sorted(limiter._events) == [
            "login:198.51.100.10",
            "login:198.51.100.11",
        ]

        now = 200.0
        lease_c = limiter.try_acquire("login:198.51.100.12")

        assert lease_c is not None
        assert sorted(limiter._events) == ["login:198.51.100.12"]

    def test_release_prunes_expired_buckets_for_other_keys(self):
        now = 100.0
        limiter = InMemoryRateLimiter(
            max_attempts=1,
            window_seconds=60,
            now_fn=lambda: now,
        )

        stale = limiter.try_acquire("heavy:198.51.100.20")
        active = limiter.try_acquire("heavy:198.51.100.21")

        assert stale is not None
        assert active is not None

        now = 200.0
        limiter.release(active)

        assert limiter._events == {}


class TestAuthMiddleware:
    def test_unauthenticated_request_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"

    def test_static_path_is_public(self, client):
        resp = client.get("/static/app.css", follow_redirects=False)
        # 200 or 404 — middlewareがリダイレクトしないことを確認
        assert resp.status_code in (200, 404)

    def test_login_path_is_public(self, client):
        resp = client.get("/login", follow_redirects=False)
        # 200 (form rendered) / 404 (ルート未実装) / 405 — いずれもリダイレクトではない
        assert resp.status_code in (200, 404, 405)

    def test_invalid_session_cookie_redirects_to_login(self, client):
        """壊れた/改ざんされたセッションクッキーは BadSignature → /login リダイレクト"""
        client.cookies.set(SESSION_COOKIE, "tampered.token.value")
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"


class TestRequireUser:
    def test_raises_401_when_user_missing(self):
        request = SimpleNamespace(state=SimpleNamespace(user=None))
        with pytest.raises(HTTPException) as exc:
            require_user(request)
        assert exc.value.status_code == 401
        assert exc.value.detail == "Not authenticated"

    def test_raises_401_when_state_has_no_user_attr(self):
        request = SimpleNamespace(state=SimpleNamespace())
        with pytest.raises(HTTPException) as exc:
            require_user(request)
        assert exc.value.status_code == 401

    def test_returns_user_when_present(self):
        request = SimpleNamespace(state=SimpleNamespace(user="alice"))
        assert require_user(request) == "alice"


class TestLoginRoute:
    def test_get_login_renders_form(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert "password" in resp.text.lower()

    def test_post_login_with_correct_password_sets_cookie(self, client):
        resp = client.post(
            "/login",
            data={"password": "test-pass"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        assert "stock_session" in resp.cookies

    def test_post_login_sets_secure_cookie_when_enabled(self, tmp_path):
        cfg = AppConfig()
        cfg.database.path = str(tmp_path / "test.db")
        cfg.web = WebConfig(
            host="127.0.0.1",
            port=8501,
            password_hash=TEST_PASSWORD_HASH,
            session_secret="test-secret-please-do-not-use-in-prod",
            secure_cookies=True,
            allowed_hosts=["testserver", "localhost", "127.0.0.1"],
        )
        app = create_app(config=cfg)

        with TestClient(app) as client:
            resp = client.post(
                "/login",
                data={"password": "test-pass"},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert "Secure" in resp.headers["set-cookie"]

    def test_post_login_with_wrong_password_fails(self, client):
        resp = client.post(
            "/login",
            data={"password": "wrong"},
            follow_redirects=False,
        )
        assert resp.status_code == 401
        assert "stock_session" not in resp.cookies

    def test_login_rate_limit_returns_429_after_repeated_failures(self, client):
        for _ in range(5):
            resp = client.post(
                "/login",
                data={"password": "wrong"},
                follow_redirects=False,
            )
            assert resp.status_code == 401

        resp = client.post(
            "/login",
            data={"password": "wrong"},
            follow_redirects=False,
        )

        assert resp.status_code == 429

    def test_successful_login_does_not_clear_previous_failed_attempts(self, tmp_path):
        cfg = AppConfig()
        cfg.database.path = str(tmp_path / "test.db")
        cfg.web = WebConfig(
            host="127.0.0.1",
            port=8501,
            password_hash=TEST_PASSWORD_HASH,
            session_secret="test-secret-please-do-not-use-in-prod",
            login_rate_limit_attempts=2,
            login_rate_limit_window_seconds=60,
            allowed_hosts=["testserver", "localhost", "127.0.0.1"],
        )
        app = create_app(config=cfg)

        with TestClient(app) as client:
            wrong1 = client.post(
                "/login",
                data={"password": "wrong"},
                follow_redirects=False,
            )
            ok = client.post(
                "/login",
                data={"password": "test-pass"},
                follow_redirects=False,
            )
            wrong2 = client.post(
                "/login",
                data={"password": "wrong"},
                follow_redirects=False,
            )
            blocked = client.post(
                "/login",
                data={"password": "wrong"},
                follow_redirects=False,
            )

        assert wrong1.status_code == 401
        assert ok.status_code == 303
        assert wrong2.status_code == 401
        assert blocked.status_code == 429

    def test_logout_clears_cookie(self, auth_client):
        resp = auth_client.post("/logout", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"] == "/login"
        # クッキー削除フラグ
        assert auth_client.cookies.get("stock_session") in (None, "")

    def test_logout_via_get_is_not_allowed(self, auth_client):
        resp = auth_client.get("/logout", follow_redirects=False)
        assert resp.status_code == 405

    def test_cross_origin_state_change_is_rejected(self, auth_client):
        resp = auth_client.post(
            "/logout",
            headers={"origin": "https://evil.example"},
            follow_redirects=False,
        )

        assert resp.status_code == 403
