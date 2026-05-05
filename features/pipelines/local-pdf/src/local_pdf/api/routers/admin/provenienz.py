"""Provenienz tab routes — sessions CRUD (Stage 1).

Step + decision routes land in later stages.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path  # noqa: TC003
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from local_pdf.provenienz.llm import (
    ActionOption,
    ActionProposalPayload,
    build_proposal_node,
    resolve_provider,
)
from local_pdf.provenienz.searcher import InDocSearcher
from local_pdf.provenienz.storage import (
    Edge,
    Node,
    SessionMeta,
    append_edge,
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


def _llm_extract_claims(chunk_text: str, provider: str) -> list[str]:
    """Real LLM call — wired in Stage 5.5. v1 is a sentence-split heuristic
    so the route is testable without spinning up vLLM or Azure.

    Tests monkey-patch this symbol on the module.
    """
    sentences = [s.strip() for s in chunk_text.split(".") if len(s.strip()) > 8]
    return sentences[:5]


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
    claims = _llm_extract_claims(chunk.payload.get("text", ""), body.provider or "vllm")

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
        guidance_consulted=[],
    )
    node = build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    landed = append_node(sd, node)
    return landed.__dict__


def _llm_formulate_task(claim_text: str, provider: str) -> str:
    """Real LLM call lands in Stage 5.5. v1 stub: pass-through, trimmed.

    Tests monkey-patch this symbol on the module.
    """
    return (claim_text or "").strip()[:200]


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

    nodes, _ = read_session(sd)
    claim = next((n for n in nodes if n.node_id == body.claim_node_id), None)
    if claim is None:
        raise HTTPException(status_code=404, detail=f"claim node not found: {body.claim_node_id}")
    if claim.kind != "claim":
        raise HTTPException(status_code=400, detail=f"anchor must be claim, got kind={claim.kind}")

    actor = resolve_provider(body.provider)
    query = _llm_formulate_task(claim.payload.get("text", ""), body.provider or "vllm")
    payload = ActionProposalPayload(
        step_kind="formulate_task",
        anchor_node_id=body.claim_node_id,
        recommended=ActionOption(label=f"Suchanfrage: {query!r}", args={"query": query}),
        alternatives=[
            ActionOption(label="Eigene Suchanfrage formulieren", args={"query": ""}),
        ],
        reasoning="Heuristik v0: Claim-Text als Suchanfrage.",
        guidance_consulted=[],
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


def _llm_evaluate(claim_text: str, candidate_chunk_text: str, provider: str) -> dict:
    """Real LLM call lands in Stage 5.5. v1 stub returns an unknown
    verdict so the route + decide dispatch are testable without a
    running model.

    Tests monkey-patch this symbol on the module.
    """
    return {"verdict": "unknown", "confidence": 0.5, "reasoning": "stub: no LLM"}


class EvaluateStepRequest(BaseModel):
    search_result_node_id: str
    against_claim_id: str
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

    nodes, _ = read_session(sd)
    sr = next((n for n in nodes if n.node_id == body.search_result_node_id), None)
    if sr is None:
        raise HTTPException(
            status_code=404,
            detail=f"search_result node not found: {body.search_result_node_id}",
        )
    if sr.kind != "search_result":
        raise HTTPException(
            status_code=400,
            detail=f"anchor must be search_result, got kind={sr.kind}",
        )
    claim = next((n for n in nodes if n.node_id == body.against_claim_id), None)
    if claim is None:
        raise HTTPException(
            status_code=404, detail=f"claim node not found: {body.against_claim_id}"
        )
    if claim.kind != "claim":
        raise HTTPException(
            status_code=400, detail=f"against_claim_id must be claim, got kind={claim.kind}"
        )

    actor = resolve_provider(body.provider)
    verdict_payload = _llm_evaluate(
        claim.payload.get("text", ""),
        sr.payload.get("text", ""),
        body.provider or "vllm",
    )
    verdict = verdict_payload["verdict"]
    confidence = verdict_payload["confidence"]
    reasoning = verdict_payload["reasoning"]

    payload = ActionProposalPayload(
        step_kind="evaluate",
        anchor_node_id=body.search_result_node_id,
        recommended=ActionOption(
            label=f"{verdict} (conf {confidence:.2f})",
            args={
                "verdict": verdict,
                "confidence": confidence,
                "reasoning": reasoning,
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
        guidance_consulted=[],
    )
    landed = append_node(
        sd, build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    )
    return landed.__dict__


def _llm_propose_stop(anchor_text: str, provider: str) -> str:
    """Real LLM call lands in Stage 5.5. v1 stub returns a fixed
    reasoning text so the route + decide dispatch are testable
    without a running model.

    Tests monkey-patch this symbol on the module.
    """
    return "Quelle gefunden"


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

    nodes, _ = read_session(sd)
    anchor = next((n for n in nodes if n.node_id == body.anchor_node_id), None)
    if anchor is None:
        raise HTTPException(status_code=404, detail=f"anchor node not found: {body.anchor_node_id}")

    actor = resolve_provider(body.provider)
    reason_text = _llm_propose_stop(anchor.payload.get("text", ""), body.provider or "vllm")
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
        guidance_consulted=[],
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
        for ct in claim_texts:
            claim = append_node(
                sd,
                Node(
                    node_id=new_id(),
                    session_id=session_id,
                    kind="claim",
                    payload={"text": ct, "source_node_id": anchor_chunk},
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
        return {
            "decision_node": decision_landed.__dict__,
            "spawned_nodes": [n.__dict__ for n in spawned_nodes],
            "spawned_edges": [e.__dict__ for e in spawned_edges],
        }

    raise HTTPException(status_code=501, detail=f"step_kind not yet handled: {step_kind}")
