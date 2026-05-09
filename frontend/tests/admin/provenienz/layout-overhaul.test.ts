import { describe, expect, it } from "vitest";

import type {
  ProvEdge,
  ProvNode,
} from "../../../src/admin/hooks/useProvenienz";
import { layoutGraph } from "../../../src/admin/provenienz/layout";

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

describe("Layout overhaul — rank alignment", () => {
  it("places same-depth nodes from sibling subtrees at the same Y (TB)", () => {
    // Two independent root chunks, each with one claim child. The two
    // claims are at depth 1 in different subtrees — rank-alignment must
    // put them at the same Y even though their parents differ.
    const nodes: ProvNode[] = [
      node("c1", "chunk", { text: "ch1" }),
      node("c2", "chunk", { text: "ch2" }),
      node("cl1", "claim", { text: "claim1" }),
      node("cl2", "claim", { text: "claim2" }),
    ];
    const edges: ProvEdge[] = [
      {
        edge_id: "e1",
        session_id: "s1",
        from_node: "cl1",
        to_node: "c1",
        kind: "extracts-from",
        reason: null,
        actor: "agent",
        created_at: "e1",
      },
      {
        edge_id: "e2",
        session_id: "s1",
        from_node: "cl2",
        to_node: "c2",
        kind: "extracts-from",
        reason: null,
        actor: "agent",
        created_at: "e2",
      },
    ];
    const { nodes: rfNodes } = layoutGraph(nodes, edges);
    const cl1 = rfNodes.find((n) => n.id === "view:cl1")!;
    const cl2 = rfNodes.find((n) => n.id === "view:cl2")!;
    expect(cl1.position.y).toBe(cl2.position.y);
    // Both chunks should also share Y (depth 0).
    const c1 = rfNodes.find((n) => n.id === "view:c1")!;
    const c2 = rfNodes.find((n) => n.id === "view:c2")!;
    expect(c1.position.y).toBe(c2.position.y);
    // Claims sit BELOW chunks in TB direction.
    expect(cl1.position.y).toBeGreaterThan(c1.position.y);
  });

  it("places deeper nodes strictly below shallower nodes (TB monotonic Y)", () => {
    // Single trunk chunk → claim → task chain. Each rank must sit
    // below the previous one.
    const nodes: ProvNode[] = [
      node("c1", "chunk", { text: "ch" }),
      node("cl1", "claim", { text: "claim" }),
      node("t1", "task", { query: "q", focus_claim_id: "cl1" }),
    ];
    const edges: ProvEdge[] = [
      {
        edge_id: "e1",
        session_id: "s1",
        from_node: "cl1",
        to_node: "c1",
        kind: "extracts-from",
        reason: null,
        actor: "agent",
        created_at: "e1",
      },
    ];
    const { nodes: rfNodes } = layoutGraph(nodes, edges);
    const c1 = rfNodes.find((n) => n.id === "view:c1")!;
    const cl1 = rfNodes.find((n) => n.id === "view:cl1")!;
    const t1 = rfNodes.find((n) => n.id === "view:t1")!;
    expect(cl1.position.y).toBeGreaterThan(c1.position.y);
    expect(t1.position.y).toBeGreaterThan(cl1.position.y);
  });
});

describe("Layout overhaul — subtree wrap", () => {
  it("starts a new row when the cumulative subtree width exceeds WRAP_WIDTH", () => {
    // Build many independent root chunks. Each chunk is 272px wide;
    // with TILE_SEP=80 and ROOT_SEP=192, ~10 chunks comfortably push
    // past the 2400px wrap threshold.
    const numRoots = 12;
    const nodes: ProvNode[] = [];
    for (let i = 0; i < numRoots; i++) {
      nodes.push(node(`c${i}`, "chunk", { text: `ch${i}` }));
    }
    const { nodes: rfNodes } = layoutGraph(nodes, []);
    // Group root tiles by Y; if wrap kicked in there must be ≥2
    // distinct Y values among the root chunks.
    const ysSet = new Set(rfNodes.map((n) => n.position.y));
    expect(ysSet.size).toBeGreaterThanOrEqual(2);
    // The largest x on the first row should not exceed WRAP_WIDTH.
    const minY = Math.min(...rfNodes.map((n) => n.position.y));
    const firstRow = rfNodes.filter((n) => n.position.y === minY);
    const maxXFirstRow = Math.max(...firstRow.map((n) => n.position.x));
    // Each chunk is 272px; allow some slack.
    expect(maxXFirstRow + 272).toBeLessThanOrEqual(2400 + 32 + 100);
  });

  it("does not wrap when all subtrees comfortably fit on one row", () => {
    // 3 independent root chunks; combined width well under WRAP_WIDTH.
    const nodes: ProvNode[] = [
      node("c1", "chunk", { text: "ch1" }),
      node("c2", "chunk", { text: "ch2" }),
      node("c3", "chunk", { text: "ch3" }),
    ];
    const { nodes: rfNodes } = layoutGraph(nodes, []);
    const ys = new Set(rfNodes.map((n) => n.position.y));
    expect(ys.size).toBe(1);
  });
});

describe("Layout overhaul — orthogonal edges", () => {
  it("emits smoothstep edges with arrow markers + path options", () => {
    const nodes: ProvNode[] = [
      node("c1", "chunk", { text: "ch" }),
      node("cl1", "claim", { text: "claim" }),
    ];
    const edges: ProvEdge[] = [
      {
        edge_id: "e1",
        session_id: "s1",
        from_node: "cl1",
        to_node: "c1",
        kind: "extracts-from",
        reason: null,
        actor: "agent",
        created_at: "e1",
      },
    ];
    const { edges: rfEdges } = layoutGraph(nodes, edges);
    expect(rfEdges.length).toBeGreaterThan(0);
    for (const e of rfEdges) {
      expect(e.type).toBe("smoothstep");
      // pathOptions present on the edge object (smoothstep-specific).
      expect(
        (e as unknown as { pathOptions?: unknown }).pathOptions,
      ).toBeDefined();
      // markerEnd is an object with the closed-arrow type.
      expect(e.markerEnd).toBeDefined();
      const m = e.markerEnd as { type: string };
      expect(m.type).toBe("arrowclosed");
    }
  });
});
