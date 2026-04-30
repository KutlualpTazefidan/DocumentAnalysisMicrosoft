"""Concrete ElementsLoader backed by Document Intelligence analyze.json.

The loader walks `<outputs_root>/<slug>/analyze/`, picks the
lexicographically latest `*.json`, filters out noise paragraph roles,
maps the rest to DocumentElement, and returns them ordered by
(page, top-y).

Element IDs are content-stable: `p{page}-{first-8-of-sha256(content)}`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from goldens.creation.elements.adapter import DocumentElement
from goldens.schemas import SourceElement

if TYPE_CHECKING:
    from collections.abc import Iterable

    from goldens.schemas import ElementType

_SKIP_ROLES: frozenset[str] = frozenset(
    {
        "pageHeader",
        "pageFooter",
        "pageNumber",
        "footnote",
    }
)

_HEADING_ROLES: frozenset[str] = frozenset({"title", "sectionHeading"})


@dataclass(frozen=True)
class _Positioned:
    """Internal: an element plus its (page, top_y) sort key."""

    page: int
    top_y: float
    element: DocumentElement


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]


def _make_id(page: int, content: str) -> str:
    return f"p{page}-{_content_hash(content)}"


def _bounding_region(raw: dict[str, Any]) -> tuple[int, float] | None:
    regions = raw.get("boundingRegions") or []
    if not regions:
        return None
    region = regions[0]
    page = region.get("pageNumber")
    polygon = region.get("polygon") or []
    if page is None or len(polygon) < 2:
        return None
    return (int(page), float(polygon[1]))


def _table_stub(rows: int, cols: int, cells: Iterable[dict[str, Any]]) -> str:
    """Compact preview: up to 3 rows x 5 cols, '|' separated, '...' truncated."""
    grid: dict[tuple[int, int], str] = {}
    for c in cells:
        r = int(c.get("rowIndex", 0))
        col = int(c.get("columnIndex", 0))
        grid[(r, col)] = (c.get("content") or "").strip()
    preview_rows = []
    for r in range(min(rows, 3)):
        cells_text = [grid.get((r, col), "") for col in range(min(cols, 5))]
        if cols > 5:
            cells_text.append("...")
        preview_rows.append(" | ".join(cells_text))
    if rows > 3:
        preview_rows.append("...")
    return "\n".join(preview_rows)


class AnalyzeJsonLoader:
    """Load DocumentElements from `<outputs_root>/<slug>/analyze/<latest>.json`."""

    slug: str

    def __init__(self, slug: str, *, outputs_root: Path | None = None) -> None:
        self.slug = slug
        self._outputs_root = outputs_root or Path("outputs")

    def elements(self) -> list[DocumentElement]:
        analyze_dir = self._outputs_root / self.slug / "analyze"
        if not analyze_dir.is_dir():
            raise FileNotFoundError(
                f"no analyze/ directory for slug {self.slug!r} at {analyze_dir}"
            )
        candidates = sorted(p for p in analyze_dir.glob("*.json"))
        if not candidates:
            raise FileNotFoundError(
                f"no analyze/*.json files for slug {self.slug!r} at {analyze_dir}"
            )
        raw = json.loads(candidates[-1].read_text(encoding="utf-8"))

        positioned: list[_Positioned] = []
        positioned.extend(self._paragraphs(raw.get("paragraphs") or []))
        positioned.extend(self._tables(raw.get("tables") or []))
        positioned.extend(self._figures(raw.get("figures") or []))
        positioned.sort(key=lambda p: (p.page, p.top_y))
        return [p.element for p in positioned]

    def to_source_element(self, el: DocumentElement) -> SourceElement:
        """Map a DocumentElement to a pipeline-agnostic SourceElement.

        Strips the `p{page}-` prefix from element_id (Category-1 helper
        for A.5 — it must produce the same SourceElement.element_id
        from the same DocumentElement).
        """
        return SourceElement(
            document_id=self.slug,
            page_number=el.page_number,
            element_id=el.element_id.split("-", 1)[1],
            element_type=el.element_type,
        )

    def _paragraphs(self, raws: list[dict[str, Any]]) -> Iterable[_Positioned]:
        for raw in raws:
            role = raw.get("role")
            if role in _SKIP_ROLES:
                continue
            pos = _bounding_region(raw)
            if pos is None:
                continue
            page, top_y = pos
            content = (raw.get("content") or "").strip()
            if not content:
                continue
            element_type: ElementType = "heading" if role in _HEADING_ROLES else "paragraph"
            yield _Positioned(
                page=page,
                top_y=top_y,
                element=DocumentElement(
                    element_id=_make_id(page, content),
                    page_number=page,
                    element_type=element_type,
                    content=content,
                ),
            )

    def _tables(self, raws: list[dict[str, Any]]) -> Iterable[_Positioned]:
        for raw in raws:
            pos = _bounding_region(raw)
            if pos is None:
                continue
            page, top_y = pos
            rows = int(raw.get("rowCount", 0))
            cols = int(raw.get("columnCount", 0))
            cells = raw.get("cells") or []
            stub = _table_stub(rows, cols, cells)
            if not stub.strip():
                continue
            yield _Positioned(
                page=page,
                top_y=top_y,
                element=DocumentElement(
                    element_id=_make_id(page, stub),
                    page_number=page,
                    element_type="table",
                    content=stub,
                    table_dims=(rows, cols),
                ),
            )

    def _figures(self, raws: list[dict[str, Any]]) -> Iterable[_Positioned]:
        for raw in raws:
            pos = _bounding_region(raw)
            if pos is None:
                continue
            page, top_y = pos
            caption_blob = raw.get("caption") or {}
            caption = (caption_blob.get("content") or "").strip()
            if not caption:
                continue
            yield _Positioned(
                page=page,
                top_y=top_y,
                element=DocumentElement(
                    element_id=_make_id(page, caption),
                    page_number=page,
                    element_type="figure",
                    content="",
                    caption=caption,
                ),
            )
