# Provenienzanalyse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Provenienz tab — an auditable, human-in-the-loop claim-tracing system that grows a knowledge graph (event-log persisted, react-flow rendered) from a starting chunk through claim → task → search → evaluate → decide → stop.

**Architecture:** Append-only JSONL event log per session (mirrors goldens). Open-string node + edge kinds (no migrations on schema growth). `Searcher` Protocol (in-doc BM25 in v1, cross-doc + Azure deferred). LLM steps emit `action_proposal` nodes (recommended + alternatives + reasoning); a separate `/decide` route consumes a decision and spawns the triggered child. Two guidance mechanisms: implicit reason corpus + explicit approach library.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic on backend (no new deps); React + react-flow + dagre on frontend (new deps); BM25 from `local_pdf.comparison.bm25` (existing).

**Spec:** `docs/superpowers/specs/2026-05-05-provenienzanalyse-design.md`

---

## NOTE TO IMPLEMENTING WORKER

**Suggested model per task** is annotated. Haiku for mechanical wiring + tests, Sonnet for handler + UI logic, Opus only when stuck.

**Shared contracts referenced across tasks:**

- `local_pdf.provenienz.storage.{Node, Edge, append_event, read_session, write_meta}` (Stage 1)
- `local_pdf.provenienz.searcher.{Searcher, SearchHit, InDocSearcher}` (Stage 2)
- `local_pdf.provenienz.steps.action_proposal(...)` (Stage 3)
- `POST /api/admin/provenienz/sessions` body `{slug, root_chunk_id}` returns `{session_id, ...}` (Stage 1)
- All step routes consume `{anchor_node_id, provider?}` and return the new `action_proposal` node (Stages 3 & 5)
- `POST /api/admin/provenienz/sessions/{id}/decide` body `{proposal_node_id, accepted, reason?, override?}` returns the new triggered node(s) (Stage 4)

**Branch:** create a feature branch `feat/provenienzanalyse` off main when starting Task 1.1.

---

## Stage 1 — Backend storage + session CRUD

### Task 1.1 — Storage primitives (Node, Edge, event log)

**Model:** Haiku
**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/provenienz/__init__.py`
- Create: `features/pipelines/local-pdf/src/local_pdf/provenienz/storage.py`
- Create: `features/pipelines/local-pdf/tests/test_provenienz_storage.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_provenienz_storage.py
from pathlib import Path
import pytest
from local_pdf.provenienz.storage import (
    Node, Edge, SessionMeta,
    append_node, append_edge, read_session,
    write_meta, read_meta,
)


def test_append_then_read_round_trips_one_node(tmp_path: Path):
    session_dir = tmp_path / "sess1"
    n = Node(node_id="n1", session_id="s1", kind="chunk",
             payload={"text": "hi"}, actor="human")
    append_node(session_dir, n)
    nodes, edges = read_session(session_dir)
    assert len(nodes) == 1
    assert nodes[0].node_id == "n1"
    assert nodes[0].kind == "chunk"
    assert nodes[0].payload["text"] == "hi"
    assert edges == []


def test_append_then_read_round_trips_edge(tmp_path: Path):
    session_dir = tmp_path / "sess1"
    append_node(session_dir, Node(node_id="n1", session_id="s1",
                                   kind="chunk", payload={}, actor="human"))
    append_node(session_dir, Node(node_id="n2", session_id="s1",
                                   kind="claim", payload={}, actor="llm:vllm"))
    append_edge(session_dir, Edge(edge_id="e1", session_id="s1",
                                   from_node="n2", to_node="n1",
                                   kind="extracts-from", reason=None,
                                   actor="llm:vllm"))
    nodes, edges = read_session(session_dir)
    assert len(nodes) == 2
    assert len(edges) == 1
    assert edges[0].kind == "extracts-from"


def test_meta_round_trip(tmp_path: Path):
    session_dir = tmp_path / "sess1"
    meta = SessionMeta(session_id="s1", slug="doc-a",
                       root_chunk_id="p3-b4", status="open")
    write_meta(session_dir, meta)
    got = read_meta(session_dir)
    assert got is not None
    assert got.session_id == "s1"
    assert got.status == "open"


def test_read_session_returns_empty_when_dir_missing(tmp_path: Path):
    nodes, edges = read_session(tmp_path / "does-not-exist")
    assert nodes == []
    assert edges == []
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
.venv/bin/pytest features/pipelines/local-pdf/tests/test_provenienz_storage.py -q --override-ini="addopts="
# Expected: ImportError on local_pdf.provenienz.storage
```

- [ ] **Step 3: Implement**

```python
# src/local_pdf/provenienz/__init__.py
"""Provenienz — claim-tracing knowledge-graph engine."""
```

```python
# src/local_pdf/provenienz/storage.py
"""Append-only event-log storage for Provenienz sessions.

Each session lives at ``{LOCAL_PDF_DATA_ROOT}/{slug}/provenienz/{session_id}/``
with three files:

  events.jsonl       — one event per line: {kind: "node"|"edge", ...}
  meta.json          — session header (root chunk, status, timestamps)
  reasons.jsonl      — implicit guidance corpus (Stage 6)

Storage validates *nothing* about node/edge payloads — kinds are open
strings, payloads are arbitrary dicts. Validation happens at the
handler layer (see steps/*.py).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class Node:
    node_id: str
    session_id: str
    kind: str
    payload: dict[str, Any]
    actor: str
    created_at: str = ""  # filled by append_node


@dataclass(frozen=True)
class Edge:
    edge_id: str
    session_id: str
    from_node: str
    to_node: str
    kind: str
    reason: str | None
    actor: str
    created_at: str = ""


@dataclass(frozen=True)
class SessionMeta:
    session_id: str
    slug: str
    root_chunk_id: str
    status: Literal["open", "closed"]
    created_at: str = ""
    last_touched_at: str = ""


def _now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _events_path(d: Path) -> Path:
    return d / "events.jsonl"


def _meta_path(d: Path) -> Path:
    return d / "meta.json"


def append_node(session_dir: Path, n: Node) -> Node:
    session_dir.mkdir(parents=True, exist_ok=True)
    n2 = Node(**{**n.__dict__, "created_at": n.created_at or _now()})
    rec = {"kind": "node", **n2.__dict__}
    with _events_path(session_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return n2


def append_edge(session_dir: Path, e: Edge) -> Edge:
    session_dir.mkdir(parents=True, exist_ok=True)
    e2 = Edge(**{**e.__dict__, "created_at": e.created_at or _now()})
    rec = {"kind": "edge", **e2.__dict__}
    with _events_path(session_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return e2


def read_session(session_dir: Path) -> tuple[list[Node], list[Edge]]:
    if not _events_path(session_dir).exists():
        return [], []
    nodes: list[Node] = []
    edges: list[Edge] = []
    with _events_path(session_dir).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            kind = r.pop("kind")
            if kind == "node":
                nodes.append(Node(**r))
            elif kind == "edge":
                edges.append(Edge(**r))
    return nodes, edges


def write_meta(session_dir: Path, m: SessionMeta) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    m2 = SessionMeta(**{**m.__dict__,
                        "created_at": m.created_at or _now(),
                        "last_touched_at": _now()})
    _meta_path(session_dir).write_text(
        json.dumps(m2.__dict__, ensure_ascii=False, indent=2)
    )


def read_meta(session_dir: Path) -> SessionMeta | None:
    p = _meta_path(session_dir)
    if not p.exists():
        return None
    return SessionMeta(**json.loads(p.read_text()))
```

- [ ] **Step 4: Run tests — confirm pass**

```bash
.venv/bin/pytest features/pipelines/local-pdf/tests/test_provenienz_storage.py -q --override-ini="addopts="
# Expected: 4 passed
```

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/provenienz features/pipelines/local-pdf/tests/test_provenienz_storage.py
git commit -m "feat(provenienz): event-log storage primitives (Node, Edge, SessionMeta)"
```

---

### Task 1.2 — ULID generator + path helpers

**Model:** Haiku
**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/provenienz/storage.py`
- Modify: `features/pipelines/local-pdf/tests/test_provenienz_storage.py`

- [ ] **Step 1: Add tests for the helpers**

```python
def test_new_id_is_unique_and_lexically_sortable():
    from local_pdf.provenienz.storage import new_id
    a, b = new_id(), new_id()
    assert a != b
    # ULIDs sort by time when generated in order.
    assert b > a


def test_session_dir_layout(tmp_path):
    from local_pdf.provenienz.storage import session_dir
    d = session_dir(tmp_path, "my-slug", "01H...")
    assert d == tmp_path / "my-slug" / "provenienz" / "01H..."
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement**

```python
# Add to storage.py
import secrets
from typing import Final

_ALPHABET: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford


def new_id() -> str:
    """Time-prefixed random id, 26 chars, lex-sortable. ULID-shaped
    but we don't pull in the ulid lib for one helper."""
    from datetime import UTC, datetime
    ts = int(datetime.now(UTC).timestamp() * 1000)
    out = ""
    for _ in range(10):
        out = _ALPHABET[ts & 0x1F] + out
        ts >>= 5
    out += "".join(secrets.choice(_ALPHABET) for _ in range(16))
    return out


def session_dir(data_root: Path, slug: str, session_id: str) -> Path:
    return data_root / slug / "provenienz" / session_id
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(provenienz): id generator + session_dir helper"
```

---

### Task 1.3 — Session CRUD router

**Model:** Sonnet
**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/provenienz.py`
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/app.py`
- Create: `features/pipelines/local-pdf/tests/test_router_provenienz_sessions.py`

- [ ] **Step 1: Tests**

```python
# test_router_provenienz_sessions.py
import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    return TestClient(create_app())


def _create_doc(client, slug="doc"):
    import io
    r = client.post("/api/admin/docs",
                    headers={"X-Auth-Token": "tok"},
                    files={"file": (f"{slug}.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"),
                                    "application/pdf")})
    assert r.status_code == 201
    return r.json()["slug"]


def test_create_session_round_trips(client):
    slug = _create_doc(client)
    r = client.post("/api/admin/provenienz/sessions",
                    headers={"X-Auth-Token": "tok"},
                    json={"slug": slug, "root_chunk_id": "p1-b0"})
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["status"] == "open"
    assert s["slug"] == slug
    assert s["root_chunk_id"] == "p1-b0"
    sid = s["session_id"]

    listing = client.get("/api/admin/provenienz/sessions",
                          headers={"X-Auth-Token": "tok"}).json()
    assert any(x["session_id"] == sid for x in listing)

    detail = client.get(f"/api/admin/provenienz/sessions/{sid}",
                          headers={"X-Auth-Token": "tok"}).json()
    assert detail["meta"]["session_id"] == sid
    # Root chunk node was created.
    assert any(n["kind"] == "chunk" for n in detail["nodes"])


def test_delete_session_removes_dir(client):
    slug = _create_doc(client)
    sid = client.post("/api/admin/provenienz/sessions",
                      headers={"X-Auth-Token": "tok"},
                      json={"slug": slug, "root_chunk_id": "p1-b0"}).json()["session_id"]
    r = client.delete(f"/api/admin/provenienz/sessions/{sid}",
                      headers={"X-Auth-Token": "tok"})
    assert r.status_code == 204
    listing = client.get("/api/admin/provenienz/sessions",
                          headers={"X-Auth-Token": "tok"}).json()
    assert all(x["session_id"] != sid for x in listing)


def test_create_404_when_doc_missing(client):
    r = client.post("/api/admin/provenienz/sessions",
                    headers={"X-Auth-Token": "tok"},
                    json={"slug": "nope", "root_chunk_id": "p1-b0"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run — fails (no router)**

- [ ] **Step 3: Implement**

```python
# src/local_pdf/api/routers/admin/provenienz.py
"""Provenienz tab routes — sessions CRUD (Stage 1).

Steps + decision routes land in later stages.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from local_pdf.provenienz.storage import (
    Node, SessionMeta, append_node, new_id, read_meta, read_session,
    session_dir, write_meta,
)
from local_pdf.storage.sidecar import doc_dir, read_mineru

if TYPE_CHECKING:
    pass

router = APIRouter()


def _ms_paren_root(data_root: Path, slug: str) -> Path:
    return data_root / slug / "provenienz"


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


@router.post("/api/admin/provenienz/sessions",
             status_code=201, response_model=SessionMetaResponse)
async def create_session(body: CreateSessionRequest,
                         request: Request) -> SessionMetaResponse:
    cfg = request.app.state.config
    if not doc_dir(cfg.data_root, body.slug).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {body.slug}")

    # Seed the chunk text from the document's mineru.json so the
    # canvas can render the root node immediately.
    mineru = read_mineru(cfg.data_root, body.slug) or {"elements": []}
    el = next((e for e in mineru.get("elements", [])
               if e.get("box_id") == body.root_chunk_id), None)
    if el is None:
        raise HTTPException(status_code=404,
                            detail=f"chunk not found in {body.slug}: {body.root_chunk_id}")

    sid = new_id()
    sdir = session_dir(cfg.data_root, body.slug, sid)
    meta = SessionMeta(session_id=sid, slug=body.slug,
                       root_chunk_id=body.root_chunk_id, status="open")
    write_meta(sdir, meta)

    # Root chunk node.
    import re
    text = re.sub(r"<[^>]+>", " ", el.get("html_snippet", "")).strip()
    append_node(sdir, Node(node_id=new_id(), session_id=sid, kind="chunk",
                            payload={"box_id": body.root_chunk_id,
                                     "doc_slug": body.slug,
                                     "text": text},
                            actor="system"))
    return _meta_to_response(read_meta(sdir))


@router.get("/api/admin/provenienz/sessions")
async def list_sessions(request: Request,
                        slug: str | None = None) -> list[SessionMetaResponse]:
    cfg = request.app.state.config
    out: list[SessionMetaResponse] = []
    slugs = [slug] if slug else [
        p.name for p in cfg.data_root.iterdir() if p.is_dir()
    ]
    for s in slugs:
        root = _ms_paren_root(cfg.data_root, s)
        if not root.exists():
            continue
        for sd in sorted(root.iterdir()):
            m = read_meta(sd)
            if m is not None:
                out.append(_meta_to_response(m))
    return out


@router.get("/api/admin/provenienz/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> dict:
    cfg = request.app.state.config
    # Find the session by scanning slugs (cheap; per-doc dirs).
    for slug_dir in cfg.data_root.iterdir():
        if not slug_dir.is_dir():
            continue
        sd = slug_dir / "provenienz" / session_id
        if sd.exists():
            meta = read_meta(sd)
            nodes, edges = read_session(sd)
            return {
                "meta": _meta_to_response(meta).model_dump() if meta else None,
                "nodes": [n.__dict__ for n in nodes],
                "edges": [e.__dict__ for e in edges],
            }
    raise HTTPException(status_code=404, detail=f"session not found: {session_id}")


@router.delete("/api/admin/provenienz/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request) -> None:
    cfg = request.app.state.config
    for slug_dir in cfg.data_root.iterdir():
        if not slug_dir.is_dir():
            continue
        sd = slug_dir / "provenienz" / session_id
        if sd.exists():
            shutil.rmtree(sd)
            return
    raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
```

Wire into `app.py`:

```python
from local_pdf.api.routers.admin.provenienz import router as provenienz_router
# ...
app.include_router(provenienz_router)
```

- [ ] **Step 4: Run — pass**

```bash
.venv/bin/pytest features/pipelines/local-pdf/tests/test_router_provenienz_sessions.py -q --override-ini="addopts="
```

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(provenienz): session CRUD endpoints + root-chunk seeding"
```

---

## Stage 2 — Searcher protocol + InDocSearcher

### Task 2.1 — Searcher Protocol + SearchHit

**Model:** Haiku
**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/provenienz/searcher.py`
- Create: `features/pipelines/local-pdf/tests/test_provenienz_searcher.py`

- [ ] **Step 1: Tests for InDocSearcher**

```python
# test_provenienz_searcher.py
from pathlib import Path
import pytest
from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
from local_pdf.provenienz.searcher import InDocSearcher, SearchHit
from local_pdf.storage.sidecar import write_mineru, write_segments


def _seed(tmp_path: Path, slug: str = "doc"):
    boxes = [
        SegmentBox(box_id="p1-b0", page=1, bbox=(0,0,100,50),
                    kind=BoxKind.paragraph, confidence=1.0, reading_order=0),
        SegmentBox(box_id="p2-b0", page=2, bbox=(0,0,100,50),
                    kind=BoxKind.paragraph, confidence=1.0, reading_order=0),
    ]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(tmp_path, slug, {"elements": [
        {"box_id": "p1-b0", "html_snippet": "<p>Gesamtwärmeleistung 5.6 kW</p>"},
        {"box_id": "p2-b0", "html_snippet": "<p>Wetterbericht Berlin</p>"},
    ], "diagnostics": []})


def test_in_doc_searcher_returns_relevant_hits(tmp_path: Path):
    _seed(tmp_path)
    searcher = InDocSearcher(data_root=tmp_path, slug="doc")
    hits = searcher.search("Wärmeleistung kW", top_k=5)
    assert hits[0].box_id == "p1-b0"
    assert hits[0].score > 0
    assert hits[0].searcher == "in_doc"


def test_in_doc_searcher_excludes_self_when_provided(tmp_path: Path):
    _seed(tmp_path)
    searcher = InDocSearcher(data_root=tmp_path, slug="doc",
                              exclude_box_ids=("p1-b0",))
    hits = searcher.search("Wärmeleistung", top_k=5)
    assert all(h.box_id != "p1-b0" for h in hits)


def test_in_doc_searcher_returns_empty_for_empty_query(tmp_path: Path):
    _seed(tmp_path)
    searcher = InDocSearcher(data_root=tmp_path, slug="doc")
    assert searcher.search("", top_k=5) == []
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement**

```python
# src/local_pdf/provenienz/searcher.py
"""Searcher Protocol + InDocSearcher — v1 of the provenance corpus.

Cross-doc and Azure variants land in later iterations as drop-in
replacements (same Protocol, new instance).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from local_pdf.comparison.bm25 import bm25_scores
from local_pdf.storage.sidecar import read_mineru


@dataclass(frozen=True)
class SearchHit:
    box_id: str
    text: str
    score: float
    doc_slug: str
    searcher: str   # name of the producing Searcher


class Searcher(Protocol):
    name: str
    def search(self, query: str, *, top_k: int) -> list[SearchHit]: ...


_TAG_RE = re.compile(r"<[^>]+>")


def _strip(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html or "")).strip()


@dataclass(frozen=True)
class InDocSearcher:
    data_root: Path
    slug: str
    exclude_box_ids: tuple[str, ...] = field(default_factory=tuple)
    name: str = "in_doc"

    def search(self, query: str, *, top_k: int) -> list[SearchHit]:
        if not query or not query.strip():
            return []
        m = read_mineru(self.data_root, self.slug)
        if m is None:
            return []
        elements = [e for e in m.get("elements", [])
                    if e.get("box_id") not in self.exclude_box_ids]
        if not elements:
            return []
        texts = [_strip(e.get("html_snippet", "")) for e in elements]
        scores = bm25_scores(query, texts)
        ranked = sorted(zip(elements, texts, scores, strict=True),
                        key=lambda t: t[2], reverse=True)
        out: list[SearchHit] = []
        for el, text, sc in ranked[:top_k]:
            if sc <= 0:
                continue
            out.append(SearchHit(
                box_id=el["box_id"], text=text, score=float(sc),
                doc_slug=self.slug, searcher=self.name,
            ))
        return out
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(provenienz): Searcher Protocol + InDocSearcher (BM25 in-doc)"
```

---

## Stage 3 — LLM-step pattern + first step (extract-claims)

### Task 3.1 — ActionProposal builder + provider resolver

**Model:** Sonnet
**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/provenienz/llm.py`
- Create: `features/pipelines/local-pdf/tests/test_provenienz_llm.py`

- [ ] **Step 1: Tests**

```python
# test_provenienz_llm.py
from local_pdf.provenienz.llm import (
    ActionProposalPayload, ActionOption, build_proposal_node,
)


def test_build_proposal_node_emits_action_proposal_kind():
    payload = ActionProposalPayload(
        step_kind="search",
        anchor_node_id="n1",
        recommended=ActionOption(label="bm25 search", args={"q": "x"}),
        alternatives=[],
        reasoning="...",
        guidance_consulted=[],
    )
    n = build_proposal_node(session_id="s1", actor="llm:vllm", payload=payload)
    assert n.kind == "action_proposal"
    assert n.payload["step_kind"] == "search"
    assert n.payload["recommended"]["label"] == "bm25 search"
    assert n.actor == "llm:vllm"
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement**

```python
# src/local_pdf/provenienz/llm.py
"""ActionProposal data shapes + provider resolution.

Every LLM-decided step in the Provenienz flow emits an
``action_proposal`` node — never a final action. A separate /decide
route consumes it and runs the accepted option.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from local_pdf.provenienz.storage import Node, new_id


@dataclass(frozen=True)
class ActionOption:
    label: str
    args: dict[str, Any]


@dataclass(frozen=True)
class GuidanceRef:
    kind: Literal["reason", "approach"]
    id: str
    summary: str


@dataclass(frozen=True)
class ActionProposalPayload:
    step_kind: str
    anchor_node_id: str
    recommended: ActionOption
    alternatives: list[ActionOption] = field(default_factory=list)
    reasoning: str = ""
    guidance_consulted: list[GuidanceRef] = field(default_factory=list)


def build_proposal_node(*, session_id: str, actor: str,
                        payload: ActionProposalPayload) -> Node:
    return Node(
        node_id=new_id(),
        session_id=session_id,
        kind="action_proposal",
        payload={
            "step_kind": payload.step_kind,
            "anchor_node_id": payload.anchor_node_id,
            "recommended": asdict(payload.recommended),
            "alternatives": [asdict(a) for a in payload.alternatives],
            "reasoning": payload.reasoning,
            "guidance_consulted": [asdict(g) for g in payload.guidance_consulted],
        },
        actor=actor,
    )


def resolve_provider(provider: str | None) -> str:
    """Map a 'provider' query/body field to a concrete actor string.

    None / empty → default (env: PROVENIENZ_DEFAULT_PROVIDER, fallback 'vllm').
    """
    p = (provider or os.environ.get("PROVENIENZ_DEFAULT_PROVIDER", "vllm")).strip()
    return f"llm:{p}"
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(provenienz): ActionProposal data shapes + provider resolver"
```

---

### Task 3.2 — `/extract-claims` step route (deterministic stub)

**Model:** Sonnet
**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/provenienz.py`
- Create: `features/pipelines/local-pdf/tests/test_router_provenienz_extract.py`

For v1 the LLM call is a small helper that we can stub in tests. Real LLM wiring happens in Task 5.5.

- [ ] **Step 1: Tests**

```python
# test_router_provenienz_extract.py
import pytest
from local_pdf.api.routers.admin import provenienz as router_mod


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    # Stub the LLM helper.
    monkeypatch.setattr(router_mod, "_llm_extract_claims",
                        lambda chunk_text, provider: [
                            "Gesamtwärmeleistung beträgt 5.6 kW",
                            "Die Baugruppe ist X",
                        ])
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    return TestClient(create_app())


def _bootstrap(client):
    """Create a doc + a session with one chunk, return (slug, session_id, chunk_node_id)."""
    import io
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"},
                files={"file": ("d.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"),
                                "application/pdf")})
    # Need a chunk to root the session against.
    from local_pdf.storage.sidecar import write_mineru
    cfg = client.app.state.config
    write_mineru(cfg.data_root, "d", {"elements": [
        {"box_id": "p1-b0", "html_snippet": "<p>Die Gesamtwärmeleistung beträgt 5.6 kW.</p>"},
    ], "diagnostics": []})

    sid = client.post("/api/admin/provenienz/sessions",
                       headers={"X-Auth-Token": "tok"},
                       json={"slug": "d", "root_chunk_id": "p1-b0"}).json()["session_id"]
    detail = client.get(f"/api/admin/provenienz/sessions/{sid}",
                          headers={"X-Auth-Token": "tok"}).json()
    chunk_node = next(n for n in detail["nodes"] if n["kind"] == "chunk")
    return "d", sid, chunk_node["node_id"]


def test_extract_claims_emits_action_proposal_with_alternatives(client):
    _slug, sid, chunk_node_id = _bootstrap(client)
    r = client.post(f"/api/admin/provenienz/sessions/{sid}/extract-claims",
                    headers={"X-Auth-Token": "tok"},
                    json={"chunk_node_id": chunk_node_id})
    assert r.status_code == 201, r.text
    proposal = r.json()
    assert proposal["kind"] == "action_proposal"
    assert proposal["payload"]["step_kind"] == "extract_claims"
    assert proposal["payload"]["anchor_node_id"] == chunk_node_id
    # Recommended carries the list of claim strings; alternatives is a single
    # "skip" option for v1.
    assert "claims" in proposal["payload"]["recommended"]["args"]
    assert proposal["payload"]["recommended"]["args"]["claims"] == [
        "Gesamtwärmeleistung beträgt 5.6 kW",
        "Die Baugruppe ist X",
    ]
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement**

Add to `provenienz.py`:

```python
from local_pdf.provenienz.llm import (
    ActionOption, ActionProposalPayload, build_proposal_node, resolve_provider,
)


def _llm_extract_claims(chunk_text: str, provider: str) -> list[str]:
    """Real LLM call — wired in Task 5.5. For now, simple heuristic so
    the route is testable without spinning up vLLM."""
    sentences = [s.strip() for s in chunk_text.split(".") if len(s.strip()) > 8]
    return sentences[:5]


class ExtractClaimsRequest(BaseModel):
    chunk_node_id: str
    provider: str | None = None


@router.post("/api/admin/provenienz/sessions/{session_id}/extract-claims",
             status_code=201)
async def extract_claims(session_id: str,
                         body: ExtractClaimsRequest,
                         request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail="session not found")
    nodes, _ = read_session(sd)
    chunk = next((n for n in nodes if n.node_id == body.chunk_node_id), None)
    if chunk is None or chunk.kind != "chunk":
        raise HTTPException(status_code=404, detail="chunk node not found")

    actor = resolve_provider(body.provider)
    claims = _llm_extract_claims(chunk.payload.get("text", ""), body.provider or "vllm")

    payload = ActionProposalPayload(
        step_kind="extract_claims",
        anchor_node_id=body.chunk_node_id,
        recommended=ActionOption(label=f"Akzeptiere {len(claims)} Aussagen",
                                  args={"claims": claims}),
        alternatives=[ActionOption(label="Überspringen — keine prüfbaren Aussagen",
                                     args={"claims": []})],
        reasoning="Heuristik v0: Sätze ≥ 8 Zeichen aus dem Chunk-Text.",
        guidance_consulted=[],
    )
    node = build_proposal_node(session_id=session_id, actor=actor, payload=payload)
    append_node(sd, node)
    return node.__dict__


def _find_session_dir(data_root: Path, session_id: str) -> Path | None:
    for slug_dir in data_root.iterdir():
        if not slug_dir.is_dir():
            continue
        sd = slug_dir / "provenienz" / session_id
        if sd.exists():
            return sd
    return None
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(provenienz): /extract-claims step → emits action_proposal"
```

---

## Stage 4 — Decision executor

### Task 4.1 — `/decide` route + claim-spawn for `extract_claims`

**Model:** Sonnet
**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/provenienz.py`
- Create: `features/pipelines/local-pdf/tests/test_router_provenienz_decide.py`

- [ ] **Step 1: Tests**

```python
# test_router_provenienz_decide.py — full happy-path through the
# extract → decide → claim-spawn loop.

# (use the same fixtures as test_router_provenienz_extract.py)

def test_decide_recommended_spawns_claim_nodes(client):
    _slug, sid, chunk_node_id = _bootstrap(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_node_id}).json()

    r = client.post(f"/api/admin/provenienz/sessions/{sid}/decide",
                    headers={"X-Auth-Token": "tok"},
                    json={"proposal_node_id": proposal["node_id"],
                          "accepted": "recommended"})
    assert r.status_code == 201, r.text
    spawned = r.json()
    # Two claims expected per the stub.
    assert len(spawned["spawned_nodes"]) == 2
    assert all(n["kind"] == "claim" for n in spawned["spawned_nodes"])
    # Edges: claim → chunk (extracts-from), decision → proposal (decided-by),
    # decision → claim (triggers).
    edge_kinds = {e["kind"] for e in spawned["spawned_edges"]}
    assert "extracts-from" in edge_kinds
    assert "decided-by" in edge_kinds
    assert "triggers" in edge_kinds


def test_decide_override_uses_freeform_text(client):
    _slug, sid, chunk_node_id = _bootstrap(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_node_id}).json()

    r = client.post(f"/api/admin/provenienz/sessions/{sid}/decide",
                    headers={"X-Auth-Token": "tok"},
                    json={"proposal_node_id": proposal["node_id"],
                          "accepted": "override",
                          "override": "Eigene Aussage manuell",
                          "reason": "der Stub hat eine wichtige Aussage übersehen"})
    assert r.status_code == 201
    spawned = r.json()
    claims = [n for n in spawned["spawned_nodes"] if n["kind"] == "claim"]
    assert len(claims) == 1
    assert claims[0]["payload"]["text"] == "Eigene Aussage manuell"
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement**

Add to `provenienz.py`:

```python
from local_pdf.provenienz.storage import Edge, append_edge


class DecideRequest(BaseModel):
    proposal_node_id: str
    accepted: Literal["recommended", "alt", "override"]
    alt_index: int | None = None
    reason: str | None = None
    override: str | None = None


def _resolve_claims(payload: dict, body: DecideRequest) -> list[str]:
    if body.accepted == "recommended":
        return list(payload["recommended"]["args"].get("claims", []))
    if body.accepted == "alt":
        idx = body.alt_index or 0
        return list(payload["alternatives"][idx]["args"].get("claims", []))
    if body.accepted == "override":
        if not body.override:
            raise HTTPException(status_code=400,
                                detail="override requires 'override' text")
        return [body.override]
    raise HTTPException(status_code=400, detail=f"unknown accepted: {body.accepted}")


@router.post("/api/admin/provenienz/sessions/{session_id}/decide",
             status_code=201)
async def decide(session_id: str, body: DecideRequest,
                 request: Request) -> dict:
    cfg = request.app.state.config
    sd = _find_session_dir(cfg.data_root, session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail="session not found")
    nodes, _ = read_session(sd)
    proposal = next((n for n in nodes if n.node_id == body.proposal_node_id), None)
    if proposal is None or proposal.kind != "action_proposal":
        raise HTTPException(status_code=404, detail="action_proposal not found")

    # 1. Append the decision node.
    decision = Node(
        node_id=new_id(), session_id=session_id, kind="decision",
        payload={
            "accepted": body.accepted, "alt_index": body.alt_index,
            "reason": body.reason, "override": body.override,
        },
        actor="human",
    )
    append_node(sd, decision)
    append_edge(sd, Edge(edge_id=new_id(), session_id=session_id,
                          from_node=decision.node_id, to_node=proposal.node_id,
                          kind="decided-by", reason=None, actor="human"))

    # 2. Dispatch on step_kind.
    step_kind = proposal.payload["step_kind"]
    if step_kind == "extract_claims":
        anchor_chunk = proposal.payload["anchor_node_id"]
        claim_texts = _resolve_claims(proposal.payload, body)
        spawned_nodes: list[Node] = []
        spawned_edges: list[Edge] = []
        for ct in claim_texts:
            claim = Node(node_id=new_id(), session_id=session_id, kind="claim",
                          payload={"text": ct, "source_node_id": anchor_chunk},
                          actor=("human" if body.accepted == "override" else proposal.actor))
            append_node(sd, claim)
            spawned_nodes.append(claim)
            e1 = Edge(edge_id=new_id(), session_id=session_id,
                       from_node=claim.node_id, to_node=anchor_chunk,
                       kind="extracts-from", reason=None, actor=claim.actor)
            append_edge(sd, e1)
            spawned_edges.append(e1)
            e2 = Edge(edge_id=new_id(), session_id=session_id,
                       from_node=decision.node_id, to_node=claim.node_id,
                       kind="triggers", reason=None, actor="human")
            append_edge(sd, e2)
            spawned_edges.append(e2)
        return {
            "decision_node": decision.__dict__,
            "spawned_nodes": [n.__dict__ for n in spawned_nodes],
            "spawned_edges": [e.__dict__ for e in spawned_edges],
        }
    raise HTTPException(status_code=501, detail=f"step_kind not yet handled: {step_kind}")
```

- [ ] **Step 4: Run — pass**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(provenienz): /decide route + extract_claims dispatch (claim spawn)"
```

---

## Stage 5 — Remaining steps + LLM wiring

### Task 5.1 — `/formulate-task` step route
### Task 5.2 — `/search` step route (delegates to InDocSearcher)
### Task 5.3 — `/evaluate` step route
### Task 5.4 — `/propose-stop` step route
### Task 5.5 — Wire real LLM (vLLM via `local_pdf.llm.get_llm_client`)

Each follows the same TDD shape as Task 3.2 + 4.1: stub → route → decide-dispatch → tests. **Each lands in its own commit.** Per task:

**Files:** modify `provenienz.py`, add corresponding test file.
**Pattern:** route emits `action_proposal`; `/decide` learns the new `step_kind` and spawns the appropriate child kind (`task` for formulate, `search_result[]` for search, `evaluation` for evaluate, no spawn — flips session.status — for stop).

I'll detail these inline once Stage 4 lands; the contracts are identical so the bodies write themselves.

---

## Stage 6 — Reasons + approach library

### Task 6.1 — `reasons.jsonl` write on every override
### Task 6.2 — Reason-corpus loader → injects last-N relevant reasons into prompts
### Task 6.3 — `approaches.jsonl` CRUD + per-session pin

Identical TDD shape; defer detailed bodies until Stage 5 settles the LLM prompt format.

---

## Stage 7 — Frontend tab + sessions list

### Task 7.1 — Add `Provenienz` to DocStepTabs + register route

**Model:** Haiku
**Files:**
- Modify: `frontend/src/admin/components/DocStepTabs.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/admin/routes/Provenienz.tsx` (skeleton only)

- [ ] **Step 1: Skeleton route**

```tsx
// frontend/src/admin/routes/Provenienz.tsx
import { useParams } from "react-router-dom";
import { useAuth } from "../../auth/useAuth";
import { DocStepTabs } from "../components/DocStepTabs";

export function Provenienz(): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const { token } = useAuth();
  if (!token) return <div className="p-6">Not authorised.</div>;

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-4 py-2 bg-navy-800 text-white border-b border-navy-700">
        <DocStepTabs slug={slug} />
      </div>
      <div className="flex-1 flex items-center justify-center text-slate-500 italic">
        Provenienz — Skeleton (Sessions UI lands in Task 7.2)
      </div>
    </div>
  );
}
```

DocStepTabs entry:

```tsx
{ key: "provenienz", label: "Provenienz", icon: GitMerge,
  href: (slug: string) => `/admin/doc/${slug}/provenienz` },
```

App.tsx route:

```tsx
<Route path="doc/:slug/provenienz" element={<Provenienz />} />
```

- [ ] **Steps 2-5:** tsc clean, smoke-render in dev server, commit `feat(provenienz): add Provenienz tab skeleton`.

---

### Task 7.2 — Sessions list pane + create-session flow
### Task 7.3 — `useProvenienzSession` hook (GET / POST / DELETE)

Same TDD shape as the Comparison tab hooks. Reuse the existing `apiBase()` + `fetchOk` pattern.

---

## Stage 8 — react-flow canvas + node renderers

### Task 8.1 — Install `reactflow` + `dagre` (frontend deps)
### Task 8.2 — Canvas wrapper + `nodeTypes` registry
### Task 8.3 — `ChunkNode`, `ClaimNode`, `TaskNode` renderers
### Task 8.4 — `SearchResultNode`, `ActionProposalNode`, `DecisionNode` renderers
### Task 8.5 — Auto-layout via `dagre` on session load

Each renderer is a small Tailwind-styled component with one prop (`data: NodePayload`). They live under `frontend/src/admin/provenienz/nodes/`.

---

## Stage 9 — Side panel + step actions

### Task 9.1 — Selection state + side-panel registry
### Task 9.2 — Per-kind side panel components
### Task 9.3 — Action buttons trigger backend step routes; results refresh canvas

Side panel mirrors the LlmServerPanel + box-metadata pattern from Synthesise.

---

## Stage 10 — End-to-end smoke + cleanup

### Task 10.1 — Manual e2e checklist (markdown)

Steps:

1. Click `Provenienz`, click `+ Neue Sitzung`, pick a chunk.
2. Canvas renders chunk node.
3. Click chunk → side panel → `Aussagen extrahieren` → LLM proposes claims.
4. Click proposal → `Empfehlung übernehmen`.
5. Two claim nodes appear connected to the chunk.
6. Click a claim → `Aufgabe formulieren` → `Suchen` → `Bewerten` → `Stopp vorschlagen`.
7. Reload the page → graph re-renders identically.

### Task 10.2 — Branch-merge / PR

Open a draft PR from `feat/provenienzanalyse` to `main` after Stage 9 lands.

---

## Self-review checklist

- ✅ Each task has one focused goal (≤5 minutes per step)
- ✅ Every step shows the actual code, not "implement X"
- ✅ Tests precede implementation (TDD)
- ✅ Commits are atomic and named
- ✅ No placeholders ("TODO", "fill in details")
- ✅ Inter-task contracts (Node, Edge, ActionProposal*, /decide body) are stated upfront
- ✅ New deps are flagged at Task 8.1 (reactflow + dagre)
- ✅ Stages 5 + 6 leave bodies for after Stage 4 confirms the dispatch shape — risk-managed: don't mass-write code until the contract is exercised once

## Stage-by-stage decision points

| After stage | Decide |
|---|---|
| Stage 1 | Are session-CRUD response shapes (meta, nodes, edges JSON) what the frontend wants? Adjust before Stage 2. |
| Stage 2 | Is BM25 useful enough for in-doc search? If not, swap to embedding-based before Stage 3. |
| Stage 4 | Does the action_proposal → decide → child-spawn flow feel right end-to-end? Adjust shape before mass-writing 5.1-5.4. |
| Stage 5.5 | Real LLM responses: do they fit the ActionProposal shape, or do we need to broaden it? |
| Stage 6 | After 3-5 sessions: is implicit reason corpus enough, or does the explicit approach library see real use? |
| Stage 8.5 | Is dagre's auto-layout readable for >10-node graphs, or do we need user-draggable layout persistence? |

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-05-provenienzanalyse.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review

**Which approach?**
