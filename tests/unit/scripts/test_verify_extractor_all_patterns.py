import json

from scripts import verify_extractor_all_patterns as verify


EXPECTED_SUMMARY_KEYS = {
    "total",
    "raised_count",
    "expected_input_missing_count",
    "unexpected_raised_count",
    "known_unexpected_missing_count",
    "expected_empty_edge_count",
    "unexpected_missing_count",
    "raised_labels",
    "expected_input_missing_labels",
    "unexpected_raised_labels",
    "known_unexpected_missing_labels",
    "known_unexpected_missing_entries",
    "expected_empty_edge_labels",
    "expected_empty_edge_entries",
    "unexpected_missing_labels",
    "unexpected_missing_entries",
    "real_count",
    "edge_count",
    "real_failures",
    "all_missing_sections",
}


def test_summarise_flags_unallowlisted_missing_sections_as_failures():
    results = [
        {
            "label": "US_NEW FY2026 10-K (filing_id=999)",
            "raised": None,
            "missing_unexpectedly": ["mda"],
        },
    ]

    summary = verify._summarise(results)

    assert summary["unexpected_missing_count"] == 1
    assert summary["unexpected_missing_labels"] == [
        "US_NEW FY2026 10-K (filing_id=999)",
    ]
    assert summary["unexpected_missing_entries"] == [
        {
            "label": "US_NEW FY2026 10-K (filing_id=999)",
            "missing": ["mda"],
        },
    ]
    assert verify._exit_code(summary) == 1


def test_summarise_allows_documented_real_missing_sections():
    results = [
        {
            "label": "US_ABCL FY2025 10-K (filing_id=258)",
            "raised": None,
            "missing_unexpectedly": ["risk_factors"],
        },
    ]

    summary = verify._summarise(results)

    assert summary["known_unexpected_missing_count"] == 1
    assert summary["known_unexpected_missing_labels"] == [
        "US_ABCL FY2025 10-K (filing_id=258)",
    ]
    assert summary["known_unexpected_missing_entries"] == [
        {
            "label": "US_ABCL FY2025 10-K (filing_id=258)",
            "missing": ["risk_factors"],
        },
    ]
    assert summary["unexpected_missing_count"] == 0
    assert verify._exit_code(summary) == 0


def test_summarise_allows_expected_empty_edge_cases():
    results = [
        {
            "label": "edge: raw/ empty HTML",
            "raised": None,
            "missing_unexpectedly": [
                "business_summary",
                "competitors",
                "mda",
                "risk_factors",
            ],
        },
    ]

    summary = verify._summarise(results)

    assert summary["expected_empty_edge_count"] == 1
    assert summary["expected_empty_edge_labels"] == ["edge: raw/ empty HTML"]
    assert summary["expected_empty_edge_entries"] == [
        {
            "label": "edge: raw/ empty HTML",
            "missing": [
                "business_summary",
                "competitors",
                "mda",
                "risk_factors",
            ],
        },
    ]
    assert summary["unexpected_missing_count"] == 0
    assert summary["unexpected_missing_labels"] == []
    assert summary["all_missing_sections"] == [
        {
            "label": "edge: raw/ empty HTML",
            "missing": ["business_summary", "competitors", "mda", "risk_factors"],
        },
    ]
    assert verify._exit_code(summary) == 0


def test_summary_uses_stable_key_set_and_json_shapes():
    results = [
        {
            "label": "US_NEW FY2026 10-K (filing_id=999)",
            "raised": None,
            "missing_unexpectedly": ["mda"],
        },
    ]

    summary = verify._summarise(results)

    assert set(summary) == EXPECTED_SUMMARY_KEYS
    assert summary["all_missing_sections"] == [
        {
            "label": "US_NEW FY2026 10-K (filing_id=999)",
            "missing": ["mda"],
        },
    ]
    assert json.loads(json.dumps(summary))["all_missing_sections"] == summary["all_missing_sections"]


def test_expected_empty_edge_requires_all_analysis_sections_missing():
    results = [
        {
            "label": "edge: raw/ empty HTML",
            "raised": None,
            "missing_unexpectedly": ["mda"],
        },
    ]

    summary = verify._summarise(results)

    assert summary["expected_empty_edge_count"] == 0
    assert summary["expected_empty_edge_labels"] == []
    assert summary["unexpected_missing_count"] == 1
    assert summary["unexpected_missing_entries"] == [
        {"label": "edge: raw/ empty HTML", "missing": ["mda"]},
    ]
    assert verify._exit_code(summary) == 1


def test_summarise_splits_known_and_unknown_missing_for_same_label():
    results = [
        {
            "label": "US_ABCL FY2025 10-K (filing_id=258)",
            "raised": None,
            "missing_unexpectedly": ["risk_factors", "mda"],
        },
    ]

    summary = verify._summarise(results)

    assert summary["known_unexpected_missing_entries"] == [
        {"label": "US_ABCL FY2025 10-K (filing_id=258)", "missing": ["risk_factors"]},
    ]
    assert summary["unexpected_missing_entries"] == [
        {"label": "US_ABCL FY2025 10-K (filing_id=258)", "missing": ["mda"]},
    ]
    assert summary["known_unexpected_missing_labels"] == [
        "US_ABCL FY2025 10-K (filing_id=258)",
    ]
    assert summary["unexpected_missing_labels"] == [
        "US_ABCL FY2025 10-K (filing_id=258)",
    ]
    assert verify._exit_code(summary) == 1


def test_summarise_keeps_expected_raises_out_of_missing_classification():
    results = [
        {
            "label": "edge: storage_path=None",
            "raised": "ExtractionInputMissingError: missing",
            "expected_raise": True,
            "unexpected_raise": False,
            "missing_unexpectedly": ["mda"],
        },
    ]

    summary = verify._summarise(results)

    assert summary["expected_input_missing_count"] == 1
    assert summary["expected_input_missing_labels"] == ["edge: storage_path=None"]
    assert summary["all_missing_sections"] == []
    assert summary["unexpected_missing_count"] == 0
    assert verify._exit_code(summary) == 0


def test_exit_code_fails_for_unexpected_raises_or_missing_sections():
    assert verify._exit_code({
        "unexpected_raised_count": 1,
        "unexpected_missing_count": 0,
    }) == 1
    assert verify._exit_code({
        "unexpected_raised_count": 0,
        "unexpected_missing_count": 1,
    }) == 1
    assert verify._exit_code({
        "unexpected_raised_count": 0,
        "unexpected_missing_count": 0,
    }) == 0

def test_result_prefix_uses_same_classification_as_summary_for_expected_empty_drift():
    result = {
        "label": "edge: raw/ empty HTML",
        "raised": None,
        "missing_unexpectedly": ["mda"],
    }

    assert verify._result_prefix(result) == "MISSING"


def test_result_prefix_marks_full_expected_empty_as_expected_empty():
    result = {
        "label": "edge: raw/ empty HTML",
        "raised": None,
        "missing_unexpectedly": [
            "business_summary",
            "competitors",
            "mda",
            "risk_factors",
        ],
    }

    assert verify._result_prefix(result) == "EXPECTED-EMPTY"
