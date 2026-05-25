"""ADR-004 §4.5 — Step 3 reasoning_content runaway リスクの実機検証.

`_analyze_section` と同じ呼び出し条件 (extra_body enable_thinking=False,
response_format なし, max_tokens=16384) で実 10-K の risk_factors / mda /
business_summary / competitors を Qwen3.6 へ投げ、`content` / `reasoning_content`
/ `finish_reason` / `usage` を観測する。

実行:
  PYTHONUNBUFFERED=1 python3 scripts/verify_step3_reasoning_runaway.py 2>&1 \
      | tee /tmp/step3_runaway.log
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, "src")

# Local llama-server is OpenAI-compatible but litellm still requires an api_key
# for the `openai/...` route. The production app loads `.env` (OPENAI_API_KEY=dummy);
# mirror that here without depending on dotenv at script level.
os.environ.setdefault("OPENAI_API_KEY", "dummy")

import litellm

from stock_analyze_system.services.filing_section_extractor import FilingSectionExtractor
from stock_analyze_system.services.prompts import ANALYSIS_TYPES

# === probe target =========================================================
# RXRX 2025 10-K は ADR-004 §Situation で PageIndex が落ちた filing。
FILING_TYPE = "10-K"
STORAGE_PATH = "data/filings/SEC/US_RXRX/2025/annual/10-K/0001601830-26-000039"

# === LLM call config (must match LlmClient.completion + RagService) =======
MODEL = "openai/Qwen3.6-27B-Q4_K_M.gguf"
BASE_URL = "http://localhost:8080/v1"
MAX_TOKENS = 16384            # config.py LlmConfig.max_tokens default
TEMPERATURE = 0.1             # config.py LlmConfig.temperature default
REQUEST_TIMEOUT = 600         # config.py LlmConfig.request_timeout default
ENABLE_THINKING = False       # config.py LlmConfig.enable_thinking default

OUTPUT_PATH = Path("data/step3_runaway_verification.json")


@dataclass
class _FakeFiling:
    """FilingSectionExtractor が触る最小フィールドのみ持つ。"""
    id: int
    filing_type: str
    storage_path: str


async def _probe_section(analysis_type: str, section_text: str) -> dict:
    spec = ANALYSIS_TYPES[analysis_type]
    prompt = f"{spec['prompt']}\n\n--- Filing section text ---\n{section_text}"

    messages = [{"role": "user", "content": prompt}]
    started = time.perf_counter()
    try:
        resp = await litellm.acompletion(
            model=MODEL,
            messages=messages,
            api_base=BASE_URL,
            timeout=REQUEST_TIMEOUT,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            extra_body={"chat_template_kwargs": {"enable_thinking": ENABLE_THINKING}},
        )
        elapsed = time.perf_counter() - started
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started
        return {
            "analysis_type": analysis_type,
            "prompt_chars": len(prompt),
            "section_chars": len(section_text),
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_sec": round(elapsed, 2),
        }

    choice = resp.choices[0]
    msg = choice.message
    # litellm normalises reasoning_content under .reasoning_content (CoT models).
    content = (getattr(msg, "content", None) or "")
    reasoning = getattr(msg, "reasoning_content", None) or ""
    finish_reason = getattr(choice, "finish_reason", None)
    usage = getattr(resp, "usage", None)
    usage_dict = (
        {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        if usage is not None else None
    )

    return {
        "analysis_type": analysis_type,
        "prompt_chars": len(prompt),
        "section_chars": len(section_text),
        "elapsed_sec": round(elapsed, 2),
        "finish_reason": finish_reason,
        "content_chars": len(content),
        "content_empty": not content.strip(),
        "content_head": content[:200],
        "reasoning_chars": len(reasoning),
        "reasoning_head": reasoning[:200],
        "usage": usage_dict,
    }


async def main() -> int:
    extractor = FilingSectionExtractor()
    filing = _FakeFiling(id=0, filing_type=FILING_TYPE, storage_path=STORAGE_PATH)

    print(f"[extract] filing_type={FILING_TYPE} path={STORAGE_PATH}")
    sections = await extractor.extract(filing)
    sizes = {k: len(v or "") for k, v in sections.items()}
    print(f"[extract] section sizes (chars): {sizes}")

    def _print(atype: str, result: dict) -> None:
        if "error" in result:
            print(f"  -> ERROR {result['error']} (elapsed={result['elapsed_sec']}s)")
            return
        print(
            f"  -> finish={result['finish_reason']} "
            f"content_chars={result['content_chars']} "
            f"reasoning_chars={result['reasoning_chars']} "
            f"usage={result['usage']} elapsed={result['elapsed_sec']}s "
            f"empty={result['content_empty']}"
        )

    # ── Phase A: production-faithful probe (no truncation) ──
    results: list[dict] = []
    for atype in ["mda", "competitors", "business_summary", "risk_factors"]:
        text = sections.get(atype, "")
        if not text:
            print(f"[full] SKIP {atype}: empty section")
            results.append({"phase": "full", "analysis_type": atype, "skipped": True})
            continue
        print(f"[full] {atype}: section_chars={len(text)}")
        result = await _probe_section(atype, text)
        result["phase"] = "full"
        results.append(result)
        _print(atype, result)

    # ── Phase B: truncated probe to specifically reach the reasoning_content
    # runaway scenario. Slot ctx=8192; reserve ~2.5K for response + chat template
    # → cap prompt around ~5.5K tokens (~17K chars at ~3 chars/tok English).
    TRUNC_CHARS = 17000
    for atype in ["mda", "risk_factors"]:
        text = sections.get(atype, "") or ""
        if not text:
            continue
        truncated = text[:TRUNC_CHARS]
        print(f"[trunc] {atype}: section_chars={len(truncated)} (orig {len(text)})")
        result = await _probe_section(atype, truncated)
        result["phase"] = "truncated"
        result["truncated_to"] = TRUNC_CHARS
        results.append(result)
        _print(atype, result)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "filing_type": FILING_TYPE,
                "storage_path": STORAGE_PATH,
                "model": MODEL,
                "max_tokens": MAX_TOKENS,
                "enable_thinking_extra_body": ENABLE_THINKING,
                "section_sizes": sizes,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n[output] wrote {OUTPUT_PATH}")

    # Summary line for quick grep
    empties = [r for r in results if r.get("content_empty")]
    errors = [r for r in results if "error" in r]
    print(
        f"[summary] runs={len(results)} empty_content={len(empties)} "
        f"errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
