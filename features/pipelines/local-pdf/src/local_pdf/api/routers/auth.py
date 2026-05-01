"""Shared (public + token-validating) auth + feature endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from local_pdf.api.auth import lookup_token

router = APIRouter()


class CheckTokenRequest(BaseModel):
    token: str


class CheckTokenResponse(BaseModel):
    role: str
    name: str


class FeaturesResponse(BaseModel):
    features: list[str]
    roles: list[str]


@router.post("/api/auth/check", response_model=CheckTokenResponse)
async def check_token(body: CheckTokenRequest, request: Request) -> CheckTokenResponse:
    cfg = request.app.state.config
    ident = lookup_token(cfg.data_root, body.token, admin_token=cfg.api_token)
    if ident is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return CheckTokenResponse(role=ident.role, name=ident.name)


@router.get("/api/_features", response_model=FeaturesResponse)
async def get_features() -> FeaturesResponse:
    return FeaturesResponse(
        features=["local-pdf", "curate", "synthesise"],
        roles=["admin", "curator"],
    )
