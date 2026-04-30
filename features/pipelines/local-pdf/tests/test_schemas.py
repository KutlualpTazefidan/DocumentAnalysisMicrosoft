"""Schema validation tests for local-pdf API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_box_kind_enum_has_eight_values() -> None:
    from local_pdf.api.schemas import BoxKind

    expected = {
        "heading",
        "paragraph",
        "table",
        "figure",
        "caption",
        "formula",
        "list_item",
        "discard",
    }
    assert {k.value for k in BoxKind} == expected


def test_doc_status_enum_transitions() -> None:
    from local_pdf.api.schemas import DocStatus

    expected = {"raw", "segmenting", "extracting", "done", "needs_ocr"}
    assert {s.value for s in DocStatus} == expected


def test_segment_box_requires_positive_page_and_4tuple_bbox() -> None:
    from local_pdf.api.schemas import SegmentBox

    ok = SegmentBox(
        box_id="b-1", page=1, bbox=(10, 20, 100, 200), kind="paragraph", confidence=0.92
    )
    assert ok.box_id == "b-1"
    assert ok.bbox == (10, 20, 100, 200)

    with pytest.raises(ValidationError):
        SegmentBox(box_id="b-2", page=0, bbox=(10, 20, 100, 200), kind="paragraph", confidence=0.5)
    with pytest.raises(ValidationError):
        SegmentBox(box_id="b-3", page=1, bbox=(10, 20, 100), kind="paragraph", confidence=0.5)
    with pytest.raises(ValidationError):
        SegmentBox(box_id="", page=1, bbox=(10, 20, 100, 200), kind="paragraph", confidence=0.5)


def test_doc_meta_round_trip() -> None:
    from local_pdf.api.schemas import DocMeta, DocStatus

    m = DocMeta(
        slug="bam-tragkorb-2024",
        filename="BAM_Tragkorb_2024.pdf",
        pages=42,
        status=DocStatus.raw,
        last_touched_utc="2026-04-30T10:00:00Z",
    )
    j = m.model_dump(mode="json")
    assert j["status"] == "raw"
    assert DocMeta.model_validate(j) == m


def test_extract_event_discriminator() -> None:
    from local_pdf.api.schemas import (
        ExtractCompleteLine,
        ExtractElementLine,
        ExtractErrorLine,
        ExtractLine,
        ExtractStartLine,
    )
    from pydantic import TypeAdapter

    adapter: TypeAdapter[
        ExtractStartLine | ExtractElementLine | ExtractCompleteLine | ExtractErrorLine
    ] = TypeAdapter(ExtractLine)
    assert isinstance(
        adapter.validate_python({"type": "start", "total_boxes": 12}), ExtractStartLine
    )
    assert isinstance(
        adapter.validate_python({"type": "element", "box_id": "b-1", "html_snippet": "<p>x</p>"}),
        ExtractElementLine,
    )
    assert isinstance(
        adapter.validate_python({"type": "complete", "boxes_extracted": 12}), ExtractCompleteLine
    )
    assert isinstance(
        adapter.validate_python({"type": "error", "box_id": "b-1", "reason": "vlm-timeout"}),
        ExtractErrorLine,
    )


def test_update_box_request_kind_must_be_in_enum() -> None:
    from local_pdf.api.schemas import UpdateBoxRequest

    ok = UpdateBoxRequest(kind="heading", bbox=(10, 20, 100, 200))
    assert ok.kind == "heading"
    with pytest.raises(ValidationError):
        UpdateBoxRequest(kind="banana", bbox=(10, 20, 100, 200))
