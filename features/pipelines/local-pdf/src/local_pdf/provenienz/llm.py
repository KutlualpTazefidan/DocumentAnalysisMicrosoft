"""ActionProposal data shapes + provider resolution.

Every LLM-decided step in the Provenienz flow emits an
``action_proposal`` node — never a final action. A separate /decide
route (Stage 4) consumes it and runs the accepted option.

The dataclasses here intentionally hold simple/serialisable shapes
so build_proposal_node() can dump them straight into Node.payload
(a dict[str, Any]) without bespoke encoders.
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


def build_proposal_node(*, session_id: str, actor: str, payload: ActionProposalPayload) -> Node:
    """Materialise an ``action_proposal`` Node from a typed payload.

    Node.created_at stays empty here — the storage layer fills it
    when the node lands via append_node.
    """
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

    Resolution order:
      1. Argument (when truthy)
      2. PROVENIENZ_DEFAULT_PROVIDER env var
      3. 'vllm'
    """
    chosen = (provider or os.environ.get("PROVENIENZ_DEFAULT_PROVIDER") or "vllm").strip()
    return f"llm:{chosen}"
