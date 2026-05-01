from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def client_with_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    box = SegmentBox(
        box_id="p1-aaa",
        page=1,
        bbox=(0.0, 0.0, 100.0, 50.0),
        kind=BoxKind.paragraph,
        confidence=0.95,
        reading_order=0,
    )
    write_segments(root, "spec", SegmentsFile(slug="spec", boxes=[box]))
    return client


def test_admin_get_segments(client_with_segments) -> None:
    r = client_with_segments.get("/api/admin/docs/spec/segments", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    assert r.json()["boxes"][0]["box_id"] == "p1-aaa"


def test_admin_update_box(client_with_segments) -> None:
    r = client_with_segments.put(
        "/api/admin/docs/spec/segments/p1-aaa",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "heading"},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "heading"


def test_admin_delete_box(client_with_segments) -> None:
    r = client_with_segments.delete(
        "/api/admin/docs/spec/segments/p1-aaa", headers={"X-Auth-Token": "tok"}
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "discard"


def test_admin_create_box(client_with_segments) -> None:
    r = client_with_segments.post(
        "/api/admin/docs/spec/segments",
        headers={"X-Auth-Token": "tok"},
        json={"page": 1, "bbox": [0.0, 60.0, 100.0, 110.0], "kind": "paragraph"},
    )
    assert r.status_code == 201
    assert r.json()["page"] == 1
