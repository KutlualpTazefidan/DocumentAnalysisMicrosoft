"""Build canonical SourceElement payload from user-edited segments + html.

Output shape matches features/pipelines/microsoft/ pipeline (PR #12 schema)
plus a `source_pipeline: "local-pdf"` discriminator field. Boxes whose
kind == "discard" are skipped.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from local_pdf.api.schemas import BoxKind, SegmentsFile


class _TextExtractor(HTMLParser):
    """Capture raw text between balanced tags, indexed by data-source-box."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[str | None] = []
        self._buf: list[str] = []
        self._capture: str | None = None
        self.results: dict[str, str] = {}
        self.tags: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        bid = attrs_d.get("data-source-box")
        if bid and self._capture is None:
            self._capture = bid
            self._buf = []
            self._stack.append(bid)
            self.tags[bid] = tag
        else:
            self._stack.append(None)

    def handle_endtag(self, tag):
        if not self._stack:
            return
        top = self._stack.pop()
        if top is not None and top == self._capture:
            self.results[self._capture] = "".join(self._buf).strip()
            self._capture = None
            self._buf = []

    def handle_data(self, data):
        if self._capture is not None:
            self._buf.append(data)


def _heading_level(tag: str) -> int:
    m = re.match(r"h([1-6])$", tag.lower())
    return int(m.group(1)) if m else 1


def build_source_elements_payload(*, slug: str, segments: SegmentsFile, html: str) -> dict:
    parser = _TextExtractor()
    parser.feed(html)
    elements: list[dict] = []
    for box in segments.boxes:
        if box.kind == BoxKind.discard:
            continue
        text = parser.results.get(box.box_id, "")
        tag = parser.tags.get(box.box_id, "p")
        entry: dict = {
            "kind": box.kind.value,
            "page": box.page,
            "bbox": list(box.bbox),
            "text": text,
            "box_id": box.box_id,
        }
        if box.kind == BoxKind.heading:
            entry["level"] = _heading_level(tag)
        elements.append(entry)
    return {
        "doc_slug": slug,
        "source_pipeline": "local-pdf",
        "elements": elements,
    }
