from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Protocol, Tuple

from deepresearch_x.models import MemoryFact, MemoryUpsertResult, SessionCheckpoint

GLOBAL_SESSION_ID = "__global__"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_fact(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class MemoryStore(Protocol):
    backend_name: str

    def get_memory(self, session_id: str, scope: str, limit: int = 40) -> List[MemoryFact]:
        ...

    def upsert_facts(self, facts: List[MemoryFact]) -> MemoryUpsertResult:
        ...

    def save_checkpoint(self, checkpoint: SessionCheckpoint) -> None:
        ...

    def get_checkpoints(self, session_id: str, limit: int = 20) -> List[SessionCheckpoint]:
        ...


class InMemoryStore:
    backend_name = "inmemory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._facts: Dict[Tuple[str, str, str], MemoryFact] = {}
        self._checkpoints: Dict[str, List[SessionCheckpoint]] = {}

    def get_memory(self, session_id: str, scope: str, limit: int = 40) -> List[MemoryFact]:
        with self._lock:
            candidates = []
            for fact in self._facts.values():
                if scope == "session" and fact.session_id == session_id and fact.scope == "session":
                    candidates.append(fact)
                elif scope == "global" and fact.scope == "global":
                    candidates.append(fact)
                elif scope == "hybrid":
                    if (
                        (fact.scope == "session" and fact.session_id == session_id)
                        or fact.scope == "global"
                    ):
                        candidates.append(fact)
            candidates.sort(key=lambda x: (x.confidence, x.last_seen_at), reverse=True)
            return [f.model_copy(deep=True) for f in candidates[:limit]]

    def upsert_facts(self, facts: List[MemoryFact]) -> MemoryUpsertResult:
        writes = 0
        conflicts = 0
        with self._lock:
            for fact in facts:
                key = (fact.session_id, fact.scope, hash_fact(fact.fact_text))
                existing = self._facts.get(key)
                now = utc_now_iso()
                if existing is None:
                    if not fact.memory_id:
                        fact.memory_id = str(uuid.uuid4())
                    fact.created_at = fact.created_at or now
                    fact.last_seen_at = now
                    self._facts[key] = fact.model_copy(deep=True)
                else:
                    merged_sources = list(dict.fromkeys(existing.source_ids + fact.source_ids))
                    merged_tags = list(dict.fromkeys(existing.tags + fact.tags))
                    existing.confidence = round(max(existing.confidence, fact.confidence), 3)
                    existing.source_ids = merged_sources
                    existing.tags = merged_tags
                    existing.last_seen_at = now
                    existing.hit_count += 1
                    existing.decay_score = max(0.0, existing.decay_score * 0.85)
                    existing.conflict = existing.conflict or fact.conflict
                    self._facts[key] = existing
                writes += 1
                if fact.conflict:
                    conflicts += 1
        return MemoryUpsertResult(write_count=writes, conflict_count=conflicts)

    def save_checkpoint(self, checkpoint: SessionCheckpoint) -> None:
        with self._lock:
            self._checkpoints.setdefault(checkpoint.session_id, []).append(checkpoint.model_copy(deep=True))
            self._checkpoints[checkpoint.session_id].sort(key=lambda x: x.created_at, reverse=True)

    def get_checkpoints(self, session_id: str, limit: int = 20) -> List[SessionCheckpoint]:
        with self._lock:
            return [c.model_copy(deep=True) for c in self._checkpoints.get(session_id, [])[:limit]]


class SQLiteStore:
    backend_name = "sqlite"

    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_facts (
                    memory_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    fact_hash TEXT NOT NULL,
                    fact_text TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source_ids TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    decay_score REAL NOT NULL DEFAULT 0,
                    conflict INTEGER NOT NULL DEFAULT 0,
                    hit_count INTEGER NOT NULL DEFAULT 1
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_unique
                    ON memory_facts(session_id, scope, fact_hash);
                CREATE INDEX IF NOT EXISTS idx_memory_session
                    ON memory_facts(session_id, last_seen_at DESC);
                CREATE TABLE IF NOT EXISTS session_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    loops INTEGER NOT NULL,
                    source_count INTEGER NOT NULL,
                    claim_count INTEGER NOT NULL,
                    memory_snapshot_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    metrics_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_checkpoint_session
                    ON session_checkpoints(session_id, created_at DESC);
                """
            )

    def get_memory(self, session_id: str, scope: str, limit: int = 40) -> List[MemoryFact]:
        clauses = []
        params: List[object] = []
        if scope == "session":
            clauses.append("(scope='session' AND session_id=?)")
            params.append(session_id)
        elif scope == "global":
            clauses.append("(scope='global')")
        else:
            clauses.append("(scope='global' OR (scope='session' AND session_id=?))")
            params.append(session_id)

        query = (
            "SELECT * FROM memory_facts WHERE "
            + " OR ".join(clauses)
            + " ORDER BY confidence DESC, last_seen_at DESC LIMIT ?"
        )
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_fact(r) for r in rows]

    def upsert_facts(self, facts: List[MemoryFact]) -> MemoryUpsertResult:
        writes = 0
        conflicts = 0
        now = utc_now_iso()
        with self._conn() as conn:
            for fact in facts:
                fact_hash = hash_fact(fact.fact_text)
                row = conn.execute(
                    """
                    SELECT * FROM memory_facts
                    WHERE session_id=? AND scope=? AND fact_hash=?
                    """,
                    (fact.session_id, fact.scope, fact_hash),
                ).fetchone()
                if row is None:
                    memory_id = fact.memory_id or str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO memory_facts (
                            memory_id, session_id, scope, fact_hash, fact_text, confidence,
                            source_ids, tags, created_at, last_seen_at, decay_score, conflict, hit_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            memory_id,
                            fact.session_id,
                            fact.scope,
                            fact_hash,
                            fact.fact_text,
                            fact.confidence,
                            json.dumps(fact.source_ids, ensure_ascii=False),
                            json.dumps(fact.tags, ensure_ascii=False),
                            fact.created_at or now,
                            now,
                            fact.decay_score,
                            1 if fact.conflict else 0,
                            fact.hit_count or 1,
                        ),
                    )
                else:
                    merged_sources = list(
                        dict.fromkeys(
                            json.loads(row["source_ids"]) + list(fact.source_ids)
                        )
                    )
                    merged_tags = list(dict.fromkeys(json.loads(row["tags"]) + list(fact.tags)))
                    merged_confidence = round(max(float(row["confidence"]), fact.confidence), 3)
                    merged_hit_count = int(row["hit_count"]) + 1
                    merged_conflict = bool(row["conflict"]) or fact.conflict
                    decay_score = max(0.0, float(row["decay_score"]) * 0.85)
                    conn.execute(
                        """
                        UPDATE memory_facts
                        SET confidence=?, source_ids=?, tags=?, last_seen_at=?, hit_count=?, conflict=?, decay_score=?
                        WHERE memory_id=?
                        """,
                        (
                            merged_confidence,
                            json.dumps(merged_sources, ensure_ascii=False),
                            json.dumps(merged_tags, ensure_ascii=False),
                            now,
                            merged_hit_count,
                            1 if merged_conflict else 0,
                            decay_score,
                            row["memory_id"],
                        ),
                    )
                writes += 1
                if fact.conflict:
                    conflicts += 1
        return MemoryUpsertResult(write_count=writes, conflict_count=conflicts)

    def save_checkpoint(self, checkpoint: SessionCheckpoint) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO session_checkpoints (
                    checkpoint_id, session_id, run_id, topic, loops,
                    source_count, claim_count, memory_snapshot_count, created_at, metrics_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.checkpoint_id,
                    checkpoint.session_id,
                    checkpoint.run_id,
                    checkpoint.topic,
                    checkpoint.loops,
                    checkpoint.source_count,
                    checkpoint.claim_count,
                    checkpoint.memory_snapshot_count,
                    checkpoint.created_at,
                    json.dumps(checkpoint.metrics, ensure_ascii=False),
                ),
            )

    def get_checkpoints(self, session_id: str, limit: int = 20) -> List[SessionCheckpoint]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM session_checkpoints
                WHERE session_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        result: List[SessionCheckpoint] = []
        for row in rows:
            result.append(
                SessionCheckpoint(
                    checkpoint_id=row["checkpoint_id"],
                    session_id=row["session_id"],
                    run_id=row["run_id"],
                    topic=row["topic"],
                    loops=int(row["loops"]),
                    source_count=int(row["source_count"]),
                    claim_count=int(row["claim_count"]),
                    memory_snapshot_count=int(row["memory_snapshot_count"]),
                    created_at=row["created_at"],
                    metrics=json.loads(row["metrics_json"]),
                )
            )
        return result

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> MemoryFact:
        return MemoryFact(
            memory_id=row["memory_id"],
            session_id=row["session_id"],
            scope=row["scope"],
            fact_text=row["fact_text"],
            confidence=float(row["confidence"]),
            source_ids=json.loads(row["source_ids"]),
            tags=json.loads(row["tags"]),
            created_at=row["created_at"],
            last_seen_at=row["last_seen_at"],
            decay_score=float(row["decay_score"]),
            conflict=bool(row["conflict"]),
            hit_count=int(row["hit_count"]),
        )
