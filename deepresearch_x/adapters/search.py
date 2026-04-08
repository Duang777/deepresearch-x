from __future__ import annotations

import re
from datetime import datetime
from typing import List, Protocol

from deepresearch_x.models import SourceDocument


class SearchProvider(Protocol):
    def search(self, query: str, top_k: int) -> List[SourceDocument]:
        ...


class DuckDuckGoSearchProvider:
    """Uses DuckDuckGo search results when no paid API key is provided."""

    def search(self, query: str, top_k: int) -> List[SourceDocument]:
        try:
            from ddgs import DDGS
        except Exception as exc:  # pragma: no cover
            try:
                # Backward-compatible fallback for older environments.
                from duckduckgo_search import DDGS  # type: ignore
            except Exception as inner_exc:  # pragma: no cover
                raise RuntimeError(
                    "DDGS search dependency is unavailable. Install requirements first."
                ) from inner_exc

        results: List[SourceDocument] = []
        with DDGS(impersonate="random") as ddgs:
            rows = ddgs.text(query, max_results=top_k)
            for idx, row in enumerate(rows, start=1):
                url = row.get("href") or row.get("url") or ""
                if not url:
                    continue
                results.append(
                    SourceDocument(
                        source_id=f"S{idx}",
                        title=row.get("title", "Untitled"),
                        url=url,
                        snippet=row.get("body", ""),
                        query=query,
                        rank=idx,
                    )
                )
        if not results:
            raise RuntimeError("No search results returned from DuckDuckGo.")
        return results


class MockSearchProvider:
    """Reliable fallback provider for local demos and tests."""

    _DOMAIN_HINTS = (
        "arxiv.org",
        "huggingface.co",
        "github.com",
        "nature.com",
        "openai.com",
        "who.int",
        "nvidia.com",
    )

    def search(self, query: str, top_k: int) -> List[SourceDocument]:
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:48]
        now = datetime.now().strftime("%Y-%m-%d")
        results: List[SourceDocument] = []

        snippets = [
            f"Recent analysis ({now}) suggests {query} adoption is accelerated by tooling maturity, not just model quality.",
            f"Benchmark summaries indicate {query} performance depends heavily on retrieval quality and citation discipline.",
            f"Community reports show teams shipping {query} faster when they separate planning, retrieval, and synthesis stages.",
            f"Cost breakdowns reveal that staged model routing lowers spend for {query} without obvious quality loss in many tasks.",
            f"Failure analyses emphasize hallucination risk for {query} when sources are weak or contradictory.",
            f"Enterprise case studies highlight observability and guardrails as key blockers for production {query} deployments.",
            f"Several open-source implementations of {query} now expose intermediate traces to improve trust and debugging.",
            f"Comparative evaluations show multilingual retrieval remains a bottleneck for {query} systems.",
        ]

        for idx in range(1, top_k + 1):
            domain = self._DOMAIN_HINTS[(idx - 1) % len(self._DOMAIN_HINTS)]
            results.append(
                SourceDocument(
                    source_id=f"M{idx}",
                    title=f"{query.title()} - Research Insight {idx}",
                    url=f"https://{domain}/search/{slug}/{idx}",
                    snippet=snippets[(idx - 1) % len(snippets)],
                    query=query,
                    rank=idx,
                    is_mock=True,
                    content_preview="",
                    fetch_status="snippet_only",
                )
            )
        return results
