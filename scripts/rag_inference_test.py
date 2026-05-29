"""PageIndex RAG推論テスト — インデックス構築 + TOC検証 + RAGクエリ

使い方:
  # 初回（インデックス構築あり）:
  PYTHONUNBUFFERED=1 python3 scripts/rag_inference_test.py 2>&1 | tee /tmp/rag_inference_test.log

  # キャッシュツリー再利用（Phase 1スキップ）:
  PYTHONUNBUFFERED=1 python3 scripts/rag_inference_test.py --use-cache 2>&1 | tee /tmp/rag_inference_test.log
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time

sys.path.insert(0, "src")
sys.path.insert(0, "/tmp/PageIndex")

from pathlib import Path

from stock_analyze_system.config import load_config, LlmConfig
from stock_analyze_system.services.llm_client import LlmClient
from stock_analyze_system.services.pageindex.tree_utils import (
    collect_node_map,
    count_nodes,
    node_page,
    strip_text,
)
from stock_analyze_system.shared.json_utils import extract_json_object

# ── 設定 ──────────────────────────────────────────────────────

MODEL = "openai/Qwen3.6-27B-Q4_K_M.gguf"
PDF_PATH = "data/filings/SEC/US_AAPL/2025/annual/10-K/0000320193-25-000079/converted.pdf"
BASE_URL = "http://localhost:8080/v1"
TREE_CACHE_DIR = Path("/tmp")

# 難易度別の回答生成設定（basic: 非推論＋短答、heavy/long_context: 推論モード）
DIFFICULTY_SETTINGS = {
    "basic":        {"thinking": False, "max_tokens": 2048},
    "heavy":        {"thinking": True,  "max_tokens": 8192},
    "long_context": {"thinking": True,  "max_tokens": 16384},
}

# カテゴリ別RAGテスト質問
# difficulty: basic(基本事実) / heavy(重い推論) / long_context(長文把握)
RAG_QUESTIONS = [
    # ── 基本（比較ベースライン） ──
    {
        "difficulty": "basic",
        "category": "数値抽出",
        "question": "Appleの2024年度の総売上高（Total net sales）はいくらですか？",
    },
    {
        "difficulty": "basic",
        "category": "リスト抽出",
        "question": "主要なリスク要因を3つ挙げてください。",
    },
    {
        "difficulty": "basic",
        "category": "前年比較",
        "question": "研究開発費（R&D）は前年比でどのように変化しましたか？",
    },
    # ── 重い推論（複数ソース統合＋計算＋因果推論） ──
    {
        "difficulty": "heavy",
        "category": "セグメント分析＋計算",
        "question": (
            "Appleの2025年度のProducts部門とServices部門それぞれの売上額と"
            "グロスマージン率を特定し、全社グロスマージン率への各部門の寄与度を"
            "定量的に説明してください。さらに今後サービス事業の構成比上昇が"
            "全社収益性に与える影響を考察してください。"
        ),
    },
    {
        "difficulty": "heavy",
        "category": "キャッシュフロー統合分析",
        "question": (
            "2023年度から2025年度までの営業キャッシュフロー、投資キャッシュフロー、"
            "財務キャッシュフローの推移を読み取り、Appleが成長フェーズか成熟フェーズかを"
            "判断してください。また株主還元（配当＋自社株買い）の総額を年度別に示し、"
            "現在の還元水準の持続可能性を営業CFとの比率で評価してください。"
        ),
    },
    {
        "difficulty": "heavy",
        "category": "地政学×財務影響",
        "question": (
            "リスク要因セクションで言及されている地政学リスク（中国、台湾を含む）と、"
            "MD&Aでの地域別売上の記述を照らし合わせ、Greater China地域の売上変動が"
            "全社業績に与える具体的影響を推論してください。"
        ),
    },
    # ── 長文把握（広範囲スキャン＋網羅的抽出） ──
    {
        "difficulty": "long_context",
        "category": "リスク要因網羅分類",
        "question": (
            "Item 1A. Risk Factorsセクションに記載されている全てのリスク要因を網羅的に列挙し、"
            "以下の5カテゴリに分類してください: (1)マクロ経済・地政学 (2)サプライチェーン・製造 "
            "(3)法規制・コンプライアンス (4)技術・競争 (5)財務・市場。"
            "各カテゴリに該当する件数と代表的なリスクのタイトルを示してください。"
        ),
    },
    {
        "difficulty": "long_context",
        "category": "脚注全列挙要約",
        "question": (
            "Item 8. Financial StatementsのNotes to Consolidated Financial Statementsに含まれる"
            "全ての脚注を番号順に列挙し、それぞれのタイトルと主な内容を1〜2行で要約してください。"
        ),
    },
]

config = load_config("config/settings.yaml")
llm_config = LlmConfig(
    backend=config.llm.backend,
    base_url=BASE_URL,
    model=MODEL,
    model_quality=MODEL,
    enable_thinking=config.llm.enable_thinking,
    temperature=config.llm.temperature,
    max_tokens=config.llm.max_tokens,
    request_timeout=config.llm.request_timeout,
)
client = LlmClient(llm_config)


def _tree_cache_path(
    pdf_path: str | Path,
    model: str,
    build_options: dict | None = None,
) -> Path:
    """PDF / model / build options / file 内容ごとに分離された tree cache path を返す。

    cache key には次を含める:
      - pdf_path (str)
      - model (str)
      - PDF file の (mtime_ns, size) — 存在しない場合は (0, 0)
      - build_options を sort_keys でシリアライズした JSON (None なら "{}")
    """
    pdf_path = Path(pdf_path)
    try:
        st = pdf_path.stat()
        stat_part = f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        stat_part = "0:0"
    options_part = json.dumps(build_options or {}, sort_keys=True, ensure_ascii=False)
    raw = f"{pdf_path}|{model}|{stat_part}|{options_part}"
    cache_key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", pdf_path.stem) or "document"
    return TREE_CACHE_DIR / f"rag_tree_cache_{safe_stem}_{cache_key}.json"


def _build_options_for_cache() -> dict:
    return {
        "toc_check_pages": config.pageindex.toc_check_pages,
        "max_pages_per_node": config.pageindex.max_pages_per_node,
        "max_tokens_per_node": config.pageindex.max_tokens_per_node,
        "add_node_summary": bool(config.pageindex.add_node_summary),
        "add_node_text": bool(config.pageindex.add_node_text),
        "max_tokens": client.max_tokens,
    }


def separator(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


# 質問からの日本語/英語キーワード → 10-Kセクション名 のラフマッピング
_MDNA_FS = ["management", "discussion", "financial statements"]
_FS_ONLY = ["financial statements"]
_RISK_ONLY = ["risk factors"]
_FALLBACK_KEYWORDS: dict[str, list[str]] = {
    "売上": _MDNA_FS,
    "r&d": _MDNA_FS,
    "研究開発": _MDNA_FS,
    "グロスマージン": _MDNA_FS,
    "セグメント": _MDNA_FS,
    "キャッシュフロー": _FS_ONLY,
    "脚注": _FS_ONLY,
    "会計方針": _FS_ONLY,
    "リスク": _RISK_ONLY,
    "地政学": ["risk factors", "management"],
}


def _keyword_match_nodes(question: str, node_map: dict) -> list[str]:
    """質問キーワードからセクションタイトルをマッチして候補ノードIDを返す

    extract_json_objectが失敗したときの堅牢なフォールバック。
    先頭5ノード返却よりもセマンティックに関連する可能性が高い。
    """
    q_lower = question.lower()
    target_sections: set[str] = set()
    for kw, sections in _FALLBACK_KEYWORDS.items():
        if kw.lower() in q_lower:
            target_sections.update(sections)

    matched: list[str] = []
    for nid, node in node_map.items():
        title = node.get("title", "").lower()
        if any(ts in title for ts in target_sections):
            matched.append(nid)

    # マッチなしならItem 7 (MD&A) と Item 8 (Financial Statements) を探索
    if not matched:
        for nid, node in node_map.items():
            title = node.get("title", "").lower()
            if "item 7" in title or "item 8" in title:
                matched.append(nid)

    return matched[:5] if matched else list(node_map.keys())[:5]


def phase0_health():
    """Phase 0: ヘルスチェック（同期ラッパー）"""
    separator("Phase 0: Health Check")
    result = asyncio.run(client.health_check())
    print(f"  Status:   {result['status']}")
    print(f"  Model:    {result['model']}")
    print(f"  Backend:  {result['backend']}")
    print(f"  Base URL: {result['base_url']}")
    if result["status"] != "ok":
        print(f"  Error:    {result.get('error')}")
        sys.exit(1)
    return result


def phase1_build_index(use_cache: bool = False):
    """Phase 1: インデックス構築（同期 — page_index自身がasyncio.run使用）

    use_cache=True かつ cache file があれば構築をスキップしキャッシュを読む。
    """
    separator("Phase 1: Build Index")
    tree_cache_path = _tree_cache_path(PDF_PATH, MODEL, _build_options_for_cache())

    if use_cache and tree_cache_path.exists():
        print(f"  [CACHE] Loading tree from {tree_cache_path}")
        tree = json.loads(tree_cache_path.read_text())
        node_map = collect_node_map(tree)
        structure = tree.get("structure", [])
        print(f"  Sections: {len(structure)}")
        print(f"  Node map: {len(node_map)} entries")
        return tree, 0.0

    from pageindex import page_index
    from pageindex.utils import configure_max_tokens, configure_thinking

    configure_max_tokens(client.max_tokens)
    configure_thinking(False)

    model = client.resolve_model(quality=False)
    print(f"  Model:      {model}")
    print(f"  PDF:        {PDF_PATH}")
    print(f"  max_tokens: {client.max_tokens}")
    print()

    t0 = time.perf_counter()
    tree = page_index(
        PDF_PATH,
        model=model,
        api_base=BASE_URL,
        toc_check_page_num=config.pageindex.toc_check_pages,
        max_page_num_each_node=config.pageindex.max_pages_per_node,
        max_token_num_each_node=config.pageindex.max_tokens_per_node,
        if_add_node_summary="yes" if config.pageindex.add_node_summary else "no",
        if_add_node_text="yes" if config.pageindex.add_node_text else "no",
        max_tokens=client.max_tokens,
    )
    elapsed = time.perf_counter() - t0

    nodes = count_nodes(tree)
    node_map = collect_node_map(tree)
    has_text = any("text" in n for n in node_map.values())
    page_count = tree.get("page_count", 0)

    print("  Result:")
    print(f"    Pages:     {page_count}")
    print(f"    Nodes:     {nodes}")
    print(f"    Node map:  {len(node_map)} entries")
    print(f"    Has text:  {has_text}")
    print(f"    Time:      {elapsed:.1f}s")

    structure = tree.get("structure", [])
    print(f"\n  Top-level sections ({len(structure)}):")
    for i, sec in enumerate(structure):
        title = sec.get("title", "?")
        pi = sec.get("physical_index", sec.get("start_index", "?"))
        children = len(sec.get("nodes", sec.get("children", [])))
        print(f"    [{i:2d}] page={pi}  children={children}  {title}")

    # Save tree for later phases
    tree_cache_path.write_text(json.dumps(tree, ensure_ascii=False))
    print(f"\n  Tree cached to: {tree_cache_path}")

    return tree, elapsed


def phase2_toc_verify(tree: dict):
    """Phase 2: TOC精度検証"""
    separator("Phase 2: TOC Accuracy Verification")

    async def _verify():
        from pageindex.page_index import check_title_appearance
        from pageindex.utils import get_page_tokens

        model = client.resolve_model(quality=False)
        page_list = get_page_tokens(PDF_PATH, model=model)
        print(f"  Total pages: {len(page_list)}")

        node_map = collect_node_map(tree)
        items_to_check = []
        for nid, node in node_map.items():
            pi = node_page(node)
            if pi is not None:
                items_to_check.append(node)

        print(f"  Nodes with page index: {len(items_to_check)}")
        print()

        correct = 0
        incorrect = 0
        errors = []

        for idx, item in enumerate(items_to_check):
            page_num = node_page(item)
            title = item.get("title", "?")

            item_copy = item.copy()
            item_copy["list_index"] = idx
            if "physical_index" not in item_copy:
                item_copy["physical_index"] = page_num

            try:
                result = await check_title_appearance(
                    item_copy, page_list, start_index=1,
                    model=model, api_base=BASE_URL,
                )
                answer = result.get("answer", "no")
            except Exception as e:
                answer = "error"
                errors.append((title, str(e)))

            mark = " OK " if answer == "yes" else "FAIL"
            if answer == "yes":
                correct += 1
            else:
                incorrect += 1
            print(f"  [{idx:2d}] {mark}  page={page_num:>3d}  {title}")

        total = correct + incorrect
        accuracy = correct / total * 100 if total > 0 else 0

        print(f"\n  Result: {correct}/{total} = {accuracy:.1f}%")
        if errors:
            print(f"  Errors: {len(errors)}")
            for t, err in errors:
                print(f"    - {t}: {err}")

        return accuracy, correct, total

    return asyncio.run(_verify())


def phase3_rag_query(tree: dict):
    """Phase 3: RAGクエリ"""
    separator("Phase 3: RAG Query")

    async def _query():
        model = client.resolve_model(quality=True)
        node_map = collect_node_map(tree)
        print(f"  Model:      {model}")
        print(f"  Questions:  {len(RAG_QUESTIONS)}")
        print()

        results = []
        tree_summary = json.dumps(strip_text(tree), indent=2, ensure_ascii=False)

        for qi, qdef in enumerate(RAG_QUESTIONS):
            difficulty = qdef["difficulty"]
            category = qdef["category"]
            question = qdef["question"]
            cfg = DIFFICULTY_SETTINGS[difficulty]
            answer_thinking = cfg["thinking"]
            answer_max_tokens = cfg["max_tokens"]

            print(f"  Q{qi+1} [{difficulty}/{category}] thinking={answer_thinking}")
            print(f"     {question[:100]}{'...' if len(question) > 100 else ''}")
            t0 = time.perf_counter()
            search_prompt = (
                f"以下のドキュメントツリー構造から、質問に回答するために必要なノードを特定してください。\n"
                f"長文把握が必要な質問では複数ノードを選択してください（最大10個）。\n\n"
                f"質問: {question}\n\n"
                f"ドキュメントツリー:\n{tree_summary}\n\n"
                f"JSON形式で回答してください: "
                f'{{"thinking": "理由", "node_list": ["ノードID1", "ノードID2"]}}'
            )
            t_search = time.perf_counter()
            # 検索段階は構造マッチングのため非思考モードで実行
            search_result = await client.completion(
                search_prompt, quality=True, model=model,
                thinking=False, max_tokens=4096,
            )
            search_time = time.perf_counter() - t_search

            parsed = extract_json_object(search_result)
            if parsed is not None:
                node_ids = parsed.get("node_list", [])
                search_thinking = parsed.get("thinking", "")
                search_parse_status = "ok"
            else:
                # 抽出失敗: タイトルキーワードマッチで候補を推定
                node_ids = _keyword_match_nodes(question, node_map)
                search_thinking = "(JSON extract failed, keyword fallback)"
                search_parse_status = "failed"

            context_parts = []
            sections = []
            pages = []
            for nid in node_ids:
                node = node_map.get(nid)
                if node is None:
                    continue
                sections.append(node.get("title", nid))
                page = node_page(node)
                if page is not None:
                    pages.append(page)
                text = node.get("text", node.get("summary", ""))
                if text:
                    context_parts.append(f"[{node.get('title', nid)}]\n{text}")

            context = "\n\n".join(context_parts)
            context_chars = len(context)

            answer_prompt = (
                f"以下のコンテキストに基づいて質問に日本語で回答してください。\n"
                f"長文把握が必要な場合は網羅的に列挙・分類してください。\n\n"
                f"質問: {question}\n\n"
                f"コンテキスト:\n{context}"
            )
            t_answer = time.perf_counter()
            answer = await client.completion(
                answer_prompt, quality=True, model=model,
                thinking=answer_thinking, max_tokens=answer_max_tokens,
            )
            answer_time = time.perf_counter() - t_answer

            total_time = time.perf_counter() - t0

            print(f"     Nodes selected: {node_ids}")
            print(f"     Sections: {sections}")
            print(f"     Pages: {sorted(set(pages))}")
            print(f"     Context: {context_chars:,} chars")
            print(f"     Timing: search={search_time:.1f}s answer={answer_time:.1f}s total={total_time:.1f}s")
            print(f"     Answer: {answer[:300]}{'...' if len(answer) > 300 else ''}")
            print()

            results.append({
                "question": question,
                "difficulty": difficulty,
                "category": category,
                "answer": answer,
                "node_ids": node_ids,
                "sections": sections,
                "pages": sorted(set(pages)),
                "search_raw": search_result,
                "search_thinking": search_thinking,
                "search_parse_status": search_parse_status,
                "context_chars": context_chars,
                "search_time": round(search_time, 2),
                "answer_time": round(answer_time, 2),
                "total_time": round(total_time, 2),
            })

        return results

    return asyncio.run(_query())


def main():
    parser = argparse.ArgumentParser(description="PageIndex RAG Inference Test")
    parser.add_argument(
        "--use-cache", action="store_true",
        help="キャッシュ済みツリーを再利用しPhase 1をスキップ",
    )
    parser.add_argument(
        "--skip-toc", action="store_true",
        help="Phase 2 (TOC検証) をスキップ",
    )
    args = parser.parse_args()

    print("PageIndex RAG Inference Test")
    print(f"Model: {MODEL}")
    print(f"PDF:   {PDF_PATH}")
    print(f"Time:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Use cache: {args.use_cache}  Skip TOC: {args.skip_toc}")

    t_total = time.perf_counter()

    # Phase 0
    phase0_health()

    # Phase 1
    tree, build_time = phase1_build_index(use_cache=args.use_cache)

    # Phase 2
    if args.skip_toc:
        accuracy, correct, total = 0.0, 0, 0
        print("\n[SKIP] Phase 2 TOC verification skipped")
    else:
        accuracy, correct, total = phase2_toc_verify(tree)

    # Phase 3
    query_results = phase3_rag_query(tree)

    total_time = time.perf_counter() - t_total

    # Summary
    separator("Summary")
    print(f"  Model:           {MODEL}")
    print(f"  Index build:     {build_time:.1f}s")
    print(f"  TOC accuracy:    {correct}/{total} = {accuracy:.1f}%")
    print(f"  RAG queries:     {len(query_results)}")
    print()
    print(f"  {'Category':<30} {'Difficulty':<12} {'search':>8} {'answer':>8} {'total':>8}")
    print(f"  {'-' * 70}")
    for r in query_results:
        cat = r["category"][:28]
        diff = r["difficulty"]
        print(f"  {cat:<30} {diff:<12} {r['search_time']:>7.1f}s {r['answer_time']:>7.1f}s {r['total_time']:>7.1f}s")
    print()
    print(f"  Total time:      {total_time:.1f}s ({total_time/60:.1f} min)")

    # Save results
    output = {
        "model": MODEL,
        "pdf": PDF_PATH,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "build_time_s": round(build_time, 2),
        "toc_accuracy": {"correct": correct, "total": total, "pct": round(accuracy, 1)},
        "queries": query_results,
        "total_time_s": round(total_time, 2),
    }
    output_path = Path("data/rag_inference_test_result.json")
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n  Results saved to: {output_path}")

    # 検証レポート (メモリ要件: 各アイテムの詳細)
    ts = time.strftime("%Y%m%d_%H%M%S")
    verification_path = Path(f"data/logs/verification/AAPL_10K_{ts}.json")
    verification_path.parent.mkdir(parents=True, exist_ok=True)
    verification_data = {
        "model": MODEL,
        "pdf": PDF_PATH,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "phase2_toc": {
            "accuracy_pct": round(accuracy, 1),
            "correct": correct,
            "total": total,
        },
        "phase3_rag": {
            "total_queries": len(query_results),
            "by_difficulty": {
                d: sum(1 for r in query_results if r["difficulty"] == d)
                for d in ("basic", "heavy", "long_context")
            },
            "queries": [
                {
                    "index": i,
                    "difficulty": r["difficulty"],
                    "category": r["category"],
                    "question": r["question"],
                    "search_raw": r.get("search_raw", ""),
                    "search_parse_status": r.get("search_parse_status", "?"),
                    "search_thinking": r.get("search_thinking", ""),
                    "selected_node_ids": r["node_ids"],
                    "selected_sections": r["sections"],
                    "selected_pages": r["pages"],
                    "context_chars": r.get("context_chars", 0),
                    "answer_full": r["answer"],
                    "timing": {
                        "search_s": r["search_time"],
                        "answer_s": r["answer_time"],
                        "total_s": r["total_time"],
                    },
                }
                for i, r in enumerate(query_results)
            ],
        },
    }
    verification_path.write_text(
        json.dumps(verification_data, indent=2, ensure_ascii=False),
    )
    print(f"  Verification data: {verification_path}")


if __name__ == "__main__":
    main()
