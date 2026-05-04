"""External-pipeline runner — the "right pane" of the Vergleich tab.

Two pipelines:

  microsoft → Azure AI Search hybrid (text+vector) retrieval, then
              Azure OpenAI chat completion using the retrieved chunks.
              Lives entirely inside features/pipelines/microsoft so
              local-pdf never imports Azure types directly.

  bam       → Stub. 501 until wired.

The route layer here is a thin adapter: it calls into the Microsoft
package and shapes the response. No local_pdf state is mutated and
no goldens events are written — comparison is read-only against
external pipelines.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


PipelineName = Literal["microsoft", "bam"]


class AskRequest(BaseModel):
    question: str
    top_k: int = 5


class PipelineChunk(BaseModel):
    chunk_id: str
    title: str | None = None
    chunk: str
    score: float
    source_file: str | None = None


class AskResponse(BaseModel):
    pipeline: PipelineName
    question: str
    chunks: list[PipelineChunk]
    answer: str


# ── Microsoft pipeline runner ────────────────────────────────────────────────


def _ask_microsoft(question: str, top_k: int) -> AskResponse:
    """Run hybrid_search + Azure OpenAI completion for one question.

    Imports happen here, not at module top, so the local-pdf backend
    starts even when the Microsoft package isn't installed (e.g. test
    environments without Azure creds).
    """
    try:
        from query_index.client import get_openai_client
        from query_index.config import Config
        from query_index.search import hybrid_search
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Microsoft pipeline package not installed: {exc}",
        ) from exc

    try:
        cfg = Config.from_env()
    except KeyError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Microsoft credentials missing in env: {exc}",
        ) from exc

    try:
        hits = hybrid_search(question, top=top_k, cfg=cfg)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Azure search failed: {exc}") from exc

    chunks = [
        PipelineChunk(
            chunk_id=h.chunk_id,
            title=h.title,
            chunk=h.chunk,
            score=h.score,
            source_file=h.source_file,
        )
        for h in hits
    ]

    # Build a context-only prompt. Use AZURE_OPENAI_DEPLOYMENT (chat) if
    # set; fall back to the embedding deployment name's family is wrong,
    # so require an explicit chat-deployment env var.
    import os

    chat_deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT")
    if not chat_deployment:
        raise HTTPException(
            status_code=503,
            detail="AZURE_OPENAI_CHAT_DEPLOYMENT not set — can't ask Microsoft for an answer",
        )

    context = "\n\n---\n\n".join(
        f"[{i + 1}] {c.title or c.chunk_id}\n{c.chunk}" for i, c in enumerate(chunks)
    )
    prompt = (
        "Beantworte die Frage AUSSCHLIESSLICH anhand des unten stehenden Kontexts. "
        "Wenn der Kontext die Antwort nicht enthält, antworte mit 'unbekannt'. "
        "Antworte knapp in der Sprache der Frage.\n\n"
        f"Kontext:\n{context}\n\n"
        f"Frage: {question}"
    )

    client = get_openai_client(cfg)
    try:
        resp = client.chat.completions.create(
            model=chat_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Azure chat failed: {exc}") from exc

    answer = (resp.choices[0].message.content or "").strip()
    return AskResponse(pipeline="microsoft", question=question, chunks=chunks, answer=answer)


@router.post("/api/admin/pipelines/{name}/ask", response_model=AskResponse)
async def ask(name: str, body: AskRequest) -> AskResponse:
    if name == "microsoft":
        return _ask_microsoft(body.question, body.top_k)
    if name == "bam":
        raise HTTPException(status_code=501, detail="BAM pipeline not implemented yet")
    raise HTTPException(status_code=404, detail=f"unknown pipeline: {name}")


# Expose available pipelines so the frontend dropdown stays in sync.


class PipelineInfo(BaseModel):
    name: str
    label: str
    available: bool
    note: str | None = None


@router.get("/api/admin/pipelines", response_model=list[PipelineInfo])
async def list_pipelines() -> list[PipelineInfo]:
    import os

    ms_keys_present = bool(
        os.environ.get("AI_SEARCH_KEY")
        and os.environ.get("AI_SEARCH_ENDPOINT")
        and os.environ.get("AI_SEARCH_INDEX_NAME")
    )
    return [
        PipelineInfo(
            name="microsoft",
            label="Microsoft",
            available=ms_keys_present,
            note=None if ms_keys_present else "Azure-Credentials fehlen in .env",
        ),
        PipelineInfo(
            name="bam",
            label="BAM",
            available=False,
            note="Noch nicht implementiert",
        ),
    ]


# Mypy quiet-down for unused TYPE_CHECKING import slot.
_: Any = None
