from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, Iterable, List

from deepresearch_x.adapters.llm import HeuristicLLMProvider, LLMProvider, OpenAIProvider
from deepresearch_x.adapters.reader import HybridPageReader
from deepresearch_x.adapters.search import DuckDuckGoSearchProvider, MockSearchProvider, SearchProvider
from deepresearch_x.config import AppSettings
from deepresearch_x.memory import InMemoryStore, MemoryService, OpenVikingMemoryAdapter, SQLiteStore
from deepresearch_x.models import (
    Claim,
    MemoryFact,
    PipelineMetrics,
    ResearchRunResult,
    ResearchStep,
    SessionCheckpoint,
    SourceAttribution,
    SourceDocument,
)

logger = logging.getLogger("deepresearch_x.pipeline")


STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "are",
    "was",
    "were",
    "have",
    "has",
    "will",
    "into",
    "when",
    "where",
    "many",
    "more",
    "your",
    "about",
    "without",
    "their",
}

CONTRADICTION_MARKERS = (
    "no evidence",
    "unclear",
    "disputed",
    "uncertain",
    "conflicting",
    "cannot verify",
)


@dataclass
class StageTimers:
    retrieval_ms: int = 0
    source_fetch_ms: int = 0
    claim_ms: int = 0
    report_ms: int = 0


class ResearchPipeline:
    def __init__(
        self,
        search_provider: SearchProvider,
        llm_provider: LLMProvider,
        settings: AppSettings,
        page_reader: HybridPageReader | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self.search_provider = search_provider
        self.llm_provider = llm_provider
        self.settings = settings
        self.page_reader = page_reader
        self.memory_service = memory_service or MemoryService(default_store=InMemoryStore())

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "ResearchPipeline":
        search_provider: SearchProvider
        if settings.search_provider.lower() == "duckduckgo":
            search_provider = DuckDuckGoSearchProvider()
        else:
            search_provider = MockSearchProvider()

        llm_provider: LLMProvider
        if settings.llm_provider.lower() == "openai":
            llm_provider = OpenAIProvider(settings.openai_model)
        else:
            llm_provider = HeuristicLLMProvider()

        page_reader = (
            HybridPageReader(timeout_seconds=settings.reader_timeout_seconds)
            if settings.enable_page_reader
            else None
        )

        sqlite_store = SQLiteStore(settings.memory_sqlite_path)
        openviking_store = OpenVikingMemoryAdapter(
            base_url=settings.openviking_base_url,
            timeout_seconds=settings.openviking_timeout_seconds,
            fallback_store=sqlite_store,
        )
        memory_service = MemoryService(default_store=sqlite_store, openviking_store=openviking_store)

        return cls(
            search_provider=search_provider,
            llm_provider=llm_provider,
            settings=settings,
            page_reader=page_reader,
            memory_service=memory_service,
        )

    def run(
        self,
        topic: str,
        loops: int,
        top_k: int,
        session_id: str = "",
        use_memory: bool | None = None,
        memory_budget_tokens: int | None = None,
        memory_scope: str | None = None,
        memory_backend: str = "",
    ) -> ResearchRunResult:
        run_id = str(uuid.uuid4())[:8]
        active_session_id = session_id.strip() or str(uuid.uuid4())[:10]
        active_use_memory = self.settings.enable_memory if use_memory is None else use_memory
        active_scope = (memory_scope or self.settings.memory_scope).lower()
        active_backend = (memory_backend or self.settings.memory_backend).lower()
        if active_scope not in {"session", "global", "hybrid"}:
            active_scope = "hybrid"
        if active_backend not in {"sqlite", "openviking"}:
            active_backend = "sqlite"
        active_budget = memory_budget_tokens or self.settings.memory_budget_tokens
        self._log_event(
            "run_start",
            run_id=run_id,
            session_id=active_session_id,
            loops=loops,
            top_k=top_k,
            search_provider=self.settings.search_provider,
            llm_provider=self.settings.llm_provider,
            memory_backend=active_backend,
            memory_scope=active_scope,
            use_memory=active_use_memory,
        )

        total_start = time.perf_counter()
        stage = StageTimers()
        all_sources: "OrderedDict[str, SourceDocument]" = OrderedDict()
        steps: List[ResearchStep] = []
        latest_claims: List[Claim] = []
        memory_context = ""
        memory_facts: List[MemoryFact] = []
        memory_tokens = 0
        degraded_reasons: List[str] = []
        heuristic_fallback = HeuristicLLMProvider()

        if active_use_memory:
            selection = self.memory_service.select_for_injection(
                session_id=active_session_id,
                scope=active_scope,
                budget_tokens=active_budget,
                backend=active_backend,
            )
            memory_facts = selection.facts
            memory_context = selection.context_text
            memory_tokens = selection.injection_tokens

        for loop_idx in range(loops):
            query = self._build_query(
                topic=topic,
                loop_idx=loop_idx,
                latest_claims=latest_claims,
                memory_facts=memory_facts,
            )
            retrieval_start = time.perf_counter()
            try:
                fetched = self.search_provider.search(query=query, top_k=top_k)
            except Exception as exc:
                if (
                    self.settings.allow_search_mock_fallback
                    and self.settings.search_provider.lower() != "mock"
                ):
                    fetched = MockSearchProvider().search(query=query, top_k=top_k)
                    self._append_degraded_reason(
                        degraded_reasons,
                        f"search_fallback:{self.settings.search_provider.lower()}->mock:{exc.__class__.__name__}",
                    )
                else:
                    raise RuntimeError(
                        "Search provider failed and mock fallback is disabled."
                    ) from exc
            stage.retrieval_ms += int((time.perf_counter() - retrieval_start) * 1000)

            new_sources: List[SourceDocument] = []
            for source in fetched:
                if source.url not in all_sources:
                    all_sources[source.url] = source
                    new_sources.append(source)

            if self.page_reader and new_sources:
                fetch_start = time.perf_counter()
                for source in new_sources[: self.settings.max_page_fetch_per_loop]:
                    if source.is_mock:
                        if not source.content_preview:
                            source.content_preview = source.snippet
                        source.fetch_status = "fulltext_mock"
                        continue
                    read_result = self.page_reader.read(
                        url=source.url,
                        max_chars=self.settings.max_page_chars,
                    )
                    source.fetch_status = read_result.status
                    source.fetch_error = read_result.error[:220]
                    if read_result.preview_text:
                        source.content_preview = read_result.preview_text
                stage.source_fetch_ms += int((time.perf_counter() - fetch_start) * 1000)

            claim_start = time.perf_counter()
            try:
                extracted = self.llm_provider.extract_claims(
                    topic=topic,
                    sources=list(all_sources.values()),
                    memory_context=memory_context,
                )
            except Exception as exc:
                if (
                    self.settings.allow_llm_heuristic_fallback
                    and self.settings.llm_provider.lower() == "openai"
                ):
                    extracted = heuristic_fallback.extract_claims(
                        topic=topic,
                        sources=list(all_sources.values()),
                        memory_context=memory_context,
                    )
                    self._append_degraded_reason(
                        degraded_reasons,
                        f"llm_fallback:openai->heuristic_extract:{exc.__class__.__name__}",
                    )
                else:
                    raise RuntimeError(
                        "LLM claim extraction failed and heuristic fallback is disabled."
                    ) from exc
            aligned = self._align_evidence(extracted, list(all_sources.values()))
            stage.claim_ms += int((time.perf_counter() - claim_start) * 1000)
            latest_claims = aligned

            steps.append(
                ResearchStep(
                    loop_index=loop_idx + 1,
                    query=query,
                    new_sources=len(fetched),
                    total_sources=len(all_sources),
                    claims=aligned,
                    elapsed_ms=stage.retrieval_ms + stage.source_fetch_ms + stage.claim_ms,
                )
            )

        report_start = time.perf_counter()
        try:
            report = self.llm_provider.synthesize_report(
                topic=topic,
                claims=latest_claims,
                memory_context=memory_context,
            )
        except Exception as exc:
            if (
                self.settings.allow_llm_heuristic_fallback
                and self.settings.llm_provider.lower() == "openai"
            ):
                report = heuristic_fallback.synthesize_report(
                    topic=topic,
                    claims=latest_claims,
                    memory_context=memory_context,
                )
                self._append_degraded_reason(
                    degraded_reasons,
                    f"llm_fallback:openai->heuristic_report:{exc.__class__.__name__}",
                )
            else:
                raise RuntimeError(
                    "LLM report synthesis failed and heuristic fallback is disabled."
                ) from exc
        stage.report_ms = int((time.perf_counter() - report_start) * 1000)

        memory_write_count = 0
        memory_conflict_count = 0
        memory_queue_latency_ms = 0
        memory_compact_removed = 0
        if active_use_memory:
            outcome = self.memory_service.enqueue_claims(
                session_id=active_session_id,
                claims=latest_claims,
                scope=active_scope,
                backend=active_backend,
                wait_ms=self.settings.memory_queue_wait_ms,
            )
            memory_write_count = outcome.result.write_count
            memory_conflict_count = outcome.result.conflict_count
            memory_queue_latency_ms = outcome.elapsed_ms
            memory_compact_removed = self.memory_service.compact(
                backend=active_backend,
                ttl_hours=self.settings.memory_ttl_hours,
                max_session_facts=self.settings.memory_max_session_facts,
                max_global_facts=self.settings.memory_max_global_facts,
            )

        total_elapsed_ms = int((time.perf_counter() - total_start) * 1000)
        estimated_tokens = self._estimate_tokens(topic, all_sources.values(), latest_claims, report)
        estimated_cost = self._estimate_cost(estimated_tokens)

        metrics = PipelineMetrics(
            total_elapsed_ms=total_elapsed_ms,
            retrieval_elapsed_ms=stage.retrieval_ms,
            source_fetch_elapsed_ms=stage.source_fetch_ms,
            claim_elapsed_ms=stage.claim_ms,
            report_elapsed_ms=stage.report_ms,
            estimated_tokens=estimated_tokens,
            estimated_cost_usd=round(estimated_cost, 4),
            source_count=len(all_sources),
            fulltext_source_count=len(
                [s for s in all_sources.values() if s.fetch_status.startswith("fulltext")]
            ),
            claim_count=len(latest_claims),
            memory_recall_hits=len(memory_facts),
            memory_injection_tokens=memory_tokens,
            memory_queue_latency_ms=memory_queue_latency_ms,
            degraded_fallback_count=len(degraded_reasons),
            memory_compact_removed=memory_compact_removed,
        )

        memory_snapshot = (
            self.memory_service.get_memory(
                backend=active_backend,
                session_id=active_session_id,
                scope=active_scope,
                limit=80,
            )
            if active_use_memory
            else []
        )

        checkpoint = SessionCheckpoint(
            checkpoint_id=str(uuid.uuid4()),
            session_id=active_session_id,
            run_id=run_id,
            topic=topic,
            loops=loops,
            source_count=len(all_sources),
            claim_count=len(latest_claims),
            memory_snapshot_count=len(memory_snapshot),
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            metrics=metrics,
        )
        self.memory_service.save_checkpoint(backend=active_backend, checkpoint=checkpoint)

        self._log_event(
            "run_finish",
            run_id=run_id,
            session_id=active_session_id,
            degraded_mode=bool(degraded_reasons),
            degraded_reasons=degraded_reasons,
            source_count=metrics.source_count,
            claim_count=metrics.claim_count,
            latency_ms=metrics.total_elapsed_ms,
            est_cost=metrics.estimated_cost_usd,
            compact_removed=metrics.memory_compact_removed,
        )

        return ResearchRunResult(
            run_id=run_id,
            topic=topic,
            loops=loops,
            report_markdown=report,
            steps=steps,
            final_claims=latest_claims,
            sources=list(all_sources.values()),
            metrics=metrics,
            session_id=active_session_id,
            memory_used_count=len(memory_facts),
            memory_write_count=memory_write_count,
            memory_conflict_count=memory_conflict_count,
            degraded_mode=bool(degraded_reasons),
            degraded_reasons=degraded_reasons,
        )

    def get_session_checkpoints(
        self,
        session_id: str,
        memory_backend: str = "",
        limit: int = 20,
    ) -> List[SessionCheckpoint]:
        backend = (memory_backend or self.settings.memory_backend).lower()
        if backend not in {"sqlite", "openviking"}:
            backend = "sqlite"
        return self.memory_service.get_checkpoints(backend=backend, session_id=session_id, limit=limit)

    def get_session_memory(
        self,
        session_id: str,
        memory_backend: str = "",
        memory_scope: str = "hybrid",
        limit: int = 40,
    ) -> List[MemoryFact]:
        backend = (memory_backend or self.settings.memory_backend).lower()
        if backend not in {"sqlite", "openviking"}:
            backend = "sqlite"
        scope = memory_scope if memory_scope in {"session", "global", "hybrid"} else "hybrid"
        return self.memory_service.get_memory(
            backend=backend,
            session_id=session_id,
            scope=scope,
            limit=limit,
        )

    def _build_query(
        self,
        topic: str,
        loop_idx: int,
        latest_claims: List[Claim],
        memory_facts: List[MemoryFact],
    ) -> str:
        if loop_idx == 0:
            if memory_facts:
                memory_hint = memory_facts[0].fact_text[:72]
                return f"{topic} latest trends evidence {memory_hint}"
            return f"{topic} latest trends evidence"
        if not latest_claims:
            return f"{topic} verification contradictory evidence"
        sorted_claims = sorted(latest_claims, key=lambda c: c.confidence, reverse=True)
        top_claims = sorted_claims[:2]
        anchors = []
        for claim in top_claims:
            key_terms = self._keywords(f"{claim.statement} {claim.rationale}")[:4]
            if key_terms:
                anchors.append(" ".join(key_terms))
            else:
                anchors.append(claim.statement[:80])
        conflict_hint = "resolve contradiction" if any(c.conflicting_sources for c in top_claims) else "verify evidence"
        return f"{topic} {conflict_hint} {' '.join(anchors)}"

    def _align_evidence(self, claims: List[Claim], sources: List[SourceDocument]) -> List[Claim]:
        aligned_claims: List[Claim] = []
        for claim in claims:
            keywords = self._keywords(claim.statement + " " + claim.rationale)
            source_scored = []
            for src in sources:
                hay = f"{src.title} {src.snippet} {src.content_preview}".lower()
                hit = sum(1 for kw in keywords if kw in hay)
                if hit <= 0:
                    continue
                score = min(1.0, 0.2 + hit * 0.12)
                source_scored.append((score, src))

            source_scored.sort(key=lambda x: x[0], reverse=True)
            supporting: List[SourceAttribution] = []
            for score, source in source_scored[:3]:
                excerpt, origin = self._best_evidence_excerpt(keywords=keywords, source=source)
                supporting.append(
                    SourceAttribution(
                        source_id=source.source_id,
                        title=source.title,
                        url=source.url,
                        relevance_score=round(score, 2),
                        snippet=excerpt,
                        evidence_origin=origin,
                    )
                )

            conflicting: List[SourceAttribution] = []
            for score, source in source_scored:
                if not self._is_conflicting(f"{source.snippet} {source.content_preview}"):
                    continue
                excerpt, origin = self._best_evidence_excerpt(keywords=keywords, source=source)
                conflicting.append(
                    SourceAttribution(
                        source_id=source.source_id,
                        title=source.title,
                        url=source.url,
                        relevance_score=round(score, 2),
                        snippet=excerpt,
                        evidence_origin=origin,
                    )
                )
                if len(conflicting) >= 2:
                    break

            fulltext_support = len([s for s in supporting if s.evidence_origin == "fulltext"])
            confidence = (
                0.55
                + len(supporting) * 0.1
                + fulltext_support * 0.03
                - len(conflicting) * 0.08
            )
            claim.supporting_sources = supporting
            claim.conflicting_sources = conflicting
            claim.confidence = max(0.2, min(0.95, round(confidence, 2)))
            aligned_claims.append(claim)
        return aligned_claims

    @staticmethod
    def _is_conflicting(text: str) -> bool:
        text_lower = text.lower()
        return any(marker in text_lower for marker in CONTRADICTION_MARKERS)

    @staticmethod
    def _keywords(text: str) -> List[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower())
        uniq: Dict[str, None] = {}
        for token in tokens:
            if token in STOP_WORDS:
                continue
            uniq[token] = None
        return list(uniq.keys())[:12]

    def _best_evidence_excerpt(self, keywords: List[str], source: SourceDocument) -> tuple[str, str]:
        from_content = self._best_excerpt_from_content(keywords, source.content_preview)
        if from_content:
            return from_content, "fulltext"
        return source.snippet, "snippet"

    @staticmethod
    def _best_excerpt_from_content(keywords: List[str], content: str) -> str:
        if not content:
            return ""
        sentences = re.split(r"(?<=[.!?。！？])\s+", content)
        best_sentence = ""
        best_score = 0
        for sentence in sentences:
            cleaned = sentence.strip()
            if len(cleaned) < 40:
                continue
            lowered = cleaned.lower()
            score = sum(1 for kw in keywords if kw in lowered)
            if score > best_score:
                best_sentence = cleaned
                best_score = score
        if best_score <= 0:
            return ""
        return best_sentence[:320]

    def _estimate_tokens(
        self,
        topic: str,
        sources: Iterable[SourceDocument],
        claims: Iterable[Claim],
        report: str,
    ) -> int:
        text_blob = [topic, report]
        text_blob.extend(f"{s.title} {s.snippet} {s.content_preview[:800]}" for s in sources)
        text_blob.extend(f"{c.statement} {c.rationale}" for c in claims)
        chars = len(" ".join(text_blob))
        return max(200, chars // 4)

    def _estimate_cost(self, tokens: int) -> float:
        cheap_tokens = int(tokens * 0.7)
        expensive_tokens = tokens - cheap_tokens
        return (
            (cheap_tokens / 1000.0) * self.settings.cheap_model_cost_per_1k
            + (expensive_tokens / 1000.0) * self.settings.expensive_model_cost_per_1k
        )

    @staticmethod
    def _append_degraded_reason(reasons: List[str], reason: str) -> None:
        if reason not in reasons:
            reasons.append(reason)
            logger.warning("degraded_fallback %s", reason)

    @staticmethod
    def _log_event(event: str, **payload: object) -> None:
        body = {"event": event, **payload}
        logger.info(json.dumps(body, ensure_ascii=False, default=str))
