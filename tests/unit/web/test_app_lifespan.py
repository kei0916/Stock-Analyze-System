"""Web app の lifespan が worker を起動しないことを保証 (ST02)。"""
from __future__ import annotations

import inspect

from stock_analyze_system.web import app as web_app_module


def test_lifespan_source_does_not_start_worker():
    """create_app のソース文字列に analysis_queue.start() が含まれないこと。"""
    src = inspect.getsource(web_app_module.create_app)
    assert ".analysis_queue.start" not in src, (
        "Web lifespan must not start the in-process worker; "
        "use `stock-analyze worker` CLI instead."
    )
    assert ".analysis_queue.stop" not in src, (
        "Web lifespan must not stop a worker it never started."
    )
