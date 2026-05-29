"""RAG定型分析プロンプトテンプレート"""
from __future__ import annotations

ANALYSIS_TYPES: dict[str, dict[str, str]] = {
    "business_summary": {
        "label": "事業概要",
        "prompt": (
            "この企業の有価証券報告書/10-K/20-Fに基づき、事業概要を日本語で構造化してください。\n\n"
            "以下のJSON形式で回答してください:\n"
            "{\n"
            '  "company_name": "企業名",\n'
            '  "industry": "業種",\n'
            '  "business_segments": [\n'
            '    {"name": "セグメント名", "description": "概要", "revenue_share": "売上比率"}\n'
            "  ],\n"
            '  "key_products": ["主要製品/サービス"],\n'
            '  "geographic_presence": ["主要展開地域"],\n'
            '  "employees": "従業員数",\n'
            '  "summary": "200字程度の事業概要"\n'
            "}"
        ),
    },
    "risk_factors": {
        "label": "リスク要因",
        "prompt": (
            "この企業の有価証券報告書/10-Kに記載されているリスク要因を分析してください。\n\n"
            "以下のJSON形式で回答してください:\n"
            "{\n"
            '  "risks": [\n'
            "    {\n"
            '      "category": "カテゴリ（市場/規制/技術/財務/オペレーション）",\n'
            '      "title": "リスク名",\n'
            '      "description": "概要",\n'
            '      "severity": "high/medium/low"\n'
            "    }\n"
            "  ],\n"
            '  "top_risks_summary": "最も重要なリスク3つの要約"\n'
            "}"
        ),
    },
    "mda": {
        "label": "経営者による分析 (MD&A)",
        "prompt": (
            "経営者による財政状態及び経営成績の分析（MD&A）セクションを要約してください。\n\n"
            "以下のJSON形式で回答してください:\n"
            "{\n"
            '  "revenue_analysis": "売上高の動向と要因分析",\n'
            '  "profitability": "利益率の動向",\n'
            '  "cash_flow": "キャッシュフローの状況",\n'
            '  "capital_allocation": "資本配分方針",\n'
            '  "outlook": "業績見通し",\n'
            '  "key_metrics": [\n'
            '    {"metric": "指標名", "current": "当期", "previous": "前期", "change": "変化率"}\n'
            "  ],\n"
            '  "summary": "200字程度のMD&A要約"\n'
            "}"
        ),
    },
    "competitors": {
        "label": "競合分析",
        "prompt": (
            "この企業の競合環境を有価証券報告書/10-Kの記載に基づいて分析してください。\n\n"
            "以下のJSON形式で回答してください:\n"
            "{\n"
            '  "competitive_position": "競合ポジション",\n'
            '  "market_share": "市場シェア（記載があれば）",\n'
            '  "competitors": [\n'
            '    {"name": "競合企業名", "description": "概要"}\n'
            "  ],\n"
            '  "competitive_advantages": ["競合優位性"],\n'
            '  "competitive_risks": ["競合上のリスク"],\n'
            '  "summary": "200字程度の競合分析要約"\n'
            "}"
        ),
    },
}

ANALYSIS_TYPE_NAMES = list(ANALYSIS_TYPES.keys())
