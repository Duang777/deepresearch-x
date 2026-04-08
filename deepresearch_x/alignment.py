from __future__ import annotations

import logging
from typing import List, Protocol, Sequence

logger = logging.getLogger("deepresearch_x.alignment")


class SimilarityScorer(Protocol):
    def score(self, query: str, documents: Sequence[str]) -> List[float]:
        ...


class SentenceTransformerScorer:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def score(self, query: str, documents: Sequence[str]) -> List[float]:
        if not documents:
            return []
        vectors = self._model.encode([query, *documents], normalize_embeddings=True)
        query_vector = vectors[0]
        doc_vectors = vectors[1:]
        scores: List[float] = []
        for vec in doc_vectors:
            cosine = sum(float(a) * float(b) for a, b in zip(query_vector, vec))
            # Map cosine from [-1, 1] to [0, 1] for easier score blending.
            normalized = max(0.0, min(1.0, (cosine + 1.0) / 2.0))
            scores.append(normalized)
        return scores


def build_semantic_scorer(enabled: bool, model_name: str) -> SimilarityScorer | None:
    if not enabled:
        return None
    try:
        scorer = SentenceTransformerScorer(model_name=model_name)
        logger.info("semantic_alignment_enabled model=%s", model_name)
        return scorer
    except Exception as exc:
        logger.warning(
            "semantic_alignment_disabled reason=%s",
            exc.__class__.__name__,
        )
        return None
