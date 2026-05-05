"""Cross-question / cross-answer similarity scoring for the Vergleich tab.

Public surface:

    similar_questions(query_text, candidates, k=5)
        BM25 + (optional) cosine ranking of the doc's other questions.

    score_pair(reference, candidate)
        Numeric similarity between two answer strings — BM25 + (optional)
        cosine. Used by /api/admin/compare to compare the local
        reference answer against a pipeline's answer.

Embedding-based scoring is opt-in: callers pass an embedder callable
that returns a list[float] per text. When None, only BM25 runs.
"""

from local_pdf.comparison.bm25 import bm25_scores, tokenize
from local_pdf.comparison.similarity import (
    SimilarQuestion,
    cosine,
    score_pair,
    similar_questions,
)

__all__ = [
    "SimilarQuestion",
    "bm25_scores",
    "cosine",
    "score_pair",
    "similar_questions",
    "tokenize",
]
