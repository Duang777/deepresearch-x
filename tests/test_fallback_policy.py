import pytest

from deepresearch_x.adapters.llm import HeuristicLLMProvider
from deepresearch_x.adapters.search import MockSearchProvider
from deepresearch_x.config import AppSettings
from deepresearch_x.models import Claim, SourceDocument
from deepresearch_x.pipeline import ResearchPipeline


class FailingSearchProvider:
    def search(self, query: str, top_k: int) -> list[SourceDocument]:
        raise RuntimeError("search backend unavailable")


class FailingLLMProvider:
    def extract_claims(
        self,
        topic: str,
        sources: list[SourceDocument],
        memory_context: str = "",
    ) -> list[Claim]:
        raise RuntimeError("llm extraction unavailable")

    def synthesize_report(
        self,
        topic: str,
        claims: list[Claim],
        memory_context: str = "",
    ) -> str:
        raise RuntimeError("llm synthesis unavailable")


def test_search_failure_raises_when_mock_fallback_disabled() -> None:
    settings = AppSettings(
        search_provider="duckduckgo",
        llm_provider="heuristic",
        enable_page_reader=False,
        allow_search_mock_fallback=False,
    )
    pipeline = ResearchPipeline(
        search_provider=FailingSearchProvider(),
        llm_provider=HeuristicLLMProvider(),
        settings=settings,
    )

    with pytest.raises(RuntimeError, match="mock fallback is disabled"):
        pipeline.run(topic="strict fallback policy", loops=1, top_k=3)


def test_search_failure_degrades_when_mock_fallback_enabled() -> None:
    settings = AppSettings(
        search_provider="duckduckgo",
        llm_provider="heuristic",
        enable_page_reader=False,
        allow_search_mock_fallback=True,
    )
    pipeline = ResearchPipeline(
        search_provider=FailingSearchProvider(),
        llm_provider=HeuristicLLMProvider(),
        settings=settings,
    )

    result = pipeline.run(topic="search fallback demo", loops=1, top_k=3)

    assert result.degraded_mode is True
    assert any("search_fallback" in reason for reason in result.degraded_reasons)
    assert result.metrics.degraded_fallback_count >= 1
    assert any(source.is_mock for source in result.sources)


def test_llm_failure_raises_when_heuristic_fallback_disabled() -> None:
    settings = AppSettings(
        search_provider="mock",
        llm_provider="openai",
        enable_page_reader=False,
        allow_llm_heuristic_fallback=False,
    )
    pipeline = ResearchPipeline(
        search_provider=MockSearchProvider(),
        llm_provider=FailingLLMProvider(),
        settings=settings,
    )

    with pytest.raises(RuntimeError, match="heuristic fallback is disabled"):
        pipeline.run(topic="llm strict policy", loops=1, top_k=3)


def test_llm_failure_degrades_when_heuristic_fallback_enabled() -> None:
    settings = AppSettings(
        search_provider="mock",
        llm_provider="openai",
        enable_page_reader=False,
        allow_llm_heuristic_fallback=True,
    )
    pipeline = ResearchPipeline(
        search_provider=MockSearchProvider(),
        llm_provider=FailingLLMProvider(),
        settings=settings,
    )

    result = pipeline.run(topic="llm fallback demo", loops=1, top_k=3)

    assert result.degraded_mode is True
    assert any("heuristic_extract" in reason for reason in result.degraded_reasons)
    assert any("heuristic_report" in reason for reason in result.degraded_reasons)
    assert result.metrics.claim_count >= 1
