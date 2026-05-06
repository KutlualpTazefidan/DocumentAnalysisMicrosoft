"""Searcher Protocol + InDocSearcher — v1 of the provenance corpus.

The Searcher Protocol is the seam for Stages 5+ to swap in
CrossDocSearcher (every locally-extracted slug) or AzureSearcher
(existing Azure AI Search indexes) without touching the Provenienz
step routes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003
from typing import Protocol

from local_pdf.comparison.bm25 import bm25_scores
from local_pdf.storage.sidecar import read_mineru


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


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip(html: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", html or "")).strip()


@dataclass(frozen=True)
class InDocSearcher:
    """BM25 over one slug's mineru.json elements.

    Used as the v1 backend for /search step routes. exclude_box_ids
    is the standard "don't return the same chunk we started from"
    knob — set to (root_chunk_id,) when scoping a session.
    """

    data_root: Path
    slug: str
    exclude_box_ids: tuple[str, ...] = field(default_factory=tuple)
    name: str = "in_doc"

    def search(self, query: str, *, top_k: int) -> list[SearchHit]:
        if not query or not query.strip():
            return []
        m = read_mineru(self.data_root, self.slug)
        if m is None:
            return []
        elements = [e for e in m.get("elements", []) if e.get("box_id") not in self.exclude_box_ids]
        if not elements:
            return []
        texts = [_strip(e.get("html_snippet", "")) for e in elements]
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
