# features/pipelines/local-pdf/tests/test_routers_docs.py
from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def client_and_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app()), root


def _pdf_bytes() -> bytes:
    # Minimal valid-ish PDF header. pdfplumber will fail to parse this so the
    # upload route only checks magic + persists; page count comes from a
    # tolerant counter implemented in the router (or fallback to 0).
    return b"%PDF-1.4\n%%EOF\n"


def test_upload_pdf_creates_slug_dir(client_and_root) -> None:
    client, root = client_and_root
    files = {"file": ("BAM Tragkorb 2024.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    resp = client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "bam-tragkorb-2024"
    assert body["status"] == "raw"
    assert (root / "bam-tragkorb-2024" / "source.pdf").exists()
    assert (root / "bam-tragkorb-2024" / "meta.json").exists()


def test_upload_collision_appends_counter(client_and_root) -> None:
    client, root = client_and_root
    (root / "report").mkdir()
    files = {"file": ("Report.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    resp = client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    assert resp.status_code == 201
    assert resp.json()["slug"] == "report-2"


def test_upload_rejects_non_pdf(client_and_root) -> None:
    client, _ = client_and_root
    files = {"file": ("note.txt", io.BytesIO(b"hello"), "text/plain")}
    resp = client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    assert resp.status_code == 400


def test_inbox_lists_uploaded_docs(client_and_root) -> None:
    client, _ = client_and_root
    files1 = {"file": ("A.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    files2 = {"file": ("B.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files1)
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files2)
    resp = client.get("/api/docs", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    slugs = {d["slug"] for d in resp.json()}
    assert slugs == {"a", "b"}


def test_get_doc_returns_meta(client_and_root) -> None:
    client, _ = client_and_root
    files = {"file": ("Spec.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    resp = client.get("/api/docs/spec", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    assert resp.json()["slug"] == "spec"


def test_get_unknown_doc_returns_404(client_and_root) -> None:
    client, _ = client_and_root
    resp = client.get("/api/docs/nonexistent", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404


def test_source_pdf_serves_bytes(client_and_root) -> None:
    client, _ = client_and_root
    files = {"file": ("Spec.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    resp = client.get("/api/docs/spec/source.pdf", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == _pdf_bytes()
