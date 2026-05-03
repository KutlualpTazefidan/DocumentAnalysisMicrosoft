#!/usr/bin/env bash
# vllm-server/start.sh — read config.toml, exec `vllm serve …`.
#
# Usage:
#   ./start.sh              # foreground, log to stdout + logs/vllm.log
#   ./start.sh --background # nohup-style, write PID to logs/vllm.pid
#
# The FastAPI backend's /api/admin/llm/start endpoint invokes this
# script directly (without --background) so it can manage the PID and
# capture stdout/stderr itself.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

CONFIG="${HERE}/config.toml"
LOG_DIR="${HERE}/logs"
mkdir -p "$LOG_DIR"

# Find the python interpreter — prefer this folder's .venv, fall back
# to whatever python is on PATH.
if [[ -x "${HERE}/.venv/bin/python" ]]; then
    PY="${HERE}/.venv/bin/python"
else
    PY="$(command -v python || command -v python3)"
fi

if [[ -z "${PY}" ]]; then
    echo "error: no python interpreter found" >&2
    exit 1
fi

# Resolve the vllm binary the same way: prefer this folder's .venv, fall
# back to PATH. Doing this here means the FastAPI backend can launch
# start.sh without inheriting vllm-server/.venv/bin in its PATH.
if [[ -x "${HERE}/.venv/bin/vllm" ]]; then
    VLLM_BIN="${HERE}/.venv/bin/vllm"
else
    VLLM_BIN="$(command -v vllm || true)"
fi

if [[ -z "${VLLM_BIN}" ]]; then
    echo "error: vllm CLI not found — run 'uv sync' in ${HERE}" >&2
    exit 1
fi

# Parse config.toml via stdlib tomllib and emit a vllm CLI argv.
# Stays in a single python -c so we don't add tomli as a bash dep.
mapfile -t CMD < <("${PY}" - "$CONFIG" "$VLLM_BIN" <<'EOF'
import sys, tomllib, shlex
cfg = tomllib.loads(open(sys.argv[1]).read())
vllm_bin = sys.argv[2]
server = cfg.get("server", {})
model = cfg.get("model", {})
runtime = cfg.get("runtime", {})

argv = [vllm_bin, "serve", model.get("name", "Qwen/Qwen2.5-3B-Instruct")]
argv += ["--host", str(server.get("host", "127.0.0.1"))]
argv += ["--port", str(server.get("port", 8000))]
if "max_model_len" in model:
    argv += ["--max-model-len", str(model["max_model_len"])]
if "dtype" in model:
    argv += ["--dtype", str(model["dtype"])]
if "quantization" in model:
    argv += ["--quantization", str(model["quantization"])]
if "gpu_memory_utilization" in runtime:
    argv += ["--gpu-memory-utilization", str(runtime["gpu_memory_utilization"])]
for tok in argv:
    print(tok)
EOF
)

LOG_FILE="${LOG_DIR}/vllm.log"

if [[ "${1:-}" == "--background" ]]; then
    PID_FILE="${LOG_DIR}/vllm.pid"
    echo "starting in background, logs: ${LOG_FILE}"
    nohup "${CMD[@]}" >"${LOG_FILE}" 2>&1 &
    echo $! >"${PID_FILE}"
    echo "pid: $(cat "${PID_FILE}")"
else
    # Foreground: tee logs but don't background. The FastAPI backend
    # calls this mode and captures stdout/stderr itself via its
    # subprocess.Popen pipe.
    exec "${CMD[@]}" 2>&1 | tee -a "${LOG_FILE}"
fi
