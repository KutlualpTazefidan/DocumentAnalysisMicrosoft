"""Searcher Protocol + InDocSearcher — v1 of the provenance corpus.

The Searcher Protocol is the seam for Stages 5+ to swap in
CrossDocSearcher (every locally-extracted slug) or AzureSearcher
(existing Azure AI Search indexes) without touching the Provenienz
step routes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003
from typing import Protocol

from local_pdf.comparison.bm25 import bm25_scores
from local_pdf.provenienz.registers import REGISTER_KINDS
from local_pdf.provenienz.text import strip_html
from local_pdf.storage.sidecar import read_mineru, read_segments


@dataclass(frozen=True)
class SearchHit:
    box_id: str
    text: str
    score: float
    doc_slug: str
    searcher: str  # name of the producing Searcher instance


class Searcher(Protocol):
    name: str

    def search(self, query: str, *, top_k: int) -> list[SearchHit]: ...


@dataclass(frozen=True)
class InDocSearcher:
    """BM25 over one slug's mineru.json elements.

    Used as the v1 backend for /search step routes. exclude_box_ids
    is the standard "don't return the same chunk we started from"
    knob — set to (root_chunk_id,) when scoping a session.

    Verzeichnis-Boxes (toc / list_of_tables / list_of_figures /
    bibliography) are EXCLUDED by default because they're navigation
    elements, not source content. Set ``include_registers=True`` to
    bring them back into the corpus (used by the future
    register-aware skill that reads them through ``RegisterLookup``).
    """

    data_root: Path
    slug: str
    exclude_box_ids: tuple[str, ...] = field(default_factory=tuple)
    name: str = "in_doc"
    include_registers: bool = False

    def search(self, query: str, *, top_k: int) -> list[SearchHit]:
        if not query or not query.strip():
            return []
        m = read_mineru(self.data_root, self.slug)
        if m is None:
            return []
        register_box_ids = self._register_box_ids() if not self.include_registers else frozenset()
        elements = [
            e
            for e in m.get("elements", [])
            if e.get("box_id") not in self.exclude_box_ids
            and e.get("box_id") not in register_box_ids
        ]
        if not elements:
            return []
        texts = [strip_html(e.get("html_snippet", "")) for e in elements]
        scores = bm25_scores(query, texts)
        ranked = sorted(
            zip(elements, texts, scores, strict=True),
            key=lambda t: t[2],
            reverse=True,
        )
        out: list[SearchHit] = []
        for el, text, sc in ranked[:top_k]:
            if sc <= 0:
                continue
            out.append(
                SearchHit(
                    box_id=el["box_id"],
                    text=text,
                    score=float(sc),
                    doc_slug=self.slug,
                    searcher=self.name,
                )
            )
        return out

    def _register_box_ids(self) -> frozenset[str]:
        """Look up box_ids whose kind is one of the register kinds.

        Returns empty set when segments.json is absent (legacy slug
        without segmentation — fall back to the pre-Verzeichnis
        behaviour and don't filter).
        """
        seg = read_segments(self.data_root, self.slug)
        if seg is None:
            return frozenset()
        return frozenset(b.box_id for b in seg.boxes if b.kind.value in REGISTER_KINDS)
