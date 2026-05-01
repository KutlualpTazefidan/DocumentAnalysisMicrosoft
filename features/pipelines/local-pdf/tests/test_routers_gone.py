from __future__ import annotations

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


def test_old_docs_returns_410(client) -> None:
    r = client.get("/api/docs", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 410
    body = r.json()
    assert "moved to /api/admin/docs" in body["detail"].lower()


def test_old_doc_slug_returns_410(client) -> None:
    r = client.get("/api/docs/spec", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 410


def test_old_segments_returns_410(client) -> None:
    r = client.get("/api/docs/spec/segments", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 410
