from deepresearch_x.adapters.llm import HeuristicLLMProvider
from deepresearch_x.adapters.search import MockSearchProvider
from deepresearch_x.config import AppSettings
from deepresearch_x.models import Claim, SourceDocument
from deepresearch_x.pipeline import ResearchPipeline


class FixedSemanticScorer:
    def score(self, query: str, documents: list[str]) -> list[float]:
        del query
        if not documents:
            return []
        return [0.92] + [0.08 for _ in documents[1:]]


def test_excerpt_split_supports_cjk_punctuation() -> None:
    content = (
        "Intro background sentence\u3002Second sentence provides retrieval evidence and benchmark metrics\u3002"
        "Third sentence is less relevant."
    )
    excerpt = ResearchPipeline._best_excerpt_from_content(
        keywords=["retrieval", "benchmark"],
        content=content,
    )
    assert "retrieval evidence" in excerpt.lower()


def test_semantic_alignment_can_recall_low_keyword_source() -> None:
    settings = AppSettings(
        search_provider="mock",
        llm_provider="heuristic",
        enable_page_reader=False,
        enable_semantic_alignment=False,
        semantic_weight=0.8,
        keyword_weight=0.2,
    )
    pipeline = ResearchPipeline(
        search_provider=MockSearchProvider(),
        llm_provider=HeuristicLLMProvider(),
        settings=settings,
    )
    pipeline.semantic_scorer = FixedSemanticScorer()

    claim = Claim(
        claim_id="C1",
        statement="retrieval augmentation memory reliability",
        rationale="needs supporting evidence",
        confidence=0.5,
    )
    sources = [
        SourceDocument(
            source_id="S1",
            title="Context persistence strategy",
            url="https://example.com/context",
            snippet="Long-horizon recall and fact stability patterns in agents.",
            query="test",
            rank=1,
        ),
        SourceDocument(
            source_id="S2",
            title="Irrelevant topic",
            url="https://example.com/other",
            snippet="A generic unrelated article with weak relevance.",
            query="test",
            rank=2,
        ),
    ]

    aligned = pipeline._align_evidence([claim], sources)
    assert len(aligned[0].supporting_sources) == 1
    assert aligned[0].supporting_sources[0].source_id == "S1"
