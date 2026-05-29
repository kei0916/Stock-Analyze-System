"""アプリケーション例外階層"""


class StockAnalyzeError(Exception):
    """全例外の基底クラス"""


class ConfigError(StockAnalyzeError):
    """設定ファイル・環境変数の問題"""


class IngestionError(StockAnalyzeError):
    """データ取得の基底例外"""


class RateLimitError(IngestionError):
    """レート制限超過（429応答）"""


class ApiConnectionError(IngestionError):
    """API接続失敗"""


class ApiResponseError(IngestionError):
    """予期しないAPI応答"""


class ContentFetchError(IngestionError):
    """Filing 本体 (HTML/PDF) 取得失敗の汎用エラー。"""


class ContentNotFoundError(ContentFetchError):
    """Filing 本体が source 側に存在しない (404 等)。"""


class ParsingError(StockAnalyzeError):
    """XBRL/HTMLパース失敗"""


class LlmError(StockAnalyzeError):
    """LLM関連の基底例外"""


class LlmConnectionError(LlmError):
    """Ollamaサーバー接続失敗"""


class LlmResponseError(LlmError):
    """LLM応答の構造化失敗（JSON不正等）"""


class DiagnosticLlmError(LlmError):
    """Base for LLM-tier failures that carry a diagnostic dict to the UI."""

    def __init__(self, message: str = "", *, diagnostic: dict | None = None):
        super().__init__(message)
        self.diagnostic = diagnostic


class IndexBuildError(DiagnosticLlmError):
    """PageIndex インデックス構築失敗 (ask_question 経路)."""


class ExtractionFailedError(DiagnosticLlmError):
    """定型分析の前提条件 (preflight LLM probe / 章抽出) が失敗したことを示す."""


class AnalysisFailedError(LlmError):
    """定型分析タイプの一部または全てが失敗したことを示す例外。"""

    def __init__(self, failed_types: list[dict]):
        self.failed_types = failed_types
        types = ", ".join(f["type"] for f in failed_types if f.get("type"))
        super().__init__(f"Analysis failed for: {types}")


class NotFoundError(StockAnalyzeError):
    """リソース未検出"""


class DuplicateError(StockAnalyzeError):
    """一意制約違反"""
