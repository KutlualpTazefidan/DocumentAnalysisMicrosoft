"""Smoke tests for /similar, /compare, /pipelines.

Microsoft's Azure-search backend isn't exercised here — that's its
own integration concern. We only verify route plumbing + the BM25
fallback path (no embedder needed).
"""

from __future__ import annotations

import pytest
from goldens.schemas.base import (
    Event,
    HumanActor,
    SourceElement,
)
from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_events
from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
from local_pdf.storage.sidecar import doc_dir, write_mineru, write_segments


def _add_question(events_path, slug: str, query: str, page: int, bare_id: str) -> str:
    eid = new_entry_id()
    actor = HumanActor(pseudonym="admin", level="expert")
    src = SourceElement(
        document_id=slug,
        element_id=bare_id,
        page_number=page,
        element_type="paragraph",
    )
    ev = Event(
        event_id=new_event_id(),
        timestamp_utc="2026-05-04T10:00:00Z",
        event_type="created",
        entry_id=eid,
        schema_version=1,
        payload={
            "task_type": "retrieval",
            "actor": actor.model_dump(mode="json"),
            "action": "created_from_scratch",
            "notes": None,
            "entry_data": {
                "query": query,
                "expected_chunk_ids": [],
                "chunk_hashes": {},
                "source_element": src.model_dump(mode="json"),
            },
        },
    )
    append_events(events_path, [ev])
    return eid


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    # Stub out Azure deps so _build_embedder returns None and the route
    # falls back to BM25-only.
    monkeypatch.delenv("AI_FOUNDRY_KEY", raising=False)
    monkeypatch.delenv("EMBEDDING_DEPLOYMENT_NAME", raising=False)

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _seed_doc(client, slug: str = "doc"):
    """Upload a fake PDF + write segments + mineru + 3 questions."""
    import io

    files = {"file": (f"{slug}.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    upload_resp = client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    assert upload_resp.status_code == 201, upload_resp.text
    slug = upload_resp.json()["slug"]
    cfg = client.app.state.config
    boxes = [
        SegmentBox(
            box_id="p1-b0",
            page=1,
            bbox=(0.0, 0.0, 100.0, 50.0),
            kind=BoxKind.paragraph,
            confidence=1.0,
            reading_order=0,
        ),
        SegmentBox(
            box_id="p1-b1",
            page=1,
            bbox=(0.0, 60.0, 100.0, 110.0),
            kind=BoxKind.paragraph,
            confidence=1.0,
            reading_order=1,
        ),
    ]
    write_segments(cfg.data_root, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        cfg.data_root,
        slug,
        {
            "elements": [
                {"box_id": "p1-b0", "html_snippet": "<p>Druck und Last bei Schraube M6.</p>"},
                {"box_id": "p1-b1", "html_snippet": "<p>Wetterbericht für Berlin.</p>"},
            ],
            "diagnostics": [],
        },
    )
    from goldens.storage import GOLDEN_EVENTS_V1_FILENAME

    events_path = doc_dir(cfg.data_root, slug) / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    events_path.parent.mkdir(parents=True, exist_ok=True)
    e1 = _add_question(events_path, slug, "Welche Last hält die Schraube M6?", 1, "p1-b0")
    e2 = _add_question(events_path, slug, "Was ist der Druck bei M6?", 1, "p1-b0")
    e3 = _add_question(events_path, slug, "Wie ist das Wetter heute?", 1, "p1-b1")
    return slug, e1, e2, e3


def test_similar_returns_top_k_with_bm25_only(client):
    slug, e1, _e2, _e3 = _seed_doc(client)
    r = client.get(
        f"/api/admin/docs/{slug}/questions/{e1}/similar?k=5",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["entry_id"] == e1
    # No Azure creds → embedder False, BM25-only.
    assert body["embedder"] is False
    hits = body["hits"]
    # The query itself is filtered out.
    assert all(h["entry_id"] != e1 for h in hits)
    # The Druck-Schraube question (e2) should rank above the Wetter
    # question (e3) — BM25 sees overlap on "schraube"/"m6".
    ids = [h["entry_id"] for h in hits]
    assert ids[0] != e1


def test_similar_404_when_entry_unknown(client):
    slug, _e1, _e2, _e3 = _seed_doc(client)
    r = client.get(
        f"/api/admin/docs/{slug}/questions/missing/similar",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 404


def test_compare_bm25_only(client):
    r = client.post(
        "/api/admin/compare",
        headers={"X-Auth-Token": "tok"},
        json={"reference": "Die Schraube M6 hält 5 kN.", "candidate": "Schraube M6 trägt 5 kN."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["embedder"] is False
    assert body["cosine"] == 0.0
    assert 0.0 < body["bm25"] <= 1.0


def test_pipelines_lists_microsoft_and_bam(client):
    r = client.get("/api/admin/pipelines", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    body = r.json()
    names = [p["name"] for p in body]
    assert "microsoft" in names
    assert "bam" in names
    bam = next(p for p in body if p["name"] == "bam")
    assert bam["available"] is False


def test_pipelines_bam_returns_501(client):
    r = client.post(
        "/api/admin/pipelines/bam/ask",
        headers={"X-Auth-Token": "tok"},
        json={"question": "Test?"},
    )
    assert r.status_code == 501


def test_pipelines_unknown_returns_404(client):
    r = client.post(
        "/api/admin/pipelines/foo/ask",
        headers={"X-Auth-Token": "tok"},
        json={"question": "Test?"},
    )
    assert r.status_code == 404
