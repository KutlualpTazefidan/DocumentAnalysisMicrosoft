"""Minimal BM25 — hand-rolled to avoid adding rank-bm25 as a dep.

Standard Okapi BM25 with the usual k1=1.5, b=0.75 defaults. Tokenizer
lower-cases, strips punctuation, splits on whitespace. Good enough
for short German question strings; Lucene-grade tokenisation is not
warranted here.

Public surface:

    tokenize(text) -> list[str]
    bm25_scores(query_text, corpus_texts) -> list[float]
        One score per corpus document; aligned positionally with the
        input list. Higher = more relevant.
"""

from __future__ import annotations

import math
import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")

# Minimal German + English stopwords. Dropped because BM25 over short
# question strings is dominated by stopwords otherwise (every question
# starts with "Was/Wie/Welche" → no signal).
_STOPWORDS = frozenset(
    {
        # German articles, copulas, prepositions, interrogatives.
        "der",
        "die",
        "das",
        "ein",
        "eine",
        "einen",
        "einem",
        "einer",
        "und",
        "oder",
        "ist",
        "sind",
        "wird",
        "werden",
        "wurde",
        "wurden",
        "war",
        "waren",
        "im",
        "auf",
        "am",
        "zu",
        "zum",
        "zur",
        "von",
        "vom",
        "mit",
        "für",
        "fuer",
        "ueber",
        "über",
        "bei",
        "nach",
        "vor",
        "aus",
        "als",
        "den",
        "dem",
        "des",
        "auch",
        "noch",
        "nur",
        "so",
        "wie",
        "was",
        "wer",
        "welcher",
        "welche",
        "welches",
        # English overlap. "in"/"an"/"was" already covered above.
        "the",
        "and",
        "or",
        "is",
        "are",
        "were",
        "of",
        "on",
        "at",
        "to",
        "by",
        "for",
        "with",
        "this",
        "that",
        "what",
        "which",
        "who",
        "how",
    }
)


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    s = unicodedata.normalize("NFKC", text).casefold()
    s = _PUNCT_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return [t for t in s.split(" ") if t and t not in _STOPWORDS]


def bm25_scores(
    query_text: str,
    corpus_texts: list[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Return one BM25 score per *corpus_texts* entry, aligned to input order."""
    if not corpus_texts:
        return []
    docs = [tokenize(t) for t in corpus_texts]
    query = tokenize(query_text)
    if not query:
        return [0.0] * len(corpus_texts)

    n_docs = len(docs)
    avgdl = sum(len(d) for d in docs) / n_docs if n_docs else 0.0

    # Document frequency per query term.
    df: dict[str, int] = {}
    for term in set(query):
        df[term] = sum(1 for d in docs if term in d)

    scores: list[float] = []
    for d in docs:
        if not d:
            scores.append(0.0)
            continue
        dl = len(d)
        # Term-frequency in this doc.
        tf: dict[str, int] = {}
        for tok in d:
            tf[tok] = tf.get(tok, 0) + 1

        s = 0.0
        for term in query:
            if term not in tf:
                continue
            n_q = df.get(term, 0)
            # Standard Okapi BM25 IDF (with the +1 inside log to avoid
            # negative values when a term appears in more than half the docs).
            idf = math.log((n_docs - n_q + 0.5) / (n_q + 0.5) + 1.0)
            f_qd = tf[term]
            denom = f_qd + k1 * (1.0 - b + b * (dl / avgdl if avgdl else 0.0))
            s += idf * (f_qd * (k1 + 1.0)) / (denom or 1.0)
        scores.append(s)
    return scores
