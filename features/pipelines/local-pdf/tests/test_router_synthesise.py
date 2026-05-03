"""Tests for POST /api/admin/docs/{slug}/synthesise/test."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


class FakeLLMClient:
    """Fake LLMClient that returns a canned response without hitting any service."""

    def complete(self, messages, model, **kwargs):
        from llm_clients.base import Completion

        return Completion(text="fake response", model=model, usage=None)

    def embed(self, texts, model):
        raise NotImplementedError


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    import local_pdf.api.routers.admin.synthesise as synth_mod

    synth_mod._LLM_CLIENT = FakeLLMClient()
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    app = TestClient(create_app())
    yield app
    synth_mod._LLM_CLIENT = None


def _upload_doc(client) -> None:
    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    r = client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    assert r.status_code == 201


def test_synthesise_test_calls_llm_and_returns_response(client) -> None:
    _upload_doc(client)
    r = client.post(
        "/api/admin/docs/spec/synthesise/test",
        headers={"X-Auth-Token": "tok"},
        json={"prompt": "Summarize the document."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["response"] == "fake response"
    assert "elapsed_seconds" in body
    assert isinstance(body["elapsed_seconds"], float)


def test_synthesise_test_returns_model_name(client) -> None:
    _upload_doc(client)
    r = client.post(
        "/api/admin/docs/spec/synthesise/test",
        headers={"X-Auth-Token": "tok"},
        json={"prompt": "Hello"},
    )
    assert r.status_code == 200
    body = r.json()
    # model name comes from get_default_model() which defaults to qwen2.5:7b-instruct
    # but FakeLLMClient echoes back whatever model string is passed
    assert "model" in body
    assert body["model"] == "qwen2.5:7b-instruct"


def test_synthesise_test_404_for_missing_doc(client) -> None:
    r = client.post(
        "/api/admin/docs/nonexistent/synthesise/test",
        headers={"X-Auth-Token": "tok"},
        json={"prompt": "anything"},
    )
    assert r.status_code == 404


def test_synthesise_test_requires_auth(client) -> None:
    _upload_doc(client)
    r = client.post(
        "/api/admin/docs/spec/synthesise/test",
        json={"prompt": "Hello"},
    )
    assert r.status_code == 401


# ── Real generation flow (per-box / list / refine / deprecate) ───────────────


class FakeJSONLLMClient:
    """Returns canned JSON-shaped completions matching A.5's prompt
    template expectations. The synthetic generator parses the output as
    JSON and extracts ``questions`` keyed by ``sub_unit_id``."""

    def __init__(self, questions: list[str] | None = None) -> None:
        self._questions = questions or ["What is the value?", "Which standard applies?"]

    def complete(self, messages, model, **kwargs):
        import json as _json

        from llm_clients.base import Completion

        # Generator expects {"questions": [{"sub_unit": "<text>", "question": "..."}]}.
        # Use a placeholder sub_unit string; the generator only checks the
        # field is present and that "question" is non-empty.
        payload = _json.dumps(
            {
                "questions": [
                    {"sub_unit": f"sub-{i + 1}", "question": q}
                    for i, q in enumerate(self._questions)
                ]
            }
        )
        return Completion(text=payload, model=model, usage=None)

    def embed(self, texts, model):
        # Disabled — embed_client is None in tests so dedup degrades gracefully.
        raise NotImplementedError


@pytest.fixture
def gen_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Fixture with a doc + populated mineru.json and a FakeJSONLLMClient
    so synthesise endpoints can run without a real LLM."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.setenv("LLM_MODEL", "test-model")  # any non-empty model id

    import local_pdf.api.routers.admin.synthesise as synth_mod

    synth_mod._LLM_CLIENT = FakeJSONLLMClient()
    synth_mod._EMBED_CLIENT = None

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    app = TestClient(create_app())
    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    r = app.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    assert r.status_code == 201

    # Seed one paragraph element so the loader has something to yield.
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_mineru, write_segments

    boxes = [
        SegmentBox(
            box_id="p1-b0",
            page=1,
            bbox=(0.0, 0.0, 400.0, 100.0),
            kind=BoxKind.paragraph,
            confidence=1.0,
            reading_order=0,
        ),
    ]
    write_segments(root, "spec", SegmentsFile(slug="spec", boxes=boxes, raster_dpi=288))
    write_mineru(
        root,
        "spec",
        {
            "elements": [
                {
                    "box_id": "p1-b0",
                    "html_snippet": (
                        "<p>Die maximale Zugkraft betraegt 8.5 kN gemaess DIN 912.</p>"
                    ),
                    "html_snippet_raw": (
                        "<p>Die maximale Zugkraft betraegt 8.5 kN gemaess DIN 912.</p>"
                    ),
                },
            ],
            "diagnostics": [],
        },
    )

    yield app
    synth_mod._LLM_CLIENT = None
    synth_mod._EMBED_CLIENT = None


def test_synthesise_per_box_creates_questions(gen_client) -> None:
    r = gen_client.post(
        "/api/admin/docs/spec/synthesise?box_id=p1-b0",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["box_id"] == "p1-b0"
    assert body["accepted"] >= 1
    assert all(q["box_id"] == "p1-b0" for q in body["questions"])


def test_synthesise_per_box_404_for_unknown_box(gen_client) -> None:
    r = gen_client.post(
        "/api/admin/docs/spec/synthesise?box_id=p99-bxx",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 404


def test_list_questions_groups_by_box(gen_client) -> None:
    # Generate first.
    gen_client.post(
        "/api/admin/docs/spec/synthesise?box_id=p1-b0",
        headers={"X-Auth-Token": "tok"},
    )
    r = gen_client.get(
        "/api/admin/docs/spec/questions",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "p1-b0" in body
    assert isinstance(body["p1-b0"], list)
    assert len(body["p1-b0"]) >= 1


def test_refine_question_replaces_text(gen_client) -> None:
    gen = gen_client.post(
        "/api/admin/docs/spec/synthesise?box_id=p1-b0",
        headers={"X-Auth-Token": "tok"},
    ).json()
    qid = gen["questions"][0]["entry_id"]

    r = gen_client.patch(
        f"/api/admin/docs/spec/questions/{qid}",
        headers={"X-Auth-Token": "tok"},
        json={"text": "Edited question text?"},
    )
    assert r.status_code == 200, r.text
    assert "new_entry_id" in r.json()

    # Old id is now deprecated; new id appears in active list with new text.
    listing = gen_client.get(
        "/api/admin/docs/spec/questions",
        headers={"X-Auth-Token": "tok"},
    ).json()
    texts = [q["text"] for q in listing.get("p1-b0", [])]
    assert "Edited question text?" in texts


def test_deprecate_question_removes_from_active_list(gen_client) -> None:
    gen = gen_client.post(
        "/api/admin/docs/spec/synthesise?box_id=p1-b0",
        headers={"X-Auth-Token": "tok"},
    ).json()
    qid = gen["questions"][0]["entry_id"]

    r = gen_client.delete(
        f"/api/admin/docs/spec/questions/{qid}",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200

    listing = gen_client.get(
        "/api/admin/docs/spec/questions/p1-b0",
        headers={"X-Auth-Token": "tok"},
    ).json()
    ids = [q["entry_id"] for q in listing]
    assert qid not in ids


def test_synthesise_full_doc_streams_ndjson(gen_client) -> None:
    """No box_id / page → full-doc NDJSON stream with a 'done' terminator."""
    r = gen_client.post(
        "/api/admin/docs/spec/synthesise",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    lines = [line for line in r.text.splitlines() if line.strip()]
    events = [__import__("json").loads(line) for line in lines]
    types = [e["event"] for e in events]
    assert "completed" in types
    assert types[-1] == "done"
