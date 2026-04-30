from __future__ import annotations


def test_convert_html_and_segments_to_source_elements_payload() -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.convert.source_elements import build_source_elements_payload

    segments = SegmentsFile(
        slug="rep",
        boxes=[
            SegmentBox(
                box_id="p1-b0",
                page=1,
                bbox=(10, 20, 100, 50),
                kind=BoxKind.heading,
                confidence=0.95,
            ),
            SegmentBox(
                box_id="p1-b1",
                page=1,
                bbox=(10, 60, 100, 200),
                kind=BoxKind.paragraph,
                confidence=0.88,
            ),
            SegmentBox(
                box_id="p1-b2",
                page=1,
                bbox=(10, 210, 100, 250),
                kind=BoxKind.discard,
                confidence=0.4,
            ),
        ],
    )
    html = (
        "<!DOCTYPE html><html><body>"
        '<h1 data-source-box="p1-b0">3 Prüfverfahren</h1>'
        '<p data-source-box="p1-b1">Die Prüfung des Tragkorbs.</p>'
        '<p data-source-box="p1-b2">discarded</p>'
        "</body></html>"
    )
    payload = build_source_elements_payload(slug="rep", segments=segments, html=html)
    assert payload["doc_slug"] == "rep"
    assert payload["source_pipeline"] == "local-pdf"
    elements = payload["elements"]
    assert len(elements) == 2
    assert elements[0] == {
        "kind": "heading",
        "page": 1,
        "bbox": [10.0, 20.0, 100.0, 50.0],
        "text": "3 Prüfverfahren",
        "level": 1,
        "box_id": "p1-b0",
    }
    assert elements[1]["kind"] == "paragraph"
    assert elements[1]["text"] == "Die Prüfung des Tragkorbs."


def test_converter_strips_html_tags_inside_text() -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.convert.source_elements import build_source_elements_payload

    segments = SegmentsFile(
        slug="x",
        boxes=[
            SegmentBox(
                box_id="p1-b0", page=1, bbox=(0, 0, 1, 1), kind=BoxKind.paragraph, confidence=0.9
            )
        ],
    )
    html = '<p data-source-box="p1-b0">Hello <em>world</em>!</p>'
    payload = build_source_elements_payload(slug="x", segments=segments, html=html)
    assert payload["elements"][0]["text"] == "Hello world!"


def test_export_writes_sourceelements_json(tmp_path) -> None:
    """End-to-end: build payload + write_source_elements stores correct JSON."""
    import json

    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.convert.source_elements import build_source_elements_payload
    from local_pdf.storage.sidecar import doc_dir, write_source_elements

    slug = "rep"
    doc_dir(tmp_path, slug).mkdir()
    segments = SegmentsFile(
        slug=slug,
        boxes=[
            SegmentBox(
                box_id="p1-b0", page=1, bbox=(0, 0, 1, 1), kind=BoxKind.paragraph, confidence=0.9
            )
        ],
    )
    html = '<p data-source-box="p1-b0">Hi</p>'
    payload = build_source_elements_payload(slug=slug, segments=segments, html=html)
    write_source_elements(tmp_path, slug, payload)
    loaded = json.loads(
        (doc_dir(tmp_path, slug) / "sourceelements.json").read_text(encoding="utf-8")
    )
    assert loaded == payload
