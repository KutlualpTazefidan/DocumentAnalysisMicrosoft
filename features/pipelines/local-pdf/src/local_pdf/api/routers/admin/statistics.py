"""Statistics — read-only aggregators powering the Statistik tab.

v1 is C1 live-scan: every request walks the on-disk artifacts. See
docs/superpowers/specs/2026-06-03-statistics-and-voting-design.md
for the V2 (DuckDB) trigger.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from fastapi import APIRouter, HTTPException, Request

from local_pdf.api.models.statistics import (
    DiagnosticCounts,
    ExtractStats,
)
from local_pdf.auth.tenant_root import tenant_data_root, tenant_slug_from_request
from local_pdf.storage.sidecar import doc_dir, read_mineru, read_segments

router = APIRouter()

_REGISTER_KINDS = {"toc", "list_of_tables", "list_of_figures", "bibliography"}


def _tr(request: Request) -> Path:
    raw = request.app.state.config.data_root
    return tenant_data_root(raw, tenant_slug_from_request(request))


def _count_diagnostics(mineru: dict | None) -> DiagnosticCounts:
    diags = (mineru or {}).get("diagnostics") or []
    elements = (mineru or {}).get("elements") or []
    split = sum(1 for d in diags if d.get("kind") == "split")
    nodecomp = sum(1 for d in diags if d.get("kind") == "no_decomposition")
    total = len(elements)
    clean = max(total - split - nodecomp, 0)
    return DiagnosticCounts(split=split, no_decomposition=nodecomp, clean=clean, total=total)


def _count_register_boxes(segments: dict | None) -> tuple[int, int]:
    boxes = (segments or {}).get("boxes") or []
    total = len(boxes)
    reg = sum(1 for b in boxes if b.get("kind") in _REGISTER_KINDS)
    return reg, total


@router.get("/api/admin/statistics/extract/{slug}", response_model=ExtractStats)
async def extract_stats(slug: str, request: Request) -> ExtractStats:
    data_root = _tr(request)
    if not doc_dir(data_root, slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    mineru = read_mineru(data_root, slug)
    segments_file = read_segments(data_root, slug)
    segments_dict = segments_file.model_dump() if segments_file is not None else None
    reg, total_boxes = _count_register_boxes(segments_dict)
    diag = _count_diagnostics(mineru)
    rate = (reg / total_boxes) if total_boxes > 0 else None
    return ExtractStats(
        slug=slug,
        diagnostics=diag,
        register_boxes=reg,
        total_boxes=total_boxes,
        register_rate=rate,
    )
