from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


@pytest.fixture
def client_with_multipage_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Client pre-loaded with a doc that has boxes on two different pages."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_segments

    client = TestClient(create_app())
    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    boxes = [
        SegmentBox(
            box_id="p1-aa",
            page=1,
            bbox=(0.0, 0.0, 100.0, 50.0),
            kind=BoxKind.paragraph,
            confidence=0.9,
            reading_order=0,
        ),
        SegmentBox(
            box_id="p2-bb",
            page=2,
            bbox=(0.0, 0.0, 100.0, 50.0),
            kind=BoxKind.heading,
            confidence=0.85,
            reading_order=0,
        ),
        SegmentBox(
            box_id="p2-cc",
            page=2,
            bbox=(0.0, 60.0, 100.0, 120.0),
            kind=BoxKind.paragraph,
            confidence=0.8,
            reading_order=1,
        ),
    ]
    write_segments(root, "spec", SegmentsFile(slug="spec", boxes=boxes))
    return client


def _stub_extract(client, monkeypatch):
    """Patch MineruWorker so extract returns a minimal result without GPU."""
    import local_pdf.api.routers.admin.extract as ext_mod

    captured: list[int] = []

    def fake_fn(pdf_path, box):
        captured.append(box.page)
        return type("R", (), {"box_id": box.box_id, "html": f"<p>{box.box_id}</p>"})()

    ext_mod._MINERU_EXTRACT_FN = fake_fn
    return captured


def test_admin_html_404_when_missing(client) -> None:
    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    r = client.get("/api/admin/docs/spec/html", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 404


def test_admin_put_html_round_trip(client) -> None:
    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    r = client.put(
        "/api/admin/docs/spec/html",
        headers={"X-Auth-Token": "tok"},
        json={"html": "<p>hi</p>"},
    )
    assert r.status_code == 200
    g = client.get("/api/admin/docs/spec/html", headers={"X-Auth-Token": "tok"})
    assert g.json()["html"] == "<p>hi</p>"


def test_extract_page_filter_limits_targets(client_with_multipage_segments, monkeypatch) -> None:
    """?page=1 must only process boxes whose page == 1, not page 2 boxes."""
    import local_pdf.api.routers.admin.extract as ext_mod

    pages_seen: list[int] = []

    def fake_fn(pdf_path, box):
        pages_seen.append(box.page)
        return type("R", (), {"box_id": box.box_id, "html": f"<p>{box.box_id}</p>"})()

    ext_mod._MINERU_EXTRACT_FN = fake_fn
    r = client_with_multipage_segments.post(
        "/api/admin/docs/spec/extract?page=1",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    # Consume the streaming response so the generator runs fully.
    list(r.iter_lines())
    assert pages_seen == [1], f"expected only page-1 boxes, got pages: {pages_seen}"


def test_extract_no_page_filter_processes_all(client_with_multipage_segments, monkeypatch) -> None:
    """Without ?page, all non-discard boxes from every page are processed."""
    import local_pdf.api.routers.admin.extract as ext_mod

    pages_seen: list[int] = []

    def fake_fn(pdf_path, box):
        pages_seen.append(box.page)
        return type("R", (), {"box_id": box.box_id, "html": f"<p>{box.box_id}</p>"})()

    ext_mod._MINERU_EXTRACT_FN = fake_fn
    r = client_with_multipage_segments.post(
        "/api/admin/docs/spec/extract",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    list(r.iter_lines())
    assert sorted(pages_seen) == [1, 2, 2], f"expected boxes from both pages, got: {pages_seen}"


def test_diagnose_returns_503_when_mineru_missing(client, monkeypatch) -> None:
    """GET /extract/diagnose returns 503 when MinerU is not installed."""
    # Patch the import by raising inside the endpoint's try block.
    original_import = __import__

    def _raise_on_mineru(name, *args, **kwargs):
        if name.startswith("mineru.backend.pipeline.pipeline_analyze"):
            raise ImportError("MinerU not installed (test stub)")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _raise_on_mineru)

    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    r = client.get(
        "/api/admin/docs/spec/extract/diagnose?page=1",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 503


def test_diagnose_returns_404_for_missing_pdf(client) -> None:
    """GET /extract/diagnose on a slug with no PDF returns 404."""
    r = client.get(
        "/api/admin/docs/nonexistent/extract/diagnose?page=1",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 404


def test_get_mineru_404_before_extraction(client) -> None:
    """GET /mineru returns 404 when no extraction has been run yet."""
    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    r = client.get("/api/admin/docs/spec/mineru", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 404


def test_get_mineru_returns_stored_data(client, monkeypatch) -> None:
    """GET /mineru returns the elements written by a prior extraction run."""
    from local_pdf.storage.sidecar import write_mineru

    root = client.app.state.config.data_root
    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    # Write mineru data directly.
    payload = {"elements": [{"box_id": "p1-b0", "html_snippet": "<p>hi</p>"}]}
    write_mineru(root, "spec", payload)
    r = client.get("/api/admin/docs/spec/mineru", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    assert r.json()["elements"][0]["box_id"] == "p1-b0"


# ---------------------------------------------------------------------------
# _wrap_html unit tests
# ---------------------------------------------------------------------------


def test_wrap_html_single_page_produces_section_no_hr() -> None:
    """_wrap_html wraps a single-page extraction in a section[data-page] — no hr."""
    from local_pdf.api.routers.admin.extract import _wrap_html

    html = _wrap_html([{"box_id": "p8-b0", "html_snippet": "<p>x</p>"}])
    assert '<section data-page="8">' in html
    assert "<hr" not in html
    assert "page-break" not in html


def test_wrap_html_multi_page_groups_correctly() -> None:
    """_wrap_html groups three elements across two pages into two sections."""
    from local_pdf.api.routers.admin.extract import _wrap_html

    elements = [
        {"box_id": "p1-b0", "html_snippet": "<p>a</p>"},
        {"box_id": "p1-b1", "html_snippet": "<p>b</p>"},
        {"box_id": "p2-b0", "html_snippet": "<p>c</p>"},
    ]
    html = _wrap_html(elements)
    assert html.count("<section data-page=") == 2
    assert '<section data-page="1">' in html
    assert '<section data-page="2">' in html
    # Both p1 snippets are inside the page-1 section.
    p1_start = html.index('<section data-page="1">')
    p2_start = html.index('<section data-page="2">')
    assert html.index("<p>a</p>") < p2_start
    assert html.index("<p>b</p>") < p2_start
    assert html.index("<p>c</p>") > p1_start


def test_wrap_html_skips_elements_without_box_id() -> None:
    """Elements with no parseable box_id are silently skipped."""
    from local_pdf.api.routers.admin.extract import _wrap_html

    elements = [
        {"box_id": "p3-b0", "html_snippet": "<p>good</p>"},
        {"box_id": "", "html_snippet": "<p>bad</p>"},
        {"box_id": "p3-b1", "html_snippet": "<p>also-good</p>"},
    ]
    html = _wrap_html(elements)
    assert "<p>good</p>" in html
    assert "<p>also-good</p>" in html
    assert "<p>bad</p>" not in html


# ---------------------------------------------------------------------------
# _merge_elements unit tests
# ---------------------------------------------------------------------------


def test_merge_elements_replaces_existing_box_id() -> None:
    """_merge_elements replaces an element when box_id already exists."""
    from local_pdf.api.routers.admin.extract import _merge_elements

    existing = [{"box_id": "p1-b0", "html_snippet": "<p>old</p>"}]
    new = [{"box_id": "p1-b0", "html_snippet": "<p>new</p>"}]
    result = _merge_elements(existing, new)
    assert len(result) == 1
    assert result[0]["html_snippet"] == "<p>new</p>"


def test_merge_elements_appends_novel_box_ids() -> None:
    """_merge_elements appends elements whose box_id doesn't exist yet."""
    from local_pdf.api.routers.admin.extract import _merge_elements

    existing = [{"box_id": "p1-b0", "html_snippet": "<p>p1</p>"}]
    new = [{"box_id": "p2-b0", "html_snippet": "<p>p2</p>"}]
    result = _merge_elements(existing, new)
    assert len(result) == 2
    assert result[0]["box_id"] == "p1-b0"
    assert result[1]["box_id"] == "p2-b0"


# ---------------------------------------------------------------------------
# Partial extraction preserves other pages (integration-level)
# ---------------------------------------------------------------------------


def test_partial_extraction_preserves_other_pages(
    client_with_multipage_segments, monkeypatch
) -> None:
    """Extracting page 1 then page 2 keeps both pages' elements in mineru.json + HTML."""
    import local_pdf.api.routers.admin.extract as ext_mod
    from local_pdf.storage.sidecar import read_mineru

    root = client_with_multipage_segments.app.state.config.data_root

    def fake_fn(pdf_path, box):
        return type("R", (), {"box_id": box.box_id, "html": f"<p>{box.box_id}</p>"})()

    ext_mod._MINERU_EXTRACT_FN = fake_fn

    # Extract page 1 only.
    r1 = client_with_multipage_segments.post(
        "/api/admin/docs/spec/extract?page=1",
        headers={"X-Auth-Token": "tok"},
    )
    assert r1.status_code == 200
    list(r1.iter_lines())

    after_p1 = read_mineru(root, "spec")
    assert after_p1 is not None
    p1_ids = {e["box_id"] for e in after_p1["elements"]}
    assert "p1-aa" in p1_ids
    assert "p2-bb" not in p1_ids

    # Now extract page 2 — page 1 elements must still be present.
    r2 = client_with_multipage_segments.post(
        "/api/admin/docs/spec/extract?page=2",
        headers={"X-Auth-Token": "tok"},
    )
    assert r2.status_code == 200
    list(r2.iter_lines())

    after_p2 = read_mineru(root, "spec")
    assert after_p2 is not None
    ids = {e["box_id"] for e in after_p2["elements"]}
    assert "p1-aa" in ids, "page 1 element must survive partial page-2 extraction"
    assert "p2-bb" in ids
    assert "p2-cc" in ids

    # The HTML must contain sections for both pages.
    from local_pdf.storage.sidecar import read_html

    html = read_html(root, "spec")
    assert html is not None
    assert '<section data-page="1">' in html
    assert '<section data-page="2">' in html


def test_reextract_page1_replaces_only_page1_elements(
    client_with_multipage_segments, monkeypatch
) -> None:
    """Re-extracting page 1 replaces page-1 elements without touching page-2 elements."""
    import local_pdf.api.routers.admin.extract as ext_mod
    from local_pdf.storage.sidecar import read_mineru

    root = client_with_multipage_segments.app.state.config.data_root

    # Use a mutable container so the inner closure can flip the suffix between runs.
    state = {"suffix": "v1"}

    def fake_fn(pdf_path, box):
        return type(
            "R", (), {"box_id": box.box_id, "html": f"<p>{box.box_id}-{state['suffix']}</p>"}
        )()

    ext_mod._MINERU_EXTRACT_FN = fake_fn

    # Full extraction first (all boxes get v1).
    r = client_with_multipage_segments.post(
        "/api/admin/docs/spec/extract",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    list(r.iter_lines())

    # Switch to v2 suffix before the second run.
    state["suffix"] = "v2"

    # Re-extract page 1 only — only the page-1 box should get v2.
    r2 = client_with_multipage_segments.post(
        "/api/admin/docs/spec/extract?page=1",
        headers={"X-Auth-Token": "tok"},
    )
    assert r2.status_code == 200
    list(r2.iter_lines())

    data = read_mineru(root, "spec")
    assert data is not None
    by_id = {e["box_id"]: e for e in data["elements"]}
    # Page-1 element must have been replaced (v2).
    assert "v2" in by_id["p1-aa"]["html_snippet"]
    # Page-2 elements must be untouched (v1 from full extraction).
    assert "v1" in by_id["p2-bb"]["html_snippet"]
    assert "v1" in by_id["p2-cc"]["html_snippet"]
