"""Provenienz tab routes — sessions CRUD (Stage 1).

Step + decision routes land in later stages.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from collections.abc import Iterator  # noqa: TC003
from dataclasses import asdict, dataclass, field
from pathlib import Path  # noqa: TC003
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from llm_clients.base import Message
from pydantic import BaseModel

from local_pdf.llm import get_default_model, get_llm_client
from local_pdf.provenienz.approaches import (
    Approach,
    auto_select_approaches,
    get_approach,
    match_triggers,
    read_approaches,
    scan_capabilities,
)
from local_pdf.provenienz.llm import (
    ActionOption,
    ActionProposalPayload,
    GuidanceRef,
    build_proposal_node,
    resolve_provider,
)
from local_pdf.provenienz.reasons import Reason, append_reason, read_reasons
from local_pdf.provenienz.searcher import InDocSearcher
from local_pdf.provenienz.storage import (
    Edge,
    Node,
    SessionMeta,
    append_edge,
    append_node,
    append_tombstone,
    new_id,
    read_meta,
    read_session,
    session_dir,
    write_meta,
)
from local_pdf.provenienz.tools import list_tools
from local_pdf.storage.sidecar import doc_dir, read_mineru

_log = logging.getLogger(__name__)

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
    pinned_approach_ids: list[str] = []
    goal: str = ""


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


@router.get("/api/admin/provenienz/capability-requests")
async def list_capability_requests(request: Request) -> dict:
    """Aggregate every ``capability_request`` Node across all sessions
    into a TODO list grouped by name. Powers the "Capability-Wünsche"
    tab on the Agent page — turns the agent's lived experience of
    "what's missing" into a data-driven roadmap.

    Sorted by count descending. Each entry carries a few example
    occurrences so the user can see the actual sessions / contexts.
    """
    cfg = request.app.state.config
    aggregated: dict[str, list[dict]] = {}
    for slug_dir in cfg.data_root.iterdir():
        if not slug_dir.is_dir():
            continue
        prov = slug_dir / "provenienz"
        if not prov.exists():
            continue
        for sd in sorted(prov.iterdir()):
            if not sd.is_dir():
                continue
            try:
                nodes, _ = read_session(sd)
            except Exception:
                continue
            for n in nodes:
                if n.kind != "capability_request":
                    continue
                name = str(n.payload.get("name", "")).strip() or "(unnamed)"
                aggregated.setdefault(name, []).append(
                    {
                        "session_id": n.session_id,
                        "slug": slug_dir.name,
                        "node_id": n.node_id,
                        "description": str(n.payload.get("description", "")),
                        "reasoning": str(n.payload.get("reasoning", "")),
                        "created_at": n.created_at,
                    }
                )
    pairs: list[tuple[int, str, list[dict]]] = [
        (len(items), name, items[:5]) for name, items in aggregated.items()
    ]
    pairs.sort(key=lambda p: (-p[0], p[1]))
    return {
        "requests": [
            {"name": name, "count": count, "examples": examples} for count, name, examples in pairs
        ]
    }


@router.get("/api/admin/provenienz/tools")
async def get_tools() -> dict:
    """Tool/capability registry — what skills the Planner can pick from.

    Adds new tools by appending to ``TOOL_REGISTRY`` in
    ``local_pdf.provenienz.tools``. The Agent tab + the Planner both
    consume this list. ``enabled=False`` tools are visible (so the user
    knows the system *could* do that) but the Planner is constrained from
    selecting them.
    """
    return {"tools": [t.__dict__ for t in list_tools()]}


@router.get("/api/admin/provenienz/agent-info")
async def get_agent_info() -> dict:
    """Static description of the agent's topology, prompts, tools and rules.

    Surfaced so the Agent tab can render a flowchart of the system itself
    without duplicating any prompt strings on the frontend. Read-only —
    editing prompts/models requires a redeploy today (a future "live edit"
    feature would land its own POST endpoint).
    """
    backend = os.environ.get("LLM_BACKEND", "ollama_local")
    if backend == "vllm_remote":
        model = os.environ.get("VLLM_MODEL", "")
        base_url = os.environ.get("VLLM_BASE_URL", "")
    elif backend == "azure_openai":
        model = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "")
        base_url = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    else:
        model = os.environ.get("LLM_MODEL", "qwen2.5:7b-instruct")
        base_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

    return {
        "llm": {"backend": backend, "model": model, "base_url": base_url},
        "next_step": {
            "kind": "next_step",
            "label": "Was als nächstes?",
            "input_kind": "any node (chunk / claim / task / search_result)",
            "output_kind": ("plan_proposal | capability_request | manual_review"),
            "uses_llm": True,
            "uses_tool": None,
            "rules": ["approaches", "reasons"],
            "system_prompt": NEXT_STEP_SYSTEM,
            "expected_output": (
                "JSON-Objekt mit kind-Diskriminator. Drei Modi:\n"
                "  - executable_step: Agent wählt einen registrierten Step "
                "aus _VALID_STEPS_FOR_KIND und übergibt name + tool + "
                "approach_id. Frontend feuert den passenden /step-Endpoint "
                "via 'Akzeptieren'.\n"
                "  - capability_request: kein registrierter Step + Tool "
                "passt. name = Bezeichnung der fehlenden Capability, "
                "description = was nötig wäre. Wird zur TODO-Liste für "
                "Tool-Entwicklung.\n"
                "  - manual_review: nur Mensch kann lösen. description = "
                "warum, name = kurze Bezeichnung der Aufgabe."
            ),
        },
        "valid_steps_per_anchor": {
            kind: list(steps) for kind, steps in _VALID_STEPS_FOR_KIND.items()
        },
        "steps": [
            {
                "kind": "extract_claims",
                "label": "Aussagen extrahieren",
                "input_kind": "chunk",
                "output_kind": "claim",
                "uses_llm": True,
                "uses_tool": None,
                "rules": ["reasons", "approaches", "origin_context"],
                "system_prompt": EXTRACT_CLAIMS_SYSTEM,
                "user_template": (
                    "Textabschnitt:\n<chunk_text>\n\nGib das JSON-Array der Aussagen zurück."
                ),
                "expected_output": "JSON-Array von Strings (eine Aussage pro Eintrag)",
            },
            {
                "kind": "formulate_task",
                "label": "Aufgabe formulieren",
                "input_kind": "claim",
                "output_kind": "task",
                "uses_llm": True,
                "uses_tool": None,
                "rules": ["reasons", "approaches"],
                "system_prompt": FORMULATE_TASK_SYSTEM,
                "user_template": "Aussage: <claim_text>\nSuchanfrage:",
                "expected_output": "Eine Suchanfrage (max. 12 Wörter)",
            },
            {
                "kind": "search",
                "label": "Suchen",
                "input_kind": "task",
                "output_kind": "search_result",
                "uses_llm": False,
                "uses_tool": "InDocSearcher",
                "rules": [],
                "system_prompt": "",
                "user_template": "",
                "expected_output": "Liste von SearchHits (top_k konfigurierbar, default 5)",
            },
            {
                "kind": "evaluate",
                "label": "Bewerten",
                "input_kind": "search_result",
                "output_kind": "evaluation",
                "uses_llm": True,
                "uses_tool": None,
                "rules": ["reasons", "approaches"],
                "system_prompt": EVALUATE_SYSTEM,
                "user_template": ("Aussage:\n<claim_text>\n\nKandidat:\n<candidate_text>\n\nJSON:"),
                "expected_output": (
                    "JSON-Objekt mit verdict, confidence, reasoning. "
                    "Tolerant: akzeptiert auch [verdict, conf, reasoning]-Array; "
                    "fällt bei unparsbarer Ausgabe auf verdict='unknown' zurück."
                ),
            },
            {
                "kind": "propose_stop",
                "label": "Stopp vorschlagen",
                "input_kind": "any",
                "output_kind": "stop_proposal",
                "uses_llm": True,
                "uses_tool": None,
                "rules": ["reasons", "approaches"],
                "system_prompt": PROPOSE_STOP_SYSTEM,
                "user_template": "Aktueller Knoten: <anchor_text>\nBegründung für Stopp:",
                "expected_output": "Ein deutscher Satz (max. 25 Wörter)",
            },
            {
                "kind": "extract_goal",
                "label": "Recherche-Ziel ableiten",
                "input_kind": "chunk + first_claim",
                "output_kind": "session.goal",
                "uses_llm": True,
                "uses_tool": None,
                "rules": ["approaches"],
                "system_prompt": EXTRACT_GOAL_SYSTEM,
                "user_template": (
                    "Textabschnitt:\n<chunk_text>\n\n"
                    "Erste überprüfbare Aussage:\n<first_claim_text>\n\n"
                    "Recherche-Ziel:"
                ),
                "expected_output": (
                    "Ein deutscher Satz (max. 20 Wörter), eher Frage als Vermutung. "
                    "Wird automatisch nach der ersten /decide-Akzeptanz von "
                    "extract_claims ausgeführt; Best-Effort, Fehler werden "
                    "geloggt + verschluckt. Manuell überschreibbar via "
                    "PUT /sessions/{id}/goal."
                ),
            },
            {
                "kind": "promote_search_result",
                "label": "Treffer weiter erforschen",
                "input_kind": "search_result",
                "output_kind": "chunk",
                "uses_llm": False,
                "uses_tool": None,
                "rules": ["origin_context"],
                "system_prompt": "",
                "user_template": "",
                "expected_output": (
                    "Neuer Chunk-Knoten mit Recherche-Kontext (origin_claim, "
                    "origin_query, origin_chunk). Anschließendes extract_claims "
                    "auf diesem Chunk erhält den Kontext im System-Prompt."
                ),
            },
        ],
        "tools": [t.__dict__ for t in list_tools()],
        "rules": {
            "reasons": {
                "summary": "Implizite Hinweise aus früheren Korrekturen",
                "trigger": "Nutzer wählt 'Eigene Eingabe' bei /decide + füllt 'Begründung'",
                "storage": "{data_root}/provenienz/reasons.jsonl (global)",
                "injection": "letzte N=5 passende step_kind-Reasons in System-Prompt",
                "applies_to": ["extract_claims", "formulate_task", "evaluate", "propose_stop"],
            },
            "approaches": {
                "summary": "Explizite, benannte Prompt-Erweiterungen",
                "trigger": "Curator legt einen Approach an + Sitzung pinnt ihn",
                "storage": "{data_root}/provenienz/approaches.jsonl (global)",
                "injection": (
                    "extra_system aller gepinnten + aktivierten + step_kind-passenden Approaches"
                ),
                "applies_to": ["extract_claims", "formulate_task", "evaluate", "propose_stop"],
            },
            "origin_context": {
                "summary": "Recherche-Kontext bei abgeleiteten Chunks",
                "trigger": "Chunk wurde via promote-search-result erzeugt",
                "storage": "Auf chunk.payload (origin_claim_text, origin_query, …)",
                "injection": "Als 'Kontext der Recherche'-Block vor extra_system",
                "applies_to": ["extract_claims"],
            },
        },
    }


@router.delete("/api/admin/provenienz/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request) -> None:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    shutil.rmtree(sd)


_DEPENDS_ON_EDGE_KINDS: set[str] = {
    "extracts-from",  # claim → chunk
    "verifies",  # task → claim
    "candidates-for",  # search_result → task
    "evaluates",  # evaluation → search_result
    "promoted-from",  # promoted chunk → search_result
    "enriches",  # claim_background → claim
}

# Edges from a *decision* to a node that the decision spawned. When the
# decision itself is in the cascade-set (because its proposal got
# deleted), every node it spawned must follow — otherwise deleting a
# search-action_proposal would leave its bag of search_results behind.
_TRIGGERED_BY_DECISION_EDGE_KINDS: set[str] = {"triggers"}


def _collect_cascade(target_id: str, nodes: list[Node], edges: list[Edge]) -> set[str]:
    """Walk the dependency graph and return every node that should be
    tombstoned together with *target_id*.

    A node X depends on Y when there's an edge X → Y whose kind is in
    ``_DEPENDS_ON_EDGE_KINDS``. Deleting Y means X must go too. We also
    sweep up: action_proposals + stop_proposals anchored to anything in
    the deleted set, and decisions resolving those proposals. The pass
    repeats until the set stabilises.
    """
    deleted: set[str] = {target_id}
    while True:
        before = len(deleted)
        # 1) Domain-dependency cascade: child → parent edges
        for e in edges:
            if (
                e.to_node in deleted
                and e.kind in _DEPENDS_ON_EDGE_KINDS
                and e.from_node not in deleted
            ):
                deleted.add(e.from_node)
        # 2) Anchor cascade: action_proposal / stop_proposal anchored to
        #    a deleted node
        for n in nodes:
            if n.node_id in deleted:
                continue
            if n.kind not in {"action_proposal", "stop_proposal"}:
                continue
            anchor = n.payload.get("anchor_node_id")
            if isinstance(anchor, str) and anchor in deleted:
                deleted.add(n.node_id)
        # 3) Decision cascade: decided-by → proposal
        for e in edges:
            if e.kind == "decided-by" and e.to_node in deleted and e.from_node not in deleted:
                deleted.add(e.from_node)
        # 4) Decision-spawned cascade: decision (deleted) → spawned nodes
        #    via "triggers" edges. Lets bag-delete (= delete the search
        #    action_proposal) sweep all search_results + evaluations +
        #    capability_gates the same decision created.
        decisions_in_set = {
            n.node_id for n in nodes if n.kind == "decision" and n.node_id in deleted
        }
        for e in edges:
            if (
                e.kind in _TRIGGERED_BY_DECISION_EDGE_KINDS
                and e.from_node in decisions_in_set
                and e.to_node not in deleted
            ):
                deleted.add(e.to_node)
        if len(deleted) == before:
            return deleted


class SetGoalRequest(BaseModel):
    goal: str


@router.put("/api/admin/provenienz/sessions/{session_id}/goal")
async def set_goal(session_id: str, body: SetGoalRequest, request: Request) -> dict:
    """Manual override for the session goal. Used when the auto-extracted
    goal is wrong or when the user wants to set it before any claim has
    been accepted."""
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    new_meta = SessionMeta(**{**meta.__dict__, "goal": body.goal.strip()[:300]})
    write_meta(sd, new_meta)
    written = read_meta(sd)
    assert written is not None
    return {"meta": _meta_to_response(written).model_dump()}


class SetClaimGoalRequest(BaseModel):
    goal: str


@router.put("/api/admin/provenienz/sessions/{session_id}/claims/{claim_id}/goal")
async def set_claim_goal(
    session_id: str, claim_id: str, body: SetClaimGoalRequest, request: Request
) -> dict:
    """Manual override for a single claim's research goal. Per-claim goals
    are auto-extracted at /decide time; this route lets the user refine
    them after the fact. Updates are written as a *new* claim Node with a
    tombstone on the previous one — keeps the audit trail honest while
    letting the canvas show the latest version.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    nodes, _ = read_session(sd)
    claim = next((n for n in nodes if n.node_id == claim_id), None)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"claim not found: {claim_id}")
    if claim.kind != "claim":
        raise HTTPException(status_code=400, detail=f"node is not a claim: kind={claim.kind}")
    new_payload = {**claim.payload, "goal": body.goal.strip()[:300]}
    # Patch in place via tombstone+respawn would shuffle node_ids and break
    # references; simpler is to keep the node_id stable and just append a
    # synthetic "goal_update" event. For v1 we mutate the payload by writing
    # a new node with the same node_id (events.jsonl is read-replay; the
    # later record wins because read_session iterates in order).
    updated = Node(
        node_id=claim.node_id,
        session_id=claim.session_id,
        kind="claim",
        payload=new_payload,
        actor="human",
        created_at=claim.created_at,  # preserved
    )
    append_node(sd, updated)
    return updated.__dict__


@router.delete("/api/admin/provenienz/sessions/{session_id}/nodes/{node_id}", status_code=204)
async def delete_node(session_id: str, node_id: str, request: Request) -> None:
    """Soft-delete a node *and every node that depends on it*. Tombstones
    are appended to events.jsonl one line per cascaded node — the Node
    events themselves stay intact for audit; subsequent ``read_session``
    calls hide all tombstoned nodes plus any edge touching them.

    Cascade rules: claims under a chunk go with it, tasks under a claim,
    search_results under a task, evaluations of those results, chunks
    promoted from those results (and *their* whole subtree), plus any
    proposals/decisions/stop_proposals anchored to the deleted set.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    nodes, edges = read_session(sd)
    if not any(n.node_id == node_id for n in nodes):
        raise HTTPException(status_code=404, detail=f"node not found: {node_id}")
    for nid in _collect_cascade(node_id, nodes, edges):
        append_tombstone(sd, nid)


class PromoteSearchResultRequest(BaseModel):
    search_result_node_id: str


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/promote-search-result",
    status_code=201,
)
async def promote_search_result(
    session_id: str, body: PromoteSearchResultRequest, request: Request
) -> dict:
    """Create a new chunk node seeded with a search_result's text, so the
    user can extract claims and dig deeper from that specific result.

    The new chunk inherits **breadcrumbs** from its origin: the claim that
    triggered the search, the search query, and the source chunk. Stored
    on the chunk payload so the frontend can render context, and so a
    later ``extract_claims`` call on this chunk can inject those
    breadcrumbs into the LLM prompt — keeping the recursive exploration
    on-topic instead of producing arbitrary claims about the result text.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    nodes, edges = read_session(sd)
    sr = next((n for n in nodes if n.node_id == body.search_result_node_id), None)
    if sr is None:
        raise HTTPException(
            status_code=404, detail=f"search_result not found: {body.search_result_node_id}"
        )
    if sr.kind != "search_result":
        raise HTTPException(status_code=400, detail=f"node is not a search_result: kind={sr.kind}")

    # Walk back: search_result → task → claim → original chunk.
    by_id = {n.node_id: n for n in nodes}
    task_id = sr.payload.get("task_node_id")
    task = by_id.get(task_id) if isinstance(task_id, str) else None
    claim_id = task.payload.get("focus_claim_id") if task else None
    claim = by_id.get(claim_id) if isinstance(claim_id, str) else None
    origin_chunk_id: str | None = None
    if claim:
        for e in edges:
            if e.from_node == claim.node_id and e.kind == "extracts-from":
                origin_chunk_id = e.to_node
                break
    origin_chunk = by_id.get(origin_chunk_id) if origin_chunk_id else None

    text = str(sr.payload.get("text", ""))
    box_id = str(sr.payload.get("box_id", ""))
    doc_slug = str(sr.payload.get("doc_slug", ""))
    chunk = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=session_id,
            kind="chunk",
            payload={
                "box_id": box_id,
                "doc_slug": doc_slug,
                "text": text,
                "promoted_from": sr.node_id,
                "origin_claim_id": claim.node_id if claim else None,
                "origin_claim_text": str(claim.payload.get("text", "")) if claim else None,
                "origin_query": str(task.payload.get("query", "")) if task else None,
                "origin_chunk_id": origin_chunk.node_id if origin_chunk else None,
                "origin_chunk_box_id": (
                    str(origin_chunk.payload.get("box_id", "")) if origin_chunk else None
                ),
            },
            actor="human",
        ),
    )
    append_edge(
        sd,
        Edge(
            edge_id=new_id(),
            session_id=session_id,
            from_node=chunk.node_id,
            to_node=sr.node_id,
            kind="promoted-from",
            reason=None,
            actor="human",
        ),
    )
    return chunk.__dict__


def _build_decision_context(
    claim: Node,
    nodes: list[Node],
    meta: SessionMeta | None = None,
    *,
    task: Node | None = None,
    max_chunk_chars: int = 1500,
) -> str:
    """Render the decision-support bundle (Ziel + Recherche-Frage +
    Quell-Chunk + Such-Aufgabe) as a system-prompt prefix.

    Used by formulate_task, evaluate, re-evaluate. Each part is omitted
    when not available, so caller doesn't need to branch.

    Args:
        claim: the claim node — source for chunk-lookup + per-claim goal.
        nodes: full session node list, for chunk resolution.
        meta: session meta, for the session goal. Optional.
        task: the task node, for the search query. Pass for evaluate /
            re-evaluate; omit for formulate_task (task doesn't exist
            yet at that point).
        max_chunk_chars: cap on the inlined chunk text (chunks can be
            multi-page). Truncated with " […]" suffix.
    """
    parts: list[str] = []

    if meta and meta.goal and meta.goal.strip():
        parts.append(f"## SITZUNGS-ZIEL\n{meta.goal.strip()}")

    claim_goal = str(claim.payload.get("goal", "")).strip()
    if claim_goal:
        parts.append(f"## RECHERCHE-FRAGE ZUR AUSSAGE\n{claim_goal}")

    src_id = claim.payload.get("source_node_id")
    if isinstance(src_id, str) and src_id:
        chunk = next((n for n in nodes if n.node_id == src_id), None)
        if chunk is not None and chunk.kind == "chunk":
            chunk_text = str(chunk.payload.get("text", "")).strip()
            claim_text = str(claim.payload.get("text", "")).strip()
            if chunk_text and chunk_text != claim_text:
                truncated = chunk_text[:max_chunk_chars]
                if len(chunk_text) > max_chunk_chars:
                    truncated += " […]"
                parts.append(
                    "## QUELL-KONTEXT (Original-Textabschnitt der Aussage)\n"
                    f"{truncated}\n\n"
                    "Diese Aussage wurde aus obigem Textabschnitt extrahiert. "
                    "Nutze den Kontext nur, um Thema, Einheiten und Bezüge "
                    "korrekt einzuordnen — er ist nicht selbst Gegenstand der "
                    "Auswertung."
                )

    # Per-claim background — chunk-comprehension Nodes attached via
    # `enriches` edge. Latest one wins (claims can have backgrounds
    # re-extracted manually later).
    background_nodes = [
        n
        for n in nodes
        if n.kind == "claim_background" and n.payload.get("claim_node_id") == claim.node_id
    ]
    if background_nodes:
        latest_bg = max(background_nodes, key=lambda n: n.created_at)
        bg_text = str(latest_bg.payload.get("text", "")).strip()
        if bg_text:
            parts.append(f"## AUSSAGE-HINTERGRUND (aus Chunk extrahiert)\n{bg_text}")

    if task is not None and task.kind == "task":
        task_text = str(task.payload.get("query") or task.payload.get("text") or "").strip()
        if task_text:
            parts.append(
                f"## SUCH-AUFGABE (Suchanfrage, die zu diesem Ergebnis führte)\n{task_text}"
            )

    if not parts:
        return ""
    return "\n\n" + "\n\n".join(parts) + "\n"


# Backwards-compat alias — older call sites used the chunk-only helper.
def _build_claim_source_context(claim: Node, nodes: list[Node]) -> str:
    return _build_decision_context(claim, nodes, meta=None, task=None)


def _build_origin_context(chunk: Node) -> str:
    """Render the breadcrumbs stored on a promoted chunk's payload as a
    German prompt-prefix the next ``extract_claims`` LLM call can use to
    stay on-topic. Empty string for chunks that weren't promoted.
    """
    p = chunk.payload
    if not p.get("promoted_from"):
        return ""
    parts: list[str] = []
    origin_claim = p.get("origin_claim_text")
    if isinstance(origin_claim, str) and origin_claim.strip():
        parts.append(f'Ursprüngliche Aussage: "{origin_claim.strip()}"')
    origin_query = p.get("origin_query")
    if isinstance(origin_query, str) and origin_query.strip():
        parts.append(f'Damalige Suchanfrage: "{origin_query.strip()}"')
    if not parts:
        return ""
    return (
        "\n\n## Kontext der Recherche\n"
        "Dieser Textabschnitt wurde als möglicher Beleg für eine frühere "
        "Aussage in derselben Sitzung identifiziert. "
        + " · ".join(parts)
        + ".\nKonzentriere dich auf Aussagen, die zur ursprünglichen Recherche passen."
    )


class PinApproachRequest(BaseModel):
    approach_id: str


@router.post("/api/admin/provenienz/sessions/{session_id}/pin-approach")
async def pin_approach(session_id: str, body: PinApproachRequest, request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    pinned = list(meta.pinned_approach_ids)
    if body.approach_id not in pinned:
        pinned.append(body.approach_id)
    new_meta = SessionMeta(**{**meta.__dict__, "pinned_approach_ids": pinned})
    write_meta(sd, new_meta)
    written = read_meta(sd)
    assert written is not None
    return {"meta": _meta_to_response(written).model_dump()}


@router.post("/api/admin/provenienz/sessions/{session_id}/unpin-approach")
async def unpin_approach(session_id: str, body: PinApproachRequest, request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    pinned = [a for a in meta.pinned_approach_ids if a != body.approach_id]
    new_meta = SessionMeta(**{**meta.__dict__, "pinned_approach_ids": pinned})
    write_meta(sd, new_meta)
    written = read_meta(sd)
    assert written is not None
    return {"meta": _meta_to_response(written).model_dump()}


def _strip_thinking_tags(s: str) -> str:
    """Strip ``<think>...</think>`` reasoning blocks (Qwen3, DeepSeek-R1).

    Standalone helper for plain-text outputs (pre_reason etc.) that
    don't go through ``_strip_json_fence``. Empty thinking blocks
    (``<think>\\n\\n</think>``) leak into German one-liners when
    ``/no_think`` is honored partially.
    """
    import re as _re

    s = _re.sub(r"<think>.*?</think>", "", s, flags=_re.DOTALL)
    return s.strip()


def _strip_json_fence(s: str) -> str:
    """Strip ```json ... ``` fences, ``<think>...</think>`` reasoning
    blocks (Qwen3, DeepSeek-R1, etc.), and extract the first top-level
    JSON value (object or array) from prose-wrapped output.

    Small models routinely return ``Hier ist die Antwort: {...}`` or wrap
    JSON in code fences. Reasoning-tuned models like Qwen3 prepend
    ``<think>…</think>`` chain-of-thought before the JSON; we strip
    those so callers downstream get clean JSON.
    """
    s = s.strip()
    # Reasoning blocks (Qwen3, DeepSeek-R1) — close-tag may be missing
    # if the model truncated mid-thought, so handle both shapes.
    import re as _re

    s = _re.sub(r"<think>.*?</think>", "", s, flags=_re.DOTALL).strip()
    # If only an opening tag survived a truncation, drop everything up
    # to the first ``{`` / ``[`` so we still try to parse what's there.
    if s.startswith("<think>"):
        for marker in ("{", "["):
            idx = s.find(marker)
            if idx != -1:
                s = s[idx:]
                break
    s = s.strip()

    if s.startswith("```"):
        first_newline = s.find("\n")
        s = s[first_newline + 1 :] if first_newline != -1 else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    s = s.strip()

    # Already pure JSON? cheap path.
    if s.startswith("{") or s.startswith("["):
        return s

    # Otherwise scan for the first balanced JSON object or array.
    extracted = _extract_first_json_value(s)
    return extracted if extracted is not None else s


def _extract_first_json_value(s: str) -> str | None:
    """Return the first balanced ``{...}`` or ``[...]`` substring, or None.
    Tracks string literals so braces inside strings don't throw the count.
    """
    start = -1
    open_ch = ""
    for i, ch in enumerate(s):
        if ch == "{" or ch == "[":
            start = i
            open_ch = ch
            break
    if start < 0:
        return None
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


_EVALUATE_VERDICTS = {"likely-source", "partial-support", "unrelated", "contradicts"}


# ─────────────────────────────────────────────────────────────────────────────
# System prompts — single source of truth.
#
# Surfaced via /api/admin/provenienz/agent-info so the Agent tab can render
# the actual strings the LLM sees, instead of duplicating them in TypeScript.
# Edit here → both the live LLM call and the docs UI update.
# ─────────────────────────────────────────────────────────────────────────────

# Reasoning-tuned models (Qwen3, DeepSeek-R1) emit <think>...</think> chain-
# of-thought before their final answer. For our structured-JSON outputs that
# pollutes the parse and burns through max_tokens. ``/no_think`` is the
# Qwen3 directive that disables thinking-mode for a single call. Non-
# reasoning models silently ignore this token, so it's safe to append
# universally. Combined with the <think>-stripping in _strip_json_fence,
# we're robust whether the model honors the directive or not.
_NO_THINK = "\n\n/no_think"

# Output-token budget. Has to fit alongside the input prompt within the
# model's max_model_len. With max_model_len=4096 and our typical
# system+user prompts running 1500-2500 input tokens, 1024 leaves
# enough headroom for JSON output + small <think> block leakage.
# Default vLLM max_tokens can be as low as 16 which truncates anything
# non-trivial, so we always pass this explicitly.
_MAX_TOKENS_STRUCTURED = 1024

EXTRACT_CLAIMS_SYSTEM = (
    "Du extrahierst überprüfbare Aussagen aus einem Textabschnitt. Eine Aussage "
    "ist eine spezifische, faktische Behauptung — Zahl, Datum, Eigenschaft, "
    "Beziehung. Antworte ausschließlich als JSON-Array von Strings, ohne Vor- "
    "oder Nachtext. Keine Aufzählungen, keine Markdown-Codeblöcke."
)
FORMULATE_TASK_SYSTEM = (
    "Du formulierst eine knappe Suchanfrage (max. 12 Wörter, deutsch oder "
    "englisch je nach Claim-Sprache), mit der die Quelle einer Aussage in "
    "einem Korpus gefunden werden kann. Antworte ausschließlich mit der "
    "Suchanfrage selbst — keine Anführungszeichen, keine Erklärung, kein "
    "Zeilenumbruch davor oder danach."
)
EVALUATE_SYSTEM = (
    "Du bewertest, ob ein Kandidaten-Textabschnitt die Quelle einer "
    "Aussage ist.\n\n"
    "ARBEITSWEISE - strikt einhalten:\n"
    "1. Lies den Kandidaten-Text VOLLSTÄNDIG.\n"
    "2. Liste JEDEN selbständigen Satz / jede Aussage einzeln auf.\n"
    "3. Pro Satz markiere: STÜTZT / WIDERSPRICHT / NICHT-RELEVANT "
    "für die zu prüfende Behauptung.\n"
    "4. Sätze mit Zahlen, Datumsangaben, technischen Werten, "
    "Einheiten oder Eigennamen sind IMMER potentiell relevant — "
    "beweise das Gegenteil bevor du sie als nicht-relevant markierst.\n"
    "5. Erst NACH dieser per-Satz-Aufstellung gib das Gesamt-Verdict.\n\n"
    "Antworte AUSSCHLIESSLICH als JSON-Objekt:\n"
    "{\n"
    '  "sentences": [\n'
    '    {"text": <wörtlicher Satz>, "tag": "STÜTZT" | "WIDERSPRICHT" '
    '| "NICHT-RELEVANT", "why": <kurzer deutscher Grund>}\n'
    "  ],\n"
    '  "verdict": "likely-source" | "partial-support" | "unrelated" '
    '| "contradicts",\n'
    '  "confidence": <0.0-1.0>,\n'
    '  "reasoning": <Gesamtfazit als deutscher Satz, der die '
    "sentences-Liste zusammenfasst>\n"
    "}\n\n"
    "Kein Vor- oder Nachtext, keine Codeblöcke."
)
DECOMPOSE_HIT_SYSTEM = (
    "Du zerlegst einen Suchtreffer-Text in atomare Sub-Aussagen, "
    "damit jede einzeln auf Stützung der Original-Behauptung "
    "geprüft werden kann.\n\n"
    "REGELN:\n"
    "1. Eine Sub-Aussage = EINE faktische Behauptung (genau eine Zahl, "
    "ein Datum, eine Eigenschaft, eine Beziehung).\n"
    "2. Splitte an natürlichen Satz- und Klausel-Grenzen — keine "
    "willkürliche Wort-Aufteilung.\n"
    "3. Inkludiere Sätze mit Zahlen, Datumsangaben, technischen "
    "Werten — diese sind oft die wichtigsten.\n"
    "4. Verneine NIEMALS — gib die Aussage so wieder wie sie im Text "
    "steht.\n\n"
    "Antworte ausschließlich als JSON-Array von Strings, jeder String "
    "ist eine Sub-Aussage. Kein Vor- oder Nachtext, keine Codeblöcke."
)
REFLECT_EVALUATE_SYSTEM = (
    "Du prüfst eine bereits abgegebene Bewertung eines Suchtreffers "
    "auf Vollständigkeit. Du bekommst:\n"
    "1. Die zu prüfende Behauptung (claim)\n"
    "2. Den vollständigen Treffer-Text (kandidat)\n"
    "3. Das bisherige verdict + reasoning + die per-Satz-Tagging-Liste\n\n"
    "Aufgabe: kritisiere die bestehende Bewertung. Hat das Modell:\n"
    "- JEDEN Satz im Treffer-Text addressiert (per-Satz-Liste vollständig)?\n"
    "- Sätze mit Zahlen, Datumsangaben, technischen Werten richtig getagt?\n"
    "- Sätze als NICHT-RELEVANT markiert obwohl sie eigentlich stützen "
    "oder widersprechen?\n"
    "- Das verdict konsistent mit der per-Satz-Tagging-Liste vergeben?\n\n"
    "Antworte AUSSCHLIESSLICH als JSON-Objekt:\n"
    "{\n"
    '  "self_assessment": "vollständig" | "lückenhaft" | "fehlerhaft",\n'
    '  "missed_statements": [<wörtliche Sätze die übersehen / falsch '
    "getagt wurden>],\n"
    '  "concerns": [<deutsche Sätze: WAS genau ist die Lücke / der '
    "Fehler>],\n"
    '  "recommendation": "accept" | "re-evaluate" | "expand-context",\n'
    '  "recommended_focus": <wenn re-evaluate: deutscher Satz mit dem '
    "Fokus für den nächsten Lauf, sonst leer>\n"
    "}\n\n"
    "Kein Vor- oder Nachtext, keine Codeblöcke."
)
PROPOSE_STOP_SYSTEM = (
    "Du formulierst einen kurzen deutschen Satz (max. 25 Wörter), warum "
    "die Recherche zu einer Aussage abgeschlossen werden kann (Quelle "
    "gefunden, mehrfach bestätigt, oder Sackgasse). Antworte ausschließlich "
    "mit dem Satz selbst, ohne Anführungszeichen oder Markdown."
)
EXTRACT_GOAL_SYSTEM = (
    "Du formulierst das übergeordnete Recherche-Ziel einer Sitzung als "
    "kurzen deutschen Satz (max. 20 Wörter). Eine Sitzung beginnt mit "
    "einem Textabschnitt und einer ersten überprüfbaren Aussage daraus. "
    "Das Ziel beschreibt, was die Recherche herausfinden oder belegen "
    "will — eher Frage als Vermutung. Antworte ausschließlich mit dem "
    "Satz selbst, keine Anführungszeichen, kein Vor- oder Nachtext, "
    "kein Markdown."
)
EXTRACT_CLAIM_GOALS_SYSTEM = (
    "Du formulierst pro Aussage ein spezifisches Recherche-Ziel als "
    "kurze deutsche Frage (max. 20 Wörter pro Frage). Jede Frage "
    "beschreibt, was konkret nachgewiesen werden muss — Zahl, Datum, "
    "technische Spezifikation, Beziehung. Aussagen sind unabhängig "
    "voneinander, jede Aussage bekommt ihre eigene Frage. Antworte "
    "ausschließlich als JSON-Array von Strings (selbe Länge wie "
    "Input), kein Vor- oder Nachtext, kein Markdown, keine Codeblöcke."
)
EXTRACT_CLAIM_BACKGROUND_SYSTEM = (
    "Du extrahierst pro Aussage den IMPLIZITEN Hintergrund aus dem "
    "Quell-Textabschnitt. Ziel: was steht im Chunk, das die Aussage "
    "kontextualisiert (Bezugsgrößen, Voraussetzungen, definierende "
    "Begriffe, Zeitpunkte, Standortinformationen, Einheitensystem) — "
    "und das in der Aussage selbst NICHT explizit steht? Diese "
    "Hintergrund-Information wird später in die Recherche-Aufgabe + "
    "Bewertung eingespeist, damit Suche und Quellen-Vergleich nicht "
    "generisch werden. Antworte pro Aussage in 2-4 deutschen Sätzen, "
    "knapp und faktisch, ohne Spekulation. Wenn der Chunk KEINEN "
    "weiterführenden Kontext zur Aussage liefert, gib einen leeren "
    "String zurück. Antworte ausschließlich als JSON-Array von "
    "Strings (selbe Länge wie Input), kein Vor- oder Nachtext, kein "
    "Markdown, keine Codeblöcke."
)
PRE_REASON_SYSTEM = (
    "Du bist die reflektierende Schicht eines Recherche-Agenten. Vor "
    "jeder Aktion erklärst du in EINEM kurzen deutschen Satz (max. "
    "30 Wörter), was diese Aktion zum Recherche-Ziel beiträgt — warum "
    "sie jetzt für DIESEN Knoten sinnvoll ist. Beziehe dich konkret "
    "auf den Knoten und das Ziel. Antworte ausschließlich mit dem "
    "Satz selbst, keine Anführungszeichen, kein Vor- oder Nachtext, "
    "kein Markdown."
)
NEXT_STEP_SYSTEM = (
    "Du bist der reflektierende Teil eines Recherche-Agenten. Du bekommst "
    "einen Knoten + Sitzungs-Ziel + Liste der verfügbaren Steps + Liste "
    "der verfügbaren Tools (mit Agent-Hinweisen wann welches Tool zu "
    "wählen ist). Wähle den nächsten Schritt — ABER nur wenn ein "
    "registrierter Step wirklich passt. Wenn kein Step + kein Tool "
    "ausreicht, darfst du auch ehrlich sagen: 'wir bräuchten X, das "
    "fehlt' (capability_request) oder 'das ist Mensch-Arbeit' "
    "(manual_review).\n\n"
    "Antworte AUSSCHLIESSLICH als JSON-Objekt:\n"
    "{\n"
    '  "kind": "executable_step" | "capability_request" | "manual_review",\n'
    '  "name": <siehe unten>,\n'
    '  "description": <bei capability_request/manual_review: was fehlt / '
    "warum Mensch — deutscher Satz>,\n"
    '  "reasoning": <warum diese Wahl jetzt — deutscher Satz>,\n'
    '  "goal_alignment": <Pflicht: zitiere das Sitzungs-Ziel wörtlich und '
    "erkläre konkret, wie der gewählte Step diesem Ziel näher bringt. "
    "Beispiel: \"Ziel ist 'Worauf beruhen die Aussagen?'. extract_claims "
    "teilt den Text in einzelne Behauptungen, damit ich für jede die "
    'Quelle suchen kann." Schreibe vollständige Sätze ohne Platzhalter '
    "(< >). Wenn kein Sitzungs-Ziel gesetzt ist: leerer String.>,\n"
    '  "considered_alternatives": [\n'
    '    {"name": <name>, "kind": <kind>, "why_not": <Grund>}\n'
    "  ],\n"
    '  "confidence": <0.0-1.0>,\n'
    '  "tool": <Tool-Name oder null>,\n'
    '  "approach_id": <Approach-Name oder null>\n'
    "}\n\n"
    "Kein Vor- oder Nachtext, keine Codeblöcke.\n\n"
    "REGELN für name:\n"
    "- executable_step → name = Step-Name aus der verfügbaren Liste "
    "(extract_claims, formulate_task, search, evaluate, propose_stop, "
    "promote_search_result).\n"
    "- capability_request → name = exakter Tool-Name aus dem Tool-Registry "
    "wenn ein deaktivierter Tool-Stub zur Lücke passt (z.B. "
    "'CrossDocSearcher', 'SemanticSearcher', 'NumericExtractor'). NICHT "
    "vage Begriffe wie 'search' oder 'parse' — sondern der spezifische "
    "Tool-Name. Wenn KEINES der Stubs passt, erfinde eine kurze "
    "PascalCase-Bezeichnung (z.B. 'TableParser') + erkläre in description "
    "was es können müsste.\n"
    "- manual_review → name = kurze Bezeichnung der Mensch-Aufgabe "
    "(z.B. 'Juristische Bewertung', 'Domain-Expertise erforderlich')."
)
PLAN_SYSTEM = (
    "Du bist der Planer eines Recherche-Agenten. Eingabe: ein Ziel, "
    "der aktuelle Sitzungs-Zustand (Knoten + offene Fronten), die "
    "verfügbaren Schritte mit ihren Tools, und die Approach-Bibliothek. "
    "Du wählst den nächsten sinnvollen Schritt.\n\n"
    "Ausgabe AUSSCHLIESSLICH als JSON-Objekt mit Feldern: next_step "
    "(eines von: extract_claims, formulate_task, search, evaluate, "
    "propose_stop, promote_search_result, stop), target_anchor_id "
    "(node_id auf den sich der Schritt bezieht; bei stop leer), tool "
    "(Tool-Name oder null), approach_id (Approach-Name oder null), "
    "reasoning (deutscher Satz: warum dieser Schritt jetzt), "
    "expected_outcome (was vom Schritt erwartet wird), confidence "
    "(0.0-1.0), fallback_plan (Plan B wenn der Schritt scheitert; "
    "leerer String wenn nicht relevant). Kein Vor- oder Nachtext, "
    "kein Markdown. Bevorzuge offene Fronten mit hoher erwarteter "
    "Informationsausbeute. Wähle stop wenn Ziel erreicht oder alle "
    "Fronten ausgeschöpft."
)


def _format_reason_examples(reasons: list[Reason]) -> str:
    """Render a list of past overrides as a German-language in-context
    examples block. Empty list → empty string (no block at all)."""
    if not reasons:
        return ""
    lines = ["", "## Frühere Korrekturen durch den Nutzer"]
    for r in reasons:
        lines.append(
            f"- Empfehlung: {r.proposal_summary}\n"
            f"  Korrektur:  {r.override_summary}\n"
            f"  Grund:      {r.reason_text}"
        )
    lines.append("Berücksichtige diese Korrekturen, wenn sie auf die aktuelle Aufgabe zutreffen.")
    return "\n".join(lines)


def _gather_reason_guidance(
    data_root: Path, step_kind: str, last_n: int = 5
) -> tuple[str, list[GuidanceRef]]:
    """Fetch up to *last_n* reasons matching *step_kind* and return
    ``(extra_system_block, guidance_refs)``."""
    reasons = read_reasons(data_root, step_kind=step_kind, last_n=last_n)
    block = _format_reason_examples(reasons)
    refs = [
        GuidanceRef(
            kind="reason",
            id=r.reason_id,
            summary=(r.reason_text or "")[:80],
        )
        for r in reasons
    ]
    return block, refs


def _walk_approaches(
    data_root: Path,
    meta: SessionMeta,
    step_kind: str,
    *,
    anchor: Node | None,
) -> tuple[list[tuple[Approach, GuidanceRef]], list[tuple[Approach, GuidanceRef]]]:
    """Walk pinned + auto-selected approaches and partition them by
    ``mode`` (``passive`` vs ``active``).

    Returns ``(passive_with_refs, active_with_refs)``. Each tuple
    bundles the Approach (so the caller has ``extra_system`` available
    for prompt-injection or active-skill calls) with its matching
    GuidanceRef (auto-vs-pinned + match reasons captured for audit).

    Both lists share the same ordering: pinned-first, auto-second.
    """
    passive: list[tuple[Approach, GuidanceRef]] = []
    active: list[tuple[Approach, GuidanceRef]] = []
    seen_ids: set[str] = set()

    def _push(a: Approach, ref: GuidanceRef) -> None:
        if a.approach_id in seen_ids:
            return
        seen_ids.add(a.approach_id)
        target = active if a.mode == "active" else passive
        target.append((a, ref))

    for app_id in meta.pinned_approach_ids:
        a = get_approach(data_root, app_id)
        if a is None or not a.enabled:
            continue
        if step_kind not in a.step_kinds:
            continue
        _push(
            a,
            GuidanceRef(
                kind="approach",
                id=a.approach_id,
                summary=a.name[:80],
                auto_selected=False,
            ),
        )

    if anchor is not None:
        candidates = [
            a
            for a in read_approaches(data_root, step_kind=step_kind, enabled_only=True)
            if a.approach_id not in seen_ids
        ]
        anchor_text = str(anchor.payload.get("text", "")) or str(anchor.payload.get("query", ""))
        for a, match_reasons in auto_select_approaches(
            candidates,
            anchor_kind=anchor.kind,
            anchor_text=anchor_text,
            goal=meta.goal,
        ):
            _push(
                a,
                GuidanceRef(
                    kind="approach",
                    id=a.approach_id,
                    summary=a.name[:80],
                    auto_selected=True,
                    selection_reasons=match_reasons,
                ),
            )

    return passive, active


def _build_passive_block(passive: list[tuple[Approach, GuidanceRef]]) -> str:
    """Concat passive approaches into the system-prompt overlay block."""
    if not passive:
        return ""
    parts = [f"## Vorgehen: {a.name}\n{a.extra_system}" for a, _ in passive]
    return "\n\n" + "\n\n".join(parts)


def _gather_guidance_via_skills(
    data_root: Path,
    meta: SessionMeta | None,
    step_kind: str,
    *,
    anchor: Node | None = None,
) -> tuple[str, list[GuidanceRef]]:
    """Skills-backed replacement for the legacy ``_gather_guidance``.

    Returns the same ``(extra_system, refs)`` tuple shape so callers do
    not need to change. References point to ``skill_id``\\ s now — the
    unified ``skills.jsonl`` storage replaces the approaches+reasons
    split. Active/sub-agent skills are deliberately **not** mixed into
    the passive overlay text (they fire via the multi-agent pipeline in
    :func:`_gather_guidance_split`).
    """
    from local_pdf.provenienz.skill_dispatcher import apply_skills

    bundle = apply_skills(
        data_root,
        step_kind=step_kind,
        anchor=anchor,
        session_goal=meta.goal if meta else "",
    )
    text = bundle.extra_system
    if bundle.notes:
        text += "\n\n## Lehr-Notizen\n" + "\n".join(f"- {n}" for n in bundle.notes)
    refs = [
        GuidanceRef(kind="skill", id=sid, summary="")  # type: ignore[arg-type]
        for sid in bundle.consulted_skill_ids
    ]
    return text, refs


def _gather_guidance_split(
    data_root: Path,
    meta: SessionMeta,
    step_kind: str,
    *,
    anchor: Node | None,
) -> tuple[str, list[tuple[Approach, GuidanceRef]], list[GuidanceRef]]:
    """Phase-3 multi-agent variant.

    Returns ``(passive_extra_system, active_with_refs, all_refs)``:

    - ``passive_extra_system``: legacy text block (passive approaches +
      reason corpus) for direct prompt injection into the Meta-Planer.
    - ``active_with_refs``: list of (Approach, GuidanceRef) for every
      ``mode=active`` approach that matched. The pipeline fires each
      via :func:`_llm_active_skill`.
    - ``all_refs``: union of passive + active + reason refs for the
      audit / live-run UI.
    """
    passive, active = _walk_approaches(data_root, meta, step_kind, anchor=anchor)
    blocks: list[str] = []
    extra = _build_passive_block(passive)
    if extra:
        blocks.append(extra)
    refs: list[GuidanceRef] = [ref for _a, ref in passive]
    refs.extend(ref for _a, ref in active)
    reason_block, reason_refs = _gather_reason_guidance(data_root, step_kind)
    if reason_block:
        blocks.append(reason_block)
        refs.extend(reason_refs)
    return ("".join(blocks), active, refs)


def _llm_extract_claims(chunk_text: str, provider: str, *, extra_system: str = "") -> list[str]:
    """Extract verifiable claims from a chunk via the configured LLM.

    The ``provider`` arg is plumbed-through but unused today — per-step
    provider routing lands in Stage 6 with the reason corpus. Tests
    monkey-patch this symbol on the module.
    """
    del provider  # reserved for Stage 6 routing
    system = EXTRACT_CLAIMS_SYSTEM + (extra_system or "") + _NO_THINK
    user = f"Textabschnitt:\n{chunk_text}\n\nGib das JSON-Array der Aussagen zurück."
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
        max_tokens=_MAX_TOKENS_STRUCTURED,
    )
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"_llm_extract_claims: could not parse LLM response: {raw[:500]}"
        ) from exc
    if not isinstance(parsed, list) or not all(isinstance(c, str) and c.strip() for c in parsed):
        raise RuntimeError(f"_llm_extract_claims: could not parse LLM response: {raw[:500]}")
    return [c.strip() for c in parsed]


class ExtractClaimsRequest(BaseModel):
    chunk_node_id: str
    provider: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/extract-claims",
    status_code=201,
)
async def extract_claims(session_id: str, body: ExtractClaimsRequest, request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")

    nodes, _ = read_session(sd)
    chunk = next((n for n in nodes if n.node_id == body.chunk_node_id), None)
    if chunk is None:
        raise HTTPException(
            status_code=404,
            detail=f"chunk node not found: {body.chunk_node_id}",
        )
    if chunk.kind != "chunk":
        raise HTTPException(
            status_code=400,
            detail=f"anchor must be a chunk node, got kind={chunk.kind}",
        )

    actor = resolve_provider(body.provider)
    extra_system, guidance_refs = _gather_guidance_via_skills(cfg.data_root, meta, "extract_claims")
    # Promoted chunks carry breadcrumbs back to the original claim/query;
    # prepend them so the LLM stays on-topic for the recursive exploration.
    origin_context = _build_origin_context(chunk)
    if origin_context:
        extra_system = origin_context + extra_system
    # ReAct Thought: why this step now? Best-effort, never blocks the action.
    pre_reasoning = _llm_pre_reason(
        step_kind="extract_claims",
        step_label="Aussagen extrahieren",
        anchor_summary=str(chunk.payload.get("text", "")),
        session_goal=meta.goal,
        claim_goal="",
    )
    full_system = EXTRACT_CLAIMS_SYSTEM + (extra_system or "") + _NO_THINK
    try:
        claims = _llm_extract_claims(
            chunk.payload.get("text", ""),
            body.provider or "vllm",
            extra_system=extra_system,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM-Fehler: {exc}") from exc

    payload = ActionProposalPayload(
        step_kind="extract_claims",
        anchor_node_id=body.chunk_node_id,
        recommended=ActionOption(
            label=f"Akzeptiere {len(claims)} Aussage(n)",
            args={"claims": claims},
        ),
        alternatives=[
            ActionOption(
                label="Überspringen — keine prüfbaren Aussagen",
                args={"claims": []},
            )
        ],
        reasoning="Heuristik v0: Sätze ≥ 8 Zeichen aus dem Chunk-Text.",
        guidance_consulted=guidance_refs,
        pre_reasoning=pre_reasoning,
        system_prompt_used=full_system,
        tool_used=None,
    )
    node = build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    landed = append_node(sd, node)
    return landed.__dict__


def _llm_formulate_task(claim_text: str, provider: str, *, extra_system: str = "") -> str:
    """Build a short search query for the claim via the configured LLM.

    The ``provider`` arg is plumbed-through but unused today. Tests
    monkey-patch this symbol on the module.
    """
    del provider  # reserved for Stage 6 routing
    system = FORMULATE_TASK_SYSTEM + (extra_system or "") + _NO_THINK
    user = f"Aussage: {claim_text}\nSuchanfrage:"
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
        max_tokens=_MAX_TOKENS_STRUCTURED,
    )
    raw = (completion.text or "").strip()
    # strip outer matching single/double quotes if present
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        raw = raw[1:-1].strip()
    raw = raw[:200]
    if not raw:
        raise RuntimeError("_llm_formulate_task: empty response from LLM")
    return raw


class FormulateTaskRequest(BaseModel):
    claim_node_id: str
    provider: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/formulate-task",
    status_code=201,
)
async def formulate_task(session_id: str, body: FormulateTaskRequest, request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")

    nodes, _ = read_session(sd)
    claim = next((n for n in nodes if n.node_id == body.claim_node_id), None)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"claim node not found: {body.claim_node_id}")
    if claim.kind != "claim":
        raise HTTPException(status_code=400, detail=f"anchor must be claim, got kind={claim.kind}")

    actor = resolve_provider(body.provider)
    extra_system, guidance_refs = _gather_guidance_via_skills(cfg.data_root, meta, "formulate_task")
    # Prepend session-goal + per-claim research-question + source-chunk
    # so the LLM can form a search query that's targeted, not generic.
    extra_system = _build_decision_context(claim, nodes, meta) + extra_system
    pre_reasoning = _llm_pre_reason(
        step_kind="formulate_task",
        step_label="Aufgabe formulieren",
        anchor_summary=str(claim.payload.get("text", "")),
        session_goal=meta.goal,
        claim_goal=str(claim.payload.get("goal", "")),
    )
    full_system = FORMULATE_TASK_SYSTEM + (extra_system or "") + _NO_THINK
    try:
        query = _llm_formulate_task(
            claim.payload.get("text", ""),
            body.provider or "vllm",
            extra_system=extra_system,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM-Fehler: {exc}") from exc
    payload = ActionProposalPayload(
        step_kind="formulate_task",
        anchor_node_id=body.claim_node_id,
        recommended=ActionOption(label=f"Suchanfrage: {query!r}", args={"query": query}),
        alternatives=[
            ActionOption(label="Eigene Suchanfrage formulieren", args={"query": ""}),
        ],
        reasoning="Heuristik v0: Claim-Text als Suchanfrage.",
        guidance_consulted=guidance_refs,
        pre_reasoning=pre_reasoning,
        system_prompt_used=full_system,
        tool_used=None,
    )
    landed = append_node(
        sd, build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    )
    return landed.__dict__


class SearchStepRequest(BaseModel):
    task_node_id: str
    top_k: int = 5


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/search",
    status_code=201,
)
async def search_step(session_id: str, body: SearchStepRequest, request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    nodes, _ = read_session(sd)
    task = next((n for n in nodes if n.node_id == body.task_node_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task node not found: {body.task_node_id}")
    if task.kind != "task":
        raise HTTPException(status_code=400, detail=f"anchor must be task, got kind={task.kind}")

    query = task.payload.get("query", "")
    actor = "system"  # this step doesn't call an LLM in v1
    searcher = InDocSearcher(
        data_root=cfg.data_root,
        slug=meta.slug,
        exclude_box_ids=(meta.root_chunk_id,),
    )
    hits = searcher.search(query, top_k=body.top_k)
    hits_payload = [
        {
            "box_id": h.box_id,
            "text": h.text,
            "score": h.score,
            "doc_slug": h.doc_slug,
            "searcher": h.searcher,
        }
        for h in hits
    ]
    top1 = hits_payload[:1]
    payload = ActionProposalPayload(
        step_kind="search",
        anchor_node_id=body.task_node_id,
        recommended=ActionOption(
            label=f"{len(hits_payload)} Treffer übernehmen",
            args={"hits": hits_payload},
        ),
        alternatives=[
            ActionOption(label="Nur Top-1 übernehmen", args={"hits": top1}),
        ],
        reasoning=(
            f"InDocSearcher BM25, exclude root_chunk={meta.root_chunk_id}, "
            f"top_k={body.top_k}, hits={len(hits_payload)}"
        ),
        guidance_consulted=[],
    )
    landed = append_node(
        sd, build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    )
    return landed.__dict__


def _llm_evaluate(
    claim_text: str,
    candidate_chunk_text: str,
    provider: str,
    *,
    extra_system: str = "",
) -> dict:
    """Ask the LLM whether a candidate chunk is the source of a claim.

    Returns a dict with ``verdict`` (constrained set), ``confidence``
    (float 0..1) and ``reasoning`` (short German sentence). The
    ``provider`` arg is plumbed-through but unused today. Tests
    monkey-patch this symbol on the module.
    """
    del provider  # reserved for Stage 6 routing
    system = EVALUATE_SYSTEM + (extra_system or "") + _NO_THINK
    user = f"Aussage:\n{claim_text}\n\nKandidat:\n{candidate_chunk_text}\n\nJSON:"
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
        max_tokens=_MAX_TOKENS_STRUCTURED,
    )
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    parsed: object | None = None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = None

    # Coerce many model-output shapes into our expected fields.
    # Degrades gracefully — never raises — so the side-panel always shows
    # *something*, even if the LLM was creative. Frontend handles unknown
    # verdicts by falling back to the neutral chip color.
    verdict = "unknown"
    confidence = 0.0
    reasoning = f"LLM-Antwort konnte nicht interpretiert werden: {raw[:200]}"
    sentences: list[dict] = []

    if isinstance(parsed, dict):
        v = parsed.get("verdict")
        c = parsed.get("confidence")
        r = parsed.get("reasoning")
        s = parsed.get("sentences")
        if isinstance(v, str) and v.strip():
            verdict = v.strip()
        if isinstance(c, (int, float)) and 0.0 <= float(c) <= 1.0:
            confidence = float(c)
        if isinstance(r, str) and r.strip():
            reasoning = r.strip()
        # Per-sentence enumeration. Tolerant: accept any list of dicts
        # with at least a text or tag field. Drops malformed entries.
        if isinstance(s, list):
            for item in s:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text", "") or "").strip()
                tag = str(item.get("tag", "") or "").strip().upper()
                why = str(item.get("why", "") or "").strip()
                if text or tag:
                    sentences.append({"text": text, "tag": tag, "why": why})
    elif isinstance(parsed, list) and len(parsed) >= 1:
        # Positional fallback: [verdict, confidence, reasoning]
        if isinstance(parsed[0], str) and parsed[0].strip():
            verdict = parsed[0].strip()
        if (
            len(parsed) >= 2
            and isinstance(parsed[1], (int, float))
            and 0.0 <= float(parsed[1]) <= 1.0
        ):
            confidence = float(parsed[1])
        if len(parsed) >= 3 and isinstance(parsed[2], str) and parsed[2].strip():
            reasoning = parsed[2].strip()

    return {
        "verdict": verdict,
        "confidence": float(confidence),
        "reasoning": reasoning,
        "sentences": sentences,
    }


def _llm_reflect_evaluate(
    *,
    claim_text: str,
    candidate_text: str,
    prior_verdict: str,
    prior_reasoning: str,
    prior_sentences: list[dict],
    extra_system: str = "",
) -> dict:
    """Self-critique an existing evaluate-style action_proposal.

    Returns a dict with ``self_assessment``, ``missed_statements``,
    ``concerns``, ``recommendation``, ``recommended_focus``. Tolerant
    parser — falls back to a generic "could not parse" record so the
    UI always shows *something*.
    """
    system = REFLECT_EVALUATE_SYSTEM + (extra_system or "") + _NO_THINK
    sentences_json = json.dumps(prior_sentences, ensure_ascii=False)
    user = (
        f"## Aussage (zu prüfen)\n{claim_text}\n\n"
        f"## Kandidaten-Text (vollständig)\n{candidate_text}\n\n"
        f"## Bisherige Bewertung\n"
        f"verdict: {prior_verdict}\n"
        f"reasoning: {prior_reasoning}\n"
        f"sentences: {sentences_json}\n\n"
        "Kritisiere diese Bewertung als JSON:"
    )
    fallback: dict = {
        "self_assessment": "vollständig",
        "missed_statements": [],
        "concerns": [],
        "recommendation": "accept",
        "recommended_focus": "",
    }
    try:
        client = get_llm_client()
        completion = client.complete(
            messages=[
                Message(role="system", content=system),
                Message(role="user", content=user),
            ],
            model=get_default_model(),
            max_tokens=_MAX_TOKENS_STRUCTURED,
        )
    except Exception as exc:
        _log.warning("reflect_evaluate LLM call failed: %s", exc)
        fallback["concerns"] = [f"LLM-Aufruf fehlgeschlagen: {exc}"]
        return fallback
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        fallback["concerns"] = [f"LLM-Antwort nicht parsbar: {raw[:200]}"]
        return fallback
    if not isinstance(parsed, dict):
        return fallback
    assessment = str(parsed.get("self_assessment", "") or "").strip()
    if assessment not in ("vollständig", "lückenhaft", "fehlerhaft"):
        assessment = "vollständig"
    missed = parsed.get("missed_statements", [])
    if not isinstance(missed, list):
        missed = []
    concerns = parsed.get("concerns", [])
    if not isinstance(concerns, list):
        concerns = []
    rec = str(parsed.get("recommendation", "") or "").strip()
    if rec not in ("accept", "re-evaluate", "expand-context"):
        rec = "accept"
    return {
        "self_assessment": assessment,
        "missed_statements": [str(m) for m in missed if str(m).strip()],
        "concerns": [str(c) for c in concerns if str(c).strip()],
        "recommendation": rec,
        "recommended_focus": str(parsed.get("recommended_focus", "") or ""),
    }


class EvaluateStepRequest(BaseModel):
    search_result_node_id: str
    # Optional: if omitted, the backend walks the chain
    # search_result → task → claim to resolve it. Lets the agent's
    # plan_proposal flow accept evaluate without the panel having to
    # know the upstream claim.
    against_claim_id: str | None = None
    provider: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/evaluate",
    status_code=201,
)
async def evaluate_step(session_id: str, body: EvaluateStepRequest, request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")

    nodes, _ = read_session(sd)
    anchor = next((n for n in nodes if n.node_id == body.search_result_node_id), None)
    if anchor is None:
        raise HTTPException(
            status_code=404,
            detail=f"anchor node not found: {body.search_result_node_id}",
        )
    if anchor.kind not in ("search_result", "sub_statement"):
        raise HTTPException(
            status_code=400,
            detail=f"anchor must be search_result or sub_statement, got kind={anchor.kind}",
        )
    # Resolve to the upstream search_result for chain-walk + candidate
    # text. For sub_statement anchors, the candidate text is the
    # sub_statement's own atomic claim (one fact at a time). For
    # search_result anchors, candidate text is the full hit.
    if anchor.kind == "sub_statement":
        parent_id = str(anchor.payload.get("parent_search_result_id", ""))
        sr = next((n for n in nodes if n.node_id == parent_id), None)
        if sr is None or sr.kind != "search_result":
            raise HTTPException(
                status_code=400,
                detail=f"sub_statement {body.search_result_node_id} has no parent search_result",
            )
        candidate_text = str(anchor.payload.get("text", ""))
    else:
        sr = anchor
        candidate_text = str(sr.payload.get("text", ""))
    # Resolve the upstream claim_id either from the request or via the
    # chain search_result → task → claim. The chain hops are stable:
    # search_result.payload.task_node_id and task.payload.focus_claim_id
    # are written when those nodes get spawned (see /search and
    # /formulate-task handlers).
    claim_id = body.against_claim_id
    if not claim_id:
        task_id = sr.payload.get("task_node_id")
        task = next((n for n in nodes if n.node_id == task_id), None) if task_id else None
        focus_claim_id = task.payload.get("focus_claim_id") if task else None
        if not focus_claim_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "against_claim_id missing and could not resolve from "
                    "search_result chain (task_node_id / focus_claim_id "
                    "not set on upstream nodes)."
                ),
            )
        claim_id = str(focus_claim_id)
    claim = next((n for n in nodes if n.node_id == claim_id), None)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"claim node not found: {claim_id}")
    if claim.kind != "claim":
        raise HTTPException(
            status_code=400, detail=f"against_claim_id must be claim, got kind={claim.kind}"
        )

    actor = resolve_provider(body.provider)
    extra_system, guidance_refs = _gather_guidance_via_skills(cfg.data_root, meta, "evaluate")
    # Decision-support bundle: Sitzungs-Ziel + Recherche-Frage zur
    # Aussage + Original-Chunk + Such-Aufgabe. Resolve task via
    # search_result → task chain.
    eval_task_id = sr.payload.get("task_node_id")
    eval_task = (
        next((n for n in nodes if n.node_id == eval_task_id), None)
        if isinstance(eval_task_id, str)
        else None
    )
    extra_system = _build_decision_context(claim, nodes, meta, task=eval_task) + extra_system
    pre_reasoning = _llm_pre_reason(
        step_kind="evaluate",
        step_label="Bewerten",
        anchor_summary=(
            f"Treffer: {sr.payload.get('text', '')[:200]} | "
            f"vs. Aussage: {claim.payload.get('text', '')[:200]}"
        ),
        session_goal=meta.goal,
        claim_goal=str(claim.payload.get("goal", "")),
    )
    full_system = EVALUATE_SYSTEM + (extra_system or "") + _NO_THINK
    try:
        verdict_payload = _llm_evaluate(
            claim.payload.get("text", ""),
            candidate_text,
            body.provider or "vllm",
            extra_system=extra_system,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM-Fehler: {exc}") from exc
    verdict = verdict_payload["verdict"]
    confidence = verdict_payload["confidence"]
    reasoning = verdict_payload["reasoning"]
    sentences = verdict_payload.get("sentences", [])

    payload = ActionProposalPayload(
        step_kind="evaluate",
        anchor_node_id=body.search_result_node_id,
        recommended=ActionOption(
            label=f"{verdict} (conf {confidence:.2f})",
            args={
                "verdict": verdict,
                "confidence": confidence,
                "reasoning": reasoning,
                "sentences": sentences,
                "against_claim_id": body.against_claim_id,
            },
        ),
        alternatives=[
            ActionOption(
                label="Verwerfen — keine Quelle",
                args={
                    "verdict": "not-source",
                    "confidence": 1.0,
                    "reasoning": "manuell verworfen",
                    "against_claim_id": body.against_claim_id,
                },
            ),
        ],
        reasoning="LLM-Bewertung Kandidat vs. Claim.",
        guidance_consulted=guidance_refs,
        pre_reasoning=pre_reasoning,
        system_prompt_used=full_system,
        tool_used=None,
    )
    landed = append_node(
        sd, build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    )
    return landed.__dict__


# ── Phase B: Self-Critique / Reflect ───────────────────────────────────


class ReflectRequest(BaseModel):
    proposal_node_id: str
    provider: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/reflect",
    status_code=201,
)
async def reflect_step(session_id: str, body: ReflectRequest, request: Request) -> dict:
    """Run a self-critique LLM call against an existing action_proposal.

    Today supports evaluate-style proposals (input: claim+search_result,
    output: verdict). Other step_kinds return 400 — extend as needed.
    Result lands as a ``reflection`` Node anchored to the proposal so
    the canvas can chain it visually under the action_proposal.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    nodes, _ = read_session(sd)
    proposal = next((n for n in nodes if n.node_id == body.proposal_node_id), None)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"proposal not found: {body.proposal_node_id}")
    if proposal.kind != "action_proposal":
        raise HTTPException(
            status_code=400,
            detail=f"reflect target must be action_proposal, got kind={proposal.kind}",
        )
    step_kind = str(proposal.payload.get("step_kind", ""))
    if step_kind != "evaluate":
        raise HTTPException(
            status_code=400,
            detail=(
                f"reflect-Implementierung deckt aktuell nur step_kind=evaluate ab "
                f"(angefragt: {step_kind}). Andere Step-Typen folgen separat."
            ),
        )

    sr_id = str(proposal.payload.get("anchor_node_id", ""))
    sr = next((n for n in nodes if n.node_id == sr_id), None)
    if sr is None or sr.kind != "search_result":
        raise HTTPException(
            status_code=400,
            detail="proposal anchor is not a search_result — kann nicht reflektieren.",
        )
    recommended = proposal.payload.get("recommended", {})
    rec_args = recommended.get("args", {}) if isinstance(recommended, dict) else {}
    claim_id = str(rec_args.get("against_claim_id", "") or "")
    if not claim_id:
        # Fallback: walk sr → task → claim (same chain as evaluate
        # endpoint's auto-resolve).
        task_id = sr.payload.get("task_node_id")
        task = next((n for n in nodes if n.node_id == task_id), None) if task_id else None
        focus = task.payload.get("focus_claim_id") if task else None
        if focus:
            claim_id = str(focus)
    claim = next((n for n in nodes if n.node_id == claim_id), None)
    if claim is None or claim.kind != "claim":
        raise HTTPException(
            status_code=400,
            detail="Konnte den ursprünglichen claim nicht auflösen — kann nicht reflektieren.",
        )

    extra_system, guidance_refs = _gather_guidance_via_skills(cfg.data_root, meta, "reflect")
    critique = _llm_reflect_evaluate(
        claim_text=str(claim.payload.get("text", "")),
        candidate_text=str(sr.payload.get("text", "")),
        prior_verdict=str(rec_args.get("verdict", "")),
        prior_reasoning=str(rec_args.get("reasoning", "")),
        prior_sentences=list(rec_args.get("sentences", []) or []),
        extra_system=extra_system,
    )
    actor = resolve_provider(body.provider)
    audit = {
        "source_label": "Reflektieren (POST /reflect → _llm_reflect_evaluate)",
        "system_prompt_used": REFLECT_EVALUATE_SYSTEM + (extra_system or "") + _NO_THINK,
        "input_summary": {
            "proposal_node_id": body.proposal_node_id,
            "search_result_node_id": sr_id,
            "claim_node_id": claim_id,
            "prior_verdict": str(rec_args.get("verdict", "")),
        },
        "guidance_consulted": [g.__dict__ for g in guidance_refs],
    }
    reflection_node = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=session_id,
            kind="reflection",
            payload={
                "anchor_node_id": body.proposal_node_id,
                "step_kind_reviewed": step_kind,
                **critique,
                "audit": audit,
            },
            actor=actor,
        ),
    )
    return reflection_node.__dict__


# ── Reactive-Capability Re-Evaluate ────────────────────────────────────


class ReEvaluateRequest(BaseModel):
    capability_gate_node_id: str
    capability_ids: list[str]
    provider: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/re-evaluate",
    status_code=201,
)
async def re_evaluate_step(session_id: str, body: ReEvaluateRequest, request: Request) -> dict:
    """Re-run evaluate with the capability_gate's selected capabilities
    injected as domain rules into the prompt.

    Spawns a fresh ``action_proposal`` (step_kind=evaluate) — the user
    decides as usual. The action_proposal's audit field carries
    ``capabilities_used`` for traceability.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    nodes, _ = read_session(sd)
    gate = next((n for n in nodes if n.node_id == body.capability_gate_node_id), None)
    if gate is None or gate.kind != "capability_gate":
        raise HTTPException(
            status_code=404,
            detail=f"capability_gate not found: {body.capability_gate_node_id}",
        )
    sr_id = str(gate.payload.get("search_result_node_id", ""))
    sr = next((n for n in nodes if n.node_id == sr_id), None)
    if sr is None or sr.kind != "search_result":
        raise HTTPException(status_code=400, detail="capability_gate's search_result not found")
    claim_id = str(gate.payload.get("claim_node_id", ""))
    claim = next((n for n in nodes if n.node_id == claim_id), None)
    if claim is None or claim.kind != "claim":
        raise HTTPException(status_code=400, detail="capability_gate's claim not found")
    selected: list[Approach] = []
    for app_id in body.capability_ids:
        a = get_approach(cfg.data_root, app_id)
        if a is not None and a.enabled:
            selected.append(a)
    if not selected:
        raise HTTPException(status_code=400, detail="keine gültigen capability_ids ausgewählt")
    prior_evaluation = next(
        (n for n in nodes if n.node_id == str(gate.payload.get("evaluation_node_id", ""))),
        None,
    )
    prior_verdict = str(prior_evaluation.payload.get("verdict", "")) if prior_evaluation else ""
    prior_reasoning = str(prior_evaluation.payload.get("reasoning", "")) if prior_evaluation else ""
    rules_blocks = [f"## {a.name}\n{a.domain_rules}" for a in selected if a.domain_rules]
    re_task_id = sr.payload.get("task_node_id")
    re_task = (
        next((n for n in nodes if n.node_id == re_task_id), None)
        if isinstance(re_task_id, str)
        else None
    )
    extra_system = (
        _build_decision_context(claim, nodes, meta, task=re_task)
        + "\n\n# GELADENE DOMÄNEN-CAPABILITIES\n\n"
        + "\n\n".join(rules_blocks)
        + "\n\n# WICHTIG\n"
        + "Du hast diese Bewertung schon einmal abgegeben:\n"
        + f"  Original-Verdict: {prior_verdict}\n"
        + f"  Original-Reasoning: {prior_reasoning}\n\n"
        + "Berücksichtige nun die Domänen-Capabilities und prüfe, ob das "
        + "Verdict angepasst werden muss. Wenn ja: erkläre WARUM das "
        + "Domänen-Wissen die ursprüngliche Bewertung umkippt."
    )
    actor = resolve_provider(body.provider)
    pre_reasoning = _llm_pre_reason(
        step_kind="evaluate",
        step_label="Re-Evaluate (mit Capabilities)",
        anchor_summary=(
            f"Treffer: {sr.payload.get('text', '')[:200]} | "
            f"vs. Aussage: {claim.payload.get('text', '')[:200]} | "
            f"Capabilities: {', '.join(a.name for a in selected)}"
        ),
        session_goal=meta.goal,
        claim_goal=str(claim.payload.get("goal", "")),
    )
    full_system = EVALUATE_SYSTEM + extra_system + _NO_THINK
    try:
        verdict_payload = _llm_evaluate(
            claim.payload.get("text", ""),
            sr.payload.get("text", ""),
            body.provider or "vllm",
            extra_system=extra_system,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM-Fehler: {exc}") from exc
    verdict = verdict_payload["verdict"]
    confidence = verdict_payload["confidence"]
    reasoning = verdict_payload["reasoning"]
    sentences = verdict_payload.get("sentences", [])
    payload = ActionProposalPayload(
        step_kind="evaluate",
        anchor_node_id=sr.node_id,
        recommended=ActionOption(
            label=f"{verdict} (re-eval, conf {confidence:.2f})",
            args={
                "verdict": verdict,
                "confidence": confidence,
                "reasoning": reasoning,
                "sentences": sentences,
                "against_claim_id": claim.node_id,
                "capabilities_used": [a.approach_id for a in selected],
                "capability_gate_node_id": body.capability_gate_node_id,
                "prior_evaluation_node_id": gate.payload.get("evaluation_node_id"),
            },
        ),
        alternatives=[
            ActionOption(
                label="Verwerfen — bei alter Bewertung bleiben",
                args={
                    "verdict": prior_verdict or "manual",
                    "confidence": 1.0,
                    "reasoning": "Re-Evaluate verworfen — alte Bewertung bleibt.",
                    "against_claim_id": claim.node_id,
                },
            ),
        ],
        reasoning="Re-Evaluation mit geladenen Domänen-Capabilities.",
        guidance_consulted=[],
        pre_reasoning=pre_reasoning,
        system_prompt_used=full_system,
        tool_used=None,
    )
    landed = append_node(
        sd, build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    )
    # Mark the gate as accepted + record the new proposal id.
    gate_update = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=session_id,
            kind="capability_gate",
            payload={
                **gate.payload,
                "status": "accepted",
                "re_evaluate_proposal_id": landed.node_id,
                "selected_capability_ids": [a.approach_id for a in selected],
            },
            actor="human",
        ),
    )
    append_edge(
        sd,
        Edge(
            edge_id=new_id(),
            session_id=session_id,
            from_node=gate.node_id,
            to_node=landed.node_id,
            kind="re-evaluated-with",
            reason=None,
            actor="human",
        ),
    )
    return {
        "action_proposal": landed.__dict__,
        "gate_update": gate_update.__dict__,
    }


def _llm_decompose_hit(candidate_text: str, *, extra_system: str = "") -> list[str]:
    """Split a search-hit text into atomic sub-statements.

    Returns a list of strings — each is one self-contained claim that
    can be evaluated independently. Strict parser: rejects non-list
    output by raising RuntimeError, so the calling endpoint can
    surface a clear 502.
    """
    system = DECOMPOSE_HIT_SYSTEM + (extra_system or "") + _NO_THINK
    user = f"Treffer-Text:\n{candidate_text}\n\nGib das JSON-Array der Sub-Aussagen zurück."
    client = get_llm_client()
    completion = client.complete(
        messages=[
            Message(role="system", content=system),
            Message(role="user", content=user),
        ],
        model=get_default_model(),
        max_tokens=_MAX_TOKENS_STRUCTURED,
    )
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"_llm_decompose_hit: could not parse LLM response: {raw[:500]}"
        ) from exc
    if not isinstance(parsed, list) or not all(isinstance(s, str) and s.strip() for s in parsed):
        raise RuntimeError(
            f"_llm_decompose_hit: response is not a list of non-empty strings: {raw[:500]}"
        )
    return [s.strip() for s in parsed]


class DecomposeHitRequest(BaseModel):
    search_result_node_id: str
    provider: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/decompose-hit",
    status_code=201,
)
async def decompose_hit_step(session_id: str, body: DecomposeHitRequest, request: Request) -> dict:
    """Phase C: split a search_result into atomic sub_statements.

    Lands as an action_proposal with step_kind="decompose_hit". On
    /decide accept, each sub-statement becomes its own
    ``sub_statement`` Node anchored to the search_result.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    nodes, _ = read_session(sd)
    sr = next((n for n in nodes if n.node_id == body.search_result_node_id), None)
    if sr is None or sr.kind != "search_result":
        raise HTTPException(
            status_code=400,
            detail=f"node not a search_result: {body.search_result_node_id}",
        )
    extra_system, guidance_refs = _gather_guidance_via_skills(cfg.data_root, meta, "decompose_hit")
    try:
        sub_statements = _llm_decompose_hit(
            str(sr.payload.get("text", "")), extra_system=extra_system
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM-Fehler: {exc}") from exc
    actor = resolve_provider(body.provider)
    full_system = DECOMPOSE_HIT_SYSTEM + (extra_system or "") + _NO_THINK
    payload = ActionProposalPayload(
        step_kind="decompose_hit",
        anchor_node_id=body.search_result_node_id,
        recommended=ActionOption(
            label=f"{len(sub_statements)} Sub-Aussagen",
            args={"sub_statements": sub_statements},
        ),
        alternatives=[
            ActionOption(label="Verwerfen — keine Decomposition", args={"sub_statements": []}),
        ],
        reasoning=(
            f"LLM hat den Treffer in {len(sub_statements)} atomare "
            "Sub-Aussagen zerlegt — jede kann einzeln gegen den Claim "
            "evaluiert werden."
        ),
        guidance_consulted=guidance_refs,
        pre_reasoning="",
        system_prompt_used=full_system,
        tool_used=None,
    )
    landed = append_node(
        sd, build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    )
    return landed.__dict__


def _llm_extract_claim_backgrounds(
    claim_texts: list[str],
    chunk_text: str,
    *,
    extra_system: str = "",
) -> list[str]:
    """Batched per-claim chunk-comprehension. One LLM call returns N
    background snippets for N claims. Each snippet captures the
    surrounding context that disambiguates the claim's topic + units +
    references but is NOT in the claim itself.

    Returns ``[""] * len(claim_texts)`` on any parse / size failure
    (best-effort, never blocks claim creation). Empty strings are also
    valid for individual claims when the chunk doesn't add anything.
    """
    if not claim_texts or not chunk_text or not chunk_text.strip():
        return [""] * len(claim_texts)
    system = EXTRACT_CLAIM_BACKGROUND_SYSTEM + (extra_system or "") + _NO_THINK
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(claim_texts))
    truncated = chunk_text.strip()[:1500]
    if len(chunk_text) > 1500:
        truncated += " […]"
    user = (
        f"Quell-Textabschnitt:\n{truncated}\n\n"
        f"Aussagen:\n{numbered}\n\n"
        f"JSON-Array der Hintergrund-Snippets (selbe Reihenfolge):"
    )
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
        max_tokens=_MAX_TOKENS_STRUCTURED,
    )
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return [""] * len(claim_texts)
    if not isinstance(parsed, list) or len(parsed) != len(claim_texts):
        return [""] * len(claim_texts)
    return [str(b).strip()[:1200] if isinstance(b, str) else "" for b in parsed]


def _llm_extract_claim_goals(
    claim_texts: list[str],
    session_goal: str,
    provider: str,
    *,
    chunk_text: str = "",
    extra_system: str = "",
) -> list[str]:
    """Batched per-claim-goal extraction. One LLM call returns N goals
    for N claims. JSON-array output, length must match input. On any
    parse / size failure, returns ``[""] * len(claim_texts)`` — best
    effort, never blocks claim creation.

    ``chunk_text`` is the surrounding chunk the claims came from; used
    to disambiguate topic, units, and pronoun references in the
    research-question (so e.g. "Brennelement TRINO" gets a question
    that references the reactor context, not a generic question).
    """
    del provider
    if not claim_texts:
        return []
    system = EXTRACT_CLAIM_GOALS_SYSTEM + (extra_system or "") + _NO_THINK
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(claim_texts))
    chunk_block = ""
    if chunk_text and chunk_text.strip():
        truncated = chunk_text.strip()[:1500]
        if len(chunk_text) > 1500:
            truncated += " […]"
        chunk_block = (
            f"Quell-Textabschnitt (Kontext der Aussagen — nutze ihn, "
            f"um Thema und Bezüge der Recherche-Fragen zu konkretisieren):\n"
            f"{truncated}\n\n"
        )
    user = (
        f"Sitzungs-Ziel: {session_goal or '(kein Ziel gesetzt)'}\n\n"
        f"{chunk_block}"
        f"Aussagen:\n{numbered}\n\n"
        f"JSON-Array der Recherche-Fragen (selbe Reihenfolge):"
    )
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
        max_tokens=_MAX_TOKENS_STRUCTURED,
    )
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return [""] * len(claim_texts)
    if not isinstance(parsed, list) or len(parsed) != len(claim_texts):
        return [""] * len(claim_texts)
    return [str(g).strip()[:200] if isinstance(g, str) else "" for g in parsed]


def _llm_next_step(
    anchor: Node,
    session_goal: str,
    available_steps: list[str],
    tools_summary: str,
    *,
    extra_system: str = "",
) -> dict:
    """Open-ended planner. Returns a dict with discriminator ``kind``:

    - ``executable_step``: pick a registered step. Caller routes to the
      matching step LLM, creates an action_proposal.
    - ``capability_request``: nothing in the registry fits. Caller
      creates a capability_request Node carrying the description.
    - ``manual_review``: only a human can resolve this. Caller creates
      a manual_review Node.

    Tolerant parser: on any LLM/parse failure returns a safe fallback
    that defaults to manual_review, so the user always sees *something*.
    """
    anchor_summary = (
        f"kind={anchor.kind}, payload={json.dumps(anchor.payload, ensure_ascii=False)[:600]}"
    )
    system = NEXT_STEP_SYSTEM + (extra_system or "") + _NO_THINK
    user = (
        f"## Knoten\n{anchor_summary}\n\n"
        f"## Sitzungs-Ziel\n{session_goal or '(nicht gesetzt)'}\n\n"
        f"## Verfügbare Steps\n{', '.join(available_steps)}\n\n"
        f"## Verfügbare Tools\n{tools_summary or '(keine)'}\n\n"
        f"Was schlägst du vor? JSON:"
    )
    fallback: dict = {
        "kind": "manual_review",
        "name": "LLM-Antwort nicht verfügbar",
        "description": "Der Agent konnte keinen Vorschlag generieren — bitte manuell entscheiden.",
        "reasoning": "Fallback bei Parse-Fehler.",
        "goal_alignment": "",
        "considered_alternatives": [],
        "confidence": 0.0,
        "tool": None,
        "approach_id": None,
    }
    try:
        client = get_llm_client()
        completion = client.complete(
            messages=[
                Message(role="system", content=system),
                Message(role="user", content=user),
            ],
            model=get_default_model(),
        )
    except Exception as exc:
        _log.warning("next_step LLM call failed: %s", exc)
        fallback["description"] = f"LLM-Aufruf fehlgeschlagen: {exc}"
        return fallback
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        fallback["description"] = f"LLM-Antwort nicht parsbar: {raw[:200]}"
        return fallback
    if not isinstance(parsed, dict):
        return fallback
    kind = str(parsed.get("kind", "")).strip()
    if kind not in ("executable_step", "capability_request", "manual_review"):
        kind = "manual_review"
    return {
        "kind": kind,
        "name": str(parsed.get("name", "") or ""),
        "description": str(parsed.get("description", "") or ""),
        "reasoning": str(parsed.get("reasoning", "") or ""),
        "goal_alignment": str(parsed.get("goal_alignment", "") or ""),
        "considered_alternatives": (
            parsed.get("considered_alternatives", [])
            if isinstance(parsed.get("considered_alternatives"), list)
            else []
        ),
        "confidence": (
            float(parsed["confidence"])
            if isinstance(parsed.get("confidence"), (int, float))
            else 0.5
        ),
        "tool": parsed.get("tool") if isinstance(parsed.get("tool"), str) else None,
        "approach_id": (
            parsed.get("approach_id") if isinstance(parsed.get("approach_id"), str) else None
        ),
    }


# Anchor-kind → list of steps the planner may pick. Open-ended: when none of
# these fit, the planner is allowed to escape into capability_request /
# manual_review instead.
_VALID_STEPS_FOR_KIND: dict[str, list[str]] = {
    "chunk": ["extract_claims", "propose_stop"],
    "claim": ["formulate_task", "propose_stop"],
    "task": ["search", "propose_stop"],
    "search_result": [
        "evaluate",
        "decompose_hit",
        "promote_search_result",
        "propose_stop",
    ],
    "sub_statement": ["evaluate", "propose_stop"],
    "evaluation": ["propose_stop"],
}


# ── Phase 3: Active Skill / Coordinator wrappers ─────────────────────────
#
# An ``active`` Approach (mode="active") is invoked as its own LLM call
# with a wrapper prompt that frames the approach's extra_system as
# specialist domain knowledge. The skill returns a structured opinion
# (reasoning + suggested step + confidence). The Coordinator then merges
# the Meta-Plan and all skill opinions into the final plan.

ACTIVE_SKILL_SYSTEM = (
    "Du bist ein spezialisierter Sub-Agent eines Recherche-Agenten. "
    "Du bekommst einen Knoten + Sitzungs-Ziel + die verfügbaren Steps. "
    "Deine Aufgabe: gib aus deiner Spezialist-Perspektive eine "
    "fundierte Empfehlung — welcher Step ist deiner Meinung nach "
    "jetzt richtig, warum, wie sicher bist du.\n\n"
    "Antworte AUSSCHLIESSLICH als JSON:\n"
    "{\n"
    '  "reasoning": <deutscher Satz: was siehst du, was schließt du daraus>,\n'
    '  "suggested_step": <Step-Name aus der verfügbaren Liste oder leer>,\n'
    '  "confidence": <0.0-1.0>\n'
    "}\n\n"
    "Kein Vor- oder Nachtext, keine Codeblöcke. Wenn dein Spezialwissen "
    "auf diesen Knoten nicht zutrifft, gib leeren suggested_step zurück "
    "und erkläre kurz warum nicht.\n\n"
    "## DEIN SPEZIALWISSEN\n"
)

COORDINATOR_SYSTEM = (
    "Du bist der Koordinator eines Multi-Agenten-Recherche-Systems. "
    "Du bekommst:\n"
    "1. Den Initial-Plan des Meta-Planers.\n"
    "2. Empfehlungen mehrerer Spezialisten (jeweils reasoning + "
    "suggested_step + confidence).\n\n"
    "Deine Aufgabe: synthesisiere die FINALE Entscheidung. Bei "
    "Konsens → folge dem Konsens. Bei Konflikten → gewichte nach "
    "Konfidenz und Spezialisierung; bei klarer Mehrheit → folge der "
    "Mehrheit; sonst entscheide nach Plausibilität.\n\n"
    "Antworte AUSSCHLIESSLICH als JSON-Objekt im selben Format wie "
    "der Meta-Planer:\n"
    "{\n"
    '  "kind": "executable_step" | "capability_request" | "manual_review",\n'
    '  "name": <siehe Meta-Planer-Regeln>,\n'
    '  "description": <bei capability_request/manual_review>,\n'
    '  "reasoning": <warum diese finale Wahl - berücksichtige '
    "Spezialisten-Stimmen wörtlich>,\n"
    '  "goal_alignment": <Pflicht: zitiere das Sitzungs-Ziel wörtlich '
    "und erkläre konkret, wie der gewählte Step diesem Ziel näher bringt. "
    "Beispiel: \"Ziel ist 'Worauf beruhen die Aussagen?'. extract_claims "
    "teilt den Text in einzelne Behauptungen, damit ich für jede die "
    'Quelle suchen kann." Schreibe vollständige Sätze ohne Platzhalter '
    "(< >).>,\n"
    '  "considered_alternatives": [\n'
    '    {"name": <name>, "kind": <kind>, "why_not": <Grund>}\n'
    "  ],\n"
    '  "confidence": <0.0-1.0>,\n'
    '  "tool": <Tool-Name oder null>,\n'
    '  "approach_id": <Approach-Name oder null>\n'
    "}\n\n"
    "Kein Vor- oder Nachtext, keine Codeblöcke."
)


def _llm_active_skill(
    *,
    skill_name: str,
    skill_extra_system: str,
    anchor: Node,
    session_goal: str,
    available_steps: list[str],
) -> dict:
    """Single active-skill call. Returns dict with keys ``reasoning``,
    ``suggested_step``, ``confidence``. Tolerant on parse failures —
    returns an empty-suggestion fallback so the coordinator can still
    proceed with whatever specialists succeeded.
    """
    anchor_summary = (
        f"kind={anchor.kind}, payload={json.dumps(anchor.payload, ensure_ascii=False)[:400]}"
    )
    system = ACTIVE_SKILL_SYSTEM + (skill_extra_system or "") + _NO_THINK
    user = (
        f"## Knoten\n{anchor_summary}\n\n"
        f"## Sitzungs-Ziel\n{session_goal or '(nicht gesetzt)'}\n\n"
        f"## Verfügbare Steps\n{', '.join(available_steps) or '(keine)'}\n\n"
        f"Was empfiehlst du? JSON:"
    )
    fallback: dict = {
        "reasoning": f"({skill_name}: LLM-Aufruf fehlgeschlagen oder Antwort nicht parsbar)",
        "suggested_step": "",
        "confidence": 0.0,
    }
    try:
        client = get_llm_client()
        completion = client.complete(
            messages=[
                Message(role="system", content=system),
                Message(role="user", content=user),
            ],
            model=get_default_model(),
        )
    except Exception as exc:
        _log.warning("active_skill %s LLM call failed: %s", skill_name, exc)
        fallback["reasoning"] = f"({skill_name}: Aufruf fehlgeschlagen: {exc})"
        return fallback
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return fallback
    if not isinstance(parsed, dict):
        return fallback
    return {
        "reasoning": str(parsed.get("reasoning", "") or ""),
        "suggested_step": str(parsed.get("suggested_step", "") or ""),
        "confidence": (
            float(parsed["confidence"])
            if isinstance(parsed.get("confidence"), (int, float))
            else 0.5
        ),
    }


def _llm_coordinator(
    *,
    meta_plan: dict,
    skill_outputs: list[dict],
    anchor: Node,
    session_goal: str,
    available_steps: list[str],
    tools_summary: str,
) -> dict:
    """Coordinator call. Merges Meta-Plan + skill outputs into a final
    plan dict (same shape as _llm_next_step). On parse failure, falls
    back to the original Meta-Plan so the pipeline still has a result.
    """
    anchor_summary = (
        f"kind={anchor.kind}, payload={json.dumps(anchor.payload, ensure_ascii=False)[:400]}"
    )
    skill_lines = []
    for s in skill_outputs:
        skill_lines.append(
            f"- {s.get('skill_name', '?')}: "
            f"step={s.get('suggested_step') or '(leer)'} "
            f"({(s.get('confidence', 0) * 100):.0f}% conf) — "
            f"{s.get('reasoning', '')}"
        )
    skills_block = "\n".join(skill_lines) if skill_lines else "(keine)"
    meta_summary = (
        f"kind={meta_plan.get('kind', '?')}, "
        f"name={meta_plan.get('name', '')}, "
        f"reasoning={meta_plan.get('reasoning', '')}"
    )

    user = (
        f"## Knoten\n{anchor_summary}\n\n"
        f"## Sitzungs-Ziel\n{session_goal or '(nicht gesetzt)'}\n\n"
        f"## Verfügbare Steps\n{', '.join(available_steps) or '(keine)'}\n\n"
        f"## Verfügbare Tools\n{tools_summary or '(keine)'}\n\n"
        f"## Meta-Planer Initial-Plan\n{meta_summary}\n\n"
        f"## Spezialisten-Empfehlungen\n{skills_block}\n\n"
        f"Synthesisiere die finale Entscheidung als JSON:"
    )
    try:
        client = get_llm_client()
        completion = client.complete(
            messages=[
                Message(role="system", content=COORDINATOR_SYSTEM + _NO_THINK),
                Message(role="user", content=user),
            ],
            model=get_default_model(),
        )
    except Exception as exc:
        _log.warning("coordinator LLM call failed, falling back to meta-plan: %s", exc)
        return dict(meta_plan)
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        _log.warning("coordinator response unparsable, falling back to meta-plan")
        return dict(meta_plan)
    if not isinstance(parsed, dict):
        return dict(meta_plan)
    kind = str(parsed.get("kind", "")).strip()
    if kind not in ("executable_step", "capability_request", "manual_review"):
        kind = "manual_review"
    return {
        "kind": kind,
        "name": str(parsed.get("name", "") or ""),
        "description": str(parsed.get("description", "") or ""),
        "reasoning": str(parsed.get("reasoning", "") or ""),
        "goal_alignment": str(parsed.get("goal_alignment", "") or ""),
        "considered_alternatives": (
            parsed.get("considered_alternatives", [])
            if isinstance(parsed.get("considered_alternatives"), list)
            else []
        ),
        "confidence": (
            float(parsed["confidence"])
            if isinstance(parsed.get("confidence"), (int, float))
            else 0.5
        ),
        "tool": parsed.get("tool") if isinstance(parsed.get("tool"), str) else None,
        "approach_id": (
            parsed.get("approach_id") if isinstance(parsed.get("approach_id"), str) else None
        ),
    }


def _llm_pre_reason(
    step_kind: str,
    step_label: str,
    anchor_summary: str,
    session_goal: str,
    claim_goal: str,
    *,
    extra_system: str = "",
) -> str:
    """ReAct-style "Thought" before each action: a short German sentence
    explaining why this step makes sense for this anchor right now,
    relative to the session goal + the per-claim research question (if
    relevant). Best-effort: returns "" on parse / LLM failure so the
    action path never blocks on the reflective layer.
    """
    system = PRE_REASON_SYSTEM + (extra_system or "") + _NO_THINK
    user = (
        f"Schritt: {step_label} ({step_kind})\n"
        f"Knoten-Inhalt: {anchor_summary[:400]}\n"
        f"Sitzungs-Ziel: {session_goal or '(nicht gesetzt)'}\n"
        f"Recherche-Frage zur Aussage: {claim_goal or '(nicht relevant)'}\n\n"
        f"Begründung in einem Satz:"
    )
    try:
        client = get_llm_client()
        completion = client.complete(
            messages=[
                Message(role="system", content=system),
                Message(role="user", content=user),
            ],
            model=get_default_model(),
        )
    except Exception as exc:
        _log.warning("pre_reason LLM call failed: %s", exc)
        return ""
    raw = _strip_thinking_tags(completion.text or "")
    while len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"', "„"):
        raw = raw[1:-1].strip()
    return raw[:300]


def _llm_extract_goal(
    chunk_text: str,
    first_claim_text: str,
    provider: str,
    *,
    extra_system: str = "",
) -> str:
    """Synthesise the session's overall research goal from its starting
    chunk + the first claim accepted from it. Called once per session,
    automatically, when the user lands their first claim. The user can
    override the result via PUT /sessions/{id}/goal at any time.

    Returns a one-line German sentence (≤200 chars). Failure modes are
    swallowed by the caller — a missing goal is fine, the Planner falls
    back to the chunk text.
    """
    del provider  # reserved for Stage 6 routing
    system = EXTRACT_GOAL_SYSTEM + (extra_system or "") + _NO_THINK
    user = (
        f"Textabschnitt:\n{chunk_text}\n\n"
        f"Erste überprüfbare Aussage:\n{first_claim_text}\n\n"
        f"Recherche-Ziel:"
    )
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
        max_tokens=_MAX_TOKENS_STRUCTURED,
    )
    raw = (completion.text or "").strip()
    # Strip outer quote pairs the model sometimes emits.
    while len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"', "„"):
        raw = raw[1:-1].strip()
    raw = raw[:200]
    if not raw:
        raise RuntimeError("_llm_extract_goal: empty response from LLM")
    return raw


def _maybe_extract_goal(cfg: object, sd: Path, meta: SessionMeta, claim_text: str) -> SessionMeta:
    """Auto-trigger goal extraction after the first claim of a session is
    accepted. Idempotent: if ``meta.goal`` is already set we return meta
    unchanged. Failures are logged + swallowed — a session is still usable
    without an extracted goal."""
    if meta.goal:
        return meta
    nodes, _ = read_session(sd)
    chunk = next((n for n in nodes if n.node_id == meta.root_chunk_id), None)
    if chunk is None:
        # Older sessions stored the chunk node under its own node_id, not
        # the box_id. Fall back to "first chunk in the session".
        chunk = next((n for n in nodes if n.kind == "chunk"), None)
    if chunk is None:
        return meta
    chunk_text = str(chunk.payload.get("text", ""))
    extra_system, _ = _gather_guidance_via_skills(cfg.data_root, meta, "extract_goal")  # type: ignore[attr-defined]
    try:
        goal = _llm_extract_goal(chunk_text, claim_text, "vllm", extra_system=extra_system)
    except Exception as exc:
        _log.warning("extract_goal failed: %s", exc)
        return meta
    new_meta = SessionMeta(**{**meta.__dict__, "goal": goal})
    write_meta(sd, new_meta)
    return new_meta


def _summarize_session_state(meta: SessionMeta, nodes: list[Node], edges: list[Edge]) -> str:
    """Compact German prose summary of the session state for the Planner.

    Lists the goal, counts each kind, and surfaces the *open fronts* —
    claims without tasks, tasks without searches, results without
    evaluations, etc. Truncated to keep the prompt small for big sessions.
    """
    chunks = [n for n in nodes if n.kind == "chunk"]
    claims = [n for n in nodes if n.kind == "claim"]
    tasks = [n for n in nodes if n.kind == "task"]
    results = [n for n in nodes if n.kind == "search_result"]
    evals = [n for n in nodes if n.kind == "evaluation"]
    stops = [n for n in nodes if n.kind == "stop_proposal"]

    # Walk relationships
    task_by_claim: dict[str, Node] = {}
    for t in tasks:
        cid = t.payload.get("focus_claim_id")
        if isinstance(cid, str):
            task_by_claim[cid] = t
    results_by_task: dict[str, list[Node]] = {}
    for r in results:
        tid = r.payload.get("task_node_id")
        if isinstance(tid, str):
            results_by_task.setdefault(tid, []).append(r)
    eval_by_result: dict[str, Node] = {}
    for ev in evals:
        for e in edges:
            if e.from_node == ev.node_id and e.kind == "evaluates":
                eval_by_result[e.to_node] = ev
    stopped_anchors = {
        s.payload.get("anchor_node_id")
        for s in stops
        if isinstance(s.payload.get("anchor_node_id"), str)
    }

    lines: list[str] = []
    lines.append(f"Ziel: {meta.goal or '(noch nicht gesetzt)'}")
    lines.append("")
    lines.append("Bestand:")
    lines.append(
        f"  - {len(chunks)} Chunk(s), {len(claims)} Aussage(n), "
        f"{len(tasks)} Suchanfrage(n), {len(results)} Treffer, "
        f"{len(evals)} Bewertung(en), {len(stops)} Stopp(s)"
    )

    open_fronts: list[str] = []
    for c in claims:
        cid = c.node_id
        ctext = str(c.payload.get("text", ""))[:80]
        cgoal = str(c.payload.get("goal", "")).strip()
        # When per-claim goal is set, surface it inline so the planner
        # picks the right next move per claim rather than treating them
        # as one homogeneous batch.
        cdesc = f'"{ctext}"' + (f" — Frage: {cgoal}" if cgoal else "")
        if cid in stopped_anchors:
            continue
        if cid not in task_by_claim:
            open_fronts.append(
                f"- Aussage {cid[:8]}… ({cdesc}) → benötigt formulate_task oder propose_stop"
            )
            continue
        task = task_by_claim[cid]
        rs = results_by_task.get(task.node_id, [])
        if not rs:
            open_fronts.append(
                f'- Suchanfrage {task.node_id[:8]}… für Aussage "{ctext}" → noch nicht gesucht'
            )
            continue
        unevaluated = [r for r in rs if r.node_id not in eval_by_result]
        if unevaluated:
            ids = ", ".join(r.node_id[:6] for r in unevaluated[:3])
            extra = f" + {len(unevaluated) - 3} weitere" if len(unevaluated) > 3 else ""
            open_fronts.append(
                f'- {len(unevaluated)} unbewertete Treffer für Aussage "{ctext}" '
                f"(IDs: {ids}{extra})"
            )
            continue
        # all evaluated — categorise verdicts
        verdicts = [str(eval_by_result[r.node_id].payload.get("verdict", "?")) for r in rs]
        verdict_summary = ", ".join(f"{verdicts.count(v)}x {v}" for v in sorted(set(verdicts)))
        good = any(v in ("likely-source", "partial-support") for v in verdicts)
        if good:
            open_fronts.append(
                f'- Aussage "{ctext}" hat Quelle ({verdict_summary}) → '
                "Kandidat für propose_stop oder promote_search_result"
            )
        else:
            open_fronts.append(
                f'- Aussage "{ctext}" → keine Quelle ({verdict_summary}) → '
                "andere Suchanfrage / propose_stop"
            )

    # Promoted but un-analysed chunks
    for ch in chunks:
        if ch.payload.get("promoted_from") and not any(
            c.payload.get("source_node_id") == ch.node_id for c in claims
        ):
            open_fronts.append(f"- abgeleiteter Chunk {ch.node_id[:8]}… → benötigt extract_claims")

    if open_fronts:
        lines.append("")
        lines.append("Offene Fronten:")
        lines.extend(open_fronts[:12])  # cap
        if len(open_fronts) > 12:
            lines.append(f"  … und {len(open_fronts) - 12} weitere")
    else:
        lines.append("")
        lines.append("Keine offenen Fronten — alle Claims bearbeitet.")

    # ID-Index so the Planner can pick a target_anchor_id meaningfully
    lines.append("")
    lines.append("Knoten-IDs (für target_anchor_id):")
    for n in nodes:
        if n.kind == "decision" or n.kind == "action_proposal":
            continue
        text = str(
            n.payload.get("text") or n.payload.get("query") or n.payload.get("box_id") or ""
        )[:40]
        lines.append(f"  - {n.node_id} ({n.kind}): {text}")
        if len(lines) > 200:  # hard cap
            break

    return "\n".join(lines)


def _summarize_tools_for_planner() -> str:
    """Multi-line tool listing for the Planner's user prompt. Includes
    each tool's ``agent_hint`` (concrete trigger heuristic) so the LLM
    knows exactly when to capability_request a stub by its right name —
    e.g. ``CrossDocSearcher`` rather than a vague ``"search"``.
    """
    out: list[str] = []
    for t in list_tools():
        status = "verfügbar" if t.enabled else "DEAKTIVIERT (capability_request möglich)"
        consumers = ", ".join(t.used_by)
        out.append(
            f"- {t.name} ({t.scope}, {t.cost_hint}, {status}, für: {consumers})\n"
            f"    {t.when_to_use}"
        )
        if t.agent_hint:
            out.append(f"    Agent-Hinweis: {t.agent_hint}")
    return "\n".join(out)


def _llm_plan(
    goal: str,
    state_summary: str,
    tools_summary: str,
    approaches_summary: str,
    provider: str,
    *,
    extra_system: str = "",
) -> dict:
    """Call the Planner LLM. Returns parsed JSON dict with keys: next_step,
    target_anchor_id, tool, approach_id, reasoning, expected_outcome,
    confidence, fallback_plan. Tolerant to messy output (uses
    ``_strip_json_fence`` + extracts first balanced JSON object).
    """
    del provider  # reserved for Stage 6 routing
    system = PLAN_SYSTEM + (extra_system or "") + _NO_THINK
    user = (
        f"## Ziel der Sitzung\n{goal or '(kein Ziel gesetzt — leite aus dem Zustand ab)'}\n\n"
        f"## Aktueller Zustand\n{state_summary}\n\n"
        f"## Verfügbare Tools\n{tools_summary or '(keine)'}\n\n"
        f"## Approach-Bibliothek\n{approaches_summary or '(leer)'}\n\n"
        f"Was ist der nächste sinnvolle Schritt? Antworte als JSON."
    )
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
        max_tokens=_MAX_TOKENS_STRUCTURED,
    )
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"_llm_plan: could not parse: {raw[:500]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"_llm_plan: not a dict: {raw[:500]}")
    # Coerce + default missing fields so downstream consumers don't crash.
    return {
        "next_step": str(parsed.get("next_step", "stop")),
        "target_anchor_id": str(parsed.get("target_anchor_id", "")),
        "tool": parsed.get("tool") if isinstance(parsed.get("tool"), str) else None,
        "approach_id": parsed.get("approach_id")
        if isinstance(parsed.get("approach_id"), str)
        else None,
        "reasoning": str(parsed.get("reasoning", "")),
        "expected_outcome": str(parsed.get("expected_outcome", "")),
        "confidence": float(parsed.get("confidence", 0.5))
        if isinstance(parsed.get("confidence"), (int, float))
        else 0.5,
        "fallback_plan": str(parsed.get("fallback_plan", "")),
    }


def _summarize_approaches_for_planner(data_root: Path) -> str:
    """One-line-per-approach listing of *enabled* approaches the Planner
    can pin. Disabled / tombstoned approaches are excluded."""
    from local_pdf.provenienz.approaches import read_approaches

    items = read_approaches(data_root, enabled_only=True)
    if not items:
        return ""
    return "\n".join(
        f"- {a.name} (für {', '.join(a.step_kinds)}): {a.extra_system[:120]}" for a in items
    )


def _llm_propose_stop(anchor_text: str, provider: str, *, extra_system: str = "") -> str:
    """Generate a short German sentence justifying a stop on the current node.

    The ``provider`` arg is plumbed-through but unused today. Tests
    monkey-patch this symbol on the module.
    """
    del provider  # reserved for Stage 6 routing
    system = PROPOSE_STOP_SYSTEM + (extra_system or "") + _NO_THINK
    user = f"Aktueller Knoten: {anchor_text}\nBegründung für Stopp:"
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
        max_tokens=_MAX_TOKENS_STRUCTURED,
    )
    raw = (completion.text or "").strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        raw = raw[1:-1].strip()
    raw = raw[:300]
    if not raw:
        raise RuntimeError("_llm_propose_stop: empty response from LLM")
    return raw


class ProposeStopRequest(BaseModel):
    anchor_node_id: str
    provider: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/propose-stop",
    status_code=201,
)
async def propose_stop(session_id: str, body: ProposeStopRequest, request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")

    nodes, _ = read_session(sd)
    anchor = next((n for n in nodes if n.node_id == body.anchor_node_id), None)
    if anchor is None:
        raise HTTPException(status_code=404, detail=f"anchor node not found: {body.anchor_node_id}")

    actor = resolve_provider(body.provider)
    extra_system, guidance_refs = _gather_guidance_via_skills(cfg.data_root, meta, "propose_stop")
    pre_reasoning = _llm_pre_reason(
        step_kind="propose_stop",
        step_label="Stopp vorschlagen",
        anchor_summary=str(anchor.payload.get("text", "") or anchor.payload.get("query", "")),
        session_goal=meta.goal,
        claim_goal=str(anchor.payload.get("goal", "")) if anchor.kind == "claim" else "",
    )
    full_system = PROPOSE_STOP_SYSTEM + (extra_system or "") + _NO_THINK
    try:
        reason_text = _llm_propose_stop(
            anchor.payload.get("text", ""),
            body.provider or "vllm",
            extra_system=extra_system,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM-Fehler: {exc}") from exc
    payload = ActionProposalPayload(
        step_kind="propose_stop",
        anchor_node_id=body.anchor_node_id,
        recommended=ActionOption(
            label="Sitzung schließen",
            args={"reason": reason_text, "close_session": True},
        ),
        alternatives=[
            ActionOption(
                label="Stopp annehmen, Sitzung offen lassen",
                args={"reason": reason_text, "close_session": False},
            ),
        ],
        reasoning="Manueller Vorschlag: Recherche abgeschlossen?",
        guidance_consulted=guidance_refs,
        pre_reasoning=pre_reasoning,
        system_prompt_used=full_system,
        tool_used=None,
    )
    landed = append_node(
        sd, build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    )
    return landed.__dict__


class DecideRequest(BaseModel):
    proposal_node_id: str
    accepted: Literal["recommended", "alt", "override"]
    alt_index: int | None = None
    reason: str | None = None
    override: str | None = None


def _override_summary(body: DecideRequest) -> str:
    """One-line override summary capped at 200 chars."""
    s = (body.override or "").strip().replace("\n", " ")
    return s[:200]


def _maybe_record_reason(
    cfg, body: DecideRequest, proposal: Node, step_kind: str, session_id: str
) -> None:
    """Append a Reason record if the user overrode with a non-empty reason.

    Stage 6.1: implicit guidance corpus. Skipped for recommended/alt
    paths and for overrides without a reason or override text.
    """
    if body.accepted != "override":
        return
    reason_text = (body.reason or "").strip()
    override_text = (body.override or "").strip()
    if not reason_text or not override_text:
        return
    rec_label = proposal.payload.get("recommended", {}).get("label", "")
    append_reason(
        cfg.data_root,
        Reason(
            reason_id=new_id(),
            step_kind=step_kind,
            session_id=session_id,
            proposal_id=body.proposal_node_id,
            proposal_summary=rec_label[:200],
            override_summary=_override_summary(body),
            reason_text=reason_text[:200],
            actor="human",
        ),
    )


def _resolve_claims(payload: dict, body: DecideRequest) -> list[str]:
    """Pick the list of claim strings to spawn, based on the user's
    decision against an extract_claims proposal."""
    if body.accepted == "recommended":
        return list(payload["recommended"]["args"].get("claims", []))
    if body.accepted == "alt":
        idx = body.alt_index or 0
        alts = payload.get("alternatives", [])
        if not (0 <= idx < len(alts)):
            raise HTTPException(
                status_code=400,
                detail=f"alt_index out of range: {idx}",
            )
        return list(alts[idx]["args"].get("claims", []))
    if body.accepted == "override":
        if not body.override:
            raise HTTPException(status_code=400, detail="override requires 'override' text")
        return [body.override]
    # Pydantic Literal already constrains this, but keep a safety net.
    raise HTTPException(status_code=400, detail=f"unknown accepted: {body.accepted}")


class PlanRequest(BaseModel):
    provider: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/plan",
    status_code=201,
)
async def plan(session_id: str, body: PlanRequest, request: Request) -> dict:
    """Planner-Schritt: liest Goal + Sitzungs-Zustand + Tool-Registry +
    Approach-Bibliothek, ruft den LLM-Planner und speichert das Ergebnis
    als ``plan_proposal``-Node (audit-trail bleibt komplett). Frontend
    rendert das Resultat als Vorschlag mit "Akzeptieren"-Button, der den
    empfohlenen Step automatisch auslöst.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    nodes, edges = read_session(sd)

    state_summary = _summarize_session_state(meta, nodes, edges)
    tools_summary = _summarize_tools_for_planner()
    approaches_summary = _summarize_approaches_for_planner(cfg.data_root)
    extra_system, guidance_refs = _gather_guidance_via_skills(cfg.data_root, meta, "plan")

    try:
        plan_dict = _llm_plan(
            meta.goal,
            state_summary,
            tools_summary,
            approaches_summary,
            body.provider or "vllm",
            extra_system=extra_system,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Planner-Fehler: {exc}") from exc

    actor = resolve_provider(body.provider)
    plan_node = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=session_id,
            kind="plan_proposal",
            payload={
                **plan_dict,
                "guidance_consulted": [g.__dict__ for g in guidance_refs],
            },
            actor=actor,
        ),
    )
    return plan_node.__dict__


class NextStepRequest(BaseModel):
    anchor_node_id: str
    provider: str | None = None


# ── Live-Run-Stream: phases of one /next-step execution ──────────────────
#
# Each /next-step call walks the same five phases. The streaming endpoint
# emits one PhaseEvent per phase boundary (started + completed/failed)
# plus a final CompleteEvent carrying the persisted Node. The
# non-streaming endpoint exhausts the same generator.


@dataclass
class PhaseEvent:
    phase: str
    status: Literal["started", "completed", "failed"]
    label: str
    ms_since_run_start: int
    ms_elapsed: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    type: Literal["phase"] = "phase"


@dataclass
class CompleteEvent:
    node: dict
    type: Literal["complete"] = "complete"


def _next_step_run(
    *,
    cfg: Any,
    session_id: str,
    body: NextStepRequest,
    anchor: Node,
    meta: SessionMeta,
    sd: Path,
) -> Iterator[PhaseEvent | CompleteEvent]:
    """Phase-by-phase execution of /next-step.

    Yields PhaseEvent on every started/completed boundary and a final
    CompleteEvent with the persisted Node. Both /next-step (drained)
    and /next-step/stream (forwarded as SSE) consume this iterator.
    """
    t0 = time.monotonic()

    def now_ms() -> int:
        return int((time.monotonic() - t0) * 1000)

    # ── Phase 1: gather_guidance (split passive vs active) ────────────
    p_start = time.monotonic()
    yield PhaseEvent(
        phase="gather_guidance",
        status="started",
        label="Heuristiken sammeln",
        ms_since_run_start=now_ms(),
    )
    extra_system, active_with_refs, guidance_refs = _gather_guidance_split(
        cfg.data_root, meta, "next_step", anchor=anchor
    )
    yield PhaseEvent(
        phase="gather_guidance",
        status="completed",
        label="Heuristiken sammeln",
        ms_since_run_start=now_ms(),
        ms_elapsed=int((time.monotonic() - p_start) * 1000),
        payload={
            "active_guidance": [g.__dict__ for g in guidance_refs],
            "extra_system_chars": len(extra_system or ""),
            "active_skill_count": len(active_with_refs),
        },
    )

    # ── Phase 2: gather_tools ─────────────────────────────────────────
    p_start = time.monotonic()
    yield PhaseEvent(
        phase="gather_tools",
        status="started",
        label="Tool-Hinweise sammeln",
        ms_since_run_start=now_ms(),
    )
    available_steps = _VALID_STEPS_FOR_KIND.get(anchor.kind, [])
    tools_summary = _summarize_tools_for_planner()
    yield PhaseEvent(
        phase="gather_tools",
        status="completed",
        label="Tool-Hinweise sammeln",
        ms_since_run_start=now_ms(),
        ms_elapsed=int((time.monotonic() - p_start) * 1000),
        payload={
            "available_steps": available_steps,
            "anchor_kind": anchor.kind,
            "tools_summary_chars": len(tools_summary or ""),
        },
    )

    # ── Phase 3: llm_call — Meta-Planner (Layer 1) ────────────────────
    full_system = NEXT_STEP_SYSTEM + (extra_system or "") + _NO_THINK
    anchor_preview = (
        str(anchor.payload.get("text", ""))[:300]
        or str(anchor.payload.get("query", ""))[:300]
        or ""
    )
    p_start = time.monotonic()
    yield PhaseEvent(
        phase="llm_call",
        status="started",
        label="L1 Meta-Planer LLM-Call",
        ms_since_run_start=now_ms(),
        payload={
            "model": get_default_model(),
            "system_prompt_chars": len(full_system),
            "system_prompt_preview": full_system[:800],
            "anchor_text_preview": anchor_preview,
            "session_goal": meta.goal,
        },
    )
    meta_plan = _llm_next_step(
        anchor,
        meta.goal,
        available_steps,
        tools_summary,
        extra_system=extra_system,
    )
    yield PhaseEvent(
        phase="llm_call",
        status="completed",
        label="L1 Meta-Planer LLM-Call",
        ms_since_run_start=now_ms(),
        ms_elapsed=int((time.monotonic() - p_start) * 1000),
        payload={
            "kind": meta_plan["kind"],
            "name": meta_plan.get("name", ""),
            "reasoning": meta_plan.get("reasoning", ""),
            "goal_alignment": meta_plan.get("goal_alignment", ""),
            "confidence": meta_plan.get("confidence", 0.0),
            "tool": meta_plan.get("tool"),
            "approach_id": meta_plan.get("approach_id"),
        },
    )

    # ── Phase 4..N: skill_call:idx — Layer 2 active specialists ───────
    skill_outputs: list[dict] = []
    for idx, (approach, _ref) in enumerate(active_with_refs):
        phase_id = f"skill_call:{idx}"
        label = f"L2 Spezialist: {approach.name}"
        p_start = time.monotonic()
        yield PhaseEvent(
            phase=phase_id,
            status="started",
            label=label,
            ms_since_run_start=now_ms(),
            payload={
                "approach_id": approach.approach_id,
                "approach_name": approach.name,
                "approach_extra_system_preview": approach.extra_system[:400],
            },
        )
        skill_out = _llm_active_skill(
            skill_name=approach.name,
            skill_extra_system=approach.extra_system,
            anchor=anchor,
            session_goal=meta.goal,
            available_steps=available_steps,
        )
        skill_out["skill_name"] = approach.name
        skill_out["approach_id"] = approach.approach_id
        skill_outputs.append(skill_out)
        yield PhaseEvent(
            phase=phase_id,
            status="completed",
            label=label,
            ms_since_run_start=now_ms(),
            ms_elapsed=int((time.monotonic() - p_start) * 1000),
            payload={
                "approach_id": approach.approach_id,
                "approach_name": approach.name,
                "reasoning": skill_out.get("reasoning", ""),
                "suggested_step": skill_out.get("suggested_step", ""),
                "confidence": skill_out.get("confidence", 0.0),
            },
        )

    # ── Phase N+1: coordinate — Layer 3 synthesis (only when L2 ran) ──
    if active_with_refs:
        p_start = time.monotonic()
        yield PhaseEvent(
            phase="coordinate",
            status="started",
            label="L3 Koordinator LLM-Call",
            ms_since_run_start=now_ms(),
            payload={
                "skill_count": len(skill_outputs),
                "meta_pick": f"{meta_plan.get('kind')}/{meta_plan.get('name', '')}",
                "skill_picks": [
                    f"{s.get('skill_name')}→{s.get('suggested_step') or '(leer)'}"
                    for s in skill_outputs
                ],
            },
        )
        plan = _llm_coordinator(
            meta_plan=meta_plan,
            skill_outputs=skill_outputs,
            anchor=anchor,
            session_goal=meta.goal,
            available_steps=available_steps,
            tools_summary=tools_summary,
        )
        yield PhaseEvent(
            phase="coordinate",
            status="completed",
            label="L3 Koordinator LLM-Call",
            ms_since_run_start=now_ms(),
            ms_elapsed=int((time.monotonic() - p_start) * 1000),
            payload={
                "kind": plan["kind"],
                "name": plan.get("name", ""),
                "reasoning": plan.get("reasoning", ""),
                "goal_alignment": plan.get("goal_alignment", ""),
                "confidence": plan.get("confidence", 0.0),
            },
        )
    else:
        plan = meta_plan

    # ── Phase: validate (clamp invalid step picks → manual_review) ────
    p_start = time.monotonic()
    yield PhaseEvent(
        phase="validate",
        status="started",
        label="Step-Wahl validieren",
        ms_since_run_start=now_ms(),
    )
    invalid_step_picked: str | None = None
    if (
        plan["kind"] == "executable_step"
        and available_steps
        and plan["name"] not in available_steps
    ):
        invalid_step_picked = plan["name"]
        plan = {
            **plan,
            "kind": "manual_review",
            "name": "Ungültige Step-Wahl",
            "description": (
                f"Der Agent hat '{invalid_step_picked}' für einen Knoten vom Typ "
                f"'{anchor.kind}' gewählt — das steht aber nicht in den "
                f"verfügbaren Steps ({', '.join(available_steps)}). "
                "Wahrscheinlich LLM-Halluzination. Bitte manuell prüfen "
                "oder den Vorschlag verwerfen."
            ),
        }
    yield PhaseEvent(
        phase="validate",
        status="completed",
        label="Step-Wahl validieren",
        ms_since_run_start=now_ms(),
        ms_elapsed=int((time.monotonic() - p_start) * 1000),
        payload={
            "ok": invalid_step_picked is None,
            "demoted_from": invalid_step_picked,
            "final_kind": plan["kind"],
            "final_name": plan.get("name", ""),
        },
    )

    # ── Phase: persist ────────────────────────────────────────────────
    p_start = time.monotonic()
    yield PhaseEvent(
        phase="persist",
        status="started",
        label="Knoten schreiben",
        ms_since_run_start=now_ms(),
    )
    actor = resolve_provider(body.provider)
    out_kind = {
        "executable_step": "plan_proposal",
        "capability_request": "capability_request",
        "manual_review": "manual_review",
    }[plan["kind"]]
    audit_label = (
        "Was als nächstes? (Multi-Agent: Meta + L2 Skills + Coordinator)"
        if active_with_refs
        else "Was als nächstes? (POST /next-step → _llm_next_step)"
    )
    audit = {
        "source_label": audit_label,
        "system_prompt_used": full_system,
        "input_summary": {
            "anchor_kind": anchor.kind,
            "anchor_text_preview": anchor_preview,
            "session_goal": meta.goal,
            "available_steps": available_steps,
            "tools_summary": tools_summary,
        },
        "guidance_consulted": [g.__dict__ for g in guidance_refs],
        # Multi-agent transparency: when active skills fired, persist
        # the meta-plan + each skill's verbatim output so the audit
        # panel can reconstruct the full L1+L2+L3 chain. Empty list
        # when no active skills participated.
        "meta_plan": dict(meta_plan) if active_with_refs else None,
        "skill_outputs": skill_outputs,
    }
    node = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=session_id,
            kind=out_kind,
            payload={
                **plan,
                "anchor_node_id": body.anchor_node_id,
                "audit": audit,
            },
            actor=actor,
        ),
    )
    yield PhaseEvent(
        phase="persist",
        status="completed",
        label="Knoten schreiben",
        ms_since_run_start=now_ms(),
        ms_elapsed=int((time.monotonic() - p_start) * 1000),
        payload={"node_id": node.node_id, "node_kind": out_kind},
    )

    yield CompleteEvent(node=node.__dict__)


def _resolve_next_step_inputs(
    cfg: Any, session_id: str, body: NextStepRequest
) -> tuple[Path, SessionMeta, Node]:
    """Pre-flight resolution shared by both /next-step variants.

    Raises HTTPException 404 if session/meta/anchor are missing.
    """
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    nodes, _ = read_session(sd)
    anchor = next((n for n in nodes if n.node_id == body.anchor_node_id), None)
    if anchor is None:
        raise HTTPException(status_code=404, detail=f"anchor node not found: {body.anchor_node_id}")
    return sd, meta, anchor


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/next-step",
    status_code=201,
)
async def next_step(session_id: str, body: NextStepRequest, request: Request) -> dict:
    """Open-ended planner — the primary "Was als nächstes?" surface.

    Drains the phase generator and returns the persisted Node. Use
    /next-step/stream for the live-run UI variant.
    """
    cfg = request.app.state.config
    sd, meta, anchor = _resolve_next_step_inputs(cfg, session_id, body)
    final: dict | None = None
    for ev in _next_step_run(
        cfg=cfg, session_id=session_id, body=body, anchor=anchor, meta=meta, sd=sd
    ):
        if isinstance(ev, CompleteEvent):
            final = ev.node
    assert final is not None, "next_step_run terminated without a CompleteEvent"
    return final


@router.post("/api/admin/provenienz/sessions/{session_id}/next-step/stream")
async def next_step_stream(
    session_id: str, body: NextStepRequest, request: Request
) -> StreamingResponse:
    """SSE variant of /next-step — emits one event per phase boundary
    so the frontend can render a live-run panel.

    Event types:
      - ``phase``    : PhaseEvent (started/completed/failed)
      - ``complete`` : CompleteEvent with the persisted Node
      - ``error``    : unexpected exception during run
    """
    cfg = request.app.state.config
    sd, meta, anchor = _resolve_next_step_inputs(cfg, session_id, body)

    def event_stream() -> Iterator[str]:
        try:
            for ev in _next_step_run(
                cfg=cfg,
                session_id=session_id,
                body=body,
                anchor=anchor,
                meta=meta,
                sd=sd,
            ):
                if isinstance(ev, PhaseEvent):
                    yield f"event: phase\ndata: {json.dumps(asdict(ev), ensure_ascii=False)}\n\n"
                else:
                    yield f"event: complete\ndata: {json.dumps(asdict(ev), ensure_ascii=False)}\n\n"
        except Exception as exc:
            _log.exception("next_step_stream failed")
            err = {"type": "error", "message": str(exc)}
            yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/decide",
    status_code=201,
)
async def decide(session_id: str, body: DecideRequest, request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")

    nodes, _ = read_session(sd)
    proposal = next((n for n in nodes if n.node_id == body.proposal_node_id), None)
    if proposal is None:
        raise HTTPException(
            status_code=404, detail=f"proposal node not found: {body.proposal_node_id}"
        )
    if proposal.kind != "action_proposal":
        raise HTTPException(
            status_code=400,
            detail=f"node is not an action_proposal (kind={proposal.kind})",
        )

    # 1. Append the decision node + decided-by edge.
    decision = Node(
        node_id=new_id(),
        session_id=session_id,
        kind="decision",
        payload={
            "accepted": body.accepted,
            "alt_index": body.alt_index,
            "reason": body.reason,
            "override": body.override,
        },
        actor="human",
    )
    decision_landed = append_node(sd, decision)
    spawned_edges: list[Edge] = []
    e_decided = append_edge(
        sd,
        Edge(
            edge_id=new_id(),
            session_id=session_id,
            from_node=decision_landed.node_id,
            to_node=proposal.node_id,
            kind="decided-by",
            reason=None,
            actor="human",
        ),
    )
    spawned_edges.append(e_decided)

    # 2. Dispatch on step_kind.
    step_kind = proposal.payload["step_kind"]
    spawned_nodes: list[Node] = []

    if step_kind == "extract_claims":
        anchor_chunk = proposal.payload["anchor_node_id"]
        claim_texts = _resolve_claims(proposal.payload, body)
        claim_actor = "human" if body.accepted == "override" else proposal.actor
        # Batched per-claim goal extraction. Best-effort: failure → "" goals.
        claim_meta = read_meta(sd)
        session_goal_for_extract = claim_meta.goal if claim_meta else ""
        # Pass the source chunk text along so the LLM can form
        # context-aware research questions ("Welche Wärmeleistung hat
        # TRINO?" rather than "Welche Wärmeleistung?").
        chunk_for_goals = next((n for n in nodes if n.node_id == anchor_chunk), None)
        chunk_text_for_goals = (
            str(chunk_for_goals.payload.get("text", "")) if chunk_for_goals is not None else ""
        )
        try:
            claim_goals = _llm_extract_claim_goals(
                claim_texts,
                session_goal_for_extract,
                "vllm",
                chunk_text=chunk_text_for_goals,
            )
        except Exception as exc:
            _log.warning("extract_claim_goals failed: %s", exc)
            claim_goals = [""] * len(claim_texts)
        # Auto-extract per-claim background from the chunk: 2-4 sentences
        # of context the claim doesn't carry on its own. Best-effort.
        # User can override the prompt via an Approach with
        # step_kind="extract_claim_background".
        bg_extra_system = ""
        if claim_meta is not None:
            bg_extra_system, _ = _gather_guidance_via_skills(
                cfg.data_root, claim_meta, "extract_claim_background"
            )
        try:
            claim_backgrounds = _llm_extract_claim_backgrounds(
                claim_texts,
                chunk_text_for_goals,
                extra_system=bg_extra_system,
            )
        except Exception as exc:
            _log.warning("extract_claim_backgrounds failed: %s", exc)
            claim_backgrounds = [""] * len(claim_texts)
        for idx, ct in enumerate(claim_texts):
            goal_for_claim = claim_goals[idx] if idx < len(claim_goals) else ""
            claim = append_node(
                sd,
                Node(
                    node_id=new_id(),
                    session_id=session_id,
                    kind="claim",
                    payload={
                        "text": ct,
                        "source_node_id": anchor_chunk,
                        "goal": goal_for_claim,
                    },
                    actor=claim_actor,
                ),
            )
            spawned_nodes.append(claim)
            spawned_edges.append(
                append_edge(
                    sd,
                    Edge(
                        edge_id=new_id(),
                        session_id=session_id,
                        from_node=claim.node_id,
                        to_node=anchor_chunk,
                        kind="extracts-from",
                        reason=None,
                        actor=claim_actor,
                    ),
                )
            )
            spawned_edges.append(
                append_edge(
                    sd,
                    Edge(
                        edge_id=new_id(),
                        session_id=session_id,
                        from_node=decision_landed.node_id,
                        to_node=claim.node_id,
                        kind="triggers",
                        reason=None,
                        actor="human",
                    ),
                )
            )
            # Per-claim chunk-comprehension Node. Empty → skip (LLM said
            # the chunk adds nothing, or the call failed).
            bg_text = claim_backgrounds[idx] if idx < len(claim_backgrounds) else ""
            if bg_text and bg_text.strip():
                bg_node = append_node(
                    sd,
                    Node(
                        node_id=new_id(),
                        session_id=session_id,
                        kind="claim_background",
                        payload={
                            "text": bg_text.strip(),
                            "claim_node_id": claim.node_id,
                            "source_chunk_node_id": anchor_chunk,
                        },
                        actor="system",
                    ),
                )
                spawned_nodes.append(bg_node)
                spawned_edges.append(
                    append_edge(
                        sd,
                        Edge(
                            edge_id=new_id(),
                            session_id=session_id,
                            from_node=bg_node.node_id,
                            to_node=claim.node_id,
                            kind="enriches",
                            reason=None,
                            actor="system",
                        ),
                    )
                )
        _maybe_record_reason(cfg, body, proposal, step_kind, session_id)
        # Auto-extract the session goal off the *first* claim. Best-effort —
        # failures are logged + swallowed inside the helper.
        if claim_texts:
            decide_meta = read_meta(sd)
            if decide_meta is not None:
                _maybe_extract_goal(cfg, sd, decide_meta, claim_texts[0])
        return {
            "decision_node": decision_landed.__dict__,
            "spawned_nodes": [n.__dict__ for n in spawned_nodes],
            "spawned_edges": [e.__dict__ for e in spawned_edges],
        }

    if step_kind == "decompose_hit":
        anchor_sr = proposal.payload["anchor_node_id"]
        sub_texts = []
        if body.accepted == "recommended":
            sub_texts = list(
                proposal.payload["recommended"]["args"].get("sub_statements", []) or []
            )
        sub_actor = "human" if body.accepted == "override" else proposal.actor
        for sub_text in sub_texts:
            if not isinstance(sub_text, str) or not sub_text.strip():
                continue
            sub_node = append_node(
                sd,
                Node(
                    node_id=new_id(),
                    session_id=session_id,
                    kind="sub_statement",
                    payload={
                        "text": sub_text.strip(),
                        "parent_search_result_id": anchor_sr,
                    },
                    actor=sub_actor,
                ),
            )
            spawned_nodes.append(sub_node)
            spawned_edges.append(
                append_edge(
                    sd,
                    Edge(
                        edge_id=new_id(),
                        session_id=session_id,
                        from_node=sub_node.node_id,
                        to_node=anchor_sr,
                        kind="extracts-from",
                        reason=None,
                        actor=sub_actor,
                    ),
                )
            )
            spawned_edges.append(
                append_edge(
                    sd,
                    Edge(
                        edge_id=new_id(),
                        session_id=session_id,
                        from_node=decision_landed.node_id,
                        to_node=sub_node.node_id,
                        kind="triggers",
                        reason=None,
                        actor="human",
                    ),
                )
            )
        _maybe_record_reason(cfg, body, proposal, step_kind, session_id)
        return {
            "decision_node": decision_landed.__dict__,
            "spawned_nodes": [n.__dict__ for n in spawned_nodes],
            "spawned_edges": [e.__dict__ for e in spawned_edges],
        }

    if step_kind == "formulate_task":
        anchor_claim_id = proposal.payload["anchor_node_id"]
        if body.accepted == "recommended":
            query = proposal.payload["recommended"]["args"].get("query", "")
        elif body.accepted == "alt":
            idx = body.alt_index or 0
            alts = proposal.payload.get("alternatives", [])
            if not (0 <= idx < len(alts)):
                raise HTTPException(status_code=400, detail=f"alt_index out of range: {idx}")
            query = alts[idx]["args"].get("query", "")
        else:  # override
            if not body.override:
                raise HTTPException(status_code=400, detail="override requires 'override' text")
            query = body.override
        if not query.strip():
            raise HTTPException(status_code=400, detail="query is empty")
        task_actor = "human" if body.accepted == "override" else proposal.actor
        task_node = append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=session_id,
                kind="task",
                payload={"query": query, "focus_claim_id": anchor_claim_id},
                actor=task_actor,
            ),
        )
        spawned_nodes.append(task_node)
        spawned_edges.append(
            append_edge(
                sd,
                Edge(
                    edge_id=new_id(),
                    session_id=session_id,
                    from_node=task_node.node_id,
                    to_node=anchor_claim_id,
                    kind="verifies",
                    reason=None,
                    actor=task_actor,
                ),
            )
        )
        spawned_edges.append(
            append_edge(
                sd,
                Edge(
                    edge_id=new_id(),
                    session_id=session_id,
                    from_node=decision_landed.node_id,
                    to_node=task_node.node_id,
                    kind="triggers",
                    reason=None,
                    actor="human",
                ),
            )
        )
        _maybe_record_reason(cfg, body, proposal, step_kind, session_id)
        return {
            "decision_node": decision_landed.__dict__,
            "spawned_nodes": [n.__dict__ for n in spawned_nodes],
            "spawned_edges": [e.__dict__ for e in spawned_edges],
        }

    if step_kind == "search":
        anchor_task_id = proposal.payload["anchor_node_id"]
        if body.accepted == "override":
            raise HTTPException(
                status_code=400,
                detail="override path not supported for search step (v1)",
            )
        if body.accepted == "recommended":
            hits = proposal.payload["recommended"]["args"].get("hits", [])
        else:  # alt
            idx = body.alt_index or 0
            alts = proposal.payload.get("alternatives", [])
            if not (0 <= idx < len(alts)):
                raise HTTPException(status_code=400, detail=f"alt_index out of range: {idx}")
            hits = alts[idx]["args"].get("hits", [])
        for h in hits:
            sr = append_node(
                sd,
                Node(
                    node_id=new_id(),
                    session_id=session_id,
                    kind="search_result",
                    payload={**h, "task_node_id": anchor_task_id},
                    actor=proposal.actor,
                ),
            )
            spawned_nodes.append(sr)
            spawned_edges.append(
                append_edge(
                    sd,
                    Edge(
                        edge_id=new_id(),
                        session_id=session_id,
                        from_node=sr.node_id,
                        to_node=anchor_task_id,
                        kind="candidates-for",
                        reason=None,
                        actor=proposal.actor,
                    ),
                )
            )
            spawned_edges.append(
                append_edge(
                    sd,
                    Edge(
                        edge_id=new_id(),
                        session_id=session_id,
                        from_node=decision_landed.node_id,
                        to_node=sr.node_id,
                        kind="triggers",
                        reason=None,
                        actor="human",
                    ),
                )
            )
        return {
            "decision_node": decision_landed.__dict__,
            "spawned_nodes": [n.__dict__ for n in spawned_nodes],
            "spawned_edges": [e.__dict__ for e in spawned_edges],
        }

    if step_kind == "evaluate":
        anchor_sr_id = proposal.payload["anchor_node_id"]
        rec_args = proposal.payload["recommended"]["args"]
        if body.accepted == "recommended":
            args = rec_args
        elif body.accepted == "alt":
            idx = body.alt_index or 0
            alts = proposal.payload.get("alternatives", [])
            if not (0 <= idx < len(alts)):
                raise HTTPException(status_code=400, detail=f"alt_index out of range: {idx}")
            args = alts[idx]["args"]
        else:  # override
            if not body.override:
                raise HTTPException(status_code=400, detail="override requires 'override' text")
            args = {
                "verdict": "manual",
                "confidence": 1.0,
                "reasoning": body.override,
                "against_claim_id": rec_args.get("against_claim_id"),
            }
        eval_actor = "human" if body.accepted == "override" else proposal.actor
        # Run the reactive-capability scan FIRST so the per-approach
        # summary (matched + considered-but-not-matched) lands on the
        # evaluation Node payload itself. The user can then see "0/3
        # capabilities triggered" even when no gate is shown, plus the
        # *reasons* per non-match for debugging.
        capability_scan: list[dict] = []
        capability_matches: list[tuple] = []
        try:
            sentence_texts_for_scan = [
                str((s or {}).get("text", ""))
                for s in args.get("sentences", []) or []
                if isinstance(s, dict)
            ]
            sr_for_claim = next((n for n in nodes if n.node_id == anchor_sr_id), None)
            claim_id_for_scan = args.get("against_claim_id") or ""
            if not claim_id_for_scan and sr_for_claim is not None:
                task_id_scan = sr_for_claim.payload.get("task_node_id")
                tnode_scan = (
                    next((n for n in nodes if n.node_id == task_id_scan), None)
                    if task_id_scan
                    else None
                )
                claim_id_for_scan = (
                    str(tnode_scan.payload.get("focus_claim_id")) if tnode_scan else ""
                )
            cnode_scan = (
                next((n for n in nodes if n.node_id == claim_id_for_scan), None)
                if claim_id_for_scan
                else None
            )
            claim_text_for_scan = (
                str(cnode_scan.payload.get("text", ""))
                if cnode_scan is not None and cnode_scan.kind == "claim"
                else ""
            )
            all_apps_for_scan = read_approaches(cfg.data_root, enabled_only=True)
            verdict_str = str(args.get("verdict", ""))
            capability_matches = scan_capabilities(
                all_apps_for_scan,
                verdict=verdict_str,
                sentence_texts=sentence_texts_for_scan,
                claim_text=claim_text_for_scan,
            )
            # Build per-approach summary covering EVERY enabled approach
            # with non-empty triggers, matched or not. Lets the eval
            # panel show the full skill-scan, not just the winners.
            matched_ids = set()
            for top, _, subs in capability_matches:
                matched_ids.add(top.approach_id)
                for sub, _ in subs:
                    matched_ids.add(sub.approach_id)
            for app in all_apps_for_scan:
                if not app.triggers:
                    continue
                ok, reasons = match_triggers(
                    app.triggers,
                    verdict=verdict_str,
                    sentence_texts=sentence_texts_for_scan,
                    claim_text=claim_text_for_scan,
                )
                capability_scan.append(
                    {
                        "approach_id": app.approach_id,
                        "name": app.name,
                        "parent_capability": app.parent_capability or "",
                        "matched": ok and app.approach_id in matched_ids,
                        "reasons": reasons,
                    }
                )
        except Exception as exc:
            _log.warning("capability scan pre-eval failed: %s", exc)
            capability_scan = []
            capability_matches = []

        eval_node = append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=session_id,
                kind="evaluation",
                payload={
                    "verdict": args["verdict"],
                    "confidence": args["confidence"],
                    "reasoning": args["reasoning"],
                    "against_claim_id": args["against_claim_id"],
                    "search_result_node_id": anchor_sr_id,
                    # Carry the per-sentence enumeration through to the
                    # evaluation node so the canvas tile / panel can
                    # render the full audit without re-loading the
                    # parent action_proposal.
                    "sentences": args.get("sentences", []),
                    "proposal_node_id": proposal.node_id,
                    # Per-approach scan: which capabilities were
                    # considered (have triggers != {}) and which fired.
                    # Always present, even when empty / no matches.
                    "capability_scan": capability_scan,
                },
                actor=eval_actor,
            ),
        )
        spawned_nodes.append(eval_node)
        spawned_edges.append(
            append_edge(
                sd,
                Edge(
                    edge_id=new_id(),
                    session_id=session_id,
                    from_node=eval_node.node_id,
                    to_node=anchor_sr_id,
                    kind="evaluates",
                    reason=None,
                    actor=eval_actor,
                ),
            )
        )
        spawned_edges.append(
            append_edge(
                sd,
                Edge(
                    edge_id=new_id(),
                    session_id=session_id,
                    from_node=decision_landed.node_id,
                    to_node=eval_node.node_id,
                    kind="triggers",
                    reason=None,
                    actor="human",
                ),
            )
        )
        # ── Capability gate (only if at least one match) ─────────────────
        # The scan itself ran above (pre-eval_node) so the per-approach
        # summary is on eval_node.payload. Here we just persist the gate
        # Node when at least one approach actually fired, so the canvas
        # shows the orange "Re-evaluate?" tile.
        if capability_matches:
            try:
                rules_preview_parts: list[str] = []
                detected_summary: list[dict] = []
                cap_ids: list[str] = []
                for top, top_reasons, subs in capability_matches:
                    cap_ids.append(top.approach_id)
                    detected_summary.append(
                        {
                            "name": top.name,
                            "approach_id": top.approach_id,
                            "kind": "top",
                            "reasons": top_reasons,
                        }
                    )
                    if top.domain_rules:
                        rules_preview_parts.append(f"## {top.name}\n{top.domain_rules}")
                    for sub, sub_reasons in subs:
                        cap_ids.append(sub.approach_id)
                        detected_summary.append(
                            {
                                "name": sub.name,
                                "approach_id": sub.approach_id,
                                "kind": "sub",
                                "parent": top.name,
                                "reasons": sub_reasons,
                            }
                        )
                        if sub.domain_rules:
                            rules_preview_parts.append(
                                f"## {sub.name} (sub von {top.name})\n{sub.domain_rules}"
                            )
                gate_node = append_node(
                    sd,
                    Node(
                        node_id=new_id(),
                        session_id=session_id,
                        kind="capability_gate",
                        payload={
                            "evaluation_node_id": eval_node.node_id,
                            "anchor_node_id": eval_node.node_id,
                            "search_result_node_id": anchor_sr_id,
                            "claim_node_id": claim_id_for_scan,
                            "detected": detected_summary,
                            "capability_ids": cap_ids,
                            "loaded_rules_preview": "\n\n".join(rules_preview_parts),
                            "status": "pending",
                        },
                        actor="system",
                    ),
                )
                spawned_nodes.append(gate_node)
                spawned_edges.append(
                    append_edge(
                        sd,
                        Edge(
                            edge_id=new_id(),
                            session_id=session_id,
                            from_node=eval_node.node_id,
                            to_node=gate_node.node_id,
                            kind="triggers-capability",
                            reason=None,
                            actor="system",
                        ),
                    )
                )
            except Exception as exc:
                _log.warning("capability gate persist failed: %s", exc)
        _maybe_record_reason(cfg, body, proposal, step_kind, session_id)
        return {
            "decision_node": decision_landed.__dict__,
            "spawned_nodes": [n.__dict__ for n in spawned_nodes],
            "spawned_edges": [e.__dict__ for e in spawned_edges],
        }

    if step_kind == "propose_stop":
        anchor_id = proposal.payload["anchor_node_id"]
        if body.accepted == "recommended":
            args = proposal.payload["recommended"]["args"]
        elif body.accepted == "alt":
            idx = body.alt_index or 0
            alts = proposal.payload.get("alternatives", [])
            if not (0 <= idx < len(alts)):
                raise HTTPException(status_code=400, detail=f"alt_index out of range: {idx}")
            args = alts[idx]["args"]
        else:  # override
            if not body.override:
                raise HTTPException(status_code=400, detail="override requires 'override' text")
            args = {"reason": body.override, "close_session": True}
        stop_actor = "human" if body.accepted == "override" else proposal.actor
        stop_node = append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=session_id,
                kind="stop_proposal",
                payload={
                    "reason": args["reason"],
                    "close_session": args["close_session"],
                    "anchor_node_id": anchor_id,
                },
                actor=stop_actor,
            ),
        )
        spawned_nodes.append(stop_node)
        spawned_edges.append(
            append_edge(
                sd,
                Edge(
                    edge_id=new_id(),
                    session_id=session_id,
                    from_node=decision_landed.node_id,
                    to_node=stop_node.node_id,
                    kind="triggers",
                    reason=None,
                    actor="human",
                ),
            )
        )
        if args["close_session"]:
            meta = read_meta(sd)
            if meta is not None:
                write_meta(sd, SessionMeta(**{**meta.__dict__, "status": "closed"}))
        _maybe_record_reason(cfg, body, proposal, step_kind, session_id)
        return {
            "decision_node": decision_landed.__dict__,
            "spawned_nodes": [n.__dict__ for n in spawned_nodes],
            "spawned_edges": [e.__dict__ for e in spawned_edges],
        }

    raise HTTPException(status_code=501, detail=f"step_kind not yet handled: {step_kind}")
