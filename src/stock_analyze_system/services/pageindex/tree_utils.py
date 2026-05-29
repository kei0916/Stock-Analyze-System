"""PageIndex tree 操作の純粋 helper (公開 API)."""
from __future__ import annotations


def count_nodes(tree: dict) -> int:
    """ツリー内のノード数を再帰カウントする (ルートラッパーを除く子ノードのみ).

    PageIndex returns ``{'doc_name': ..., 'structure': [...]}``.
    Each node inside *structure* may have ``'nodes'`` children.
    """
    children = tree.get("structure") or tree.get("nodes") or tree.get("children") or []
    if not children:
        return 0
    count = 0
    for child in children:
        count += 1 + count_nodes(child)
    return count


def collect_node_map(tree: dict, _mapping: dict[str, dict] | None = None) -> dict[str, dict]:
    """ノードIDからノード情報へのマッピングを構築する."""
    if _mapping is None:
        _mapping = {}
    nid = tree.get("id") or tree.get("node_id")
    if nid is not None:
        _mapping[nid] = tree
    for child in tree.get("structure") or tree.get("nodes") or []:
        collect_node_map(child, _mapping)
    return _mapping


def node_page(node: dict) -> int | None:
    """ノードのページインデックスを返す (physical_index 優先、start_index フォールバック)."""
    return node.get("physical_index") or node.get("start_index")


def extract_page_count(tree: dict) -> int:
    """ツリー構造からページ数を推定する (全ノードの max physical_index を使用)."""
    page_count = tree.get("page_count")
    if isinstance(page_count, int):
        return page_count

    max_page = 0

    def _walk(node: dict) -> None:
        nonlocal max_page
        pi = node.get("physical_index") or node.get("start_index")
        if isinstance(pi, int) and pi > max_page:
            max_page = pi
        ei = node.get("end_index")
        if isinstance(ei, int) and ei > max_page:
            max_page = ei
        for child in node.get("structure") or node.get("nodes") or []:
            _walk(child)

    for child in tree.get("structure") or tree.get("nodes") or []:
        _walk(child)
    return max_page


def strip_text(tree: dict) -> dict:
    """ツリーから text フィールドを除去し構造だけ返す (検索用)."""
    result = {k: v for k, v in tree.items() if k not in ("text",)}
    for key in ("structure", "nodes"):
        if key in result:
            result[key] = [strip_text(n) for n in result[key]]
    return result
