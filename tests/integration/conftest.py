"""結合テスト共通フィクスチャ。

AppConfig のテスト用インスタンス生成ヘルパーを提供する。
本ファイルは Phase A-3 (container assembly) と Phase C (service assembly) で共有する。
"""
from __future__ import annotations

from stock_analyze_system.config import (
    AppConfig,
    DatabaseConfig,
    EdinetConfig,
    FilingsConfig,
    FmpConfig,
    LlmConfig,
    LoggingConfig,
    PageIndexConfig,
    SecEdgarConfig,
    WebConfig,
    YahooFinanceConfig,
)


def build_test_config(pageindex_enabled: bool = False) -> AppConfig:
    """テスト用の最小 AppConfig を返す。

    - 外部 API キーは空文字 or ダミー (実通信が走らない初期化のみ確認)
    - PageIndex は引数で有効/無効切替
    - LLM は ollama デフォルト (初期化時通信なし)
    """
    return AppConfig(
        database=DatabaseConfig(path=":memory:"),
        sec_edgar=SecEdgarConfig(email="test@example.com"),
        edinet=EdinetConfig(api_key="test"),
        fmp=FmpConfig(api_key="test"),
        yahoo_finance=YahooFinanceConfig(),
        llm=LlmConfig(),
        filings=FilingsConfig(),
        logging=LoggingConfig(),
        web=WebConfig(session_secret="test-secret"),
        pageindex=PageIndexConfig(enabled=pageindex_enabled),
    )
