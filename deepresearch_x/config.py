from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class AppSettings:
    search_provider: str = os.getenv("SEARCH_PROVIDER", "duckduckgo")
    llm_provider: str = os.getenv("LLM_PROVIDER", "heuristic")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    enable_page_reader: bool = os.getenv("ENABLE_PAGE_READER", "true").lower() == "true"
    max_page_fetch_per_loop: int = int(os.getenv("MAX_PAGE_FETCH_PER_LOOP", "3"))
    page_fetch_workers: int = int(os.getenv("PAGE_FETCH_WORKERS", "4"))
    max_page_chars: int = int(os.getenv("MAX_PAGE_CHARS", "12000"))
    reader_timeout_seconds: float = float(os.getenv("READER_TIMEOUT_SECONDS", "8"))
    cheap_model_cost_per_1k: float = float(
        os.getenv("CHEAP_MODEL_COST_PER_1K", "0.0006")
    )
    expensive_model_cost_per_1k: float = float(
        os.getenv("EXPENSIVE_MODEL_COST_PER_1K", "0.005")
    )
    default_loops: int = int(os.getenv("DEFAULT_LOOPS", "3"))
    default_top_k: int = int(os.getenv("DEFAULT_TOP_K", "6"))
    enable_memory: bool = os.getenv("ENABLE_MEMORY", "true").lower() == "true"
    memory_backend: str = os.getenv("MEMORY_BACKEND", "sqlite").lower()
    memory_sqlite_path: str = os.getenv("MEMORY_SQLITE_PATH", "outputs/memory_store.db")
    memory_budget_tokens: int = int(os.getenv("MEMORY_BUDGET_TOKENS", "280"))
    memory_scope: str = os.getenv("MEMORY_SCOPE", "hybrid").lower()
    memory_queue_wait_ms: int = int(os.getenv("MEMORY_QUEUE_WAIT_MS", "220"))
    openviking_base_url: str = os.getenv("OPENVIKING_BASE_URL", "http://127.0.0.1:8100")
    openviking_timeout_seconds: float = float(os.getenv("OPENVIKING_TIMEOUT_SECONDS", "0.8"))
    allow_search_mock_fallback: bool = (
        os.getenv("ALLOW_SEARCH_MOCK_FALLBACK", "false").lower() == "true"
    )
    allow_llm_heuristic_fallback: bool = (
        os.getenv("ALLOW_LLM_HEURISTIC_FALLBACK", "false").lower() == "true"
    )
    memory_ttl_hours: int = int(os.getenv("MEMORY_TTL_HOURS", "336"))
    memory_max_global_facts: int = int(os.getenv("MEMORY_MAX_GLOBAL_FACTS", "600"))
    memory_max_session_facts: int = int(os.getenv("MEMORY_MAX_SESSION_FACTS", "250"))
    enable_semantic_alignment: bool = (
        os.getenv("ENABLE_SEMANTIC_ALIGNMENT", "false").lower() == "true"
    )
    semantic_model_name: str = os.getenv(
        "SEMANTIC_MODEL_NAME",
        "sentence-transformers/all-MiniLM-L6-v2",
    )
    semantic_weight: float = float(os.getenv("SEMANTIC_WEIGHT", "0.6"))
    keyword_weight: float = float(os.getenv("KEYWORD_WEIGHT", "0.4"))
