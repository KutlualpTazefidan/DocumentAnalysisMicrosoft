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
