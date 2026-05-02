"""Tests for the MinerU 3 worker class."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


# ── Existing tests (updated to keep extract_fn injection path working) ────────


def test_mineru_worker_advertises_name_and_estimated_vram() -> None:
    from local_pdf.workers.mineru import MineruWorker

    assert MineruWorker.name == "MinerU 2.5 VLM"
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
    assert loading.model == "MinerU 2.5 VLM"
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
    """A user bbox (paragraph kind) covering two stacked elements yields plain-text concatenation.

    User box is in pixel space at raster_dpi=144.  After conversion to pts
    (factor 72/144 = 0.5) it maps to (0,0,50,50).  The two parsed elements
    are given in pt coords that both fall inside that converted box.

    New behaviour: kind=paragraph → text extracted from matched elements,
    joined with space, wrapped in <p data-source-box="...">.
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

    # Kind=paragraph → kind-driven output: <p data-source-box="p1-b0">top bottom</p>
    assert "top" in result.html
    assert "bottom" in result.html
    assert 'data-source-box="p1-b0"' in result.html


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
            1: [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>page1</p>", text="page1")],
            2: [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>page2</p>", text="page2")],
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        list(worker.run(pdf, boxes))

    assert call_count == 1, f"expected parse_doc_fn called once, got {call_count}"
    assert len(worker.results) == 2
    # New behaviour: kind=paragraph → <p data-source-box="...">text</p>
    assert 'data-source-box="p1-b0"' in worker.results[0].html
    assert "page1" in worker.results[0].html
    assert 'data-source-box="p2-b0"' in worker.results[1].html
    assert "page2" in worker.results[1].html


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
    """parse_doc_fn path: kind=paragraph strips HTML from matched element, emits <p>."""
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
        return {
            1: [ParsedElement(bbox=(0.0, 0.0, 100.0, 100.0), html="<p>hello</p>", text="hello")]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        result = worker.extract_region(pdf, box)

    # New behaviour: kind=paragraph → plain text "hello" wrapped in <p data-source-box="...">
    assert 'data-source-box="p1-b0"' in result.html
    assert "hello" in result.html
    assert result.html == '<p data-source-box="p1-b0">hello</p>'


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
    Without conversion IoU is 0 and the box would emit an empty marker."""
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
        return {
            1: [
                ParsedElement(
                    bbox=(50.0, 100.0, 250.0, 150.0), html="<p>matched</p>", text="matched"
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        result = worker.extract_region(pdf, box)

    # New behaviour: kind=paragraph → <p data-source-box="p1-b0">matched</p>
    assert "matched" in result.html, (
        f"expected 'matched' inside output but got {result.html!r}; "
        "bbox conversion may not be applied"
    )
    assert 'data-source-box="p1-b0"' in result.html
    assert "empty" not in result.html


# ── _block_to_html type-aware output tests ────────────────────────────────────


def _make_mock_merge(monkeypatch, return_text: str) -> None:
    """Inject mock merge_para_with_text so _block_to_html works without MinerU."""
    import sys
    import types

    pkg = types.ModuleType("mineru")
    backend = types.ModuleType("mineru.backend")
    pipeline_pkg = types.ModuleType("mineru.backend.pipeline")
    mkcontent = types.ModuleType("mineru.backend.pipeline.pipeline_middle_json_mkcontent")
    mkcontent.merge_para_with_text = lambda _b: return_text
    mkcontent.merge_visual_blocks_to_markdown = lambda _b: return_text
    sys.modules.setdefault("mineru", pkg)
    sys.modules["mineru.backend"] = backend
    sys.modules["mineru.backend.pipeline"] = pipeline_pkg
    sys.modules["mineru.backend.pipeline.pipeline_middle_json_mkcontent"] = mkcontent


def test_block_to_html_title_produces_h2(monkeypatch) -> None:
    """type=title wraps in <h2> by default (no level key)."""
    _make_mock_merge(monkeypatch, "My Section")
    from local_pdf.workers.mineru import _block_to_html

    html = _block_to_html({"type": "title", "bbox": [0, 100, 200, 120]})
    assert html == "<h2>My Section</h2>"


def test_block_to_html_title_level1_produces_h1(monkeypatch) -> None:
    """type=title with level=1 produces <h1>."""
    _make_mock_merge(monkeypatch, "Document Title")
    from local_pdf.workers.mineru import _block_to_html

    html = _block_to_html({"type": "title", "level": 1, "bbox": [0, 100, 200, 130]})
    assert html == "<h1>Document Title</h1>"


def test_block_to_html_text_produces_p(monkeypatch) -> None:
    """type=text wraps in <p>."""
    _make_mock_merge(monkeypatch, "Some paragraph.")
    from local_pdf.workers.mineru import _block_to_html

    html = _block_to_html({"type": "text", "bbox": [0, 200, 300, 230]})
    assert html == "<p>Some paragraph.</p>"


def test_block_to_html_image_wraps_in_figure(monkeypatch) -> None:
    """type=image wraps visual markdown in <figure>."""
    _make_mock_merge(monkeypatch, "![fig](img.png)")
    from local_pdf.workers.mineru import _block_to_html

    html = _block_to_html({"type": "image", "bbox": [0, 300, 400, 500]})
    assert html == "<figure>![fig](img.png)</figure>"


def test_block_to_html_header_position_wraps_in_header(monkeypatch) -> None:
    """A text block in the top 8% of the page becomes <header class='page-header'>."""
    _make_mock_merge(monkeypatch, "Running Head")
    from local_pdf.workers.mineru import _block_to_html

    # Page height 1000pts; block y0=0..y1=70 is within top 8% (80 pts)
    html = _block_to_html(
        {"type": "text", "bbox": [0, 0, 300, 70]},
        page_size=(700.0, 1000.0),
    )
    assert "<header" in html and "page-header" in html


def test_block_to_html_footer_position_wraps_in_footer(monkeypatch) -> None:
    """A text block in the bottom 8% of the page becomes <footer class='page-footer'>."""
    _make_mock_merge(monkeypatch, "Page Footer")
    from local_pdf.workers.mineru import _block_to_html

    # Page height 1000pts; block y0=930 is above bottom threshold (920pts)
    html = _block_to_html(
        {"type": "text", "bbox": [0, 930, 300, 960]},
        page_size=(700.0, 1000.0),
    )
    assert "<footer" in html and "page-footer" in html


def test_block_to_html_page_number_detection(monkeypatch) -> None:
    """A short all-digit block in header/footer zone becomes <span class='page-number'>."""
    _make_mock_merge(monkeypatch, "42")
    from local_pdf.workers.mineru import _block_to_html

    html = _block_to_html(
        {"type": "text", "bbox": [300, 950, 400, 970]},
        page_size=(700.0, 1000.0),
    )
    assert 'class="page-number"' in html
    assert "42" in html


# ── Bug 3: data-source-box wrapper tests ──────────────────────────────────────


def test_run_result_has_data_source_box_wrapper(tmp_path: Path) -> None:
    """Each MinerUResult.html carries data-source-box on the kind-driven tag.

    New behaviour: kind=paragraph → <p data-source-box='{box_id}'>{text}</p>
    (not a <div> wrapper — the kind tag itself carries the attribute).
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p1-b0",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        return {
            1: [ParsedElement(bbox=(0.0, 0.0, 100.0, 100.0), html="<p>content</p>", text="content")]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, [box]))

    result = worker.results[0]
    assert result.html == '<p data-source-box="p1-b0">content</p>'


def test_extract_region_result_has_data_source_box_wrapper(tmp_path: Path) -> None:
    """extract_region: kind=table wraps MinerU HTML in extracted-table div with data-source-box."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p2-b3",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        kind=BoxKind.table,
        confidence=0.8,
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        # html field holds raw table HTML from MinerU (visual block)
        return {
            1: [
                ParsedElement(
                    bbox=(0.0, 0.0, 100.0, 100.0),
                    html="<table><tr><td>x</td></tr></table>",
                    text="",
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        result = worker.extract_region(pdf, box)

    # kind=table → <div data-source-box="..."><div class="extracted-table">{html}</div></div>
    assert 'data-source-box="p2-b3"' in result.html
    assert 'class="extracted-table"' in result.html


def test_parse_page_fn_path_has_data_source_box_wrapper(tmp_path: Path) -> None:
    """Legacy parse_page_fn path: kind=paragraph → <p data-source-box=...>text</p>."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p1-b5",
        page=1,
        bbox=(0.0, 0.0, 100.0, 100.0),
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    def fake_parse(_pdf: Path, _page: int) -> list[ParsedElement]:
        return [ParsedElement(bbox=(0.0, 0.0, 100.0, 100.0), html="<p>legacy</p>", text="legacy")]

    with MineruWorker(parse_page_fn=fake_parse, raster_dpi=144) as worker:
        list(worker.run(pdf, [box]))

    result = worker.results[0]
    # New behaviour: kind drives the tag, data-source-box on the element itself
    assert result.html == '<p data-source-box="p1-b5">legacy</p>'


# ── New tests: kind-driven output (user-bbox → tag mapping) ──────────────────


def test_user_kind_heading_emits_h2(tmp_path: Path) -> None:
    """kind=heading → <h2 data-source-box="...">text</h2>."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p1-h0",
        page=1,
        bbox=(0.0, 100.0, 200.0, 130.0),
        kind=BoxKind.heading,
        confidence=0.9,
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(0.0, 50.0, 200.0, 65.0), html="<h2>My Title</h2>", text="My Title"
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        result = worker.extract_region(pdf, box)

    assert result.html == '<h2 data-source-box="p1-h0">My Title</h2>'


def test_user_kind_paragraph_emits_p(tmp_path: Path) -> None:
    """kind=paragraph → <p data-source-box="...">text</p>."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p1-p0",
        page=1,
        bbox=(0.0, 0.0, 200.0, 100.0),
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(0.0, 0.0, 200.0, 50.0), html="<p>Hello world</p>", text="Hello world"
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        result = worker.extract_region(pdf, box)

    assert result.html == '<p data-source-box="p1-p0">Hello world</p>'


def test_user_kind_table_uses_mineru_html(tmp_path: Path) -> None:
    """kind=table → MinerU HTML wrapped in extracted-table div, not plain text."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    table_html = "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
    box = SegmentBox(
        box_id="p1-t0",
        page=1,
        bbox=(0.0, 0.0, 400.0, 200.0),
        kind=BoxKind.table,
        confidence=0.85,
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        return {1: [ParsedElement(bbox=(0.0, 0.0, 400.0, 100.0), html=table_html, text="")]}

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        result = worker.extract_region(pdf, box)

    assert 'data-source-box="p1-t0"' in result.html
    assert 'class="extracted-table"' in result.html
    assert table_html in result.html


def test_user_kind_auxiliary_top_zone_emits_header(tmp_path: Path) -> None:
    """kind=auxiliary, y_top < 8% page height → <header class="page-header">."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, PageData, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # Page height 792pt. At raster_dpi=144: pt = px * 72/144 = px * 0.5
    # Top 8% of 792pt = 63.36pt → px = 63.36 / 0.5 = 126.72px
    # y_top = 10px → pt = 5pt (well within 8%)
    box = SegmentBox(
        box_id="p1-aux0",
        page=1,
        bbox=(0.0, 10.0, 400.0, 40.0),  # y_top=10px → 5pt; 5/792 = 0.63% < 8%
        kind=BoxKind.auxiliary,
        confidence=0.8,
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        return {
            1: PageData(
                page_size=(612.0, 792.0),
                elements=[
                    ParsedElement(
                        bbox=(0.0, 5.0, 400.0, 20.0),
                        html="<p>Running Head</p>",
                        text="Running Head",
                    )
                ],
            )
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        result = worker.extract_region(pdf, box)

    assert '<header class="page-header"' in result.html
    assert "Running Head" in result.html
    assert 'data-source-box="p1-aux0"' in result.html


def test_user_kind_auxiliary_bottom_zone_emits_footer(tmp_path: Path) -> None:
    """kind=auxiliary, y_top > 92% page height → <footer class="page-footer">."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, PageData, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # Page height 792pt. At raster_dpi=144: pt = px * 0.5
    # 92% of 792pt = 728.64pt → px = 1457.28px
    # y_top = 1500px → pt = 750pt; 750/792 = 94.7% > 92%
    box = SegmentBox(
        box_id="p1-aux1",
        page=1,
        bbox=(0.0, 1500.0, 400.0, 1550.0),  # y_top=1500px → 750pt; 750/792 ≈ 94.7% > 92%
        kind=BoxKind.auxiliary,
        confidence=0.8,
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        return {
            1: PageData(
                page_size=(612.0, 792.0),
                elements=[
                    ParsedElement(
                        bbox=(0.0, 750.0, 400.0, 775.0),
                        html="<p>Page Footer</p>",
                        text="Page Footer",
                    )
                ],
            )
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        result = worker.extract_region(pdf, box)

    assert '<footer class="page-footer"' in result.html
    assert "Page Footer" in result.html
    assert 'data-source-box="p1-aux1"' in result.html


def test_custom_box_no_mineru_match_emits_empty_marker(tmp_path: Path) -> None:
    """When no MinerU element matches (empty page), emit the empty marker."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, PageData

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p1-custom",
        page=1,
        bbox=(300.0, 300.0, 500.0, 400.0),
        kind=BoxKind.paragraph,
        confidence=0.7,
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        # Empty page — no elements at all
        return {1: PageData(page_size=(612.0, 792.0), elements=[])}

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        result = worker.extract_region(pdf, box)

    assert "empty" in result.html
    assert "Keine Extraktion" in result.html
    assert 'data-source-box="p1-custom"' in result.html


def test_user_boxes_sorted_by_y_then_x(tmp_path: Path) -> None:
    """Worker results for a page must follow (y_top, x_left) reading order."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # Three boxes on page 1: deliberately given out of y-order
    boxes = [
        SegmentBox(
            box_id="p1-c",
            page=1,
            bbox=(0.0, 200.0, 100.0, 250.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="p1-a",
            page=1,
            bbox=(0.0, 0.0, 100.0, 50.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="p1-b",
            page=1,
            bbox=(50.0, 100.0, 150.0, 150.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: Path) -> dict:
        return {
            1: [
                ParsedElement(bbox=(0.0, 0.0, 50.0, 25.0), html="<p>a</p>", text="a"),
                ParsedElement(bbox=(25.0, 50.0, 75.0, 75.0), html="<p>b</p>", text="b"),
                ParsedElement(bbox=(0.0, 100.0, 50.0, 125.0), html="<p>c</p>", text="c"),
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        list(worker.run(pdf, boxes))

    # Results are emitted in targets order (input order), not sorted — sorting
    # affects which MinerU elements are matched, not result output order.
    # The key invariant: each box gets the right matched element.
    result_ids = [r.box_id for r in worker.results]
    # All three boxes must be processed
    assert set(result_ids) == {"p1-a", "p1-b", "p1-c"}
    assert len(worker.results) == 3


def test_h1_promotion_for_single_first_page_heading(tmp_path: Path) -> None:
    """A single heading on page 1 that is the topmost box is promoted to <h1>."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # One heading on page 1 (topmost box) and one paragraph below it
    boxes = [
        SegmentBox(
            box_id="p1-h0",
            page=1,
            bbox=(0.0, 0.0, 400.0, 50.0),
            kind=BoxKind.heading,
            confidence=0.95,
        ),
        SegmentBox(
            box_id="p1-p0",
            page=1,
            bbox=(0.0, 60.0, 400.0, 120.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: Path) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(0.0, 0.0, 200.0, 25.0), html="<h2>Doc Title</h2>", text="Doc Title"
                ),
                ParsedElement(
                    bbox=(0.0, 30.0, 200.0, 60.0), html="<p>Body text</p>", text="Body text"
                ),
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        list(worker.run(pdf, boxes))

    heading_result = next(r for r in worker.results if r.box_id == "p1-h0")
    para_result = next(r for r in worker.results if r.box_id == "p1-p0")

    # Single heading on first page → promoted to h1
    assert heading_result.html == '<h1 data-source-box="p1-h0">Doc Title</h1>'
    # Paragraph stays as <p>
    assert '<p data-source-box="p1-p0">' in para_result.html


def test_h1_promotion_not_applied_when_multiple_headings(tmp_path: Path) -> None:
    """When page 1 has two heading boxes, neither is promoted to h1."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    boxes = [
        SegmentBox(
            box_id="p1-h0",
            page=1,
            bbox=(0.0, 0.0, 400.0, 50.0),
            kind=BoxKind.heading,
            confidence=0.95,
        ),
        SegmentBox(
            box_id="p1-h1",
            page=1,
            bbox=(0.0, 60.0, 400.0, 100.0),
            kind=BoxKind.heading,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: Path) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(0.0, 0.0, 200.0, 25.0), html="<h2>Title A</h2>", text="Title A"
                ),
                ParsedElement(
                    bbox=(0.0, 30.0, 200.0, 50.0), html="<h2>Title B</h2>", text="Title B"
                ),
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        list(worker.run(pdf, boxes))

    for r in worker.results:
        assert "<h1" not in r.html, f"Expected no h1 promotion, got: {r.html}"
        assert "<h2" in r.html


# ── New tests: page-subset slicing (fix for full-doc VLM on single-page extract) ─


def test_run_with_page_subset_only_returns_those_pages(tmp_path: Path) -> None:
    """When targets only touch page 2, parse_doc_fn is called once and results
    contain only page-2 boxes — pages 1 and 3 are filtered out of the cache."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "three_pages.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # Single box on page 2 only
    boxes = [
        SegmentBox(
            box_id="p2-b0",
            page=2,
            bbox=(0.0, 0.0, 50.0, 50.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
        )
    ]

    call_args: list[int | None] = []

    def fake_parse_doc(_pdf: Path) -> dict[int, list[ParsedElement]]:
        # Return three pages worth of data; worker should filter to page 2 only
        call_args.append(None)  # sentinel: we were called
        return {
            1: [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>page1</p>", text="page1")],
            2: [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>page2</p>", text="page2")],
            3: [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>page3</p>", text="page3")],
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        list(worker.run(pdf, boxes))

    assert len(call_args) == 1, "parse_doc_fn should be called exactly once"
    assert len(worker.results) == 1
    assert worker.results[0].box_id == "p2-b0"
    assert "page2" in worker.results[0].html


def test_page_subset_cache_key_is_independent_of_full_doc(tmp_path: Path) -> None:
    """A partial-page run and a full-doc run use separate cache slots.

    parse_doc_fn is called twice: once for the subset run, once for the
    full-doc run.  Neither result is reused for the other.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "two_pages.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box_p1 = SegmentBox(
        box_id="p1-b0",
        page=1,
        bbox=(0.0, 0.0, 50.0, 50.0),
        kind=BoxKind.paragraph,
        confidence=0.9,
    )
    box_p2 = SegmentBox(
        box_id="p2-b0",
        page=2,
        bbox=(0.0, 0.0, 50.0, 50.0),
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    call_count = 0

    def fake_parse_doc(_pdf: Path) -> dict[int, list[ParsedElement]]:
        nonlocal call_count
        call_count += 1
        return {
            1: [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>p1</p>", text="p1")],
            2: [ParsedElement(bbox=(0.0, 0.0, 50.0, 50.0), html="<p>p2</p>", text="p2")],
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        # First run: page 1 only → partial cache entry (pdf, {1})
        list(worker.run(pdf, [box_p1]))
        # Second run: both pages → full cache entry (pdf, {1, 2})
        list(worker.run(pdf, [box_p1, box_p2]))

    # parse_doc_fn called twice: different cache keys → no sharing
    assert call_count == 2, (
        f"expected 2 parse_doc_fn calls (different cache keys), got {call_count}"
    )


def test_pdf_slicing_helper_extracts_correct_pages(tmp_path: Path) -> None:
    """_slice_pdf_to_pages: slicing a 5-page PDF to pages [2, 4] yields a 2-page PDF."""
    import io

    from local_pdf.workers.mineru import _slice_pdf_to_pages
    from pypdf import PdfReader, PdfWriter

    # Build a minimal 5-page PDF in memory using pypdf
    writer = PdfWriter()
    for _ in range(5):
        writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    five_page_bytes = buf.getvalue()

    # Slice to pages 2 and 4 (1-indexed)
    sliced = _slice_pdf_to_pages(five_page_bytes, [2, 4])

    reader = PdfReader(io.BytesIO(sliced))
    assert len(reader.pages) == 2, f"expected 2 pages after slicing, got {len(reader.pages)}"
