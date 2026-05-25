"""litellm非同期ラッパー — モデル選択・タイムアウト・ヘルスチェック"""
from __future__ import annotations

import logging

import litellm
from stock_analyze_system.config import LlmConfig

logger = logging.getLogger(__name__)


class LlmClient:
    """litellm経由の非同期LLMクライアント"""

    def __init__(self, config: LlmConfig):
        self._config = config

    @property
    def base_url(self) -> str:
        """LLMバックエンドのベースURLを返す"""
        return self._config.base_url

    @property
    def max_tokens(self) -> int:
        """設定されたmax_tokensを返す"""
        return self._config.max_tokens

    @property
    def request_timeout(self) -> int:
        """設定されたLLMリクエストタイムアウトを返す"""
        return self._config.request_timeout

    @property
    def thinking_enabled(self) -> bool:
        """バックエンドに thinking を要求できるかを返す"""
        return self._config.enable_thinking

    def resolve_model(
        self,
        *,
        quality: bool = False,
        model: str | None = None,
    ) -> str:
        """用途に応じたモデル名を解決する"""
        if model:
            return model
        if quality and self._config.model_quality:
            return self._config.model_quality
        return self._config.model

    async def completion(
        self,
        prompt: str,
        *,
        system: str | None = None,
        quality: bool = False,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        thinking: bool = False,
    ) -> str:
        """LLM補完を実行し応答テキストを返す"""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        effective_thinking = thinking and self._config.enable_thinking

        resp = await litellm.acompletion(
            model=self.resolve_model(quality=quality, model=model),
            messages=messages,
            api_base=self._config.base_url,
            timeout=self._config.request_timeout,
            max_tokens=max_tokens or self._config.max_tokens,
            temperature=temperature if temperature is not None else self._config.temperature,
            extra_body={"chat_template_kwargs": {"enable_thinking": effective_thinking}},
        )
        return resp.choices[0].message.content or ""

    async def health_check(self) -> dict:
        """LLM接続ヘルスチェック"""
        try:
            await self.completion("Reply OK.", max_tokens=10)
            return {
                "status": "ok",
                "model": self._config.model,
                "backend": self._config.backend,
                "base_url": self._config.base_url,
            }
        except Exception as e:
            logger.warning("LLM health check failed: %s", e)
            return {
                "status": "error",
                "error": str(e),
                "model": self._config.model,
                "backend": self._config.backend,
                "base_url": self._config.base_url,
            }
