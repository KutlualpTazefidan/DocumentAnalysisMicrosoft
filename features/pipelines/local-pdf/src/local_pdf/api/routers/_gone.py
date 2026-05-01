"""410 Gone shim for the pre-A.1.0 /api/docs/* paths.

Removed from this codebase 2026-05-15 (two weeks after the A.1.0 cutover).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_GONE_BODY = {
    "detail": (
        "moved to /api/admin/docs (admin) or /api/curate/docs (curator) — "
        "this shim is removed 2026-05-15"
    )
}


@router.api_route(
    "/api/docs",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    include_in_schema=False,
)
async def _gone_root() -> JSONResponse:
    return JSONResponse(status_code=410, content=_GONE_BODY)


@router.api_route(
    "/api/docs/{rest:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    include_in_schema=False,
)
async def _gone_rest(rest: str) -> JSONResponse:
    return JSONResponse(status_code=410, content=_GONE_BODY)
