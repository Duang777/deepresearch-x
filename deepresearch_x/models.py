from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    source_id: str
    title: str
    url: str
    snippet: str
    query: str
    rank: int
    is_mock: bool = False
    content_preview: str = ""
    fetch_status: str = "snippet_only"
    fetch_error: str = ""


class SourceAttribution(BaseModel):
    source_id: str
    title: str
    url: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    snippet: str
    evidence_origin: str = "snippet"


class Claim(BaseModel):
    claim_id: str
    statement: str
    rationale: str
    supporting_sources: List[SourceAttribution] = Field(default_factory=list)
    conflicting_sources: List[SourceAttribution] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ResearchStep(BaseModel):
    loop_index: int
    query: str
    new_sources: int
    total_sources: int
    claims: List[Claim] = Field(default_factory=list)
    elapsed_ms: int


class PipelineMetrics(BaseModel):
    total_elapsed_ms: int
    retrieval_elapsed_ms: int
    source_fetch_elapsed_ms: int
    claim_elapsed_ms: int
    report_elapsed_ms: int
    estimated_tokens: int
    estimated_cost_usd: float
    source_count: int
    fulltext_source_count: int
    claim_count: int
    memory_recall_hits: int = 0
    memory_injection_tokens: int = 0
    memory_queue_latency_ms: int = 0
    degraded_fallback_count: int = 0


class MemoryFact(BaseModel):
    memory_id: str
    session_id: str
    scope: Literal["session", "global"]
    fact_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_ids: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_at: str
    last_seen_at: str
    decay_score: float = Field(ge=0.0, le=1.0, default=0.0)
    conflict: bool = False
    hit_count: int = 1


class SessionCheckpoint(BaseModel):
    checkpoint_id: str
    session_id: str
    run_id: str
    topic: str
    loops: int
    source_count: int
    claim_count: int
    memory_snapshot_count: int
    created_at: str
    metrics: dict


class MemoryUpsertResult(BaseModel):
    write_count: int = 0
    conflict_count: int = 0


class ResearchRunResult(BaseModel):
    run_id: str
    topic: str
    loops: int
    report_markdown: str
    steps: List[ResearchStep]
    final_claims: List[Claim]
    sources: List[SourceDocument]
    metrics: PipelineMetrics
    session_id: str
    memory_used_count: int = 0
    memory_write_count: int = 0
    memory_conflict_count: int = 0
    degraded_mode: bool = False
    degraded_reasons: List[str] = Field(default_factory=list)


class ResearchRequest(BaseModel):
    topic: str = Field(min_length=4, max_length=400)
    loops: int = Field(default=3, ge=1, le=6)
    top_k: int = Field(default=6, ge=3, le=10)
    session_id: str = Field(default="")
    use_memory: bool = True
    memory_backend: Literal["sqlite", "openviking"] = "sqlite"
    memory_budget_tokens: int = Field(default=280, ge=64, le=2000)
    memory_scope: Literal["session", "global", "hybrid"] = "hybrid"
