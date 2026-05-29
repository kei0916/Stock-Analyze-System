# src/stock_analyze_system/ingestion/edinet_xbrl_parser.py
"""EDINET XBRL パーサー"""
from __future__ import annotations

import logging
from pathlib import Path
from defusedxml.ElementTree import parse as safe_xml_parse
from xml.etree.ElementTree import ParseError as XmlParseError

import yaml

logger = logging.getLogger(__name__)

_IFRS_NS_MARKER = "jppfs_ifrs"
_JP_GAAP_NS_MARKER = "jpcrp"


class EdinetXbrlParser:
    """EDINET XBRLファイリングの解析"""

    def __init__(self, mapping_path: str = "config/edinet_taxonomy_mapping.yaml"):
        self._mapping = self._load_mapping(mapping_path)

    def parse_xbrl_directory(
        self,
        xbrl_dir: str | Path,
        accounting_standard: str = "jp_gaap",
    ) -> dict:
        """XBRLディレクトリから財務データを抽出"""
        xbrl_dir = Path(xbrl_dir)
        instance_doc = self._find_instance_document(xbrl_dir)
        if instance_doc is None:
            logger.warning("No XBRL instance document found in %s", xbrl_dir)
            return {}

        try:
            tree = safe_xml_parse(str(instance_doc))
        except XmlParseError as e:
            logger.error("Failed to parse XBRL: %s", e)
            return {}

        # コンテキスト解析: 連結/単体を判別
        # contextRef に "Consolidated" を含むものを連結、
        # "NonConsolidated" を含むものを単体と判定
        consolidated_values: dict[str, str] = {}
        standalone_values: dict[str, str] = {}
        no_context_values: dict[str, str] = {}

        for elem in tree.iter():
            tag = elem.tag
            if "}" in tag:
                local_name = tag.split("}")[-1]
            else:
                local_name = tag
            if not (elem.text and elem.text.strip()):
                continue
            text = elem.text.strip()
            context_ref = elem.get("contextRef", "")
            if "NonConsolidated" in context_ref:
                standalone_values[local_name] = text
            elif "Consolidated" in context_ref:
                consolidated_values[local_name] = text
            else:
                no_context_values[local_name] = text

        # 連結優先: consolidated > no_context > standalone
        element_values: dict[str, str] = {}
        element_values.update(standalone_values)
        element_values.update(no_context_values)
        element_values.update(consolidated_values)

        # accounting_standard の正規化
        std_key = accounting_standard.lower().replace("-", "_")

        result: dict[str, float | None] = {}
        for field_name, standards in self._mapping.items():
            if not isinstance(standards, dict):
                result[field_name] = None
                continue
            candidates = standards.get(std_key, [])
            if not candidates:
                result[field_name] = None
                continue
            result[field_name] = self._resolve_value(element_values, candidates)

        return result

    def detect_accounting_standard(self, xbrl_dir: str | Path) -> str:
        """会計基準を自動判別"""
        xbrl_dir = Path(xbrl_dir)
        instance_doc = self._find_instance_document(xbrl_dir)
        if instance_doc is None:
            return "jp_gaap"

        try:
            tree = safe_xml_parse(str(instance_doc))
        except XmlParseError:
            return "jp_gaap"

        namespaces: set[str] = set()
        for elem in tree.iter():
            if "}" in elem.tag:
                ns = elem.tag.split("}")[0].strip("{")
                namespaces.add(ns)

        for ns in namespaces:
            if _IFRS_NS_MARKER in ns:
                return "ifrs"
        return "jp_gaap"

    @staticmethod
    def _find_instance_document(xbrl_dir: Path) -> Path | None:
        """XBRLインスタンス文書を探索"""
        preferred_dirs = [xbrl_dir / "XBRL" / "PublicDoc", xbrl_dir]
        for search_dir in preferred_dirs:
            if not search_dir.exists():
                continue
            for ext in ("*.xbrl", "*.xml"):
                for candidate in search_dir.glob(ext):
                    name_lower = candidate.name.lower()
                    if "manifest" in name_lower or "schema" in name_lower:
                        continue
                    return candidate
        # フォールバック: 再帰探索
        for candidate in xbrl_dir.rglob("*.xbrl"):
            return candidate
        return None

    @staticmethod
    def _resolve_value(
        element_values: dict[str, str],
        candidates: list[str],
    ) -> float | None:
        """候補タグから値を解決"""
        for candidate in candidates:
            # namespace prefix を除去
            local_name = candidate.split(":")[-1] if ":" in candidate else candidate
            text = element_values.get(local_name)
            if text is not None:
                try:
                    return float(text)
                except (ValueError, TypeError):
                    continue
        return None

    @staticmethod
    def _load_mapping(mapping_path: str) -> dict:
        """マッピングYAMLを読み込み"""
        path = Path(mapping_path)
        if not path.exists():
            logger.warning("EDINET mapping file not found: %s", path)
            return {}
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        result: dict = {}
        for field_name, standards in data.items():
            if isinstance(standards, dict):
                result[field_name] = {
                    k: v if isinstance(v, list) else []
                    for k, v in standards.items()
                }
            else:
                result[field_name] = {}
        return result
