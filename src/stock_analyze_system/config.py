"""設定管理: YAML + 環境変数 + optional .env fallback の階層的ロード"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml


def _resolve_project_path(relative: str) -> Path:
    """プロジェクトルート基準でパスを解決する"""
    project_root = Path(__file__).resolve().parent.parent.parent
    return project_root / relative


@dataclass
class DatabaseConfig:
    path: str = "data/stock_analyze.db"


@dataclass
class SecEdgarConfig:
    email: str = ""
    rate_limit_rps: int = 10


@dataclass
class EdinetConfig:
    base_url: str = "https://api.edinet-fsa.go.jp/api/v2"
    rate_limit_interval: int = 5
    api_key: str = field(default="", repr=False)


@dataclass
class FmpConfig:
    api_key: str = field(default="", repr=False)
    base_url: str = "https://financialmodelingprep.com/stable"
    rate_limit_rps: int = 5
    daily_limit: int = 250


@dataclass
class YahooFinanceConfig:
    rate_limit_rps: int = 2
    batch_size: int = 20


DEFAULT_GOOGLE_SHEETS_WORKSHEET = "test"


@dataclass
class GoogleSheetsConfig:
    enabled: bool = False
    spreadsheet_id: str = ""
    worksheet_name: str = DEFAULT_GOOGLE_SHEETS_WORKSHEET
    credentials_json_path: str = ""
    credentials_json_env: str = "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON"
    credentials_json: str = field(default="", repr=False)
    batch_size: int = 500
    poll_interval_seconds: int = 30
    max_poll_attempts: int = 10


@dataclass
class LlmConfig:
    backend: str = "llamacpp"
    base_url: str = "http://localhost:8080/v1"
    model: str = "openai/Qwen3.6-27B-Q4_K_M.gguf"
    model_quality: str = "openai/Qwen3.6-27B-Q4_K_M.gguf"
    enable_thinking: bool = False
    temperature: float = 0.1
    max_tokens: int = 16384
    request_timeout: int = 600


@dataclass
class FilingsConfig:
    base_path: str = "data/filings"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "data/logs/stock_analyze.log"


@dataclass
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8501
    password: str = field(default="", repr=False)
    session_secret: str = field(default="", repr=False)
    secure_cookies: bool = False
    trust_proxy_headers: bool = False
    trusted_proxy_hosts: list[str] = field(default_factory=list)
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60
    heavy_rate_limit_attempts: int = 20
    heavy_rate_limit_window_seconds: int = 60


@dataclass
class PageIndexConfig:
    enabled: bool = False
    model: str = ""
    backend: str = ""
    lm_studio_base_url: str = "http://localhost:1234/v1"
    api_key: str = field(default="", repr=False)
    toc_check_pages: int = 20
    max_pages_per_node: int = 10
    max_tokens_per_node: int = 20000
    add_node_summary: bool = True
    add_node_text: bool = False
    cache_indices: bool = True


@dataclass
class AppConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    sec_edgar: SecEdgarConfig = field(default_factory=SecEdgarConfig)
    edinet: EdinetConfig = field(default_factory=EdinetConfig)
    fmp: FmpConfig = field(default_factory=FmpConfig)
    yahoo_finance: YahooFinanceConfig = field(default_factory=YahooFinanceConfig)
    google_sheets: GoogleSheetsConfig = field(default_factory=GoogleSheetsConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    filings: FilingsConfig = field(default_factory=FilingsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    web: WebConfig = field(default_factory=WebConfig)
    pageindex: PageIndexConfig = field(default_factory=PageIndexConfig)


def _merge_dict_to_dataclass(dc_class, data: dict | None):
    """辞書からdataclassインスタンスを生成（未知キーは無視）"""
    if not data:
        return dc_class()
    valid_fields = {f.name for f in fields(dc_class)}
    filtered = {k: v for k, v in data.items() if k in valid_fields}
    return dc_class(**filtered)


def _load_dotenv(env_path: Path | None = None) -> None:
    """Load repo-local .env for backward compatibility without overriding real env vars."""
    path = env_path or _resolve_project_path(".env")
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _should_load_dotenv() -> bool:
    value = os.environ.get("STOCK_ANALYZE_LOAD_DOTENV", "1")
    return value.lower() not in {"0", "false", "no", "off"}


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """設定ファイルを読み込み、環境変数でシークレットを上書きする"""
    if _should_load_dotenv():
        _load_dotenv()

    if config_path is None:
        config_path = _resolve_project_path("config/settings.yaml")
    config_path = Path(config_path)

    raw: dict = {}
    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}

    config = AppConfig(
        database=_merge_dict_to_dataclass(DatabaseConfig, raw.get("database")),
        sec_edgar=_merge_dict_to_dataclass(SecEdgarConfig, raw.get("sec_edgar")),
        edinet=_merge_dict_to_dataclass(EdinetConfig, raw.get("edinet")),
        fmp=_merge_dict_to_dataclass(FmpConfig, raw.get("fmp")),
        yahoo_finance=_merge_dict_to_dataclass(
            YahooFinanceConfig, raw.get("yahoo_finance"),
        ),
        google_sheets=_merge_dict_to_dataclass(
            GoogleSheetsConfig, raw.get("google_sheets"),
        ),
        llm=_merge_dict_to_dataclass(LlmConfig, raw.get("llm")),
        filings=_merge_dict_to_dataclass(FilingsConfig, raw.get("filings")),
        logging=_merge_dict_to_dataclass(LoggingConfig, raw.get("logging")),
        web=_merge_dict_to_dataclass(WebConfig, raw.get("web")),
        pageindex=_merge_dict_to_dataclass(PageIndexConfig, raw.get("pageindex")),
    )

    # 環境変数でシークレットを上書き
    if val := os.environ.get("SEC_EDGAR_EMAIL"):
        config.sec_edgar.email = val
    if val := os.environ.get("EDINET_API_KEY"):
        config.edinet.api_key = val
    if val := os.environ.get("FMP_API_KEY"):
        config.fmp.api_key = val
    if val := os.environ.get("WEB_PASSWORD"):
        config.web.password = val
    if val := os.environ.get("WEB_SESSION_SECRET"):
        config.web.session_secret = val
    if val := os.environ.get("PAGEINDEX_API_KEY"):
        config.pageindex.api_key = val
    if val := os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID"):
        config.google_sheets.spreadsheet_id = val
    if val := os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON_PATH"):
        config.google_sheets.credentials_json_path = val
    if val := os.environ.get(config.google_sheets.credentials_json_env):
        config.google_sheets.credentials_json = val

    return config
