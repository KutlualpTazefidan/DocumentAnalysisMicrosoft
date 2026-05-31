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


def test_publish_flips_status(client) -> None:
    files = {"file": ("X.pdf", io.BytesIO(_pdf()), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    # set to extracted manually for the test
    from local_pdf.api.schemas import DocStatus
    from local_pdf.storage.sidecar import read_meta, write_meta

    cfg_root = client.app.state.config.data_root
    m = read_meta(cfg_root, "x")
    write_meta(cfg_root, "x", m.model_copy(update={"status": DocStatus.extracted}))

    r = client.post("/api/admin/docs/x/publish", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    assert r.json()["status"] == "open-for-curation"


def test_archive_flips_status(client) -> None:
    files = {"file": ("Y.pdf", io.BytesIO(_pdf()), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)

    r = client.post("/api/admin/docs/y/archive", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_delete_doc_removes_directory(client, tmp_path) -> None:
    """DELETE /api/admin/docs/{slug} wipes the entire per-doc directory.

    The list endpoint should stop returning the slug afterwards.
    """
    files = {"file": ("ToDel.pdf", io.BytesIO(_pdf()), "application/pdf")}
    r = client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    slug = r.json()["slug"]

    listed = client.get("/api/admin/docs", headers={"X-Auth-Token": "tok"}).json()
    assert any(d["slug"] == slug for d in listed)

    r = client.delete(f"/api/admin/docs/{slug}", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 204

    listed = client.get("/api/admin/docs", headers={"X-Auth-Token": "tok"}).json()
    assert not any(d["slug"] == slug for d in listed)


def test_delete_doc_404_when_missing(client) -> None:
    r = client.delete("/api/admin/docs/nonexistent", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Per-page status routes
# ---------------------------------------------------------------------------


def _upload_with_pages(client, filename: str, pages: int) -> str:
    """Upload a PDF and force its meta.pages to *pages*. Returns the slug.

    The stub PDF blob always rasterises to pages=1, so multi-page range checks
    need the meta bumped directly.
    """
    from local_pdf.storage.sidecar import read_meta, write_meta

    files = {"file": (filename, io.BytesIO(_pdf()), "application/pdf")}
    r = client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    slug = r.json()["slug"]
    root = client.app.state.config.data_root
    m = read_meta(root, slug)
    write_meta(root, slug, m.model_copy(update={"pages": pages}))
    return slug


def test_get_page_status_default_empty(client) -> None:
    """GET pages/status on a fresh doc returns an empty done_pages list."""
    slug = _upload_with_pages(client, "PS1.pdf", 5)
    r = client.get(f"/api/admin/docs/{slug}/pages/status", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == slug
    assert body["done_pages"] == []


def test_get_page_status_404_unknown_slug(client) -> None:
    """GET pages/status for an unknown slug is a 404."""
    r = client.get("/api/admin/docs/ghost/pages/status", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 404


def test_patch_page_done_then_get_shows_it(client) -> None:
    """PATCH a page to done, then GET reflects it in done_pages."""
    slug = _upload_with_pages(client, "PS2.pdf", 5)
    r = client.patch(
        f"/api/admin/docs/{slug}/pages/3/status",
        headers={"X-Auth-Token": "tok"},
        json={"status": "done"},
    )
    assert r.status_code == 200
    assert r.json() == {"page": 3, "status": "done"}
    g = client.get(f"/api/admin/docs/{slug}/pages/status", headers={"X-Auth-Token": "tok"})
    assert g.json()["done_pages"] == [3]


def test_patch_not_started_removes_page(client) -> None:
    """PATCH done then PATCH not_started removes the page from done_pages."""
    slug = _upload_with_pages(client, "PS3.pdf", 5)
    client.patch(
        f"/api/admin/docs/{slug}/pages/2/status",
        headers={"X-Auth-Token": "tok"},
        json={"status": "done"},
    )
    r = client.patch(
        f"/api/admin/docs/{slug}/pages/2/status",
        headers={"X-Auth-Token": "tok"},
        json={"status": "not_started"},
    )
    assert r.status_code == 200
    assert r.json() == {"page": 2, "status": "not_started"}
    g = client.get(f"/api/admin/docs/{slug}/pages/status", headers={"X-Auth-Token": "tok"})
    assert g.json()["done_pages"] == []


def test_patch_in_progress_does_not_persist(client) -> None:
    """in_progress is derived client-side — PATCHing it never adds to done_pages."""
    slug = _upload_with_pages(client, "PS3b.pdf", 5)
    r = client.patch(
        f"/api/admin/docs/{slug}/pages/4/status",
        headers={"X-Auth-Token": "tok"},
        json={"status": "in_progress"},
    )
    assert r.status_code == 200
    g = client.get(f"/api/admin/docs/{slug}/pages/status", headers={"X-Auth-Token": "tok"})
    assert g.json()["done_pages"] == []


def test_patch_out_of_range_400(client) -> None:
    """PATCH a page beyond meta.pages (or < 1) is a 400."""
    slug = _upload_with_pages(client, "PS4.pdf", 3)
    r = client.patch(
        f"/api/admin/docs/{slug}/pages/99/status",
        headers={"X-Auth-Token": "tok"},
        json={"status": "done"},
    )
    assert r.status_code == 400
    r0 = client.patch(
        f"/api/admin/docs/{slug}/pages/0/status",
        headers={"X-Auth-Token": "tok"},
        json={"status": "done"},
    )
    assert r0.status_code == 400


def test_patch_unknown_slug_404(client) -> None:
    """PATCH pages/status for an unknown slug is a 404."""
    r = client.patch(
        "/api/admin/docs/ghost/pages/1/status",
        headers={"X-Auth-Token": "tok"},
        json={"status": "done"},
    )
    assert r.status_code == 404


def test_patch_page_status_leaves_docstatus_unchanged_bumps_touch(client) -> None:
    """PATCHing a page's status must NOT change DocStatus but MUST bump last_touched_utc."""
    from local_pdf.storage.sidecar import read_meta

    slug = _upload_with_pages(client, "PS5.pdf", 5)
    root = client.app.state.config.data_root
    before = read_meta(root, slug)
    # Force a known earlier timestamp + a distinctive status to detect drift.
    from local_pdf.api.schemas import DocStatus
    from local_pdf.storage.sidecar import write_meta

    write_meta(
        root,
        slug,
        before.model_copy(
            update={"status": DocStatus.extracting, "last_touched_utc": "2000-01-01T00:00:00Z"}
        ),
    )

    r = client.patch(
        f"/api/admin/docs/{slug}/pages/1/status",
        headers={"X-Auth-Token": "tok"},
        json={"status": "done"},
    )
    assert r.status_code == 200

    after = read_meta(root, slug)
    # DocStatus is orthogonal — must be untouched.
    assert after.status == DocStatus.extracting
    # last_touched_utc must have advanced.
    assert after.last_touched_utc != "2000-01-01T00:00:00Z"


def test_delete_doc_removes_page_status_sidecar(client) -> None:
    """DELETE of a doc wipes page_status.json along with the rest of the dir."""
    from local_pdf.storage.sidecar import _page_status_path

    slug = _upload_with_pages(client, "PS6.pdf", 5)
    client.patch(
        f"/api/admin/docs/{slug}/pages/1/status",
        headers={"X-Auth-Token": "tok"},
        json={"status": "done"},
    )
    root = client.app.state.config.data_root
    assert _page_status_path(root, slug).exists()

    r = client.delete(f"/api/admin/docs/{slug}", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 204
    assert not _page_status_path(root, slug).exists()
