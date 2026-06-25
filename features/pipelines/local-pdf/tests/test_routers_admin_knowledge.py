from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOLDENS_API_TOKEN", "ADMIN")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(tmp_path / "raw"))
    kb = tmp_path / "kb"
    monkeypatch.setenv("KNOWLEDGE_ROOT", str(kb))
    base = kb / "bauartpruefung-lm" / "behoerden"
    base.mkdir(parents=True)
    (kb / "bauartpruefung-lm" / "index.md").write_text(
        "---\ntype: Index\ntitle: Bauartprüfung\n---\n[BAM](/behoerden/bam.md)\n",
        encoding="utf-8",
    )
    (base / "bam.md").write_text(
        "---\ntype: Behörde\ntitle: BAM\ntags: [behoerde]\n---\nSiehe [Index](/index.md).\n",
        encoding="utf-8",
    )
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def test_bases_requires_admin_token(client) -> None:
    assert client.get("/api/admin/knowledge/bases").status_code == 401


def test_list_bases(client) -> None:
    r = client.get("/api/admin/knowledge/bases", headers={"X-Auth-Token": "ADMIN"})
    assert r.status_code == 200
    body = r.json()
    assert body[0]["name"] == "bauartpruefung-lm"
    assert body[0]["title"] == "Bauartprüfung"
    assert body[0]["concept_count"] == 2


def test_list_concepts(client) -> None:
    r = client.get(
        "/api/admin/knowledge/bases/bauartpruefung-lm/concepts",
        headers={"X-Auth-Token": "ADMIN"},
    )
    paths = {c["path"]: c for c in r.json()}
    assert paths["behoerden/bam.md"]["type"] == "Behörde"


def test_get_concept_with_links(client) -> None:
    r = client.get(
        "/api/admin/knowledge/bases/bauartpruefung-lm/concept",
        params={"path": "behoerden/bam.md"},
        headers={"X-Auth-Token": "ADMIN"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "Behörde"
    assert body["links"][0]["path"] == "index.md"
    assert body["links"][0]["resolved"] is True


def test_get_concept_missing_is_404(client) -> None:
    r = client.get(
        "/api/admin/knowledge/bases/bauartpruefung-lm/concept",
        params={"path": "behoerden/nope.md"},
        headers={"X-Auth-Token": "ADMIN"},
    )
    assert r.status_code == 404


def test_get_concept_traversal_is_400(client) -> None:
    r = client.get(
        "/api/admin/knowledge/bases/bauartpruefung-lm/concept",
        params={"path": "../../secret"},
        headers={"X-Auth-Token": "ADMIN"},
    )
    assert r.status_code == 400
