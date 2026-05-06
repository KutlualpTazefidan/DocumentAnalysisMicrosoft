"""Provenienz tab routes — sessions CRUD (Stage 1).

Step + decision routes land in later stages.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path  # noqa: TC003
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from llm_clients.base import Message
from pydantic import BaseModel

from local_pdf.llm import get_default_model, get_llm_client
from local_pdf.provenienz.approaches import get_approach
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
    new_id,
    read_meta,
    read_session,
    session_dir,
    write_meta,
)
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


def _strip_json_fence(s: str) -> str:
    """Strip ```json ... ``` or ``` ... ``` fences and extract the first
    top-level JSON value (object or array) from prose-wrapped output.

    Small models routinely return ``Hier ist die Antwort: {...}`` or wrap
    JSON in code fences; we want both shapes to parse.
    """
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


def _gather_guidance(
    data_root: Path, meta: SessionMeta, step_kind: str
) -> tuple[str, list[GuidanceRef]]:
    """Combine pinned approaches (explicit) with the reason corpus
    (implicit). Approaches come first as named overlays; reasons come
    after as "lessons learned" examples.

    Approaches are filtered to those that are enabled and have
    *step_kind* in their step_kinds list. Disabled or non-matching
    pinned approaches are silently skipped.
    """
    blocks: list[str] = []
    refs: list[GuidanceRef] = []

    if meta.pinned_approach_ids:
        approach_block_lines: list[str] = []
        for app_id in meta.pinned_approach_ids:
            a = get_approach(data_root, app_id)
            if a is None or not a.enabled:
                continue
            if step_kind not in a.step_kinds:
                continue
            approach_block_lines.append(f"## Vorgehen: {a.name}\n{a.extra_system}")
            refs.append(
                GuidanceRef(
                    kind="approach",
                    id=a.approach_id,
                    summary=a.name[:80],
                )
            )
        if approach_block_lines:
            blocks.append("\n\n" + "\n\n".join(approach_block_lines))

    reason_block, reason_refs = _gather_reason_guidance(data_root, step_kind)
    if reason_block:
        blocks.append(reason_block)
        refs.extend(reason_refs)

    return ("".join(blocks), refs)


def _llm_extract_claims(chunk_text: str, provider: str, *, extra_system: str = "") -> list[str]:
    """Extract verifiable claims from a chunk via the configured LLM.

    The ``provider`` arg is plumbed-through but unused today — per-step
    provider routing lands in Stage 6 with the reason corpus. Tests
    monkey-patch this symbol on the module.
    """
    del provider  # reserved for Stage 6 routing
    system = (
        "Du extrahierst überprüfbare Aussagen aus einem Textabschnitt. Eine Aussage "
        "ist eine spezifische, faktische Behauptung — Zahl, Datum, Eigenschaft, "
        "Beziehung. Antworte ausschließlich als JSON-Array von Strings, ohne Vor- "
        "oder Nachtext. Keine Aufzählungen, keine Markdown-Codeblöcke."
    )
    if extra_system:
        system = system + extra_system
    user = f"Textabschnitt:\n{chunk_text}\n\nGib das JSON-Array der Aussagen zurück."
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
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
    extra_system, guidance_refs = _gather_guidance(cfg.data_root, meta, "extract_claims")
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
    system = (
        "Du formulierst eine knappe Suchanfrage (max. 12 Wörter, deutsch oder "
        "englisch je nach Claim-Sprache), mit der die Quelle einer Aussage in "
        "einem Korpus gefunden werden kann. Antworte ausschließlich mit der "
        "Suchanfrage selbst — keine Anführungszeichen, keine Erklärung, kein "
        "Zeilenumbruch davor oder danach."
    )
    if extra_system:
        system = system + extra_system
    user = f"Aussage: {claim_text}\nSuchanfrage:"
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
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
    extra_system, guidance_refs = _gather_guidance(cfg.data_root, meta, "formulate_task")
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
    system = (
        "Du bewertest, ob ein Kandidaten-Textabschnitt die Quelle einer Aussage "
        "ist. Antworte ausschließlich als JSON-Objekt mit den Feldern verdict "
        "(eines von: 'likely-source', 'partial-support', 'unrelated', "
        "'contradicts'), confidence (Zahl 0.0-1.0) und reasoning (kurzer "
        "deutscher Satz). Kein Vor- oder Nachtext, keine Codeblöcke."
    )
    if extra_system:
        system = system + extra_system
    user = f"Aussage:\n{claim_text}\n\nKandidat:\n{candidate_chunk_text}\n\nJSON:"
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
    )
    raw = completion.text or ""
    cleaned = _strip_json_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"_llm_evaluate: could not parse: {raw[:500]}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"_llm_evaluate: could not parse: {raw[:500]}")
    verdict = parsed.get("verdict")
    confidence = parsed.get("confidence")
    reasoning = parsed.get("reasoning")
    if (
        not isinstance(verdict, str)
        or verdict not in _EVALUATE_VERDICTS
        or not isinstance(confidence, (int, float))
        or not (0.0 <= float(confidence) <= 1.0)
        or not isinstance(reasoning, str)
    ):
        raise RuntimeError(f"_llm_evaluate: could not parse: {raw[:500]}")
    return {
        "verdict": verdict,
        "confidence": float(confidence),
        "reasoning": reasoning,
    }


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
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")

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
    extra_system, guidance_refs = _gather_guidance(cfg.data_root, meta, "evaluate")
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
        guidance_consulted=guidance_refs,
    )
    landed = append_node(
        sd, build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    )
    return landed.__dict__


def _llm_propose_stop(anchor_text: str, provider: str, *, extra_system: str = "") -> str:
    """Generate a short German sentence justifying a stop on the current node.

    The ``provider`` arg is plumbed-through but unused today. Tests
    monkey-patch this symbol on the module.
    """
    del provider  # reserved for Stage 6 routing
    system = (
        "Du formulierst einen kurzen deutschen Satz (max. 25 Wörter), warum "
        "die Recherche zu einer Aussage abgeschlossen werden kann (Quelle "
        "gefunden, mehrfach bestätigt, oder Sackgasse). Antworte ausschließlich "
        "mit dem Satz selbst, ohne Anführungszeichen oder Markdown."
    )
    if extra_system:
        system = system + extra_system
    user = f"Aktueller Knoten: {anchor_text}\nBegründung für Stopp:"
    client = get_llm_client()
    completion = client.complete(
        messages=[Message(role="system", content=system), Message(role="user", content=user)],
        model=get_default_model(),
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
    extra_system, guidance_refs = _gather_guidance(cfg.data_root, meta, "propose_stop")
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
