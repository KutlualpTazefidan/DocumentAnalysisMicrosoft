"""Tests for the comparison helpers (BM25 + hybrid similar-questions)."""

from __future__ import annotations

from local_pdf.comparison import (
    SimilarQuestion,
    bm25_scores,
    cosine,
    score_pair,
    similar_questions,
    tokenize,
)


def test_tokenize_drops_stopwords_and_punct():
    assert tokenize("Was ist die Norm?") == ["norm"]
    assert tokenize("Wie schwer ist die Schraube M6?") == ["schwer", "schraube", "m6"]


def test_bm25_scores_align_with_input_order():
    scores = bm25_scores(
        "Was ist die maximale Last?",
        [
            "Was ist die maximale Last bei Druck?",
            "Wie ist das Wetter?",
            "Maximale Last ist 5 kN.",
        ],
    )
    # Doc 0 mentions "maximale" and "last" → highest. Doc 1 has none → 0.
    assert scores[1] == 0.0
    assert scores[0] > scores[2] > scores[1]
    assert len(scores) == 3


def test_bm25_empty_query_returns_zeros():
    assert bm25_scores("", ["a", "b"]) == [0.0, 0.0]
    assert bm25_scores("???", ["abc"]) == [0.0]


def test_cosine_known_values():
    assert cosine([1, 0, 0], [1, 0, 0]) == 1.0
    assert cosine([1, 0], [0, 1]) == 0.0
    assert abs(cosine([1, 1], [1, 0]) - (1 / (2**0.5))) < 1e-9


def test_similar_questions_filters_self_and_ranks_by_bm25():
    cands = [
        ("e1", "Welche Last hält die Schraube?", "p1-b0"),
        ("e2", "Was ist das Wetter?", "p1-b1"),
        ("e3", "Welche Last hält die Mutter?", "p2-b0"),  # near-paraphrase of query
    ]
    chunks = {"p1-b0": "chunk-A", "p1-b1": "chunk-B", "p2-b0": "chunk-C"}
    hits = similar_questions(
        query_entry_id="e3",
        query_text="Welche Last hält die Mutter?",
        candidates=cands,
        chunks=chunks,
        embedder=None,
        k=5,
    )
    # The query (e3) is filtered out.
    assert all(h.entry_id != "e3" for h in hits)
    # e1 (paraphrase) should rank above e2 (unrelated).
    ids = [h.entry_id for h in hits]
    assert ids[0] == "e1"
    assert "e2" in ids
    # Chunks attached.
    assert hits[0].chunk == "chunk-A"


def test_similar_questions_uses_embedder_when_provided():
    """A fake embedder that flips the BM25 ranking: e2 gets vec parallel
    to query, e1 gets perpendicular. Hybrid score should put e2 first
    even though BM25 says otherwise."""
    cands = [
        ("e1", "Welche Last hält die Schraube?", "p1-b0"),
        ("e2", "Wie ist das Wetter?", "p1-b1"),
    ]
    chunks = {"p1-b0": "chunk-A", "p1-b1": "chunk-B"}

    def embedder(texts: list[str]) -> list[list[float]]:
        # Index 0 = query, 1 = e1, 2 = e2.
        return [
            [1.0, 0.0],  # query
            [0.0, 1.0],  # e1: perpendicular → cos 0
            [1.0, 0.0],  # e2: parallel → cos 1
        ]

    hits = similar_questions(
        query_entry_id="self",
        query_text="Welche Last hält die Mutter?",
        candidates=cands,
        chunks=chunks,
        embedder=embedder,
        k=5,
    )
    # Hybrid weighting: 0.5*bm25 + 0.5*cosine. e2 has cosine 1.0 → wins.
    assert hits[0].entry_id == "e2"
    assert hits[0].cosine_score == 1.0
    assert hits[1].cosine_score == 0.0


def test_score_pair_self_similarity_bm25_is_one():
    s = score_pair("Welche Last hält die Schraube?", "Welche Last hält die Schraube?")
    assert s["bm25"] == 1.0
    assert s["cosine"] == 0.0  # no embedder → 0


def test_score_pair_with_embedder():
    def embedder(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0], [0.5, 0.5]]

    s = score_pair("a", "b", embedder=embedder)
    expected = 1 / (2**0.5)  # cosine of (1,0) vs (0.5,0.5) normalized
    assert abs(s["cosine"] - expected) < 1e-9


def test_similar_questions_dataclass_shape():
    hits = similar_questions(
        query_entry_id="self",
        query_text="x",
        candidates=[("e1", "x", "p1-b0")],
        chunks={"p1-b0": "chunk-A"},
        embedder=None,
        k=5,
    )
    assert isinstance(hits[0], SimilarQuestion)
    assert hits[0].entry_id == "e1"
    assert hits[0].chunk == "chunk-A"
