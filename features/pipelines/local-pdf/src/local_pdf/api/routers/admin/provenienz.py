"""Provenienz tab routes — sessions CRUD (Stage 1).

Step + decision routes land in later stages.
"""

from __future__ import annotations

import hashlib
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
from local_pdf.provenienz.context import (
    NodeContext,
    empty_context,
    get_context,
    merge_contexts,
    origin_entry,
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
from local_pdf.storage.sidecar import doc_dir, read_mineru, read_segments

_log = logging.getLogger(__name__)

router = APIRouter()

from local_pdf.provenienz.text import strip_html as _strip_html  # noqa: E402


def _load_box_metadata(data_root: Path, slug: str, box_id: str) -> dict:
    """Return the structured metadata fields for a box from segments.json,
    or an empty dict if segments.json is missing / the box_id isn't found.

    Field name ``box_kind`` (rather than ``kind``) avoids colliding with the
    Provenienz ``Node.kind`` field, which already has well-defined semantics
    (chunk / claim / task / search_result / …).

    For figure / table boxes additionally attaches the closest adjacent
    caption (same page, ``|reading_order - target| <= 1``, kind=caption)
    as ``caption_box_id`` + ``caption_text`` so the agent + UI see what
    the figure/table is actually labelled.
    """
    try:
        seg = read_segments(data_root, slug)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return {}
    if seg is None:
        return {}
    target = next((b for b in seg.boxes if b.box_id == box_id), None)
    if target is None:
        return {}
    out: dict = {
        "page": target.page,
        "bbox": list(target.bbox),
        "box_kind": target.kind,
        "reading_order": target.reading_order,
        "continues_from": target.continues_from,
        "continues_to": target.continues_to,
        "confidence": target.confidence,
    }
    # Caption attachment for visual elements. Walk outward step by
    # step in two directions; the priority order depends on kind:
    #   - table : prefer caption ABOVE (German tech-doc convention)
    #             → primary = -1 (one before), secondary = +1 (one after)
    #   - figure: prefer caption BELOW
    #             → primary = +1 (one after),  secondary = -1 (one before)
    # If a paragraph is encountered in a direction, that direction
    # is blocked (caption can't sit "behind" body prose). Walk at
    # most _MAX_CAPTION_DISTANCE steps; typical layouts have it
    # directly adjacent.
    if target.kind in ("figure", "table"):
        cap = _find_caption_for(target, seg.boxes)
        if cap is not None:
            mineru = read_mineru(data_root, slug) or {"elements": []}
            cap_el = next(
                (e for e in mineru.get("elements", []) if e.get("box_id") == cap.box_id),
                None,
            )
            cap_text = _strip_html(cap_el.get("html_snippet", "")) if cap_el else ""
            if cap_text:
                out["caption_box_id"] = cap.box_id
                out["caption_text"] = cap_text[:300]
    return out


_MAX_CAPTION_DISTANCE = 3


_BOX_KIND_HINTS: dict[str, str] = {
    "heading": "Abschnitts-Überschrift — meist ohne eigenständige prüfbare Aussagen.",
    "paragraph": "Fließtext — typische Quelle für extrahierbare Aussagen.",
    "list_item": "Aufzählungspunkt — kompakte Aussage, oft eigenständig.",
    "table": (
        "Tabellen-Inhalt mit Zeilen/Spalten-Struktur (im Text als Markdown). "
        "Werte stehen meist in Spalten-Beziehung; beim Extrahieren / Bewerten "
        "die Spalten-Header berücksichtigen."
    ),
    "figure": (
        "Bild/Abbildung — der Text ist die VLM-Beschreibung des Bildes. "
        "Caption (falls vorhanden) liefert das Bild-Label."
    ),
    "caption": (
        "Bild-/Tabellen-Beschriftung — referenziert ein anderes Element; "
        "selten alleine prüfbar, eher Kontext."
    ),
    "formula": "Mathematischer Ausdruck — Inhalt oft als MathML/LaTeX-Salat im Text.",
    "auxiliary": "Seiten-Hilfselement (Kopf-/Fußzeile, Seitenzahl) — meist irrelevant.",
    "toc": "Inhaltsverzeichnis-Eintrag — Navigations-Element, kein eigenständiger Inhalt.",
    "list_of_tables": "Tabellenverzeichnis-Eintrag — Verweis auf eine Tabelle im Dokument.",
    "list_of_figures": "Abbildungsverzeichnis-Eintrag — Verweis auf eine Abbildung.",
    "bibliography": "Literaturverzeichnis-Eintrag — externe Quelle, keine eigene Behauptung.",
}


def _format_box_metadata_block(anchor: Node) -> str:
    """Render the structured box-metadata fields on a chunk or
    search_result anchor as a labelled prompt block.

    Lets the next_step planner reason about the anchor's TYPE
    (heading / paragraph / table / figure / caption / formula) and
    location (page, reading order) when picking the right step.
    Returns ``""`` when the anchor has no metadata (legacy nodes from
    sessions before Phase A).
    """
    if anchor.kind not in ("chunk", "search_result"):
        return ""
    p = anchor.payload
    box_kind = str(p.get("box_kind") or "").strip()
    page = p.get("page")
    reading_order = p.get("reading_order")
    caption_text = str(p.get("caption_text") or "").strip()
    recursion_depth = p.get("recursion_depth")
    if not box_kind and page is None and not caption_text:
        return ""
    parts: list[str] = ["## Quell-Metadaten"]
    if box_kind:
        hint = _BOX_KIND_HINTS.get(box_kind, "")
        parts.append(f"Box-Typ: **{box_kind}**" + (f" — {hint}" if hint else ""))
    if isinstance(page, int):
        order_str = f", Position {reading_order}" if isinstance(reading_order, int) else ""
        parts.append(f"Lage: Seite {page}{order_str}")
    if caption_text:
        parts.append(f'Caption: "{caption_text[:200]}"')
    if isinstance(recursion_depth, int) and recursion_depth > 0:
        parts.append(
            f"Recursion-Tiefe: {recursion_depth} "
            f"(via promote_search_result aus früherem Treffer entstanden)"
        )
    return "\n".join(parts) + "\n\n"


_CAPTION_BLOCKING_KINDS = frozenset(("paragraph", "list_item", "heading"))


def _find_caption_for(target: Any, boxes: list) -> Any:
    """Walk the page outward from a figure/table to find its caption.

    Direction priority:
      table  → 1 before > 1 after > 2 before > 2 after > ...
      figure → 1 after  > 1 before > 2 after  > 2 before > ...

    Stops in a direction when a content-block kind (paragraph,
    list_item, heading) is encountered — captions can't sit "behind"
    body prose, list items or section headings. Auxiliary boxes
    (page numbers, headers/footers) and sibling figures/tables are
    walked past.
    """
    same_page = {b.reading_order: b for b in boxes if b.page == target.page}
    if target.kind == "table":
        priority: tuple[int, int] = (-1, +1)
    else:  # figure
        priority = (+1, -1)
    blocked = {d: False for d in priority}
    for distance in range(1, _MAX_CAPTION_DISTANCE + 1):
        for direction in priority:
            if blocked[direction]:
                continue
            ro = target.reading_order + direction * distance
            box = same_page.get(ro)
            if box is None:
                blocked[direction] = True
                continue
            if box.kind == "caption":
                return box
            if box.kind in _CAPTION_BLOCKING_KINDS:
                blocked[direction] = True
                continue
            # auxiliary / figure / table — keep walking
        if all(blocked.values()):
            break
    return None


def _chunk_text_hash(text: str) -> str:
    """Stable across-process fingerprint of a chunk's text.

    Used by the refresh endpoint to compare a chunk Node's stored text
    against the current mineru.json/segments.json content. We use sha1
    truncated to 16 hex chars (8 bytes) — collisions are astronomically
    unlikely for the comparison sizes we deal with, and it's stable across
    Python processes (unlike ``hash()``, which is salted per-interpreter).
    """
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


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
    chunk_node_id = new_id()
    chunk_payload: dict[str, Any] = {
        "box_id": body.root_chunk_id,
        "doc_slug": body.slug,
        "text": text,
        # Top-level chunk: depth 0. Recursive promote_search_result
        # increments this on each new derived chunk.
        "recursion_depth": 0,
        # Forward-flowing investigation context — seeds the chain so
        # downstream tools (searcher exclude lists, right-pane
        # breadcrumbs) can read directly off any descendant's payload.
        "context": merge_contexts(
            empty_context(),
            {
                "visited_box_ids": [body.root_chunk_id],
                "visited_doc_slugs": [body.slug],
                "recursion_depth": 0,
                "origin_chain": [
                    origin_entry(chunk_node_id, "chunk", text[:160] or body.root_chunk_id),
                ],
            },
        ),
        **_load_box_metadata(cfg.data_root, body.slug, body.root_chunk_id),
    }
    append_node(
        sdir,
        Node(
            node_id=chunk_node_id,
            session_id=sid,
            kind="chunk",
            payload=chunk_payload,
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
    # Click-trail: when promote is invoked from a Bewertungs-trail, the
    # frontend forwards the original tile's node_id here. The new chunk
    # inherits it on its payload AND, if the trail head is an evaluation,
    # that verdict + reasoning lands as breadcrumbs so a later
    # extract_claims call sees WHY this chunk is being researched.
    triggered_from_node_id: str | None = None


def _build_promoted_chunk_payload(
    *,
    sr: Node,
    nodes: list[Node],
    edges: list[Edge],
    data_root: Path,
    triggered_from_node_id: str | None,
) -> dict[str, Any]:
    """Walk the search_result's audit chain back to claim/task/origin_chunk
    and assemble the payload for a derived chunk Node.

    The same payload shape is built at proposal-time (so the action_proposal
    carries everything the decide-handler needs to materialise the chunk
    deterministically — no second walk required, no risk of audit drift).
    """
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
    # Recursive depth tracking: derived chunk lives one level below its
    # parent. Older parent chunks (pre-unification) lack the field —
    # treat as depth 0, so the first promote always lands at depth 1.
    parent_depth = int(origin_chunk.payload.get("recursion_depth", 0)) if origin_chunk else 0
    # Forward-flow context: inherit from the search_result (which got
    # it from the task → claim → chunk chain), then add THIS chunk's
    # box_id to visited_box_ids and bump recursion_depth. The
    # origin_chain entry for this chunk gets stamped at spawn time
    # (in /decide promote_search_result) when the new node_id exists.
    parent_context = get_context(sr.payload)
    new_context: NodeContext = merge_contexts(
        parent_context,
        {
            "visited_box_ids": [box_id] if box_id else [],
            "visited_doc_slugs": [doc_slug] if doc_slug else [],
            "recursion_depth": parent_depth + 1,
        },
    )
    promoted_payload: dict[str, Any] = {
        "box_id": box_id,
        "doc_slug": doc_slug,
        "text": text,
        "recursion_depth": parent_depth + 1,
        "context": new_context,
        "promoted_from": sr.node_id,
        "origin_claim_id": claim.node_id if claim else None,
        "origin_claim_text": str(claim.payload.get("text", "")) if claim else None,
        "origin_query": str(task.payload.get("query", "")) if task else None,
        "origin_chunk_id": origin_chunk.node_id if origin_chunk else None,
        "origin_chunk_box_id": (
            str(origin_chunk.payload.get("box_id", "")) if origin_chunk else None
        ),
    }
    # Propagate the click-trail. When the trail head is an evaluation,
    # also write breadcrumbs (verdict + reasoning) so a later
    # extract_claims on this chunk sees WHY it is being researched.
    if triggered_from_node_id:
        promoted_payload["triggered_from_node_id"] = triggered_from_node_id
        trail_node = by_id.get(triggered_from_node_id)
        if trail_node is not None and trail_node.kind == "evaluation":
            promoted_payload["origin_evaluation_id"] = trail_node.node_id
            promoted_payload["origin_evaluation_verdict"] = str(
                trail_node.payload.get("verdict", "")
            )
            promoted_payload["origin_evaluation_reasoning"] = str(
                trail_node.payload.get("reasoning", "")
            )[:400]
    if box_id and doc_slug:
        promoted_payload.update(_load_box_metadata(data_root, doc_slug, box_id))
    return promoted_payload


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/promote-search-result",
    status_code=201,
)
async def promote_search_result(
    session_id: str, body: PromoteSearchResultRequest, request: Request
) -> dict:
    """Build an ``action_proposal`` (step_kind="promote_search_result") that
    captures everything needed to spawn a derived chunk Node — text,
    breadcrumbs, recursion_depth, box metadata.

    The proposal lands as an audit-anchor; the actual chunk creation
    happens in /decide on user accept (same shape as decompose_hit and
    every other step). This wires promote_search_result into the standard
    action_proposal + decision + triggers chain so the canvas can connect
    the new chunk back to the proposal that produced it via
    ``proposalSpawningNode`` (decision → triggers → chunk).

    The new chunk inherits **breadcrumbs** from its origin: the claim that
    triggered the search, the search query, and the source chunk. Stored
    on the chunk payload (assembled here, materialised in /decide) so the
    frontend can render context, and so a later ``extract_claims`` call
    on this chunk can inject those breadcrumbs into the LLM prompt —
    keeping the recursive exploration on-topic instead of producing
    arbitrary claims about the result text.
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

    chunk_args = _build_promoted_chunk_payload(
        sr=sr,
        nodes=nodes,
        edges=edges,
        data_root=cfg.data_root,
        triggered_from_node_id=body.triggered_from_node_id,
    )
    text_preview = chunk_args.get("text", "")
    label_preview = (text_preview[:60] + "…") if len(text_preview) > 60 else text_preview
    payload = ActionProposalPayload(
        step_kind="promote_search_result",
        anchor_node_id=body.search_result_node_id,
        recommended=ActionOption(
            label=f'Neuer Chunk: "{label_preview}"' if label_preview else "Neuer Chunk",
            args=chunk_args,
        ),
        alternatives=[],
        reasoning=(
            "Suchtreffer wird als abgeleiteter Chunk geöffnet — extract_claims "
            "läuft regulär darauf und neue Claim-Knoten anlegt (recursive "
            f"claim tracing, depth → {chunk_args.get('recursion_depth', 1)})."
        ),
        guidance_consulted=[],
        pre_reasoning="",
        system_prompt_used="",
        tool_used=None,
    )
    actor = "human"
    landed = append_node(
        sd,
        _attach_trail(
            build_proposal_node(session_id=session_id, actor=actor, payload=payload),
            body.triggered_from_node_id,
        ),
    )
    return landed.__dict__


class RefreshChunkResponse(BaseModel):
    """Response shape for ``POST .../chunks/{id}/refresh``.

    ``refreshed=False`` when the chunk's stored text + box_kind +
    reading_order already match the current mineru.json/segments.json —
    nothing was appended. ``refreshed=True`` when a new chunk Node was
    appended with the current source content; ``new_chunk`` carries the
    freshly-spawned node so the frontend can switch focus to it.
    """

    refreshed: bool
    reason: Literal["current", "updated", "source-missing"]
    new_chunk: dict | None = None


def _refresh_chunk_one(cfg, sd, session_id: str, chunk: Node) -> RefreshChunkResponse:
    """Diff one chunk Node against current segments.json/mineru.json
    and append a refreshed chunk + ``refreshes`` edge if the source
    has changed. Shared by the per-chunk and per-session refresh
    endpoints.
    """
    box_id = str(chunk.payload.get("box_id", ""))
    doc_slug = str(chunk.payload.get("doc_slug", ""))
    if not box_id or not doc_slug:
        return RefreshChunkResponse(refreshed=False, reason="source-missing")

    mineru = read_mineru(cfg.data_root, doc_slug) or {"elements": []}
    el = next(
        (e for e in mineru.get("elements", []) if e.get("box_id") == box_id),
        None,
    )
    if el is None:
        return RefreshChunkResponse(refreshed=False, reason="source-missing")

    current_text = _strip_html(el.get("html_snippet", ""))
    current_meta = _load_box_metadata(cfg.data_root, doc_slug, box_id)

    stored_text = str(chunk.payload.get("text", ""))
    stored_box_kind = chunk.payload.get("box_kind")
    stored_reading_order = chunk.payload.get("reading_order")
    stored_caption_text = str(chunk.payload.get("caption_text", ""))
    stored_caption_box_id = str(chunk.payload.get("caption_box_id", ""))

    text_changed = _chunk_text_hash(current_text) != _chunk_text_hash(stored_text)
    kind_changed = current_meta.get("box_kind") != stored_box_kind
    order_changed = current_meta.get("reading_order") != stored_reading_order
    caption_changed = (
        str(current_meta.get("caption_text", "")) != stored_caption_text
        or str(current_meta.get("caption_box_id", "")) != stored_caption_box_id
    )
    if not (text_changed or kind_changed or order_changed or caption_changed):
        return RefreshChunkResponse(refreshed=False, reason="current")

    new_payload: dict[str, Any] = {
        "box_id": box_id,
        "doc_slug": doc_slug,
        "text": current_text,
        **current_meta,
    }
    for k in (
        "promoted_from",
        "origin_claim_id",
        "origin_claim_text",
        "origin_query",
        "origin_chunk_id",
        "origin_chunk_box_id",
    ):
        if k in chunk.payload:
            new_payload[k] = chunk.payload[k]

    new_chunk = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=session_id,
            kind="chunk",
            payload=new_payload,
            actor="human",
        ),
    )
    append_edge(
        sd,
        Edge(
            edge_id=new_id(),
            session_id=session_id,
            from_node=new_chunk.node_id,
            to_node=chunk.node_id,
            kind="refreshes",
            reason=None,
            actor="human",
        ),
    )
    return RefreshChunkResponse(refreshed=True, reason="updated", new_chunk=new_chunk.__dict__)


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/chunks/{chunk_node_id}/refresh",
)
async def refresh_chunk(
    session_id: str, chunk_node_id: str, request: Request
) -> RefreshChunkResponse:
    """Spawn a fresh chunk Node from the current segments.json/mineru.json
    when the underlying source has been edited in the Extract tab.

    Append-only audit semantics: the old chunk + all its descendants
    (claims/tasks/evaluations) stay; a new chunk Node with a NEW node_id
    but the SAME box_id is appended, plus a ``refreshes`` edge from the
    new chunk to the old one. The ``refreshes`` edge is intentionally NOT
    in ``_DEPENDS_ON_EDGE_KINDS`` — neither side cascades on delete; both
    chunks stand independently for audit.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    nodes, _ = read_session(sd)
    chunk = next((n for n in nodes if n.node_id == chunk_node_id), None)
    if chunk is None:
        raise HTTPException(status_code=404, detail=f"chunk not found: {chunk_node_id}")
    if chunk.kind != "chunk":
        raise HTTPException(status_code=400, detail=f"node is not a chunk: kind={chunk.kind}")
    if not chunk.payload.get("box_id") or not chunk.payload.get("doc_slug"):
        raise HTTPException(
            status_code=400,
            detail="chunk payload missing box_id/doc_slug — cannot refresh",
        )
    return _refresh_chunk_one(cfg, sd, session_id, chunk)


class RefreshAllChunksResponse(BaseModel):
    """Result of a session-level chunk refresh sweep."""

    total: int
    refreshed: int
    current: int
    source_missing: int
    new_chunks: list[dict]


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/chunks/refresh-all",
)
async def refresh_all_chunks(session_id: str, request: Request) -> RefreshAllChunksResponse:
    """Walk every chunk node in the session and refresh those whose
    source has changed. Cheap (file IO only, no LLM calls) so safe to
    run on demand. Returns counts + the freshly-spawned chunk nodes
    so the frontend can summarise.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    nodes, _ = read_session(sd)
    chunks = [n for n in nodes if n.kind == "chunk"]
    refreshed = 0
    current = 0
    missing = 0
    new_chunks: list[dict] = []
    for chunk in chunks:
        if not chunk.payload.get("box_id") or not chunk.payload.get("doc_slug"):
            missing += 1
            continue
        result = _refresh_chunk_one(cfg, sd, session_id, chunk)
        if result.refreshed and result.new_chunk is not None:
            refreshed += 1
            new_chunks.append(result.new_chunk)
        elif result.reason == "source-missing":
            missing += 1
        else:
            current += 1
    return RefreshAllChunksResponse(
        total=len(chunks),
        refreshed=refreshed,
        current=current,
        source_missing=missing,
        new_chunks=new_chunks,
    )


def _build_decision_context(
    claim: Node,
    nodes: list[Node],
    meta: SessionMeta | None = None,
    *,
    task: Node | None = None,
    max_chunk_chars: int = 1500,
    consuming_step: str = "",
    data_root: Path | None = None,
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
        consuming_step: name of the step that will consume this context
            (e.g. ``"formulate_task"`` / ``"evaluate"``). Used to filter
            enrichment-skill annotations by their declared
            ``output.consumed_by``. Empty string → include any
            ``enriches``-edged annotation on the claim.
        data_root: workspace root, needed to look up enrichment skills
            and decide which annotation kinds belong to ``consuming_step``.
            Optional; when omitted, falls back to including any
            annotation with ``payload.claim_node_id == claim.node_id``
            and a non-empty ``text`` field.
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
                    "## QUELL-KONTEXT (Original-Textabschnitt aus dem die "
                    "Hypothese extrahiert wurde — KEIN Beleg!)\n"
                    f"{truncated}\n\n"
                    "Dieser Block ist die HERKUNFT der Hypothese, nicht ein "
                    "weiteres Belegstück. Nutze ihn ausschließlich, um "
                    "Begriffe, Einheiten und Bezüge im Kandidaten-Treffer "
                    "korrekt einzuordnen. Wenn die Hypothese hier wörtlich "
                    "steht: das beweist sie NICHT — der Kandidat-Treffer "
                    "muss die Hypothese aus seinem eigenen Inhalt belegen."
                )

    # Per-claim enrichment annotations — produced by enrichment skills
    # at extract_claims time, attached to the claim via an `enriches`
    # edge. Skills whose ``output.consumed_by`` includes the current
    # ``consuming_step`` contribute their latest annotation. Latest one
    # wins per (skill_id, kind) pair.
    relevant_annotation_kinds: set[str] | None = None
    if data_root is not None:
        try:
            from local_pdf.provenienz.skills import read_skills

            relevant_annotation_kinds = set()
            # Pick up enrichment skills that attach to claims, regardless
            # of ``fires_on`` (which describes when they run, not when
            # they're consumed).
            for s in read_skills(data_root):
                if not s.enabled:
                    continue
                if s.output.attaches_to != "claim":
                    continue
                if not s.output.annotation_kind:
                    continue
                if consuming_step and consuming_step not in s.output.consumed_by:
                    continue
                relevant_annotation_kinds.add(s.output.annotation_kind)
        except Exception:  # pragma: no cover - defensive
            relevant_annotation_kinds = None

    annotation_nodes = [
        n
        for n in nodes
        if n.payload.get("claim_node_id") == claim.node_id
        and (relevant_annotation_kinds is None or n.kind in relevant_annotation_kinds)
        and str(n.payload.get("text", "")).strip()
    ]
    # Group by kind, take the latest per kind.
    latest_by_kind: dict[str, Node] = {}
    for n in annotation_nodes:
        prev = latest_by_kind.get(n.kind)
        if prev is None or n.created_at > prev.created_at:
            latest_by_kind[n.kind] = n
    for kind in sorted(latest_by_kind):
        ann = latest_by_kind[kind]
        ann_text = str(ann.payload.get("text", "")).strip()
        if not ann_text:
            continue
        heading = ann.payload.get("skill_name") or kind
        parts.append(f"## ANNOTATION ({heading})\n{ann_text}")

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

    When the chunk inherits a Bewertungs-Trail (origin_evaluation_*),
    the verdict + reasoning are appended as an extra block so the LLM
    knows WHY this chunk is being researched (e.g. "the evaluation was
    'partially-supported' — focus on the unsupported parts").
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
    if not parts and not p.get("origin_evaluation_id"):
        return ""
    blocks: list[str] = []
    if parts:
        blocks.append(
            "\n\n## Kontext der Recherche\n"
            "Dieser Textabschnitt wurde als möglicher Beleg für eine frühere "
            "Aussage in derselben Sitzung identifiziert. "
            + " · ".join(parts)
            + ".\nKonzentriere dich auf Aussagen, die zur ursprünglichen Recherche passen."
        )
    eval_verdict = p.get("origin_evaluation_verdict")
    eval_reasoning = p.get("origin_evaluation_reasoning")
    if isinstance(eval_verdict, str) and eval_verdict.strip():
        reasoning_text = (
            str(eval_reasoning).strip()
            if isinstance(eval_reasoning, str) and eval_reasoning.strip()
            else ""
        )
        eval_block = (
            "\n\n## Vorherige Bewertung\n"
            f"Bewertung: {eval_verdict.strip()}"
            + (f' — "{reasoning_text}"' if reasoning_text else "")
            + "\nKonzentriere dich auf Aussagen, die im Bewertungs-Kontext "
            "relevant sind — z.B. Berechnungen oder Werte die hier zitiert "
            "werden, könnten ihrerseits Belege brauchen."
        )
        blocks.append(eval_block)
    return "".join(blocks)


def _attach_trail(node: Node, trail_id: str | None) -> Node:
    """Stamp ``triggered_from_node_id`` onto an action_proposal Node's
    payload when the request body carried one. No-op when ``trail_id``
    is empty/None — keeps the payload shape identical to today's
    direct-anchor invocations so the diff stays contained.

    Mutates ``node.payload`` in place AND returns the same Node so the
    call site reads as ``append_node(sd, _attach_trail(build…, body.trail))``.
    """
    if trail_id:
        node.payload["triggered_from_node_id"] = trail_id
    return node


def _calculator_tool_call(
    claim_text: str, candidate_text: str
) -> tuple[str, dict[str, Any] | None]:
    """Run the deterministic Calculator across (number, unit) pairs in
    both texts. Returns ``(hint_string, tool_call_record)``.

    - ``hint_string``: German prompt-block injected into the LLM's
      evaluate user prompt. Empty when either side has no parseable
      quantities.
    - ``tool_call_record``: structured audit entry
      ``{tool, operation, input, output}`` persisted on the
      action_proposal / evaluation payload so the UI can render
      "this tool ran with these inputs and got these outputs"
      (parallel to the existing capability_scan for skills).
      ``None`` when no quantities to compare.
    """
    from local_pdf.provenienz.calculator import (
        best_pairwise_compare,
        parse_quantities,
    )

    a_qs = parse_quantities(claim_text)
    b_qs = parse_quantities(candidate_text)
    if not a_qs or not b_qs:
        return "", None
    # Strict equality only — domain interpretation (conservative
    # rounding, measurement-uncertainty windows, etc.) is the job of
    # Skills, not the calculator. The tool reports raw facts; the LLM
    # and Skill prompts decide what those facts mean for the verdict.
    out = best_pairwise_compare(a_qs, b_qs, rel_tolerance=0.0)
    lines = [out["reasoning"]]
    for r in out.get("results", []):
        lines.append(f"- {r['reasoning']}")
    hint = "\n".join(lines)
    tool_call = {
        "tool": "calculator",
        "operation": "compare",
        "input": {
            "rel_tolerance": 0.0,
            "claim_quantities": [
                {"value": q.value, "unit": q.unit, "raw_unit": q.raw_unit} for q in a_qs
            ],
            "candidate_quantities": [
                {"value": q.value, "unit": q.unit, "raw_unit": q.raw_unit} for q in b_qs
            ],
        },
        "output": out,
    }
    return hint, tool_call


def _persisted_tool_calls_for_sr(
    sr_node_id: str, nodes: list[Node], edges: list[Edge]
) -> tuple[str, list[dict[str, Any]]]:
    """Gather Calculator (and future tool) results that were already
    persisted as tool_annotation Nodes attached to *sr_node_id* via
    "enriches" edges. Returns (hint_string, tool_call_dicts) — same
    shape as :func:`_calculator_tool_call` so the evaluate route
    drops in unchanged.

    The user (or planner) must have explicitly run the tool via the
    /calculator-on-result endpoint beforehand; nothing is computed
    here. Empty when no annotations exist — keeps the evaluate prompt
    clean for purely semantic claims.
    """
    annotation_node_ids = {
        e.from_node for e in edges if e.to_node == sr_node_id and e.kind == "enriches"
    }
    annotations = [
        n for n in nodes if n.node_id in annotation_node_ids and n.kind == "tool_annotation"
    ]
    if not annotations:
        return "", []
    tool_calls: list[dict[str, Any]] = []
    lines: list[str] = []
    for ann in annotations:
        tc = ann.payload.get("tool_call")
        if not isinstance(tc, dict):
            continue
        tool_calls.append(tc)
        out = tc.get("output", {}) if isinstance(tc.get("output"), dict) else {}
        if isinstance(out.get("reasoning"), str):
            lines.append(str(out["reasoning"]))
        for r in out.get("results", []) or []:
            if isinstance(r, dict) and isinstance(r.get("reasoning"), str):
                lines.append(f"- {r['reasoning']}")
    return "\n".join(lines), tool_calls


def _collect_applied_capabilities_in_chain(prior_eval_id: str, nodes: list[Node]) -> set[str]:
    """Walk back through the evaluation chain via ``prior_evaluation_node_id``
    and return the union of every ``applied_capabilities`` set seen.

    Used by capability_scan in /decide-evaluate to filter out skills
    that have already been injected into a re-eval prompt earlier in
    the same chain — re-firing them would re-create the same gate
    they just resolved (the loop the user reported).

    Returns empty set when *prior_eval_id* is empty (= first-time
    evaluate) or when the linked nodes can't be resolved.
    """
    by_id = {n.node_id: n for n in nodes}
    out: set[str] = set()
    seen: set[str] = set()
    cursor = prior_eval_id
    while cursor and cursor not in seen:
        seen.add(cursor)
        node = by_id.get(cursor)
        if node is None or node.kind != "evaluation":
            break
        applied = node.payload.get("applied_capabilities") or []
        for sid in applied:
            if isinstance(sid, str) and sid:
                out.add(sid)
        cursor = str(node.payload.get("prior_evaluation_node_id") or "")
    return out


def _ensure_table_consistency_annotation(
    sd: Path,
    session_id: str,
    sr: Node,
    nodes: list[Node],
    edges: list[Edge],
) -> None:
    """If a parsed-table annotation exists for *sr* but no consistency-
    check annotation, run TableConsistencyChecker on the parsed table
    and persist the report as a second tool_annotation.

    Runs AFTER ``_ensure_table_annotation`` so the parsed structure is
    available. Reads the parsed table directly off the existing
    tool_annotation Node (no re-parsing).
    """
    from local_pdf.provenienz.table_consistency import (
        check_consistency,
        render_report,
    )
    from local_pdf.provenienz.table_consistency import (
        to_dict as consistency_to_dict,
    )
    from local_pdf.provenienz.table_parser import StructuredTable, TableRow

    existing_ann_ids = {
        e.from_node for e in edges if e.to_node == sr.node_id and e.kind == "enriches"
    }
    parsed_ann: Node | None = None
    has_consistency = False
    for n in nodes:
        if n.kind != "tool_annotation" or n.node_id not in existing_ann_ids:
            continue
        tc = n.payload.get("tool_call")
        if not isinstance(tc, dict):
            continue
        if tc.get("tool") == "table_parser":
            parsed_ann = n
        elif tc.get("tool") == "table_consistency_checker":
            has_consistency = True
    if parsed_ann is None or has_consistency:
        return
    # Reconstruct StructuredTable from the persisted parsed-table dict.
    parsed_dict = (parsed_ann.payload.get("tool_call") or {}).get("output", {})
    headers = list(parsed_dict.get("headers") or [])
    raw_rows = parsed_dict.get("rows") or []
    rows: list[TableRow] = []
    for r in raw_rows:
        if not isinstance(r, dict):
            continue
        rows.append(TableRow(label=str(r.get("label", "")), cells=dict(r.get("cells") or {})))
    if not rows or not headers:
        return
    table = StructuredTable(caption=str(parsed_dict.get("caption", "")), headers=headers, rows=rows)
    report = check_consistency(table)
    md = render_report(report)
    tool_call = {
        "tool": "table_consistency_checker",
        "operation": "check",
        "input": {
            "n_rows": len(rows),
            "n_columns": len(headers),
            "sum_rel_tolerance": 0.001,
        },
        "output": consistency_to_dict(report),
    }
    annotation_id = new_id()
    annotation_payload = {
        "tool_call": tool_call,
        "text": md,
        "annotation_kind": "table_consistency",
        "attaches_to_node_id": sr.node_id,
        "auto_fired": True,
    }
    append_node(
        sd,
        Node(
            node_id=annotation_id,
            session_id=session_id,
            kind="tool_annotation",
            payload=annotation_payload,
            actor="system",
        ),
    )
    append_edge(
        sd,
        Edge(
            edge_id=new_id(),
            session_id=session_id,
            from_node=annotation_id,
            to_node=sr.node_id,
            kind="enriches",
            reason=None,
            actor="system",
        ),
    )


def _ensure_table_annotation(
    sd: Path,
    session_id: str,
    sr: Node,
    nodes: list[Node],
    edges: list[Edge],
    data_root: Path,
) -> None:
    """If the search_result is a kind=table box AND no parsed-table
    annotation exists yet, run the deterministic TableParser on the
    box's html_snippet and persist the structured 2D mapping as a
    tool_annotation Node + "enriches" edge to the SR.

    Engineering-rationale: tables are 2D bindings (row x column to
    value). LLMs handle this poorly when the input is plain text;
    deterministic parsing eliminates the parse-failure mode entirely.
    """
    from local_pdf.provenienz.table_parser import (
        parse_table,
        render_markdown,
        to_dict,
    )

    if str(sr.payload.get("box_kind", "")) != "table":
        return
    existing_ann_ids = {
        e.from_node for e in edges if e.to_node == sr.node_id and e.kind == "enriches"
    }
    has_table_ann = any(
        n.kind == "tool_annotation"
        and n.node_id in existing_ann_ids
        and isinstance(n.payload.get("tool_call"), dict)
        and (n.payload.get("tool_call") or {}).get("tool") == "table_parser"
        for n in nodes
    )
    if has_table_ann:
        return
    box_id = str(sr.payload.get("box_id", ""))
    doc_slug = str(sr.payload.get("doc_slug", ""))
    if not box_id or not doc_slug:
        return
    mineru = read_mineru(data_root, doc_slug)
    if mineru is None:
        return
    html_snippet = ""
    for el in mineru.get("elements", []) or []:
        if el.get("box_id") == box_id:
            html_snippet = str(el.get("html_snippet", ""))
            break
    if not html_snippet:
        return
    fallback_caption = str(sr.payload.get("caption_text", ""))
    parsed = parse_table(html_snippet, fallback_caption=fallback_caption)
    if parsed is None:
        return
    md = render_markdown(parsed)
    tool_call = {
        "tool": "table_parser",
        "operation": "parse",
        "input": {
            "box_id": box_id,
            "had_caption_in_html": bool(parsed.caption and not fallback_caption),
            "fallback_caption_used": bool(fallback_caption and parsed.caption == fallback_caption),
        },
        "output": {
            **to_dict(parsed),
            "reasoning": (
                f"Tabelle geparst: {len(parsed.rows)} Zeilen, "
                f"{len(parsed.headers)} Spalten."
                + (f" Caption: {parsed.caption}" if parsed.caption else "")
            ),
            "markdown": md,
        },
    }
    annotation_id = new_id()
    annotation_payload = {
        "tool_call": tool_call,
        "text": md,
        "annotation_kind": "table_parsed",
        "attaches_to_node_id": sr.node_id,
        "auto_fired": True,
    }
    append_node(
        sd,
        Node(
            node_id=annotation_id,
            session_id=session_id,
            kind="tool_annotation",
            payload=annotation_payload,
            actor="system",
        ),
    )
    append_edge(
        sd,
        Edge(
            edge_id=new_id(),
            session_id=session_id,
            from_node=annotation_id,
            to_node=sr.node_id,
            kind="enriches",
            reason=None,
            actor="system",
        ),
    )


def _ensure_calculator_annotation(
    sd: Path,
    session_id: str,
    sr: Node,
    claim: Node,
    nodes: list[Node],
    edges: list[Edge],
) -> None:
    """If no Calculator annotation already exists for *sr*, run the
    Calculator on (claim_text, sr_text) and persist the result as a
    tool_annotation Node + "enriches" edge. No-op when:

      - an annotation already exists for this SR (don't double-run),
      - the texts have no parseable (number, unit) pairs (nothing to
        compute).

    Auto-fire rationale: when an LLM evaluates a claim with numbers
    against a candidate with numbers, it should NEVER do mental
    arithmetic. The Calculator must run first; this helper guarantees
    that, while still leaving the manual /calculator-on-result path
    available for explicit re-runs (different tolerance, etc.).
    """
    existing_ann_ids = {
        e.from_node for e in edges if e.to_node == sr.node_id and e.kind == "enriches"
    }
    has_calc_ann = any(
        n.kind == "tool_annotation"
        and n.node_id in existing_ann_ids
        and isinstance(n.payload.get("tool_call"), dict)
        and (n.payload.get("tool_call") or {}).get("tool") == "calculator"
        for n in nodes
    )
    if has_calc_ann:
        return
    claim_text = str(claim.payload.get("text", ""))
    candidate_text = str(sr.payload.get("text", ""))
    hint, tool_call = _calculator_tool_call(claim_text, candidate_text)
    if tool_call is None:
        return
    annotation_id = new_id()
    annotation_payload = {
        "tool_call": tool_call,
        "text": hint,
        "annotation_kind": "calculator_result",
        "attaches_to_node_id": sr.node_id,
        "auto_fired": True,
    }
    append_node(
        sd,
        Node(
            node_id=annotation_id,
            session_id=session_id,
            kind="tool_annotation",
            payload=annotation_payload,
            actor="system",
        ),
    )
    append_edge(
        sd,
        Edge(
            edge_id=new_id(),
            session_id=session_id,
            from_node=annotation_id,
            to_node=sr.node_id,
            kind="enriches",
            reason=None,
            actor="system",
        ),
    )


def _build_calculator_hint(claim_text: str, candidate_text: str) -> str:
    """Backwards-compat wrapper — only the hint string. Prefer
    :func:`_calculator_tool_call` so the structured record gets
    persisted on the eval payload.
    """
    hint, _ = _calculator_tool_call(claim_text, candidate_text)
    return hint


def _ancestor_chunk_box_ids(
    nodes: list[Node],
    edges: list[Edge],
    start_node_id: str,
) -> list[str]:
    """Walk parent edges upward from *start_node_id* and collect every
    chunk Node's ``box_id`` along the ancestry path.

    Used by /search to populate ``exclude_box_ids`` so the searcher
    doesn't re-surface chunks the investigation already derived from.
    On a fresh session this returns just ``[meta.root_chunk_id]``;
    after a promote_search_result it grows to include the promoted
    chunk's box_id; after multiple nested promotes the whole chain is
    excluded — exactly the boxes whose contents we've already mined
    for claims.

    Edge convention in this graph is **dependent → dependency**
    (see ``_DEPENDS_ON_EDGE_KINDS``): claim → chunk, task → claim,
    search_result → task, promoted_chunk → search_result, etc. So
    "walking upward" means following each node's OUTGOING depends-on
    edges back to its parents — not incoming, which would walk down
    into descendants.
    """
    by_id = {n.node_id: n for n in nodes}
    parents: dict[str, list[str]] = {}
    for e in edges:
        if e.kind not in _DEPENDS_ON_EDGE_KINDS:
            continue
        parents.setdefault(e.from_node, []).append(e.to_node)
    seen: set[str] = set()
    box_ids: list[str] = []
    queue: list[str] = [start_node_id]
    while queue:
        nid = queue.pop()
        if nid in seen:
            continue
        seen.add(nid)
        node = by_id.get(nid)
        if node is None:
            continue
        if node.kind == "chunk":
            bid = str(node.payload.get("box_id") or "")
            if bid:
                box_ids.append(bid)
        for parent in parents.get(nid, []):
            queue.append(parent)
    return box_ids


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
# model's max_model_len. With max_model_len=8192 (current default) and
# our system+user prompts running 4000-6500 input tokens (skill-stacked
# next_step + evaluate), 1024 leaves enough headroom for JSON output +
# small <think> block leakage.
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
    "Hypothese ist.\n\n"
    "GRUND-PRINZIP — strikt einhalten:\n"
    "Der Kandidat-Treffer muss die Hypothese AUS SEINEM EIGENEN INHALT "
    "belegen. Wenn ein QUELL-KONTEXT (Original-Textabschnitt aus dem die "
    "Hypothese extrahiert wurde) im System-Prompt erwähnt ist, dient er "
    "NUR der Disambiguierung von Begriffen und Einheiten — er ist "
    "NIEMALS Beleg dafür, dass die Hypothese stimmt. Genauso ein "
    "möglicher Untersuchungs-Pfad oder eine Recherche-Frage: das ist "
    "Vergangenheit, nicht Evidenz.\n\n"
    "Beispiel: Hypothese 'Gesamtwärmeleistung 5,596'. Kandidat ist eine "
    "Tabellenzelle '5,596' ohne semantische Bindung. → 'partial-support' "
    "(NICHT 'likely-source') — die Tabelle alleine sagt nicht, was die "
    "Zahl bedeutet. Selbst wenn QUELL-KONTEXT 'Gesamtwärmeleistung "
    "5,596' wörtlich nennt: das ist nur die Herkunft der Hypothese, "
    "kein zweites Belegstück.\n\n"
    "ARBEITSWEISE - strikt einhalten:\n"
    "1. Lies den Kandidaten-Text VOLLSTÄNDIG.\n"
    "2. Liste JEDEN selbständigen Satz / jede Aussage einzeln auf.\n"
    "3. Pro Satz markiere: STÜTZT / WIDERSPRICHT / NICHT-RELEVANT "
    "für die zu prüfende Hypothese.\n"
    "4. Sätze mit Zahlen, Datumsangaben, technischen Werten, "
    "Einheiten oder Eigennamen sind IMMER potentiell relevant — "
    "beweise das Gegenteil bevor du sie als nicht-relevant markierst.\n"
    "5. Erst NACH dieser per-Satz-Aufstellung gib das Gesamt-Verdict. "
    "Bewerte ausschliesslich, was im Kandidat steht — nicht was im "
    "QUELL-KONTEXT, der Recherche-Frage oder anderen Vergangenheits-"
    "Hinweisen steht.\n\n"
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
PRE_REASON_SYSTEM = (
    "Du bist die reflektierende Schicht eines Recherche-Agenten. Vor "
    "jeder Aktion erklärst du in EINEM kurzen deutschen Satz (max. "
    "30 Wörter), warum diese Art von Aktion JETZT für DIESEN Knoten "
    "der richtige Prozess-Schritt ist UND was konkret geprüft wird.\n\n"
    "ANFORDERUNGEN:\n"
    "- Nenne konkret die Hypothese / Aussage, die geprüft wird. "
    "Schreibe sie als Hypothese, mit dem Wort 'Hypothese' oder "
    "'Aussage' davor — z.B. 'Bewertung des Treffers gegen die "
    "Hypothese der Wärmeleistung von 5,6 kW' oder 'Prüfung der "
    "Aussage zur Brennelement-Anzahl gegen den Treffer'.\n"
    "- Mache klar, dass es eine ZU PRÜFENDE Behauptung ist — nicht "
    "ein bewiesener Fakt.\n\n"
    "STRIKTE VERBOTE:\n"
    "- Du URTEILST NICHT über das Ergebnis. VERMEIDE Outcome-Verben "
    "wie 'stützt', 'unterstützt', 'bestätigt', 'widerlegt', "
    "'beweist', 'zeigt'. Diese Wörter gehören in die nachfolgende "
    "Aktion, nicht in deine Vor-Begründung.\n"
    "- Behandle Inhalte aus dem Anker NIEMALS als Tatsache. Schreibe "
    "z.B. NICHT 'Die Angabe von 5,6 kW unterstützt die Annahme' "
    "(das ist Vorgriff). Schreibe stattdessen 'Bewertung des Treffers "
    "gegen die Hypothese der Wärmeleistung von 5,6 kW' (neutral).\n"
    "- Mische niemals Hypothese und Kandidat zu einer einzigen "
    "Aussage. Die Hypothese ist das Subjekt der Prüfung; der "
    "Kandidat-Inhalt erscheint NICHT in der Vor-Begründung.\n\n"
    "Antworte ausschließlich mit dem Satz selbst, keine "
    "Anführungszeichen-Zaun, kein Vor- oder Nachtext, kein Markdown."
)
NEXT_STEP_SYSTEM = (
    "Du bist der reflektierende Teil eines Recherche-Agenten. Du bekommst "
    "einen Knoten + Sitzungs-Ziel + Liste der verfügbaren Steps + Liste "
    "der verfügbaren Tools (mit Agent-Hinweisen wann welches Tool zu "
    "wählen ist). Wähle den nächsten Schritt.\n\n"
    "PRÄZEDENZ — strikt einhalten, in dieser Reihenfolge:\n\n"
    "1. executable_step ist die DEFAULT-Wahl. Prüfe ZUERST ob ein "
    "registrierter Step für den Anker-Typ existiert und auf den "
    "Untersuchungs-Zustand passt. Beispiele die Anker → Step "
    "abdecken: chunk → extract_claims; claim → formulate_task; "
    "task → search; search_result → evaluate / promote_search_result; "
    "evaluation → next-step-along-the-trail. Diese Steps sind ALLE "
    "autonom (LLM + Skills + Tools); sie sind NICHT Mensch-Arbeit, "
    "auch wenn die Aufgabe Urteil verlangt — Urteilen ist genau was "
    "evaluate (und vergleichbare Steps) macht.\n\n"
    "2. capability_request NUR wenn die Aufgabe ein Tool oder Skill "
    "braucht das im Registry nicht existiert (oder nur als "
    "deaktivierter Stub). Schreibe in `description` was fehlt; "
    "`name` ist der spezifische Tool-Name.\n\n"
    "3. manual_review IST legitim, aber NUR als Fallback wenn weder "
    "ein registrierter executable_step noch ein vorstellbares Tool "
    "den Fall abdecken könnten. Beispiele für legitime "
    "Mensch-Arbeit: ethische Abwägung, widersprüchliche "
    "Domain-Belege wo keine Skill-Regel greift, Untersuchungs-Pause "
    "auf User-Wunsch, völlig neue Situationen jenseits des Step-"
    "Repertoires.\n\n"
    "manual_review ist NICHT das Mittel um vor einer schwierigen "
    "Bewertung zu kapitulieren — schwierige Bewertungen erledigt "
    "evaluate (mit allen Skills + Tools). Wenn Du an evaluate denkst "
    "aber 'lieber Mensch' wählen willst: nimm executable_step "
    "name='evaluate', NICHT manual_review.\n\n"
    "ANTI-PATTERN — wenn Du gerade dabei bist, einen Step aus der "
    "verfügbaren Liste (z.B. promote_search_result, search, evaluate) "
    "als `kind: manual_review` zu deklarieren weil die Aufgabe "
    "'Urteil' erfordert: STOPP. Sobald der name aus der verfügbaren "
    "Step-Liste kommt, ist `kind: executable_step` die EINZIG korrekte "
    "Wahl — der Step ist autonom ausführbar (LLM + Skills + Tools), "
    "und der User klickt 'Akzeptieren'. manual_review ist NUR für "
    "Aufgaben deren name KEIN registrierter Step ist (z.B. "
    "'Juristische Bewertung', 'Vertrags-Konsultation').\n\n"
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
    not need to change. The unified ``skills.jsonl`` storage replaces
    the approaches+reasons split, but the ``GuidanceRef.kind`` field
    keeps the legacy ``"approach"`` / ``"reason"`` values so existing
    audit consumers (UI, tests, /sessions/{sid} payloads) stay valid.
    Active/sub-agent skills are deliberately **not** mixed into the
    passive overlay text — they fire via the multi-agent pipeline in
    :func:`_gather_guidance_split`.
    """
    del meta  # session_goal not consumed yet — anchor matching lands later
    del anchor

    from local_pdf.provenienz.skills import SkillKind, read_skills

    overlay_parts: list[str] = []
    note_parts: list[str] = []
    refs: list[GuidanceRef] = []
    for skill in read_skills(data_root, fires_on=step_kind, enabled_only=True):
        if skill.skill_kind == SkillKind.PROMPT_OVERLAY and skill.prompt.free_text:
            overlay_parts.append(skill.prompt.free_text)
            refs.append(
                GuidanceRef(
                    kind="approach",
                    id=skill.skill_id,
                    summary=skill.name[:80],
                )
            )
        elif skill.skill_kind == SkillKind.NOTE and skill.prompt.free_text:
            note_parts.append(skill.prompt.free_text)
            refs.append(
                GuidanceRef(
                    kind="reason",
                    id=skill.skill_id,
                    summary=skill.prompt.free_text[:80],
                )
            )
        # subagent / enrichment / reactive skills route through their
        # own dispatchers — they must NOT bleed into the passive overlay.

    text = ""
    if overlay_parts:
        text += "\n\n" + "\n\n".join(overlay_parts)
    if note_parts:
        text += "\n\n## Frühere Korrekturen durch den Nutzer\n"
        text += "\n".join(f"- {n}" for n in note_parts)
        text += "\nBerücksichtige diese Korrekturen, wenn sie auf die aktuelle Aufgabe zutreffen."
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
    # Click-trail: persisted on the spawned action_proposal so the
    # decide-handler can copy it onto every spawned downstream node
    # (claim, claim_background, …). Empty/None → omitted from payload.
    triggered_from_node_id: str | None = None


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
    # For figure/table chunks: prepend the caption (if attached at
    # session-creation / promote time) so the agent reads label and
    # content together when extracting claims.
    extract_text = str(chunk.payload.get("text", ""))
    cap = str(chunk.payload.get("caption_text", "")).strip()
    if cap:
        extract_text = f"Caption: {cap}\n\n{extract_text}"
    try:
        claims = _llm_extract_claims(
            extract_text,
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
    node = _attach_trail(
        build_proposal_node(session_id=session_id, actor=actor, payload=payload),
        body.triggered_from_node_id,
    )
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
    raw = _strip_thinking_tags(completion.text or "")
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
    # Click-trail: persisted on the spawned action_proposal so the
    # decide-handler can copy it onto the spawned task. Empty/None →
    # omitted from payload.
    triggered_from_node_id: str | None = None


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
    extra_system = (
        _build_decision_context(
            claim,
            nodes,
            meta,
            consuming_step="formulate_task",
            data_root=cfg.data_root,
        )
        + extra_system
    )
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
        sd,
        _attach_trail(
            build_proposal_node(session_id=session_id, actor=actor, payload=payload),
            body.triggered_from_node_id,
        ),
    )
    return landed.__dict__


class SearchStepRequest(BaseModel):
    task_node_id: str
    top_k: int = 5
    # Click-trail: persisted on the spawned action_proposal so the
    # decide-handler can copy it onto every spawned search_result.
    triggered_from_node_id: str | None = None


class CalculatorOnResultRequest(BaseModel):
    """Run the Calculator on a session's search_result and persist the
    output as a tool_annotation Node attached to that result.

    Used as the explicit "user reasons → triggers tool" path: instead
    of auto-injecting a calculator pass into every evaluate, the user
    (or a future auto-executor reading capability_request Nodes) hits
    this endpoint to materialise the comparison. Subsequent evaluate
    on the same search_result will pick up the persisted annotation
    via :func:`_persisted_tool_calls_for_sr` and feed it to the LLM
    as ground truth.
    """

    search_result_node_id: str
    rel_tolerance: float = 0.0
    triggered_from_node_id: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/calculator-on-result",
    status_code=201,
)
async def calculator_on_result(
    session_id: str, body: CalculatorOnResultRequest, request: Request
) -> dict:
    """Run a Calculator compare against the search_result's text vs.
    the linked claim's text, and persist the result as a
    tool_annotation Node + "enriches" edge to the search_result.

    Idempotency-light: re-running just appends a new annotation.
    Older annotations remain in the graph as audit history; evaluate
    consumes ALL of them, so the user sees their full tool-call
    history per search_result.
    """
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
    # Resolve linked claim by walking sr → task → focus_claim.
    task_id = sr.payload.get("task_node_id")
    task = (
        next((n for n in nodes if n.node_id == task_id), None) if isinstance(task_id, str) else None
    )
    claim_id = task.payload.get("focus_claim_id") if task is not None else None
    claim = (
        next((n for n in nodes if n.node_id == claim_id), None)
        if isinstance(claim_id, str)
        else None
    )
    if claim is None:
        raise HTTPException(
            status_code=400,
            detail="no linked claim — search_result must descend from a task with focus_claim_id",
        )
    claim_text = str(claim.payload.get("text", ""))
    candidate_text = str(sr.payload.get("text", ""))
    hint, tool_call = _calculator_tool_call(claim_text, candidate_text)
    if tool_call is None:
        raise HTTPException(
            status_code=400,
            detail="no parseable (number, unit) pairs in claim or candidate",
        )
    if body.rel_tolerance > 0.0:
        # Caller-supplied tolerance — re-run with that. Domain-Skill
        # path: a planner Skill that knows the legitimate tolerance for
        # this domain (conservative rounding etc.) drives this value.
        from local_pdf.provenienz.calculator import (
            best_pairwise_compare,
            parse_quantities,
        )

        a_qs = parse_quantities(claim_text)
        b_qs = parse_quantities(candidate_text)
        out = best_pairwise_compare(a_qs, b_qs, rel_tolerance=body.rel_tolerance)
        tool_call["input"]["rel_tolerance"] = body.rel_tolerance
        tool_call["output"] = out
        lines = [out["reasoning"]]
        for r in out.get("results", []) or []:
            lines.append(f"- {r.get('reasoning', '')}")
        hint = "\n".join(lines)

    annotation_id = new_id()
    annotation_payload = {
        "tool_call": tool_call,
        "text": hint,
        "annotation_kind": "calculator_result",
        "attaches_to_node_id": sr.node_id,
    }
    if body.triggered_from_node_id:
        annotation_payload["triggered_from_node_id"] = body.triggered_from_node_id
    annotation = append_node(
        sd,
        Node(
            node_id=annotation_id,
            session_id=session_id,
            kind="tool_annotation",
            payload=annotation_payload,
            actor="human",
        ),
    )
    append_edge(
        sd,
        Edge(
            edge_id=new_id(),
            session_id=session_id,
            from_node=annotation.node_id,
            to_node=sr.node_id,
            kind="enriches",
            reason=None,
            actor="human",
        ),
    )
    return annotation.__dict__


class InvestigateTableRequest(BaseModel):
    """Spawn a 3-axis follow-up investigation around a table-typed
    search_result. The 4th axis (Konsistenz-Pruefung) is already
    auto-fired as a tool_annotation by ``_ensure_table_consistency_
    annotation`` during evaluate, so this endpoint covers only the
    remaining three:

    1. **Text-Referenz**: search the document for textual mentions
       of the table's identifier ("Tabelle 3.7", "Tab. 3-7", ...).
       Catches text passages that DESCRIBE what the table shows.
    2. **Quellen-Attribution**: search for the source token cited
       in the caption ("[4]", "(nach Mueller 2019)", ...). Catches
       the upstream reference if the table was copied from elsewhere.
    3. **Semantik-Rueckpruefung**: re-evaluate this search_result with
       extra system prompt that emphasizes (row, column, value)
       binding so an LLM can't accept a table as 'likely-source'
       just because the right numbers appear in the right region —
       the BINDING must match too.

    Each spawned action_proposal is a regular proposal the user
    accepts/rejects in the canvas. Searches are pre-run server-side
    so the user sees real hits before deciding.
    """

    search_result_node_id: str
    triggered_from_node_id: str | None = None


_TABLE_REF_RE = re.compile(
    r"\b(?:Tabelle|Tab\.?)\s*(\d+(?:[.\-]\d+)*)",
    re.IGNORECASE,
)
_SOURCE_TOKEN_RE = re.compile(
    r"(?:nach\s+|gemaess\s+|gemäß\s+)?(?:\[\d+\]|\(\d{4}\)|\([A-ZÄÖÜ][a-zäöüß]+(?:\s+et\s+al\.)?\s+\d{4}\))",
    re.IGNORECASE,
)


def _extract_table_identifier(caption: str) -> str | None:
    """Return the canonical table-identifier from a caption, e.g.
    ``"Tabelle 3.7"`` from ``"Tabelle 3.7: Reaktorparameter"``.

    Returns None when no identifier-pattern is present.
    """
    if not caption:
        return None
    m = _TABLE_REF_RE.search(caption)
    if m is None:
        return None
    return f"Tabelle {m.group(1)}"


def _extract_source_attribution(caption: str) -> str | None:
    """Return a search-friendly source-attribution token from the
    caption, e.g. ``"[4]"`` from ``"... nach [4]"`` or
    ``"(Mueller 2019)"``. Returns None when nothing matches.
    """
    if not caption:
        return None
    m = _SOURCE_TOKEN_RE.search(caption)
    if m is None:
        return None
    return m.group(0).strip()


_SEMANTIK_EXTRA_SYSTEM = (
    "\n\n## TABELLEN-SEMANTIK-RUECKPRUEFUNG (zwingend)\n"
    "Du re-pruefst eine bereits bewertete Tabelle aus genau einem "
    "Blickwinkel: stimmt die BINDUNG (Zeilen-Label, Spalten-Label, "
    "Wert) der zu pruefenden Aussage zu? Es reicht NICHT, dass die "
    "behauptete Zahl irgendwo in der Tabelle vorkommt. Sie muss in "
    "der EXAKT bezeichneten Zeile UND der EXAKT bezeichneten Spalte "
    "stehen. Wenn die Aussage z.B. 'Gesamt-Wert: 5,6' lautet, dann "
    "darf 5,6 nicht in einer beliebigen Komponenten-Zeile auftauchen "
    "— die Zeile MUSS 'Gesamt' (oder Synonym) heissen, sonst ist die "
    "Bindung verletzt. Verletzte Bindung ⇒ partial-support oder "
    "contradicts, nicht likely-source.\n\n"
    "Falls Zeilen- oder Spalten-Label nicht eindeutig aus der "
    "Aussage hervorgehen: das ist selbst schon eine Bindungs-Luecke "
    "(partial-support, in der reasoning festhalten welche Achse "
    "unklar bleibt)."
)


def _spawn_semantik_rueckpruefung_proposal(
    *,
    sd: Path,
    session_id: str,
    sr: Node,
    nodes: list[Node],
    triggered_from_node_id: str | None,
) -> dict | None:
    """Pre-bake a Semantik-Rueckpruefung evaluate action_proposal for a
    table search_result.

    Resolves claim via sr → task → focus_claim_id, runs ``_llm_evaluate``
    with the Semantik extra_system, and persists an action_proposal with
    the same args shape as a regular evaluate proposal. Returns the
    landed Node dict or ``None`` if the claim could not be resolved or
    the LLM call failed (caller reports the axis as skipped).
    """
    task_id = sr.payload.get("task_node_id")
    task = next((n for n in nodes if n.node_id == task_id), None) if task_id else None
    focus_claim_id = task.payload.get("focus_claim_id") if task is not None else None
    claim = (
        next((n for n in nodes if n.node_id == focus_claim_id), None)
        if isinstance(focus_claim_id, str)
        else None
    )
    if claim is None or claim.kind != "claim":
        return None

    claim_text = str(claim.payload.get("text", ""))
    candidate_text = str(sr.payload.get("text", ""))
    cap = str(sr.payload.get("caption_text", "")).strip()
    if cap:
        candidate_text = f"Caption: {cap}\n\n{candidate_text}"

    try:
        verdict_payload = _llm_evaluate(
            claim_text,
            candidate_text,
            "vllm",
            extra_system=_SEMANTIK_EXTRA_SYSTEM,
            calc_hint="",
        )
    except Exception as exc:
        _log.warning("Semantik-Rueckpruefung LLM call failed: %s", exc)
        return None

    verdict = str(verdict_payload.get("verdict", "unknown"))
    confidence = float(verdict_payload.get("confidence", 0.0))
    reasoning = str(verdict_payload.get("reasoning", ""))
    sentences = verdict_payload.get("sentences", [])

    payload = ActionProposalPayload(
        step_kind="evaluate",
        anchor_node_id=sr.node_id,
        recommended=ActionOption(
            label=f"Semantik-Rueckpruefung: {verdict} (conf {confidence:.2f})",
            args={
                "search_result_node_id": sr.node_id,
                "against_claim_id": str(claim.node_id),
                "verdict": verdict,
                "confidence": confidence,
                "reasoning": reasoning,
                "sentences": sentences,
                "investigation_axis": "Semantik-Rueckpruefung",
            },
        ),
        alternatives=[],
        reasoning=(
            "Tabellen-Untersuchung — Semantik-Rueckpruefung: prueft ob die "
            "(Zeilen-Label, Spalten-Label, Wert)-Bindung der Aussage "
            "entspricht (nicht nur ob die Zahl irgendwo in der Tabelle "
            "vorkommt). LLM-Verdict bereits berechnet — Akzeptieren "
            f"persistiert die Bewertung. Verdict: {verdict}."
        ),
        guidance_consulted=[],
    )
    landed = append_node(
        sd,
        _attach_trail(
            build_proposal_node(session_id=session_id, actor="system", payload=payload),
            triggered_from_node_id,
        ),
    )
    return landed.__dict__


def _spawn_investigate_table_axes(
    *,
    cfg: Any,
    sd: Path,
    session_id: str,
    sr: Node,
    task: Node,
    nodes: list[Node],
    edges: list[Edge],
    meta: SessionMeta,
    triggered_from_node_id: str | None,
) -> dict:
    """Spawn the 3 follow-up action_proposals around a table search_result
    (Text-Referenz + Quellen-Attribution + Semantik-Rueckpruefung).

    Shared helper for the explicit POST /investigate-table route and for
    the planner-driven step_kind=investigate_table /decide branch — both
    paths produce the same audit-trail shape.
    """
    caption = str(sr.payload.get("caption_text", ""))
    table_box_id = str(sr.payload.get("box_id", ""))

    proposals: list[dict] = []
    skipped: list[dict] = []

    task_context = get_context(task.payload)
    visited = list(task_context.get("visited_box_ids", []))
    if not visited:
        visited = _ancestor_chunk_box_ids(nodes, edges, task.node_id)
    exclude_set = {meta.root_chunk_id, *visited}
    if table_box_id:
        exclude_set.add(table_box_id)
    searcher = InDocSearcher(
        data_root=cfg.data_root,
        slug=meta.slug,
        exclude_box_ids=tuple(sorted(exclude_set)),
    )

    def _spawn_search_proposal(query: str, axis_label: str, axis_reason: str) -> dict:
        hits = searcher.search(query, top_k=5)
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
        payload = ActionProposalPayload(
            step_kind="search",
            anchor_node_id=task.node_id,
            recommended=ActionOption(
                label=f"{axis_label}: {len(hits_payload)} Treffer übernehmen",
                args={"hits": hits_payload, "investigation_axis": axis_label},
            ),
            alternatives=[
                ActionOption(
                    label=f"{axis_label}: nur Top-1 übernehmen",
                    args={"hits": hits_payload[:1], "investigation_axis": axis_label},
                ),
            ],
            reasoning=(
                f"Tabellen-Untersuchung — {axis_reason}. Query='{query}', hits={len(hits_payload)}."
            ),
            guidance_consulted=[],
        )
        landed = append_node(
            sd,
            _attach_trail(
                build_proposal_node(session_id=session_id, actor="system", payload=payload),
                triggered_from_node_id,
            ),
        )
        return landed.__dict__

    # Axis 2: Text-Referenz
    table_id = _extract_table_identifier(caption)
    if table_id:
        proposals.append(
            _spawn_search_proposal(
                query=table_id,
                axis_label="Text-Referenz",
                axis_reason=(
                    f"Suche nach Text-Stellen die '{table_id}' explizit erwaehnen "
                    "(beschreibender Kontext)"
                ),
            )
        )
    else:
        skipped.append(
            {
                "axis": "Text-Referenz",
                "reason": "Kein Tabellen-Bezeichner in der Caption (Tabelle X / Tab. X).",
            }
        )

    # Axis 3: Quellen-Attribution
    source_token = _extract_source_attribution(caption)
    if source_token:
        proposals.append(
            _spawn_search_proposal(
                query=source_token,
                axis_label="Quellen-Attribution",
                axis_reason=(
                    f"Suche nach der in der Caption angegebenen Quelle '{source_token}' im Korpus"
                ),
            )
        )
    else:
        skipped.append(
            {
                "axis": "Quellen-Attribution",
                "reason": (
                    "Keine erkennbare Quellen-Attribution in der Caption "
                    "([n] / (Autor Jahr) / nach ...)."
                ),
            }
        )

    # Axis 4: Semantik-Rueckpruefung — pre-bake the verdict so the
    # spawned action_proposal has the same shape as a regular evaluate
    # proposal (args contain verdict/confidence/reasoning/...). The
    # /decide handler for step_kind=evaluate then accepts it without a
    # special branch. Costs one LLM call at investigate-time, but the
    # user has explicitly opted into the choreography so the spend is
    # warranted.
    semantik_axis_proposal = _spawn_semantik_rueckpruefung_proposal(
        sd=sd,
        session_id=session_id,
        sr=sr,
        nodes=nodes,
        triggered_from_node_id=triggered_from_node_id,
    )
    if semantik_axis_proposal is not None:
        proposals.append(semantik_axis_proposal)
    else:
        skipped.append(
            {
                "axis": "Semantik-Rueckpruefung",
                "reason": (
                    "Konnte die Aussage zum search_result nicht aufloesen "
                    "(task_node_id / focus_claim_id fehlt) oder LLM-Aufruf "
                    "scheiterte."
                ),
            }
        )

    return {
        "proposals": proposals,
        "skipped": skipped,
        "table_caption": caption,
        "axes_run": ["Text-Referenz", "Quellen-Attribution", "Semantik-Rueckpruefung"],
    }


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/investigate-table",
    status_code=201,
)
async def investigate_table(
    session_id: str, body: InvestigateTableRequest, request: Request
) -> dict:
    """Choreography orchestrator: spawn 2 search action_proposals
    (text-reference + source-attribution) plus 1 evaluate
    action_proposal (semantic re-check) for a table-typed
    search_result.

    Thin HTTP wrapper around :func:`_spawn_investigate_table_axes`. The
    same helper is invoked from the /decide handler when the planner
    picks step_kind=investigate_table — keeps the audit-trail shape
    identical regardless of how the choreography was triggered.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    nodes, edges = read_session(sd)
    sr = next((n for n in nodes if n.node_id == body.search_result_node_id), None)
    if sr is None:
        raise HTTPException(
            status_code=404, detail=f"search_result not found: {body.search_result_node_id}"
        )
    if sr.kind != "search_result":
        raise HTTPException(
            status_code=400, detail=f"anchor must be search_result, got kind={sr.kind}"
        )
    if str(sr.payload.get("box_kind", "")) != "table":
        raise HTTPException(
            status_code=400,
            detail=(
                f"investigate-table requires box_kind=table on search_result, "
                f"got box_kind={sr.payload.get('box_kind')!r}"
            ),
        )
    task_id = sr.payload.get("task_node_id")
    task = next((n for n in nodes if n.node_id == task_id), None) if task_id else None
    if task is None:
        raise HTTPException(
            status_code=400,
            detail="search_result has no parent task — cannot anchor follow-up search proposals",
        )
    return _spawn_investigate_table_axes(
        cfg=cfg,
        sd=sd,
        session_id=session_id,
        sr=sr,
        task=task,
        nodes=nodes,
        edges=edges,
        meta=meta,
        triggered_from_node_id=body.triggered_from_node_id,
    )


class CalculatorRequest(BaseModel):
    """Stateless deterministic numerical-comparison endpoint.

    Two operations:
      - ``compare``: extract (number, unit) pairs from ``a_text`` and
        ``b_text``, return pairwise best-match summary.
      - ``sum``: extract numbers with consistent units from ``text``,
        return the total.

    No session writes — the agent uses this as a verification step
    when its own LLM-based numerical reasoning is unreliable.
    """

    operation: Literal["compare", "sum"]
    a_text: str | None = None
    b_text: str | None = None
    text: str | None = None
    rel_tolerance: float = 0.01


@router.post("/api/admin/provenienz/calculator")
async def calculator_step(body: CalculatorRequest, request: Request) -> dict:
    """Run the requested numerical operation deterministically and
    return a structured result the agent can use without re-doing
    the math itself.
    """
    del request  # stateless endpoint — config + session unused
    from local_pdf.provenienz.calculator import (
        best_pairwise_compare,
        parse_quantities,
        sum_quantities,
    )

    def _q(q: Any) -> dict[str, Any]:
        return {"value": q.value, "unit": q.unit, "raw_unit": q.raw_unit}

    if body.operation == "compare":
        if not body.a_text or not body.b_text:
            raise HTTPException(status_code=400, detail="compare requires a_text and b_text")
        a_qs = parse_quantities(body.a_text)
        b_qs = parse_quantities(body.b_text)
        result = best_pairwise_compare(a_qs, b_qs, rel_tolerance=body.rel_tolerance)
        return {
            "operation": "compare",
            "a_quantities": [_q(q) for q in a_qs],
            "b_quantities": [_q(q) for q in b_qs],
            **result,
        }
    if body.operation == "sum":
        if not body.text:
            raise HTTPException(status_code=400, detail="sum requires text")
        qs = parse_quantities(body.text)
        result = sum_quantities(qs)
        return {
            "operation": "sum",
            "quantities": [_q(q) for q in qs],
            **result,
        }
    raise HTTPException(status_code=400, detail=f"unknown operation: {body.operation}")


class RegisterLookupRequest(BaseModel):
    """Body for the RegisterLookup tool executor.

    The agent's planner emits ``capability_request name='RegisterLookup'``
    when a claim references a Verzeichnis entry ("siehe Tabelle 5",
    "[3]", "Abb. 7", "Kapitel 3.2"). This route runs the actual lookup
    against the on-disk consolidated Verzeichnis and emits a search-style
    ActionProposal.

    Both ``kind`` and ``number`` are optional — if missing, they're
    parsed out of the task's ``query`` payload via
    ``detect_register_target``. Specifying them lets the caller bypass
    the heuristic when it already knows the target.
    """

    task_node_id: str
    kind: str | None = None  # toc / list_of_tables / list_of_figures / bibliography
    number: str | None = None
    triggered_from_node_id: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/register-lookup",
    status_code=201,
)
async def register_lookup_step(
    session_id: str, body: RegisterLookupRequest, request: Request
) -> dict:
    """Execute the RegisterLookup tool: resolve a Verzeichnis-reference
    in the task's query into a structured ``{number, title, page}`` hit.

    Detection precedence:
      1. If body.kind + body.number are provided, use those verbatim.
      2. Else parse the task's query via ``detect_register_target``.
      3. Else return an empty proposal (no register reference found).

    For non-bibliography hits the proposal carries
    ``follow_up_query_suggestion`` — the entry's title — so the user/UI
    can one-click kick off a regular ``search`` step that retrieves the
    actual table/figure content (the metadata alone doesn't verify a
    claim about the table values). Bibliography hits don't get a
    suggestion since the citation IS the answer.
    """
    from local_pdf.api.schemas import BoxKind
    from local_pdf.provenienz.bib_matcher import match_bib_to_corpus
    from local_pdf.provenienz.registers import (
        detect_register_target,
        lookup_register_entry,
    )

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
    target_kind: BoxKind | None
    target_number: str | None
    if body.kind and body.number:
        try:
            target_kind = BoxKind(body.kind)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"invalid kind: {body.kind}") from e
        target_number = body.number
        detection_source = "explicit"
    else:
        detected = detect_register_target(query)
        if detected is None:
            target_kind = None
            target_number = None
        else:
            target_kind, target_number = detected
        detection_source = "from-query"

    hits_payload: list[dict] = []
    follow_up: str | None = None
    if target_kind is not None and target_number is not None:
        entry = lookup_register_entry(cfg.data_root, meta.slug, target_kind, target_number)
        if entry is not None:
            text = (
                f"{target_kind.value} #{entry['number']} (Seite {entry['page']}): {entry['title']}"
                if entry["page"]
                else f"{target_kind.value} #{entry['number']}: {entry['title']}"
            )
            hit: dict = {
                "box_id": f"register:{target_kind.value}:{entry['number']}",
                "text": text,
                "score": 1.0,
                "doc_slug": meta.slug,
                "searcher": "register_lookup",
            }
            # Reactive: bibliography hits auto-fire BibFileMatcher so the
            # user immediately sees whether the cited document is already
            # in the local corpus. Token-overlap heuristic — falsy /
            # ambiguous matches return None and are simply not attached.
            # The matcher excludes the current slug so we don't surface
            # "this same doc cites itself".
            if target_kind == BoxKind.bibliography:
                corpus_match = match_bib_to_corpus(entry["title"], cfg.data_root)
                if corpus_match is not None and corpus_match["slug"] != meta.slug:
                    hit["corpus_match"] = corpus_match
            hits_payload.append(hit)
            if target_kind != BoxKind.bibliography:
                follow_up = entry["title"]

    if hits_payload:
        recommended = ActionOption(
            label=f"{len(hits_payload)} Verzeichnis-Treffer übernehmen",
            args={"hits": hits_payload, "follow_up_query_suggestion": follow_up},
        )
        alternatives: list[ActionOption] = []
    else:
        recommended = ActionOption(
            label="Kein Verzeichnis-Treffer — als manual_review markieren",
            args={"hits": [], "follow_up_query_suggestion": None},
        )
        alternatives = []

    reasoning_parts = [f"detection={detection_source}"]
    if target_kind is not None:
        reasoning_parts.append(f"kind={target_kind.value}")
    if target_number is not None:
        reasoning_parts.append(f"number={target_number}")
    reasoning_parts.append(f"hits={len(hits_payload)}")

    payload = ActionProposalPayload(
        step_kind="search",
        anchor_node_id=body.task_node_id,
        recommended=recommended,
        alternatives=alternatives,
        reasoning="RegisterLookup: " + ", ".join(reasoning_parts),
        guidance_consulted=[],
    )
    landed = append_node(
        sd,
        _attach_trail(
            build_proposal_node(session_id=session_id, actor="system", payload=payload),
            body.triggered_from_node_id,
        ),
    )
    return landed.__dict__


class CrossDocSearchRequest(BaseModel):
    """Run an InDocSearcher in a DIFFERENT slug than the session's
    own. Used to "continue the task" in a cited document the user just
    opened via BibFileMatcher's corpus_match — no new session needed,
    the search_result Nodes land in the current session and carry
    ``doc_slug=target_slug`` so downstream consumers see they came
    from elsewhere.
    """

    task_node_id: str
    target_slug: str
    top_k: int = 5
    triggered_from_node_id: str | None = None


@router.post(
    "/api/admin/provenienz/sessions/{session_id}/cross-doc-search",
    status_code=201,
)
async def cross_doc_search_step(
    session_id: str, body: CrossDocSearchRequest, request: Request
) -> dict:
    """Same shape as ``/search`` but uses ``body.target_slug`` for the
    InDocSearcher corpus instead of the session's own slug. The hits
    are still appended into the current session — the session itself
    stays bound to its original slug, only the per-hit ``doc_slug``
    changes.

    Validates that *target_slug* exists in the data_root (a meta.json
    must be present); otherwise the agent could spawn nodes pointing
    at non-existent docs.
    """
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
    meta = read_meta(sd)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session meta missing: {session_id}")
    if not (cfg.data_root / body.target_slug / "meta.json").exists():
        raise HTTPException(
            status_code=404, detail=f"target slug not in corpus: {body.target_slug}"
        )
    nodes, _ = read_session(sd)
    task = next((n for n in nodes if n.node_id == body.task_node_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task node not found: {body.task_node_id}")
    if task.kind != "task":
        raise HTTPException(status_code=400, detail=f"anchor must be task, got kind={task.kind}")

    query = task.payload.get("query", "")
    # No exclude_box_ids — the foreign doc has no root_chunk in this
    # session, so nothing to exclude.
    searcher = InDocSearcher(data_root=cfg.data_root, slug=body.target_slug)
    hits = searcher.search(query, top_k=body.top_k)
    hits_payload = [
        {
            "box_id": h.box_id,
            "text": h.text,
            "score": h.score,
            "doc_slug": h.doc_slug,  # = body.target_slug
            "searcher": h.searcher,
        }
        for h in hits
    ]
    payload = ActionProposalPayload(
        step_kind="search",
        anchor_node_id=body.task_node_id,
        recommended=ActionOption(
            label=f"{len(hits_payload)} Treffer aus {body.target_slug} übernehmen",
            args={"hits": hits_payload},
        ),
        alternatives=[
            ActionOption(label="Nur Top-1 übernehmen", args={"hits": hits_payload[:1]}),
        ],
        reasoning=(
            f"CrossDocSearch InDocSearcher in {body.target_slug}, "
            f"top_k={body.top_k}, hits={len(hits_payload)}"
        ),
        guidance_consulted=[],
    )
    landed = append_node(
        sd,
        _attach_trail(
            build_proposal_node(session_id=session_id, actor="system", payload=payload),
            body.triggered_from_node_id,
        ),
    )
    return landed.__dict__


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
    nodes, edges = read_session(sd)
    task = next((n for n in nodes if n.node_id == body.task_node_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task node not found: {body.task_node_id}")
    if task.kind != "task":
        raise HTTPException(status_code=400, detail=f"anchor must be task, got kind={task.kind}")

    query = task.payload.get("query", "")
    actor = "system"  # this step doesn't call an LLM in v1
    # Exclude every chunk the investigation already derived from. The
    # task's forward-flowing context lists them; for legacy tasks
    # without that context, the ancestor walk reconstructs the same
    # set from the edge graph. Either way, root_chunk_id is added as
    # a defensive fallback.
    task_context = get_context(task.payload)
    visited = task_context.get("visited_box_ids", [])
    if not visited:
        visited = _ancestor_chunk_box_ids(nodes, edges, body.task_node_id)
    exclude_set = {meta.root_chunk_id, *visited}
    searcher = InDocSearcher(
        data_root=cfg.data_root,
        slug=meta.slug,
        exclude_box_ids=tuple(sorted(exclude_set)),
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
        sd,
        _attach_trail(
            build_proposal_node(session_id=session_id, actor=actor, payload=payload),
            body.triggered_from_node_id,
        ),
    )
    return landed.__dict__


def _llm_evaluate(
    claim_text: str,
    candidate_chunk_text: str,
    provider: str,
    *,
    extra_system: str = "",
    calc_hint: str = "",
) -> dict:
    """Ask the LLM whether a candidate chunk is the source of a claim.

    Returns a dict with ``verdict`` (constrained set), ``confidence``
    (float 0..1) and ``reasoning`` (short German sentence). The
    ``provider`` arg is plumbed-through but unused today. Tests
    monkey-patch this symbol on the module.
    """
    del provider  # reserved for Stage 6 routing
    system = EVALUATE_SYSTEM + (extra_system or "") + _NO_THINK
    # Frame the claim as a hypothesis to be tested by the candidate's
    # own content, not as an established fact looking for confirmation.
    # Combined with the GRUND-PRINZIP block in EVALUATE_SYSTEM, this
    # blocks confirmation bias when the upstream QUELL-KONTEXT happens
    # to contain the claim text verbatim.
    #
    # Calculator hint: deterministic (number, unit) comparison results
    # injected as ground truth so the LLM doesn't have to do the math
    # in its head. Built by the caller via _build_calculator_hint.
    parts = [
        "## Hypothese (zu prüfen)",
        claim_text,
        "",
        "## Kandidaten-Treffer (muss die Hypothese AUS SICH SELBST belegen)",
        candidate_chunk_text,
        "",
    ]
    if calc_hint:
        parts.extend(
            [
                "## Werkzeug-Ergebnis: deterministischer Zahlen-Vergleich",
                calc_hint,
                "",
                "Diese Werte stammen aus einer deterministischen Berechnung "
                "und gelten als Tatsachen — korrigiere sie nicht aus eigener "
                "Schätzung. Das Werkzeug prüft NUR strikte Gleichheit, ohne "
                "Toleranz. Wenn die Werte exakt übereinstimmen, ist das ein "
                "starkes Indiz für 'likely-source'. Wenn sie nicht exakt "
                "übereinstimmen, urteile NICHT eigenmächtig 'na ja, fast' — "
                "die Bewertung der Differenz ist eine Domain-Frage und wird "
                "ausschließlich durch aktive Skills (z.B. konservative "
                "Aufrundung in bestimmten Sicherheits-Kontexten) entschieden. "
                "Ohne aktiven Skill der die Differenz domain-spezifisch "
                "rechtfertigt: Zahlen-Differenz = WIDERSPRUCH oder "
                "PARTIAL-SUPPORT, nicht 'likely-source'.",
                "",
            ]
        )
    parts.append("JSON:")
    user = "\n".join(parts)
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
    # Click-trail: persisted on the spawned action_proposal so the
    # decide-handler can copy it onto the spawned evaluation.
    triggered_from_node_id: str | None = None


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

    nodes, edges = read_session(sd)
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
        sr_for_caption = anchor
    else:
        sr = anchor
        candidate_text = str(sr.payload.get("text", ""))
        sr_for_caption = sr
    # When the candidate hit / sub-statement carries a caption (figure
    # or table), prepend it so the LLM evaluating the candidate sees
    # the label alongside the content.
    cap = str(sr_for_caption.payload.get("caption_text", "")).strip()
    if cap:
        candidate_text = f"Caption: {cap}\n\n{candidate_text}"
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
    extra_system = (
        _build_decision_context(
            claim,
            nodes,
            meta,
            task=eval_task,
            consuming_step="evaluate",
            data_root=cfg.data_root,
        )
        + extra_system
    )
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
    # Auto-fire deterministic tools and persist results as
    # tool_annotation Nodes BEFORE building the prompt. The LLM never
    # has to do mental table-parsing, mental arithmetic, or mental
    # consistency-checking; structured ground-truth is always
    # available when applicable.
    _ensure_table_annotation(sd, session_id, sr, nodes, edges, cfg.data_root)
    nodes, edges = read_session(sd)
    _ensure_table_consistency_annotation(sd, session_id, sr, nodes, edges)
    _ensure_calculator_annotation(sd, session_id, sr, claim, nodes, edges)
    # Re-read after potential persist so the gather sees the new
    # annotations. Cheap: read_session is a single-pass JSONL scan.
    nodes, edges = read_session(sd)
    calc_hint, tool_calls = _persisted_tool_calls_for_sr(body.search_result_node_id, nodes, edges)
    try:
        verdict_payload = _llm_evaluate(
            claim.payload.get("text", ""),
            candidate_text,
            body.provider or "vllm",
            extra_system=extra_system,
            calc_hint=calc_hint,
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
                # Tool-call audit travels through the args bundle so it
                # lands on the eval Node payload at /decide. Mirrors how
                # capability_scan persists; lets the UI render "tools
                # that fired during this evaluation".
                "tool_calls": tool_calls,
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
                    "tool_calls": [],
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
        sd,
        _attach_trail(
            build_proposal_node(session_id=session_id, actor=actor, payload=payload),
            body.triggered_from_node_id,
        ),
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
    nodes, edges = read_session(sd)
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
        _build_decision_context(
            claim,
            nodes,
            meta,
            task=re_task,
            consuming_step="evaluate",
            data_root=cfg.data_root,
        )
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
    # Same auto-fire-and-persist as the main evaluate route — see there.
    _ensure_table_annotation(sd, session_id, sr, nodes, edges, cfg.data_root)
    nodes, edges = read_session(sd)
    _ensure_table_consistency_annotation(sd, session_id, sr, nodes, edges)
    _ensure_calculator_annotation(sd, session_id, sr, claim, nodes, edges)
    nodes, edges = read_session(sd)
    calc_hint, tool_calls = _persisted_tool_calls_for_sr(sr.node_id, nodes, edges)
    try:
        verdict_payload = _llm_evaluate(
            claim.payload.get("text", ""),
            sr.payload.get("text", ""),
            body.provider or "vllm",
            extra_system=extra_system,
            calc_hint=calc_hint,
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
                "tool_calls": tool_calls,
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
                    "tool_calls": [],
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
    # Click-trail: persisted on the spawned action_proposal so the
    # decide-handler can copy it onto every spawned sub_statement.
    triggered_from_node_id: str | None = None


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
        sd,
        _attach_trail(
            build_proposal_node(session_id=session_id, actor=actor, payload=payload),
            body.triggered_from_node_id,
        ),
    )
    return landed.__dict__


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
    triggered_from_node: Node | None = None,
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

    ``triggered_from_node`` carries the click-trail when "Was als
    nächstes?" is invoked from a Folge-Knoten (e.g. a Bewertungs-Tile
    routes to the parent search_result for re-planning). If the trail
    points at an evaluation Node the planner is told NOT to re-evaluate
    but to deepen the trace instead.
    """
    anchor_summary = (
        f"kind={anchor.kind}, payload={json.dumps(anchor.payload, ensure_ascii=False)[:600]}"
    )
    metadata_block = _format_box_metadata_block(anchor)
    trigger_block = ""
    if triggered_from_node is not None and triggered_from_node.kind == "evaluation":
        prior_verdict = str(triggered_from_node.payload.get("verdict", ""))
        prior_reasoning = str(triggered_from_node.payload.get("reasoning", ""))[:200]
        is_table_anchor = (
            anchor.kind == "search_result" and str(anchor.payload.get("box_kind", "")) == "table"
        )
        is_likely_source = prior_verdict == "likely-source"
        table_likely_source_block = ""
        if is_table_anchor and is_likely_source:
            table_likely_source_block = (
                "- `investigate_table` ist hier der KANONISCHE Schritt: der "
                "Treffer ist eine Tabelle UND wurde als wahrscheinliche "
                "Quelle bewertet. Die Tabelle muss jetzt entlang von 3 "
                "Achsen abgesichert werden (Text-Referenz / Quellen-"
                "Attribution / Semantik-Rueckpruefung). Konsistenz wurde "
                "bereits beim Bewerten als Werkzeug-Annotation gefeuert. "
                "Diese Empfehlung gilt unabhängig vom bisherigen Pfad — "
                "jede neue likely-source-Bewertung an einer Tabelle ist "
                "eine eigene Untersuchungs-Gelegenheit.\n"
            )
        trigger_block = (
            "## KONTEXT — du wirst aus einer Bewertung heraus aufgerufen\n"
            f"Vorheriges Verdict: {prior_verdict}\n"
            f"Vorherige Begründung: {prior_reasoning}\n\n"
            "Der Suchtreffer wurde bereits bewertet. Der Nutzer will den "
            "Treffer JETZT VERTIEFEN — nicht nochmal bewerten. `evaluate` "
            "ist deshalb aus den verfügbaren Steps entfernt.\n\n"
            "Wähle aus den verbleibenden Steps:\n"
            f"{table_likely_source_block}"
            "- `promote_search_result` wenn der Treffer weitere prüfbare "
            "Aussagen enthält: spawnt einen abgeleiteten Chunk-Knoten, auf "
            "dem extract_claims regulär läuft und neue Claim-Knoten "
            "anlegt — recursive claim tracing über die kanonische "
            "Pipeline.\n"
            "- `propose_stop` nur wenn die Aussage hinreichend belegt ist "
            "und der Treffer keine weiteren prüfbaren Behauptungen "
            "enthält.\n\n"
        )
    system = NEXT_STEP_SYSTEM + (extra_system or "") + _NO_THINK
    user = (
        f"## Knoten\n{anchor_summary}\n\n"
        f"{metadata_block}"
        f"## Sitzungs-Ziel\n{session_goal or '(nicht gesetzt)'}\n\n"
        f"{trigger_block}"
        f"## Verfügbare Steps\n{_steps_block(available_steps)}\n\n"
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
    # ``decompose_hit`` is intentionally absent: recursive claim tracing
    # goes through ``promote_search_result`` → new chunk →
    # ``extract_claims``, which spawns regular claim Nodes. The legacy
    # /decompose-hit endpoint stays callable for old action_proposals,
    # but the planner won't recommend it for new flows.
    "search_result": [
        "evaluate",
        "promote_search_result",
        "investigate_table",
        "propose_stop",
    ],
    # Legacy: ``sub_statement`` Nodes from before the unification still
    # need their pipeline to read existing sessions.
    "sub_statement": ["evaluate", "propose_stop"],
    "evaluation": ["propose_stop"],
}


# Human-readable descriptions of each registered step. The planner sees
# these in the user prompt so it can pick the right step from semantics
# instead of guessing from the bare name. Keep concise — these are read
# by the LLM, not by humans, but a senior reviewer should still recognise
# the rules of when each step applies.
_STEP_DESCRIPTIONS: dict[str, str] = {
    "extract_claims": (
        "Aus dem Chunk-Text alle messbaren Aussagen herausziehen. Erste "
        "Aktion auf einem neu eröffneten Chunk."
    ),
    "formulate_task": (
        "Aus einer Aussage eine konkrete Suchanfrage formulieren — "
        "Schlüsselwörter, Zahlen, Einheiten."
    ),
    "search": (
        "Die formulierte Suchanfrage gegen das Korpus laufen lassen. "
        "Liefert Suchtreffer als Kandidaten-Belege."
    ),
    "evaluate": (
        "Beurteile ob ein einzelner Suchtreffer die Aussage stützt, "
        "teilweise stützt, widerspricht oder unrelated ist. EINE Bewertung "
        "pro Treffer-Aussage-Paar. Genug wenn der Treffer kurz, atomar und "
        "selbst keine weiterzuverfolgenden Behauptungen enthält."
    ),
    "decompose_hit": (
        "[DEPRECATED] Wurde durch promote_search_result + extract_claims "
        "ersetzt. Bleibt nur für alte Sitzungen lesbar."
    ),
    "promote_search_result": (
        "DER kanonische Weg, einen Suchtreffer tiefer zu erforschen: spawnt "
        "einen abgeleiteten Chunk-Knoten (recursion_depth = parent + 1), "
        "auf dem dann extract_claims regulär läuft und eigene Claim-Knoten "
        "anlegt. Nutze IMMER, wenn der Treffer weitere prüfbare Aussagen "
        "enthält — egal ob ein einzelner Satz oder ein ganzer Absatz. Die "
        "Pipeline wiederholt sich auf jeder Tiefe."
    ),
    "propose_stop": (
        "Diese Untersuchung abschließen — kein weiterer Schritt sinnvoll. "
        "Nutze NUR wenn alle Behauptungen belegt oder unbelegbar sind ODER "
        "wenn weitere Recherche das Ziel nicht voranbringt."
    ),
    "investigate_table": (
        "Tabellen-Untersuchungs-Choreografie: spawnt 3 Folge-Aufgaben "
        "rund um einen Tabellen-Treffer (Text-Referenz, Quellen-"
        "Attribution, Semantik-Rueckpruefung). Konsistenz-Pruefung "
        "wurde bereits beim Bewerten als Werkzeug-Annotation gefeuert. "
        "Wähle DIESEN Step wenn der Anker ein search_result mit "
        "box_kind=table ist UND eine Bewertung verdict=likely-source "
        "vorliegt — die Tabelle wurde als wahrscheinliche Quelle "
        "identifiziert, jetzt soll sie systematisch abgesichert werden. "
        "Nicht für Nicht-Tabellen-Treffer."
    ),
}


def _format_step_with_desc(name: str) -> str:
    """Render one step as a markdown bullet with its description (or
    just the name if no description is registered). Used by the next-step
    family of prompts so the planner sees WHEN each step applies."""
    desc = _STEP_DESCRIPTIONS.get(name, "")
    return f"- **{name}**: {desc}" if desc else f"- **{name}**"


def _steps_block(available_steps: list[str]) -> str:
    """Format the available-steps section of a planner prompt: one
    markdown bullet per step, or ``(keine)`` when the list is empty."""
    if not available_steps:
        return "(keine)"
    return "\n".join(_format_step_with_desc(s) for s in available_steps)


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
        f"## Verfügbare Steps\n{_steps_block(available_steps)}\n\n"
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
        f"## Verfügbare Steps\n{_steps_block(available_steps)}\n\n"
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
    # Anker-Inhalt is intentionally truncated to 400 chars and labeled as
    # "Anker-Inhalt (zur Orientierung, KEINE Fakten)" so the LLM treats it
    # as topic-only context, not as established truth to reason about.
    user = (
        f"Geplanter Prozess-Schritt: {step_label} ({step_kind})\n\n"
        f"Sitzungs-Ziel: {session_goal or '(nicht gesetzt)'}\n"
        f"Recherche-Frage zur Aussage: {claim_goal or '(nicht relevant)'}\n\n"
        f"Anker-Inhalt (NUR zur Themen-Orientierung, NICHT als bewiesene "
        f"Tatsachen behandeln): {anchor_summary[:400]}\n\n"
        f"Begründung in einem Satz, warum dieser Schritt jetzt der "
        f"richtige Prozess-Zug ist (kein Outcome-Vorgriff):"
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
    raw = _strip_thinking_tags(completion.text or "")
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
    raw = _strip_thinking_tags(completion.text or "")
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        raw = raw[1:-1].strip()
    raw = raw[:300]
    if not raw:
        raise RuntimeError("_llm_propose_stop: empty response from LLM")
    return raw


class ProposeStopRequest(BaseModel):
    anchor_node_id: str
    provider: str | None = None
    # Click-trail: persisted on the spawned action_proposal so the
    # decide-handler can copy it onto the spawned stop_proposal.
    triggered_from_node_id: str | None = None


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
        sd,
        _attach_trail(
            build_proposal_node(session_id=session_id, actor=actor, payload=payload),
            body.triggered_from_node_id,
        ),
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
    # Click-trail: when "Was als nächstes?" is invoked from a Folge-Knoten
    # (e.g. a Bewertungs-Tile that routes to the parent search_result),
    # the frontend forwards the original tile's node_id here. The backend
    # persists it on the spawned plan_proposal so the canvas can draw a
    # "triggered-from" edge, and the planner sees it as extra context
    # (deepen the trace, not re-evaluate). Optional — None = unchanged
    # behaviour for direct-anchor invocations.
    triggered_from_node_id: str | None = None


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
    triggered_from_node: Node | None = None,
) -> Iterator[PhaseEvent | CompleteEvent]:
    """Phase-by-phase execution of /next-step.

    Yields PhaseEvent on every started/completed boundary and a final
    CompleteEvent with the persisted Node. Both /next-step (drained)
    and /next-step/stream (forwarded as SSE) consume this iterator.

    ``triggered_from_node`` carries the click-trail Node when the
    request was raised from a Folge-Knoten (e.g. a Bewertungs-Tile).
    The node_id is persisted on the spawned plan_proposal so the layout
    can draw a "triggered-from" edge, and the planner gets a context
    block instructing it to deepen the trace rather than re-run the
    same evaluation.
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
    available_steps = list(_VALID_STEPS_FOR_KIND.get(anchor.kind, []))
    # Click-trail constraint: when the run was triggered from a
    # Bewertungs-Tile (evaluation Node) on its parent search_result,
    # `evaluate` is structurally removed from the available steps —
    # the hit was just evaluated, the user wants to deepen, not
    # re-bewerten. Forces the planner to pick decompose_hit /
    # promote_search_result / propose_stop.
    if (
        triggered_from_node is not None
        and triggered_from_node.kind == "evaluation"
        and anchor.kind == "search_result"
        and "evaluate" in available_steps
    ):
        available_steps = [s for s in available_steps if s != "evaluate"]
    # investigate_table is only applicable to table-typed search_results.
    # Strip it from the offer set otherwise so the planner can't pick it
    # for text/figure hits.
    if (
        anchor.kind == "search_result"
        and str(anchor.payload.get("box_kind", "")) != "table"
        and "investigate_table" in available_steps
    ):
        available_steps = [s for s in available_steps if s != "investigate_table"]
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
        triggered_from_node=triggered_from_node,
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

    # ── Phase: validate (clamp invalid step picks + auto-promote) ─────
    p_start = time.monotonic()
    yield PhaseEvent(
        phase="validate",
        status="started",
        label="Step-Wahl validieren",
        ms_since_run_start=now_ms(),
    )
    invalid_step_picked: str | None = None
    promoted_from_kind: str | None = None
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
    # Auto-promote: when the LLM picks kind=manual_review (oder
    # capability_request) but names a registered executable_step from
    # available_steps, that is a Präzedenz-Fehler — der Step existiert
    # und ist autonom ausführbar. Den Vorschlag deterministisch zum
    # executable_step zurückbiegen statt den User mit einer
    # Pseudo-Mensch-Aufgabe zu konfrontieren.
    elif (
        plan["kind"] in ("manual_review", "capability_request")
        and available_steps
        and plan.get("name") in available_steps
    ):
        promoted_from_kind = plan["kind"]
        plan = {
            **plan,
            "kind": "executable_step",
            "description": (
                f"[Auto-promoted from {promoted_from_kind}] " + str(plan.get("description") or "")
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
            "promoted_from": promoted_from_kind,
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
                # Click-trail: empty string when this run came from a
                # direct-anchor click. Non-empty when "Was als nächstes?"
                # was invoked from a Folge-Knoten (e.g. Bewertungs-Tile)
                # — the layout reads this to draw the "triggered-from"
                # edge from the trail node back to this plan_proposal.
                "triggered_from_node_id": (body.triggered_from_node_id or ""),
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
) -> tuple[Path, SessionMeta, Node, Node | None]:
    """Pre-flight resolution shared by both /next-step variants.

    Returns ``(session_dir, meta, anchor, triggered_from_node)`` —
    the trail node is None when ``body.triggered_from_node_id`` is
    unset or doesn't resolve. A missing trail node is non-fatal (the
    click-trail is purely informational); only the anchor must exist.

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
    triggered_from_node: Node | None = None
    if body.triggered_from_node_id:
        triggered_from_node = next(
            (n for n in nodes if n.node_id == body.triggered_from_node_id), None
        )
    return sd, meta, anchor, triggered_from_node


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
    sd, meta, anchor, triggered_from_node = _resolve_next_step_inputs(cfg, session_id, body)
    final: dict | None = None
    for ev in _next_step_run(
        cfg=cfg,
        session_id=session_id,
        body=body,
        anchor=anchor,
        meta=meta,
        sd=sd,
        triggered_from_node=triggered_from_node,
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
    sd, meta, anchor, triggered_from_node = _resolve_next_step_inputs(cfg, session_id, body)

    def event_stream() -> Iterator[str]:
        try:
            for ev in _next_step_run(
                cfg=cfg,
                session_id=session_id,
                body=body,
                anchor=anchor,
                meta=meta,
                sd=sd,
                triggered_from_node=triggered_from_node,
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
    # Trail-as-Trunk: when the action_proposal carries a click-trail
    # (set by /extract-claims, /formulate-task, /search, /evaluate,
    # /decompose-hit, /propose-stop step routes when triggered_from_node_id
    # was forwarded from the frontend), every node spawned by this
    # decision inherits the same trail. The layout reads the trail to
    # render a single visual strand "Bewertung → plan → action → new_node"
    # instead of branching back to the structural anchor.
    trail_id = str(proposal.payload.get("triggered_from_node_id", "") or "")
    trail_node = next((n for n in nodes if n.node_id == trail_id), None) if trail_id else None

    def _payload_with_trail(payload: dict) -> dict:
        if trail_id:
            return {**payload, "triggered_from_node_id": trail_id}
        return payload

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
        # Auto-extract per-claim enrichment annotations via enrichment
        # skills that fire on ``extract_claims`` and attach to claims.
        # The default ``claim_background`` skill is seeded by the
        # legacy-to-skills migration; users can register additional
        # skills (or disable the default) without touching this code.
        from local_pdf.provenienz.skill_dispatcher import (
            list_enrichment_skills,
            run_enrichment_skill,
        )

        enrichment_skills = [
            s
            for s in list_enrichment_skills(cfg.data_root, fires_on="extract_claims")
            if s.output.attaches_to == "claim"
        ]
        skill_results: dict[str, list[str]] = {}
        for skill in enrichment_skills:
            try:
                skill_results[skill.skill_id] = run_enrichment_skill(
                    skill,
                    claim_texts,
                    chunk_text=chunk_text_for_goals,
                    data_root=cfg.data_root,
                )
            except Exception as exc:
                _log.warning("enrichment skill %s failed: %s", skill.name, exc)
                skill_results[skill.skill_id] = [""] * len(claim_texts)
        # Claims inherit recursion_depth from the chunk they're extracted
        # from. Pre-unification chunks miss the field → fall back to 0.
        chunk_depth = (
            int(chunk_for_goals.payload.get("recursion_depth", 0))
            if chunk_for_goals is not None
            else 0
        )
        # Forward-flow context for claims: inherit from the origin
        # chunk so a later /search on a task derived from this claim
        # sees the full ancestor visited_box_ids list.
        claim_parent_context = (
            get_context(chunk_for_goals.payload) if chunk_for_goals is not None else empty_context()
        )
        for idx, ct in enumerate(claim_texts):
            goal_for_claim = claim_goals[idx] if idx < len(claim_goals) else ""
            claim_node_id = new_id()
            claim_context = merge_contexts(
                claim_parent_context,
                {"origin_chain": [origin_entry(claim_node_id, "claim", ct[:160])]},
            )
            claim = append_node(
                sd,
                Node(
                    node_id=claim_node_id,
                    session_id=session_id,
                    kind="claim",
                    payload=_payload_with_trail(
                        {
                            "text": ct,
                            "source_node_id": anchor_chunk,
                            "goal": goal_for_claim,
                            "recursion_depth": chunk_depth,
                            "context": claim_context,
                        }
                    ),
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
            # Per-claim enrichment annotations — one Node per enrichment
            # skill that produced a non-empty result for this claim.
            # Empty results are LLM-signalled "nothing to add" / parse
            # failure → skipped silently.
            for skill in enrichment_skills:
                results = skill_results.get(skill.skill_id, [])
                ann_text = results[idx] if idx < len(results) else ""
                if not ann_text or not ann_text.strip():
                    continue
                ann_node = append_node(
                    sd,
                    Node(
                        node_id=new_id(),
                        session_id=session_id,
                        kind=skill.output.annotation_kind,
                        payload=_payload_with_trail(
                            {
                                "text": ann_text.strip(),
                                "claim_node_id": claim.node_id,
                                "source_chunk_node_id": anchor_chunk,
                                "skill_id": skill.skill_id,
                                "skill_name": skill.name,
                                "skill_version": skill.version,
                            }
                        ),
                        actor="system",
                    ),
                )
                spawned_nodes.append(ann_node)
                spawned_edges.append(
                    append_edge(
                        sd,
                        Edge(
                            edge_id=new_id(),
                            session_id=session_id,
                            from_node=ann_node.node_id,
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
        # Evaluation breadcrumbs for sub_statements: when the action_proposal
        # carries a trail pointing at an evaluation Node, attach the verdict
        # + reasoning to each spawned sub_statement so the downstream prompt
        # context (and side-panel) can show why this fact is being checked.
        sub_breadcrumbs: dict[str, str] = {}
        if trail_node is not None and trail_node.kind == "evaluation":
            sub_breadcrumbs = {
                "origin_evaluation_id": trail_node.node_id,
                "origin_evaluation_verdict": str(trail_node.payload.get("verdict", "")),
                "origin_evaluation_reasoning": str(trail_node.payload.get("reasoning", ""))[:400],
            }
        for sub_text in sub_texts:
            if not isinstance(sub_text, str) or not sub_text.strip():
                continue
            sub_node = append_node(
                sd,
                Node(
                    node_id=new_id(),
                    session_id=session_id,
                    kind="sub_statement",
                    payload=_payload_with_trail(
                        {
                            "text": sub_text.strip(),
                            "parent_search_result_id": anchor_sr,
                            **sub_breadcrumbs,
                        }
                    ),
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

    if step_kind == "promote_search_result":
        # The proposal carries the full chunk payload (built at proposal-time
        # by walking the search_result's audit chain). On accept we just
        # materialise it into a chunk Node and wire the standard
        # decision → triggers → chunk + chunk → search_result (promoted-from)
        # edges. Override is not supported v1 — the promote step has no free
        # parameters the user could meaningfully override.
        anchor_sr_id = proposal.payload["anchor_node_id"]
        if body.accepted == "override":
            raise HTTPException(
                status_code=400,
                detail="override path not supported for promote_search_result step (v1)",
            )
        if body.accepted == "recommended":
            chunk_args = dict(proposal.payload["recommended"]["args"] or {})
        else:  # alt
            idx = body.alt_index or 0
            alts = proposal.payload.get("alternatives", [])
            if not (0 <= idx < len(alts)):
                raise HTTPException(status_code=400, detail=f"alt_index out of range: {idx}")
            chunk_args = dict(alts[idx]["args"] or {})
        # Trail propagation: mirror the other branches — the proposal-level
        # trail (read off the proposal payload) is the source of truth for
        # what the chunk should carry. The args copy from
        # _build_promoted_chunk_payload happens to set the same value at
        # proposal-creation time, but we re-apply here so the chunk stays
        # consistent with `_payload_with_trail` semantics used elsewhere.
        chunk_args.pop("triggered_from_node_id", None)
        # Stamp this chunk's origin_chain entry now that we have a
        # concrete node_id. The helper that built chunk_args already
        # populated visited_box_ids + recursion_depth; we just append
        # the breadcrumb.
        chunk_node_id = new_id()
        # get_context normalises whatever shape arrived in chunk_args
        # (dict-from-JSON or already-typed NodeContext) into a clean
        # NodeContext so the type checker stops complaining about the
        # union return.
        existing_ctx = get_context(chunk_args)
        chunk_text_for_label = str(chunk_args.get("text", ""))[:160] or str(
            chunk_args.get("box_id", "")
        )
        chunk_args["context"] = merge_contexts(
            existing_ctx,
            {"origin_chain": [origin_entry(chunk_node_id, "chunk", chunk_text_for_label)]},
        )
        chunk_node = append_node(
            sd,
            Node(
                node_id=chunk_node_id,
                session_id=session_id,
                kind="chunk",
                payload=_payload_with_trail(chunk_args),
                actor="human",
            ),
        )
        spawned_nodes.append(chunk_node)
        spawned_edges.append(
            append_edge(
                sd,
                Edge(
                    edge_id=new_id(),
                    session_id=session_id,
                    from_node=decision_landed.node_id,
                    to_node=chunk_node.node_id,
                    kind="triggers",
                    reason=None,
                    actor="human",
                ),
            )
        )
        spawned_edges.append(
            append_edge(
                sd,
                Edge(
                    edge_id=new_id(),
                    session_id=session_id,
                    from_node=chunk_node.node_id,
                    to_node=anchor_sr_id,
                    kind="promoted-from",
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
        # Forward-flow context for tasks: inherit from the focus claim
        # (which inherited from its origin chunk). search_step's
        # exclude_box_ids comes from this context's visited_box_ids.
        anchor_claim_node = next((n for n in nodes if n.node_id == anchor_claim_id), None)
        task_parent_context = (
            get_context(anchor_claim_node.payload)
            if anchor_claim_node is not None
            else empty_context()
        )
        task_node_id = new_id()
        task_context = merge_contexts(
            task_parent_context,
            {"origin_chain": [origin_entry(task_node_id, "task", query[:160])]},
        )
        task_node = append_node(
            sd,
            Node(
                node_id=task_node_id,
                session_id=session_id,
                kind="task",
                payload=_payload_with_trail(
                    {
                        "query": query,
                        "focus_claim_id": anchor_claim_id,
                        "context": task_context,
                    }
                ),
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
        # Forward-flow context for search_results: inherit from the
        # task. When a hit lands in a foreign slug (cross-doc search)
        # the slug is added to visited_doc_slugs so a future
        # cross-doc step doesn't loop back into it.
        anchor_task_node = next((n for n in nodes if n.node_id == anchor_task_id), None)
        sr_parent_context = (
            get_context(anchor_task_node.payload)
            if anchor_task_node is not None
            else empty_context()
        )
        for h in hits:
            # Enrich the hit's payload with structured box metadata
            # (page / box_kind / reading_order / bbox / continues_*)
            # from segments.json. Lets the agent + UI reason about
            # whether a hit is a table / figure / paragraph, on which
            # page, in which reading-order position. Falls back to {}
            # if segments.json is missing or the box_id isn't found.
            sr_metadata = _load_box_metadata(
                cfg.data_root,
                str(h.get("doc_slug", "")),
                str(h.get("box_id", "")),
            )
            sr_node_id = new_id()
            hit_doc_slug = str(h.get("doc_slug", ""))
            sr_context = merge_contexts(
                sr_parent_context,
                {
                    "visited_doc_slugs": [hit_doc_slug] if hit_doc_slug else [],
                    "origin_chain": [
                        origin_entry(
                            sr_node_id,
                            "search_result",
                            str(h.get("text", ""))[:160] or str(h.get("box_id", "")),
                        )
                    ],
                },
            )
            sr = append_node(
                sd,
                Node(
                    node_id=sr_node_id,
                    session_id=session_id,
                    kind="search_result",
                    payload=_payload_with_trail(
                        {
                            **h,
                            "task_node_id": anchor_task_id,
                            "context": sr_context,
                            **sr_metadata,
                        }
                    ),
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
            # B: walk back through the eval-chain (prior_evaluation_node_id
            # links one re-eval to its predecessor) and collect all skill
            # IDs that were already injected into prompts. Filter them out
            # so we don't re-fire skills that already had their say —
            # otherwise re-eval → same skills → same gate → infinite loop.
            already_applied = _collect_applied_capabilities_in_chain(
                args.get("prior_evaluation_node_id", ""), nodes
            )
            relevant_apps_for_scan = [
                a for a in all_apps_for_scan if a.approach_id not in already_applied
            ]
            capability_matches = scan_capabilities(
                relevant_apps_for_scan,
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
                is_applied = app.approach_id in already_applied
                if is_applied:
                    reasons = ["Bereits in einem früheren Re-Eval auf dieser Eval-Kette angewendet"]
                capability_scan.append(
                    {
                        "approach_id": app.approach_id,
                        "name": app.name,
                        "parent_capability": app.parent_capability or "",
                        "matched": ok and app.approach_id in matched_ids,
                        "applied_previously": is_applied,
                        "reasons": reasons,
                    }
                )
        except Exception as exc:
            _log.warning("capability scan pre-eval failed: %s", exc)
            capability_scan = []
            capability_matches = []

        # Forward-flow context for evaluations: inherit from the
        # search_result that's being evaluated.
        anchor_sr_node = next((n for n in nodes if n.node_id == anchor_sr_id), None)
        eval_parent_context = (
            get_context(anchor_sr_node.payload) if anchor_sr_node is not None else empty_context()
        )
        eval_node_id = new_id()
        eval_context = merge_contexts(
            eval_parent_context,
            {
                "origin_chain": [
                    origin_entry(
                        eval_node_id,
                        "evaluation",
                        f"{args['verdict']} · {str(args.get('reasoning', ''))[:120]}",
                    )
                ],
            },
        )
        eval_node = append_node(
            sd,
            Node(
                node_id=eval_node_id,
                session_id=session_id,
                kind="evaluation",
                payload=_payload_with_trail(
                    {
                        "verdict": args["verdict"],
                        "confidence": args["confidence"],
                        "reasoning": args["reasoning"],
                        "against_claim_id": args["against_claim_id"],
                        "search_result_node_id": anchor_sr_id,
                        "context": eval_context,
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
                        # Tool-call audit — which deterministic tools
                        # (Calculator, etc.) ran during this evaluate
                        # step. Parallel to capability_scan but for
                        # tools, not skills. Empty list when no tool
                        # produced output.
                        "tool_calls": args.get("tool_calls", []),
                        # Capabilities that were injected into THIS
                        # evaluate's prompt — used by future
                        # capability_scans on descendant evals (via
                        # prior_evaluation_node_id chain) to skip
                        # already-applied skills, breaking the
                        # gate-creation loop. Empty for first-time
                        # evaluates; populated by re_evaluate_step.
                        "applied_capabilities": args.get("capabilities_used", []),
                        # Link to the eval that came before this one in
                        # a re-eval chain — empty for first-time
                        # evaluates, set when this eval was kicked off
                        # from a capability_gate's re-eval flow.
                        "prior_evaluation_node_id": args.get("prior_evaluation_node_id", ""),
                    }
                ),
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
        #
        # A — verdict-based gate threshold: at "good enough" verdicts
        # (likely-source / partial-support) the investigation has
        # converged on a position; further re-eval rarely flips it AND
        # would create the gate-loop the user reported. Skills only
        # gate-up the verdict if it's still in "needs work" territory:
        # unrelated or contradicts.
        gate_eligible = str(args.get("verdict", "")) in {
            "unrelated",
            "contradicts",
        }
        if capability_matches and gate_eligible:
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
                        payload=_payload_with_trail(
                            {
                                "evaluation_node_id": eval_node.node_id,
                                "anchor_node_id": eval_node.node_id,
                                "search_result_node_id": anchor_sr_id,
                                "claim_node_id": claim_id_for_scan,
                                "detected": detected_summary,
                                "capability_ids": cap_ids,
                                "loaded_rules_preview": "\n\n".join(rules_preview_parts),
                                "status": "pending",
                            }
                        ),
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
                payload=_payload_with_trail(
                    {
                        "reason": args["reason"],
                        "close_session": args["close_session"],
                        "anchor_node_id": anchor_id,
                    }
                ),
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
