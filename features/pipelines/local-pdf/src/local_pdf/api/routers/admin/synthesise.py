"""Synthesise routes — admin LLM-driven question generation per element.

This is the front of the A.5 synthetic pipeline: we take the local-pdf
``mineru.json`` + ``segments.json`` artifacts, bridge them into the
``goldens.creation.synthetic`` generator via ``MineruElementsLoader``,
and surface the resulting per-element questions (RetrievalEntry) to
the SPA's Synthesise tab.

Endpoints
---------

POST  /api/admin/docs/{slug}/synthesise
      ?box_id=X (sync) | ?page=N (NDJSON) | (no params, full doc, NDJSON)

GET   /api/admin/docs/{slug}/questions               — all (grouped by box_id)
GET   /api/admin/docs/{slug}/questions/{box_id}      — for one box
PATCH /api/admin/docs/{slug}/questions/{question_id} — A.6 refine (text edit)
DELETE /api/admin/docs/{slug}/questions/{question_id} — A.6 deprecate

Cancellation: NDJSON streams check ``request.is_disconnected()`` between
elements and exit cleanly. Already-generated questions stay in the log.

Per the user's direction, ``max_questions_per_element`` is hardcoded
to **5** in this router.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from goldens.creation.synthetic import synthesise_iter
from goldens.operations._time import now_utc_iso
from goldens.operations.deprecate import deprecate as deprecate_op
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.schemas.base import Event, HumanActor
from goldens.storage import (
    GOLDEN_EVENTS_V1_FILENAME,
    iter_active_retrieval_entries,
)
from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_events, read_events
from goldens.storage.projection import build_state
from pydantic import BaseModel

from local_pdf.storage.sidecar import doc_dir
from local_pdf.synthetic import MineruElementsLoader

if TYPE_CHECKING:
    from pathlib import Path

    from llm_clients.base import LLMClient

router = APIRouter()
_logger = logging.getLogger(__name__)

# Test hooks — inject fake LLM clients.
_LLM_CLIENT: LLMClient | None = None
_EMBED_CLIENT: LLMClient | None = None

# Per spec / user direction.
_MAX_QUESTIONS_PER_ELEMENT = 5

# Legacy proof-of-life endpoint kept for backwards compat with any tooling
# poking the playground; the real flow is the new endpoints below.


class SynthesiseTestRequest(BaseModel):
    prompt: str


class SynthesiseTestResponse(BaseModel):
    response: str
    model: str
    elapsed_seconds: float


class RefineQuestionRequest(BaseModel):
    text: str


class GeneratedQuestion(BaseModel):
    entry_id: str
    text: str
    box_id: str


class GenerateBoxResponse(BaseModel):
    box_id: str
    questions: list[GeneratedQuestion]
    accepted: int
    skipped_reason: str | None = None


def _events_path(cfg: Any, slug: str) -> Path:
    path: Path = cfg.data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    return path


def _resolve_clients() -> tuple[LLMClient, LLMClient | None, str, str | None]:
    """Construct (llm_client, embed_client, model, embedding_model).

    Embeddings are optional — when ``OPENAI_EMBEDDING_MODEL`` isn't set
    we pass ``None`` and dedup degrades to text-equality only (acceptable
    for vLLM-without-embeddings deployments).
    """
    if _LLM_CLIENT is not None:
        client = _LLM_CLIENT
    else:
        from local_pdf.llm import get_default_model, get_llm_client

        client = get_llm_client()
        _ = get_default_model  # silence unused-import
    from local_pdf.llm import get_default_model

    model = get_default_model()
    if not model:
        raise HTTPException(
            status_code=500,
            detail="No LLM model configured. Set VLLM_MODEL (or LLM_MODEL).",
        )

    import os

    embed_client: LLMClient | None = _EMBED_CLIENT
    embedding_model = os.environ.get("OPENAI_EMBEDDING_MODEL") or os.environ.get(
        "VLLM_EMBEDDING_MODEL"
    )
    return client, embed_client, model, embedding_model


def _box_id_from_source_element(page: int, bare_id: str) -> str:
    """Reverse synthetic._build_event's element_id stripping (``p{page}-bare``)."""
    return f"p{page}-{bare_id}"


def _list_questions(cfg: Any, slug: str) -> list[GeneratedQuestion]:
    """Read all active retrieval entries for *slug* and project them into
    the SPA's box_id-keyed shape.
    """
    path = _events_path(cfg, slug)
    if not path.exists():
        return []
    out: list[GeneratedQuestion] = []
    for entry in iter_active_retrieval_entries(path):
        src = entry.source_element
        if src is None or src.document_id != slug:
            continue
        out.append(
            GeneratedQuestion(
                entry_id=entry.entry_id,
                text=entry.query,
                box_id=_box_id_from_source_element(src.page_number, src.element_id),
            )
        )
    return out


# ── Legacy ping endpoint ──────────────────────────────────────────────────────


@router.post(
    "/api/admin/docs/{slug}/synthesise/test",
    response_model=SynthesiseTestResponse,
)
async def synthesise_test(
    slug: str,
    body: SynthesiseTestRequest,
    request: Request,
) -> SynthesiseTestResponse:
    """Proof-of-life ping for the configured LLM. Kept for the existing
    placeholder UI / smoke test scripts."""
    cfg = request.app.state.config
    if not doc_dir(cfg.data_root, slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    client, _, model, _ = _resolve_clients()

    from llm_clients.base import Message

    messages = [Message(role="user", content=body.prompt)]
    t0 = time.monotonic()
    completion = client.complete(messages=messages, model=model)
    elapsed = time.monotonic() - t0
    return SynthesiseTestResponse(
        response=completion.text,
        model=completion.model,
        elapsed_seconds=round(elapsed, 3),
    )


# ── Generate ──────────────────────────────────────────────────────────────────


@router.post("/api/admin/docs/{slug}/synthesise")
async def synthesise(
    slug: str,
    request: Request,
    box_id: str | None = None,
    page: int | None = None,
) -> Any:
    """Generate questions for one box (sync) or for a page / full doc (NDJSON).

    Scope is determined by the query params:
      - ``box_id`` set → sync, returns ``GenerateBoxResponse``
      - ``page`` set or both unset → NDJSON stream with cancellation
    """
    cfg = request.app.state.config
    if not doc_dir(cfg.data_root, slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    client, embed_client, model, embedding_model = _resolve_clients()
    events_path = _events_path(cfg, slug)
    events_path.parent.mkdir(parents=True, exist_ok=True)

    loader = MineruElementsLoader(
        data_root=cfg.data_root,
        slug=slug,
        only_box_id=box_id,
        only_page=page,
    )

    if box_id is not None:
        # Sync, single-box path.
        if not loader.elements():
            raise HTTPException(
                status_code=404,
                detail=f"no element with box_id={box_id} (or kind doesn't support questions)",
            )
        before_ids: set[str] = (
            {e.entry_id for e in iter_active_retrieval_entries(events_path)}
            if events_path.exists()
            else set()
        )
        skipped: str | None = None
        for _element, result in synthesise_iter(
            slug=slug,
            loader=loader,
            client=client,
            embed_client=embed_client,
            model=model,
            embedding_model=embedding_model,
            max_questions_per_element=_MAX_QUESTIONS_PER_ELEMENT,
            events_path=events_path,
        ):
            skipped = result.skipped_reason
            break  # only one element by construction
        new_questions = [
            q
            for q in _list_questions(cfg, slug)
            if q.box_id == box_id and q.entry_id not in before_ids
        ]
        return GenerateBoxResponse(
            box_id=box_id,
            questions=new_questions,
            accepted=len(new_questions),
            skipped_reason=skipped,
        )

    # Streaming path (page or full doc).
    async def _stream():
        before_ids = (
            {e.entry_id for e in iter_active_retrieval_entries(events_path)}
            if events_path.exists()
            else set()
        )
        try:
            for element, result in synthesise_iter(
                slug=slug,
                loader=loader,
                client=client,
                embed_client=embed_client,
                model=model,
                embedding_model=embedding_model,
                max_questions_per_element=_MAX_QUESTIONS_PER_ELEMENT,
                events_path=events_path,
            ):
                if await request.is_disconnected():
                    yield json.dumps({"event": "cancelled"}) + "\n"
                    return
                # Find entries produced for this element since the last tick.
                current_active = list(iter_active_retrieval_entries(events_path))
                new_for_element: list[GeneratedQuestion] = []
                for entry in current_active:
                    if entry.entry_id in before_ids:
                        continue
                    src = entry.source_element
                    if src is None:
                        continue
                    bare = element.element_id.split("-", 1)[1]
                    if src.element_id != bare:
                        continue
                    new_for_element.append(
                        GeneratedQuestion(
                            entry_id=entry.entry_id,
                            text=entry.query,
                            box_id=_box_id_from_source_element(src.page_number, src.element_id),
                        )
                    )
                    before_ids.add(entry.entry_id)
                for q in new_for_element:
                    yield (
                        json.dumps(
                            {
                                "event": "question",
                                "element_id": element.element_id,
                                "entry_id": q.entry_id,
                                "text": q.text,
                                "box_id": q.box_id,
                            }
                        )
                        + "\n"
                    )
                yield (
                    json.dumps(
                        {
                            "event": "completed",
                            "element_id": element.element_id,
                            "accepted": len(new_for_element),
                            "skipped_reason": result.skipped_reason,
                        }
                    )
                    + "\n"
                )
                # Yield to the event loop so cancellation can be observed.
                await asyncio.sleep(0)
        except Exception as exc:  # surface as a streamed error, don't crash
            _logger.exception("synthesise stream failed for %s", slug)
            yield json.dumps({"event": "error", "detail": str(exc)}) + "\n"
            return
        yield json.dumps({"event": "done"}) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


# ── Read questions ────────────────────────────────────────────────────────────


@router.get("/api/admin/docs/{slug}/questions")
async def list_questions(slug: str, request: Request) -> dict[str, list[dict]]:
    cfg = request.app.state.config
    if not doc_dir(cfg.data_root, slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    questions = _list_questions(cfg, slug)
    by_box: dict[str, list[dict]] = {}
    for q in questions:
        by_box.setdefault(q.box_id, []).append(q.model_dump(mode="json"))
    return by_box


@router.get("/api/admin/docs/{slug}/questions/{box_id}")
async def list_questions_for_box(slug: str, box_id: str, request: Request) -> list[dict]:
    cfg = request.app.state.config
    if not doc_dir(cfg.data_root, slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    return [q.model_dump(mode="json") for q in _list_questions(cfg, slug) if q.box_id == box_id]


# ── Refine / Deprecate (admin-side editing) ──────────────────────────────────


def _admin_actor(request: Request) -> HumanActor:
    """Build a HumanActor for admin-driven refine / deprecate events.

    The auth layer attaches identity to ``request.state.identity`` for
    authenticated /api/admin requests; falls back to a generic admin
    pseudonym so unit tests without auth still work. ``level`` is
    required by HumanActor — admin actors are ``expert``.
    """
    ident = getattr(request.state, "identity", None)
    name = getattr(ident, "name", None) or "admin"
    return HumanActor(pseudonym=name, level="expert")


@router.patch("/api/admin/docs/{slug}/questions/{question_id}")
async def refine_question(
    slug: str,
    question_id: str,
    body: RefineQuestionRequest,
    request: Request,
) -> dict[str, str]:
    """Admin edits a question's text.

    Inlines the A.6 refine pattern (atomic create-new + deprecate-old) so
    we can preserve the entry's ``source_element`` — the upstream
    ``goldens.operations.refine`` doesn't carry source_element forward,
    which would orphan refined questions from their box.
    """
    cfg = request.app.state.config
    path = _events_path(cfg, slug)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"no questions for {slug}")
    state = build_state(read_events(path))
    if question_id not in state:
        raise HTTPException(status_code=404, detail=f"entry {question_id} not found")
    old = state[question_id]
    if old.deprecated:
        raise HTTPException(status_code=409, detail=f"entry {question_id} already deprecated")

    actor = _admin_actor(request)
    actor_dict = actor.model_dump(mode="json")
    ts = now_utc_iso()
    new_id = new_entry_id()

    entry_data: dict[str, Any] = {
        "query": body.text,
        "expected_chunk_ids": list(old.expected_chunk_ids),
        "chunk_hashes": dict(old.chunk_hashes),
        "refines": question_id,
    }
    if old.source_element is not None:
        entry_data["source_element"] = old.source_element.model_dump(mode="json")

    create_ev = Event(
        event_id=new_event_id(),
        timestamp_utc=ts,
        event_type="created",
        entry_id=new_id,
        schema_version=1,
        payload={
            "task_type": "retrieval",
            "actor": actor_dict,
            # "refined" isn't an allowed Review.action; use the catch-all
            # creation type (matches goldens.operations.refine's default).
            # The relationship to the old entry is encoded via entry_data.refines.
            "action": "created_from_scratch",
            "notes": "admin edit",
            "entry_data": entry_data,
        },
    )
    deprecate_ev = Event(
        event_id=new_event_id(),
        timestamp_utc=ts,
        event_type="deprecated",
        entry_id=question_id,
        schema_version=1,
        payload={"actor": actor_dict, "reason": "superseded by refine"},
    )
    append_events(path, [create_ev, deprecate_ev])
    return {"new_entry_id": new_id}


@router.delete("/api/admin/docs/{slug}/questions/{question_id}")
async def deprecate_question(
    slug: str,
    question_id: str,
    request: Request,
) -> dict[str, str]:
    cfg = request.app.state.config
    path = _events_path(cfg, slug)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"no questions for {slug}")
    try:
        event_id = deprecate_op(
            path,
            question_id,
            actor=_admin_actor(request),
            reason="admin delete",
        )
    except EntryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EntryDeprecatedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"event_id": event_id}
