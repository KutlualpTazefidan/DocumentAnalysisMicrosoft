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


def _pdf() -> bytes:
    return b"%PDF-1.4\n%%EOF\n"


def test_admin_upload_creates_slug(client) -> None:
    files = {"file": ("Spec.pdf", io.BytesIO(_pdf()), "application/pdf")}
    r = client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    assert r.status_code == 201
    assert r.json()["slug"] == "spec"


def test_admin_list(client) -> None:
    files = {"file": ("A.pdf", io.BytesIO(_pdf()), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    r = client.get("/api/admin/docs", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    assert {d["slug"] for d in r.json()} == {"a"}


def test_admin_get_meta(client) -> None:
    files = {"file": ("Spec.pdf", io.BytesIO(_pdf()), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    r = client.get("/api/admin/docs/spec", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200 and r.json()["slug"] == "spec"


def test_admin_source_pdf(client) -> None:
    files = {"file": ("Spec.pdf", io.BytesIO(_pdf()), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    r = client.get("/api/admin/docs/spec/source.pdf", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
