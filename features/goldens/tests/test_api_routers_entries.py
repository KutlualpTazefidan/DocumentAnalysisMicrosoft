from __future__ import annotations

import shutil
from pathlib import Path

import pytest


def _seed_identity(xdg: Path) -> None:
    cfg = xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        'schema_version = 1\npseudonym = "alice"\nlevel = "phd"\n'
        'created_at_utc = "2026-04-30T08:00:00Z"\n',
        encoding="utf-8",
    )


def _seed_doc(outputs: Path, slug: str = "doc-a") -> None:
    src = Path(__file__).parent / "fixtures" / "analyze_minimal.json"
    analyze = outputs / slug / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(src, analyze / "ts.json")


@pytest.fixture
def client_with_one_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    _seed_identity(xdg)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
    monkeypatch.setenv("GOLDENS_DATA_ROOT", str(outputs))
    _seed_doc(outputs)

    from goldens.api.app import create_app

    client = TestClient(create_app())
    client.headers.update({"X-Auth-Token": "tok-test"})

    elements = client.get("/api/docs/doc-a/elements").json()
    el_id = elements[0]["element"]["element_id"]
    create_resp = client.post(
        f"/api/docs/doc-a/elements/{el_id}/entries",
        json={"query": "Test-Frage 1"},
    )
    entry_id = create_resp.json()["entry_id"]
    return client, entry_id


def test_list_entries_returns_active(client_with_one_entry) -> None:
    client, entry_id = client_with_one_entry
    resp = client.get("/api/entries")
    assert resp.status_code == 200
    body = resp.json()
    assert any(e["entry_id"] == entry_id for e in body)


def test_list_entries_filter_by_slug(client_with_one_entry) -> None:
    client, _ = client_with_one_entry
    resp = client.get("/api/entries?slug=doc-a")
    assert resp.status_code == 200
    body = resp.json()
    assert all(
        e["source_element"] is None or e["source_element"]["document_id"] == "doc-a" for e in body
    )


def test_get_entry_returns_full_object(client_with_one_entry) -> None:
    client, entry_id = client_with_one_entry
    resp = client.get(f"/api/entries/{entry_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entry_id"] == entry_id
    assert body["query"] == "Test-Frage 1"
    assert body["deprecated"] is False


def test_get_entry_unknown_404(client_with_one_entry) -> None:
    client, _ = client_with_one_entry
    resp = client.get("/api/entries/e_does_not_exist")
    assert resp.status_code == 404


def test_refine_creates_new_entry_and_deprecates_old(client_with_one_entry) -> None:
    client, old_entry_id = client_with_one_entry
    resp = client.post(
        f"/api/entries/{old_entry_id}/refine",
        json={"query": "Verbesserte Frage"},
    )
    assert resp.status_code == 200
    new_id = resp.json()["new_entry_id"]
    assert new_id != old_entry_id

    # Old is now deprecated; new is active.
    new_get = client.get(f"/api/entries/{new_id}")
    assert new_get.status_code == 200
    assert new_get.json()["query"] == "Verbesserte Frage"

    # Old is no longer in active list.
    active_ids = {e["entry_id"] for e in client.get("/api/entries").json()}
    assert old_entry_id not in active_ids


def test_refine_unknown_entry_404(client_with_one_entry) -> None:
    client, _ = client_with_one_entry
    resp = client.post("/api/entries/e_missing/refine", json={"query": "x"})
    assert resp.status_code == 404


@pytest.mark.skip("deprecate endpoint added in Task 16")
def test_refine_already_deprecated_entry_409(client_with_one_entry) -> None:
    client, entry_id = client_with_one_entry
    # Deprecate first.
    client.post(f"/api/entries/{entry_id}/deprecate", json={"reason": "test"})
    # Then try to refine.
    resp = client.post(f"/api/entries/{entry_id}/refine", json={"query": "x"})
    assert resp.status_code == 409
