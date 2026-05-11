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


# ── Phase: model picker / select-model ──────────────────────────────────────


def test_models_route_returns_curated_list(client) -> None:
    r = client.get("/api/admin/llm/models", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    body = r.json()
    names = [m["name"] for m in body["models"]]
    # Sanity: the curated allowlist contains the project's defaults.
    # Only models that fit in 24 GB without further quantization make
    # the list — bf16 14B / Phi-4 / Gemma-bf16 / Mistral-bf16 are
    # excluded by design (they'd OOM on the target hardware).
    assert "Qwen/Qwen2.5-3B-Instruct" in names
    assert "Qwen/Qwen2.5-7B-Instruct" in names
    assert "Qwen/Qwen3.5-9B" in names
    assert "RedHatAI/gemma-3-27b-it-FP8-dynamic" in names
    # Every listed model must self-report as fitting on 24 GB.
    assert all(m["fits_24gb_bf16"] for m in body["models"])
    # ``current`` reflects the fake config.toml the test fixture set up.
    assert body["current"] == "test/fake-model"


def test_select_model_writes_config_toml_for_allowlisted(client) -> None:
    r = client.post(
        "/api/admin/llm/select-model",
        headers={"X-Auth-Token": "tok"},
        json={"model_name": "Qwen/Qwen2.5-7B-Instruct"},
    )
    assert r.status_code == 200, r.text
    # The status route now reflects the new model.
    status_r = client.get("/api/admin/llm/status", headers={"X-Auth-Token": "tok"})
    assert status_r.json()["model"] == "Qwen/Qwen2.5-7B-Instruct"


def test_select_model_rejects_unknown_name(client) -> None:
    r = client.post(
        "/api/admin/llm/select-model",
        headers={"X-Auth-Token": "tok"},
        json={"model_name": "evil/SomeRandom-99B"},
    )
    assert r.status_code == 400
    assert "nicht in der curated Liste" in r.json()["detail"]


def test_select_model_does_not_auto_restart(client) -> None:
    """Switching the model while running must not silently restart —
    it just rewrites config.toml. The user must explicitly stop+start."""
    client.post("/api/admin/llm/start", headers={"X-Auth-Token": "tok"})
    r = client.post(
        "/api/admin/llm/select-model",
        headers={"X-Auth-Token": "tok"},
        json={"model_name": "Qwen/Qwen2.5-3B-Instruct"},
    )
    assert r.status_code == 200
    # State is whatever it was before the switch (still starting/running).
    assert r.json()["state"] in {"starting", "running"}


def test_select_model_routes_require_auth(client) -> None:
    assert client.get("/api/admin/llm/models").status_code == 401
    assert client.post("/api/admin/llm/select-model").status_code == 401


# ── Phase: quantization-line plumbing ───────────────────────────────────


def test_select_quantized_model_writes_quantization_line(tmp_path: Path) -> None:
    """When the picker model has a non-None ``quantization``, the new
    config.toml must have a ``quantization = "..."`` line under
    [model]. Tested with a synthetic model name — the registry's
    current entries don't need explicit quantization on a 24-GB box."""
    cfg = _fake_config(tmp_path)
    p = VllmProcess(config_path=cfg, start_script=_fake_script(tmp_path))
    p.set_model_name("test/synthetic-int4", quantization="awq")
    text = cfg.read_text()
    assert 'quantization = "awq"' in text
    assert 'name = "test/synthetic-int4"' in text
    p.stop(grace_seconds=1.0)


def test_select_unquantized_model_strips_stale_quantization_line(tmp_path: Path) -> None:
    """Switching from a quantized model to a plain bf16 one must remove
    the stale ``quantization = ...`` line — otherwise vLLM would try
    to apply the wrong quantizer to a non-quantized checkpoint."""
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[server]\nhost = "127.0.0.1"\nport = 19999\n'
        '[model]\nname = "test/some-int4"\n'
        'quantization = "awq"\n'
    )
    p = VllmProcess(config_path=cfg, start_script=_fake_script(tmp_path))
    p.set_model_name("Qwen/Qwen2.5-7B-Instruct", quantization=None)
    text = cfg.read_text()
    assert "quantization" not in text
    assert 'name = "Qwen/Qwen2.5-7B-Instruct"' in text
    p.stop(grace_seconds=1.0)
