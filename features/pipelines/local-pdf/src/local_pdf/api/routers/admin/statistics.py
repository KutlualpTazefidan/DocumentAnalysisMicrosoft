"""Statistics — read-only aggregators powering the Statistik tab.

v1 is C1 live-scan: every request walks the on-disk artifacts. See
docs/superpowers/specs/2026-06-03-statistics-and-voting-design.md
for the V2 (DuckDB) trigger.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from fastapi import APIRouter, HTTPException, Request
from goldens.storage import GOLDEN_EVENTS_V1_FILENAME, iter_active_retrieval_entries
from goldens.storage.log import read_events

from local_pdf.api.models.statistics import (
    CapabilityWish,
    CapabilityWishes,
    DiagnosticCounts,
    ExtractStats,
    ProvenienzStats,
    SyntheseStats,
    VoteDistributionRow,
)
from local_pdf.api.routers.admin.provenienz import list_capability_requests
from local_pdf.auth.tenant_root import tenant_data_root, tenant_slug_from_request
from local_pdf.provenienz.storage import read_session
from local_pdf.storage.sidecar import doc_dir, read_mineru, read_segments

router = APIRouter()

_REGISTER_KINDS = {"toc", "list_of_tables", "list_of_figures", "bibliography"}


def _tr(request: Request) -> Path:
    raw = request.app.state.config.data_root
    return tenant_data_root(raw, tenant_slug_from_request(request))


def _count_diagnostics(mineru: dict | None) -> DiagnosticCounts:
    diags = (mineru or {}).get("diagnostics") or []
    elements = (mineru or {}).get("elements") or []
    split = sum(1 for d in diags if d.get("kind") == "split")
    nodecomp = sum(1 for d in diags if d.get("kind") == "no_decomposition")
    total = len(elements)
    clean = max(total - split - nodecomp, 0)
    return DiagnosticCounts(split=split, no_decomposition=nodecomp, clean=clean, total=total)


def _count_register_boxes(segments: dict | None) -> tuple[int, int]:
    boxes = (segments or {}).get("boxes") or []
    total = len(boxes)
    reg = sum(1 for b in boxes if b.get("kind") in _REGISTER_KINDS)
    return reg, total


@router.get("/api/admin/statistics/extract/{slug}", response_model=ExtractStats)
async def extract_stats(slug: str, request: Request) -> ExtractStats:
    data_root = _tr(request)
    if not doc_dir(data_root, slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    mineru = read_mineru(data_root, slug)
    segments_file = read_segments(data_root, slug)
    segments_dict = segments_file.model_dump() if segments_file is not None else None
    reg, total_boxes = _count_register_boxes(segments_dict)
    diag = _count_diagnostics(mineru)
    rate = (reg / total_boxes) if total_boxes > 0 else None
    return ExtractStats(
        slug=slug,
        diagnostics=diag,
        register_boxes=reg,
        total_boxes=total_boxes,
        register_rate=rate,
    )


def _events_path(data_root: Path, slug: str) -> Path:
    path: Path = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    return path


def _collapse_votes(events) -> tuple[dict[tuple[str, str], str], dict[str, dict[str, int]]]:
    """Walk reviewed events; return (latest_per_pair, per_entry_counts).

    latest_per_pair maps (entry_id, pseudonym) → action.
    per_entry_counts maps entry_id → {"approved": n, "rejected": m}
    counting only non-revoked latest votes.
    """
    latest: dict[tuple[str, str], tuple[str, str]] = {}
    for ev in events:
        if ev.event_type != "reviewed":
            continue
        action = ev.payload.get("action")
        if action not in {"approved", "rejected", "revoked"}:
            continue
        actor = ev.payload.get("actor") or {}
        pseudo = actor.get("pseudonym")
        if not pseudo:
            continue
        key = (ev.entry_id, pseudo)
        prev = latest.get(key)
        if prev is None or ev.timestamp_utc >= prev[1]:
            latest[key] = (action, ev.timestamp_utc)
    latest_actions = {k: v[0] for k, v in latest.items()}
    per_entry: dict[str, dict[str, int]] = {}
    for (entry_id, _pseudo), action in latest_actions.items():
        if action == "revoked":
            continue
        bucket = per_entry.setdefault(entry_id, {"approved": 0, "rejected": 0})
        bucket[action] += 1
    return latest_actions, per_entry


@router.get("/api/admin/statistics/synthese/{slug}", response_model=SyntheseStats)
async def synthese_stats(slug: str, request: Request) -> SyntheseStats:
    data_root = _tr(request)
    if not doc_dir(data_root, slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    path = _events_path(data_root, slug)
    events = read_events(path) if path.exists() else []
    created = sum(1 for ev in events if ev.event_type == "created")
    deprecated = sum(1 for ev in events if ev.event_type == "deprecated")
    survival = ((created - deprecated) / created) if created > 0 else None

    _, per_entry = _collapse_votes(events)
    total_approved = sum(v["approved"] for v in per_entry.values())
    total_rejected = sum(v["rejected"] for v in per_entry.values())
    denom = total_approved + total_rejected
    approval_rate = (total_approved / denom) if denom > 0 else None

    text_by_entry: dict[str, str] = {}
    if path.exists():
        for entry in iter_active_retrieval_entries(path):
            text_by_entry[entry.entry_id] = (entry.query or "")[:60]

    rows = [
        VoteDistributionRow(
            entry_id=entry_id,
            text_short=text_by_entry.get(entry_id, entry_id),
            approved=counts["approved"],
            rejected=counts["rejected"],
        )
        for entry_id, counts in per_entry.items()
    ]
    rows.sort(key=lambda r: min(r.approved, r.rejected), reverse=True)
    rows = rows[:20]

    return SyntheseStats(
        slug=slug,
        questions_created=created,
        questions_deprecated=deprecated,
        survival_rate=survival,
        vote_approved=total_approved,
        vote_rejected=total_rejected,
        vote_approval_rate=approval_rate,
        vote_distribution=rows,
    )


_EXPERT_OVERRIDE_KINDS = {"expert_step_override", "expert_method_request"}


@router.get("/api/admin/statistics/provenienz/{slug}", response_model=ProvenienzStats)
async def provenienz_stats(slug: str, request: Request) -> ProvenienzStats:
    data_root = _tr(request)
    if not doc_dir(data_root, slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    prov_root = data_root / slug / "provenienz"
    plan_proposals = 0
    overrides = 0
    if prov_root.exists():
        for sd in sorted(prov_root.iterdir()):
            if not sd.is_dir():
                continue
            try:
                nodes, _ = read_session(sd)
            except Exception:
                continue
            for n in nodes:
                if n.kind == "plan_proposal":
                    plan_proposals += 1
                elif n.kind in _EXPERT_OVERRIDE_KINDS:
                    overrides += 1
    rate = (overrides / plan_proposals) if plan_proposals > 0 else None
    return ProvenienzStats(
        slug=slug,
        plan_proposals=plan_proposals,
        expert_overrides=overrides,
        correction_rate=rate,
    )


def _skill_bucket(name: str) -> str:
    """Heuristic: lowercased leading word (camelCase split on first uppercase).

    Falls back to 'other' for empty / unrecognised names so the
    Treemap always has a parent node.
    """
    name = name.strip()
    if not name:
        return "other"
    head: list[str] = []
    for i, ch in enumerate(name):
        if i > 0 and ch.isupper():
            break
        head.append(ch)
    return "".join(head).lower() or "other"


@router.get("/api/admin/statistics/capability-wishes", response_model=CapabilityWishes)
async def capability_wishes(request: Request) -> CapabilityWishes:
    raw = await list_capability_requests(request)
    wishes = [
        CapabilityWish(
            name=item["name"],
            count=item["count"],
            by_actor=item.get("count_by_actor") or {"human": 0, "agent": item["count"]},
            skill_bucket=_skill_bucket(item["name"]),
        )
        for item in raw.get("requests", [])
    ]
    return CapabilityWishes(wishes=wishes)
