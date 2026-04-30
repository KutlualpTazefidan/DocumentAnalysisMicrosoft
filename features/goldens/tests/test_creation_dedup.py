"""Tests for goldens.creation.synthetic_dedup.QuestionDedup.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.4, §9.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import respx
from goldens.creation.synthetic_dedup import QuestionDedup
from httpx import Response
from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig


@dataclass
class FakeEmbedClient:
    """Minimal LLMClient stand-in: returns deterministic vectors and
    counts how many times `embed` was called with which texts."""

    embeddings: dict[str, list[float]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        self.calls.append(list(texts))
        out: list[list[float]] = []
        for t in texts:
            if t not in self.embeddings:
                # Default: a fixed-dim vector keyed off the string so
                # different strings differ but the same string
                # round-trips identically. Pad/truncate to length 5 so
                # all auto-generated vectors share a dimension and
                # cosine's strict-zip stays happy.
                padded = t.ljust(5, "_")[:5]
                v = [float(ord(c) % 7) for c in padded]
                # Normalise so cosine == 1.0 for identical inputs.
                norm = math.sqrt(sum(x * x for x in v)) or 1.0
                self.embeddings[t] = [x / norm for x in v]
            out.append(self.embeddings[t])
        return out


def test_filter_drops_questions_above_threshold():
    """Two near-identical questions → one kept (the second one is
    dropped because cosine to the first is >= 0.95)."""
    client = FakeEmbedClient()
    # Force identical embeddings for the two near-dups.
    same_vec = [1.0, 0.0, 0.0]
    client.embeddings["Wie groß ist die Last bei M6?"] = same_vec
    client.embeddings["Wie groß ist die Last bei M6 ?"] = same_vec  # paraphrase

    dedup = QuestionDedup(client=client, model="emb", threshold=0.95)
    kept = dedup.filter(
        ["Wie groß ist die Last bei M6?", "Wie groß ist die Last bei M6 ?"],
        against=[],
        source_key="p1-aaaaaaaa",
    )
    assert kept == ["Wie groß ist die Last bei M6?"]


def test_filter_keeps_dissimilar_questions():
    """Two unrelated questions → both kept."""
    client = FakeEmbedClient()
    client.embeddings["Was ist die Norm?"] = [1.0, 0.0, 0.0]
    client.embeddings["Wie schwer ist die Schraube?"] = [0.0, 1.0, 0.0]

    dedup = QuestionDedup(client=client, model="emb", threshold=0.95)
    kept = dedup.filter(
        ["Was ist die Norm?", "Wie schwer ist die Schraube?"],
        against=[],
        source_key="p1-aaaaaaaa",
    )
    assert kept == ["Was ist die Norm?", "Wie schwer ist die Schraube?"]


def test_filter_dedups_within_a_single_call():
    """A single filter([q1, q1_paraphrase], existing=[]) call must
    keep only one — the second is matched against the first that was
    just kept in the same call."""
    client = FakeEmbedClient()
    same_vec = [1.0, 0.0, 0.0]
    client.embeddings["X?"] = same_vec
    client.embeddings["X ?"] = same_vec

    dedup = QuestionDedup(client=client, model="emb", threshold=0.95)
    kept = dedup.filter(["X?", "X ?"], against=[], source_key="p1-aaaaaaaa")
    assert kept == ["X?"]


def test_disabled_when_client_is_none_returns_input_and_warns(caplog):
    """`client=None` → filter returns the generated list unchanged
    and logs a single WARNING for the session."""
    dedup = QuestionDedup(client=None, model="emb", threshold=0.95)
    with caplog.at_level(logging.WARNING):
        kept_a = dedup.filter(["q1", "q2"], against=[], source_key="src1")
        kept_b = dedup.filter(["q3"], against=[], source_key="src2")
    assert kept_a == ["q1", "q2"]
    assert kept_b == ["q3"]
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    # Exactly one warning per session, not one per call.
    assert len(warnings) == 1
    assert "dedup disabled" in warnings[0].getMessage().lower()


def test_caches_existing_embeddings_per_source_key():
    """Two filter calls for the same source_key with the same
    `against` list → embed_client.embed is called for `against` only
    on the first call, not the second."""
    client = FakeEmbedClient()
    dedup = QuestionDedup(client=client, model="emb", threshold=0.95)

    dedup.filter(["new1"], against=["existing1", "existing2"], source_key="src1")
    first_call_count = len(client.calls)
    dedup.filter(["new2"], against=["existing1", "existing2"], source_key="src1")
    second_call_count = len(client.calls)

    # First filter: at most 2 calls (one for `against`, one for
    # `generated`). Second filter: only `generated` is re-embedded —
    # `against` is cached. So the delta is exactly 1.
    assert second_call_count - first_call_count == 1
    # And the cached call must NOT contain "existing1"/"existing2".
    last_payload = client.calls[-1]
    assert "existing1" not in last_payload
    assert "existing2" not in last_payload


def test_filter_with_empty_generated_returns_empty_list():
    """Defensive branch: an empty `generated` list short-circuits to
    `[]` without calling embed for the generated side."""
    client = FakeEmbedClient()
    dedup = QuestionDedup(client=client, model="emb", threshold=0.95)
    kept = dedup.filter([], against=["existing"], source_key="src1")
    assert kept == []
    # Only the `against` list was embedded — `generated` side was
    # short-circuited.
    assert client.calls == [["existing"]]


@respx.mock
def test_filter_works_end_to_end_with_openai_direct_client():
    """Smoke: QuestionDedup wired against the real OpenAIDirectClient
    + respx-mocked embeddings endpoint. Proves the dedup helper does
    not depend on FakeEmbedClient internals."""
    cfg = OpenAIDirectConfig(api_key="sk-test", base_url="https://api.openai.com/v1")
    client = OpenAIDirectClient(cfg)
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [1.0, 0.0, 0.0]},
                    {"object": "embedding", "index": 1, "embedding": [1.0, 0.0, 0.0]},
                ],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )
    )
    dedup = QuestionDedup(client=client, model="text-embedding-3-large", threshold=0.95)
    kept = dedup.filter(["q same", "q same too"], against=[], source_key="p1-z")
    assert len(kept) == 1
