"""Subprocess manager for the standalone vllm-server/ launcher.

The repo-root ``vllm-server/start.sh`` script reads ``config.toml`` and
exec's ``vllm serve …``. This module owns the lifecycle of one such
subprocess from the FastAPI backend's perspective:

- **start()** — spawn ``start.sh`` with stdout/stderr captured to a
  rolling buffer (last N lines tail-able by the UI).
- **stop()** — SIGTERM, then SIGKILL after a grace period.
- **status()** — best-effort: process state + readiness probe against
  ``http://host:port/v1/models``.
- Lifespan integration — ``terminate_on_app_shutdown`` is registered as
  a FastAPI shutdown hook so an app crash / restart never leaks vLLM.

Singleton: the module-level ``_INSTANCE`` is the one VllmProcess we
manage. Multiple concurrent clients share it. Two parallel start()
calls collapse — the second sees the running process and returns its
status without spawning again.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
import tomllib
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx

# ──────────────────────────────────────────────────────────────────────────────
# Paths

# The vllm-server/ folder lives at the repo root. We resolve it relative
# to this file:
#   features/pipelines/local-pdf/src/local_pdf/llm_server/process.py
#   parents: [0]=llm_server [1]=local_pdf [2]=src [3]=local-pdf
#            [4]=pipelines  [5]=features  [6]=<repo-root>
_REPO_ROOT = Path(__file__).resolve().parents[6]
VLLM_SERVER_DIR = _REPO_ROOT / "vllm-server"
START_SCRIPT = VLLM_SERVER_DIR / "start.sh"
CONFIG_PATH = VLLM_SERVER_DIR / "config.toml"

# Lines of stdout/stderr we keep in memory for the UI's "log tail"
# panel. Bounded so a chatty vLLM doesn't OOM the backend.
LOG_TAIL_LINES = 200


def configured_model_name() -> str:
    """Read ``[model].name`` from config.toml without instantiating
    a VllmProcess. Used by ``llm.get_default_model()`` so the model
    name follows whatever the picker last selected — single source of
    truth, eliminates VLLM_MODEL-env vs config.toml drift.

    Returns empty string if the file is missing or malformed.
    """
    if not CONFIG_PATH.exists():
        return ""
    try:
        cfg = tomllib.loads(CONFIG_PATH.read_text())
    except (tomllib.TOMLDecodeError, OSError):
        return ""
    name = cfg.get("model", {}).get("name", "")
    return str(name)


# ──────────────────────────────────────────────────────────────────────────────
# Status model

State = Literal["stopped", "starting", "running", "error"]


@dataclass
class VllmStatus:
    """Snapshot of the managed vLLM process.

    Frontend consumes this verbatim via /api/admin/llm/status.
    """

    state: State
    pid: int | None = None
    model: str | None = None
    base_url: str | None = None
    healthy: bool = False
    error: str | None = None
    log_tail: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Process manager


class VllmProcess:
    """Manages a single vllm-server subprocess.

    Thread-safe — start/stop/status callable from any FastAPI request
    thread. Internally serialised via ``self._lock`` to prevent the
    "two parallel start()s" race.
    """

    def __init__(
        self,
        *,
        config_path: Path = CONFIG_PATH,
        start_script: Path = START_SCRIPT,
    ) -> None:
        self._config_path = config_path
        self._start_script = start_script
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: deque[str] = deque(maxlen=LOG_TAIL_LINES)
        self._reader_thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._last_error: str | None = None
        self._state: State = "stopped"

    # ── Config helpers ──────────────────────────────────────────────────────

    def _read_config(self) -> dict:
        if not self._config_path.exists():
            raise FileNotFoundError(f"config.toml not found: {self._config_path}")
        return tomllib.loads(self._config_path.read_text())

    def _base_url(self) -> str:
        cfg = self._read_config().get("server", {})
        host = cfg.get("host", "127.0.0.1")
        port = cfg.get("port", 8000)
        return f"http://{host}:{port}/v1"

    def _model_name(self) -> str:
        cfg = self._read_config().get("model", {})
        name = cfg.get("name", "")
        return str(name)

    def set_model_name(self, name: str, *, quantization: str | None = None) -> None:
        """Rewrite ``[model].name`` (and optionally ``quantization``) in
        config.toml in-place.

        The next ``start()`` picks up the new values via
        ``_read_config()``. Does NOT auto-restart a running process —
        callers (UI / tests) decide whether to stop + start or apply
        on next boot.

        ``quantization`` semantics:
          - ``None``  → strip any existing ``quantization = ...`` line
            (the new model wants vLLM auto-detect).
          - non-None  → set/replace the line so vLLM uses that quantizer
            (e.g. ``"moe_wna16"`` for Qwen3.5-27B-GPTQ-Int4).

        Implementation: regex-replace inside the ``[model]`` section.
        Avoids adding a TOML-writer dep (tomllib is read-only) and
        preserves comments + formatting.
        """
        if not self._config_path.exists():
            raise FileNotFoundError(f"config.toml not found: {self._config_path}")
        text = self._config_path.read_text()
        import re

        # 1) Update the ``name`` line.
        name_pattern = re.compile(
            r'(\[model\][^\[]*?\bname\s*=\s*)"[^"]*"',
            re.MULTILINE | re.DOTALL,
        )
        text, name_count = name_pattern.subn(rf'\g<1>"{name}"', text, count=1)
        if name_count == 0:
            raise ValueError(
                f"could not find [model].name in {self._config_path}; config.toml may be malformed"
            )

        # 2) Manage the optional ``quantization`` line. Match an existing
        #    one (commented or not) inside the [model] block.
        quant_pattern = re.compile(
            r'^[ \t]*#?[ \t]*quantization\s*=\s*"[^"]*"[ \t]*\n',
            re.MULTILINE,
        )
        if quantization:
            replacement = f'quantization = "{quantization}"\n'
            new_text, hit = quant_pattern.subn(replacement, text, count=1)
            if hit == 0:
                # No existing line — append it right after the name line
                # in the [model] section.
                new_text = name_pattern.sub(
                    lambda m: m.group(0) + f'\nquantization = "{quantization}"',
                    text,
                    count=1,
                )
            text = new_text
        else:
            # Strip any existing quantization line so the new model
            # doesn't inherit a stale quantizer.
            text = quant_pattern.sub("", text)

        self._config_path.write_text(text)

    # ── Process control ────────────────────────────────────────────────────

    def start(self) -> VllmStatus:
        """Spawn the vLLM subprocess if not already running.

        Idempotent — if a healthy or starting process exists, returns its
        status without spawning a duplicate.
        """
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                # Already running (or starting).
                return self.status()

            if not self._start_script.exists():
                self._state = "error"
                self._last_error = f"start.sh not found at {self._start_script}"
                return self.status()

            # Reset rolling state.
            self._log.clear()
            self._last_error = None
            self._state = "starting"

            try:
                self._proc = subprocess.Popen(
                    [str(self._start_script)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=str(self._start_script.parent),
                    # Default bufsize (binary mode); the reader thread
                    # decodes UTF-8 line-by-line via readline().
                    # New process group so SIGTERM propagates to vllm
                    # (start.sh uses `exec`, but defensive).
                    preexec_fn=os.setsid if os.name == "posix" else None,
                )
            except Exception as exc:
                self._state = "error"
                self._last_error = f"failed to spawn: {exc}"
                self._proc = None
                return self.status()

            # Reader thread: drain stdout/stderr into the rolling log
            # buffer. Daemon so it doesn't block app shutdown.
            self._reader_thread = threading.Thread(
                target=self._drain_output,
                args=(self._proc,),
                daemon=True,
                name="vllm-log-reader",
            )
            self._reader_thread.start()

            return self.status()

    def stop(self, *, grace_seconds: float = 10.0) -> VllmStatus:
        """SIGTERM the subprocess and wait up to grace_seconds; SIGKILL on timeout.

        Idempotent — calling stop() on an already-stopped process is a no-op.

        Belt-and-suspenders SIGKILL: even after the parent bash exits we
        still SIGKILL the process group, because vLLM spawns
        ``VLLM::EngineCore`` as a multiprocessing worker that catches
        SIGTERM and takes its time to release the CUDA context. Without
        the final SIGKILL the worker can hold ~20 GB of VRAM long after
        the start.sh wrapper has died.
        """
        with self._lock:
            proc = self._proc
            if proc is None or proc.poll() is not None:
                self._state = "stopped"
                self._proc = None
                return self.status()

            # Capture the process-group id BEFORE the parent dies. Once
            # the leader exits, getpgid() can still resolve via the
            # group's children, but we cache to be safe.
            try:
                pgid = os.getpgid(proc.pid) if os.name == "posix" else None
            except (ProcessLookupError, PermissionError):
                pgid = None

            try:
                if pgid is not None:
                    os.killpg(pgid, signal.SIGTERM)
                else:
                    proc.terminate()
            except (ProcessLookupError, PermissionError):
                pass

            # Wait for the parent bash to exit (proxy for "vllm responded
            # to SIGTERM"). The grace period applies to the parent only —
            # the engine worker SIGKILL below is unconditional.
            deadline = time.monotonic() + grace_seconds
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)

            # Always SIGKILL the group — survivors (engine workers,
            # detached children) won't release VRAM otherwise.
            try:
                if pgid is not None:
                    os.killpg(pgid, signal.SIGKILL)
                else:
                    proc.kill()
            except (ProcessLookupError, PermissionError):
                pass

            # Reap the parent if it's still pending so we don't leave a
            # zombie behind.
            import contextlib

            with contextlib.suppress(Exception):
                proc.wait(timeout=1.0)

            self._proc = None
            self._state = "stopped"
            return self.status()

    def status(self) -> VllmStatus:
        """Return a snapshot. Health-probes the OpenAI endpoint."""
        with self._lock:
            proc = self._proc
            if proc is None:
                state: State = self._state if self._state == "error" else "stopped"
                return VllmStatus(
                    state=state,
                    pid=None,
                    model=self._model_name() or None,
                    base_url=self._base_url(),
                    healthy=False,
                    error=self._last_error,
                    log_tail=list(self._log),
                )
            if proc.poll() is not None:
                # Process died on its own — treat as error if it ran briefly,
                # otherwise as cleanly stopped.
                state = "error" if proc.returncode != 0 else "stopped"
                if state == "error" and not self._last_error:
                    self._last_error = f"vllm exited with code {proc.returncode}"
                self._state = state
                self._proc = None
                return VllmStatus(
                    state=state,
                    pid=None,
                    model=self._model_name() or None,
                    base_url=self._base_url(),
                    healthy=False,
                    error=self._last_error,
                    log_tail=list(self._log),
                )

            # Process is alive — probe /v1/models. If it answers we
            # consider it "running"; otherwise "starting".
            healthy = _probe_health(self._base_url())
            self._state = "running" if healthy else "starting"
            return VllmStatus(
                state=self._state,
                pid=proc.pid,
                model=self._model_name() or None,
                base_url=self._base_url(),
                healthy=healthy,
                error=self._last_error,
                log_tail=list(self._log),
            )

    # ── Internals ──────────────────────────────────────────────────────────

    def _drain_output(self, proc: subprocess.Popen[bytes]) -> None:
        if proc.stdout is None:
            return
        try:
            for raw in iter(proc.stdout.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                self._log.append(line)
        except Exception:
            # Reader is best-effort; never crash the app from log capture.
            pass


def _probe_health(base_url: str, *, timeout_s: float = 1.5) -> bool:
    """GET {base_url}/models — vLLM's OpenAI-compatible readiness probe."""
    url = base_url.rstrip("/") + "/models"
    try:
        with httpx.Client(timeout=timeout_s) as c:
            r = c.get(url)
        return bool(r.status_code == 200)
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Singleton + lifespan wiring


_INSTANCE: VllmProcess | None = None
_INSTANCE_LOCK = threading.Lock()


def get_instance() -> VllmProcess:
    """Module-level singleton. Exposed so tests can substitute."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = VllmProcess()
        return _INSTANCE


def set_instance(proc: VllmProcess | None) -> None:
    """Test seam — replace the singleton."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = proc


def terminate_on_app_shutdown() -> None:
    """Lifespan hook — SIGTERM any running vLLM subprocess on app exit.

    Idempotent and exception-safe so a misbehaving process never blocks
    FastAPI's normal shutdown sequence.
    """
    import contextlib

    inst = _INSTANCE
    if inst is None:
        return
    # Best-effort — never raise from a shutdown hook.
    with contextlib.suppress(Exception):
        inst.stop(grace_seconds=5.0)


# Tiny convenience for the dev script.
def vllm_serve_available() -> bool:
    """True if a usable vllm CLI exists.

    Two locations to check, in order: vllm-server's own .venv (where
    `uv sync` installs it, isolated from the backend's .venv), then
    the parent process's PATH as a fallback for users who install
    vllm globally.
    """
    if (VLLM_SERVER_DIR / ".venv" / "bin" / "vllm").exists():
        return True
    return shutil.which("vllm") is not None
