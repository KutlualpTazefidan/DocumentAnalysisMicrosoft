"""Embedding-based question dedup, scoped to a single source_element.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.4.

Usage:
    dedup = QuestionDedup(client=embed_client, model=embed_model)
    for element, generated in ...:
        existing = [e.query for e in active_entries_for(element)]
        kept = dedup.filter(
            generated,
            against=existing,
            source_key=element.element_id,
        )

If `client is None`, dedup is disabled — `filter` returns its
`generated` argument unchanged after logging a single per-session
warning.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_clients.base import LLMClient

__all__ = ["QuestionDedup", "cosine"]

_log = logging.getLogger(__name__)


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two same-length vectors. Returns
    0.0 if either has zero norm."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class QuestionDedup:
    """Bounded-scope dedup: questions are compared only against
    other questions for the same `source_key`.

    Threshold is `>= threshold`: a similarity equal to the threshold
    counts as a duplicate.
    """

    def __init__(
        self,
        client: LLMClient | None,
        model: str,
        threshold: float = 0.95,
    ) -> None:
        self._client = client
        self._model = model
        self._threshold = threshold
        # Per-source_key cache of `against` embeddings, plus a
        # rolling list of accepted generated embeddings within the
        # session so within-call dedup works.
        self._cache: dict[str, list[list[float]]] = {}
        self._disabled_warned = False

    def filter(
        self,
        generated: list[str],
        *,
        against: list[str],
        source_key: str,
    ) -> list[str]:
        if self._client is None:
            if not self._disabled_warned:
                _log.warning(
                    "dedup disabled — no embedding client configured; "
                    "generated questions will be passed through unchanged"
                )
                self._disabled_warned = True
            return list(generated)

        # Resolve the against-vector list for this source_key, using
        # the cache. If we've never seen this source_key, embed
        # `against` now and seed the cache.
        if source_key not in self._cache:
            against_vecs = self._client.embed(against, self._model) if against else []
            self._cache[source_key] = list(against_vecs)
        baseline = self._cache[source_key]

        if not generated:
            return []

        gen_vecs = self._client.embed(generated, self._model)

        kept: list[str] = []
        kept_vecs: list[list[float]] = []
        for q, v in zip(generated, gen_vecs, strict=True):
            if any(cosine(v, b) >= self._threshold for b in baseline):
                continue
            if any(cosine(v, k) >= self._threshold for k in kept_vecs):
                continue
            kept.append(q)
            kept_vecs.append(v)

        # Within-call accepted vectors are appended to the cache so
        # subsequent calls in this session also dedup against them.
        self._cache[source_key].extend(kept_vecs)
        return kept
