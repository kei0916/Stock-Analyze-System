# Phase 1: 基盤層 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stock Analyze System の基盤層（設定管理、DBモデル、例外階層、ロギング、共有ユーティリティ、Repository基盤、テスト基盤）を構築する

**Architecture:** 全面async/await。SQLAlchemy 2.0 AsyncSession + aiosqlite。BaseRepository でジェネリックCRUD。pytest-asyncio でasyncテスト。

**Tech Stack:** Python 3.10+, SQLAlchemy 2.0 (async), aiosqlite, PyYAML, pytest, pytest-asyncio, ruff

**Spec:** `docs/superpowers/specs/2026-03-21-stock-analyze-system-design.md` セクション2-4, 6, 11

**Reference project:** `<legacy-stock-analyzer-repo>` — 参考にする場合は潜在バグ調査必須

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `pyproject.toml` | パッケージ定義、依存関係 |
| Create | `config/settings.yaml.example` | 設定テンプレート |
| Create | `src/stock_analyze_system/__init__.py` | パッケージ初期化 |
| Create | `src/stock_analyze_system/config.py` | 設定管理（YAML + .env + 環境変数） |
| Create | `src/stock_analyze_system/exceptions.py` | 例外階層 |
| Create | `src/stock_analyze_system/logging_config.py` | ロギング設定 |
| Create | `src/stock_analyze_system/models/__init__.py` | モデルパッケージ |
| Create | `src/stock_analyze_system/models/base.py` | AsyncEngine, Base, get_session |
| Create | `src/stock_analyze_system/models/company.py` | Company モデル |
| Create | `src/stock_analyze_system/models/financial_data.py` | FinancialData モデル |
| Create | `src/stock_analyze_system/models/valuation.py` | Valuation モデル |
| Create | `src/stock_analyze_system/models/filing.py` | Filing モデル |
| Create | `src/stock_analyze_system/models/company_analysis.py` | CompanyAnalysis モデル |
| Create | `src/stock_analyze_system/models/watchlist.py` | Watchlist, WatchlistItem モデル |
| Create | `src/stock_analyze_system/models/analysis_target.py` | AnalysisTarget モデル |
| Create | `src/stock_analyze_system/models/screening.py` | ScreeningCache モデル |
| Create | `src/stock_analyze_system/models/competitor_group.py` | CompetitorGroup, Member モデル |
| Create | `src/stock_analyze_system/models/document_index.py` | DocumentIndex モデル (NEW) |
| Create | `src/stock_analyze_system/repositories/__init__.py` | リポジトリパッケージ |
| Create | `src/stock_analyze_system/repositories/base.py` | BaseRepository (ジェネリックCRUD) |
| Create | `src/stock_analyze_system/shared/__init__.py` | 共有パッケージ |
| Create | `src/stock_analyze_system/shared/formatters.py` | 数値フォーマッタ |
| Create | `tests/__init__.py` | テストパッケージ |
| Create | `tests/conftest.py` | AsyncSession fixture, mock_config |
| Create | `tests/unit/__init__.py` | ユニットテストパッケージ |
| Create | `tests/unit/test_config.py` | 設定ロードのテスト |
| Create | `tests/unit/test_exceptions.py` | 例外階層のテスト |
| Create | `tests/unit/test_models.py` | モデルCRUDのテスト |
| Create | `tests/unit/test_shared_formatters.py` | フォーマッタのテスト |
| Create | `tests/unit/test_logging_config.py` | ロギング設定のテスト |
| Create | `tests/unit/repositories/__init__.py` | リポジトリテストパッケージ |
| Create | `tests/unit/repositories/test_base_repo.py` | BaseRepository のテスト |

---

## 参考プロジェクト潜在バグ調査結果

Phase 1 開始時の `<legacy-stock-analyzer-repo>` 調査で発見した問題:

| # | ファイル | 問題 | 対策 |
|---|---------|------|------|
| 既知#12 | `config.py` L48 vs `settings.yaml` | LLMモデル名デフォルト不一致 (`gptoss20b:q8` vs `clore/gpt-oss-20b-Q8_0:latest`) | デフォルト値を統一 |
| 既知#20 | `config.py` L143-157 | `SEC_EDGAR_EMAIL` 環境変数未対応 | 環境変数マッピング追加 |
| 新発見 | `config.py` L105 | `.env` パスがCWD相対。パッケージルート外から実行すると読めない | プロジェクトルート基準に |
| 新発見 | `config.py` L120 | `config_path` もCWD相対 | 同上 |
| 新発見 | `models/base.py` L17-18 | グローバル変数 `_engine`, `_SessionLocal` で状態管理。テスト時に汚染リスク | AsyncEngine を引数ベースに |
| 新発見 | `logging_config.py` L16 | `basicConfig` を2回呼ぶと2重ハンドラ | ルートロガー直接設定に変更 |

---

### Task 1: プロジェクト初期化（pyproject.toml + パッケージ構造）

**Files:**
- Create: `pyproject.toml`
- Create: `src/stock_analyze_system/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: pyproject.toml を作成**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "stock-analyze-system"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "sqlalchemy>=2.0",
    "aiosqlite>=0.20",
    "httpx>=0.27",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "itsdangerous>=2.1",
    "yfinance>=0.2",
    "pyyaml>=6.0",
    "tabulate>=0.9",
    "litellm>=1.82",
    "pymupdf>=1.26",
    "weasyprint>=62",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-httpx>=0.30",
    "pytest-cov",
    "ruff",
]

[project.scripts]
stock-analyze = "stock_analyze_system.__main__:main_entry"

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: パッケージ __init__.py を作成**

```python
# src/stock_analyze_system/__init__.py
"""Stock Analyze System - 米国株・日本株 財務分析プラットフォーム"""
```

- [ ] **Step 3: .gitignore を更新**

```gitignore
data/
.env
config/settings.yaml
__pycache__/
*.egg-info/
.pytest_cache/
.coverage
.venv/
*.pyc
```

- [ ] **Step 4: 開発環境インストール**

Run: `pip install -e ".[dev]"`
Expected: 正常終了、`stock-analyze` コマンドがPATHに登録される（エントリポイント未作成のためエラーは可）

- [ ] **Step 5: コミット**

```bash
git add pyproject.toml src/stock_analyze_system/__init__.py .gitignore
git commit -m "feat: initialize project structure with pyproject.toml"
```

---

### Task 2: 例外階層

**Files:**
- Create: `src/stock_analyze_system/exceptions.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/test_exceptions.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/test_exceptions.py
"""例外階層のテスト"""
from stock_analyze_system.exceptions import (
    StockAnalyzeError,
    ConfigError,
    IngestionError,
    RateLimitError,
    ApiConnectionError,
    ApiResponseError,
    ParsingError,
    LlmError,
    LlmConnectionError,
    LlmResponseError,
    IndexBuildError,
    NotFoundError,
    DuplicateError,
)


def test_all_exceptions_inherit_from_base():
    for exc_class in [
        ConfigError, IngestionError, ParsingError,
        LlmError, NotFoundError, DuplicateError,
    ]:
        assert issubclass(exc_class, StockAnalyzeError)


def test_ingestion_subclasses():
    for exc_class in [RateLimitError, ApiConnectionError, ApiResponseError]:
        assert issubclass(exc_class, IngestionError)
        assert issubclass(exc_class, StockAnalyzeError)


def test_llm_subclasses():
    for exc_class in [LlmConnectionError, LlmResponseError, IndexBuildError]:
        assert issubclass(exc_class, LlmError)
        assert issubclass(exc_class, StockAnalyzeError)


def test_exception_message():
    err = NotFoundError("Company US_AAPL not found")
    assert str(err) == "Company US_AAPL not found"
    assert isinstance(err, StockAnalyzeError)
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/unit/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_analyze_system.exceptions'`

- [ ] **Step 3: 例外クラスを実装**

```python
# src/stock_analyze_system/exceptions.py
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


class ParsingError(StockAnalyzeError):
    """XBRL/HTMLパース失敗"""


class LlmError(StockAnalyzeError):
    """LLM関連の基底例外"""


class LlmConnectionError(LlmError):
    """Ollamaサーバー接続失敗"""


class LlmResponseError(LlmError):
    """LLM応答の構造化失敗（JSON不正等）"""


class IndexBuildError(LlmError):
    """PageIndexインデックス構築失敗"""


class NotFoundError(StockAnalyzeError):
    """リソース未検出"""


class DuplicateError(StockAnalyzeError):
    """一意制約違反"""
```

- [ ] **Step 4: テスト通過を確認**

Run: `python -m pytest tests/unit/test_exceptions.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/exceptions.py tests/
git commit -m "feat: add exception hierarchy"
```

---

### Task 3: 共有フォーマッタ

**Files:**
- Create: `src/stock_analyze_system/shared/__init__.py`
- Create: `src/stock_analyze_system/shared/formatters.py`
- Create: `tests/unit/test_shared_formatters.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/test_shared_formatters.py
"""共有フォーマッタのテスト"""
import pytest
from stock_analyze_system.shared.formatters import (
    fmt_number, fmt_pct, fmt_large, fmt_ratio,
)


class TestFmtNumber:
    @pytest.mark.parametrize("val, precision, expected", [
        (1.234, 1, "1.2"),
        (1.256, 2, "1.26"),
        (0.0, 1, "0.0"),
        (-5.5, 1, "-5.5"),
        (None, 1, "N/A"),
    ])
    def test_fmt_number(self, val, precision, expected):
        assert fmt_number(val, precision) == expected


class TestFmtPct:
    @pytest.mark.parametrize("val, precision, expected", [
        (0.15, 1, "15.0%"),
        (0.0, 1, "0.0%"),
        (-0.05, 1, "-5.0%"),
        (1.0, 0, "100%"),
        (None, 1, "N/A"),
    ])
    def test_fmt_pct(self, val, precision, expected):
        assert fmt_pct(val, precision) == expected


class TestFmtLarge:
    @pytest.mark.parametrize("val, expected", [
        (1.5e12, "1.5T"),
        (2.3e9, "2.3B"),
        (45.6e6, "45.6M"),
        (999999, "999,999"),
        (0, "0"),
        (-2.5e9, "-2.5B"),
        (None, "N/A"),
    ])
    def test_fmt_large(self, val, expected):
        assert fmt_large(val) == expected


class TestFmtRatio:
    @pytest.mark.parametrize("val, precision, expected", [
        (1.5, 2, "1.50"),
        (0.0, 2, "0.00"),
        (-3.14, 1, "-3.1"),
        (None, 2, "N/A"),
    ])
    def test_fmt_ratio(self, val, precision, expected):
        assert fmt_ratio(val, precision) == expected
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/unit/test_shared_formatters.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: フォーマッタを実装**

```python
# src/stock_analyze_system/shared/__init__.py
```

```python
# src/stock_analyze_system/shared/formatters.py
"""共有数値フォーマットユーティリティ（CLI, Web 共通）"""
from __future__ import annotations


def fmt_number(val: float | None, precision: int = 1) -> str:
    if val is None:
        return "N/A"
    return f"{val:.{precision}f}"


def fmt_pct(val: float | None, precision: int = 1) -> str:
    if val is None:
        return "N/A"
    return f"{val * 100:.{precision}f}%"


def fmt_large(val: float | None, precision: int = 1) -> str:
    if val is None:
        return "N/A"
    if abs(val) >= 1e12:
        return f"{val / 1e12:.{precision}f}T"
    if abs(val) >= 1e9:
        return f"{val / 1e9:.{precision}f}B"
    if abs(val) >= 1e6:
        return f"{val / 1e6:.{precision}f}M"
    return f"{val:,.0f}"


def fmt_ratio(val: float | None, precision: int = 2) -> str:
    if val is None:
        return "N/A"
    return f"{val:.{precision}f}"
```

- [ ] **Step 4: テスト通過を確認**

Run: `python -m pytest tests/unit/test_shared_formatters.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/shared/ tests/unit/test_shared_formatters.py
git commit -m "feat: add shared number formatters"
```

---

### Task 4: 設定管理

**Files:**
- Create: `src/stock_analyze_system/config.py`
- Create: `config/settings.yaml.example`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/test_config.py
"""設定管理のテスト"""
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from stock_analyze_system.config import (
    AppConfig,
    DatabaseConfig,
    PageIndexConfig,
    load_config,
    _load_dotenv,
    _merge_dict_to_dataclass,
    _resolve_project_path,
)


class TestMergeDictToDataclass:
    def test_empty_dict(self):
        result = _merge_dict_to_dataclass(DatabaseConfig, {})
        assert result.path == "data/stock_analyze.db"

    def test_none_input(self):
        result = _merge_dict_to_dataclass(DatabaseConfig, None)
        assert result.path == "data/stock_analyze.db"

    def test_valid_fields(self):
        result = _merge_dict_to_dataclass(DatabaseConfig, {"path": "/tmp/test.db"})
        assert result.path == "/tmp/test.db"

    def test_unknown_fields_ignored(self):
        result = _merge_dict_to_dataclass(DatabaseConfig, {"path": "/tmp/t.db", "unknown": 42})
        assert result.path == "/tmp/t.db"


class TestResolveProjectPath:
    def test_returns_absolute_path(self):
        result = _resolve_project_path("config/settings.yaml")
        assert result.is_absolute()
        assert result.name == "settings.yaml"


class TestLoadDotenv:
    def test_loads_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('TEST_VAR_XYZ="hello"\n')
        os.environ.pop("TEST_VAR_XYZ", None)
        _load_dotenv(env_file)
        assert os.environ.get("TEST_VAR_XYZ") == "hello"
        os.environ.pop("TEST_VAR_XYZ", None)

    def test_does_not_overwrite_existing(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR_XYZ=new\n")
        os.environ["TEST_VAR_XYZ"] = "old"
        _load_dotenv(env_file)
        assert os.environ["TEST_VAR_XYZ"] == "old"
        os.environ.pop("TEST_VAR_XYZ", None)

    def test_skips_comments_and_blanks(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nKEY=value\n")
        os.environ.pop("KEY", None)
        _load_dotenv(env_file)
        assert os.environ.get("KEY") == "value"
        os.environ.pop("KEY", None)

    def test_missing_file_no_error(self, tmp_path):
        _load_dotenv(tmp_path / "nonexistent")  # should not raise


class TestLoadConfig:
    def test_default_config(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        config = load_config(yaml_path)
        assert isinstance(config, AppConfig)
        assert config.database.path == "data/stock_analyze.db"

    def test_yaml_override(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("database:\n  path: /custom/path.db\n")
        config = load_config(yaml_path)
        assert config.database.path == "/custom/path.db"

    def test_env_var_override(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        with patch.dict(os.environ, {"SEC_EDGAR_EMAIL": "test@example.com"}):
            config = load_config(yaml_path)
            assert config.sec_edgar.email == "test@example.com"

    def test_env_var_edinet(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        with patch.dict(os.environ, {"EDINET_API_KEY": "mykey"}):
            config = load_config(yaml_path)
            assert config.edinet.api_key == "mykey"

    def test_env_var_fmp(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        with patch.dict(os.environ, {"FMP_API_KEY": "fmpkey"}):
            config = load_config(yaml_path)
            assert config.fmp.api_key == "fmpkey"

    def test_pageindex_config_exists(self, tmp_path):
        yaml_path = tmp_path / "settings.yaml"
        yaml_path.write_text("")
        config = load_config(yaml_path)
        assert isinstance(config.pageindex, PageIndexConfig)
        assert config.pageindex.enabled is False

    def test_missing_yaml_file(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert isinstance(config, AppConfig)
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/unit/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: config.py を実装**

```python
# src/stock_analyze_system/config.py
"""設定管理: YAML + 環境変数 + .env の階層的ロード"""
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
    rate_limit_rps: int = 5


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


@dataclass
class LlmConfig:
    backend: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "ollama/gptoss20b:q8"
    temperature: float = 0.1
    max_tokens: int = 32768


@dataclass
class FilingsConfig:
    base_path: str = "data/filings"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "data/logs/stock_analyze.log"


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8501
    password: str = field(default="", repr=False)
    session_secret: str = field(default="", repr=False)


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
    """軽量な.envファイル読み込み（外部ライブラリ不要）"""
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


def load_config(config_path: str | Path | None = None) -> AppConfig:
    """設定ファイルを読み込み、環境変数でシークレットを上書きする"""
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

    return config
```

- [ ] **Step 4: settings.yaml.example を作成**

```yaml
# config/settings.yaml.example
database:
  path: data/stock_analyze.db
sec_edgar:
  email: "user@example.com"
  rate_limit_rps: 5
edinet:
  base_url: "https://api.edinet-fsa.go.jp/api/v2"
  rate_limit_interval: 5
fmp:
  base_url: "https://financialmodelingprep.com/stable"
  rate_limit_rps: 5
  daily_limit: 250
yahoo_finance:
  rate_limit_rps: 2
  batch_size: 20
llm:
  backend: ollama
  base_url: "http://localhost:11434"
  model: "ollama/gptoss20b:q8"
  temperature: 0.1
  max_tokens: 32768
filings:
  base_path: "data/filings"
logging:
  level: INFO
  file: "data/logs/stock_analyze.log"
web:
  host: "0.0.0.0"
  port: 8501
pageindex:
  enabled: false
  toc_check_pages: 20
  max_pages_per_node: 10
  max_tokens_per_node: 20000
  add_node_summary: true
  cache_indices: true
```

- [ ] **Step 5: テスト通過を確認**

Run: `python -m pytest tests/unit/test_config.py -v`
Expected: 全テスト PASS

- [ ] **Step 6: コミット**

```bash
git add src/stock_analyze_system/config.py config/settings.yaml.example tests/unit/test_config.py
git commit -m "feat: add config management with YAML + env var loading"
```

---

### Task 5: ロギング設定

**Files:**
- Create: `src/stock_analyze_system/logging_config.py`
- Create: `tests/unit/test_logging_config.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/test_logging_config.py
"""ロギング設定のテスト"""
import logging

import pytest

from stock_analyze_system.config import LoggingConfig
from stock_analyze_system.logging_config import setup_logging


@pytest.fixture(autouse=True)
def _clean_root_logger():
    """各テスト後にルートロガーのハンドラをクリアする"""
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()


def test_setup_logging_creates_handlers(tmp_path):
    config = LoggingConfig(level="DEBUG", file=str(tmp_path / "test.log"))
    setup_logging(config)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 2  # file + console


def test_setup_logging_no_duplicate_handlers(tmp_path):
    """2回呼んでもハンドラが重複しないこと（参考プロジェクトバグ修正確認）"""
    config = LoggingConfig(level="INFO", file=str(tmp_path / "test.log"))
    setup_logging(config)
    setup_logging(config)
    root = logging.getLogger()
    assert len(root.handlers) == 2  # 重複なし


def test_setup_logging_suppresses_noisy_loggers(tmp_path):
    config = LoggingConfig(level="DEBUG", file=str(tmp_path / "test.log"))
    setup_logging(config)
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING


def test_setup_logging_creates_log_directory(tmp_path):
    log_path = tmp_path / "subdir" / "nested" / "test.log"
    config = LoggingConfig(level="INFO", file=str(log_path))
    setup_logging(config)
    assert log_path.parent.exists()
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/unit/test_logging_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stock_analyze_system.logging_config'`

- [ ] **Step 3: logging_config.py を実装**

```python
# src/stock_analyze_system/logging_config.py
"""ログ設定"""
from __future__ import annotations

import logging
from pathlib import Path

from stock_analyze_system.config import LoggingConfig


def setup_logging(config: LoggingConfig) -> None:
    """アプリケーション全体のログ設定を初期化する"""
    log_path = Path(config.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level.upper(), logging.INFO))

    if not root_logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # モジュール別ログレベル
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
```

- [ ] **Step 4: テスト通過を確認**

Run: `python -m pytest tests/unit/test_logging_config.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/logging_config.py tests/unit/test_logging_config.py
git commit -m "feat: add logging configuration with duplicate handler prevention"
```

---

### Task 6: データベース基盤 (AsyncEngine + Base)

**Files:**
- Create: `src/stock_analyze_system/models/__init__.py`
- Create: `src/stock_analyze_system/models/base.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: テスト基盤 (conftest.py) を書く**

```python
# tests/conftest.py
"""テスト共通フィクスチャ"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from stock_analyze_system.config import AppConfig
from stock_analyze_system.models.base import Base, get_session


@pytest.fixture
async def async_engine():
    """インメモリ AsyncSQLite エンジン"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(async_engine):
    """テスト用 AsyncSession（テストごとにインメモリDB再作成）"""
    async with get_session(async_engine) as sess:
        yield sess


@pytest.fixture
def config() -> AppConfig:
    """テスト用設定"""
    return AppConfig()
```

- [ ] **Step 2: models/base.py を実装**

```python
# src/stock_analyze_system/models/__init__.py
```

```python
# src/stock_analyze_system/models/base.py
"""データベースエンジン・セッション管理 (async)"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    pass


async def create_db_engine(db_path: str) -> AsyncEngine:
    """AsyncSQLiteエンジンを作成し、WALモード・外部キーを有効化する"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return engine


@asynccontextmanager
async def get_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """AsyncSessionのコンテキストマネージャ"""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
```

- [ ] **Step 3: DB基盤テストを書いて実行**

```python
# tests/unit/test_models.py (初期部分)
"""DBモデル基盤のテスト"""
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from stock_analyze_system.models.base import Base, get_session


async def test_get_session_commit(async_engine):
    """セッションが正常にコミットされること"""
    async with get_session(async_engine) as session:
        assert session is not None


async def test_get_session_rollback_on_error(async_engine):
    """例外時にロールバックされること"""
    with pytest.raises(ValueError):
        async with get_session(async_engine) as session:
            raise ValueError("test error")
```

Run: `python -m pytest tests/unit/test_models.py -v`
Expected: 全テスト PASS

- [ ] **Step 4: コミット**

```bash
git add src/stock_analyze_system/models/ tests/conftest.py tests/unit/test_models.py
git commit -m "feat: add async database engine and session management"
```

---

### Task 7: ORM モデル（全テーブル）

**Files:**
- Create: `src/stock_analyze_system/models/company.py`
- Create: `src/stock_analyze_system/models/financial_data.py`
- Create: `src/stock_analyze_system/models/valuation.py`
- Create: `src/stock_analyze_system/models/filing.py`
- Create: `src/stock_analyze_system/models/company_analysis.py`
- Create: `src/stock_analyze_system/models/watchlist.py`
- Create: `src/stock_analyze_system/models/analysis_target.py`
- Create: `src/stock_analyze_system/models/screening.py`
- Create: `src/stock_analyze_system/models/competitor_group.py`
- Create: `src/stock_analyze_system/models/document_index.py`
- Modify: `tests/unit/test_models.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: テストを書く — 全モデルのCRUD基本テスト**

`tests/unit/test_models.py` に追記:

```python
from stock_analyze_system.models.company import Company
from stock_analyze_system.models.financial_data import FinancialData
from stock_analyze_system.models.valuation import Valuation
from stock_analyze_system.models.filing import Filing
from stock_analyze_system.models.company_analysis import CompanyAnalysis
from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem
from stock_analyze_system.models.analysis_target import AnalysisTarget
from stock_analyze_system.models.screening import ScreeningCache
from stock_analyze_system.models.competitor_group import CompetitorGroup, CompetitorGroupMember
from stock_analyze_system.models.document_index import DocumentIndex
from datetime import date


async def test_company_crud(session):
    company = Company(
        id="US_AAPL", ticker="AAPL", name="Apple Inc.",
        market="NASDAQ", accounting_standard="US-GAAP", cik="0000320193",
    )
    session.add(company)
    await session.flush()
    result = await session.get(Company, "US_AAPL")
    assert result is not None
    assert result.ticker == "AAPL"


async def test_jp_company(session):
    company = Company(
        id="JP_7203", security_code="7203", name="Toyota Motor Corporation",
        name_ja="トヨタ自動車株式会社", market="TSE_PRIME",
        accounting_standard="IFRS", edinet_code="E02144",
    )
    session.add(company)
    await session.flush()
    result = await session.get(Company, "JP_7203")
    assert result.name_ja == "トヨタ自動車株式会社"


async def test_financial_data_crud(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    fd = FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual",
        fiscal_year_end=date(2024, 9, 28), revenue=394328000000,
    )
    session.add(fd)
    await session.flush()
    assert fd.id is not None
    assert fd.revenue == 394328000000


async def test_financial_data_unique_constraint(session):
    from sqlalchemy.exc import IntegrityError
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    fd1 = FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual", fiscal_year_end=date(2024, 9, 28),
    )
    fd2 = FinancialData(
        company_id="US_AAPL", accounting_standard="US-GAAP",
        currency="USD", period_type="annual", fiscal_year_end=date(2024, 9, 28),
    )
    session.add(fd1)
    await session.flush()
    session.add(fd2)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_valuation_crud(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    v = Valuation(
        company_id="US_AAPL", currency="USD", date=date(2024, 1, 1),
        stock_price=185.0, per=28.5,
    )
    session.add(v)
    await session.flush()
    assert v.id is not None


async def test_filing_crud(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    f = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
        accession_no="0000320193-24-000123",
    )
    session.add(f)
    await session.flush()
    assert f.id is not None


async def test_document_index_crud(session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    f = Filing(
        company_id="US_AAPL", source="SEC", filing_type="10-K",
        period_type="annual", fiscal_year=2024,
    )
    session.add(f)
    await session.flush()
    di = DocumentIndex(
        filing_id=f.id, company_id="US_AAPL",
        index_json='{"nodes": []}', model_name="ollama/gptoss20b:q8",
        page_count=142, node_count=47,
    )
    session.add(di)
    await session.flush()
    assert di.id is not None


async def test_watchlist_cascade(session):
    wl = Watchlist(name="My Watchlist")
    session.add(wl)
    await session.flush()
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    item = WatchlistItem(watchlist_id=wl.id, company_id="US_AAPL")
    session.add(item)
    await session.flush()
    assert item.id is not None
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/unit/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 全モデルファイルを実装**

各モデルファイルの完全な定義を以下に示す。importパスは `stock_analyze_system.models.base` に変更済み。`document_index.py` は新規追加。

```python
# src/stock_analyze_system/models/company.py
"""企業マスタモデル"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # US_AAPL, JP_7203
    ticker: Mapped[str | None] = mapped_column(String(10), index=True)
    security_code: Mapped[str | None] = mapped_column(String(10), index=True)
    name: Mapped[str] = mapped_column(String(200))
    name_ja: Mapped[str | None] = mapped_column(String(200))
    market: Mapped[str] = mapped_column(String(20))  # NYSE, NASDAQ, TSE_PRIME, etc.
    sector: Mapped[str | None] = mapped_column(String(100))
    accounting_standard: Mapped[str] = mapped_column(String(10))  # US-GAAP, IFRS, JP-GAAP
    cik: Mapped[str | None] = mapped_column(String(20))
    edinet_code: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    financial_data = relationship("FinancialData", back_populates="company")
    valuations = relationship("Valuation", back_populates="company")
    filings = relationship("Filing", back_populates="company")
    analyses = relationship("CompanyAnalysis", back_populates="company")
```

```python
# src/stock_analyze_system/models/financial_data.py
"""財務データモデル"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class FinancialData(Base):
    __tablename__ = "financial_data"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_type", "fiscal_year_end", "accounting_standard",
            name="uq_financial_natural_key",
        ),
        Index("ix_financial_company_date", "company_id", "fiscal_year_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    accounting_standard: Mapped[str] = mapped_column(String(10))
    currency: Mapped[str] = mapped_column(String(3))  # USD, JPY
    period_type: Mapped[str] = mapped_column(String(10))  # annual, quarterly
    fiscal_year_end: Mapped[date] = mapped_column(Date)

    revenue: Mapped[float | None] = mapped_column(default=None)
    operating_income: Mapped[float | None] = mapped_column(default=None)
    net_income: Mapped[float | None] = mapped_column(default=None)
    total_assets: Mapped[float | None] = mapped_column(default=None)
    equity: Mapped[float | None] = mapped_column(default=None)
    current_assets: Mapped[float | None] = mapped_column(default=None)
    current_liabilities: Mapped[float | None] = mapped_column(default=None)
    total_debt: Mapped[float | None] = mapped_column(default=None)
    cash: Mapped[float | None] = mapped_column(default=None)
    inventory: Mapped[float | None] = mapped_column(default=None)
    cogs: Mapped[float | None] = mapped_column(default=None)
    operating_cf: Mapped[float | None] = mapped_column(default=None)
    capex: Mapped[float | None] = mapped_column(default=None)
    fcf: Mapped[float | None] = mapped_column(default=None)
    ebitda: Mapped[float | None] = mapped_column(default=None)
    eps: Mapped[float | None] = mapped_column(default=None)
    dps: Mapped[float | None] = mapped_column(default=None)
    tax_expense: Mapped[float | None] = mapped_column(default=None)
    income_before_tax: Mapped[float | None] = mapped_column(default=None)
    shares_outstanding: Mapped[float | None] = mapped_column(default=None)
    dividends_paid: Mapped[float | None] = mapped_column(default=None)
    share_repurchases: Mapped[float | None] = mapped_column(default=None)

    last_updated: Mapped[datetime] = mapped_column(server_default=func.now())

    company = relationship("Company", back_populates="financial_data")
```

```python
# src/stock_analyze_system/models/valuation.py
"""バリュエーションモデル"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class Valuation(Base):
    __tablename__ = "valuations"
    __table_args__ = (
        UniqueConstraint("company_id", "date", name="uq_valuation_company_date"),
        Index("ix_valuation_company_date", "company_id", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    date: Mapped[date] = mapped_column(Date)
    stock_price: Mapped[float | None] = mapped_column(default=None)
    market_cap: Mapped[float | None] = mapped_column(default=None)
    per: Mapped[float | None] = mapped_column(default=None)
    pbr: Mapped[float | None] = mapped_column(default=None)
    ev_ebitda: Mapped[float | None] = mapped_column(default=None)
    psr: Mapped[float | None] = mapped_column(default=None)
    fcf_yield: Mapped[float | None] = mapped_column(default=None)
    last_updated: Mapped[datetime] = mapped_column(server_default=func.now())

    company = relationship("Company", back_populates="valuations")
```

```python
# src/stock_analyze_system/models/filing.py
"""提出書類モデル"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class Filing(Base):
    __tablename__ = "filings"
    __table_args__ = (
        Index("ix_filing_company_year", "company_id", "fiscal_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source: Mapped[str] = mapped_column(String(10))  # SEC, EDINET
    filing_type: Mapped[str] = mapped_column(String(10))  # 10-K, 10-Q, 20-F, 6-K
    period_type: Mapped[str] = mapped_column(String(10))  # annual, quarterly
    fiscal_year: Mapped[int] = mapped_column()
    period_end: Mapped[date | None] = mapped_column(Date, default=None)
    filed_at: Mapped[date | None] = mapped_column(Date, default=None)
    accession_no: Mapped[str | None] = mapped_column(String(30), unique=True, default=None)
    doc_id: Mapped[str | None] = mapped_column(String(30), unique=True, default=None)
    storage_path: Mapped[str | None] = mapped_column(Text, default=None)
    content_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    last_updated: Mapped[datetime] = mapped_column(server_default=func.now())

    company = relationship("Company", back_populates="filings")
```

```python
# src/stock_analyze_system/models/company_analysis.py
"""企業分析結果モデル"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class CompanyAnalysis(Base):
    __tablename__ = "company_analyses"
    __table_args__ = (
        UniqueConstraint("company_id", "filing_id", "analysis_type", name="uq_analysis_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"))
    analysis_type: Mapped[str] = mapped_column(String(30))  # business_summary, risk_factors, mda
    result_json: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    company = relationship("Company", back_populates="analyses")
    filing = relationship("Filing")
```

```python
# src/stock_analyze_system/models/watchlist.py
"""ウォッチリストモデル"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    items = relationship("WatchlistItem", back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "company_id", name="uq_watchlist_company"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"))
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))
    status: Mapped[str] = mapped_column(String(20), default="monitoring")
    investment_thesis: Mapped[str | None] = mapped_column(Text, default=None)
    tags: Mapped[str | None] = mapped_column(Text, default=None)
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())

    watchlist = relationship("Watchlist", back_populates="items")
    company = relationship("Company")
```

```python
# src/stock_analyze_system/models/analysis_target.py
"""分析対象銘柄モデル"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class AnalysisTarget(Base):
    __tablename__ = "analysis_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"), unique=True, index=True,
    )
    source: Mapped[str] = mapped_column(String(20), default="manual")
    criteria: Mapped[str | None] = mapped_column(Text, default=None)
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())

    company = relationship("Company")
```

```python
# src/stock_analyze_system/models/screening.py
"""スクリーニングキャッシュモデル"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class ScreeningCache(Base):
    __tablename__ = "screening_cache"
    __table_args__ = (
        Index("ix_screening_cache_updated_at", "updated_at"),
        Index("ix_screening_cache_roe", "roe"),
    )

    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id"), primary_key=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(),
    )

    # Quote data
    stock_price: Mapped[float | None] = mapped_column(default=None)
    market_cap: Mapped[float | None] = mapped_column(default=None)
    trailing_per: Mapped[float | None] = mapped_column(default=None)
    eps: Mapped[float | None] = mapped_column(default=None)

    # Detailed metrics
    forward_per: Mapped[float | None] = mapped_column(default=None)
    pbr: Mapped[float | None] = mapped_column(default=None)
    psr: Mapped[float | None] = mapped_column(default=None)
    ev_ebitda: Mapped[float | None] = mapped_column(default=None)
    dividend_yield: Mapped[float | None] = mapped_column(default=None)
    roe: Mapped[float | None] = mapped_column(default=None)
    operating_margin: Mapped[float | None] = mapped_column(default=None)
    net_margin: Mapped[float | None] = mapped_column(default=None)
    revenue_growth: Mapped[float | None] = mapped_column(default=None)
    earnings_growth: Mapped[float | None] = mapped_column(default=None)
    de_ratio: Mapped[float | None] = mapped_column(default=None)
    peg_ratio: Mapped[float | None] = mapped_column(default=None)
    fcf_yield: Mapped[float | None] = mapped_column(default=None)

    # Company profile
    sector: Mapped[str | None] = mapped_column(String(100), default=None)
    industry: Mapped[str | None] = mapped_column(String(200), default=None)
    exchange: Mapped[str | None] = mapped_column(String(20), default=None)
    beta: Mapped[float | None] = mapped_column(default=None)
    volume: Mapped[int | None] = mapped_column(BigInteger, default=None)

    # Data provenance
    most_recent_quarter: Mapped[date | None] = mapped_column(Date, default=None)
    last_fiscal_year_end: Mapped[date | None] = mapped_column(Date, default=None)
    trailing_eps_date: Mapped[str | None] = mapped_column(String(30), default=None)

    company = relationship("Company")
```

```python
# src/stock_analyze_system/models/competitor_group.py
"""競合グループモデル"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class CompetitorGroup(Base):
    __tablename__ = "competitor_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    accounting_standard: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    members = relationship(
        "CompetitorGroupMember", back_populates="group", cascade="all, delete-orphan",
    )


class CompetitorGroupMember(Base):
    __tablename__ = "competitor_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "company_id", name="uq_group_company"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("competitor_groups.id"))
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))

    group = relationship("CompetitorGroup", back_populates="members")
    company = relationship("Company")
```

```python
# src/stock_analyze_system/models/document_index.py
"""PageIndex ツリーインデックスモデル"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from stock_analyze_system.models.base import Base


class DocumentIndex(Base):
    __tablename__ = "document_indices"

    id: Mapped[int] = mapped_column(primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"), unique=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    index_json: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(50))
    page_count: Mapped[int] = mapped_column()
    node_count: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_queried_at: Mapped[datetime | None] = mapped_column(default=None)

    filing = relationship("Filing")
    company = relationship("Company")
```

- [ ] **Step 4: conftest.py のimportを更新して全モデルをBase.metadataに登録**

`tests/conftest.py` に全モデルのimportを追加（`create_all` が全テーブルを作成するために必要）:

```python
# tests/conftest.py の先頭に追記
from stock_analyze_system.models.company import Company  # noqa: F401
from stock_analyze_system.models.financial_data import FinancialData  # noqa: F401
from stock_analyze_system.models.valuation import Valuation  # noqa: F401
from stock_analyze_system.models.filing import Filing  # noqa: F401
from stock_analyze_system.models.company_analysis import CompanyAnalysis  # noqa: F401
from stock_analyze_system.models.watchlist import Watchlist, WatchlistItem  # noqa: F401
from stock_analyze_system.models.analysis_target import AnalysisTarget  # noqa: F401
from stock_analyze_system.models.screening import ScreeningCache  # noqa: F401
from stock_analyze_system.models.competitor_group import CompetitorGroup, CompetitorGroupMember  # noqa: F401
from stock_analyze_system.models.document_index import DocumentIndex  # noqa: F401
```

- [ ] **Step 5: テスト通過を確認**

Run: `python -m pytest tests/unit/test_models.py -v`
Expected: 全テスト PASS

- [ ] **Step 6: コミット**

```bash
git add src/stock_analyze_system/models/ tests/
git commit -m "feat: add all ORM models including DocumentIndex"
```

---

### Task 8: BaseRepository（ジェネリックCRUD）

**Files:**
- Create: `src/stock_analyze_system/repositories/__init__.py`
- Create: `src/stock_analyze_system/repositories/base.py`
- Create: `tests/unit/repositories/__init__.py`
- Create: `tests/unit/repositories/test_base_repo.py`

- [ ] **Step 1: テストを書く**

```python
# tests/unit/repositories/test_base_repo.py
"""BaseRepository のテスト"""
import pytest
from sqlalchemy.exc import IntegrityError

from stock_analyze_system.models.company import Company
from stock_analyze_system.repositories.base import BaseRepository


@pytest.fixture
def repo(session):
    return BaseRepository(session, Company)


async def test_get_by_id_found(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    result = await repo.get_by_id("US_AAPL")
    assert result is not None
    assert result.ticker == "AAPL"


async def test_get_by_id_not_found(repo):
    result = await repo.get_by_id("US_NONEXIST")
    assert result is None


async def test_list_all(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="US_MSFT", ticker="MSFT", name="Microsoft",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    results = await repo.list_all()
    assert len(results) == 2


async def test_list_all_with_filter(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        market="TSE_PRIME", accounting_standard="IFRS",
    ))
    await session.flush()
    results = await repo.list_all(market="NASDAQ")
    assert len(results) == 1
    assert results[0].id == "US_AAPL"


async def test_upsert_insert(repo):
    result = await repo.upsert(
        filters={"id": "US_AAPL"},
        data={
            "id": "US_AAPL", "ticker": "AAPL", "name": "Apple",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        },
    )
    assert result.id == "US_AAPL"


async def test_upsert_update(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    result = await repo.upsert(
        filters={"id": "US_AAPL"},
        data={"name": "Apple Inc."},
    )
    assert result.name == "Apple Inc."


async def test_upsert_idempotent(repo):
    await repo.upsert(
        filters={"id": "US_AAPL"},
        data={
            "id": "US_AAPL", "ticker": "AAPL", "name": "Apple",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        },
    )
    await repo.upsert(
        filters={"id": "US_AAPL"},
        data={
            "id": "US_AAPL", "ticker": "AAPL", "name": "Apple",
            "market": "NASDAQ", "accounting_standard": "US-GAAP",
        },
    )
    results = await repo.list_all()
    assert len(results) == 1


async def test_delete_existing(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    result = await repo.delete("US_AAPL")
    assert result is True


async def test_delete_nonexistent(repo):
    result = await repo.delete("US_NONEXIST")
    assert result is False


async def test_count(repo, session):
    assert await repo.count() == 0
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    await session.flush()
    assert await repo.count() == 1


async def test_count_with_filter(repo, session):
    session.add(Company(
        id="US_AAPL", ticker="AAPL", name="Apple",
        market="NASDAQ", accounting_standard="US-GAAP",
    ))
    session.add(Company(
        id="JP_7203", security_code="7203", name="Toyota",
        market="TSE_PRIME", accounting_standard="IFRS",
    ))
    await session.flush()
    assert await repo.count(market="NASDAQ") == 1
    assert await repo.count(market="TSE_PRIME") == 1
```

- [ ] **Step 2: テスト失敗を確認**

Run: `python -m pytest tests/unit/repositories/test_base_repo.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: BaseRepository を実装**

```python
# src/stock_analyze_system/repositories/__init__.py
```

```python
# src/stock_analyze_system/repositories/base.py
"""ジェネリックCRUDリポジトリ基盤"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """ジェネリックCRUDリポジトリ"""

    def __init__(self, session: AsyncSession, model: type[T]):
        self._session = session
        self._model = model

    async def get_by_id(self, id: Any) -> T | None:
        return await self._session.get(self._model, id)

    async def list_all(self, **filters) -> list[T]:
        stmt = select(self._model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self._model, key) == value)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert(self, filters: dict, data: dict, label: str = "") -> T:
        stmt = select(self._model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self._model, key) == value)
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            for key, value in data.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            await self._session.flush()
            return existing

        obj = self._model(**{**filters, **data})
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def delete(self, id: Any) -> bool:
        obj = await self.get_by_id(id)
        if obj is None:
            return False
        await self._session.delete(obj)
        await self._session.flush()
        return True

    async def count(self, **filters) -> int:
        stmt = select(sa_func.count()).select_from(self._model)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self._model, key) == value)
        result = await self._session.execute(stmt)
        return result.scalar_one()
```

- [ ] **Step 4: テスト通過を確認**

Run: `python -m pytest tests/unit/repositories/test_base_repo.py -v`
Expected: 全テスト PASS

- [ ] **Step 5: 全テスト通過を確認**

Run: `python -m pytest tests/ -v`
Expected: 全テスト PASS

- [ ] **Step 6: コミット**

```bash
git add src/stock_analyze_system/repositories/ tests/unit/repositories/
git commit -m "feat: add BaseRepository with generic async CRUD"
```

---

### Task 9: conftest.py にサンプルデータ fixture 追加 + 全テスト確認

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: サンプルデータ fixture を追加**

```python
# tests/conftest.py に追記

@pytest.fixture
async def sample_company(session):
    """テスト用米国企業"""
    company = Company(
        id="US_AAPL", ticker="AAPL", name="Apple Inc.",
        market="NASDAQ", accounting_standard="US-GAAP", cik="0000320193",
    )
    session.add(company)
    await session.flush()
    return company


@pytest.fixture
async def sample_jp_company(session):
    """テスト用日本企業"""
    company = Company(
        id="JP_7203", security_code="7203", name="Toyota Motor Corporation",
        name_ja="トヨタ自動車株式会社", market="TSE_PRIME",
        accounting_standard="IFRS", edinet_code="E02144",
    )
    session.add(company)
    await session.flush()
    return company
```

- [ ] **Step 2: 全テスト通過を確認**

Run: `python -m pytest tests/ -v --tb=short`
Expected: 全テスト PASS

- [ ] **Step 3: ruff チェック**

Run: `ruff check src/ tests/`
Expected: エラーなし（または軽微な修正のみ）

- [ ] **Step 4: コミット**

```bash
git add tests/conftest.py
git commit -m "feat: add sample data fixtures to conftest"
```

---

## Phase 1 完了条件

- [ ] `pyproject.toml` でパッケージインストール可能
- [ ] 全11モデル（既存10 + DocumentIndex）がAsyncSessionでCRUD可能
- [ ] `BaseRepository` でジェネリックCRUD（get_by_id, list_all, upsert, delete, count）
- [ ] `config.py` がYAML + .env + 環境変数の3層ロードに対応（既知バグ#12, #20修正済み）
- [ ] `exceptions.py` に例外階層定義済み
- [ ] `shared/formatters.py` に数値フォーマッタ定義済み
- [ ] テスト基盤（async conftest, sample fixtures）構築済み
- [ ] 全テスト PASS、ruff エラーなし
