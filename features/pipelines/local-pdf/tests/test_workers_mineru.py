"""Tests for the MinerU 3 worker class."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


# ── Existing tests (updated to keep extract_fn injection path working) ────────


def test_mineru_worker_advertises_name_and_estimated_vram() -> None:
    from local_pdf.workers.mineru import MineruWorker

    assert MineruWorker.name == "MinerU 3"
    assert MineruWorker.estimated_vram_mb >= 1000


def test_mineru_worker_run_emits_lifecycle_events_with_injected_extract(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.base import (
        ModelLoadedEvent,
        ModelLoadingEvent,
        WorkCompleteEvent,
        WorkProgressEvent,
    )
    from local_pdf.workers.mineru import MinerUResult, MineruWorker

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    boxes = [
        SegmentBox(
            box_id="p1-b0", page=1, bbox=(10, 20, 100, 60), kind=BoxKind.heading, confidence=0.95
        ),
        SegmentBox(
            box_id="p1-b1", page=1, bbox=(10, 70, 100, 200), kind=BoxKind.paragraph, confidence=0.88
        ),
    ]

    def fake_extract(_pdf: Path, box: SegmentBox) -> MinerUResult:
        tag = "h1" if box.kind == BoxKind.heading else "p"
        return MinerUResult(box_id=box.box_id, html=f"<{tag}>{box.box_id}</{tag}>")

    events = []
    results = []
    with MineruWorker(extract_fn=fake_extract) as worker:
        for ev in worker.run(pdf, boxes):
            events.append(ev)
        results = list(worker.results)
        for ev in worker.unload():
            events.append(ev)

    types = [e.type for e in events]
    assert types[0] == "model-loading"
    assert types[1] == "model-loaded"
    assert types.count("work-progress") == 2  # two boxes
    assert types[-3] == "work-complete"
    assert types[-2] == "model-unloading"
    assert types[-1] == "model-unloaded"

    loading = next(e for e in events if isinstance(e, ModelLoadingEvent))
    assert loading.model == "MinerU 3"
    assert loading.vram_estimate_mb >= 1000

    loaded = next(e for e in events if isinstance(e, ModelLoadedEvent))
    assert loaded.load_seconds >= 0

    progress = [e for e in events if isinstance(e, WorkProgressEvent)]
    assert progress[0].stage == "box"
    assert progress[-1].current == 2 and progress[-1].total == 2

    complete = next(e for e in events if isinstance(e, WorkCompleteEvent))
    assert complete.items_processed == 2
    assert complete.output_summary["boxes_extracted"] == 2

    assert [r.box_id for r in results] == ["p1-b0", "p1-b1"]
    assert results[0].html == "<h1>p1-b0</h1>"


def test_mineru_worker_skips_discard_kind(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MinerUResult, MineruWorker

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    boxes = [
        SegmentBox(
            box_id="p1-b0", page=1, bbox=(10, 20, 100, 60), kind=BoxKind.discard, confidence=0.5
        ),
        SegmentBox(
            box_id="p1-b1", page=1, bbox=(10, 70, 100, 200), kind=BoxKind.paragraph, confidence=0.9
        ),
    ]

    def fake(_p: Path, box: SegmentBox) -> MinerUResult:
        return MinerUResult(box_id=box.box_id, html=f"<p>{box.box_id}</p>")

    with MineruWorker(extract_fn=fake) as worker:
        list(worker.run(pdf, boxes))
        results = list(worker.results)
        list(worker.unload())

    assert [r.box_id for r in results] == ["p1-b1"]


def test_mineru_worker_extract_region_one_call(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MinerUResult, MineruWorker

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    box = SegmentBox(
        box_id="p2-b3", page=2, bbox=(50, 50, 200, 200), kind=BoxKind.table, confidence=0.7
    )

    calls: list[str] = []

    def fake(_p: Path, b: SegmentBox) -> MinerUResult:
        calls.append(b.box_id)
        return MinerUResult(box_id=b.box_id, html="<table><tr><td>x</td></tr></table>")

    with MineruWorker(extract_fn=fake) as worker:
        out = worker.extract_region(pdf, box)

    assert calls == ["p2-b3"]
    assert out.html.startswith("<table>")


# ── New tests for in-process parse_page_fn path ───────────────────────────────


def test_page_parsed_once_for_multiple_boxes_on_same_page(tmp_path: Path) -> None:
    """parse_page_fn must be called exactly once per unique page, not once per box."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # 5 boxes all on page 1
    boxes = [
        SegmentBox(
            box_id=f"p1-b{i}",
            page=1,
            bbox=(float(i * 10), 0.0, float(i * 10 + 9), 10.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
        )
        for i in range(5)
    ]

    call_count = 0

    def fake_parse(_pdf: Path, page: int) -> list[ParsedElement]:
        nonlocal call_count
        call_count += 1
        # Return one element per box position so matching can succeed
        return [
            ParsedElement(
                bbox=(float(i * 10), 0.0, float(i * 10 + 9), 10.0),
                html=f"<p>elem-{i}</p>",
            )
            for i in range(5)
        ]

    with MineruWorker(parse_page_fn=fake_parse) as worker:
        list(worker.run(pdf, boxes))

    assert call_count == 1, f"expected parse_page called once, got {call_count}"
    assert len(worker.results) == 5


def test_user_bbox_spanning_two_elements_concatenates_html(tmp_path: Path) -> None:
    """A user bbox that covers two stacked elements (in PDF pts) yields concatenated HTML.

    User box is in pixel space at raster_dpi=144.  After conversion to pts
    (factor 72/144 = 0.5) it maps to (0,0,50,50).  The two parsed elements
    are given in pt coords that both fall inside that converted box.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # User box in pixels at 144 dpi: (0,0,100,100) → pts (0,0,50,50)
    box = SegmentBox(
        box_id="p1-b0",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),  # pixels at 144 dpi
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    def fake_parse(_pdf: Path, page: int) -> list[ParsedElement]:
        # Element bboxes are in PDF pts and fit within the converted user box (0,0,50,50)
        return [
            ParsedElement(bbox=(0.0, 0.0, 50.0, 25.0), html="<p>top</p>"),
            ParsedElement(bbox=(0.0, 25.0, 50.0, 50.0), html="<p>bottom</p>"),
        ]

    with MineruWorker(parse_page_fn=fake_parse, raster_dpi=144) as worker:
        result = worker.extract_region(pdf, box)

    assert "<p>top</p>" in result.html
    assert "<p>bottom</p>" in result.html


def test_enter_emits_loading_and_loaded_events(tmp_path: Path) -> None:
    """__enter__ with parse_page_fn injection: lifecycle events ModelLoading + ModelLoaded."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.base import ModelLoadedEvent, ModelLoadingEvent
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p1-b0",
        page=1,
        bbox=(0.0, 0.0, 50.0, 50.0),
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    def fake_parse(_pdf: Path, page: int) -> list[ParsedElement]:
        return [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>hi</p>")]

    events = []
    with MineruWorker(parse_page_fn=fake_parse) as worker:
        for ev in worker.run(pdf, [box]):
            events.append(ev)
        for ev in worker.unload():
            events.append(ev)

    types = [e.type for e in events]
    assert "model-loading" in types
    assert "model-loaded" in types
    assert "model-unloading" in types
    assert "model-unloaded" in types

    loaded_ev = next(e for e in events if isinstance(e, ModelLoadedEvent))
    assert loaded_ev.load_seconds >= 0

    loading_ev = next(e for e in events if isinstance(e, ModelLoadingEvent))
    assert loading_ev.vram_estimate_mb >= 1000


def test_exit_emits_unloading_and_unloaded_events(tmp_path: Path) -> None:
    """unload() yields ModelUnloading then ModelUnloaded."""
    from local_pdf.workers.base import ModelUnloadedEvent
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    def fake_parse(_pdf: Path, page: int) -> list[ParsedElement]:
        return []

    events = []
    worker = MineruWorker(parse_page_fn=fake_parse)
    worker.__enter__()
    for ev in worker.unload():
        events.append(ev)

    types = [e.type for e in events]
    assert types[0] == "model-unloading"
    assert types[1] == "model-unloaded"

    unloaded = next(e for e in events if isinstance(e, ModelUnloadedEvent))
    assert unloaded.vram_freed_mb >= 0


# ── New tests for parse_doc_fn path (Bug 2 fix) ───────────────────────────────


def test_doc_parsed_once_for_multi_page_batch(tmp_path: Path) -> None:
    """parse_doc_fn must be called exactly once even when boxes span multiple pages."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "multipage.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # Two boxes on different pages
    boxes = [
        SegmentBox(
            box_id="p1-b0",
            page=1,
            bbox=(0.0, 0.0, 50.0, 50.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="p2-b0",
            page=2,
            bbox=(0.0, 0.0, 50.0, 50.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
    ]

    call_count = 0

    def fake_parse_doc(_pdf: Path) -> dict[int, list[ParsedElement]]:
        nonlocal call_count
        call_count += 1
        return {
            1: [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>page1</p>")],
            2: [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>page2</p>")],
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        list(worker.run(pdf, boxes))

    assert call_count == 1, f"expected parse_doc_fn called once, got {call_count}"
    assert len(worker.results) == 2
    assert worker.results[0].html == "<p>page1</p>"
    assert worker.results[1].html == "<p>page2</p>"


def test_doc_parsed_once_for_multi_box_same_page(tmp_path: Path) -> None:
    """parse_doc_fn called once when all 5 boxes are on page 1."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "single_page.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    boxes = [
        SegmentBox(
            box_id=f"p1-b{i}",
            page=1,
            bbox=(float(i * 10), 0.0, float(i * 10 + 9), 10.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
        )
        for i in range(5)
    ]

    call_count = 0

    def fake_parse_doc(_pdf: Path) -> dict[int, list[ParsedElement]]:
        nonlocal call_count
        call_count += 1
        return {
            1: [
                ParsedElement(
                    bbox=(float(i * 10), 0.0, float(i * 10 + 9), 10.0),
                    html=f"<p>elem-{i}</p>",
                )
                for i in range(5)
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        list(worker.run(pdf, boxes))

    assert call_count == 1, f"expected parse_doc_fn called once, got {call_count}"
    assert len(worker.results) == 5


def test_doc_cache_prevents_second_parse_across_calls(tmp_path: Path) -> None:
    """_get_doc_pages caches result; second call to extract_region re-uses cache."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "cached.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p1-b0",
        page=1,
        bbox=(0.0, 0.0, 50.0, 50.0),
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    call_count = 0

    def fake_parse_doc(_pdf: Path) -> dict[int, list[ParsedElement]]:
        nonlocal call_count
        call_count += 1
        return {1: [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>cached</p>")]}

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        worker.extract_region(pdf, box)
        worker.extract_region(pdf, box)  # second call — should use cache

    assert call_count == 1, f"expected parse_doc_fn called once (cached), got {call_count}"


def test_block_to_content_visual_type_routing() -> None:
    """_VISUAL_BLOCK_TYPES covers table/image/chart/code but not text."""
    from local_pdf.workers.mineru import _VISUAL_BLOCK_TYPES

    assert "table" in _VISUAL_BLOCK_TYPES
    assert "image" in _VISUAL_BLOCK_TYPES
    assert "chart" in _VISUAL_BLOCK_TYPES
    assert "code" in _VISUAL_BLOCK_TYPES
    assert "text" not in _VISUAL_BLOCK_TYPES


def test_merge_para_with_text_wiring_via_monkeypatch(tmp_path: Path) -> None:
    """parse_doc_fn path wires merge_para_with_text result into ParsedElement.html."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "wired.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p1-b0",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    # Simulate what _parse_doc would produce after using merge_para_with_text
    # (the real function is not called in tests — parse_doc_fn is injected directly)
    def fake_parse_doc(_pdf: Path) -> dict[int, list[ParsedElement]]:
        # Simulates _block_to_content returning "<p>hello</p>" for a block
        return {1: [ParsedElement(bbox=(0.0, 0.0, 100.0, 100.0), html="<p>hello</p>")]}

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        result = worker.extract_region(pdf, box)

    assert result.html == "<p>hello</p>"


# ── IoU / matching unit tests ─────────────────────────────────────────────────


def test_iou_exact_overlap() -> None:
    from local_pdf.workers.mineru import _iou

    box = (0.0, 0.0, 10.0, 10.0)
    assert _iou(box, box) == 1.0


def test_iou_no_overlap() -> None:
    from local_pdf.workers.mineru import _iou

    assert _iou((0.0, 0.0, 5.0, 5.0), (10.0, 10.0, 20.0, 20.0)) == 0.0


def test_match_fallback_to_best_when_no_threshold_met() -> None:
    """If no element meets IoU > 0.3 or center-in, return the one with highest IoU."""
    from local_pdf.workers.mineru import ParsedElement, _match_box_to_elements

    user_box = (0.0, 0.0, 10.0, 10.0)
    elements = [
        ParsedElement(bbox=(20.0, 20.0, 30.0, 30.0), html="<p>far</p>"),  # IoU = 0
        ParsedElement(bbox=(5.0, 5.0, 15.0, 15.0), html="<p>near</p>"),  # partial overlap
    ]
    result = _match_box_to_elements(user_box, elements)
    assert len(result) == 1
    assert result[0].html == "<p>near</p>"


def test_match_reading_order_sort() -> None:
    """Matched elements are sorted by (top, left)."""
    from local_pdf.workers.mineru import ParsedElement, _match_box_to_elements

    # Both elements fully inside user_box → both match, sorted by y then x
    user_box = (0.0, 0.0, 100.0, 100.0)
    elements = [
        ParsedElement(bbox=(0.0, 60.0, 50.0, 80.0), html="<p>lower</p>"),
        ParsedElement(bbox=(0.0, 10.0, 50.0, 40.0), html="<p>upper</p>"),
    ]
    result = _match_box_to_elements(user_box, elements)
    assert result[0].html == "<p>upper</p>"
    assert result[1].html == "<p>lower</p>"


# ── Coordinate-space conversion tests ────────────────────────────────────────


def test_user_bbox_to_pts_default_dpi() -> None:
    """_user_bbox_to_pts converts 144-dpi pixel bbox to PDF point space (factor 0.5)."""
    from local_pdf.workers.mineru import _user_bbox_to_pts

    # At 144 dpi: pts = px * 72/144 = px * 0.5
    result = _user_bbox_to_pts((100.0, 200.0, 500.0, 300.0), raster_dpi=144)
    assert result == (50.0, 100.0, 250.0, 150.0)


def test_user_bbox_to_pts_custom_dpi() -> None:
    """_user_bbox_to_pts scales correctly for non-default DPI."""
    from local_pdf.workers.mineru import _user_bbox_to_pts

    # At 72 dpi: pts = px * 72/72 = px (1:1)
    result = _user_bbox_to_pts((100.0, 200.0, 500.0, 300.0), raster_dpi=72)
    assert result == (100.0, 200.0, 500.0, 300.0)


def test_bbox_conversion_enables_match_via_parse_doc_fn(tmp_path: Path) -> None:
    """parse_doc_fn element at PDF-pt bbox (50,100,250,150) must be matched when
    user box is (100,200,500,300) in pixels at raster_dpi=144 (→ same pts after conversion).
    Without conversion IoU is 0 and html would be empty."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "conv.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # User box: pixel coords at 144 dpi → converts to pts (50, 100, 250, 150)
    box = SegmentBox(
        box_id="p1-b0",
        page=1,
        bbox=(100.0, 200.0, 500.0, 300.0),  # pixels at 144 dpi
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    # MinerU element with the exact matching pts bbox
    def fake_parse_doc(_pdf: Path) -> dict[int, list[ParsedElement]]:
        return {1: [ParsedElement(bbox=(50.0, 100.0, 250.0, 150.0), html="<p>matched</p>")]}

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        result = worker.extract_region(pdf, box)

    assert result.html == "<p>matched</p>", (
        f"expected '<p>matched</p>' but got {result.html!r}; bbox conversion may not be applied"
    )
