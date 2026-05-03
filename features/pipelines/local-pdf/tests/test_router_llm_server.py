"""Tests for the VllmProcess subprocess manager + /api/admin/llm/* routes.

We don't actually spawn vllm — that would need a GPU and a model
download. Instead we substitute a fake start.sh that prints + sleeps,
which is enough to exercise the start/stop/status state machine.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from local_pdf.llm_server.process import VllmProcess, set_instance

if TYPE_CHECKING:
    from pathlib import Path


def _fake_script(tmp_path: Path, *, sleep_seconds: float = 30.0) -> Path:
    """Create a tiny shell script that emits a marker line then sleeps.

    The reader thread will see "starting…" appear in log_tail, and
    poll(None) keeps the subprocess alive until we stop() it.
    """
    script = tmp_path / "fake_start.sh"
    script.write_text(f"#!/usr/bin/env bash\necho 'fake-vllm starting…'\nsleep {sleep_seconds}\n")
    script.chmod(0o755)
    return script


def _fake_config(tmp_path: Path, host: str = "127.0.0.1", port: int = 19999) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'[server]\nhost = "{host}"\nport = {port}\n[model]\nname = "test/fake-model"\n')
    return cfg


@pytest.fixture
def proc(tmp_path: Path):
    script = _fake_script(tmp_path)
    cfg = _fake_config(tmp_path)
    p = VllmProcess(config_path=cfg, start_script=script)
    yield p
    # Clean up if a test left the subprocess running.
    p.stop(grace_seconds=1.0)


def test_initial_state_is_stopped(proc: VllmProcess) -> None:
    s = proc.status()
    assert s.state == "stopped"
    assert s.pid is None
    assert s.healthy is False
    assert s.model == "test/fake-model"
    assert s.base_url == "http://127.0.0.1:19999/v1"


def test_start_transitions_to_starting(proc: VllmProcess) -> None:
    s = proc.start()
    # The fake script doesn't open a port, so health probe fails →
    # state stays "starting" while the process is alive.
    assert s.state in {"starting", "running"}
    assert s.pid is not None
    assert isinstance(s.pid, int) and s.pid > 0


def test_start_is_idempotent(proc: VllmProcess) -> None:
    s1 = proc.start()
    s2 = proc.start()
    # Same pid both times — second start() didn't spawn a new process.
    assert s1.pid == s2.pid


def test_stop_transitions_to_stopped(proc: VllmProcess) -> None:
    proc.start()
    s = proc.stop(grace_seconds=2.0)
    assert s.state == "stopped"
    assert s.pid is None


def test_stop_is_idempotent_when_already_stopped(proc: VllmProcess) -> None:
    s = proc.stop()
    assert s.state == "stopped"


def test_log_tail_captures_subprocess_stdout(proc: VllmProcess) -> None:
    proc.start()
    # Reader thread is async — give it a moment to drain the marker line.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if any("fake-vllm" in line for line in proc.status().log_tail):
            break
        time.sleep(0.05)
    assert any("fake-vllm" in line for line in proc.status().log_tail)


def test_missing_start_script_yields_error_state(tmp_path: Path) -> None:
    cfg = _fake_config(tmp_path)
    proc = VllmProcess(config_path=cfg, start_script=tmp_path / "does_not_exist.sh")
    s = proc.start()
    assert s.state == "error"
    assert s.error is not None
    assert "start.sh not found" in s.error


# ── HTTP endpoint tests ──────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))

    # Substitute a VllmProcess pointed at a fake script for the duration
    # of the test so /llm/start doesn't try to spawn the real vllm.
    script = _fake_script(tmp_path)
    cfg = _fake_config(tmp_path)
    fake = VllmProcess(config_path=cfg, start_script=script)
    set_instance(fake)

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    yield TestClient(create_app())

    fake.stop(grace_seconds=1.0)
    set_instance(None)


def test_status_route_returns_stopped_initially(client) -> None:
    r = client.get("/api/admin/llm/status", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "stopped"
    assert body["healthy"] is False


def test_start_route_returns_starting(client) -> None:
    r = client.post("/api/admin/llm/start", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    body = r.json()
    assert body["state"] in {"starting", "running"}
    assert body["pid"] is not None


def test_stop_route_terminates_and_returns_stopped(client) -> None:
    client.post("/api/admin/llm/start", headers={"X-Auth-Token": "tok"})
    r = client.post("/api/admin/llm/stop", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    assert r.json()["state"] == "stopped"


def test_routes_require_auth(client) -> None:
    assert client.get("/api/admin/llm/status").status_code == 401
    assert client.post("/api/admin/llm/start").status_code == 401
    assert client.post("/api/admin/llm/stop").status_code == 401
