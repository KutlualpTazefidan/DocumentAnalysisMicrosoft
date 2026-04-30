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

from fastapi import APIRouter, Request

from goldens.api.schemas import DocSummary, ElementWithCounts
from goldens.creation.elements.analyze_json import AnalyzeJsonLoader
from goldens.storage import GOLDEN_EVENTS_V1_FILENAME
from goldens.storage.projection import iter_active_retrieval_entries

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
