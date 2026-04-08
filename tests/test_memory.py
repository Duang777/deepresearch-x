from pathlib import Path

from deepresearch_x.adapters.llm import HeuristicLLMProvider
from deepresearch_x.adapters.search import MockSearchProvider
from deepresearch_x.config import AppSettings
from deepresearch_x.memory import InMemoryStore, MemoryService, OpenVikingMemoryAdapter
from deepresearch_x.models import Claim, MemoryFact, SourceAttribution
from deepresearch_x.pipeline import ResearchPipeline


def _claim(statement: str, confidence: float, conflict: bool = False) -> Claim:
    conflict_sources = (
        [
            SourceAttribution(
                source_id="Sx",
                title="conflict",
                url="https://example.com/conflict",
                relevance_score=0.6,
                snippet="conflicting evidence",
            )
        ]
        if conflict
        else []
    )
    return Claim(
        claim_id="C1",
        statement=statement,
        rationale="test rationale",
        supporting_sources=[
            SourceAttribution(
                source_id="S1",
                title="source",
                url="https://example.com",
                relevance_score=0.9,
                snippet="evidence snippet",
            )
        ],
        conflicting_sources=conflict_sources,
        confidence=confidence,
    )


def test_memory_dedup_conflict_and_update() -> None:
    store = InMemoryStore()
    service = MemoryService(default_store=store)

    outcome1 = service.enqueue_claims(
        session_id="sess-a",
        claims=[_claim("A memory fact about retrieval quality.", 0.64)],
        scope="session",
        backend="sqlite",
        wait_ms=500,
    )
    outcome2 = service.enqueue_claims(
        session_id="sess-a",
        claims=[_claim("A memory fact about retrieval quality.", 0.82, conflict=True)],
        scope="session",
        backend="sqlite",
        wait_ms=500,
    )

    memories = service.get_memory(backend="sqlite", session_id="sess-a", scope="session", limit=10)
    assert len(memories) == 1
    assert memories[0].confidence >= 0.82
    assert memories[0].hit_count >= 2
    assert memories[0].conflict is True
    assert outcome1.result.write_count >= 1
    assert outcome2.result.conflict_count >= 1


def test_memory_budget_crops_injection() -> None:
    store = InMemoryStore()
    service = MemoryService(default_store=store)
    facts = [
        MemoryFact(
            memory_id=f"M{i}",
            session_id="sess-budget",
            scope="session",
            fact_text=f"Memory fact {i} " + ("x" * 90),
            confidence=0.9 - i * 0.02,
            source_ids=["S1"],
            tags=["test"],
            created_at="2026-01-01T00:00:00+00:00",
            last_seen_at="2026-01-01T00:00:00+00:00",
            decay_score=0.0,
            conflict=False,
            hit_count=1,
        )
        for i in range(6)
    ]
    store.upsert_facts(facts)

    selected = service.select_for_injection(
        session_id="sess-budget",
        scope="session",
        budget_tokens=80,
        backend="sqlite",
    )
    assert selected.injection_tokens <= 80
    assert 0 < len(selected.facts) < len(facts)


def test_openviking_adapter_fallback_contract() -> None:
    fallback = InMemoryStore()
    fallback.upsert_facts(
        [
            MemoryFact(
                memory_id="m1",
                session_id="sess-fallback",
                scope="session",
                fact_text="fallback fact",
                confidence=0.7,
                source_ids=["S1"],
                tags=["fallback"],
                created_at="2026-01-01T00:00:00+00:00",
                last_seen_at="2026-01-01T00:00:00+00:00",
                decay_score=0.0,
                conflict=False,
                hit_count=1,
            )
        ]
    )
    adapter = OpenVikingMemoryAdapter(
        base_url="http://127.0.0.1:1",
        timeout_seconds=0.2,
        fallback_store=fallback,
    )
    facts = adapter.get_memory(session_id="sess-fallback", scope="session", limit=5)
    assert len(facts) == 1
    result = adapter.upsert_facts(facts)
    assert result.write_count >= 1


def test_pipeline_session_continuity_with_memory(tmp_path: Path) -> None:
    settings = AppSettings(
        search_provider="mock",
        llm_provider="heuristic",
        enable_page_reader=False,
        enable_memory=True,
        memory_backend="sqlite",
        memory_sqlite_path=str(tmp_path / "memory.db"),
        memory_queue_wait_ms=600,
    )
    pipeline = ResearchPipeline.from_settings(settings)
    session_id = "continuity-demo"

    r1 = pipeline.run(
        topic="agent memory design patterns",
        loops=1,
        top_k=4,
        session_id=session_id,
        use_memory=True,
        memory_backend="sqlite",
    )
    r2 = pipeline.run(
        topic="agent memory design patterns",
        loops=1,
        top_k=4,
        session_id=session_id,
        use_memory=True,
        memory_backend="sqlite",
    )
    r3 = pipeline.run(
        topic="agent memory design patterns",
        loops=1,
        top_k=4,
        session_id=session_id,
        use_memory=True,
        memory_backend="openviking",
    )

    assert r1.memory_write_count >= 1
    assert r2.metrics.memory_recall_hits >= 1
    assert r3.metrics.claim_count >= 1
    checkpoints = pipeline.get_session_checkpoints(session_id=session_id, memory_backend="sqlite")
    assert len(checkpoints) >= 2
