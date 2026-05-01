"""Curator question entries — create, list, refine, deprecate."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status

from local_pdf.api.routers.curate.docs import _curator_can_see
from local_pdf.api.schemas import (
    CuratorQuestion,
    CuratorQuestionRequest,
    CuratorQuestionsFile,
    DeprecateQuestionRequest,
    RefineQuestionRequest,
)
from local_pdf.storage.sidecar import (
    read_curator_questions,
    read_source_elements,
    update_question,
    write_curator_questions,
)

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_curator(request: Request):
    ident = getattr(request.state, "identity", None)
    if ident is None or ident.role != "curator":
        raise HTTPException(status_code=403, detail="curator role required")
    return ident


@router.post(
    "/api/curate/docs/{slug}/questions",
    status_code=status.HTTP_201_CREATED,
)
async def post_question(slug: str, body: CuratorQuestionRequest, request: Request) -> dict:
    cfg = request.app.state.config
    ident = _require_curator(request)
    if not _curator_can_see(cfg, ident, slug):
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")

    payload = read_source_elements(cfg.data_root, slug) or {"elements": []}
    if not any(e["box_id"] == body.element_id for e in payload.get("elements", [])):
        raise HTTPException(status_code=404, detail=f"element not found: {body.element_id}")

    existing = read_curator_questions(cfg.data_root, slug) or CuratorQuestionsFile(
        slug=slug, questions=[]
    )
    q = CuratorQuestion(
        question_id=f"q-{secrets.token_hex(4)}",
        element_id=body.element_id,
        curator_id=ident.curator_id or "",
        query=body.query,
        created_at=_now_iso(),
    )
    write_curator_questions(
        cfg.data_root,
        slug,
        existing.model_copy(update={"questions": [*existing.questions, q]}),
    )
    return q.model_dump(mode="json")  # type: ignore[no-any-return]


@router.get("/api/curate/docs/{slug}/questions")
async def list_questions(
    slug: str,
    request: Request,
    element_id: str | None = Query(default=None),
) -> list[dict]:
    cfg = request.app.state.config
    ident = _require_curator(request)
    if not _curator_can_see(cfg, ident, slug):
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")

    file = read_curator_questions(cfg.data_root, slug) or CuratorQuestionsFile(
        slug=slug, questions=[]
    )
    questions = file.questions
    if element_id is not None:
        questions = [q for q in questions if q.element_id == element_id]
    return [q.model_dump(mode="json") for q in questions]


@router.post("/api/curate/docs/{slug}/questions/{question_id}/refine")
async def refine_question(
    slug: str, question_id: str, body: RefineQuestionRequest, request: Request
) -> dict:
    cfg = request.app.state.config
    ident = _require_curator(request)
    if not _curator_can_see(cfg, ident, slug):
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")

    result = update_question(cfg.data_root, slug, question_id, {"refined_query": body.query})
    if result is None:
        raise HTTPException(status_code=404, detail=f"question not found: {question_id}")

    updated = next(q for q in result.questions if q.question_id == question_id)
    return updated.model_dump(mode="json")  # type: ignore[no-any-return]


@router.post("/api/curate/docs/{slug}/questions/{question_id}/deprecate")
async def deprecate_question(
    slug: str, question_id: str, body: DeprecateQuestionRequest, request: Request
) -> dict:
    cfg = request.app.state.config
    ident = _require_curator(request)
    if not _curator_can_see(cfg, ident, slug):
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")

    patch: dict = {"deprecated": True}
    if body.reason is not None:
        patch["deprecated_reason"] = body.reason

    result = update_question(cfg.data_root, slug, question_id, patch)
    if result is None:
        raise HTTPException(status_code=404, detail=f"question not found: {question_id}")

    updated = next(q for q in result.questions if q.question_id == question_id)
    return updated.model_dump(mode="json")  # type: ignore[no-any-return]
