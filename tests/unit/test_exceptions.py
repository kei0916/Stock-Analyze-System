"""例外階層のテスト"""
from stock_analyze_system.exceptions import (
    StockAnalyzeError,
    ConfigError,
    IngestionError,
    RateLimitError,
    ApiConnectionError,
    ApiResponseError,
    ParsingError,
    LlmError,
    LlmConnectionError,
    LlmResponseError,
    IndexBuildError,
    AnalysisFailedError,
    NotFoundError,
    DuplicateError,
)


def test_all_exceptions_inherit_from_base():
    for exc_class in [
        ConfigError, IngestionError, ParsingError,
        LlmError, NotFoundError, DuplicateError,
    ]:
        assert issubclass(exc_class, StockAnalyzeError)


def test_ingestion_subclasses():
    for exc_class in [RateLimitError, ApiConnectionError, ApiResponseError]:
        assert issubclass(exc_class, IngestionError)
        assert issubclass(exc_class, StockAnalyzeError)


def test_llm_subclasses():
    for exc_class in [
        LlmConnectionError,
        LlmResponseError,
        IndexBuildError,
        AnalysisFailedError,
    ]:
        assert issubclass(exc_class, LlmError)
        assert issubclass(exc_class, StockAnalyzeError)


def test_exception_message():
    err = NotFoundError("Company US_AAPL not found")
    assert str(err) == "Company US_AAPL not found"
    assert isinstance(err, StockAnalyzeError)


def test_analysis_failed_error_carries_failed_types():
    err = AnalysisFailedError([
        {"type": "mda", "message": "timeout"},
    ])
    assert err.failed_types[0]["type"] == "mda"
    assert "mda" in str(err)


def test_index_build_error_carries_diagnostic_dict():
    err = IndexBuildError(
        "empty TOC from LLM",
        diagnostic={
            "finish_reason": "max_output_reached",
            "content_head": "<think>",
            "model": "test-model",
        },
    )
    assert err.diagnostic == {
        "finish_reason": "max_output_reached",
        "content_head": "<think>",
        "model": "test-model",
    }
    assert "empty TOC from LLM" in str(err)


def test_index_build_error_diagnostic_defaults_to_none():
    err = IndexBuildError("PageIndex is not available")
    assert err.diagnostic is None
    assert "PageIndex is not available" in str(err)
