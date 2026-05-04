"""Routes for the Vergleich (comparison) tab.

Three endpoints:

  GET  /api/admin/docs/{slug}/questions/{entry_id}/similar?k=5
       Top-k other questions in the doc, scored by BM25 (always) and
       cosine over Azure OpenAI embeddings (when configured).

  POST /api/admin/compare
       Body {reference, candidate}. Numeric similarity between two
       answers — bm25 (normalised) + cosine (when configured).

The Microsoft pipeline runner (POST /api/admin/pipelines/...) lives
in its own router so the Microsoft path stays decoupled from
local-pdf processing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from local_pdf.api.routers.admin.synthesise import _list_questions
from local_pdf.comparison import score_pair, similar_questions
from local_pdf.storage.sidecar import doc_dir
from local_pdf.synthetic import MineruElementsLoader

if TYPE_CHECKING:
    from collections.abc import Callable

router = APIRouter()


# ── Embedder factory ─────────────────────────────────────────────────────────
# Azure OpenAI text-embedding deployment (the same one the Microsoft
# retrieval pipeline uses). When AI_FOUNDRY_KEY / EMBEDDING_DEPLOYMENT_NAME
# aren't set, the embedder is None and scoring degrades to BM25-only.


def _build_embedder() -> Callable[[list[str]], list[list[float]]] | None:
    try:
        from query_index.client import get_openai_client
        from query_index.config import Config
    except ImportError:
        return None
    try:
        cfg = Config.from_env()
    except KeyError:
        return None
    try:
        client = get_openai_client(cfg)
    except Exception:
        return None

    def embed(texts: list[str]) -> list[list[float]]:
        # Azure embeddings API accepts a list — one round-trip per call.
        resp = client.embeddings.create(input=texts, model=cfg.embedding_deployment_name)
        return [list(d.embedding) for d in resp.data]

    return embed


# ── /similar ────────────────────────────────────────────────────────────────


class SimilarHit(BaseModel):
    entry_id: str
    text: str
    box_id: str
    chunk: str
    bm25_score: float
    cosine_score: float


class SimilarResponse(BaseModel):
    entry_id: str
    embedder: bool
    hits: list[SimilarHit]


@router.get(
    "/api/admin/docs/{slug}/questions/{entry_id}/similar",
    response_model=SimilarResponse,
)
async def similar(slug: str, entry_id: str, request: Request, k: int = 5) -> SimilarResponse:
    cfg = request.app.state.config
    if not doc_dir(cfg.data_root, slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")

    questions = _list_questions(cfg, slug)
    target = next((q for q in questions if q.entry_id == entry_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"entry_id not found: {entry_id}")

    candidates = [(q.entry_id, q.text, q.box_id) for q in questions]

    # box content per box_id, for the SimilarHit.chunk field. The
    # MineruElementsLoader already strips HTML and applies the table-
    # row newline rendering — so we get the same content the question
    # generator saw.
    loader = MineruElementsLoader(data_root=cfg.data_root, slug=slug)
    chunks = {el.element_id: el.content for el in loader.elements()}

    embedder = _build_embedder()
    hits = similar_questions(
        query_entry_id=target.entry_id,
        query_text=target.text,
        candidates=candidates,
        chunks=chunks,
        embedder=embedder,
        k=k,
    )
    return SimilarResponse(
        entry_id=entry_id,
        embedder=embedder is not None,
        hits=[SimilarHit(**h.__dict__) for h in hits],
    )


# ── /compare ────────────────────────────────────────────────────────────────


class CompareRequest(BaseModel):
    reference: str
    candidate: str


class CompareResponse(BaseModel):
    bm25: float
    cosine: float
    embedder: bool


@router.post("/api/admin/compare", response_model=CompareResponse)
async def compare(body: CompareRequest, request: Request) -> CompareResponse:
    _ = request  # cfg unused for compare; route signature parity with siblings
    embedder = _build_embedder()
    scores = score_pair(body.reference, body.candidate, embedder=embedder)
    return CompareResponse(
        bm25=scores["bm25"],
        cosine=scores["cosine"],
        embedder=embedder is not None,
    )


# ── /compare-bulk — score one reference against many candidates ─────────────


class CompareBulkRequest(BaseModel):
    reference: str
    candidates: list[str]


class CompareBulkScore(BaseModel):
    bm25: float
    cosine: float


class CompareBulkResponse(BaseModel):
    embedder: bool
    scores: list[CompareBulkScore]


@router.post("/api/admin/compare-bulk", response_model=CompareBulkResponse)
async def compare_bulk(body: CompareBulkRequest, request: Request) -> CompareBulkResponse:
    """Score *reference* against each *candidates*[i].

    Used by the Vergleich tab to surface "how much did each retrieved
    chunk actually contribute to the answer?" — high-scoring chunks
    were likely the basis of the answer; low-scoring ones were
    dragged in but ignored. The user reads this as a context-
    efficiency signal.
    """
    _ = request
    embedder = _build_embedder()
    out: list[CompareBulkScore] = []
    for cand in body.candidates:
        s = score_pair(body.reference, cand, embedder=embedder)
        out.append(CompareBulkScore(bm25=s["bm25"], cosine=s["cosine"]))
    return CompareBulkResponse(embedder=embedder is not None, scores=out)


# ── helpers reused by tests via dependency injection (not implemented here). ──

if TYPE_CHECKING:
    _: Any = None
