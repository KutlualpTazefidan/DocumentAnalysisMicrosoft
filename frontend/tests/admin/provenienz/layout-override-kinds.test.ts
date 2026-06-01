import { describe, expect, it } from "vitest";

import type {
  ProvEdge,
  ProvNode,
} from "../../../src/admin/hooks/useProvenienz";
import {
  buildViewGraph,
  type ExpertMethodRequestView,
  type ExpertStepOverrideView,
} from "../../../src/admin/provenienz/layout";

/**
 * Phase-3 layout walker tests: the canvas must emit the right
 * ViewNode kind for each of the two new override Node-Kinds.
 * Legacy expert_correction Nodes are aliased to the new kinds by
 * the backend session-detail endpoint before they reach the
 * frontend; the walker no longer emits the legacy kind directly.
 */

function node(
  id: string,
  kind: string,
  payload: Record<string, unknown> = {},
  actor: "human" | "agent" | "planner" = "human",
): ProvNode {
  return {
    node_id: id,
    session_id: "s1",
    kind,
    payload,
    actor,
    created_at: id,
  };
}

function edge(id: string, from: string, to: string, kind: string): ProvEdge {
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

function baseChunkAndPlan(): { nodes: ProvNode[]; edges: ProvEdge[] } {
  // Plan-proposal sits as a sibling of a chunk anchor. Minimal trunk
  // so the walker has a planViewByNodeId entry to attach the override
  // sibling to.
  const nodes: ProvNode[] = [
    node("c1", "chunk", { text: "anchor" }, "agent"),
    node(
      "plan1",
      "plan_proposal",
      {
        kind: "executable_step",
        name: "extract_claims",
        reasoning: "agent's pick",
        considered_alternatives: [],
        confidence: 0.8,
        tool: null,
        approach_id: null,
        anchor_node_id: "c1",
      },
      "planner",
    ),
  ];
  return { nodes, edges: [] };
}

describe("layout walker — Phase-3 override kinds", () => {
  it("emits ExpertStepOverrideView for an expert_step_override Node anchored to a plan_proposal", () => {
    const base = baseChunkAndPlan();
    const override = node("ovr1", "expert_step_override", {
      intended_step: "formulate_task",
      reason: "Task passt besser",
      target_proposal_node_id: "plan1",
      target_step_kind: "extract_claims",
    });
    const { viewNodes, viewEdges } = buildViewGraph(
      [...base.nodes, override],
      base.edges,
    );
    const overrideView = viewNodes.find(
      (v) => v.view_id === `view:${override.node_id}`,
    );
    expect(overrideView).toBeDefined();
    expect(overrideView!.kind).toBe("expert_step_override");
    const typed = overrideView as ExpertStepOverrideView;
    expect(typed.correction.node_id).toBe("ovr1");
    expect(typed.target_proposal_node_id).toBe("plan1");
    // Dashed "overrides" edge connects plan_proposal → override view.
    expect(
      viewEdges.find(
        (e) =>
          e.source === "view:plan1" &&
          e.target === `view:${override.node_id}` &&
          e.kind === "overrides",
      ),
    ).toBeDefined();
  });

  it("emits ExpertMethodRequestView for an expert_method_request Node anchored to a plan_proposal", () => {
    const base = baseChunkAndPlan();
    const override = node("ovr2", "expert_method_request", {
      intended_step: "summarize_section",
      name: "summarize_section",
      description: "Chunk needs a summary first",
      reason: "Chunk needs a summary first",
      target_proposal_node_id: "plan1",
      target_step_kind: "extract_claims",
    });
    const { viewNodes, viewEdges } = buildViewGraph(
      [...base.nodes, override],
      base.edges,
    );
    const overrideView = viewNodes.find(
      (v) => v.view_id === `view:${override.node_id}`,
    );
    expect(overrideView).toBeDefined();
    expect(overrideView!.kind).toBe("expert_method_request");
    const typed = overrideView as ExpertMethodRequestView;
    expect(typed.correction.node_id).toBe("ovr2");
    expect(typed.target_proposal_node_id).toBe("plan1");
    expect(
      viewEdges.find(
        (e) =>
          e.source === "view:plan1" &&
          e.target === `view:${override.node_id}` &&
          e.kind === "overrides",
      ),
    ).toBeDefined();
  });

  it("skips override Nodes whose target_proposal_node_id doesn't match a plan in the view set", () => {
    const base = baseChunkAndPlan();
    const orphan = node("orphan", "expert_step_override", {
      intended_step: "formulate_task",
      reason: "orphan — plan id doesn't exist",
      target_proposal_node_id: "missing-plan",
    });
    const { viewNodes } = buildViewGraph([...base.nodes, orphan], base.edges);
    // No view emitted for an orphan override (defensive: layout walker
    // skips when the anchor plan_proposal is absent).
    expect(
      viewNodes.find((v) => v.view_id === `view:${orphan.node_id}`),
    ).toBeUndefined();
  });

  it("does NOT emit a ViewNode for legacy expert_correction Nodes (backend aliases them upstream)", () => {
    // Defensive coverage: even if a legacy Node somehow reaches the
    // frontend (e.g. the backend alias was bypassed), the walker
    // silently skips it instead of rendering with the wrong shape.
    const base = baseChunkAndPlan();
    const legacy = node("legacy", "expert_correction", {
      intended_step: "formulate_task",
      is_unimplemented: false,
      target_proposal_node_id: "plan1",
    });
    const { viewNodes } = buildViewGraph([...base.nodes, legacy], base.edges);
    expect(
      viewNodes.find((v) => v.view_id === `view:${legacy.node_id}`),
    ).toBeUndefined();
  });

  it("emits the right kind for two overrides on the same plan_proposal (step-override + method-request)", () => {
    const base = baseChunkAndPlan();
    const stepOverride = node("ovr1", "expert_step_override", {
      intended_step: "formulate_task",
      reason: "Task passt besser",
      target_proposal_node_id: "plan1",
    });
    const methodRequest = node("ovr2", "expert_method_request", {
      intended_step: "summarize_section",
      name: "summarize_section",
      reason: "Methode fehlt",
      target_proposal_node_id: "plan1",
    });
    const { viewNodes } = buildViewGraph(
      [...base.nodes, stepOverride, methodRequest],
      base.edges,
    );
    const kindsForOverrides = viewNodes
      .filter((v) => v.view_id.startsWith("view:ovr"))
      .map((v) => v.kind)
      .sort();
    expect(kindsForOverrides).toEqual([
      "expert_method_request",
      "expert_step_override",
    ]);
  });
});
