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
