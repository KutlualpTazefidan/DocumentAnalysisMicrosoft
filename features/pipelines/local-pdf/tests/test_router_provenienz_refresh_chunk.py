"""Tests for the chunk-refresh endpoint (Phase B).

POST /api/admin/provenienz/sessions/{session_id}/chunks/{chunk_node_id}/refresh

Append-only audit semantics: when the underlying mineru.json /
segments.json content has been edited in the Extract tab, calling this
endpoint spawns a fresh chunk Node with the current text + metadata and
draws a ``refreshes`` edge new_chunk → old_chunk. The old chunk plus
all its descendants stay intact for audit.
"""

import io

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


def _seed(
    client,
    *,
    html: str = "<p>Original chunk text.</p>",
    reading_order: int = 1,
    kind: str = "paragraph",
):
    """Upload a doc, write mineru + segments, return (slug, session_id, chunk_node_id)."""
    from local_pdf.api.schemas import SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_mineru, write_segments

    r = client.post(
        "/api/admin/docs",
        headers={"X-Auth-Token": "tok"},
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    assert r.status_code == 201
    slug = r.json()["slug"]
    cfg = client.app.state.config
    write_mineru(
        cfg.data_root,
        slug,
        {"elements": [{"box_id": "p1-b0", "html_snippet": html}], "diagnostics": []},
    )
    write_segments(
        cfg.data_root,
        slug,
        SegmentsFile(
            slug=slug,
            boxes=[
                SegmentBox(
                    box_id="p1-b0",
                    page=1,
                    bbox=(0.0, 0.0, 100.0, 50.0),
                    kind=kind,
                    confidence=0.9,
                    reading_order=reading_order,
                    manually_activated=False,
                    continues_from=None,
                    continues_to=None,
                ),
            ],
        ),
    )
    r = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    )
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}",
        headers={"X-Auth-Token": "tok"},
    ).json()
    chunk = next(n for n in detail["nodes"] if n["kind"] == "chunk")
    return slug, sid, chunk["node_id"]


def test_refresh_chunk_no_op_when_source_unchanged(client):
    """When mineru.json + segments.json haven't been touched since session
    creation, the endpoint must return refreshed=False and NOT append a
    new chunk Node."""
    _, sid, chunk_id = _seed(client)

    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/chunks/{chunk_id}/refresh",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refreshed"] is False
    assert body["reason"] == "current"
    assert body["new_chunk"] is None

    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}",
        headers={"X-Auth-Token": "tok"},
    ).json()
    chunk_nodes = [n for n in detail["nodes"] if n["kind"] == "chunk"]
    assert len(chunk_nodes) == 1
    assert detail["edges"] == []


def test_refresh_chunk_appends_new_node_when_source_diverged(client):
    """Edit mineru.json + segments.json after session creation, then
    refresh: a new chunk Node with refreshed text + metadata is appended,
    a ``refreshes`` edge new → old is drawn, and the old chunk + its
    payload stay untouched for audit."""
    from local_pdf.api.schemas import SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_mineru, write_segments

    slug, sid, chunk_id = _seed(client)
    cfg = client.app.state.config

    # Simulate Extract-tab edit: text changes + reading_order shifts.
    write_mineru(
        cfg.data_root,
        slug,
        {
            "elements": [
                {"box_id": "p1-b0", "html_snippet": "<p>Edited and improved chunk text.</p>"}
            ],
            "diagnostics": [],
        },
    )
    write_segments(
        cfg.data_root,
        slug,
        SegmentsFile(
            slug=slug,
            boxes=[
                SegmentBox(
                    box_id="p1-b0",
                    page=1,
                    bbox=(0.0, 0.0, 100.0, 50.0),
                    kind="paragraph",
                    confidence=0.95,
                    reading_order=7,  # changed
                    manually_activated=False,
                    continues_from=None,
                    continues_to=None,
                ),
            ],
        ),
    )

    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/chunks/{chunk_id}/refresh",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refreshed"] is True
    assert body["reason"] == "updated"
    new_chunk = body["new_chunk"]
    assert new_chunk is not None
    assert new_chunk["kind"] == "chunk"
    assert new_chunk["node_id"] != chunk_id
    assert new_chunk["payload"]["box_id"] == "p1-b0"
    assert "Edited and improved" in new_chunk["payload"]["text"]
    assert new_chunk["payload"]["reading_order"] == 7

    # Old chunk untouched, new chunk appended, refreshes edge present.
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}",
        headers={"X-Auth-Token": "tok"},
    ).json()
    chunk_nodes = [n for n in detail["nodes"] if n["kind"] == "chunk"]
    assert len(chunk_nodes) == 2
    old = next(n for n in chunk_nodes if n["node_id"] == chunk_id)
    assert "Original" in old["payload"]["text"]  # unchanged
    edges = detail["edges"]
    refresh_edges = [e for e in edges if e["kind"] == "refreshes"]
    assert len(refresh_edges) == 1
    assert refresh_edges[0]["from_node"] == new_chunk["node_id"]
    assert refresh_edges[0]["to_node"] == chunk_id


def test_refresh_chunk_404_when_chunk_missing(client):
    _, sid, _ = _seed(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/chunks/does-not-exist/refresh",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 404


def test_refresh_chunk_400_when_node_is_not_a_chunk(client):
    """Pointing the endpoint at a non-chunk node id (e.g. a claim) is a
    client error, not a silent no-op."""
    from local_pdf.provenienz.storage import Node, append_node, new_id, session_dir

    slug, sid, _ = _seed(client)
    cfg = client.app.state.config
    sd = session_dir(cfg.data_root, slug, sid)
    fake_claim = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="claim",
            payload={"text": "x"},
            actor="human",
        ),
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/chunks/{fake_claim.node_id}/refresh",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 400


def test_refresh_chunk_does_not_cascade_delete(client):
    """The ``refreshes`` edge must NOT be in _DEPENDS_ON_EDGE_KINDS:
    deleting either chunk should leave the other intact (modulo the
    deleted one's own subtree)."""
    from local_pdf.api.schemas import SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_mineru, write_segments

    slug, sid, old_chunk_id = _seed(client)
    cfg = client.app.state.config
    write_mineru(
        cfg.data_root,
        slug,
        {
            "elements": [{"box_id": "p1-b0", "html_snippet": "<p>New text.</p>"}],
            "diagnostics": [],
        },
    )
    write_segments(
        cfg.data_root,
        slug,
        SegmentsFile(
            slug=slug,
            boxes=[
                SegmentBox(
                    box_id="p1-b0",
                    page=1,
                    bbox=(0.0, 0.0, 100.0, 50.0),
                    kind="paragraph",
                    confidence=0.9,
                    reading_order=2,
                    manually_activated=False,
                    continues_from=None,
                    continues_to=None,
                ),
            ],
        ),
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/chunks/{old_chunk_id}/refresh",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    new_chunk_id = r.json()["new_chunk"]["node_id"]

    # Delete the new chunk → old chunk must survive.
    r = client.delete(
        f"/api/admin/provenienz/sessions/{sid}/nodes/{new_chunk_id}",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 204
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}",
        headers={"X-Auth-Token": "tok"},
    ).json()
    chunks = [n for n in detail["nodes"] if n["kind"] == "chunk"]
    assert len(chunks) == 1
    assert chunks[0]["node_id"] == old_chunk_id
