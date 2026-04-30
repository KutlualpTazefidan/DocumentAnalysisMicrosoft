"""Slug-scoped routes:

- GET  /api/docs                                              — list slugs
- GET  /api/docs/{slug}/elements                              — element list (Task 9)
- GET  /api/docs/{slug}/elements/{element_id}                 — element detail (Task 10)
- POST /api/docs/{slug}/elements/{element_id}/entries         — create entry (Task 11)
- POST /api/docs/{slug}/synthesise                            — streaming (Task 13)
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from goldens.api.schemas import (
    CreateEntryRequest,
    CreateEntryResponse,
    DocSummary,
    ElementWithCounts,
    SynthCompleteLine,
    SynthElementLine,
    SynthErrorLine,
    SynthesiseRequest,
    SynthStartLine,
)
from goldens.creation.curate import build_created_event
from goldens.creation.elements.adapter import DocumentElement  # noqa: TC001
from goldens.creation.elements.analyze_json import AnalyzeJsonLoader
from goldens.creation.synthetic import synthesise_iter
from goldens.schemas import ElementType  # noqa: F401
from goldens.schemas.retrieval import RetrievalEntry  # noqa: TC001
from goldens.storage import GOLDEN_EVENTS_V1_FILENAME, append_event
from goldens.storage.projection import iter_active_retrieval_entries


class ElementDetailResponse(BaseModel):
    """Used as response_model for GET /api/docs/{slug}/elements/{element_id}.

    Lives next to the route because it's purely an aggregate view of one
    element + its active entries.
    """

    model_config = ConfigDict(frozen=True)

    element: DocumentElement
    entries: list[RetrievalEntry]


ElementDetailResponse.model_rebuild()

router = APIRouter()


@router.get("/api/docs", response_model=list[DocSummary])
async def list_docs(request: Request) -> list[DocSummary]:
    data_root: Path = request.app.state.config.data_root
    summaries: list[DocSummary] = []
    if not data_root.is_dir():
        return summaries
    for child in sorted(data_root.iterdir()):
        if not child.is_dir():
            continue
        analyze = child / "analyze"
        if not analyze.is_dir() or not any(analyze.glob("*.json")):
            continue
        loader = AnalyzeJsonLoader(child.name, outputs_root=data_root)
        elements = loader.elements()
        summaries.append(DocSummary(slug=child.name, element_count=len(elements)))
    return summaries


def _count_entries_per_element(data_root: Path, slug: str) -> dict[str, int]:
    """Bare-element-id → number of active retrieval entries projected from the log."""
    log = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    if not log.exists():
        return {}
    counts: dict[str, int] = defaultdict(int)
    for entry in iter_active_retrieval_entries(log):
        if entry.source_element is not None:
            counts[entry.source_element.element_id] += 1
    return counts


@router.get("/api/docs/{slug}/elements", response_model=list[ElementWithCounts])
async def list_elements(slug: str, request: Request) -> list[ElementWithCounts]:
    data_root: Path = request.app.state.config.data_root
    loader = AnalyzeJsonLoader(slug, outputs_root=data_root)
    elements = loader.elements()  # raises FileNotFoundError → 404 via app handler
    counts = _count_entries_per_element(data_root, slug)
    return [
        ElementWithCounts(
            element=el,
            count_active_entries=counts.get(el.element_id.split("-", 1)[1], 0),
        )
        for el in elements
    ]


@router.get(
    "/api/docs/{slug}/elements/{element_id}",
    response_model=ElementDetailResponse,
)
async def get_element(
    slug: str,
    element_id: str,
    request: Request,
) -> ElementDetailResponse:
    data_root: Path = request.app.state.config.data_root
    loader = AnalyzeJsonLoader(slug, outputs_root=data_root)
    elements = loader.elements()
    matching = next(
        (el for el in elements if el.element_id == element_id),
        None,
    )
    if matching is None:
        raise HTTPException(status_code=404, detail=f"element {element_id} not found in {slug}")

    log = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    bare = element_id.split("-", 1)[1] if "-" in element_id else element_id
    entries: list[RetrievalEntry] = []
    if log.exists():
        for entry in iter_active_retrieval_entries(log):
            if entry.source_element is not None and entry.source_element.element_id == bare:
                entries.append(entry)

    return ElementDetailResponse(element=matching, entries=entries)


@router.post(
    "/api/docs/{slug}/elements/{element_id}/entries",
    response_model=CreateEntryResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_entry(
    slug: str,
    element_id: str,
    body: CreateEntryRequest,
    request: Request,
) -> CreateEntryResponse:
    data_root: Path = request.app.state.config.data_root
    identity = request.app.state.identity

    loader = AnalyzeJsonLoader(slug, outputs_root=data_root)
    elements = loader.elements()
    matching = next((el for el in elements if el.element_id == element_id), None)
    if matching is None:
        raise HTTPException(status_code=404, detail=f"element {element_id} not found in {slug}")

    event = build_created_event(
        question=body.query,
        element=matching,
        loader=loader,
        identity=identity,
    )
    log = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    log.parent.mkdir(parents=True, exist_ok=True)
    append_event(log, event)

    return CreateEntryResponse(
        entry_id=event.entry_id,
        event_id=event.event_id,
    )


@router.post("/api/docs/{slug}/synthesise")
async def synthesise_stream(
    slug: str,
    body: SynthesiseRequest,
    request: Request,
) -> StreamingResponse:
    data_root: Path = request.app.state.config.data_root

    # Resolve loader BEFORE starting the stream so a SlugUnknown raises a
    # clean 404 (the exception handler kicks in before any chunked transfer).
    loader = AnalyzeJsonLoader(slug, outputs_root=data_root)
    elements = loader.elements()  # raises FileNotFoundError → 404

    events_path = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME

    # Lazy-build the LLM client only when not in dry_run.
    completion_client = None
    embedding_model = body.embedding_model
    embed_client = None
    if not body.dry_run:
        import os

        from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig

        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=400, detail="LLM_API_KEY env var required for non-dry-run"
            )
        base_url = body.llm_base_url or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
        completion_client = OpenAIDirectClient(
            OpenAIDirectConfig(api_key=api_key, base_url=base_url),
        )
        # Embedding-client mirrors the CLI synthesise_cmd logic.
        openai_key = os.environ.get("OPENAI_API_KEY")
        if embedding_model and openai_key:
            embed_client = OpenAIDirectClient(
                OpenAIDirectConfig(api_key=openai_key, base_url="https://api.openai.com/v1"),
            )
        elif openai_key and not embedding_model:
            embedding_model = "text-embedding-3-large"
            embed_client = OpenAIDirectClient(
                OpenAIDirectConfig(api_key=openai_key, base_url="https://api.openai.com/v1"),
            )

    async def _stream() -> AsyncIterator[bytes]:
        # SynthStartLine (with total)
        start = SynthStartLine(total_elements=len(elements))
        yield (start.model_dump_json() + "\n").encode("utf-8")

        events_written = 0
        prompt_tokens = 0
        try:
            for element, result in synthesise_iter(
                slug=slug,
                loader=loader,
                client=completion_client,
                embed_client=embed_client,
                model=body.llm_model,
                embedding_model=embedding_model,
                prompt_template_version=body.prompt_template_version,
                temperature=body.temperature,
                max_questions_per_element=body.max_questions_per_element,
                max_prompt_tokens=body.max_prompt_tokens,
                start_from=body.start_from,
                limit=body.limit,
                dry_run=body.dry_run,
                resume=body.resume,
                events_path=events_path,
            ):
                line = SynthElementLine(
                    element_id=element.element_id,
                    kept=result.kept,
                    skipped_reason=result.skipped_reason,
                    tokens_estimated=result.tokens_estimated,
                )
                events_written += result.kept
                prompt_tokens += result.tokens_estimated
                yield (line.model_dump_json() + "\n").encode("utf-8")
        except Exception as e:  # pragma: no cover (hard to test deterministically)
            err = SynthErrorLine(reason=str(e))
            yield (err.model_dump_json() + "\n").encode("utf-8")
        finally:
            done = SynthCompleteLine(
                events_written=events_written,
                prompt_tokens_estimated=prompt_tokens,
            )
            yield (done.model_dump_json() + "\n").encode("utf-8")

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
