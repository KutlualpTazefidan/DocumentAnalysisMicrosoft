import dagre from "dagre";
import type { Edge as RfEdge, Node as RfNode } from "reactflow";

import type { ProvEdge, ProvNode } from "../hooks/useProvenienz";

/**
 * Two-layer layout pipeline for the Provenienz canvas.
 *
 * The raw event log (Node/Edge from the backend) is verbose by design — every
 * proposal+decision triplet inflates the visible graph by ~3x. This module
 * folds the audit-shape into a smaller "view graph" before dagre runs:
 *
 *   - Decided proposal+decision pairs disappear; we render only what they
 *     spawned.
 *   - A claim and its single task collapse into one `claim_with_task` tile.
 *   - All search_results from one task plus their evaluations collapse into
 *     one `search_results_bag` tile that lists rows internally.
 *   - Stop proposals fold in as a "🔒 abgeschlossen" badge on their anchor.
 *   - Pending (undecided) proposals stay as their own tiles — they're the
 *     call-to-action for the human.
 *
 * Layout direction is configurable; dagre lays out the view graph TB or LR.
 */

export type ViewNodeKind =
  | "chunk"
  | "claim_with_task"
  | "search_results_bag"
  | "pending_proposal";

export interface ChunkView {
  view_id: string;
  kind: "chunk";
  chunk: ProvNode;
  closedByStop?: ProvNode; // a stop_proposal anchored to this chunk
}

export interface ClaimWithTaskView {
  view_id: string;
  kind: "claim_with_task";
  claim: ProvNode;
  task?: ProvNode; // 1:1 derivation if formulated
  closedByStop?: ProvNode;
}

export interface SearchResultsBagView {
  view_id: string;
  kind: "search_results_bag";
  task: ProvNode;
  rows: { result: ProvNode; evaluation?: ProvNode }[];
}

export interface PendingProposalView {
  view_id: string;
  kind: "pending_proposal";
  proposal: ProvNode;
}

export type ViewNode =
  | ChunkView
  | ClaimWithTaskView
  | SearchResultsBagView
  | PendingProposalView;

export interface ViewEdge {
  id: string;
  source: string; // view_id
  target: string; // view_id
  kind: string;
}

export type LayoutDirection = "TB" | "LR";

interface LayoutOptions {
  direction?: LayoutDirection;
}

const NODE_DIMS: Record<ViewNodeKind, { w: number; h: number }> = {
  chunk: { w: 260, h: 110 },
  claim_with_task: { w: 280, h: 130 },
  search_results_bag: { w: 320, h: 200 }, // grows internally; dagre needs an estimate
  pending_proposal: { w: 240, h: 110 },
};

// ─── view-graph builder ───────────────────────────────────────────────────────

interface IndexedGraph {
  byId: Map<string, ProvNode>;
  outEdges: Map<string, ProvEdge[]>; // from_node → edges
  inEdges: Map<string, ProvEdge[]>; // to_node → edges
}

function indexGraph(nodes: ProvNode[], edges: ProvEdge[]): IndexedGraph {
  const byId = new Map<string, ProvNode>();
  for (const n of nodes) byId.set(n.node_id, n);
  const outEdges = new Map<string, ProvEdge[]>();
  const inEdges = new Map<string, ProvEdge[]>();
  for (const e of edges) {
    if (!outEdges.has(e.from_node)) outEdges.set(e.from_node, []);
    outEdges.get(e.from_node)!.push(e);
    if (!inEdges.has(e.to_node)) inEdges.set(e.to_node, []);
    inEdges.get(e.to_node)!.push(e);
  }
  return { byId, outEdges, inEdges };
}

/**
 * For each `action_proposal` node, find its resolving `decision` node by
 * walking `decided-by` edges (decision → proposal). A proposal is "resolved"
 * if any decision points at it.
 */
function indexProposalResolution(g: IndexedGraph): {
  decisionByProposalId: Map<string, ProvNode>;
} {
  const decisionByProposalId = new Map<string, ProvNode>();
  for (const n of g.byId.values()) {
    if (n.kind !== "decision") continue;
    const out = g.outEdges.get(n.node_id) ?? [];
    for (const e of out) {
      if (e.kind === "decided-by") {
        decisionByProposalId.set(e.to_node, n);
      }
    }
  }
  return { decisionByProposalId };
}

/**
 * Build the collapsed view graph. See module docstring for the rules.
 */
export function buildViewGraph(
  provNodes: ProvNode[],
  provEdges: ProvEdge[],
): { viewNodes: ViewNode[]; viewEdges: ViewEdge[] } {
  const g = indexGraph(provNodes, provEdges);
  const { decisionByProposalId } = indexProposalResolution(g);

  const viewNodes: ViewNode[] = [];
  const viewEdges: ViewEdge[] = [];

  // Pre-compute: for each claim, its task (if any). 1:1 via `verifies` edge.
  const taskByClaimId = new Map<string, ProvNode>();
  for (const n of provNodes) {
    if (n.kind !== "task") continue;
    const claimId = n.payload.focus_claim_id as string | undefined;
    if (claimId && g.byId.has(claimId)) {
      taskByClaimId.set(claimId, n);
    }
  }

  // Pre-compute: for each task, its search_results (N:1) and per-result
  // evaluation (1:1 via `evaluates` edge from evaluation → search_result).
  const resultsByTaskId = new Map<string, ProvNode[]>();
  for (const n of provNodes) {
    if (n.kind !== "search_result") continue;
    const taskId = n.payload.task_node_id as string | undefined;
    if (!taskId || !g.byId.has(taskId)) continue;
    if (!resultsByTaskId.has(taskId)) resultsByTaskId.set(taskId, []);
    resultsByTaskId.get(taskId)!.push(n);
  }
  const evaluationByResultId = new Map<string, ProvNode>();
  for (const n of provNodes) {
    if (n.kind !== "evaluation") continue;
    const out = g.outEdges.get(n.node_id) ?? [];
    for (const e of out) {
      if (e.kind === "evaluates" && g.byId.has(e.to_node)) {
        evaluationByResultId.set(e.to_node, n);
      }
    }
  }

  // Pre-compute: stop_proposal by anchor_node_id (only ones whose triggering
  // decision was recommended/alt with close_session=true OR override; we just
  // accept any stop_proposal as evidence the branch is closed).
  const stopByAnchorId = new Map<string, ProvNode>();
  for (const n of provNodes) {
    if (n.kind !== "stop_proposal") continue;
    const anchor = n.payload.anchor_node_id as string | undefined;
    if (anchor) stopByAnchorId.set(anchor, n);
  }

  // ── 1) Chunks ─────────────────────────────────────────────────────────────
  const chunkNodes = provNodes.filter((n) => n.kind === "chunk");
  for (const chunk of chunkNodes) {
    viewNodes.push({
      view_id: `view:${chunk.node_id}`,
      kind: "chunk",
      chunk,
      closedByStop: stopByAnchorId.get(chunk.node_id),
    });
  }

  // ── 2) Claims + their tasks ───────────────────────────────────────────────
  const claimNodes = provNodes.filter((n) => n.kind === "claim");
  for (const claim of claimNodes) {
    const view: ClaimWithTaskView = {
      view_id: `view:${claim.node_id}`,
      kind: "claim_with_task",
      claim,
      task: taskByClaimId.get(claim.node_id),
      closedByStop: stopByAnchorId.get(claim.node_id),
    };
    viewNodes.push(view);

    // Edge: chunk → claim_with_task. Find the chunk this claim was extracted
    // from via `extracts-from` edge (claim → chunk).
    const out = g.outEdges.get(claim.node_id) ?? [];
    for (const e of out) {
      if (e.kind === "extracts-from" && g.byId.has(e.to_node)) {
        viewEdges.push({
          id: `e:${e.edge_id}`,
          source: `view:${e.to_node}`, // chunk view
          target: view.view_id,
          kind: "extracts-from",
        });
      }
    }
  }

  // ── 3) Search results bags (one per task that has results) ────────────────
  for (const [taskId, results] of resultsByTaskId.entries()) {
    const task = g.byId.get(taskId)!;
    const claimId = task.payload.focus_claim_id as string | undefined;
    const bagViewId = `view:bag:${taskId}`;
    viewNodes.push({
      view_id: bagViewId,
      kind: "search_results_bag",
      task,
      rows: results.map((r) => ({
        result: r,
        evaluation: evaluationByResultId.get(r.node_id),
      })),
    });
    // Edge: claim_with_task → bag (the bag hangs off the claim's tile, since
    // the task is folded inside that tile).
    if (claimId && g.byId.has(claimId)) {
      viewEdges.push({
        id: `e:bag:${taskId}`,
        source: `view:${claimId}`,
        target: bagViewId,
        kind: "candidates-for",
      });
    }
  }

  // ── 4) Pending proposals (undecided) ──────────────────────────────────────
  for (const n of provNodes) {
    if (n.kind !== "action_proposal") continue;
    if (decisionByProposalId.has(n.node_id)) continue; // resolved → hidden
    const proposalViewId = `view:${n.node_id}`;
    viewNodes.push({
      view_id: proposalViewId,
      kind: "pending_proposal",
      proposal: n,
    });
    // Edge: anchor → pending_proposal.
    const anchorNodeId = n.payload.anchor_node_id as string | undefined;
    if (anchorNodeId && g.byId.has(anchorNodeId)) {
      // Anchor's view_id depends on what the anchor is. Map raw node_id → view_id.
      const anchorViewId = mapAnchorToViewId(anchorNodeId, g, taskByClaimId);
      if (anchorViewId) {
        viewEdges.push({
          id: `e:pp:${n.node_id}`,
          source: anchorViewId,
          target: proposalViewId,
          kind: "pending",
        });
      }
    }
  }

  return { viewNodes, viewEdges };
}

/**
 * A pending proposal anchored to e.g. a `task` node should attach to the
 * claim_with_task tile (since the task is folded into it). This helper maps
 * a raw node_id to the view_id of the tile that visually represents it.
 */
function mapAnchorToViewId(
  anchorNodeId: string,
  g: IndexedGraph,
  _taskByClaimId: Map<string, ProvNode>,
): string | undefined {
  const anchor = g.byId.get(anchorNodeId);
  if (!anchor) return undefined;
  switch (anchor.kind) {
    case "chunk":
    case "claim":
      return `view:${anchorNodeId}`;
    case "task": {
      // task is folded into its claim's view
      const claimId = anchor.payload.focus_claim_id as string | undefined;
      if (claimId) return `view:${claimId}`;
      return undefined;
    }
    case "search_result": {
      // result is folded into its task's bag view
      const taskId = anchor.payload.task_node_id as string | undefined;
      if (taskId) return `view:bag:${taskId}`;
      return undefined;
    }
    default:
      // best-effort: claims and chunks already covered; for stop_proposal,
      // evaluation, decision, action_proposal, fall through.
      return `view:${anchorNodeId}`;
  }
}

// ─── dagre layout over the view graph ────────────────────────────────────────

export function layoutViewGraph(
  viewNodes: ViewNode[],
  viewEdges: ViewEdge[],
  opts: LayoutOptions = {},
): { nodes: RfNode[]; edges: RfEdge[] } {
  const direction: LayoutDirection = opts.direction ?? "TB";
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 50, ranksep: 80 });

  for (const v of viewNodes) {
    const dims = NODE_DIMS[v.kind];
    g.setNode(v.view_id, dims);
  }
  for (const e of viewEdges) {
    if (g.hasNode(e.source) && g.hasNode(e.target)) {
      g.setEdge(e.source, e.target);
    }
  }
  dagre.layout(g);

  const rfNodes: RfNode[] = viewNodes.map((v) => {
    const pos = g.node(v.view_id);
    const dims = NODE_DIMS[v.kind];
    const x = (pos?.x ?? 0) - dims.w / 2;
    const y = (pos?.y ?? 0) - dims.h / 2;
    return {
      id: v.view_id,
      type: v.kind,
      position: { x, y },
      data: v, // panel + renderer both read from data.kind
    };
  });

  const rfEdges: RfEdge[] = viewEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: "default",
    style: { stroke: edgeColor(e.kind), strokeWidth: 1.5 },
  }));

  return { nodes: rfNodes, edges: rfEdges };
}

/**
 * Top-level: build view graph + lay it out in one call.
 */
export function layoutGraph(
  provNodes: ProvNode[],
  provEdges: ProvEdge[],
  opts: LayoutOptions = {},
): { nodes: RfNode[]; edges: RfEdge[]; viewNodes: ViewNode[] } {
  const { viewNodes, viewEdges } = buildViewGraph(provNodes, provEdges);
  const laid = layoutViewGraph(viewNodes, viewEdges, opts);
  return { ...laid, viewNodes };
}

function edgeColor(kind: string): string {
  switch (kind) {
    case "extracts-from":
      return "#60a5fa";
    case "candidates-for":
      return "#10b981";
    case "pending":
      return "#fbbf24";
    default:
      return "#475569";
  }
}
