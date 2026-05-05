from pathlib import Path

from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
from local_pdf.provenienz.searcher import InDocSearcher, SearchHit
from local_pdf.storage.sidecar import write_mineru, write_segments


def _seed(tmp_path: Path, slug: str = "doc") -> None:
    boxes = [
        SegmentBox(
            box_id="p1-b0",
            page=1,
            bbox=(0, 0, 100, 50),
            kind=BoxKind.paragraph,
            confidence=1.0,
            reading_order=0,
        ),
        SegmentBox(
            box_id="p2-b0",
            page=2,
            bbox=(0, 0, 100, 50),
            kind=BoxKind.paragraph,
            confidence=1.0,
            reading_order=0,
        ),
    ]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        tmp_path,
        slug,
        {
            "elements": [
                {
                    "box_id": "p1-b0",
                    "html_snippet": ("<p>Gesamtwärmeleistung der Anlage. Wärmeleistung 5.6 kW</p>"),
                },
                {"box_id": "p2-b0", "html_snippet": "<p>Wetterbericht Berlin</p>"},
            ],
            "diagnostics": [],
        },
    )


def test_in_doc_searcher_returns_relevant_hits(tmp_path: Path):
    _seed(tmp_path)
    s = InDocSearcher(data_root=tmp_path, slug="doc")
    hits = s.search("Wärmeleistung kW", top_k=5)
    assert len(hits) >= 1
    assert hits[0].box_id == "p1-b0"
    assert hits[0].score > 0
    assert hits[0].searcher == "in_doc"
    assert hits[0].doc_slug == "doc"
    assert "Gesamtwärmeleistung" in hits[0].text


def test_in_doc_searcher_excludes_self_when_provided(tmp_path: Path):
    _seed(tmp_path)
    s = InDocSearcher(data_root=tmp_path, slug="doc", exclude_box_ids=("p1-b0",))
    hits = s.search("Wärmeleistung", top_k=5)
    assert all(h.box_id != "p1-b0" for h in hits)


def test_in_doc_searcher_returns_empty_for_empty_query(tmp_path: Path):
    _seed(tmp_path)
    s = InDocSearcher(data_root=tmp_path, slug="doc")
    assert s.search("", top_k=5) == []
    assert s.search("   ", top_k=5) == []


def test_in_doc_searcher_returns_empty_when_no_mineru(tmp_path: Path):
    s = InDocSearcher(data_root=tmp_path, slug="missing")
    assert s.search("anything", top_k=5) == []


def test_in_doc_searcher_drops_zero_scores(tmp_path: Path):
    _seed(tmp_path)
    s = InDocSearcher(data_root=tmp_path, slug="doc")
    # query has no overlap with either chunk
    hits = s.search("xyzzy nonsense", top_k=5)
    assert hits == []


def test_search_hit_dataclass_shape(tmp_path: Path):
    _seed(tmp_path)
    s = InDocSearcher(data_root=tmp_path, slug="doc")
    hits = s.search("Wärmeleistung", top_k=5)
    assert isinstance(hits[0], SearchHit)
    assert hits[0].box_id and hits[0].text and hits[0].doc_slug == "doc"
