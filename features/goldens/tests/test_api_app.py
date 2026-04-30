from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest


def _seed_identity(xdg: Path, pseudonym: str = "alice") -> None:
    cfg = xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        f'schema_version = 1\npseudonym = "{pseudonym}"\nlevel = "phd"\n'
        f'created_at_utc = "2026-04-30T08:00:00Z"\n',
        encoding="utf-8",
    )


@pytest.fixture
def make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _make() -> tuple:
        xdg = tmp_path / "xdg"
        xdg.mkdir()
        _seed_identity(xdg)
        outputs = tmp_path / "outputs"
        outputs.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
        monkeypatch.setenv("GOLDENS_DATA_ROOT", str(outputs))
        from goldens.api.app import create_app

        return create_app(), outputs

    return _make


def test_health_endpoint_returns_ok_without_auth(make_app) -> None:
    from fastapi.testclient import TestClient

    app, outputs = make_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["goldens_root"] == str(outputs)


def test_health_response_matches_schema(make_app) -> None:
    from fastapi.testclient import TestClient
    from goldens.api.schemas import HealthResponse

    app, _ = make_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    HealthResponse.model_validate(resp.json())


def test_unknown_path_returns_404(make_app) -> None:
    from fastapi.testclient import TestClient

    app, _ = make_app()
    client = TestClient(app)
    resp = client.get("/api/nonexistent", headers={"X-Auth-Token": "tok-test"})
    assert resp.status_code == 404


@pytest.mark.skip("router implemented in Task 15")
def test_entry_not_found_error_maps_to_404(make_app) -> None:
    """Verify the exception handler chain for goldens domain errors."""
    from fastapi.testclient import TestClient

    app, _ = make_app()
    client = TestClient(app)
    # Refining a missing entry — domain raises EntryNotFoundError.
    resp = client.post(
        "/api/entries/e_missing/refine",
        headers={"X-Auth-Token": "tok-test"},
        json={"query": "neue frage"},
    )
    assert resp.status_code == 404
    assert "e_missing" in resp.json()["detail"]


def test_missing_identity_raises_at_create_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    # NO identity.toml seeded.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
    from goldens.api.app import create_app
    from goldens.api.identity import IdentityNotConfiguredError

    with pytest.raises(IdentityNotConfiguredError):
        create_app()
