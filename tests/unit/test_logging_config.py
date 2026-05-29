"""ロギング設定のテスト"""
import logging

import pytest

from stock_analyze_system.config import LoggingConfig
from stock_analyze_system.logging_config import setup_logging


def _count_own_handlers(root: logging.Logger) -> int:
    """setup_logging が追加したハンドラのみカウントする"""
    return sum(
        1 for h in root.handlers
        if type(h) in (logging.FileHandler, logging.StreamHandler)
    )


@pytest.fixture(autouse=True)
def _clean_root_logger():
    """各テスト後にsetup_loggingが追加したハンドラをクリアする"""
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        if type(handler) in (logging.FileHandler, logging.StreamHandler):
            root.removeHandler(handler)
            handler.close()


def test_setup_logging_creates_handlers(tmp_path):
    config = LoggingConfig(level="DEBUG", file=str(tmp_path / "test.log"))
    setup_logging(config)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert _count_own_handlers(root) == 2  # file + console


def test_setup_logging_no_duplicate_handlers(tmp_path):
    """2回呼んでもハンドラが重複しないこと（参考プロジェクトバグ修正確認）"""
    config = LoggingConfig(level="INFO", file=str(tmp_path / "test.log"))
    setup_logging(config)
    setup_logging(config)
    root = logging.getLogger()
    assert _count_own_handlers(root) == 2  # 重複なし


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
