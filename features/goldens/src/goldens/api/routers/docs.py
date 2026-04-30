"""Slug-scoped routes:

- GET  /api/docs                                              — list slugs
- GET  /api/docs/{slug}/elements                              — element list (Task 9)
- GET  /api/docs/{slug}/elements/{element_id}                 — element detail (Task 10)
- POST /api/docs/{slug}/elements/{element_id}/entries         — create entry (Task 11)
- POST /api/docs/{slug}/synthesise                            — streaming (Task 13)
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from fastapi import APIRouter, Request

from goldens.api.schemas import DocSummary
from goldens.creation.elements.analyze_json import AnalyzeJsonLoader

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
