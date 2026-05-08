import { describe, expect, it } from "vitest";

import type { ProvNode } from "../../../src/admin/hooks/useProvenienz";
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

describe("Trail-as-Trunk layout", () => {
  it("plan_proposal with triggered_from points trunk at trail head, not structural anchor", () => {
    // Setup: chunk → claim → task → search_result, then a Bewertung
    // (evaluation) on the search_result, then a plan_proposal raised
    // from the Bewertung that re-anchored to the search_result.
    const nodes: ProvNode[] = [
      node("c1", "chunk", { text: "ch" }),
      node("cl1", "claim", { text: "claim" }),
      node("t1", "task", { query: "q", focus_claim_id: "cl1" }),
      node("sr1", "search_result", { text: "hit", task_node_id: "t1" }),
      node("ev1", "evaluation", {
        verdict: "supports",
        proposal_node_id: "ap-eval",
      }),
      node("pp1", "plan_proposal", {
        name: "promote_search_result",
        anchor_node_id: "sr1",
        triggered_from_node_id: "ev1",
      }),
    ];
    const { viewEdges } = buildViewGraph(nodes, []);
    // The plan_proposal's trunk edge should now come from the trail
    // head (the evaluation), NOT the structural anchor (sr1 / its bag).
    const planEdges = viewEdges.filter(
      (e) => e.target === "view:pp1" && e.id === "e:plan:pp1",
    );
    expect(planEdges).toHaveLength(1);
    expect(planEdges[0].source).toBe("view:ev1");
    expect(planEdges[0].kind).toBe("trail-trunk");
    // No competing "planner" edge from the structural anchor when trail
    // is set — that would create branching back to the search_result.
    const plannerEdges = viewEdges.filter(
      (e) => e.target === "view:pp1" && e.kind === "planner",
    );
    expect(plannerEdges).toHaveLength(0);
  });

  it("plan_proposal without triggered_from keeps structural planner edge", () => {
    const nodes: ProvNode[] = [
      node("c1", "chunk", { text: "ch" }),
      node("pp1", "plan_proposal", {
        name: "extract_claims",
        anchor_node_id: "c1",
      }),
    ];
    const { viewEdges } = buildViewGraph(nodes, []);
    const plannerEdges = viewEdges.filter(
      (e) => e.target === "view:pp1" && e.kind === "planner",
    );
    expect(plannerEdges).toHaveLength(1);
    expect(plannerEdges[0].source).toBe("view:c1");
  });

  it("action_proposal with triggered_from + no plan uses trail head as trunk parent", () => {
    const nodes: ProvNode[] = [
      node("c1", "chunk", { text: "ch" }),
      node("cl1", "claim", { text: "claim" }),
      node("t1", "task", { query: "q", focus_claim_id: "cl1" }),
      node("sr1", "search_result", { text: "hit", task_node_id: "t1" }),
      node("ev1", "evaluation", {
        verdict: "supports",
        proposal_node_id: "x",
      }),
      node("ap1", "action_proposal", {
        step_kind: "decompose_hit",
        anchor_node_id: "sr1",
        triggered_from_node_id: "ev1",
      }),
    ];
    const { viewEdges } = buildViewGraph(nodes, []);
    const apEdges = viewEdges.filter((e) => e.target === "view:ap1");
    // Trail-trunk takes precedence over structural "proposed" edge.
    expect(apEdges).toHaveLength(1);
    expect(apEdges[0].source).toBe("view:ev1");
    expect(apEdges[0].kind).toBe("trail-trunk");
  });
});
