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
