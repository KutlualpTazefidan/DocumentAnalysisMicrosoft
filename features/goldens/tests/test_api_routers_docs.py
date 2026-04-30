from __future__ import annotations

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


def _seed_doc(outputs: Path, slug: str, fixture_name: str = "analyze_minimal.json") -> None:
    import shutil

    src = Path(__file__).parent / "fixtures" / fixture_name
    analyze = outputs / slug / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(src, analyze / "ts.json")


@pytest.fixture
def make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    _seed_identity(xdg)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
    monkeypatch.setenv("GOLDENS_DATA_ROOT", str(outputs))

    def _make() -> tuple[TestClient, Path]:
        from goldens.api.app import create_app

        client = TestClient(create_app())
        client.headers.update({"X-Auth-Token": "tok-test"})
        return client, outputs

    return _make


def test_list_docs_empty(make_client) -> None:
    client, _ = make_client()
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_docs_returns_doc_summary(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    _seed_doc(outputs, "doc-b")
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    body = resp.json()
    slugs = {d["slug"] for d in body}
    assert slugs == {"doc-a", "doc-b"}
    for d in body:
        assert d["element_count"] >= 1


def test_list_docs_skips_subdirs_without_analyze_json(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "real-doc")
    (outputs / "noisy-dir").mkdir()  # no analyze/
    resp = client.get("/api/docs")
    slugs = {d["slug"] for d in resp.json()}
    assert slugs == {"real-doc"}


def test_list_docs_requires_auth(make_client) -> None:
    client, _ = make_client()
    client.headers.pop("X-Auth-Token")
    resp = client.get("/api/docs")
    assert resp.status_code == 401


def test_list_elements_returns_element_with_counts(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    resp = client.get("/api/docs/doc-a/elements")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    item = body[0]
    assert "element" in item
    assert "count_active_entries" in item
    assert item["element"]["element_id"]
    assert item["element"]["page_number"] >= 1


def test_list_elements_unknown_slug_404(make_client) -> None:
    client, _ = make_client()
    resp = client.get("/api/docs/nonexistent/elements")
    assert resp.status_code == 404


def test_get_element_returns_element_and_entries(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    # First fetch the element list to learn an ID we can hit:
    elements = client.get("/api/docs/doc-a/elements").json()
    assert elements
    el_id = elements[0]["element"]["element_id"]
    resp = client.get(f"/api/docs/doc-a/elements/{el_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "element" in body and "entries" in body
    assert body["element"]["element_id"] == el_id
    assert isinstance(body["entries"], list)


def test_get_element_unknown_slug_404(make_client) -> None:
    client, _ = make_client()
    resp = client.get("/api/docs/nope/elements/p1-aaaaaaaa")
    assert resp.status_code == 404


def test_get_element_unknown_element_404(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    resp = client.get("/api/docs/doc-a/elements/p99-deadbeef")
    assert resp.status_code == 404
    assert "p99-deadbeef" in resp.json()["detail"]


def test_create_entry_writes_event(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    elements = client.get("/api/docs/doc-a/elements").json()
    el_id = elements[0]["element"]["element_id"]

    resp = client.post(
        f"/api/docs/doc-a/elements/{el_id}/entries",
        json={"query": "Was steht hier?"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["entry_id"]
    assert body["event_id"]

    # And the count goes up.
    after = client.get("/api/docs/doc-a/elements").json()
    matching = next(e for e in after if e["element"]["element_id"] == el_id)
    assert matching["count_active_entries"] >= 1


def test_create_entry_rejects_empty_query(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    elements = client.get("/api/docs/doc-a/elements").json()
    el_id = elements[0]["element"]["element_id"]

    resp = client.post(
        f"/api/docs/doc-a/elements/{el_id}/entries",
        json={"query": ""},
    )
    assert resp.status_code == 422
