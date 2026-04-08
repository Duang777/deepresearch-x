from __future__ import annotations

import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Sequence

from deepresearch_x.models import Claim, MemoryFact, MemoryUpsertResult, SessionCheckpoint
from deepresearch_x.memory.store import GLOBAL_SESSION_ID, MemoryStore, utc_now_iso


@dataclass
class MemorySelection:
    facts: List[MemoryFact]
    context_text: str
    injection_tokens: int


@dataclass
class MemoryIngestOutcome:
    result: MemoryUpsertResult
    elapsed_ms: int


@dataclass
class _MemoryJob:
    store: MemoryStore
    facts: List[MemoryFact]
    done: threading.Event
    outcome: MemoryIngestOutcome | None = None


class MemoryService:
    def __init__(self, default_store: MemoryStore, openviking_store: MemoryStore | None = None) -> None:
        self.default_store = default_store
        self.openviking_store = openviking_store
        self._queue: "queue.Queue[_MemoryJob]" = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="memory-ingest")
        self._worker.start()

    def resolve_store(self, backend: str) -> MemoryStore:
        if backend == "openviking" and self.openviking_store is not None:
            return self.openviking_store
        return self.default_store

    def select_for_injection(
        self,
        session_id: str,
        scope: str,
        budget_tokens: int,
        backend: str,
    ) -> MemorySelection:
        store = self.resolve_store(backend)
        pool = store.get_memory(session_id=session_id, scope=scope, limit=48)
        ranked = sorted(pool, key=self._score_fact, reverse=True)

        chosen: List[MemoryFact] = []
        used_tokens = 0
        for fact in ranked:
            token_cost = self._estimate_fact_tokens(fact)
            if used_tokens + token_cost > budget_tokens:
                continue
            chosen.append(fact)
            used_tokens += token_cost

        lines = []
        for idx, fact in enumerate(chosen, start=1):
            lines.append(
                f"{idx}. [{fact.scope}] conf={fact.confidence:.2f} conflict={int(fact.conflict)} :: {fact.fact_text}"
            )
        context = "\n".join(lines)
        return MemorySelection(facts=chosen, context_text=context, injection_tokens=used_tokens)

    def enqueue_claims(
        self,
        session_id: str,
        claims: Sequence[Claim],
        scope: str,
        backend: str,
        wait_ms: int,
    ) -> MemoryIngestOutcome:
        store = self.resolve_store(backend)
        facts = self._extract_facts(session_id=session_id, claims=claims, scope=scope)
        if not facts:
            return MemoryIngestOutcome(result=MemoryUpsertResult(), elapsed_ms=0)
        job = _MemoryJob(store=store, facts=facts, done=threading.Event())
        start = time.perf_counter()
        self._queue.put(job)
        job.done.wait(timeout=max(0.01, wait_ms / 1000.0))
        elapsed = int((time.perf_counter() - start) * 1000)
        if job.outcome:
            return MemoryIngestOutcome(result=job.outcome.result, elapsed_ms=elapsed)
        return MemoryIngestOutcome(result=MemoryUpsertResult(), elapsed_ms=elapsed)

    def save_checkpoint(self, backend: str, checkpoint: SessionCheckpoint) -> None:
        store = self.resolve_store(backend)
        store.save_checkpoint(checkpoint)

    def get_checkpoints(self, backend: str, session_id: str, limit: int = 20) -> List[SessionCheckpoint]:
        store = self.resolve_store(backend)
        return store.get_checkpoints(session_id=session_id, limit=limit)

    def get_memory(
        self,
        backend: str,
        session_id: str,
        scope: str = "hybrid",
        limit: int = 40,
    ) -> List[MemoryFact]:
        store = self.resolve_store(backend)
        return store.get_memory(session_id=session_id, scope=scope, limit=limit)

    def compact(
        self,
        backend: str,
        ttl_hours: int,
        max_session_facts: int,
        max_global_facts: int,
    ) -> int:
        store = self.resolve_store(backend)
        return store.compact(
            ttl_hours=ttl_hours,
            max_session_facts=max_session_facts,
            max_global_facts=max_global_facts,
        )

    def _worker_loop(self) -> None:
        while True:
            job = self._queue.get()
            started = time.perf_counter()
            try:
                result = job.store.upsert_facts(job.facts)
                elapsed = int((time.perf_counter() - started) * 1000)
                job.outcome = MemoryIngestOutcome(result=result, elapsed_ms=elapsed)
            except Exception:
                job.outcome = MemoryIngestOutcome(result=MemoryUpsertResult(), elapsed_ms=0)
            finally:
                job.done.set()
                self._queue.task_done()

    @staticmethod
    def _extract_facts(session_id: str, claims: Sequence[Claim], scope: str) -> List[MemoryFact]:
        now = utc_now_iso()
        dedupe: dict[tuple[str, str], MemoryFact] = {}
        for claim in claims:
            fact_text = claim.statement.strip()[:360]
            if not fact_text:
                continue
            tags = MemoryService._extract_tags(f"{claim.statement} {claim.rationale}")
            source_ids = [s.source_id for s in claim.supporting_sources[:4]]
            is_conflict = len(claim.conflicting_sources) > 0
            scopes: List[str]
            if scope == "session":
                scopes = ["session"]
            elif scope == "global":
                scopes = ["global"]
            else:
                scopes = ["session"]
                if claim.confidence >= 0.72:
                    scopes.append("global")
            for fact_scope in scopes:
                fact_session_id = session_id if fact_scope == "session" else GLOBAL_SESSION_ID
                key = (fact_scope, fact_text.lower())
                incoming = MemoryFact(
                    memory_id=str(uuid.uuid4()),
                    session_id=fact_session_id,
                    scope=fact_scope,
                    fact_text=fact_text,
                    confidence=claim.confidence,
                    source_ids=source_ids,
                    tags=tags,
                    created_at=now,
                    last_seen_at=now,
                    decay_score=0.0,
                    conflict=is_conflict,
                    hit_count=1,
                )
                existing = dedupe.get(key)
                if existing is None:
                    dedupe[key] = incoming
                    continue
                existing.confidence = max(existing.confidence, incoming.confidence)
                existing.source_ids = list(dict.fromkeys(existing.source_ids + incoming.source_ids))
                existing.tags = list(dict.fromkeys(existing.tags + incoming.tags))
                existing.conflict = existing.conflict or incoming.conflict
        return list(dedupe.values())

    @staticmethod
    def _extract_tags(text: str) -> List[str]:
        tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", text.lower())
        uniq = list(dict.fromkeys(tokens))
        return uniq[:4]

    @staticmethod
    def _estimate_fact_tokens(fact: MemoryFact) -> int:
        return max(8, len(fact.fact_text) // 4 + 12)

    @staticmethod
    def _score_fact(fact: MemoryFact) -> float:
        recency = 1.0
        try:
            last_seen = datetime.fromisoformat(fact.last_seen_at.replace("Z", "+00:00"))
            age_hours = max(0.0, (datetime.now(timezone.utc) - last_seen).total_seconds() / 3600.0)
            recency = 1.0 / (1.0 + age_hours / 72.0)
        except Exception:
            pass
        conflict_penalty = 0.82 if fact.conflict else 1.0
        decay_penalty = 1.0 - min(0.75, max(0.0, fact.decay_score))
        return fact.confidence * recency * conflict_penalty * decay_penalty
