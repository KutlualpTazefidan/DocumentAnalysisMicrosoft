"""Question dedup, scoped to a single source_element.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.4.

Two modes:

  - With an embedding client → cosine similarity ≥ threshold counts
    as a duplicate (default 0.95).
  - Without an embedding client → normalized-text fallback (NFKC-
    fold + lowercase + strip punctuation + collapse whitespace).
    Catches exact duplicates and the trivial near-misses (case,
    quoting style, trailing whitespace) that table prompts emit at
    high rates.

Usage:
    dedup = QuestionDedup(client=embed_client, model=embed_model)
    for element, generated in ...:
        existing = [e.query for e in active_entries_for(element)]
        kept = dedup.filter(
            generated,
            against=existing,
            source_key=element.element_id,
        )
"""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_clients.base import LLMClient

__all__ = ["QuestionDedup", "cosine", "normalize_for_dedup"]

_log = logging.getLogger(__name__)

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_for_dedup(q: str) -> str:
    """Fold unicode, lowercase, drop punctuation, collapse whitespace.

    Stable for the cheap text-equality dedup path; also useful for
    the UI's "delete duplicates" action so frontend and backend agree
    on what counts as the same question.
    """
    s = unicodedata.normalize("NFKC", q).casefold()
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


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
            return self._filter_text_equality(generated, against=against, source_key=source_key)

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

    # ── Text-equality fallback ───────────────────────────────────────

    # Per-source_key set of normalized strings already accepted in
    # this session; mirrors `_cache` for the embedding path.
    @property
    def _norm_cache(self) -> dict[str, set[str]]:
        cache = getattr(self, "_norm_cache_inner", None)
        if cache is None:
            cache = {}
            self._norm_cache_inner = cache
        return cache

    def _filter_text_equality(
        self,
        generated: list[str],
        *,
        against: list[str],
        source_key: str,
    ) -> list[str]:
        seen = self._norm_cache.setdefault(source_key, set())
        if not seen:
            for a in against:
                n = normalize_for_dedup(a)
                if n:
                    seen.add(n)
        out: list[str] = []
        for q in generated:
            n = normalize_for_dedup(q)
            if not n or n in seen:
                continue
            out.append(q)
            seen.add(n)
        return out
