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

from fastapi import APIRouter, HTTPException, Request
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict

from goldens.api.schemas import (
    CreateEntryRequest,
    CreateEntryResponse,
    DocSummary,
    ElementWithCounts,
)
from goldens.creation.curate import build_created_event
from goldens.creation.elements.adapter import DocumentElement  # noqa: TC001
from goldens.creation.elements.analyze_json import AnalyzeJsonLoader
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
