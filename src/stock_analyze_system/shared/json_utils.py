"""共有JSONユーティリティ（日本語安全なparse/dump）"""
from __future__ import annotations

import json
import math
import re
from numbers import Number
from typing import Any


# LLM出力から ```json ... ``` / ``` ... ``` を抽出するパターン
_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def safe_json_loads(text: str, fallback_key: str = "raw_answer") -> dict:
    """JSON文字列を安全にパースする。失敗時は fallback_key でラップして返す。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {fallback_key: text}


def _try_parse_dict(candidate: str) -> dict | None:
    """文字列をJSONとしてパースし、dictの場合のみ返す"""
    try:
        result = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return result if isinstance(result, dict) else None


def _find_first_decodable_dict(text: str) -> dict | None:
    """文字列中を走査し、最初にdecodeできたJSON objectを返す。"""
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            result, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(result, dict):
            return result
        start = text.find("{", start + 1)
    return None


def extract_json_object(text: str) -> dict | None:
    """LLM出力から最初のJSONオブジェクトを頑健に抽出する。

    3段階フォールバック:
      1. そのままパース
      2. Markdownコードブロック (```json ... ```) 内を抽出してパース
      3. 文字列中を走査し、最初にdecodeできたJSON objectを抽出

    成功時はdict、失敗時はNoneを返す。``safe_json_loads`` と異なり失敗時はラップせず
    None を返す（抽出できたかどうかを呼び出し側で判断させるため）。
    """
    if not text:
        return None

    if (result := _try_parse_dict(text)) is not None:
        return result

    for match in _CODE_BLOCK_RE.finditer(text):
        if (result := _try_parse_dict(match.group(1).strip())) is not None:
            return result

    return _find_first_decodable_dict(text)


def json_dumps_ja(obj: Any, *, indent: int | None = None, default: Any = None) -> str:
    """ensure_ascii=False でJSON直列化する（日本語をエスケープしない）。"""
    return json.dumps(obj, ensure_ascii=False, indent=indent, default=default)


def json_safe(obj: Any) -> Any:
    """Return a recursively JSON-compliant value.

    Starlette's JSONResponse uses allow_nan=False, so NaN/Infinity must be
    converted before returning API payloads.
    """
    if isinstance(obj, dict):
        return {key: json_safe(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(value) for value in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, Number):
        try:
            return obj if math.isfinite(obj) else None
        except (TypeError, ValueError):
            return None
    return obj
