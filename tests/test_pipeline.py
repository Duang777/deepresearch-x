from deepresearch_x.adapters.llm import HeuristicLLMProvider
from deepresearch_x.adapters.reader import PageReadResult
from deepresearch_x.adapters.search import MockSearchProvider
from deepresearch_x.config import AppSettings
from deepresearch_x.models import SourceDocument
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


class StaticSearchProvider:
    def search(self, query: str, top_k: int) -> list[SourceDocument]:
        del top_k
        return [
            SourceDocument(
                source_id=f"S{i+1}",
                title=f"Doc {i+1}",
                url=f"https://example.com/doc-{i+1}",
                snippet=f"Snippet for source {i+1} about {query}",
                query=query,
                rank=i + 1,
            )
            for i in range(3)
        ]


class StubReader:
    def read(self, url: str, max_chars: int) -> PageReadResult:
        text = f"Full content extracted for {url}. " + ("x" * 180)
        return PageReadResult(preview_text=text[:max_chars], status="fulltext_direct")


def test_parallel_page_enrichment_keeps_fulltext_status() -> None:
    settings = AppSettings(
        search_provider="mock",
        llm_provider="heuristic",
        enable_page_reader=True,
        page_fetch_workers=3,
        max_page_fetch_per_loop=3,
    )
    pipeline = ResearchPipeline(
        search_provider=StaticSearchProvider(),
        llm_provider=HeuristicLLMProvider(),
        settings=settings,
        page_reader=StubReader(),
    )
    result = pipeline.run(topic="parallel source fetch", loops=1, top_k=3)

    assert result.metrics.source_count == 3
    assert result.metrics.fulltext_source_count == 3
    assert all(src.fetch_status == "fulltext_direct" for src in result.sources)
