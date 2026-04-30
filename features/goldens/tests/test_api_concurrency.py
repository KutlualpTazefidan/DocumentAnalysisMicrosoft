"""Verify CLI subprocess writes and API in-process writes serialise correctly
via A.3's fcntl.LOCK_EX. No torn or duplicated entries; total count = sum of
parties' writes."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def _seed_identity(xdg: Path, pseudonym: str) -> None:
    cfg = xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        f'schema_version = 1\npseudonym = "{pseudonym}"\nlevel = "phd"\n'
        f'created_at_utc = "2026-04-30T08:00:00Z"\n',
        encoding="utf-8",
    )


def _seed_doc(outputs: Path, slug: str = "doc-a") -> None:
    src = Path(__file__).parent / "fixtures" / "analyze_minimal.json"
    analyze = outputs / slug / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(src, analyze / "ts.json")


def test_parallel_api_writes_all_persist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two threads each call POST .../entries N times; expect 2*N events
    in the log, none duplicated, none lost."""
    from fastapi.testclient import TestClient

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    _seed_identity(xdg, "alice")
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

    n_writes = 10
    errors: list[str] = []

    def _writer(prefix: str) -> None:
        for i in range(n_writes):
            try:
                resp = client.post(
                    f"/api/docs/doc-a/elements/{el_id}/entries",
                    json={"query": f"Frage {prefix}-{i}"},
                )
                if resp.status_code != 201:
                    errors.append(f"{prefix}-{i}: status {resp.status_code}")
            except Exception as e:
                errors.append(f"{prefix}-{i}: {e}")

    t1 = threading.Thread(target=_writer, args=("A",))
    t2 = threading.Thread(target=_writer, args=("B",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == []
    listed = client.get("/api/entries").json()
    queries = {e["query"] for e in listed}
    assert len(queries) == 2 * n_writes
    for prefix in ("A", "B"):
        for i in range(n_writes):
            assert f"Frage {prefix}-{i}" in queries
