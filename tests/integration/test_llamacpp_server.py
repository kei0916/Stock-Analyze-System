"""llama.cpp OpenAI互換サーバー 起動・推論テスト

前提:
  - STOCK_ANALYZE_RUN_LLAMACPP_TESTS=1 が設定されている
  - llama.cpp サーバーが http://localhost:8080/v1 で稼働中
実行: STOCK_ANALYZE_RUN_LLAMACPP_TESTS=1 python3 -m pytest tests/integration/test_llamacpp_server.py -v -s
"""
from __future__ import annotations

import os

import pytest
import httpx

BASE_URL = "http://localhost:8080"
API_URL = f"{BASE_URL}/v1"
TIMEOUT = 120.0
OPT_IN_ENV = "STOCK_ANALYZE_RUN_LLAMACPP_TESTS"


def _llamacpp_skip_reason() -> str | None:
    if os.environ.get(OPT_IN_ENV) != "1":
        return f"set {OPT_IN_ENV}=1 to run external llama.cpp server tests"

    try:
        resp = httpx.get(f"{API_URL}/models", timeout=2.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"llama.cpp OpenAI-compatible server is not reachable at {API_URL}: {exc}"

    return None


_skip_reason = _llamacpp_skip_reason()
pytestmark = [
    pytest.mark.external_llamacpp,
    pytest.mark.skipif(_skip_reason is not None, reason=_skip_reason),
]


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        yield client


class TestLlamaCppHealth:
    """サーバー起動・ヘルスチェック"""

    def test_models_list(self, client):
        """GET /v1/models が 200 を返す（ヘルスチェック代替）"""
        resp = client.get("/v1/models")
        assert resp.status_code == 200

    def test_models_endpoint(self, client):
        """GET /v1/models がモデル一覧を返す"""
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert len(data["data"]) >= 1


class TestLlamaCppInference:
    """基本推論テスト"""

    def test_simple_completion(self, client):
        """短い補完が content 付きで返る (thinking 無効化: 本番 llm_client.py と同条件)"""
        resp = client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "Reply with only: OK"}],
            "max_tokens": 64,
            "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False},
        })
        assert resp.status_code == 200
        data = resp.json()
        choice = data["choices"][0]
        # content が None でないこと（推論モデルの max_tokens 消費問題の検出）
        assert choice["message"]["content"] is not None
        assert len(choice["message"]["content"].strip()) > 0

    def test_json_mode(self, client):
        """response_format=json_object でJSON出力が返る"""
        resp = client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": 'Return JSON: {"answer": "yes"}'}],
            "max_tokens": 256,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
        })
        assert resp.status_code == 200
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        assert content is not None
        # JSONとしてパース可能であること
        import json
        parsed = json.loads(content)
        assert isinstance(parsed, dict)

    def test_reasoning_token_budget(self, client):
        """max_tokens=4096 で推論トークンが出力を食い潰さないこと"""
        resp = client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": (
                "Task: Check whether the section titled \"Risk Factors\" "
                "appears on the given page.\n\n"
                "Page text: ITEM 1A. RISK FACTORS The following discussion...\n\n"
                'Return JSON: {"answer": "yes" or "no"}'
            )}],
            "max_tokens": 4096,
            "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False},
        })
        assert resp.status_code == 200
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        assert content is not None, "content is None — reasoning consumed all tokens"
        assert len(content.strip()) > 0
        # finish_reason が length でないこと（トークン枯渇していない）
        assert data["choices"][0]["finish_reason"] != "length"
