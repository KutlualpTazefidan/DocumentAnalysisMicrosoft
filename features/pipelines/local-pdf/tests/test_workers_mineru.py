"""Tests for the MinerU 3 worker wrapper.

The real MinerU CLI is heavy + slow; we inject a fake `extract_fn` to
verify the wrapper's box-by-box dispatch and result-mapping behaviour.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_run_mineru_per_box_uses_injected_extract_fn(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MinerUResult, run_mineru

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    boxes = [
        SegmentBox(
            box_id="p1-b0",
            page=1,
            bbox=(10, 20, 100, 60),
            kind=BoxKind.heading,
            confidence=0.95,
        ),
        SegmentBox(
            box_id="p1-b1",
            page=1,
            bbox=(10, 70, 100, 200),
            kind=BoxKind.paragraph,
            confidence=0.88,
        ),
    ]

    def fake_extract(_pdf: Path, box: SegmentBox) -> MinerUResult:
        tag = "h1" if box.kind == BoxKind.heading else "p"
        return MinerUResult(box_id=box.box_id, html=f"<{tag}>{box.box_id}</{tag}>")

    out = list(run_mineru(pdf, boxes, extract_fn=fake_extract))
    assert len(out) == 2
    assert out[0].box_id == "p1-b0"
    assert out[0].html == "<h1>p1-b0</h1>"
    assert out[1].html == "<p>p1-b1</p>"


def test_run_mineru_skips_discard_kind(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MinerUResult, run_mineru

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    boxes = [
        SegmentBox(
            box_id="p1-b0",
            page=1,
            bbox=(10, 20, 100, 60),
            kind=BoxKind.discard,
            confidence=0.5,
        ),
        SegmentBox(
            box_id="p1-b1",
            page=1,
            bbox=(10, 70, 100, 200),
            kind=BoxKind.paragraph,
            confidence=0.9,
        ),
    ]

    def fake(_p: Path, box: SegmentBox) -> MinerUResult:
        return MinerUResult(box_id=box.box_id, html=f"<p>{box.box_id}</p>")

    out = list(run_mineru(pdf, boxes, extract_fn=fake))
    assert [r.box_id for r in out] == ["p1-b1"]


def test_run_mineru_region_calls_extract_once(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MinerUResult, run_mineru_region

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    box = SegmentBox(
        box_id="p2-b3", page=2, bbox=(50, 50, 200, 200), kind=BoxKind.table, confidence=0.7
    )

    calls: list[str] = []

    def fake(_p: Path, b: SegmentBox) -> MinerUResult:
        calls.append(b.box_id)
        return MinerUResult(box_id=b.box_id, html="<table><tr><td>x</td></tr></table>")

    out = run_mineru_region(pdf, box, extract_fn=fake)
    assert calls == ["p2-b3"]
    assert out.html.startswith("<table>")
