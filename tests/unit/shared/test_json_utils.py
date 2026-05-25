"""shared/json_utils のユニットテスト"""
from stock_analyze_system.shared.json_utils import (
    extract_json_object,
    json_safe,
    json_dumps_ja,
    safe_json_loads,
)


class TestSafeJsonLoads:
    def test_valid_json(self):
        result = safe_json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_invalid_json_fallback(self):
        result = safe_json_loads("not json")
        assert result == {"raw_answer": "not json"}

    def test_custom_fallback_key(self):
        result = safe_json_loads("bad", fallback_key="text")
        assert result == {"text": "bad"}

    def test_empty_string(self):
        result = safe_json_loads("")
        assert result == {"raw_answer": ""}


class TestJsonDumpsJa:
    def test_japanese_not_escaped(self):
        result = json_dumps_ja({"msg": "日本語"})
        assert "日本語" in result
        assert "\\u" not in result

    def test_indent(self):
        result = json_dumps_ja({"a": 1}, indent=2)
        assert "\n" in result

    def test_no_indent(self):
        result = json_dumps_ja({"a": 1})
        assert "\n" not in result

    def test_default_handler(self):
        from datetime import date
        result = json_dumps_ja({"d": date(2025, 1, 1)}, default=str)
        assert "2025-01-01" in result


class TestJsonSafe:
    def test_json_safe_recursively_converts_non_finite_numbers_to_none(self):
        data = {
            "finite": 1.25,
            "positive_inf": float("inf"),
            "negative_inf": float("-inf"),
            "nan": float("nan"),
            "nested": [{"ok": 2, "bad": float("nan")}],
            "label": "keep",
        }

        result = json_safe(data)

        assert result == {
            "finite": 1.25,
            "positive_inf": None,
            "negative_inf": None,
            "nan": None,
            "nested": [{"ok": 2, "bad": None}],
            "label": "keep",
        }


class TestExtractJsonObject:
    def test_direct_valid_json(self):
        result = extract_json_object('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_code_block_json_tag(self):
        text = '```json\n{"thinking": "reason", "node_list": ["0012"]}\n```'
        result = extract_json_object(text)
        assert result == {"thinking": "reason", "node_list": ["0012"]}

    def test_markdown_code_block_no_tag(self):
        text = '```\n{"a": 1, "b": 2}\n```'
        result = extract_json_object(text)
        assert result == {"a": 1, "b": 2}

    def test_json_embedded_in_prose(self):
        text = 'ここに結果があります:\n{"answer": "yes", "score": 42}\nお疲れ様でした。'
        result = extract_json_object(text)
        assert result == {"answer": "yes", "score": 42}

    def test_markdown_block_preferred_over_braces(self):
        """コードブロック内を優先し、周囲の{}を誤取得しない"""
        text = 'NG例:{bad}\n```json\n{"good": true}\n```\n{not this}'
        result = extract_json_object(text)
        assert result == {"good": True}

    def test_balanced_json_object_extracted_before_trailing_braces(self):
        text = '補足: {参考情報}\n{"answer": "yes", "score": 42}\n後続メモ: {draft}'
        result = extract_json_object(text)
        assert result == {"answer": "yes", "score": 42}

    def test_empty_string(self):
        assert extract_json_object("") is None

    def test_no_json_at_all(self):
        assert extract_json_object("This has no JSON whatsoever.") is None

    def test_malformed_json_returns_none(self):
        assert extract_json_object('{"broken": ,}') is None

    def test_non_dict_json_returns_none(self):
        """配列のみのJSONはNone（dictのみ受け付ける）"""
        assert extract_json_object('[1, 2, 3]') is None

    def test_japanese_content(self):
        text = '```json\n{"回答": "はい", "理由": "文書に記載"}\n```'
        result = extract_json_object(text)
        assert result == {"回答": "はい", "理由": "文書に記載"}
