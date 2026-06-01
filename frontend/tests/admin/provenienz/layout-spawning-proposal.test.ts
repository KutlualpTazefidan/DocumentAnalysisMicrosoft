import { describe, expect, it } from "vitest";

import type {
  ProvEdge,
  ProvNode,
} from "../../../src/admin/hooks/useProvenienz";
import { buildViewGraph } from "../../../src/admin/provenienz/layout";

function node(
  id: string,
  kind: string,
  payload: Record<string, unknown> = {},
): ProvNode {
  return {
    node_id: id,
    session_id: "s1",
    kind,
    payload,
    actor: "human",
    created_at: id,
  };
}

function edge(
  id: string,
  from: string,
  to: string,
  kind: string,
): ProvEdge {
  return {
    edge_id: id,
    session_id: "s1",
    from_node: from,
    to_node: to,
    kind,
    reason: null,
    actor: "human",
    created_at: id,
  };
}

/**
 * Setup: a typical promote_search_result chain in the audit log.
 *
 *   chunk → claim → task → search_result(sr1)
 *                                     ↑ promoted_from
 *   action_proposal(promote)  ── decided-by ──> ...
 *               │
 *           decision ── triggers ──> new_chunk
 *
 * The new_chunk's `proposalSpawningNode` resolves to the
 * promote_search_result action_proposal because the decision
 * node has both a `decided-by` edge to the proposal and a
 * `triggers` edge to the chunk.
 */
function promoteChainNodes(opts: {
  trail?: string;
  proposalTrail?: string;
}): { nodes: ProvNode[]; edges: ProvEdge[] } {
  const nodes: ProvNode[] = [
    node("c1", "chunk", { text: "ch" }),
    node("cl1", "claim", { text: "claim" }),
    node("t1", "task", { query: "q", focus_claim_id: "cl1" }),
    node("sr1", "search_result", { text: "hit", task_node_id: "t1" }),
    node("ap_promote", "action_proposal", {
      step_kind: "promote_search_result",
      anchor_node_id: "sr1",
      ...(opts.proposalTrail
        ? { triggered_from_node_id: opts.proposalTrail }
        : {}),
    }),
    node("dec1", "decision", { proposal_node_id: "ap_promote" }),
    node("c2", "chunk", {
      text: "promoted",
      promoted_from: "sr1",
      ...(opts.trail ? { triggered_from_node_id: opts.trail } : {}),
    }),
  ];
  const edges: ProvEdge[] = [
    edge("e_promoted", "c2", "sr1", "promoted-from"),
    edge("e_decided", "dec1", "ap_promote", "decided-by"),
    edge("e_triggers", "dec1", "c2", "triggers"),
  ];
  return { nodes, edges };
}

describe("Promoted chunk trunk parent priority", () => {
  it("attaches to the spawning action_proposal when no trail is set", () => {
    // Bag-panel "Vertiefen" path: no triggered_from on chunk or proposal.
    // The chunk should NOT fall back to the bag — its real parent is the
    // promote_search_result action_proposal that spawned it.
    const { nodes, edges } = promoteChainNodes({});
    const { viewEdges } = buildViewGraph(nodes, edges);
    const trunk = viewEdges.filter(
      (e) => e.target === "view:c2" && e.id === "e:promoted:c2",
    );
    expect(trunk).toHaveLength(1);
    expect(trunk[0].source).toBe("view:ap_promote");
    expect(trunk[0].kind).toBe("spawns");
    // No competing edge from the bag to the chunk.
    const bagEdges = viewEdges.filter(
      (e) =>
        e.target === "view:c2" &&
        (e.kind === "promoted-from" || e.source.startsWith("view:bag:")),
    );
    expect(bagEdges).toHaveLength(0);
  });

  it("attaches to the trail parent when chunk inherits a Bewertungs-Trail", () => {
    // Plan-accept-from-Bewertung path: both proposal and chunk carry
    // triggered_from = ev1. Trail wins over proposalSpawningNode so the
    // visual stays a continuous yellow strand from the evaluation.
    const trailNodes: ProvNode[] = [
      node("ev1", "evaluation", {
        verdict: "supports",
        proposal_node_id: "x",
      }),
    ];
    const { nodes, edges } = promoteChainNodes({
      trail: "ev1",
      proposalTrail: "ev1",
    });
    const { viewEdges } = buildViewGraph([...trailNodes, ...nodes], edges);
    const trunk = viewEdges.filter(
      (e) => e.target === "view:c2" && e.id === "e:promoted:c2",
    );
    expect(trunk).toHaveLength(1);
    // Trail-parent for the chunk resolves to the spawning proposal in
    // the same trail (per the trail-pre-pass logic).
    expect(trunk[0].source).toBe("view:ap_promote");
    expect(trunk[0].kind).toBe("trail-trunk");
  });

  it("falls back to the bag when no spawning proposal exists (legacy data)", () => {
    // Older sessions promoted via the dedicated /promote-search-result
    // endpoint without a wrapping action_proposal/decision. Only the
    // structural `promoted-from` payload + edge exist. The bag must
    // still be the visible parent so the audit chain reads end-to-end.
    const nodes: ProvNode[] = [
      node("c1", "chunk", { text: "ch" }),
      node("cl1", "claim", { text: "claim" }),
      node("t1", "task", { query: "q", focus_claim_id: "cl1" }),
      // search_result has its own bag (built from a search action_proposal
      // upstream — needed so bagViewIdByResultId resolves).
      node("ap_search", "action_proposal", {
        step_kind: "search",
        anchor_node_id: "t1",
      }),
      node("dec_search", "decision", { proposal_node_id: "ap_search" }),
      node("sr1", "search_result", { text: "hit", task_node_id: "t1" }),
      node("c2", "chunk", { text: "promoted", promoted_from: "sr1" }),
    ];
    const edges: ProvEdge[] = [
      edge("e_promoted", "c2", "sr1", "promoted-from"),
      edge("e_decided_s", "dec_search", "ap_search", "decided-by"),
      edge("e_triggers_s", "dec_search", "sr1", "triggers"),
      // NO triggers edge from any decision to c2 — the legacy case.
    ];
    const { viewEdges } = buildViewGraph(nodes, edges);
    const trunk = viewEdges.filter(
      (e) => e.target === "view:c2" && e.id === "e:promoted:c2",
    );
    expect(trunk).toHaveLength(1);
    expect(trunk[0].kind).toBe("promoted-from");
    // Source is the bag (search-result row sourceHandle for visual
    // dock — same as the existing structural-fallback behaviour).
    expect(trunk[0].source).toBe("view:bag:ap_search");
    expect(trunk[0].sourceHandle).toBe("row-sr1");
  });
});

describe("Sub-statement trunk parent priority", () => {
  it("attaches to the spawning action_proposal when no trail is set", () => {
    // decompose_hit decision spawns a sub_statement via a triggers
    // edge. Without a click-trail, the sub_statement should hang under
    // the action_proposal that spawned it — NOT the structural
    // parent_search_result_id.
    const nodes: ProvNode[] = [
      node("cl1", "claim", { text: "claim" }),
      node("t1", "task", { query: "q", focus_claim_id: "cl1" }),
      // The bag itself comes from the search action_proposal — needed
      // so the structural fallback (extracted/bag) would otherwise be
      // a competing parent.
      node("ap_search", "action_proposal", {
        step_kind: "search",
        anchor_node_id: "t1",
      }),
      node("dec_search", "decision", { proposal_node_id: "ap_search" }),
      node("sr1", "search_result", { text: "hit", task_node_id: "t1" }),
      node("ap_decompose", "action_proposal", {
        step_kind: "decompose_hit",
        anchor_node_id: "sr1",
      }),
      node("dec_dec", "decision", { proposal_node_id: "ap_decompose" }),
      node("sub1", "sub_statement", {
        text: "atom",
        parent_search_result_id: "sr1",
      }),
    ];
    const edges: ProvEdge[] = [
      edge("e_decided_s", "dec_search", "ap_search", "decided-by"),
      edge("e_triggers_s", "dec_search", "sr1", "triggers"),
      edge("e_decided_d", "dec_dec", "ap_decompose", "decided-by"),
      edge("e_triggers_d", "dec_dec", "sub1", "triggers"),
      edge("e_extracts", "sub1", "sr1", "extracts-from"),
    ];
    const { viewEdges } = buildViewGraph(nodes, edges);
    const trunk = viewEdges.filter(
      (e) => e.target === "view:sub1" && e.id === "e:sub:sub1",
    );
    expect(trunk).toHaveLength(1);
    expect(trunk[0].source).toBe("view:ap_decompose");
    expect(trunk[0].kind).toBe("spawns");
  });
});
