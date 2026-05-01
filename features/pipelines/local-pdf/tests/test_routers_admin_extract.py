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
