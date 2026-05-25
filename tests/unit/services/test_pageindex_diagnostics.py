"""PageIndex LLM 呼び出しの診断ラッパーのテスト.

`<pageindex-repo>/pageindex/page_index.py:8` は
`from .utils import *` を行うため、`pageindex.page_index` モジュールは
`llm_completion` / `llm_acompletion` の独立したバインドを保持する。
そのため Stock_Analyze 側でラッパーをインストールする場合は、
`pageindex.utils` だけでなく `pageindex.page_index` を必ず差し替える必要がある
(差し替えないと generate_toc_init などの内部呼び出しが捕捉できない)。
"""
from __future__ import annotations

import sys
import types

import pytest

from stock_analyze_system.services.pageindex import diagnostics


@pytest.fixture(autouse=True)
def _reset_diagnostic_state():
    diagnostics.reset_diagnostic()
    yield


@pytest.fixture
def compatible_pageindex(monkeypatch):
    fake_pkg = types.ModuleType("pageindex")
    fake_utils = types.ModuleType("pageindex.utils")
    fake_page_index = types.ModuleType("pageindex.page_index")

    def llm_completion(
        model, prompt, chat_history=None, return_finish_reason=False,
        api_base=None, max_tokens=None,
    ):
        if return_finish_reason:
            return "{}", "finished"
        return "{}"

    async def llm_acompletion(model, prompt, api_base=None, max_tokens=None):
        return "{}"

    def toc_detector_single_page(content, model=None, api_base=None):
        return fake_page_index.llm_completion(
            model=model, prompt=content, api_base=api_base,
        )

    fake_utils.llm_completion = llm_completion
    fake_utils.llm_acompletion = llm_acompletion
    fake_page_index.llm_completion = llm_completion
    fake_page_index.llm_acompletion = llm_acompletion
    fake_page_index.toc_detector_single_page = toc_detector_single_page
    fake_pkg.page_index = lambda *args, **kwargs: {}
    fake_pkg.utils = fake_utils

    monkeypatch.setitem(sys.modules, "pageindex", fake_pkg)
    monkeypatch.setitem(sys.modules, "pageindex.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "pageindex.page_index", fake_page_index)
    return fake_page_index


def test_get_last_diagnostic_is_none_when_state_cleared():
    diagnostics._state_var.set(None)
    assert diagnostics.get_last_diagnostic() is None


def test_reset_then_record_then_get_last_returns_entry():
    diagnostics.reset_diagnostic()
    diagnostics._record({"kind": "sync", "finish_reason": "length"})
    assert diagnostics.get_last_diagnostic() == {
        "kind": "sync", "finish_reason": "length",
    }


def test_get_all_diagnostics_preserves_order():
    diagnostics.reset_diagnostic()
    diagnostics._record({"i": 1})
    diagnostics._record({"i": 2})
    diagnostics._record({"i": 3})
    assert [d["i"] for d in diagnostics.get_all_diagnostics()] == [1, 2, 3]


def test_install_targets_real_page_index_module_not_the_reexported_function(compatible_pageindex):
    """`pageindex.__init__.py` の `from .page_index import *` は同名の
    関数 `page_index` を re-export し、結果として `from pageindex import
    page_index` と `import pageindex.page_index` の両方が *モジュールでは
    なく関数* を返す。そのため setattr する対象は `sys.modules` 経由で
    取った本物のモジュールでなければ、bare `llm_completion(...)` の
    呼び出しに wrapper が効かない (page_index.py:8 の `from .utils import *`
    が結局元の binding を保つ)。"""
    import sys
    import pageindex  # noqa: F401 - trigger import chain
    from pageindex import utils as pi_utils

    real_module = sys.modules["pageindex.page_index"]
    assert type(real_module).__name__ == "module", (
        "sys.modules['pageindex.page_index'] must return the actual module"
    )

    orig_sync = pi_utils.llm_completion
    orig_async = pi_utils.llm_acompletion

    diagnostics.install_diagnostic_wrappers()

    # 本物のモジュールの binding が wrapper に差し替わっていること
    assert real_module.llm_completion is not orig_sync, (
        "real pageindex.page_index module's llm_completion must be patched, "
        "otherwise generate_toc_init's bare `llm_completion(...)` resolves "
        "to the un-wrapped utils binding."
    )
    assert real_module.llm_acompletion is not orig_async
    # pageindex.utils はそのまま (wrapper が委譲先として使う)
    assert pi_utils.llm_completion is orig_sync
    assert pi_utils.llm_acompletion is orig_async


def test_wrapper_is_hit_by_bare_name_call_inside_page_index_module(monkeypatch, compatible_pageindex):
    """PageIndex のヘルパー (toc_detector_single_page 等) が bare
    `llm_completion(...)` で wrapper を呼び出すこと。これが効かないと
    実運用の tree_parser → meta_processor → toc_transformer 経路の
    diagnostic が一切採取できない (job 19/20 で実際に発覚した回帰)。"""
    import sys

    diagnostics.install_diagnostic_wrappers()
    diagnostics.reset_diagnostic()

    captured: list = []

    def stub(model, prompt, chat_history=None, return_finish_reason=False,
             api_base=None, max_tokens=None):
        captured.append(prompt[:30])
        return '{"toc_detected": "yes"}'

    monkeypatch.setattr("pageindex.utils.llm_completion", stub)

    real_module = sys.modules["pageindex.page_index"]
    # toc_detector_single_page は page_index.py 内で bare llm_completion を呼ぶ
    real_module.toc_detector_single_page("dummy content", model="m", api_base="http://x")

    assert len(captured) == 1
    last = diagnostics.get_last_diagnostic()
    assert last is not None, (
        "diagnostic was not recorded — wrapper bypass detected"
    )
    assert last["model"] == "m"
    assert last["content_head"] == '{"toc_detected": "yes"}'


def test_install_is_idempotent(compatible_pageindex):
    diagnostics.install_diagnostic_wrappers()
    first = diagnostics.install_diagnostic_wrappers()
    second = diagnostics.install_diagnostic_wrappers()
    assert first is False, "second install must be a no-op"
    assert second is False


def test_wrapped_sync_records_finish_reason_and_content_head(monkeypatch, compatible_pageindex):
    diagnostics.install_diagnostic_wrappers()
    diagnostics.reset_diagnostic()

    def stub(
        model, prompt, chat_history=None, return_finish_reason=False,
        api_base=None, max_tokens=None,
    ):
        if return_finish_reason:
            return ('{"items": []}', "max_output_reached")
        return '{"items": []}'

    monkeypatch.setattr("pageindex.utils.llm_completion", stub)

    import sys as _sys
    pi_pkg = _sys.modules["pageindex.page_index"]

    content, finish = pi_pkg.llm_completion(
        model="m", prompt="please return JSON",
        return_finish_reason=True, max_tokens=32768,
    )

    assert content == '{"items": []}'
    assert finish == "max_output_reached"
    last = diagnostics.get_last_diagnostic()
    assert last is not None
    assert last["kind"] == "sync"
    assert last["finish_reason"] == "max_output_reached"
    assert last["content_head"] == '{"items": []}'
    assert last["content_len"] == len('{"items": []}')
    assert last["prompt_head"] == "please return JSON"
    assert last["max_tokens"] == 32768
    assert last["model"] == "m"


async def test_wrapped_async_records_content_head(monkeypatch, compatible_pageindex):
    diagnostics.install_diagnostic_wrappers()
    diagnostics.reset_diagnostic()

    async def stub(model, prompt, api_base=None, max_tokens=None):
        return '{"summary": "test"}'

    monkeypatch.setattr("pageindex.utils.llm_acompletion", stub)

    import sys as _sys
    pi_pkg = _sys.modules["pageindex.page_index"]

    out = await pi_pkg.llm_acompletion(
        model="m2", prompt="summarise section", max_tokens=4096,
    )

    assert out == '{"summary": "test"}'
    last = diagnostics.get_last_diagnostic()
    assert last is not None
    assert last["kind"] == "async"
    assert last["content_head"] == '{"summary": "test"}'
    assert last["model"] == "m2"
    assert last["max_tokens"] == 4096
    assert last["prompt_head"] == "summarise section"


def test_record_when_state_is_none_does_not_crash():
    diagnostics._state_var.set(None)
    diagnostics._record({"kind": "sync"})
    assert diagnostics.get_last_diagnostic() is None


def test_wrapper_clamps_max_tokens_when_clamp_configured(monkeypatch, compatible_pageindex):
    """PageIndex `generate_toc_init` は max_tokens=32768 をハードコードして
    `configure_max_tokens(...)` をバイパスするため、Stock_Analyze 側で
    クランプして渡さなければ thinking 32768 トークン分の暴走を抑えられない."""
    diagnostics.install_diagnostic_wrappers()
    diagnostics.reset_diagnostic()
    seen: dict = {}

    def stub(
        model, prompt, chat_history=None, return_finish_reason=False,
        api_base=None, max_tokens=None,
    ):
        seen["max_tokens"] = max_tokens
        return '{"items": []}'

    monkeypatch.setattr("pageindex.utils.llm_completion", stub)

    diagnostics.configure_max_tokens_clamp(8192)
    try:
        import sys as _sys
        pi_pkg = _sys.modules["pageindex.page_index"]
        pi_pkg.llm_completion(model="m", prompt="x", max_tokens=32768)
    finally:
        diagnostics.configure_max_tokens_clamp(None)

    assert seen["max_tokens"] == 8192


def test_wrapper_passes_through_when_clamp_is_none(monkeypatch, compatible_pageindex):
    diagnostics.install_diagnostic_wrappers()
    diagnostics.reset_diagnostic()
    seen: dict = {}

    def stub(
        model, prompt, chat_history=None, return_finish_reason=False,
        api_base=None, max_tokens=None,
    ):
        seen["max_tokens"] = max_tokens
        return '{"items": []}'

    monkeypatch.setattr("pageindex.utils.llm_completion", stub)

    diagnostics.configure_max_tokens_clamp(None)
    import sys as _sys
    pi_pkg = _sys.modules["pageindex.page_index"]
    pi_pkg.llm_completion(model="m", prompt="x", max_tokens=32768)

    assert seen["max_tokens"] == 32768


def test_wrapper_does_not_inflate_below_clamp(monkeypatch, compatible_pageindex):
    diagnostics.install_diagnostic_wrappers()
    diagnostics.reset_diagnostic()
    seen: dict = {}

    def stub(
        model, prompt, chat_history=None, return_finish_reason=False,
        api_base=None, max_tokens=None,
    ):
        seen["max_tokens"] = max_tokens
        return '{}'

    monkeypatch.setattr("pageindex.utils.llm_completion", stub)

    diagnostics.configure_max_tokens_clamp(8192)
    try:
        import sys as _sys
        pi_pkg = _sys.modules["pageindex.page_index"]
        pi_pkg.llm_completion(model="m", prompt="x", max_tokens=1024)
    finally:
        diagnostics.configure_max_tokens_clamp(None)

    # 1024 < 8192 なのでクランプは効かず、そのまま 1024 が下流に渡る
    assert seen["max_tokens"] == 1024


def test_wrapped_sync_records_diagnostic_on_raise(monkeypatch, compatible_pageindex):
    diagnostics.install_diagnostic_wrappers()
    diagnostics.reset_diagnostic()

    def stub(
        model, prompt, chat_history=None, return_finish_reason=False,
        api_base=None, max_tokens=None,
    ):
        raise RuntimeError("llm boom")

    monkeypatch.setattr("pageindex.utils.llm_completion", stub)

    import sys as _sys
    pi_pkg = _sys.modules["pageindex.page_index"]
    with pytest.raises(RuntimeError, match="llm boom"):
        pi_pkg.llm_completion(model="m", prompt="prompt text", max_tokens=123)

    last = diagnostics.get_last_diagnostic()
    assert last is not None
    assert last["kind"] == "sync"
    assert last["finish_reason"] == "error"
    assert last["error_type"] == "RuntimeError"
    assert last["error_message"] == "llm boom"
    assert last["prompt_head"] == "prompt text"
    assert last["max_tokens"] == 123


async def test_wrapped_async_records_diagnostic_on_raise(monkeypatch, compatible_pageindex):
    diagnostics.install_diagnostic_wrappers()
    diagnostics.reset_diagnostic()

    async def stub(model, prompt, api_base=None, max_tokens=None):
        raise TimeoutError("async boom")

    monkeypatch.setattr("pageindex.utils.llm_acompletion", stub)

    import sys as _sys
    pi_pkg = _sys.modules["pageindex.page_index"]
    with pytest.raises(TimeoutError, match="async boom"):
        await pi_pkg.llm_acompletion(model="m2", prompt="async prompt", max_tokens=456)

    last = diagnostics.get_last_diagnostic()
    assert last is not None
    assert last["kind"] == "async"
    assert last["finish_reason"] == "error"
    assert last["error_type"] == "TimeoutError"
    assert last["error_message"] == "async boom"
    assert last["prompt_head"] == "async prompt"
    assert last["max_tokens"] == 456
