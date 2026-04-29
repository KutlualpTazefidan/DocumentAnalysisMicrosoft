"""Tests for goldens.schemas.retrieval — RetrievalEntry,
serialization, and the level derivation."""

from __future__ import annotations

import pytest
from goldens.schemas.base import HumanActor, LLMActor, Review
from goldens.schemas.retrieval import RetrievalEntry


def _human_review(level: str, ts: str = "2026-04-28T10:00:00Z") -> Review:
    return Review(
        timestamp_utc=ts,
        action="approved",
        actor=HumanActor(pseudonym=f"alice-{level}", level=level),  # type: ignore[arg-type]
        notes=None,
    )


def _llm_review(ts: str = "2026-04-28T10:00:00Z") -> Review:
    return Review(
        timestamp_utc=ts,
        action="synthesised",
        actor=LLMActor(
            model="gpt-4o",
            model_version="2024-08-06",
            prompt_template_version="v1",
            temperature=0.0,
        ),
        notes=None,
    )


def _entry(
    *,
    entry_id: str = "r1",
    review_chain: tuple[Review, ...] = (),
    deprecated: bool = False,
    refines: str | None = None,
) -> RetrievalEntry:
    return RetrievalEntry(
        entry_id=entry_id,
        query="What is X?",
        expected_chunk_ids=("c1", "c2"),
        chunk_hashes={"c1": "sha256:aaa", "c2": "sha256:bbb"},
        review_chain=review_chain,
        deprecated=deprecated,
        refines=refines,
    )


# --- Construction & validation -----------------------------------


def test_default_task_type_is_retrieval():
    e = _entry()
    assert e.task_type == "retrieval"


def test_default_refines_is_none():
    e = _entry()
    assert e.refines is None


def test_rejects_empty_entry_id():
    with pytest.raises(ValueError, match="entry_id"):
        RetrievalEntry(
            entry_id="",
            query="q",
            expected_chunk_ids=("c1",),
            chunk_hashes={"c1": "sha256:aaa"},
            review_chain=(),
            deprecated=False,
        )


def test_rejects_empty_query():
    with pytest.raises(ValueError, match="query"):
        RetrievalEntry(
            entry_id="r1",
            query="",
            expected_chunk_ids=("c1",),
            chunk_hashes={"c1": "sha256:aaa"},
            review_chain=(),
            deprecated=False,
        )


# --- level property ----------------------------------------------


def test_level_synthetic_when_no_human():
    e = _entry(review_chain=(_llm_review(),))
    assert e.level == "synthetic"


def test_level_synthetic_when_review_chain_empty():
    e = _entry(review_chain=())
    assert e.level == "synthetic"


def test_level_expert_wins_over_lower():
    e = _entry(
        review_chain=(
            _human_review("bachelors"),
            _human_review("expert"),
            _human_review("phd"),
        )
    )
    assert e.level == "expert"


def test_level_phd_when_only_phd_and_below():
    e = _entry(
        review_chain=(
            _human_review("masters"),
            _human_review("phd"),
            _human_review("other"),
        )
    )
    assert e.level == "phd"


def test_level_masters_when_only_masters_and_below():
    e = _entry(review_chain=(_human_review("masters"), _human_review("other")))
    assert e.level == "masters"


def test_level_bachelors_when_only_bachelors_and_other():
    e = _entry(review_chain=(_human_review("bachelors"), _human_review("other")))
    assert e.level == "bachelors"


def test_level_other_when_only_other():
    e = _entry(review_chain=(_human_review("other"),))
    assert e.level == "other"


def test_level_humans_outrank_llm_in_chain():
    e = _entry(review_chain=(_llm_review(), _human_review("phd")))
    assert e.level == "phd"


# --- Serialization round-trips -----------------------------------


def test_round_trip_minimal():
    e = _entry()
    assert RetrievalEntry.from_dict(e.to_dict()) == e


def test_round_trip_with_review_chain():
    e = _entry(
        review_chain=(_human_review("expert"), _llm_review()),
        deprecated=True,
        refines="r0",
    )
    restored = RetrievalEntry.from_dict(e.to_dict())
    assert restored == e
    assert isinstance(restored.review_chain[0].actor, HumanActor)
    assert restored.review_chain[0].actor.level == "expert"


def test_from_dict_ignores_unknown_keys():
    e = _entry()
    d = e.to_dict()
    d["future_field"] = "ignored"
    restored = RetrievalEntry.from_dict(d)
    assert restored == e


def test_to_dict_returns_lists_for_tuples():
    """Serialised form must use plain JSON types — tuples become lists."""
    e = _entry()
    d = e.to_dict()
    assert isinstance(d["expected_chunk_ids"], list)
    assert isinstance(d["review_chain"], list)
