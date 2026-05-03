# vllm-server

Standalone vLLM launcher for the synthetic-question-generation pipeline.

This folder is **independent of the rest of the project's Python packaging**.
It exists so the FastAPI backend (or you, from a terminal) can spawn a
local vLLM OpenAI-compatible server with a single command, with config
isolated from the main application.

## Why separate?

vLLM pulls in CUDA toolchain, torch, sentencepiece, and a small mountain
of transitive deps. Keeping it in its own pyproject means:

- The main backend's `uv sync` doesn't drag vLLM along when you only
  need extraction / segmentation.
- You can install vLLM with whichever GPU stack matches your hardware
  (CUDA 12.1, ROCm, etc.) without conflicting with the main env.
- The model weights cache (multi-GB) lives next to this folder, not
  under `outputs/`.

## Default model

`Qwen/Qwen2.5-3B-Instruct` — chosen as a reasonable default that:

- Fits in **~8 GB VRAM** at bf16 (or 4-5 GB quantized).
- Is multilingual, including German.
- Has no Hugging Face auth gate (downloads anonymously).

If you have more VRAM and want better quality, edit `config.toml`:

| VRAM   | Suggested swap                                |
| ------ | ---------------------------------------------- |
| 8 GB   | `Qwen/Qwen2.5-3B-Instruct` (default)          |
| 12 GB  | `Qwen/Qwen2.5-7B-Instruct` (bf16)             |
| 16 GB  | `Qwen/Qwen2.5-7B-Instruct` + larger context  |
| 24+ GB | `Qwen/Qwen2.5-14B-Instruct`                   |

## Setup

Create a fresh virtual env for vLLM (separate from the main backend's
`.venv` to avoid CUDA/torch conflicts):

```bash
cd vllm-server
uv venv .venv
source .venv/bin/activate
uv pip install -e .
```

The first `start.sh` run will download the model from Hugging Face into
`~/.cache/huggingface` (default cache).

## Run standalone

```bash
./start.sh
```

The script reads `config.toml`, builds the `vllm serve …` command, and
writes stdout / stderr to `logs/vllm.log`. Press Ctrl-C to stop.

## Run from the SPA

Open the **Synthesise** tab in the admin UI. The top of the sidebar
shows an LLM-server status pill plus a **Start** / **Stop** button.
Hitting Start invokes `start.sh` as a subprocess of the FastAPI backend.
The backend SIGTERMs the subprocess on its own shutdown so you don't
end up with orphan vLLM workers.

## Files

- `pyproject.toml` — declares the `vllm` dependency.
- `config.toml` — model + server config (this is the file the SPA's
  Start button reads).
- `start.sh` — CLI entry point. Reads `config.toml`, exec's
  `vllm serve …`.
- `logs/` — captured stdout / stderr (gitignored).
