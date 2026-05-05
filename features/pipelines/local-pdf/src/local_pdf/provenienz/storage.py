"""Append-only event-log storage for Provenienz sessions.

Each session lives at ``{LOCAL_PDF_DATA_ROOT}/{slug}/provenienz/{session_id}/``
with three files:

  events.jsonl       — one event per line: {_event: "node"|"edge", ...}
  meta.json          — session header (root chunk, status, timestamps)
  reasons.jsonl      — implicit guidance corpus (filled in Stage 6)

Storage validates *nothing* about node/edge payloads — kinds are open
strings, payloads are arbitrary dicts. Validation happens at the
handler layer (see future steps/*.py).
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import Any, Final, Literal


@dataclass(frozen=True)
class Node:
    node_id: str
    session_id: str
    kind: str
    payload: dict[str, Any]
    actor: str
    created_at: str = ""  # filled by append_node when empty


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
    pinned_approach_ids: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _events_path(d: Path) -> Path:
    return d / "events.jsonl"


def _meta_path(d: Path) -> Path:
    return d / "meta.json"


def append_node(session_dir: Path, n: Node) -> Node:
    session_dir.mkdir(parents=True, exist_ok=True)
    n2 = Node(**{**n.__dict__, "created_at": n.created_at or _now()})
    rec = {"_event": "node", **n2.__dict__}
    with _events_path(session_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return n2


def append_edge(session_dir: Path, e: Edge) -> Edge:
    session_dir.mkdir(parents=True, exist_ok=True)
    e2 = Edge(**{**e.__dict__, "created_at": e.created_at or _now()})
    rec = {"_event": "edge", **e2.__dict__}
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
            event = r.pop("_event")
            if event == "node":
                nodes.append(Node(**r))
            elif event == "edge":
                edges.append(Edge(**r))
    return nodes, edges


def write_meta(session_dir: Path, m: SessionMeta) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    m2 = SessionMeta(
        **{**m.__dict__, "created_at": m.created_at or _now(), "last_touched_at": _now()}
    )
    _meta_path(session_dir).write_text(json.dumps(m2.__dict__, ensure_ascii=False, indent=2))


def read_meta(session_dir: Path) -> SessionMeta | None:
    p = _meta_path(session_dir)
    if not p.exists():
        return None
    raw = json.loads(p.read_text())
    raw.setdefault("pinned_approach_ids", [])
    return SessionMeta(**raw)


_ALPHABET: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32


def new_id() -> str:
    """Time-prefixed random id, 26 chars, lex-sortable.

    ULID-shaped (10 chars timestamp + 16 chars randomness, Crockford
    base32). Hand-rolled so we don't pull in the ulid lib for one
    helper. Two ids generated in the same millisecond may compare
    equal on the time prefix; the random tail tiebreaks.
    """
    ts = int(datetime.now(UTC).timestamp() * 1000)
    out = ""
    for _ in range(10):
        out = _ALPHABET[ts & 0x1F] + out
        ts >>= 5
    out += "".join(secrets.choice(_ALPHABET) for _ in range(16))
    return out


def session_dir(data_root: Path, slug: str, session_id: str) -> Path:
    """Filesystem path for one session's event log + meta.

    Mirrors the convention {LOCAL_PDF_DATA_ROOT}/{slug}/provenienz/{session_id}/
    used by Stage 1.3's session router.
    """
    return data_root / slug / "provenienz" / session_id
