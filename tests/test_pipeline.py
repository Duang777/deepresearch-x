from deepresearch_x.adapters.llm import HeuristicLLMProvider
from deepresearch_x.adapters.search import MockSearchProvider
from deepresearch_x.config import AppSettings
from deepresearch_x.pipeline import ResearchPipeline


def test_pipeline_returns_claims_and_metrics() -> None:
    settings = AppSettings(search_provider="mock", llm_provider="heuristic")
    pipeline = ResearchPipeline(
        search_provider=MockSearchProvider(),
        llm_provider=HeuristicLLMProvider(),
        settings=settings,
    )

    result = pipeline.run(topic="deep research agent architecture", loops=2, top_k=5)

    assert result.topic
    assert result.session_id
    assert result.metrics.source_count >= 5
    assert result.metrics.claim_count >= 1
    assert result.metrics.estimated_tokens > 0
    assert result.metrics.source_fetch_elapsed_ms == 0
    assert result.metrics.fulltext_source_count == 0
    assert result.metrics.memory_injection_tokens >= 0
    assert len(result.steps) == 2
    assert result.final_claims[0].supporting_sources[0].evidence_origin in {"snippet", "fulltext"}
