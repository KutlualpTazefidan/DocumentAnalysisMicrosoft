"""Hybrid (BM25 + cosine-embedding) similarity for the Vergleich tab.

Embedding scoring is opt-in: pass an *embedder* callable that maps a
list[str] → list[list[float]]. When None, only BM25 runs and cosine
scores are 0.0. The embedder typically wraps Azure OpenAI's text-
embedding-3-large, but anything matching the signature works (so
tests can inject a deterministic fake).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from local_pdf.comparison.bm25 import bm25_scores

Embedder = Callable[[list[str]], list[list[float]]]


@dataclass(frozen=True)
class SimilarQuestion:
    entry_id: str
    text: str
    box_id: str
    chunk: str
    bm25_score: float
    cosine_score: float


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def similar_questions(
    query_entry_id: str,
    query_text: str,
    candidates: list[tuple[str, str, str]],
    *,
    chunks: dict[str, str],
    embedder: Embedder | None = None,
    k: int = 5,
) -> list[SimilarQuestion]:
    """Return up to *k* candidates ranked by hybrid score, descending.

    ``candidates`` is a list of ``(entry_id, text, box_id)``. The query
    itself is filtered out by entry_id. Final rank = bm25_score (with
    a 0.5 weight) + cosine_score (with a 0.5 weight) when an embedder
    is provided; pure bm25 otherwise.

    ``chunks`` maps box_id → the box's text content (used to attach
    each hit's source chunk for the UI to show).
    """
    others = [(eid, t, bid) for (eid, t, bid) in candidates if eid != query_entry_id]
    if not others:
        return []

    texts = [t for (_, t, _) in others]
    bm25 = bm25_scores(query_text, texts)
    bm25_max = max(bm25) if bm25 else 0.0
    bm25_norm = [s / bm25_max if bm25_max > 0 else 0.0 for s in bm25]

    cosine_norm: list[float]
    if embedder is not None:
        try:
            vecs = embedder([query_text, *texts])
        except Exception:
            vecs = []
        if len(vecs) == len(texts) + 1:
            qv = vecs[0]
            cosine_norm = [max(0.0, cosine(qv, v)) for v in vecs[1:]]
        else:
            cosine_norm = [0.0] * len(texts)
    else:
        cosine_norm = [0.0] * len(texts)

    # Hybrid weighting: when both signals are available, weight cosine
    # higher than BM25 — semantic similarity beats lexical for question
    # near-paraphrases (e.g. "Welche Last hält die Schraube" vs "Wie viel
    # hält das Gewinde aus"). 0.6 / 0.4 is the common hybrid-retrieval
    # split.
    weight_bm25 = 0.4 if embedder is not None else 1.0
    weight_cos = 0.6 if embedder is not None else 0.0
    ranked: list[tuple[float, int]] = []
    for i in range(len(texts)):
        s = weight_bm25 * bm25_norm[i] + weight_cos * cosine_norm[i]
        ranked.append((s, i))
    ranked.sort(key=lambda p: p[0], reverse=True)

    out: list[SimilarQuestion] = []
    for _, i in ranked[:k]:
        eid, text, box_id = others[i]
        out.append(
            SimilarQuestion(
                entry_id=eid,
                text=text,
                box_id=box_id,
                chunk=chunks.get(box_id, ""),
                bm25_score=bm25_norm[i],
                cosine_score=cosine_norm[i],
            )
        )
    return out


def score_pair(
    reference: str,
    candidate: str,
    *,
    embedder: Embedder | None = None,
) -> dict[str, float]:
    """Score similarity between two strings (used by /compare).

    Returns a dict with keys ``bm25`` (normalized to [0,1] via the
    self-similarity max) and ``cosine`` (in [-1,1]; usually [0,1] for
    real text). When embedder is None, ``cosine`` is 0.0.
    """
    if not reference or not candidate:
        return {"bm25": 0.0, "cosine": 0.0}
    # BM25 of reference vs [candidate, reference] — normalize by the
    # self-score to keep the scale interpretable.
    raw = bm25_scores(reference, [candidate, reference])
    bm25 = (raw[0] / raw[1]) if raw[1] > 0 else 0.0

    cos = 0.0
    if embedder is not None:
        try:
            vecs = embedder([reference, candidate])
        except Exception:
            vecs = []
        if len(vecs) == 2:
            cos = cosine(vecs[0], vecs[1])
    return {"bm25": max(0.0, min(1.0, bm25)), "cosine": cos}
