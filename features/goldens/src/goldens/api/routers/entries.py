"""Entry-id-scoped routes:

- GET  /api/entries                        — list active (filterable)
- GET  /api/entries/{entry_id}             — single
- POST /api/entries/{entry_id}/refine      — Task 15
- POST /api/entries/{entry_id}/deprecate   — Task 16
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query, Request

if TYPE_CHECKING:
    from pathlib import Path

    from goldens.schemas import HumanActor

from goldens.api.schemas import (
    DeprecateRequest,
    DeprecateResponse,
    RefineRequest,
    RefineResponse,
)
from goldens.creation.identity import Identity, identity_to_human_actor
from goldens.operations.deprecate import deprecate as deprecate_op
from goldens.operations.errors import EntryNotFoundError
from goldens.operations.refine import refine as refine_op
from goldens.schemas.retrieval import RetrievalEntry
from goldens.storage import GOLDEN_EVENTS_V1_FILENAME
from goldens.storage.log import read_events
from goldens.storage.projection import build_state, iter_active_retrieval_entries

router = APIRouter()


def _human_actor_from_identity(identity: Identity) -> HumanActor:
    return identity_to_human_actor(identity)


def _walk_event_logs(data_root: Path) -> list[Path]:
    """Yield every existing golden_events_v1.jsonl across all slugs under data_root."""
    if not data_root.is_dir():
        return []
    return [p for p in (data_root.glob(f"*/datasets/{GOLDEN_EVENTS_V1_FILENAME}")) if p.is_file()]


@router.get("/api/entries", response_model=list[RetrievalEntry])
async def list_entries(
    request: Request,
    slug: str | None = Query(default=None),
    source_element: str | None = Query(default=None),
    include_deprecated: bool = Query(default=False),
) -> list[RetrievalEntry]:
    data_root: Path = request.app.state.config.data_root
    entries: list[RetrievalEntry] = []

    if slug:
        log = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
        logs = [log] if log.exists() else []
    else:
        logs = _walk_event_logs(data_root)

    for log in logs:
        if include_deprecated:
            for entry in build_state(read_events(log)).values():
                entries.append(entry)
        else:
            for entry in iter_active_retrieval_entries(log):
                entries.append(entry)

    if source_element is not None:
        entries = [
            e
            for e in entries
            if e.source_element is not None and e.source_element.element_id == source_element
        ]
    return entries


@router.get("/api/entries/{entry_id}", response_model=RetrievalEntry)
async def get_entry(entry_id: str, request: Request) -> RetrievalEntry:
    data_root: Path = request.app.state.config.data_root
    for log in _walk_event_logs(data_root):
        state = build_state(read_events(log))
        if entry_id in state:
            return state[entry_id]
    raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")


@router.post("/api/entries/{entry_id}/refine", response_model=RefineResponse)
async def refine_entry(
    entry_id: str,
    body: RefineRequest,
    request: Request,
) -> RefineResponse:
    data_root: Path = request.app.state.config.data_root
    identity = request.app.state.identity

    # The refine() operation needs the path to the specific log. Since entries
    # live under one slug, we walk all logs and find which one contains this id.
    target_log: Path | None = None
    for log in _walk_event_logs(data_root):
        state = build_state(read_events(log))
        if entry_id in state:
            target_log = log
            break
    if target_log is None:
        raise EntryNotFoundError(entry_id)

    new_id = refine_op(
        target_log,
        entry_id,
        query=body.query,
        expected_chunk_ids=tuple(body.expected_chunk_ids),
        chunk_hashes=dict(body.chunk_hashes),
        actor=_human_actor_from_identity(identity),
        notes=body.notes,
        deprecate_reason=body.deprecate_reason,
    )
    return RefineResponse(new_entry_id=new_id)


@router.post("/api/entries/{entry_id}/deprecate", response_model=DeprecateResponse)
async def deprecate_entry(
    entry_id: str,
    body: DeprecateRequest,
    request: Request,
) -> DeprecateResponse:
    data_root: Path = request.app.state.config.data_root
    identity = request.app.state.identity

    target_log: Path | None = None
    for log in _walk_event_logs(data_root):
        state = build_state(read_events(log))
        if entry_id in state:
            target_log = log
            break
    if target_log is None:
        raise EntryNotFoundError(entry_id)

    event_id = deprecate_op(
        target_log,
        entry_id,
        actor=_human_actor_from_identity(identity),
        reason=body.reason,
    )
    return DeprecateResponse(event_id=event_id)
