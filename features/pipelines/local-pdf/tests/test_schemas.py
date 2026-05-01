"""Schema validation tests for local-pdf API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_box_kind_enum_has_nine_values() -> None:
    from local_pdf.api.schemas import BoxKind

    expected = {
        "heading",
        "paragraph",
        "table",
        "figure",
        "caption",
        "formula",
        "list_item",
        "abandon",  # page-level chrome (headers/footers/page numbers); kept distinct from discard
        "discard",
    }
    assert {k.value for k in BoxKind} == expected


def test_doc_status_enum_transitions() -> None:
    from local_pdf.api.schemas import DocStatus

    expected = {
        "raw",
        "segmenting",
        "extracting",
        "extracted",
        "synthesising",
        "synthesised",
        "open-for-curation",
        "archived",
        "done",
        "needs_ocr",
    }
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


def test_update_box_request_kind_must_be_in_enum() -> None:
    from local_pdf.api.schemas import UpdateBoxRequest

    ok = UpdateBoxRequest(kind="heading", bbox=(10, 20, 100, 200))
    assert ok.kind == "heading"
    with pytest.raises(ValidationError):
        UpdateBoxRequest(kind="banana", bbox=(10, 20, 100, 200))


def test_worker_event_union_reexported_from_schemas() -> None:
    """schemas.WorkerEventUnion is the same TypeAdapter target as base."""
    from local_pdf.api.schemas import WorkerEventUnion
    from local_pdf.workers.base import (
        ModelLoadingEvent,
        WorkCompleteEvent,
        WorkFailedEvent,
    )
    from pydantic import TypeAdapter

    adapter: TypeAdapter[WorkerEventUnion] = TypeAdapter(WorkerEventUnion)
    assert isinstance(
        adapter.validate_python(
            {
                "type": "model-loading",
                "model": "Y",
                "timestamp_ms": 1,
                "source": "/w",
                "vram_estimate_mb": 700,
            }
        ),
        ModelLoadingEvent,
    )
    assert isinstance(
        adapter.validate_python(
            {
                "type": "work-complete",
                "model": "Y",
                "timestamp_ms": 9,
                "total_seconds": 1.0,
                "items_processed": 0,
                "output_summary": {},
            }
        ),
        WorkCompleteEvent,
    )
    assert isinstance(
        adapter.validate_python(
            {
                "type": "work-failed",
                "model": "Y",
                "timestamp_ms": 9,
                "stage": "load",
                "reason": "OOM",
                "recoverable": False,
                "hint": None,
            }
        ),
        WorkFailedEvent,
    )


def test_old_segment_extract_line_types_are_gone() -> None:
    """The pre-A.0-followup line types must no longer be importable."""
    import local_pdf.api.schemas as schemas

    for name in (
        "SegmentStartLine",
        "SegmentPageLine",
        "SegmentCompleteLine",
        "SegmentErrorLine",
        "ExtractStartLine",
        "ExtractElementLine",
        "ExtractCompleteLine",
        "ExtractErrorLine",
        "SegmentLine",
        "ExtractLine",
    ):
        assert not hasattr(schemas, name), f"{name} should be removed"
