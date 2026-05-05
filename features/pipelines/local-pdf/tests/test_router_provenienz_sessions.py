import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _seed_doc_with_chunk(client, slug: str = "doc"):
    """Upload a doc + write a mineru.json so the chunk lookup succeeds."""
    import io

    from local_pdf.storage.sidecar import write_mineru

    r = client.post(
        "/api/admin/docs",
        headers={"X-Auth-Token": "tok"},
        files={"file": (f"{slug}.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    assert r.status_code == 201
    actual = r.json()["slug"]
    cfg = client.app.state.config
    write_mineru(
        cfg.data_root,
        actual,
        {
            "elements": [{"box_id": "p1-b0", "html_snippet": "<p>The chunk text.</p>"}],
            "diagnostics": [],
        },
    )
    return actual


def test_create_session_round_trips(client):
    slug = _seed_doc_with_chunk(client)
    r = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    )
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["status"] == "open"
    assert s["slug"] == slug
    assert s["root_chunk_id"] == "p1-b0"
    sid = s["session_id"]
    assert len(sid) == 26  # ULID-shape

    listing = client.get("/api/admin/provenienz/sessions", headers={"X-Auth-Token": "tok"}).json()
    assert any(x["session_id"] == sid for x in listing)

    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    assert detail["meta"]["session_id"] == sid
    chunk_nodes = [n for n in detail["nodes"] if n["kind"] == "chunk"]
    assert len(chunk_nodes) == 1
    assert chunk_nodes[0]["payload"]["box_id"] == "p1-b0"
    assert "The chunk text" in chunk_nodes[0]["payload"]["text"]
    assert detail["edges"] == []


def test_create_404_when_doc_missing(client):
    r = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": "nope", "root_chunk_id": "p1-b0"},
    )
    assert r.status_code == 404


def test_create_404_when_chunk_missing(client):
    slug = _seed_doc_with_chunk(client)
    r = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "does-not-exist"},
    )
    assert r.status_code == 404


def test_list_sessions_filtered_by_slug(client):
    slug = _seed_doc_with_chunk(client)
    sid = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    ).json()["session_id"]
    r = client.get(
        f"/api/admin/provenienz/sessions?slug={slug}",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    body = r.json()
    assert any(x["session_id"] == sid for x in body)


def test_delete_session_removes_dir(client):
    slug = _seed_doc_with_chunk(client)
    sid = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    ).json()["session_id"]
    r = client.delete(f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 204
    listing = client.get("/api/admin/provenienz/sessions", headers={"X-Auth-Token": "tok"}).json()
    assert all(x["session_id"] != sid for x in listing)


def test_get_404_when_session_unknown(client):
    r = client.get("/api/admin/provenienz/sessions/missing-id", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 404


def test_delete_404_when_session_unknown(client):
    r = client.delete("/api/admin/provenienz/sessions/missing-id", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 404
