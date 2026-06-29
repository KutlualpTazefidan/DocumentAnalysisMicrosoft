"""Read-only OKF knowledge endpoints. Mounted under /api/admin/ so the ASGI
auth middleware gates them. Pure file reads via local_pdf.knowledge — no Azure,
no openai (import-boundary clean). FileNotFoundError -> 404 and ValueError ->
400 are handled by the app-level exception handlers in app.py."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request

from local_pdf.knowledge import (
    list_bases,
    list_concepts,
    read_concept,
)

router = APIRouter()


@router.get("/api/admin/knowledge/bases")
async def get_bases(request: Request) -> list[dict]:
    root = request.app.state.config.knowledge_root
    return [asdict(b) for b in list_bases(root)]


@router.get("/api/admin/knowledge/bases/{base}/concepts")
async def get_concepts(base: str, request: Request) -> list[dict]:
    root = request.app.state.config.knowledge_root
    return [asdict(c) for c in list_concepts(root, base)]


@router.get("/api/admin/knowledge/bases/{base}/concept")
async def get_concept(base: str, path: str, request: Request) -> dict:
    root = request.app.state.config.knowledge_root
    return asdict(read_concept(root, base, path))
