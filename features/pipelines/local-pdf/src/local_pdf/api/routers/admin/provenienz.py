"""Provenienz tab routes — sessions CRUD (Stage 1).

Step + decision routes land in later stages.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path  # noqa: TC003

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from local_pdf.provenienz.storage import (
    Node,
    SessionMeta,
    append_node,
    new_id,
    read_meta,
    read_session,
    session_dir,
    write_meta,
)
from local_pdf.storage.sidecar import doc_dir, read_mineru

router = APIRouter()

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", html or "")).strip()


def _find_session_dir(data_root: Path, session_id: str) -> Path | None:
    for slug_dir in data_root.iterdir():
        if not slug_dir.is_dir():
            continue
        sd = slug_dir / "provenienz" / session_id
        if sd.exists():
            return sd
    return None


class CreateSessionRequest(BaseModel):
    slug: str
    root_chunk_id: str


class SessionMetaResponse(BaseModel):
    session_id: str
    slug: str
    root_chunk_id: str
    status: str
    created_at: str
    last_touched_at: str


def _meta_to_response(m: SessionMeta) -> SessionMetaResponse:
    return SessionMetaResponse(**m.__dict__)


@router.post(
    "/api/admin/provenienz/sessions",
    status_code=201,
    response_model=SessionMetaResponse,
)
async def create_session(body: CreateSessionRequest, request: Request) -> SessionMetaResponse:
    cfg = request.app.state.config
    if not doc_dir(cfg.data_root, body.slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {body.slug}")
    mineru = read_mineru(cfg.data_root, body.slug) or {"elements": []}
    el = next(
        (e for e in mineru.get("elements", []) if e.get("box_id") == body.root_chunk_id),
        None,
    )
    if el is None:
        raise HTTPException(
            status_code=404,
            detail=f"chunk not found in {body.slug}: {body.root_chunk_id}",
        )

    sid = new_id()
    sdir = session_dir(cfg.data_root, body.slug, sid)
    meta = SessionMeta(
        session_id=sid,
        slug=body.slug,
        root_chunk_id=body.root_chunk_id,
        status="open",
    )
    write_meta(sdir, meta)

    text = _strip_html(el.get("html_snippet", ""))
    append_node(
        sdir,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="chunk",
            payload={"box_id": body.root_chunk_id, "doc_slug": body.slug, "text": text},
            actor="system",
        ),
    )

    written = read_meta(sdir)
    assert written is not None
    return _meta_to_response(written)


@router.get("/api/admin/provenienz/sessions")
async def list_sessions(request: Request, slug: str | None = None) -> list[SessionMetaResponse]:
    cfg = request.app.state.config
    out: list[SessionMetaResponse] = []
    if slug is not None:
        slug_dirs = [cfg.data_root / slug]
    else:
        slug_dirs = [p for p in cfg.data_root.iterdir() if p.is_dir()]
    for slug_dir in slug_dirs:
        prov = slug_dir / "provenienz"
        if not prov.exists():
            continue
        for sd in sorted(prov.iterdir()):
            m = read_meta(sd)
            if m is not None:
                out.append(_meta_to_response(m))
    return out


@router.get("/api/admin/provenienz/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    nodes, edges = read_session(sd)
    return {
        "meta": _meta_to_response(meta).model_dump() if meta else None,
        "nodes": [n.__dict__ for n in nodes],
        "edges": [e.__dict__ for e in edges],
    }


@router.delete("/api/admin/provenienz/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request) -> None:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    shutil.rmtree(sd)
