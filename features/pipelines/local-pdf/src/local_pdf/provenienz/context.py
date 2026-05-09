"""Forward-flowing investigation context.

Each Node in a Provenienz session carries a ``context`` field on its
payload that summarises what the upstream investigation already
visited or focused on. Steps that spawn new nodes copy the parent's
context, then merge their own additions:

  - create_session (root chunk) seeds the context.
  - extract_claims, formulate_task, search-decide, evaluate-decide
    inherit unchanged.
  - promote_search_result adds the new chunk's ``box_id`` to
    ``visited_box_ids`` and increments ``recursion_depth``.
  - cross-doc-search adds the foreign slug to ``visited_doc_slugs``.

Tools read ``context`` from their anchor node:
  - InDocSearcher uses ``visited_box_ids`` for ``exclude_box_ids``.
  - CrossDocSearcher could similarly skip ``visited_doc_slugs``.
  - Right-pane panels render the structured chain for transparency.

The context is a plain ``dict[str, Any]`` (no Pydantic model) to stay
inline with the existing payload convention. The TypedDict here is
purely for type hints; runtime stores native Python types so JSONL
round-trip is identity.
"""

from __future__ import annotations

from typing import Any, TypedDict


class NodeContext(TypedDict, total=False):
    """Forward-flowing investigation breadcrumbs.

    All fields are optional at the type level — older nodes (or
    nodes spawned by code paths that haven't been migrated yet)
    return :func:`empty_context` from :func:`get_context`.
    """

    # box_ids of every chunk in the ancestry — what the searcher
    # should skip so we don't re-mine sources we've already mined.
    visited_box_ids: list[str]
    # doc_slugs the investigation has already scoped into — useful
    # when the cross-doc-search tool eventually wants to skip them.
    visited_doc_slugs: list[str]
    # Same value as the legacy chunk.payload.recursion_depth field.
    # Kept here too so future generic UI doesn't have to special-case
    # chunks. Lifts naturally from parent context + 1 on promote.
    recursion_depth: int
    # Ordered breadcrumb trail, one entry per spawn step. Lets the
    # right-pane render a "how we got here" section without having
    # to walk the edge graph.
    #   {"node_id": str, "kind": str, "label": str}
    origin_chain: list[dict[str, str]]


def empty_context() -> NodeContext:
    """Fresh context for a node with no upstream investigation."""
    return {
        "visited_box_ids": [],
        "visited_doc_slugs": [],
        "recursion_depth": 0,
        "origin_chain": [],
    }


def get_context(payload: dict[str, Any]) -> NodeContext:
    """Read the ``context`` slot off a Node's payload, normalised.

    Missing/None values become empty lists / 0 so callers don't have
    to defensively check each field. Coerces back-compat: a legacy
    ``payload.recursion_depth`` (without nested context) lifts into
    the returned ``recursion_depth`` so search-style consumers see a
    consistent surface.
    """
    raw_obj = payload.get("context") or {}
    raw: dict[str, Any] = raw_obj if isinstance(raw_obj, dict) else {}
    legacy_depth = int(payload.get("recursion_depth") or 0)
    nested_depth = int(raw.get("recursion_depth") or 0)
    visited_box_ids_raw = raw.get("visited_box_ids") or []
    visited_doc_slugs_raw = raw.get("visited_doc_slugs") or []
    origin_chain_raw = raw.get("origin_chain") or []
    return {
        "visited_box_ids": [str(b) for b in visited_box_ids_raw if isinstance(b, str) and b],
        "visited_doc_slugs": [str(s) for s in visited_doc_slugs_raw if isinstance(s, str) and s],
        "recursion_depth": max(legacy_depth, nested_depth),
        "origin_chain": [
            {
                "node_id": str(e.get("node_id", "")),
                "kind": str(e.get("kind", "")),
                "label": str(e.get("label", ""))[:160],
            }
            for e in origin_chain_raw
            if isinstance(e, dict)
        ],
    }


def merge_contexts(parent: NodeContext, additions: NodeContext) -> NodeContext:
    """Combine parent's context with this-step's additions.

    Semantics:
      - List fields ``visited_box_ids`` / ``visited_doc_slugs`` are
        deduplicated unions — first occurrence wins, order preserved
        from parent → additions.
      - ``recursion_depth`` takes the max (additions win when this
        step is a deepening, e.g. promote_search_result).
      - ``origin_chain`` is appended (parent first, then additions),
        preserving the temporal order of the trail.
    """

    def _dedup_concat(a: list[str], b: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for v in [*a, *b]:
            if v and v not in seen:
                out.append(v)
                seen.add(v)
        return out

    return {
        "visited_box_ids": _dedup_concat(
            parent.get("visited_box_ids", []) or [],
            additions.get("visited_box_ids", []) or [],
        ),
        "visited_doc_slugs": _dedup_concat(
            parent.get("visited_doc_slugs", []) or [],
            additions.get("visited_doc_slugs", []) or [],
        ),
        "recursion_depth": max(
            parent.get("recursion_depth", 0) or 0,
            additions.get("recursion_depth", 0) or 0,
        ),
        "origin_chain": [
            *(parent.get("origin_chain", []) or []),
            *(additions.get("origin_chain", []) or []),
        ],
    }


def origin_entry(node_id: str, kind: str, label: str) -> dict[str, str]:
    """Tiny helper for building one ``origin_chain`` entry — keeps
    the spawn sites readable and the truncation rule centralised.
    """
    return {
        "node_id": node_id,
        "kind": kind,
        "label": label[:160],
    }
