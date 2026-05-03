"""Synthesise routes — proof-of-life LLM ping endpoint.

# v1: minimal LLM ping endpoint; full synthesise UX is a future design pass.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from local_pdf.storage.sidecar import doc_dir

if TYPE_CHECKING:
    from llm_clients.base import LLMClient

router = APIRouter()

# Test hook — inject a fake LLMClient in tests.
_LLM_CLIENT: LLMClient | None = None


class SynthesiseTestRequest(BaseModel):
    prompt: str


class SynthesiseTestResponse(BaseModel):
    response: str
    model: str
    elapsed_seconds: float


@router.post(
    "/api/admin/docs/{slug}/synthesise/test",
    response_model=SynthesiseTestResponse,
)
async def synthesise_test(
    slug: str,
    body: SynthesiseTestRequest,
    request: Request,
) -> SynthesiseTestResponse:
    cfg = request.app.state.config
    if not doc_dir(cfg.data_root, slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")

    if _LLM_CLIENT is not None:
        client = _LLM_CLIENT
    else:
        from local_pdf.llm import get_llm_client

        client = get_llm_client()

    from llm_clients.base import Message

    from local_pdf.llm import get_default_model

    model = get_default_model()
    messages = [Message(role="user", content=body.prompt)]

    t0 = time.monotonic()
    completion = client.complete(messages=messages, model=model)
    elapsed = time.monotonic() - t0

    return SynthesiseTestResponse(
        response=completion.text,
        model=completion.model,
        elapsed_seconds=round(elapsed, 3),
    )
