# tests/unit/ingestion/test_edinet_xbrl_parser.py
"""EDINET XBRL パーサーのテスト"""
import pytest
import yaml
from xml.etree.ElementTree import Element, SubElement, ElementTree

from stock_analyze_system.ingestion.edinet_xbrl_parser import EdinetXbrlParser


@pytest.fixture
def edinet_mapping(tmp_path):
    mapping = {
        "revenue": {
            "jp_gaap": ["jpcrp_cor:NetSalesSummaryOfBusinessResults"],
            "ifrs": ["jppfs_ifrs:Revenue"],
        },
        "net_income": {
            "jp_gaap": ["jpcrp_cor:NetIncomeSummaryOfBusinessResults"],
            "ifrs": ["jppfs_ifrs:ProfitLossAttributableToOwnersOfParent"],
        },
        "total_assets": {
            "jp_gaap": ["jppfs_cor:Assets"],
            "ifrs": ["jppfs_ifrs:Assets"],
        },
    }
    p = tmp_path / "edinet_taxonomy_mapping.yaml"
    p.write_text(yaml.dump(mapping))
    return p


@pytest.fixture
def parser(edinet_mapping):
    return EdinetXbrlParser(mapping_path=str(edinet_mapping))


@pytest.fixture
def sample_xbrl_dir(tmp_path):
    """サンプルXBRLディレクトリを作成"""
    xbrl_dir = tmp_path / "doc_id_123" / "XBRL" / "PublicDoc"
    xbrl_dir.mkdir(parents=True)
    # 最小限のXBRLインスタンス文書を作成
    root = Element("{http://www.xbrl.org/2003/instance}xbrl")
    root.set("xmlns:jpcrp_cor", "http://disclosure.edinet-fsa.go.jp/jpcrp/cor")
    elem = SubElement(root, "{http://disclosure.edinet-fsa.go.jp/jpcrp/cor}NetSalesSummaryOfBusinessResults")
    elem.text = "5000000000"
    elem2 = SubElement(root, "{http://disclosure.edinet-fsa.go.jp/jpcrp/cor}NetIncomeSummaryOfBusinessResults")
    elem2.text = "1000000000"
    xbrl_file = xbrl_dir / "test_instance.xbrl"
    tree = ElementTree(root)
    tree.write(str(xbrl_file), xml_declaration=True, encoding="utf-8")
    return tmp_path / "doc_id_123"


class TestParseXbrlDirectory:
    def test_parse_jp_gaap(self, parser, sample_xbrl_dir):
        result = parser.parse_xbrl_directory(sample_xbrl_dir, accounting_standard="jp_gaap")
        assert result["revenue"] == 5000000000.0
        assert result["net_income"] == 1000000000.0

    def test_parse_missing_field_returns_none(self, parser, sample_xbrl_dir):
        result = parser.parse_xbrl_directory(sample_xbrl_dir, accounting_standard="jp_gaap")
        assert result.get("total_assets") is None

    def test_parse_nonexistent_dir_returns_empty(self, parser, tmp_path):
        result = parser.parse_xbrl_directory(tmp_path / "nonexistent")
        assert result == {} or all(v is None for v in result.values())


class TestDetectAccountingStandard:
    def test_detect_jp_gaap(self, parser, sample_xbrl_dir):
        standard = parser.detect_accounting_standard(sample_xbrl_dir)
        assert standard == "jp_gaap"


class TestConsolidatedStandalone:
    """既知バグ#19修正: XBRLコンテキストで連結/単体を判別"""

    def test_prefers_consolidated(self, parser, tmp_path):
        """連結と単体の両方がある場合、連結を優先する"""
        xbrl_dir = tmp_path / "consolidated_test" / "XBRL" / "PublicDoc"
        xbrl_dir.mkdir(parents=True)
        xbrl_content = '''<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:jpcrp_cor="http://disclosure.edinet-fsa.go.jp/jpcrp/cor">
  <context id="CurrentYearDuration_ConsolidatedMember">
    <entity><identifier>E02144</identifier></entity>
    <period><startDate>2023-04-01</startDate><endDate>2024-03-31</endDate></period>
    <scenario><member>ConsolidatedMember</member></scenario>
  </context>
  <context id="CurrentYearDuration_NonConsolidatedMember">
    <entity><identifier>E02144</identifier></entity>
    <period><startDate>2023-04-01</startDate><endDate>2024-03-31</endDate></period>
    <scenario><member>NonConsolidatedMember</member></scenario>
  </context>
  <jpcrp_cor:NetSalesSummaryOfBusinessResults contextRef="CurrentYearDuration_ConsolidatedMember">8000000000</jpcrp_cor:NetSalesSummaryOfBusinessResults>
  <jpcrp_cor:NetSalesSummaryOfBusinessResults contextRef="CurrentYearDuration_NonConsolidatedMember">3000000000</jpcrp_cor:NetSalesSummaryOfBusinessResults>
</xbrl>'''
        (xbrl_dir / "test.xbrl").write_text(xbrl_content, encoding="utf-8")
        result = parser.parse_xbrl_directory(
            tmp_path / "consolidated_test", accounting_standard="jp_gaap",
        )
        assert result["revenue"] == 8000000000.0

    def test_falls_back_to_standalone(self, parser, tmp_path):
        """単体のみの場合はそれを使用する"""
        xbrl_dir = tmp_path / "standalone_test" / "XBRL" / "PublicDoc"
        xbrl_dir.mkdir(parents=True)
        xbrl_content = '''<?xml version="1.0" encoding="utf-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:jpcrp_cor="http://disclosure.edinet-fsa.go.jp/jpcrp/cor">
  <context id="CurrentYearDuration_NonConsolidatedMember">
    <entity><identifier>E02144</identifier></entity>
    <period><startDate>2023-04-01</startDate><endDate>2024-03-31</endDate></period>
  </context>
  <jpcrp_cor:NetSalesSummaryOfBusinessResults contextRef="CurrentYearDuration_NonConsolidatedMember">3000000000</jpcrp_cor:NetSalesSummaryOfBusinessResults>
</xbrl>'''
        (xbrl_dir / "test.xbrl").write_text(xbrl_content, encoding="utf-8")
        result = parser.parse_xbrl_directory(
            tmp_path / "standalone_test", accounting_standard="jp_gaap",
        )
        assert result["revenue"] == 3000000000.0


class TestResolveValue:
    def test_resolves_numeric(self, parser):
        elements = {"Revenue": "1234567890"}
        result = parser._resolve_value(elements, ["Revenue"])
        assert result == 1234567890.0

    def test_returns_none_for_missing(self, parser):
        result = parser._resolve_value({}, ["NonExistent"])
        assert result is None

    def test_strips_namespace(self, parser):
        elements = {"Revenue": "999"}
        result = parser._resolve_value(elements, ["ns:Revenue"])
        assert result == 999.0

    def test_non_numeric_returns_none(self, parser):
        elements = {"Revenue": "not-a-number"}
        assert parser._resolve_value(elements, ["Revenue"]) is None


class TestParserErrorBranches:
    def test_xml_parse_error_returns_empty(self, parser, tmp_path):
        xbrl_dir = tmp_path / "broken" / "XBRL" / "PublicDoc"
        xbrl_dir.mkdir(parents=True)
        (xbrl_dir / "test.xbrl").write_text("<<< not xml", encoding="utf-8")
        result = parser.parse_xbrl_directory(
            tmp_path / "broken", accounting_standard="jp_gaap",
        )
        assert result == {}

    def test_detect_no_instance_returns_jp_gaap(self, parser, tmp_path):
        """instance doc 不在 → jp_gaap"""
        assert parser.detect_accounting_standard(tmp_path / "empty") == "jp_gaap"

    def test_detect_parse_error_returns_jp_gaap(self, parser, tmp_path):
        """XML パースエラー → jp_gaap fallback"""
        xbrl_dir = tmp_path / "badxml" / "XBRL" / "PublicDoc"
        xbrl_dir.mkdir(parents=True)
        (xbrl_dir / "test.xbrl").write_text("not xml at all", encoding="utf-8")
        assert parser.detect_accounting_standard(tmp_path / "badxml") == "jp_gaap"

    def test_detect_ifrs(self, parser, tmp_path):
        """IFRS ネームスペースを検出"""
        xbrl_dir = tmp_path / "ifrs_doc" / "XBRL" / "PublicDoc"
        xbrl_dir.mkdir(parents=True)
        content = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<xbrl xmlns="http://www.xbrl.org/2003/instance"'
            ' xmlns:ifrs="http://disclosure.edinet-fsa.go.jp/taxonomy/jppfs_ifrs/2024-03-31">'
            '<ifrs:Revenue>1000</ifrs:Revenue>'
            '</xbrl>'
        )
        (xbrl_dir / "test.xbrl").write_text(content, encoding="utf-8")
        assert parser.detect_accounting_standard(tmp_path / "ifrs_doc") == "ifrs"

    def test_skips_manifest_schema(self, parser, tmp_path):
        """manifest/schema 名は除外され rglob fallback"""
        xbrl_dir = tmp_path / "doc" / "XBRL" / "PublicDoc"
        xbrl_dir.mkdir(parents=True)
        (xbrl_dir / "manifest_file.xbrl").write_text("<x/>", encoding="utf-8")
        # PublicDoc 以下には manifest しかない → 122 (continue) → 126 (rglob fallback)
        (tmp_path / "doc" / "nested.xbrl").write_text(
            '<?xml version="1.0"?>'
            '<xbrl xmlns="http://www.xbrl.org/2003/instance"/>',
            encoding="utf-8",
        )
        found = parser._find_instance_document(tmp_path / "doc")
        assert found is not None

    def test_missing_mapping_file(self, tmp_path):
        """マッピングファイルが無い場合は警告のみで空 mapping"""
        p = EdinetXbrlParser(mapping_path=str(tmp_path / "nope.yaml"))
        xbrl_dir = tmp_path / "d" / "XBRL" / "PublicDoc"
        xbrl_dir.mkdir(parents=True)
        (xbrl_dir / "t.xbrl").write_text(
            '<?xml version="1.0"?>'
            '<xbrl xmlns="http://www.xbrl.org/2003/instance">'
            '<revenue>1</revenue></xbrl>',
            encoding="utf-8",
        )
        result = p.parse_xbrl_directory(tmp_path / "d", accounting_standard="jp_gaap")
        # mapping なし→全フィールド欠落 (空 dict)
        assert result == {}

    def test_mapping_non_dict_value(self, tmp_path):
        """mapping で値が dict 以外なら空扱い (163 行目の else 分岐)"""
        p = tmp_path / "map.yaml"
        p.write_text(yaml.dump({"revenue": "not a dict"}))
        parser_ = EdinetXbrlParser(mapping_path=str(p))
        xbrl_dir = tmp_path / "d" / "XBRL" / "PublicDoc"
        xbrl_dir.mkdir(parents=True)
        (xbrl_dir / "t.xbrl").write_text(
            '<?xml version="1.0"?>'
            '<xbrl xmlns="http://www.xbrl.org/2003/instance">'
            '<revenue>1</revenue></xbrl>',
            encoding="utf-8",
        )
        result = parser_.parse_xbrl_directory(tmp_path / "d", accounting_standard="jp_gaap")
        assert result.get("revenue") is None
