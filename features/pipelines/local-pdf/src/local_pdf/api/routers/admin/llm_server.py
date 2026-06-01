"""Routes that control the local vLLM subprocess.

The admin top-bar in the SPA shows a status pill + model picker +
unified Start/Stop button that hits these endpoints. See
``local_pdf.llm_server.process`` for the underlying VllmProcess
manager.

Endpoints
---------

GET   /api/admin/llm/status         — current state + log tail
GET   /api/admin/llm/models         — curated allowlist with VRAM hints
POST  /api/admin/llm/start          — spawn vllm-server/start.sh if not running
POST  /api/admin/llm/stop           — SIGTERM, then SIGKILL on timeout
POST  /api/admin/llm/select-model   — rewrite [model].name in config.toml
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from local_pdf.llm_server.process import get_instance, vllm_serve_available

if TYPE_CHECKING:
    from local_pdf.llm_server import VllmStatus

router = APIRouter()


# ── Curated model registry ───────────────────────────────────────────
#
# Allowlist of models the UI can switch to. Each entry includes a
# rough bf16 VRAM estimate so the picker can flag "needs quantization"
# warnings on a 24 GB box. Users with different hardware can edit the
# list directly here.
#
# Verified on Hugging Face. Models that don't fit at bf16 in 24 GB
# (Gemma-27B, Mistral-Small-24B) are still listed but marked — the
# user is expected to pick a quantized variant or accept slower load.


class ModelOption(BaseModel):
    name: str
    label: str
    parameters_b: float
    vram_bf16_gb: int
    fits_24gb_bf16: bool
    multilingual: bool
    license: str
    notes: str
    # Optional vLLM ``--quantization`` flag. Some models require an
    # explicit value (e.g. Qwen3.5-27B-GPTQ-Int4 needs "moe_wna16")
    # because vLLM's auto-detection misses MoE-aware quantizers.
    # ``None`` = let vLLM auto-detect; ``select-model`` strips any
    # stale quantization line from config.toml in that case.
    quantization: str | None = None


MODEL_REGISTRY: list[ModelOption] = [
    # Strenge Filter-Regel: nur Modelle die SOFORT lauffähig sind auf
    # 24 GB VRAM — passt-in-bf16 ODER bereits quantisiert (FP8/INT4).
    # Reihenfolge = Empfehlung für deutschsprachiges Reasoning.
    # Modelle die nur mit Quantisierung passen würden (Qwen2.5-14B bf16,
    # Phi-4 bf16, Gemma-bf16, Mistral-bf16) sind bewusst NICHT gelistet —
    # sie würden beim Start scheitern oder OOM werfen. Falls eine
    # quantisierte Variante geladen wird, kann sie unten ergänzt werden.
    # Qwen3.5-27B-GPTQ-Int4 ENTFERNT — die Gated-Delta-Network-Layer
    # (mamba-Hybrid-Architektur) werden bei GPTQ nicht quantisiert,
    # real ~22 GB VRAM bei Inferenz statt der erwarteten ~15 GB. OOM
    # auf 24 GB. Auf einer GPU mit 32 GB+ wäre es lauffähig.
    ModelOption(
        name="Qwen/Qwen3-8B",
        label="1. Qwen3 8B Instruct ⭐ neuere Generation",
        parameters_b=8.2,
        vram_bf16_gb=16,
        fits_24gb_bf16=True,
        multilingual=True,
        license="Apache 2.0",
        notes=(
            "Qwen3 (Generation nach Qwen2.5) — text-only, 100+ Sprachen, "
            "natives Reasoning-Mode. Direkter A/B-Vergleich gegen 2.5-7B. "
            "Braucht --enable-reasoning + --reasoning-parser deepseek_r1 "
            "in vLLM für volle Qualität."
        ),
    ),
    ModelOption(
        name="Qwen/Qwen3.5-9B",
        label="3. Qwen3.5 9B (multimodal)",
        parameters_b=9.0,
        vram_bf16_gb=18,
        fits_24gb_bf16=True,
        multilingual=True,
        license="Apache 2.0",
        notes=(
            "9B in bf16 + Vision-Encoder. Knapp auf 24 GB — "
            "max_model_len=2048 in config.toml ist Pflicht (sonst OOM). "
            "Nutze nur wenn 27B-INT4 nicht geht."
        ),
    ),
    ModelOption(
        name="RedHatAI/gemma-3-27b-it-FP8-dynamic",
        label="2. Gemma 3 27B IT (FP8) ⭐ empfohlen",
        parameters_b=27.0,
        vram_bf16_gb=16,
        fits_24gb_bf16=True,
        multilingual=True,
        license="Apache 2.0",
        notes=(
            "FP8-Quantisierung von Gemma 3 27B — 27B Wissen bei 16 GB "
            "VRAM. 140 Sprachen, 99,73 % Accuracy-Recovery. Stärkstes "
            "Multilingual-Modell aus der Liste."
        ),
    ),
    ModelOption(
        name="Qwen/Qwen2.5-7B-Instruct",
        label="4. Qwen2.5 7B Instruct",
        parameters_b=7.0,
        vram_bf16_gb=16,
        fits_24gb_bf16=True,
        multilingual=True,
        license="Apache 2.0",
        notes=(
            "Solide Mittelklasse, deutsch + englisch. Schneller als 9B "
            "+ Gemma, aber etwas schwächer im Reasoning."
        ),
    ),
    ModelOption(
        name="Qwen/Qwen2.5-3B-Instruct",
        label="5. Qwen2.5 3B Instruct (Fallback)",
        parameters_b=3.0,
        vram_bf16_gb=8,
        fits_24gb_bf16=True,
        multilingual=True,
        license="Apache 2.0",
        notes=(
            "Kleinstes Modell, schnellster Boot. Bekannt schwach im "
            "Reasoning (leakt Templates, halluziniert Step-Namen). "
            "Nur für Latenz-kritische Tests."
        ),
    ),
]

_REGISTRY_NAMES = {m.name for m in MODEL_REGISTRY}


class LlmStatusResponse(BaseModel):
    state: str
    pid: int | None = None
    model: str | None = None
    base_url: str | None = None
    healthy: bool = False
    error: str | None = None
    log_tail: list[str] = []
    vllm_cli_available: bool = True


class SelectModelRequest(BaseModel):
    model_name: str


class ModelsResponse(BaseModel):
    models: list[ModelOption]
    current: str | None


def _to_response(s: VllmStatus) -> LlmStatusResponse:
    return LlmStatusResponse(
        state=s.state,
        pid=s.pid,
        model=s.model,
        base_url=s.base_url,
        healthy=s.healthy,
        error=s.error,
        log_tail=s.log_tail,
        vllm_cli_available=vllm_serve_available(),
    )


@router.get("/api/admin/llm/status", response_model=LlmStatusResponse)
async def llm_status() -> LlmStatusResponse:
    return _to_response(get_instance().status())


@router.get("/api/admin/llm/models", response_model=ModelsResponse)
async def llm_models() -> ModelsResponse:
    """Curated model allowlist + the currently configured one."""
    try:
        current = get_instance()._model_name() or None
    except Exception:
        current = None
    return ModelsResponse(models=MODEL_REGISTRY, current=current)


@router.post("/api/admin/llm/select-model", response_model=LlmStatusResponse)
async def llm_select_model(body: SelectModelRequest) -> LlmStatusResponse:
    """Rewrite ``[model].name`` in vllm-server/config.toml.

    Does NOT auto-restart a running process — the UI tells the user
    that the change applies on the next start. This keeps lifecycle
    transitions explicit (a silent restart while the user is mid-task
    would be surprising).
    """
    if body.model_name not in _REGISTRY_NAMES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Modell '{body.model_name}' nicht in der curated Liste. "
                "Erlaubt: " + ", ".join(sorted(_REGISTRY_NAMES))
            ),
        )
    # Look up the model's required quantization flag (None = strip any
    # stale ``quantization = ...`` line from config.toml so the new model
    # doesn't inherit the previous selection's quantizer).
    chosen = next(m for m in MODEL_REGISTRY if m.name == body.model_name)
    try:
        get_instance().set_model_name(
            body.model_name,
            quantization=chosen.quantization,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"config.toml-Update fehlgeschlagen: {exc}",
        ) from exc
    return _to_response(get_instance().status())


@router.post("/api/admin/llm/start", response_model=LlmStatusResponse)
async def llm_start() -> LlmStatusResponse:
    # Free MinerU/torch's cached pipeline models before starting vLLM
    # so the new server doesn't fight the backend's already-loaded
    # weights for VRAM. Idempotent — safe to call when nothing is
    # cached. Subsequent extract calls reload on demand.
    try:
        from local_pdf.workers.mineru import free_cached_models

        free_cached_models()
    except Exception:
        # Cleanup is best-effort; never let it block the start path.
        pass
    return _to_response(get_instance().start())


@router.post("/api/admin/llm/stop", response_model=LlmStatusResponse)
async def llm_stop() -> LlmStatusResponse:
    return _to_response(get_instance().stop())
