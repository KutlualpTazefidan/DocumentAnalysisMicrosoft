from __future__ import annotations

import subprocess
import sys


def test_segment_serve_help_shows_options() -> None:
    """`query-eval segment serve --help` prints --port / --host."""
    proc = subprocess.run(
        [sys.executable, "-m", "query_index_eval.cli", "segment", "serve", "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--port" in proc.stdout
    assert "--host" in proc.stdout


def test_segment_serve_loads_app_factory(monkeypatch) -> None:
    """The handler imports local_pdf.api.create_app and would call uvicorn.run."""
    captured: dict = {}

    def fake_run(app, host, port, log_level):
        captured["host"] = host
        captured["port"] = port
        captured["app"] = app

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")

    from query_index_eval.cli import cmd_segment_serve

    cmd_segment_serve(host="127.0.0.1", port=8001, log_level="info")
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8001
    assert captured["app"] is not None
