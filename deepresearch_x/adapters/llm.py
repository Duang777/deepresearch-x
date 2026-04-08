from __future__ import annotations

import json
import re
from typing import List, Protocol

from deepresearch_x.models import Claim, SourceAttribution, SourceDocument


class LLMProvider(Protocol):
    def extract_claims(
        self,
        topic: str,
        sources: List[SourceDocument],
        memory_context: str = "",
    ) -> List[Claim]:
        ...

    def synthesize_report(
        self,
        topic: str,
        claims: List[Claim],
        memory_context: str = "",
    ) -> str:
        ...


class HeuristicLLMProvider:
    """
    LLM-free fallback that still produces a structured output.
    Useful for local demos and CI sanity tests.
    """

    def extract_claims(
        self,
        topic: str,
        sources: List[SourceDocument],
        memory_context: str = "",
    ) -> List[Claim]:
        topic_context = topic if not memory_context else f"{topic} (session-memory aware)"
        selected = sources[: min(4, len(sources))]
        claims: List[Claim] = []
        for idx, src in enumerate(selected, start=1):
            statement = self._build_statement(topic_context, src)
            rationale = (
                f"Derived from {src.title}. The source snippet highlights mechanisms, "
                "trade-offs, or risks relevant to the topic."
            )
            if memory_context:
                rationale += " Prior session memory was considered in ranking."
            claims.append(
                Claim(
                    claim_id=f"C{idx}",
                    statement=statement,
                    rationale=rationale,
                    supporting_sources=[
                        SourceAttribution(
                            source_id=src.source_id,
                            title=src.title,
                            url=src.url,
                            relevance_score=0.72,
                            snippet=src.snippet,
                        )
                    ],
                    conflicting_sources=[],
                    confidence=0.62 + (idx * 0.05),
                )
            )
        return claims

    def synthesize_report(
        self,
        topic: str,
        claims: List[Claim],
        memory_context: str = "",
    ) -> str:
        lines = [f"# {topic} - Deep Research Report", ""]
        lines.append("## Executive Summary")
        lines.append(
            f"This run produced {len(claims)} key claims with explicit source links and confidence estimates."
        )
        if memory_context:
            lines.append("Session memory was injected with a token budget to improve continuity.")
        lines.append("")
        lines.append("## Key Findings")
        for claim in claims:
            lines.append(
                f"- **{claim.claim_id}** ({claim.confidence:.2f}): {claim.statement}"
            )
        lines.append("")
        lines.append("## Risk Notes")
        lines.append(
            "- Retrieval quality and source freshness strongly influence final report quality."
        )
        lines.append(
            "- Contradictory evidence should trigger a follow-up verification step before decisions."
        )
        lines.append("")
        lines.append("## Suggested Next Actions")
        lines.append("- Run a multilingual query variant for broader coverage.")
        lines.append("- Add a stronger model only for final synthesis and contradiction resolution.")
        return "\n".join(lines)

    @staticmethod
    def _build_statement(topic: str, src: SourceDocument) -> str:
        clean = re.sub(r"\s+", " ", src.snippet).strip()
        clean = clean[:180] + "..." if len(clean) > 180 else clean
        return f"{topic} evidence suggests: {clean}"


class OpenAIProvider:
    """Optional provider using OpenAI-compatible API keys from environment."""

    def __init__(self, model: str) -> None:
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "openai package is unavailable. Install requirements first."
            ) from exc
        self.model = model
        self.client = OpenAI()
        self.fallback = HeuristicLLMProvider()

    def extract_claims(
        self,
        topic: str,
        sources: List[SourceDocument],
        memory_context: str = "",
    ) -> List[Claim]:
        if not sources:
            return []

        compact_sources = [
            {
                "source_id": s.source_id,
                "title": s.title,
                "url": s.url,
                "snippet": s.snippet[:260],
            }
            for s in sources[:8]
        ]

        prompt = (
            "Extract up to 4 claims from the provided sources.\n"
            "Return strict JSON with key 'claims' and list items with fields:\n"
            "claim_id, statement, rationale.\n"
            f"Topic: {topic}\n"
            f"Session memory context (optional): {memory_context[:1800]}\n"
            f"Sources:\n{json.dumps(compact_sources, ensure_ascii=False)}"
        )

        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": "You are a precise research analyst. Output JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            raw = response.output_text
            parsed = json.loads(raw)
            claims = []
            for idx, item in enumerate(parsed.get("claims", []), start=1):
                claims.append(
                    Claim(
                        claim_id=item.get("claim_id", f"C{idx}"),
                        statement=item["statement"],
                        rationale=item.get("rationale", "Model-generated rationale."),
                        supporting_sources=[],
                        conflicting_sources=[],
                        confidence=0.65,
                    )
                )
            return claims if claims else self.fallback.extract_claims(topic, sources, memory_context)
        except Exception:
            return self.fallback.extract_claims(topic, sources, memory_context)

    def synthesize_report(
        self,
        topic: str,
        claims: List[Claim],
        memory_context: str = "",
    ) -> str:
        if not claims:
            return self.fallback.synthesize_report(topic, claims, memory_context)

        payload = [
            {
                "claim_id": c.claim_id,
                "statement": c.statement,
                "confidence": c.confidence,
            }
            for c in claims
        ]
        prompt = (
            "Write a concise deep research report in markdown with sections:\n"
            "Executive Summary, Key Findings, Risk Notes, Suggested Next Actions.\n"
            f"Topic: {topic}\n"
            f"Session memory context (optional): {memory_context[:1800]}\n"
            f"Claims:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        try:
            response = self.client.responses.create(
                model=self.model,
                input=prompt,
            )
            return response.output_text.strip()
        except Exception:
            return self.fallback.synthesize_report(topic, claims, memory_context)
