from __future__ import annotations

import json
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
def client_with_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
    return client


def test_synthesise_dry_run_streams_ndjson(client_with_doc) -> None:
    with client_with_doc.stream(
        "POST",
        "/api/docs/doc-a/synthesise",
        json={"llm_model": "gpt-4o-mini", "dry_run": True},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/x-ndjson")
        lines: list[dict] = []
        for line in resp.iter_lines():
            line = line.strip()
            if not line:
                continue
            lines.append(json.loads(line))

    assert len(lines) >= 3
    assert lines[0]["type"] == "start"
    assert lines[0]["total_elements"] >= 1
    assert lines[-1]["type"] == "complete"
    elements = [ln for ln in lines if ln["type"] == "element"]
    assert all(ln["kept"] == 0 for ln in elements)  # dry-run keeps nothing


def test_synthesise_unknown_slug_404(client_with_doc) -> None:
    resp = client_with_doc.post(
        "/api/docs/nope/synthesise",
        json={"llm_model": "gpt-4o-mini", "dry_run": True},
    )
    assert resp.status_code == 404
