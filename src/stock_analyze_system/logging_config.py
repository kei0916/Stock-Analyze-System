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

    # 重複ハンドラ防止: 自前で追加した FileHandler/StreamHandler のみカウント
    own_handlers = [
        h for h in root_logger.handlers
        if type(h) in (logging.FileHandler, logging.StreamHandler)
    ]
    if not own_handlers:
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
