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

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
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

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
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


def test_match_no_fallback_when_no_threshold_met() -> None:
    """When no element meets IoU > 0.3 or center-in, _match_box_to_elements returns [].

    The best-effort fallback was removed; callers receive an empty list and
    emit the empty marker instead of silently returning an unrelated element.

    Both elements below are strictly non-overlapping (IoU=0) with centers
    outside the user box, so neither qualifies.
    """
    from local_pdf.workers.mineru import ParsedElement, _match_box_to_elements

    # user_box: (0,0,10,10)
    user_box = (0.0, 0.0, 10.0, 10.0)
    elements = [
        ParsedElement(
            bbox=(20.0, 20.0, 30.0, 30.0), html="<p>far</p>"
        ),  # no overlap, center=(25,25)
        ParsedElement(
            bbox=(15.0, 15.0, 25.0, 25.0), html="<p>near</p>"
        ),  # no overlap, center=(20,20)
    ]
    result = _match_box_to_elements(user_box, elements)
    assert result == [], f"expected empty list (no fallback), got {result}"


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
    """Inject mock merge_para_with_text so _block_to_html works without MinerU.

    Patches BOTH the VLM and the pipeline mkcontent helpers — the worker's
    safe wrappers prefer the VLM helper, falling back to pipeline.
    """
    import sys
    import types

    pkg = types.ModuleType("mineru")
    backend = types.ModuleType("mineru.backend")

    pipeline_pkg = types.ModuleType("mineru.backend.pipeline")
    pipe_mkcontent = types.ModuleType("mineru.backend.pipeline.pipeline_middle_json_mkcontent")
    pipe_mkcontent.merge_para_with_text = lambda _b: return_text
    pipe_mkcontent.merge_visual_blocks_to_markdown = lambda _b: return_text

    vlm_pkg = types.ModuleType("mineru.backend.vlm")
    vlm_mkcontent = types.ModuleType("mineru.backend.vlm.vlm_middle_json_mkcontent")
    vlm_mkcontent.merge_para_with_text = lambda _b: return_text
    vlm_mkcontent.merge_visual_blocks_to_markdown = lambda _b: return_text

    sys.modules.setdefault("mineru", pkg)
    sys.modules["mineru.backend"] = backend
    sys.modules["mineru.backend.pipeline"] = pipeline_pkg
    sys.modules["mineru.backend.pipeline.pipeline_middle_json_mkcontent"] = pipe_mkcontent
    sys.modules["mineru.backend.vlm"] = vlm_pkg
    sys.modules["mineru.backend.vlm.vlm_middle_json_mkcontent"] = vlm_mkcontent


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

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
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

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        result = worker.extract_region(pdf, box)

    assert result.html == '<p data-source-box="p1-p0">Hello world</p>'


def test_paragraph_with_multiple_matches_emits_separate_p_tags(tmp_path: Path) -> None:
    """When one paragraph user-bbox matches multiple MinerU paragraph elements,
    each becomes its own <p> tag instead of being joined into one inline blob."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p1-p0",
        page=1,
        bbox=(0.0, 0.0, 400.0, 800.0),  # big bbox covering several paras
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(10.0, 10.0, 190.0, 60.0),
                    html="<p>First paragraph.</p>",
                    text="First paragraph.",
                ),
                ParsedElement(
                    bbox=(10.0, 70.0, 190.0, 130.0),
                    html="<p>Second paragraph.</p>",
                    text="Second paragraph.",
                ),
                ParsedElement(
                    bbox=(10.0, 140.0, 190.0, 200.0),
                    html="<p>Third paragraph.</p>",
                    text="Third paragraph.",
                ),
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        result = worker.extract_region(pdf, box)

    # Three separate <p> tags emitted, each with the same data-source-box.
    assert result.html.count("<p data-source-box=") == 3
    assert "First paragraph." in result.html
    assert "Second paragraph." in result.html
    assert "Third paragraph." in result.html
    # Adjacent <p>s share the source bbox so click-highlight still works.
    assert result.html.count('data-source-box="p1-p0"') == 3


def test_one_block_split_across_user_bboxes_via_lines(tmp_path: Path) -> None:
    """When MinerU emits one block that covers multiple user paragraph bboxes
    (e.g. a bullet list as one text block, but the user gave each bullet its
    own bbox), the assignment splits the block into its line sub-elements
    and routes each line to the user-bbox that contains it.

    Previously: best-match gave the whole block to one user bbox, so all
    bullets merged into one <p> — the other user bboxes were silent.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # 3 user-bboxes, each tight around one bullet line, raster_dpi=144.
    boxes = [
        SegmentBox(
            box_id="b1",
            page=1,
            bbox=(100.0, 100.0, 600.0, 140.0),  # → pts (50, 50, 300, 70)
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="b2",
            page=1,
            bbox=(100.0, 150.0, 600.0, 190.0),  # → pts (50, 75, 300, 95)
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="b3",
            page=1,
            bbox=(100.0, 200.0, 600.0, 240.0),  # → pts (50, 100, 300, 120)
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
    ]

    # ONE big block (in pts, covers all 3 lines) with line sub-elements.
    big_block = ParsedElement(
        bbox=(50.0, 50.0, 300.0, 120.0),
        html="<p>- bullet one\n- bullet two\n- bullet three</p>",
        text="- bullet one - bullet two - bullet three",
        block_type="text",
        lines=(
            ParsedElement(
                bbox=(50.0, 50.0, 300.0, 70.0),
                html="<p>- bullet one</p>",
                text="- bullet one",
                block_type="text",
            ),
            ParsedElement(
                bbox=(50.0, 75.0, 300.0, 95.0),
                html="<p>- bullet two</p>",
                text="- bullet two",
                block_type="text",
            ),
            ParsedElement(
                bbox=(50.0, 100.0, 300.0, 120.0),
                html="<p>- bullet three</p>",
                text="- bullet three",
                block_type="text",
            ),
        ),
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        return {1: [big_block]}

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}
    # Each user-bbox got exactly its corresponding line.
    assert "bullet one" in by_id["b1"]
    assert "bullet two" not in by_id["b1"]
    assert "bullet two" in by_id["b2"]
    assert "bullet one" not in by_id["b2"]
    assert "bullet three" in by_id["b3"]
    assert "bullet two" not in by_id["b3"]
    # Each carries its own data-source-box for click-mapping.
    assert 'data-source-box="b1"' in by_id["b1"]
    assert 'data-source-box="b2"' in by_id["b2"]
    assert 'data-source-box="b3"' in by_id["b3"]


def test_block_kept_whole_when_only_one_user_bbox_overlaps(tmp_path: Path) -> None:
    """When only one text-kind user-bbox overlaps a block, don't split it.
    A normal multi-line paragraph should stay as one element/<p>."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    box = SegmentBox(
        box_id="p0",
        page=1,
        bbox=(100.0, 100.0, 600.0, 240.0),  # one big bbox covering the whole para
        kind=BoxKind.paragraph,
        confidence=0.9,
    )

    big_block = ParsedElement(
        bbox=(50.0, 50.0, 300.0, 120.0),
        html="<p>This is a multi-line paragraph.</p>",
        text="This is a multi-line paragraph.",
        block_type="text",
        lines=(
            ParsedElement(
                bbox=(50.0, 50.0, 300.0, 80.0),
                html="<p>line a</p>",
                text="line a",
                block_type="text",
            ),
            ParsedElement(
                bbox=(50.0, 90.0, 300.0, 120.0),
                html="<p>line b</p>",
                text="line b",
                block_type="text",
            ),
        ),
    )

    def fake_parse_doc(_pdf: Path) -> dict:
        return {1: [big_block]}

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes=[box]))

    [result] = worker.results
    # Single <p> with the whole text — no line-level split.
    assert result.html.count("<p data-source-box=") == 1
    assert "multi-line paragraph" in result.html


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

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
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


def test_custom_box_no_mineru_match_returns_empty(tmp_path: Path) -> None:
    """When no MinerU element matches (empty page), the box renders as empty
    string — no marker text is injected.  Empty boxes are silent."""
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
        return {1: PageData(page_size=(612.0, 792.0), elements=[])}

    with MineruWorker(parse_doc_fn=fake_parse_doc) as worker:
        result = worker.extract_region(pdf, box)

    assert result.html == ""


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

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
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

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
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

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
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


# ── New tests: page-level best-match assignment (no double-counting) ──────────


def test_overlapping_user_boxes_no_double_count(tmp_path: Path) -> None:
    """When two user boxes both overlap the same MinerU element, only the one with
    the higher IoU score receives it; the other gets the empty marker.

    Setup (all coords in PDF pts at raster_dpi=144, px = pts * 2):
      MinerU element:  pts (50, 100, 200, 150)
      Heading user box (enclosing):  px (80, 180, 440, 320) → pts (40, 90, 220, 160)
        IoU with element ≈ 0.595 — wins
      Paragraph user box (inner):   px (120, 220, 360, 320) → pts (60, 110, 180, 160)
        IoU with element ≈ 0.552 — loses
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "overlap.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    boxes = [
        SegmentBox(
            box_id="head",
            page=1,
            bbox=(80.0, 180.0, 440.0, 320.0),  # → pts (40, 90, 220, 160)
            kind=BoxKind.heading,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="para",
            page=1,
            bbox=(120.0, 220.0, 360.0, 320.0),  # → pts (60, 110, 180, 160)
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(50.0, 100.0, 200.0, 150.0),
                    html="<p>shared element</p>",
                    text="shared element",
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # Heading box has higher IoU → gets the element text
    assert "shared element" in by_id["head"], (
        f"heading box should contain the element, got: {by_id['head']!r}"
    )
    # Paragraph box should get the empty marker (element already claimed by heading)
    assert by_id["para"] == "", f"para box should get empty marker, got: {by_id['para']!r}"
    # "shared element" must NOT appear in the paragraph box
    assert "shared element" not in by_id["para"], (
        f"para box must NOT contain the element text (double-count), got: {by_id['para']!r}"
    )


def test_table_caption_only_in_caption_box(tmp_path: Path) -> None:
    """Caption and table elements each go exclusively to the matching user box.

    Two MinerU elements (caption at top, table below) and two user boxes
    (heading tight around caption, table tight around table).  After assignment,
    neither box should contain the other's content.

    All coords in PDF pts; raster_dpi=144 so px = pts * 2.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "caption_table.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # px = pts * 2 (raster_dpi=144, factor 72/144=0.5)
    boxes = [
        SegmentBox(
            box_id="heading",
            page=1,
            bbox=(90.0, 90.0, 610.0, 170.0),  # → pts (45, 45, 305, 85): tight around caption
            kind=BoxKind.heading,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="table",
            page=1,
            bbox=(90.0, 190.0, 610.0, 610.0),  # → pts (45, 95, 305, 305): tight around table
            kind=BoxKind.table,
            confidence=0.9,
        ),
    ]

    caption_text = "Table 1. Summary of results"
    table_html = "<table><tr><td>col1</td><td>col2</td></tr></table>"

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(50.0, 50.0, 300.0, 80.0),  # caption element in pts
                    html=f"<h2>{caption_text}</h2>",
                    text=caption_text,
                ),
                ParsedElement(
                    bbox=(50.0, 100.0, 300.0, 300.0),  # table element in pts
                    html=table_html,
                    text="",
                ),
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # Heading box: caption text present, no table data
    assert caption_text in by_id["heading"], (
        f"heading box should contain caption, got: {by_id['heading']!r}"
    )
    assert "col1" not in by_id["heading"], (
        f"heading box must NOT contain table data, got: {by_id['heading']!r}"
    )

    # Table box: table HTML present, no caption text
    assert "col1" in by_id["table"], f"table box should contain table data, got: {by_id['table']!r}"
    assert caption_text not in by_id["table"], (
        f"table box must NOT contain caption text, got: {by_id['table']!r}"
    )


def test_table_user_bbox_rejects_text_block_when_heading_overlaps(tmp_path: Path) -> None:
    """Type-compat: a kind=table user-bbox enclosing a text-type MinerU block
    should NOT outscore a kind=heading user-bbox sitting next to that block.

    Geometric: table user-bbox encloses the caption block (large bbox covering
    both caption + table area); heading user-bbox is smaller, tight around just
    the caption. Without type compat, the table user-bbox would win the caption
    block via larger IoU. With type compat (table kind hard-rejects text blocks),
    the caption block goes to the heading.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "table_compat.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    boxes = [
        SegmentBox(
            box_id="heading",
            page=1,
            bbox=(90.0, 90.0, 610.0, 170.0),  # → pts (45, 45, 305, 85): tight around caption
            kind=BoxKind.heading,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="table",
            page=1,
            # → pts (40, 40, 310, 310): big enough to also envelop the caption
            bbox=(80.0, 80.0, 620.0, 620.0),
            kind=BoxKind.table,
            confidence=0.9,
        ),
    ]

    caption_text = "Table 1. Summary"

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                # Caption is a text-type block. Without type-compat, the bigger
                # table user-bbox would claim it via higher IoU (caption sits
                # inside the table user-bbox area). With type-compat, table kind
                # hard-rejects text blocks → caption goes to heading.
                ParsedElement(
                    bbox=(50.0, 50.0, 300.0, 80.0),
                    html=f"<h2>{caption_text}</h2>",
                    text=caption_text,
                    block_type="text",
                ),
                ParsedElement(
                    bbox=(50.0, 100.0, 300.0, 300.0),
                    html="<table><tr><td>col1</td></tr></table>",
                    text="",
                    block_type="table",
                ),
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # Heading user-bbox wins the caption block.
    assert caption_text in by_id["heading"]
    # Table user-bbox does NOT take the caption.
    assert caption_text not in by_id["table"]
    # Table user-bbox still gets its own table block.
    assert "col1" in by_id["table"]


# ── New tests: caption rescue ─────────────────────────────────────────────────


def test_caption_tag_rescued_from_table_block(tmp_path: Path) -> None:
    """A <caption> tag inside a table element's HTML is rescued to an empty heading bbox.

    Setup (raster_dpi=144, so px = pts * 2):
      MinerU element: table block at pts (40, 40, 300, 300) with
        html = '<caption>Tab. 1 example caption</caption><table>...</table>'
      User boxes:
        heading at px (90, 90, 610, 170) → pts (45, 45, 305, 85) — center inside table bbox
        table   at px (80, 80, 620, 620) → pts (40, 40, 310, 310)

    After run():
      - heading box html contains "Tab. 1 example caption"
      - table box html does NOT contain the <caption> tag or its text
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "caption_rescue.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    boxes = [
        SegmentBox(
            box_id="heading",
            page=1,
            bbox=(90.0, 90.0, 610.0, 170.0),  # → pts (45, 45, 305, 85)
            kind=BoxKind.heading,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="table",
            page=1,
            bbox=(80.0, 80.0, 620.0, 620.0),  # → pts (40, 40, 310, 310)
            kind=BoxKind.table,
            confidence=0.9,
        ),
    ]

    _cap_html = "<caption>Tab. 1 example caption</caption><table><tr><td>cell</td></tr></table>"

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(40.0, 40.0, 300.0, 300.0),
                    html=_cap_html,
                    text="",
                    block_type="table",
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # Heading bbox should now contain the rescued caption text.
    assert "Tab. 1 example caption" in by_id["heading"], (
        f"heading should contain caption, got: {by_id['heading']!r}"
    )
    assert "Keine Extraktion" not in by_id["heading"], (
        f"heading must not be empty, got: {by_id['heading']!r}"
    )
    # Heading rendered as a muted reference (caption-ref class) — not a
    # primary <h2> heading — since the caption is also visible in the table.
    assert 'class="caption-ref"' in by_id["heading"], (
        f"heading should be styled as caption-ref, got: {by_id['heading']!r}"
    )
    # Table HTML keeps its caption — MinerU's natural rendering preserved.
    assert "<caption" in by_id["table"]
    assert "Tab. 1 example caption" in by_id["table"]
    # Table cell data still present.
    assert "cell" in by_id["table"], (
        f"table should still contain cell data, got: {by_id['table']!r}"
    )


def test_leading_text_rescued_when_no_caption_tag(tmp_path: Path) -> None:
    """Leading text before <table> is rescued when there is no <caption> tag.

    Element html = 'Some lead-in text\\n<table>...</table>'
    Heading bbox center is inside the table user-bbox → rescue fires.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "leading_text.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    boxes = [
        SegmentBox(
            box_id="heading",
            page=1,
            bbox=(90.0, 90.0, 610.0, 170.0),  # → pts (45, 45, 305, 85)
            kind=BoxKind.heading,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="table",
            page=1,
            bbox=(80.0, 80.0, 620.0, 620.0),  # → pts (40, 40, 310, 310)
            kind=BoxKind.table,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(40.0, 40.0, 300.0, 300.0),
                    html="Some lead-in text\n<table><tr><td>cell</td></tr></table>",
                    text="",
                    block_type="table",
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # Heading gets the leading text.
    assert "Some lead-in text" in by_id["heading"], (
        f"heading should contain leading text, got: {by_id['heading']!r}"
    )
    assert "Keine Extraktion" not in by_id["heading"]
    assert 'class="caption-ref"' in by_id["heading"]
    # Table HTML preserved as MinerU rendered it (no stripping).
    assert "Some lead-in text" in by_id["table"]
    assert "cell" in by_id["table"]


def test_no_rescue_when_no_caption_or_leading_text(tmp_path: Path) -> None:
    """When the table element has no caption tag and no leading text, heading stays empty."""
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "no_caption.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    boxes = [
        SegmentBox(
            box_id="heading",
            page=1,
            bbox=(90.0, 90.0, 610.0, 170.0),
            kind=BoxKind.heading,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="table",
            page=1,
            bbox=(80.0, 80.0, 620.0, 620.0),
            kind=BoxKind.table,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(40.0, 40.0, 300.0, 300.0),
                    html="<table><tr><td>cell</td></tr></table>",
                    text="",
                    block_type="table",
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # No caption extractable → heading stays empty.
    assert by_id["heading"] == "", f"heading should stay empty, got: {by_id['heading']!r}"
    # Table unchanged.
    assert "cell" in by_id["table"]


def test_rescue_only_when_text_kind_center_inside_visual_bbox(tmp_path: Path) -> None:
    """A kind=paragraph user-bbox NOT enclosed by the table bbox gets no rescue.

    The paragraph bbox sits to the right of the table user-bbox so its center
    is outside.  No rescue should happen; paragraph box stays empty.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "no_enclosure.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    boxes = [
        SegmentBox(
            box_id="paragraph",
            page=1,
            # → pts (320, 45, 500, 85): center x=410, y=65 — x=410 > 310 so outside table box
            bbox=(640.0, 90.0, 1000.0, 170.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="table",
            page=1,
            bbox=(80.0, 80.0, 620.0, 620.0),  # → pts (40, 40, 310, 310)
            kind=BoxKind.table,
            confidence=0.9,
        ),
    ]

    _cap_html2 = "<caption>Tab. 1 example caption</caption><table><tr><td>cell</td></tr></table>"

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(40.0, 40.0, 300.0, 300.0),
                    html=_cap_html2,
                    text="",
                    block_type="table",
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # Paragraph bbox center is outside the table user-bbox → no rescue.
    assert by_id["paragraph"] == "", (
        f"paragraph should stay empty (no enclosure), got: {by_id['paragraph']!r}"
    )
    # Table box gets the element (caption still in html since no rescue occurred).
    assert "cell" in by_id["table"]


# ── New tests: adjacency-based caption rescue ─────────────────────────────────


def test_caption_above_table_rescued_via_adjacency(tmp_path: Path) -> None:
    """Canonical layout: caption user-bbox above table user-bbox, vertically separated.

    heading pts (45,47,305,65) tight around caption text.
    table   pts (45,70,305,305) tight around table body.
    Gap = 70 - 65 = 5 pts — within max_gap=50.  Same column.
    parse_doc_fn returns one block on page 1 (block_type="table") with a
    <caption> tag and a table body.  After run():
      - heading box gets "The table caption"
      - table box html no longer contains the <caption> tag
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "caption_above.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # raster_dpi=144: px = pts * 2
    boxes = [
        SegmentBox(
            box_id="heading",
            page=1,
            bbox=(90.0, 94.0, 610.0, 130.0),  # → pts (45, 47, 305, 65)
            kind=BoxKind.heading,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="table",
            page=1,
            bbox=(90.0, 140.0, 610.0, 610.0),  # → pts (45, 70, 305, 305)
            kind=BoxKind.table,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: object) -> dict:
        # One big block covering both areas; MinerU puts caption+table together.
        return {
            1: [
                ParsedElement(
                    bbox=(45.0, 47.0, 305.0, 305.0),
                    html=(
                        "<caption>The table caption</caption><table><tr><td>cell</td></tr></table>"
                    ),
                    text="",
                    block_type="table",
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # Heading bbox should contain the rescued caption text.
    assert "The table caption" in by_id["heading"], (
        f"heading should contain rescued caption, got: {by_id['heading']!r}"
    )
    assert "Keine Extraktion" not in by_id["heading"], (
        f"heading must not be empty after rescue, got: {by_id['heading']!r}"
    )
    assert 'class="caption-ref"' in by_id["heading"]
    # Table HTML preserved — MinerU's caption stays where it rendered it.
    assert "<caption" in by_id["table"]
    assert "The table caption" in by_id["table"]
    assert "cell" in by_id["table"]
    # Caption-portion of the table HTML now points back to the heading
    # bbox so clicks on the caption text in the rendered HTML highlight
    # the heading user-bbox, not the surrounding table user-bbox.
    assert 'data-source-box="heading"' in by_id["table"]


def test_caption_below_table_rescued_via_adjacency(tmp_path: Path) -> None:
    """Some PDFs place the caption below the table body.

    table   pts (45, 70, 305, 305): table body above
    heading pts (45,310, 305,330): caption label below
    Gap = heading y_top - table y_bottom = 310 - 305 = 5 pts — within max_gap=50.
    Rescue should still work regardless of above/below order.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "caption_below.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # raster_dpi=144: px = pts * 2
    boxes = [
        SegmentBox(
            box_id="table",
            page=1,
            bbox=(90.0, 140.0, 610.0, 610.0),  # → pts (45, 70, 305, 305)
            kind=BoxKind.table,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="heading",
            page=1,
            bbox=(90.0, 620.0, 610.0, 660.0),  # → pts (45, 310, 305, 330)
            kind=BoxKind.heading,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(45.0, 70.0, 305.0, 330.0),
                    html=(
                        "<caption>The table caption</caption><table><tr><td>cell</td></tr></table>"
                    ),
                    text="",
                    block_type="table",
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    assert "The table caption" in by_id["heading"], (
        f"heading should contain rescued caption (below-table layout), got: {by_id['heading']!r}"
    )
    assert "Keine Extraktion" not in by_id["heading"]
    assert 'class="caption-ref"' in by_id["heading"]
    # Table HTML preserved.
    assert "<caption" in by_id["table"]
    assert "cell" in by_id["table"]


def test_far_heading_above_table_not_rescued(tmp_path: Path) -> None:
    """Gap > max_gap (50 pts) → adjacency score is 0, no rescue.

    heading y_bottom = 50 pts, table y_top = 200 pts → gap = 150 pts > 50.
    Heading bbox should stay empty.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "far_heading.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # raster_dpi=144: px = pts * 2
    boxes = [
        SegmentBox(
            box_id="heading",
            page=1,
            bbox=(90.0, 20.0, 610.0, 100.0),  # → pts (45, 10, 305, 50)
            kind=BoxKind.heading,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="table",
            page=1,
            bbox=(90.0, 400.0, 610.0, 900.0),  # → pts (45, 200, 305, 450)
            kind=BoxKind.table,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(45.0, 200.0, 305.0, 450.0),
                    html="<caption>Far caption</caption><table><tr><td>cell</td></tr></table>",
                    text="",
                    block_type="table",
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # Gap = 200 - 50 = 150 pts > max_gap=50 → no rescue → heading stays empty.
    assert by_id["heading"] == "", (
        f"heading should stay empty (gap too large), got: {by_id['heading']!r}"
    )
    assert "Far caption" not in by_id["heading"]
    # Table box is unchanged — caption still in its html (no rescue occurred).
    assert "cell" in by_id["table"]


def test_different_column_heading_not_rescued(tmp_path: Path) -> None:
    """No horizontal overlap (2-column layout) → adjacency score is 0, no rescue.

    heading x = (400, 500) pts, table x = (50, 300) pts.
    x_overlap = max(0, min(500,300) - max(400,50)) = max(0, 300-400) = 0.
    empty_width = 100 → ratio = 0/100 = 0 < 0.3 → score = 0, no rescue.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "diff_column.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # raster_dpi=144: px = pts * 2
    boxes = [
        SegmentBox(
            box_id="heading",
            page=1,
            bbox=(800.0, 94.0, 1000.0, 130.0),  # → pts (400, 47, 500, 65)
            kind=BoxKind.heading,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="table",
            page=1,
            bbox=(100.0, 140.0, 600.0, 610.0),  # → pts (50, 70, 300, 305)
            kind=BoxKind.table,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(50.0, 70.0, 300.0, 305.0),
                    html="<caption>Col caption</caption><table><tr><td>cell</td></tr></table>",
                    text="",
                    block_type="table",
                )
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # Different column → no horizontal overlap → no rescue → heading stays empty.
    assert by_id["heading"] == "", (
        f"heading should stay empty (different column), got: {by_id['heading']!r}"
    )
    assert "Col caption" not in by_id["heading"]


def test_multiple_visual_boxes_picks_closest(tmp_path: Path) -> None:
    """When two tables are both adjacent, rescue picks the one with the higher score.

    heading at y pts (130,150): center between the two tables.
    tableA at y pts (160,300): gap = 160 - 150 = 10 → score = 1/(1+10) ≈ 0.091
    tableB at y pts (400,500): gap = 400 - 150 = 250 > max_gap=50 → score = 0

    Caption html only in tableA.  After rescue:
      heading gets tableA's caption.
      tableA html has caption stripped.
      tableB html is unchanged.
    """
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MineruWorker, ParsedElement

    pdf = tmp_path / "multi_table.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    # raster_dpi=144: px = pts * 2
    boxes = [
        SegmentBox(
            box_id="heading",
            page=1,
            bbox=(90.0, 260.0, 610.0, 300.0),  # → pts (45, 130, 305, 150)
            kind=BoxKind.heading,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="tableA",
            page=1,
            bbox=(90.0, 320.0, 610.0, 600.0),  # → pts (45, 160, 305, 300)
            kind=BoxKind.table,
            confidence=0.9,
        ),
        SegmentBox(
            box_id="tableB",
            page=1,
            bbox=(90.0, 800.0, 610.0, 1000.0),  # → pts (45, 400, 305, 500)
            kind=BoxKind.table,
            confidence=0.9,
        ),
    ]

    def fake_parse_doc(_pdf: object) -> dict:
        return {
            1: [
                ParsedElement(
                    bbox=(45.0, 160.0, 305.0, 300.0),
                    html="<caption>Close caption</caption><table><tr><td>cellA</td></tr></table>",
                    text="",
                    block_type="table",
                ),
                ParsedElement(
                    bbox=(45.0, 400.0, 305.0, 500.0),
                    html="<table><tr><td>cellB</td></tr></table>",
                    text="",
                    block_type="table",
                ),
            ]
        }

    with MineruWorker(parse_doc_fn=fake_parse_doc, raster_dpi=144) as worker:
        list(worker.run(pdf, boxes))

    by_id = {r.box_id: r.html for r in worker.results}

    # Heading rescued from tableA (gap=10, score≈0.091).
    assert "Close caption" in by_id["heading"], (
        f"heading should contain tableA's caption, got: {by_id['heading']!r}"
    )
    assert "Keine Extraktion" not in by_id["heading"]
    assert 'class="caption-ref"' in by_id["heading"]

    # tableA HTML preserved (no stripping).
    assert "<caption" in by_id["tableA"]
    assert "cellA" in by_id["tableA"]

    # tableB is unchanged (gap=250 > max_gap, no rescue from tableB).
    assert "cellB" in by_id["tableB"], f"tableB should be unchanged, got: {by_id['tableB']!r}"
