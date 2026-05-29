"""scripts/rag_inference_test.py の単体テスト"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "rag_inference_test.py"
    spec = importlib.util.spec_from_file_location("rag_inference_test_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_BASE_OPTS = {
    "toc_check_pages": 20,
    "max_pages_per_node": 8,
    "max_tokens_per_node": 16000,
    "add_node_summary": True,
    "add_node_text": True,
    "max_tokens": 8192,
}
_BASE_ARGS = ("data/aapl.pdf", "model-a", _BASE_OPTS)


class TestTreeCachePath:
    def test_same_args_reuse_same_cache_path(self):
        module = _load_module()
        assert module._tree_cache_path(*_BASE_ARGS) == module._tree_cache_path(*_BASE_ARGS)

    @pytest.mark.parametrize(
        ("varied_args", "label"),
        [
            (("data/msft.pdf", "model-a", _BASE_OPTS), "pdf"),
            (("data/aapl.pdf", "model-b", _BASE_OPTS), "model"),
            (("data/aapl.pdf", "model-a", {**_BASE_OPTS, "max_pages_per_node": 16}), "options"),
        ],
    )
    def test_different_arg_yields_different_cache_path(self, varied_args, label):
        module = _load_module()
        assert module._tree_cache_path(*_BASE_ARGS) != module._tree_cache_path(*varied_args), label

    def test_different_pdf_contents_use_different_cache_path(self, tmp_path):
        """同じ path / model / options でも file 内容が変われば cache key が変わる."""
        module = _load_module()

        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"first content")
        path1 = module._tree_cache_path(pdf, "model-a", _BASE_OPTS)

        pdf.write_bytes(b"second content with different size")
        path2 = module._tree_cache_path(pdf, "model-a", _BASE_OPTS)

        assert path1 != path2

    def test_missing_file_does_not_raise(self):
        """file が存在しなくても cache path 計算は失敗しない."""
        module = _load_module()
        path = module._tree_cache_path("nonexistent/path.pdf", "model-a", _BASE_OPTS)
        assert path.suffix == ".json"
