"""PageIndex の LLM 呼び出しを横取りして診断情報を採取するラッパー.

PageIndex は `generate_toc_init` 等の内部で `pageindex.utils.llm_completion`
を直接呼ぶが、戻り値しか公開しないため finish_reason / completion_tokens /
prompt_tokens が `error_details` に残らず、`Exception('Processing failed')`
の原因 (length 切れ / error / 空応答) を区別できない。

そこで `pageindex.page_index` 名前空間にラッパーを setattr し、
ラッパー側で各呼び出しの結果を contextvars 経由で記録する。
`pageindex.utils` だけパッチしても効かない点 (page_index.py:8 が
`from .utils import *` を行い独立 binding を保持する) は本ファイルの
契約として明示しテストで固定する。
"""
from __future__ import annotations

import contextvars
import logging
from typing import Any

logger = logging.getLogger(__name__)

# state: {"calls": [<diag dict>, ...]} or None when capture is not enabled
_state_var: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "pageindex_diagnostic_state", default=None,
)

_INSTALL_FLAG = "_sas_diagnostic_wrappers_installed"

# `generate_toc_init` / `generate_toc_continue` は `max_tokens=32768` を
# ハードコードしており `configure_max_tokens(...)` をバイパスする.
# その経路で <think> が暴走しないよう、Stock_Analyze 側でラッパーが上から
# クランプできるよう Module-level に持つ.
_max_tokens_clamp: int | None = None


def configure_max_tokens_clamp(value: int | None) -> None:
    """ラッパー越しに渡る max_tokens の上限を設定する (None で解除)."""
    global _max_tokens_clamp
    _max_tokens_clamp = value


def reset_diagnostic() -> None:
    """新しい build の前に診断バッファを初期化する."""
    _state_var.set({"calls": []})


def get_last_diagnostic() -> dict | None:
    """最後に記録された 1 件の診断 dict を返す (なければ None)."""
    state = _state_var.get()
    if not state:
        return None
    calls = state.get("calls") or []
    return calls[-1] if calls else None


def get_all_diagnostics() -> list[dict]:
    """記録された全 LLM 呼び出しの診断 dict を時系列で返す."""
    state = _state_var.get()
    if not state:
        return []
    return list(state.get("calls", []))


def _record(diag: dict[str, Any]) -> None:
    """記録. `reset_diagnostic` 未呼び出し時は何もしない (本番で誤って
    無効化されても呼び出しは静かに継続させる)."""
    state = _state_var.get()
    if state is None:
        return
    state.setdefault("calls", []).append(diag)


def _coerce_content_head(content: Any) -> str:
    if not isinstance(content, str):
        return ""
    return content[:200]


def _coerce_content_len(content: Any) -> int:
    return len(content) if isinstance(content, str) else 0


def install_diagnostic_wrappers() -> bool:
    """PageIndex の page_index 名前空間に LLM 呼び出しラッパーを setattr する.

    Returns:
        True: 新規にインストールした
        False: 既にインストール済 / PageIndex 未導入で skip

    Note (極めて重要):
        `pageindex.utils` でなく `pageindex.page_index` モジュールを必ず
        差し替える. page_index.py:8 が `from .utils import *` を行い独立
        binding を持つため、utils 側だけのパッチは generate_toc_init から
        呼ばれる bare `llm_completion(...)` を捕捉できない.

        さらに `from pageindex import page_index` や
        `import pageindex.page_index` は、`pageindex/__init__.py:1` の
        `from .page_index import *` で *同名の関数* `page_index` が
        re-export されているため、いずれも *モジュールではなく関数* を
        返す。setattr が無効化される。`sys.modules` 経由で本物のモジュール
        オブジェクトを取り、そこに setattr する.
    """
    import sys

    try:
        import pageindex  # noqa: F401 - trigger __init__.py / submodule import
    except ImportError:
        logger.warning("pageindex package not importable; diagnostic wrappers skipped")
        return False

    pi_pkg = sys.modules.get("pageindex.page_index")
    if pi_pkg is None or type(pi_pkg).__name__ != "module":
        logger.warning(
            "pageindex.page_index module not found in sys.modules; "
            "diagnostic wrappers skipped",
        )
        return False

    if getattr(pi_pkg, _INSTALL_FLAG, False):
        return False

    def wrapped_llm_completion(
        model,
        prompt,
        chat_history=None,
        return_finish_reason=False,
        api_base=None,
        max_tokens=None,
    ):
        # 委譲先は呼び出しごとに lookup する (テストが pageindex.utils.llm_completion
        # を monkeypatch できるように)
        from pageindex import utils as pi_utils

        max_tokens_effective = max_tokens
        if _max_tokens_clamp is not None and max_tokens is not None:
            max_tokens_effective = min(max_tokens, _max_tokens_clamp)

        diag = {
            "kind": "sync",
            "model": model,
            "max_tokens": max_tokens,
            "prompt_head": (prompt or "")[:200] if isinstance(prompt, str) else "",
        }
        if max_tokens_effective != max_tokens:
            diag["max_tokens_effective"] = max_tokens_effective

        try:
            result = pi_utils.llm_completion(
                model=model,
                prompt=prompt,
                chat_history=chat_history,
                return_finish_reason=return_finish_reason,
                api_base=api_base,
                max_tokens=max_tokens_effective,
            )
        except Exception as exc:
            _record({
                **diag,
                "finish_reason": "error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })
            raise

        if return_finish_reason and isinstance(result, tuple) and len(result) == 2:
            content, finish_reason = result
        else:
            content, finish_reason = result, None

        _record({
            **diag,
            "finish_reason": finish_reason,
            "content_len": _coerce_content_len(content),
            "content_head": _coerce_content_head(content),
        })
        return result

    async def wrapped_llm_acompletion(
        model,
        prompt,
        api_base=None,
        max_tokens=None,
    ):
        from pageindex import utils as pi_utils

        max_tokens_effective = max_tokens
        if _max_tokens_clamp is not None and max_tokens is not None:
            max_tokens_effective = min(max_tokens, _max_tokens_clamp)

        diag = {
            "kind": "async",
            "model": model,
            "max_tokens": max_tokens,
            "prompt_head": (prompt or "")[:200] if isinstance(prompt, str) else "",
        }
        if max_tokens_effective != max_tokens:
            diag["max_tokens_effective"] = max_tokens_effective

        try:
            content = await pi_utils.llm_acompletion(
                model=model,
                prompt=prompt,
                api_base=api_base,
                max_tokens=max_tokens_effective,
            )
        except Exception as exc:
            _record({
                **diag,
                "finish_reason": "error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })
            raise

        _record({
            **diag,
            # pageindex.utils.llm_acompletion は finish_reason を返さないため None
            "finish_reason": None,
            "content_len": _coerce_content_len(content),
            "content_head": _coerce_content_head(content),
        })
        return content

    pi_pkg.llm_completion = wrapped_llm_completion
    pi_pkg.llm_acompletion = wrapped_llm_acompletion
    setattr(pi_pkg, _INSTALL_FLAG, True)
    return True
