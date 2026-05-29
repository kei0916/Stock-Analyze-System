"""LlmClient単体テスト"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from stock_analyze_system.config import LlmConfig
from stock_analyze_system.services.llm_client import LlmClient


class TestResolveModel:
    def test_default_speed_model(self):
        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        assert client.resolve_model(quality=False) == "ollama/qwen3.5:27b-q8_0"

    def test_quality_model(self):
        config = LlmConfig(
            model="ollama/qwen3.5:27b-q8_0",
            model_quality="ollama/qwen3.5:27b-ud-q8_k_xl",
        )
        client = LlmClient(config)
        assert client.resolve_model(quality=True) == "ollama/qwen3.5:27b-ud-q8_k_xl"

    def test_quality_fallback_when_empty(self):
        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0", model_quality="")
        client = LlmClient(config)
        assert client.resolve_model(quality=True) == "ollama/qwen3.5:27b-q8_0"

    def test_explicit_model_override(self):
        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        assert client.resolve_model(model="ollama/custom:latest") == "ollama/custom:latest"

    def test_vllm_model_format(self):
        config = LlmConfig(
            model="openai/QuantTrio/Qwen3.5-27B-AWQ",
            model_quality="openai/QuantTrio/Qwen3.5-27B-AWQ",
        )
        client = LlmClient(config)
        assert client.resolve_model(quality=False) == "openai/QuantTrio/Qwen3.5-27B-AWQ"
        assert client.resolve_model(quality=True) == "openai/QuantTrio/Qwen3.5-27B-AWQ"


class TestCompletion:
    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_completion_calls_litellm(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "test response"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(
            model="ollama/qwen3.5:27b-q8_0",
            base_url="http://localhost:11434",
            temperature=0.1,
            max_tokens=4096,
            request_timeout=300,
        )
        client = LlmClient(config)
        result = await client.completion("What is 1+1?")

        assert result == "test response"
        mock_litellm.acompletion.assert_called_once()
        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["model"] == "ollama/qwen3.5:27b-q8_0"
        assert call_kwargs["timeout"] == 300

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_completion_with_quality(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "quality response"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(
            model="ollama/qwen3.5:27b-q8_0",
            model_quality="ollama/qwen3.5:27b-ud-q8_k_xl",
        )
        client = LlmClient(config)
        await client.completion("question", quality=True)

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["model"] == "ollama/qwen3.5:27b-ud-q8_k_xl"

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_completion_with_system_prompt(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "response"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        await client.completion("question", system="You are an analyst.")

        call_kwargs = mock_litellm.acompletion.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_completion_empty_response(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = None
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        result = await client.completion("question")

        assert result == ""

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_completion_custom_max_tokens_temperature(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "response"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(
            model="ollama/qwen3.5:27b-q8_0",
            max_tokens=4096,
            temperature=0.1,
        )
        client = LlmClient(config)
        await client.completion("question", max_tokens=2048, temperature=0.5)

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["max_tokens"] == 2048
        assert call_kwargs["temperature"] == 0.5

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_completion_api_base_passed(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "response"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(
            model="ollama/qwen3.5:27b-q8_0",
            base_url="http://custom:8000/v1",
        )
        client = LlmClient(config)
        await client.completion("question")

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["api_base"] == "http://custom:8000/v1"


    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_thinking_false_passes_extra_body(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = '{"answer": "yes"}'
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(model="openai/Qwen3.5-27B-Q4_K_M.gguf")
        client = LlmClient(config)
        await client.completion("test prompt", thinking=False)

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": False},
        }

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_thinking_true_passes_extra_body(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "deep analysis"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(
            model="openai/Qwen3.6-27B-Q4_K_M.gguf",
            enable_thinking=True,
        )
        client = LlmClient(config)
        await client.completion("test prompt", thinking=True)

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": True},
        }

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_thinking_true_is_suppressed_when_config_disables_it(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "plain answer"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(model="openai/Qwen3.6-27B-Q4_K_M.gguf")
        client = LlmClient(config)
        await client.completion("test prompt", thinking=True)

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": False},
        }

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_thinking_default_is_false(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "ok"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(model="openai/Qwen3.5-27B-Q4_K_M.gguf")
        client = LlmClient(config)
        await client.completion("test prompt")

        call_kwargs = mock_litellm.acompletion.call_args[1]
        assert call_kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False


class TestHealthCheck:
    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_health_check_ok(self, mock_litellm):
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "ok"
        mock_litellm.acompletion = AsyncMock(return_value=mock_resp)

        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        result = await client.health_check()
        assert result["status"] == "ok"

    @patch("stock_analyze_system.services.llm_client.litellm")
    async def test_health_check_fail(self, mock_litellm):
        mock_litellm.acompletion = AsyncMock(side_effect=Exception("connection refused"))

        config = LlmConfig(model="ollama/qwen3.5:27b-q8_0")
        client = LlmClient(config)
        result = await client.health_check()
        assert result["status"] == "error"
        assert "connection refused" in result["error"]


class TestBaseUrlProperty:
    def test_base_url_returns_config_value(self):
        config = LlmConfig(base_url="http://localhost:8000/v1")
        client = LlmClient(config)
        assert client.base_url == "http://localhost:8000/v1"

    def test_base_url_llamacpp_default(self):
        config = LlmConfig()
        client = LlmClient(config)
        assert client.base_url == "http://localhost:8080/v1"
