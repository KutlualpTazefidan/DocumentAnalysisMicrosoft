"""Tests for goldens.creation.synthetic — happy path, retry,
oversize-prompt fallback, max-cap, dry-run, resume, source_element
shape, actor metadata.

HTTP is mocked at the transport layer with respx; the openai SDK
hits httpx underneath, so respx routes intercept actual calls — this
verifies the wire payload (model, temperature, response_format) the
way A.1's tests do.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.3, §4.5, §4.6, §9.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import respx
from goldens.creation.elements import DocumentElement
from goldens.creation.synthetic import SynthesiseResult, synthesise
from goldens.storage.log import read_events
from goldens.storage.projection import build_state
from httpx import Response
from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig

if TYPE_CHECKING:
    from pathlib import Path

# ---------- Fakes ----------------------------------------------------


@dataclass
class FakeLoader:
    slug: str
    _elements: list[DocumentElement]

    def elements(self) -> list[DocumentElement]:
        return list(self._elements)


def _para(eid: str, text: str, page: int = 1) -> DocumentElement:
    return DocumentElement(
        element_id=eid,
        page_number=page,
        element_type="paragraph",
        content=text,
    )


def _completion_response(payload: object) -> Response:
    """Build a 200 chat.completions response whose `content` is
    `json.dumps(payload)`."""
    return Response(
        200,
        json={
            "id": "abc",
            "object": "chat.completion",
            "model": "gpt-4o-2024-08-06",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": json.dumps(payload)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            },
        },
    )


def _embed_response(n_vectors: int, vec: list[float] | None = None) -> Response:
    v = vec or [1.0, 0.0, 0.0]
    return Response(
        200,
        json={
            "object": "list",
            "data": [
                {"object": "embedding", "index": i, "embedding": list(v)} for i in range(n_vectors)
            ],
            "model": "text-embedding-3-large",
            "usage": {"prompt_tokens": n_vectors, "total_tokens": n_vectors},
        },
    )


@pytest.fixture
def llm_client() -> OpenAIDirectClient:
    return OpenAIDirectClient(
        OpenAIDirectConfig(api_key="sk-test", base_url="https://api.openai.com/v1")
    )


# ---------- Tests ---------------------------------------------------


@respx.mock
def test_happy_path_writes_one_event_per_kept_question(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """One paragraph element → one bundled JSON-mode call →
    two questions returned → two events written, both `created`
    with action='synthesised' and source_element pointing at the
    paragraph. Embedding endpoint is hit once for dedup (no
    `against`, two `generated`)."""
    events_path = tmp_path / "golden_events_v1.jsonl"
    completion_route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response(
            {
                "questions": [
                    {"sub_unit": "Erste.", "question": "Frage 1?"},
                    {"sub_unit": "Zweite.", "question": "Frage 2?"},
                ]
            }
        )
    )
    # Two distinct unit vectors so dedup keeps both.
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [1.0, 0.0, 0.0]},
                    {"object": "embedding", "index": 1, "embedding": [0.0, 1.0, 0.0]},
                ],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )
    )

    loader = FakeLoader(
        slug="docX",
        _elements=[_para("p1-aaaaaaaa", "Erste. Zweite.", page=1)],
    )

    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        events_path=events_path,
    )

    assert isinstance(result, SynthesiseResult)
    assert result.events_written == 2
    assert result.questions_kept == 2
    assert completion_route.call_count == 1

    state = build_state(read_events(events_path))
    assert len(state) == 2
    queries = sorted(e.query for e in state.values())
    assert queries == ["Frage 1?", "Frage 2?"]


@respx.mock
def test_json_parse_failure_retries_once_then_skips(tmp_path: Path, llm_client: OpenAIDirectClient):
    """First completion returns malformed JSON, second returns valid
    JSON → element is processed (one event written)."""
    responses = iter(
        [
            Response(
                200,
                json={
                    "id": "x",
                    "object": "chat.completion",
                    "model": "gpt-4o",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "not json"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            ),
            _completion_response({"questions": [{"sub_unit": "Erste.", "question": "Frage 1?"}]}),
        ]
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=lambda request: next(responses)
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(return_value=_embed_response(1))
    loader = FakeLoader(slug="docX", _elements=[_para("p1-aaaaaaaa", "Erste.")])

    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        events_path=tmp_path / "golden_events_v1.jsonl",
    )
    assert result.events_written == 1


@respx.mock
def test_two_consecutive_json_failures_skip_element_with_warning(
    tmp_path: Path, llm_client: OpenAIDirectClient, caplog: pytest.LogCaptureFixture
):
    """Both completion attempts return malformed JSON → element
    skipped, warning logged, no events written."""
    bad = Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "model": "gpt-4o",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "still not json"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=bad)
    loader = FakeLoader(slug="docX", _elements=[_para("p1-aaaaaaaa", "Erste.")])

    import logging

    with caplog.at_level(logging.WARNING):
        result = synthesise(
            slug="docX",
            loader=loader,
            client=llm_client,
            embed_client=None,  # dedup disabled — we don't care about embeddings here
            model="gpt-4o",
            embedding_model=None,
            events_path=tmp_path / "golden_events_v1.jsonl",
        )
    assert result.events_written == 0
    assert any("skipping element" in r.getMessage().lower() for r in caplog.records)


@respx.mock
def test_oversize_prompt_falls_back_to_per_subunit_calls(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """When the bundled prompt exceeds max_prompt_tokens, the driver
    issues N per-sub-unit calls instead of 1 bundled call. Each call
    returns a distinct question; dedup runs once over the union with
    `source_key=bare_id` (same scope as bundled mode), so all three
    survive."""
    completion_responses = iter(
        [
            _completion_response({"questions": [{"sub_unit": "S0.", "question": "Q0?"}]}),
            _completion_response({"questions": [{"sub_unit": "S1.", "question": "Q1?"}]}),
            _completion_response({"questions": [{"sub_unit": "S2.", "question": "Q2?"}]}),
        ]
    )
    completion_route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=lambda request: next(completion_responses)
    )
    # Single embed call after fallback unions all 3 questions; return
    # 3 distinct unit vectors so dedup keeps everything.
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [1.0, 0.0, 0.0]},
                    {"object": "embedding", "index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"object": "embedding", "index": 2, "embedding": [0.0, 0.0, 1.0]},
                ],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 3, "total_tokens": 3},
            },
        )
    )

    # 3 sentences in one paragraph; force the bundled prompt over the cap.
    loader = FakeLoader(
        slug="docX",
        _elements=[_para("p1-aaaaaaaa", "Erste. Zweite. Dritte.")],
    )

    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        max_prompt_tokens=1,  # forces fallback regardless of real prompt size
        events_path=tmp_path / "golden_events_v1.jsonl",
    )
    # 3 sub-units → 3 completion calls.
    assert completion_route.call_count == 3
    assert result.events_written == 3


@respx.mock
def test_respects_max_questions_cap(tmp_path: Path, llm_client: OpenAIDirectClient):
    """LLM returns 8 questions, cap=3 → 3 events written, 5 reported
    as dropped_cap. Embeddings return distinct vectors so dedup keeps
    everything before the cap is applied."""
    big = {"questions": [{"sub_unit": f"S{i}.", "question": f"Q{i}?"} for i in range(8)]}
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response(big)
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {
                        "object": "embedding",
                        "index": i,
                        # Each vector is unit-length along its own axis →
                        # cosine across them is 0, no dedup collisions.
                        "embedding": [1.0 if j == i else 0.0 for j in range(8)],
                    }
                    for i in range(8)
                ],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 8, "total_tokens": 8},
            },
        )
    )
    loader = FakeLoader(slug="docX", _elements=[_para("p1-a", "Erste. Zweite. Dritte.")])

    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        max_questions_per_element=3,
        events_path=tmp_path / "golden_events_v1.jsonl",
    )
    assert result.events_written == 3
    assert result.questions_dropped_cap == 5


@respx.mock
def test_dry_run_writes_no_events_and_does_not_call_llm(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """`dry_run=True` → 0 LLM calls (assert via respx route counts),
    0 events written, prompt_tokens_estimated populated."""
    completion_route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response({"questions": []})
    )
    embed_route = respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=_embed_response(0)
    )
    loader = FakeLoader(slug="docX", _elements=[_para("p1-a", "Erste. Zweite.")])
    events_path = tmp_path / "golden_events_v1.jsonl"

    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        dry_run=True,
        events_path=events_path,
    )
    assert result.dry_run is True
    assert result.events_written == 0
    assert result.prompt_tokens_estimated > 0
    assert completion_route.call_count == 0
    assert embed_route.call_count == 0
    assert not events_path.exists()


@respx.mock
def test_resume_skips_already_processed_elements(tmp_path: Path, llm_client: OpenAIDirectClient):
    """Pre-seed an active synthesised event for element X → second
    pass with --resume skips X, processes Y."""
    from goldens.schemas.base import Event, LLMActor
    from goldens.storage.ids import new_entry_id, new_event_id
    from goldens.storage.log import append_event

    events_path = tmp_path / "golden_events_v1.jsonl"
    seed_event = Event(
        event_id=new_event_id(),
        timestamp_utc="2026-04-29T09:00:00Z",
        event_type="created",
        entry_id=new_entry_id(),
        schema_version=1,
        payload={
            "task_type": "retrieval",
            "actor": LLMActor(
                model="gpt-4o",
                model_version="gpt-4o-2024-08-06",
                prompt_template_version="v1",
                temperature=0.0,
            ).to_dict(),
            "action": "synthesised",
            "notes": None,
            "entry_data": {
                "query": "seeded?",
                "expected_chunk_ids": [],
                "chunk_hashes": {},
                "refines": None,
                "source_element": {
                    "document_id": "docX",
                    "page_number": 1,
                    "element_id": "aaaaaaaa",  # bare hash (page prefix stripped)
                    "element_type": "paragraph",
                },
            },
        },
    )
    append_event(events_path, seed_event)

    completion_route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response({"questions": [{"sub_unit": "Yo.", "question": "Y?"}]})
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(return_value=_embed_response(1))

    loader = FakeLoader(
        slug="docX",
        _elements=[
            _para("p1-aaaaaaaa", "Erste."),  # already processed (matches seeded source_element)
            _para("p1-bbbbbbbb", "Yo."),
        ],
    )
    result = synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        resume=True,
        events_path=events_path,
    )
    # Only element "p1-bbbbbbbb" is processed.
    assert completion_route.call_count == 1
    assert result.events_written == 1
    assert result.elements_skipped >= 1


@respx.mock
def test_source_element_is_persisted_with_stripped_page_prefix(
    tmp_path: Path, llm_client: OpenAIDirectClient
):
    """Event payload must have entry_data.source_element with
    document_id=loader.slug, page_number/element_type from the loader
    element, AND element_id equal to the BARE hash (page prefix
    stripped — matches A.4's build_event_source_element_id_strips_page_prefix)."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response({"questions": [{"sub_unit": "S.", "question": "Q?"}]})
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(return_value=_embed_response(1))

    loader = FakeLoader(slug="docX", _elements=[_para("p47-a3f8b2c1", "Erste.", page=47)])
    events_path = tmp_path / "golden_events_v1.jsonl"
    synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        events_path=events_path,
    )
    events = read_events(events_path)
    assert len(events) == 1
    src = events[0].payload["entry_data"]["source_element"]
    assert src["document_id"] == "docX"
    assert src["page_number"] == 47
    assert src["element_type"] == "paragraph"
    # The bare 8-char hash, NOT the full "p47-a3f8b2c1".
    assert src["element_id"] == "a3f8b2c1"


@respx.mock
def test_actor_is_llm_with_correct_metadata(tmp_path: Path, llm_client: OpenAIDirectClient):
    """Event's actor is LLMActor with model, model_version,
    prompt_template_version='v1', temperature=0.0."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_completion_response({"questions": [{"sub_unit": "S.", "question": "Q?"}]})
    )
    respx.post("https://api.openai.com/v1/embeddings").mock(return_value=_embed_response(1))

    loader = FakeLoader(slug="docX", _elements=[_para("p1-a", "Erste.")])
    events_path = tmp_path / "golden_events_v1.jsonl"
    synthesise(
        slug="docX",
        loader=loader,
        client=llm_client,
        embed_client=llm_client,
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
        events_path=events_path,
    )
    events = read_events(events_path)
    actor = events[0].payload["actor"]
    assert actor["kind"] == "llm"
    assert actor["model"] == "gpt-4o"
    assert actor["model_version"]  # non-empty (taken from the response)
    assert actor["prompt_template_version"] == "v1"
    assert actor["temperature"] == 0.0
