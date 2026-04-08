from __future__ import annotations

import time
from typing import Any, List

import httpx

from deepresearch_x.models import MemoryFact, MemoryUpsertResult, SessionCheckpoint
from deepresearch_x.memory.store import MemoryStore


class OpenVikingMemoryAdapter:
    """
    Best-effort adapter for OpenViking-like memory services.
    Falls back to local store when remote service is unavailable.
    """

    backend_name = "openviking"

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        fallback_store: MemoryStore,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.fallback_store = fallback_store
        self.fail_cooldown_seconds = 15.0
        self._disabled_until = 0.0

    def get_memory(self, session_id: str, scope: str, limit: int = 40) -> List[MemoryFact]:
        if not self._remote_enabled():
            return self.fallback_store.get_memory(session_id, scope, limit)
        payload = {"session_id": session_id, "scope": scope, "limit": limit}
        try:
            body = self._post_json("/api/v1/retrieval/find", payload)
            records = body.get("memories") or body.get("items") or body.get("data") or []
            parsed = [self._parse_fact(item, session_id=session_id) for item in records]
            return parsed[:limit] if parsed else self.fallback_store.get_memory(session_id, scope, limit)
        except Exception:
            self._mark_remote_failed()
            return self.fallback_store.get_memory(session_id, scope, limit)

    def upsert_facts(self, facts: List[MemoryFact]) -> MemoryUpsertResult:
        if not self._remote_enabled():
            return self.fallback_store.upsert_facts(facts)
        payload = {"memories": [fact.model_dump() for fact in facts]}
        try:
            body = self._post_json("/api/v1/sessions/commit", payload)
            write_count = int(body.get("write_count", len(facts)))
            conflict_count = int(body.get("conflict_count", 0))
            return MemoryUpsertResult(write_count=write_count, conflict_count=conflict_count)
        except Exception:
            self._mark_remote_failed()
            return self.fallback_store.upsert_facts(facts)

    def save_checkpoint(self, checkpoint: SessionCheckpoint) -> None:
        self.fallback_store.save_checkpoint(checkpoint)
        if not self._remote_enabled():
            return
        try:
            self._post_json("/api/v1/sessions/checkpoint", checkpoint.model_dump())
        except Exception:
            self._mark_remote_failed()
            return

    def get_checkpoints(self, session_id: str, limit: int = 20) -> List[SessionCheckpoint]:
        return self.fallback_store.get_checkpoints(session_id, limit)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(url, json=payload)
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, dict):
            return body
        return {"data": body}

    def _remote_enabled(self) -> bool:
        return time.monotonic() >= self._disabled_until

    def _mark_remote_failed(self) -> None:
        self._disabled_until = time.monotonic() + self.fail_cooldown_seconds

    @staticmethod
    def _parse_fact(item: dict[str, Any], session_id: str) -> MemoryFact:
        return MemoryFact(
            memory_id=str(item.get("memory_id") or item.get("id") or ""),
            session_id=str(item.get("session_id") or session_id),
            scope=str(item.get("scope") or "session"),
            fact_text=str(item.get("fact_text") or item.get("text") or ""),
            confidence=float(item.get("confidence", 0.55)),
            source_ids=[str(x) for x in item.get("source_ids", [])],
            tags=[str(x) for x in item.get("tags", [])],
            created_at=str(item.get("created_at") or ""),
            last_seen_at=str(item.get("last_seen_at") or ""),
            decay_score=float(item.get("decay_score", 0.0)),
            conflict=bool(item.get("conflict", False)),
            hit_count=int(item.get("hit_count", 1)),
        )
