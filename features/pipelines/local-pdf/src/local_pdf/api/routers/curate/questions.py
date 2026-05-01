"""Curator question entry."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from local_pdf.api.routers.curate.docs import _curator_can_see
from local_pdf.api.schemas import (
    CuratorQuestion,
    CuratorQuestionRequest,
    CuratorQuestionsFile,
)
from local_pdf.storage.sidecar import (
    read_curator_questions,
    read_source_elements,
    write_curator_questions,
)

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.post(
    "/api/curate/docs/{slug}/questions",
    status_code=status.HTTP_201_CREATED,
)
async def post_question(slug: str, body: CuratorQuestionRequest, request: Request) -> dict:
    cfg = request.app.state.config
    ident = getattr(request.state, "identity", None)
    if ident is None or ident.role != "curator":
        raise HTTPException(status_code=403, detail="curator role required")
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
