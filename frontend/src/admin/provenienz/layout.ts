import dagre from "dagre";
import type { Edge as RfEdge, Node as RfNode } from "reactflow";

import type { ProvEdge, ProvNode } from "../hooks/useProvenienz";

const NODE_WIDTH = 224; // matches w-56 on the renderer cards
const NODE_HEIGHT = 90; // approximate height; dagre routes around this

/**
 * Compute a top-down DAG layout via dagre and convert backend Node/Edge into
 * React-Flow shapes. The `type` on each RF node is the backend `kind` so the
 * `nodeTypes` registry (which mirrors the kinds) picks the right renderer.
 */
export function layoutGraph(
  provNodes: ProvNode[],
  provEdges: ProvEdge[],
): { nodes: RfNode[]; edges: RfEdge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 70 });

  for (const n of provNodes) {
    g.setNode(n.node_id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const e of provEdges) {
    // Skip edges that reference nodes outside the current node set; dagre
    // would otherwise auto-create dangling nodes at (0,0).
    if (g.hasNode(e.from_node) && g.hasNode(e.to_node)) {
      g.setEdge(e.from_node, e.to_node);
    }
  }
  dagre.layout(g);

  const rfNodes: RfNode[] = provNodes.map((n) => {
    const pos = g.node(n.node_id);
    const x = pos?.x ?? 0;
    const y = pos?.y ?? 0;
    return {
      id: n.node_id,
      type: n.kind,
      position: { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 },
      data: { ...n },
    };
  });

  const rfEdges: RfEdge[] = provEdges.map((e) => ({
    id: e.edge_id,
    source: e.from_node,
    target: e.to_node,
    label: e.kind,
    type: "default",
    style: { stroke: edgeColor(e.kind) },
    labelStyle: { fontSize: 10, fill: "#cbd5e1" },
    labelBgPadding: [2, 4] as [number, number],
    labelBgStyle: { fill: "#1e293b" },
  }));

  return { nodes: rfNodes, edges: rfEdges };
}

function edgeColor(kind: string): string {
  switch (kind) {
    case "extracts-from":
      return "#60a5fa";
    case "verifies":
      return "#06b6d4";
    case "candidates-for":
      return "#10b981";
    case "evaluates":
      return "#f43f5e";
    case "decided-by":
      return "#a78bfa";
    case "triggers":
      return "#94a3b8";
    default:
      return "#64748b";
  }
}
