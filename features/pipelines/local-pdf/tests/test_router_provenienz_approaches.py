"""HTTP CRUD for the approach library."""

from __future__ import annotations

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


def _create(client, name="A", step_kinds=("extract_claims",), text="hi"):
    return client.post(
        "/api/admin/provenienz/approaches",
        headers={"X-Auth-Token": "tok"},
        json={
            "name": name,
            "step_kinds": list(step_kinds),
            "extra_system": text,
        },
    )


def test_post_creates_approach(client):
    r = _create(client, name="thorough", text="Sei gründlich.")
    assert r.status_code == 201, r.text
    a = r.json()["approach"]
    assert a["name"] == "thorough"
    assert a["version"] == 1
    assert a["enabled"] is True


def test_post_same_name_bumps_version(client):
    _create(client, name="thorough", text="v1")
    r = _create(client, name="thorough", text="v2")
    a = r.json()["approach"]
    assert a["version"] == 2
    assert a["extra_system"] == "v2"


def test_get_lists_and_filters(client):
    _create(client, name="x", step_kinds=["extract_claims"])
    _create(client, name="y", step_kinds=["evaluate"])
    r = client.get(
        "/api/admin/provenienz/approaches",
        headers={"X-Auth-Token": "tok"},
        params={"step_kind": "extract_claims"},
    )
    assert r.status_code == 200
    names = [a["name"] for a in r.json()["approaches"]]
    assert names == ["x"]


def test_patch_disables_approach(client):
    a = _create(client).json()["approach"]
    r = client.patch(
        f"/api/admin/provenienz/approaches/{a['approach_id']}",
        headers={"X-Auth-Token": "tok"},
        json={"enabled": False},
    )
    assert r.status_code == 200
    assert r.json()["approach"]["enabled"] is False
    # Default GET no longer lists it.
    listed = client.get(
        "/api/admin/provenienz/approaches",
        headers={"X-Auth-Token": "tok"},
    ).json()["approaches"]
    assert listed == []


def test_patch_updates_extra_system(client):
    a = _create(client, text="old text").json()["approach"]
    r = client.patch(
        f"/api/admin/provenienz/approaches/{a['approach_id']}",
        headers={"X-Auth-Token": "tok"},
        json={"extra_system": "neue Anweisung"},
    )
    assert r.status_code == 200
    assert r.json()["approach"]["extra_system"] == "neue Anweisung"
    assert r.json()["approach"]["version"] == 2


def test_delete_removes_approach(client):
    a = _create(client).json()["approach"]
    r = client.delete(
        f"/api/admin/provenienz/approaches/{a['approach_id']}",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    listed = client.get(
        "/api/admin/provenienz/approaches",
        headers={"X-Auth-Token": "tok"},
    ).json()["approaches"]
    assert listed == []
