"""Validation tests for API-only Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_create_entry_request_requires_non_empty_query() -> None:
    from goldens.api.schemas import CreateEntryRequest

    with pytest.raises(ValidationError):
        CreateEntryRequest(query="")
    assert CreateEntryRequest(query="Was ist X?").query == "Was ist X?"


def test_synthesise_request_defaults() -> None:
    from goldens.api.schemas import SynthesiseRequest

    req = SynthesiseRequest(llm_model="gpt-4o-mini")
    assert req.dry_run is False
    assert req.max_questions_per_element == 20
    assert req.max_prompt_tokens == 8000
    assert req.prompt_template_version == "v1"
    assert req.temperature == 0.0
    assert req.start_from is None
    assert req.limit is None
    assert req.embedding_model is None
    assert req.resume is False


def test_synthesise_request_round_trip_keeps_values() -> None:
    from goldens.api.schemas import SynthesiseRequest

    req = SynthesiseRequest(
        llm_model="gpt-4o-mini",
        dry_run=True,
        max_questions_per_element=5,
        start_from="p1-aaa",
    )
    assert req.dry_run is True
    assert req.max_questions_per_element == 5
    assert req.start_from == "p1-aaa"


def test_synth_line_discriminator_dispatches_correctly() -> None:
    from goldens.api.schemas import (
        SynthCompleteLine,
        SynthElementLine,
        SynthErrorLine,
        SynthLine,
        SynthStartLine,
    )
    from pydantic import TypeAdapter

    adapter: TypeAdapter[SynthStartLine | SynthElementLine | SynthCompleteLine | SynthErrorLine] = (
        TypeAdapter(SynthLine)
    )
    assert isinstance(
        adapter.validate_python({"type": "start", "total_elements": 5}), SynthStartLine
    )
    assert isinstance(
        adapter.validate_python(
            {
                "type": "element",
                "element_id": "p1-aaa",
                "kept": 3,
                "skipped_reason": None,
                "tokens_estimated": 30,
            }
        ),
        SynthElementLine,
    )
    assert isinstance(
        adapter.validate_python({"type": "error", "element_id": "p1-aaa", "reason": "rate-limit"}),
        SynthErrorLine,
    )
    assert isinstance(
        adapter.validate_python(
            {"type": "complete", "events_written": 9, "prompt_tokens_estimated": 1234}
        ),
        SynthCompleteLine,
    )


def test_element_with_counts_composes_document_element() -> None:
    from goldens.api.schemas import ElementWithCounts
    from goldens.creation.elements.adapter import DocumentElement

    el = DocumentElement(
        element_id="p1-aaa",
        page_number=1,
        element_type="paragraph",
        content="Body.",
    )
    wrap = ElementWithCounts(element=el, count_active_entries=2)
    dumped = wrap.model_dump(mode="json")
    assert dumped["element"]["element_id"] == "p1-aaa"
    assert dumped["count_active_entries"] == 2


def test_health_response_default() -> None:
    from goldens.api.schemas import HealthResponse

    h = HealthResponse(goldens_root="outputs")
    assert h.status == "ok"
    assert h.goldens_root == "outputs"
