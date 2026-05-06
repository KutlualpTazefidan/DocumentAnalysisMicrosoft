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
  closedByStop?: ProvNode;
  /** Number of claim children currently extracted from this chunk. */
  claimCount: number;
  /** True if this chunk was created via promote-search-result. */
  promoted: boolean;
}

export interface ClaimWithTaskView {
  view_id: string;
  kind: "claim_with_task";
  claim: ProvNode;
  task?: ProvNode;
  closedByStop?: ProvNode;
  /** Number of search results currently in this claim's bag (0 if no bag). */
  searchResultCount: number;
  /** Of those, how many have been evaluated. */
  evaluatedCount: number;
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
  /** Per-row handle id when the source tile exposes multiple ports
   *  (currently only the SearchResultsBag does this). */
  sourceHandle?: string;
}

export type LayoutDirection = "TB" | "LR";

interface LayoutOptions {
  direction?: LayoutDirection;
}

/**
 * Dagre uses these dimensions to reserve space; the actual rendered tile may
 * be slightly smaller, so estimates run a bit large to avoid overlap. Also
 * align to 16px so positions sit on the same grid as the snap setting.
 */
const NODE_DIMS: Record<ViewNodeKind, { w: number; h: number }> = {
  chunk: { w: 272, h: 144 },
  claim_with_task: { w: 304, h: 160 },
  search_results_bag: { w: 336, h: 304 }, // ~10 rows × 28px header + body
  pending_proposal: { w: 256, h: 144 },
};

/** Round to the nearest multiple so positions land on the snap grid. */
function snap(v: number, grid = 16): number {
  return Math.round(v / grid) * grid;
}

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

  // Pre-compute: claim count per chunk (for the "N Aussagen extrahiert" badge).
  const claimCountByChunkId = new Map<string, number>();
  for (const n of provNodes) {
    if (n.kind !== "claim") continue;
    const out = g.outEdges.get(n.node_id) ?? [];
    for (const e of out) {
      if (e.kind === "extracts-from" && g.byId.has(e.to_node)) {
        const prev = claimCountByChunkId.get(e.to_node) ?? 0;
        claimCountByChunkId.set(e.to_node, prev + 1);
      }
    }
  }

  // Pre-compute: chunks promoted from a search_result, keyed by source result.
  // Used to draw the bag → new-chunk edge with a per-row sourceHandle.
  const promotedChunkBySrId = new Map<string, ProvNode>();
  for (const n of provNodes) {
    if (n.kind !== "chunk") continue;
    const out = g.outEdges.get(n.node_id) ?? [];
    for (const e of out) {
      if (e.kind === "promoted-from" && g.byId.has(e.to_node)) {
        promotedChunkBySrId.set(e.to_node, n);
      }
    }
  }

  // ── 1) Chunks ─────────────────────────────────────────────────────────────
  const chunkNodes = provNodes.filter((n) => n.kind === "chunk");
  for (const chunk of chunkNodes) {
    const promoted = !!chunk.payload.promoted_from;
    viewNodes.push({
      view_id: `view:${chunk.node_id}`,
      kind: "chunk",
      chunk,
      closedByStop: stopByAnchorId.get(chunk.node_id),
      claimCount: claimCountByChunkId.get(chunk.node_id) ?? 0,
      promoted,
    });

    // If this chunk was promoted from a search_result, draw the link from
    // the originating bag's per-row handle to this new chunk.
    if (promoted) {
      const srId = String(chunk.payload.promoted_from);
      const sr = g.byId.get(srId);
      if (sr && sr.kind === "search_result") {
        const taskId = sr.payload.task_node_id as string | undefined;
        if (taskId && resultsByTaskId.has(taskId)) {
          viewEdges.push({
            id: `e:promoted:${chunk.node_id}`,
            source: `view:bag:${taskId}`,
            target: `view:${chunk.node_id}`,
            kind: "promoted-from",
            sourceHandle: `row-${srId}`,
          });
        }
      }
    }
  }

  // ── 2) Claims + their tasks ───────────────────────────────────────────────
  const claimNodes = provNodes.filter((n) => n.kind === "claim");
  for (const claim of claimNodes) {
    const task = taskByClaimId.get(claim.node_id);
    const taskResults = task ? (resultsByTaskId.get(task.node_id) ?? []) : [];
    const evaluatedCount = taskResults.filter(
      (r) => evaluationByResultId.has(r.node_id),
    ).length;
    const view: ClaimWithTaskView = {
      view_id: `view:${claim.node_id}`,
      kind: "claim_with_task",
      claim,
      task,
      closedByStop: stopByAnchorId.get(claim.node_id),
      searchResultCount: taskResults.length,
      evaluatedCount,
    };
    viewNodes.push(view);

    const out = g.outEdges.get(claim.node_id) ?? [];
    for (const e of out) {
      if (e.kind === "extracts-from" && g.byId.has(e.to_node)) {
        viewEdges.push({
          id: `e:${e.edge_id}`,
          source: `view:${e.to_node}`,
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

/**
 * Subtree-aware tree layout — replaces dagre's rank-based packing.
 *
 * Dagre TB packs every node at depth N onto the same horizontal row, so
 * sibling subtrees visually interleave (Aussage A | Aussage B | Aussage C
 * lined up, then Bag A | Bag B | Bag C lined up below — but Bag A may sit
 * directly under Aussage B, not under Aussage A). Our graph IS a tree
 * (chunk → claims → bags + pending proposals), so we lay out each subtree
 * as its own vertical column, then place sibling columns side-by-side
 * with generous horizontal spacing. Result: each branch stays visually
 * contained.
 *
 * For LR direction the same idea applies rotated 90°.
 */

const TILE_SEP = 56; // sibling-to-sibling padding within a level
const RANK_SEP = 96; // parent-to-child padding (trunk depth)
const ROOT_SEP = 160; // gap between independent root subtrees
const MARGIN = 32;

interface SubtreeBox {
  width: number;
  height: number;
  /** Center coordinate of THIS node within the subtree's local frame. */
  selfCenter: number;
  /** Per-node positions inside this subtree, in local coords (top-left). */
  positions: Map<string, { x: number; y: number }>;
}

function layoutSubtree(
  viewId: string,
  childrenOf: Map<string, string[]>,
  kindOf: Map<string, ViewNodeKind>,
  direction: LayoutDirection,
): SubtreeBox {
  const dims = NODE_DIMS[kindOf.get(viewId)!];
  const children = childrenOf.get(viewId) ?? [];
  const positions = new Map<string, { x: number; y: number }>();

  if (children.length === 0) {
    positions.set(viewId, { x: 0, y: 0 });
    if (direction === "TB") {
      return {
        width: dims.w,
        height: dims.h,
        selfCenter: dims.w / 2,
        positions,
      };
    }
    return {
      width: dims.w,
      height: dims.h,
      selfCenter: dims.h / 2,
      positions,
    };
  }

  const childBoxes = children.map((c) =>
    layoutSubtree(c, childrenOf, kindOf, direction),
  );

  if (direction === "TB") {
    // Stack children left-to-right; node sits centered above them.
    const childrenCombinedWidth =
      childBoxes.reduce((s, b) => s + b.width, 0) +
      TILE_SEP * (childBoxes.length - 1);
    const subtreeWidth = Math.max(dims.w, childrenCombinedWidth);

    // Node placement: horizontally centered over the children block.
    const childrenStartX = (subtreeWidth - childrenCombinedWidth) / 2;
    const selfX = (subtreeWidth - dims.w) / 2;
    positions.set(viewId, { x: selfX, y: 0 });

    const childY = dims.h + RANK_SEP;
    let cursorX = childrenStartX;
    let maxBottom = dims.h;
    for (let i = 0; i < children.length; i++) {
      const cb = childBoxes[i];
      for (const [k, v] of cb.positions) {
        positions.set(k, { x: v.x + cursorX, y: v.y + childY });
      }
      maxBottom = Math.max(maxBottom, childY + cb.height);
      cursorX += cb.width + TILE_SEP;
    }
    return {
      width: subtreeWidth,
      height: maxBottom,
      selfCenter: selfX + dims.w / 2,
      positions,
    };
  }

  // LR: stack children top-to-bottom; node sits centered to the left.
  const childrenCombinedHeight =
    childBoxes.reduce((s, b) => s + b.height, 0) +
    TILE_SEP * (childBoxes.length - 1);
  const subtreeHeight = Math.max(dims.h, childrenCombinedHeight);

  const childrenStartY = (subtreeHeight - childrenCombinedHeight) / 2;
  const selfY = (subtreeHeight - dims.h) / 2;
  positions.set(viewId, { x: 0, y: selfY });

  const childX = dims.w + RANK_SEP;
  let cursorY = childrenStartY;
  let maxRight = dims.w;
  for (let i = 0; i < children.length; i++) {
    const cb = childBoxes[i];
    for (const [k, v] of cb.positions) {
      positions.set(k, { x: v.x + childX, y: v.y + cursorY });
    }
    maxRight = Math.max(maxRight, childX + cb.width);
    cursorY += cb.height + TILE_SEP;
  }
  return {
    width: maxRight,
    height: subtreeHeight,
    selfCenter: selfY + dims.h / 2,
    positions,
  };
}

export function layoutViewGraph(
  viewNodes: ViewNode[],
  viewEdges: ViewEdge[],
  opts: LayoutOptions = {},
): { nodes: RfNode[]; edges: RfEdge[] } {
  const direction: LayoutDirection = opts.direction ?? "TB";

  // Build a parent → children adjacency. Edges that point back into the
  // tree (e.g. a stop_proposal pointing at a chunk) are silently ignored:
  // we walk parent-to-child only, every node has at most one parent in
  // practice.
  const childrenOf = new Map<string, string[]>();
  const hasParent = new Set<string>();
  const kindOf = new Map<string, ViewNodeKind>();
  const present = new Set<string>();
  for (const v of viewNodes) {
    kindOf.set(v.view_id, v.kind);
    present.add(v.view_id);
  }
  for (const e of viewEdges) {
    if (!present.has(e.source) || !present.has(e.target)) continue;
    if (hasParent.has(e.target)) continue; // first edge wins
    if (!childrenOf.has(e.source)) childrenOf.set(e.source, []);
    childrenOf.get(e.source)!.push(e.target);
    hasParent.add(e.target);
  }

  // Roots = nodes with no incoming edge. Lay each out independently.
  const positions = new Map<string, { x: number; y: number }>();
  if (direction === "TB") {
    let cursorX = MARGIN;
    for (const v of viewNodes) {
      if (hasParent.has(v.view_id)) continue;
      const box = layoutSubtree(v.view_id, childrenOf, kindOf, direction);
      for (const [k, p] of box.positions) {
        positions.set(k, { x: p.x + cursorX, y: p.y + MARGIN });
      }
      cursorX += box.width + ROOT_SEP;
    }
  } else {
    let cursorY = MARGIN;
    for (const v of viewNodes) {
      if (hasParent.has(v.view_id)) continue;
      const box = layoutSubtree(v.view_id, childrenOf, kindOf, direction);
      for (const [k, p] of box.positions) {
        positions.set(k, { x: p.x + MARGIN, y: p.y + cursorY });
      }
      cursorY += box.height + ROOT_SEP;
    }
  }

  const rfNodes: RfNode[] = viewNodes.map((v) => {
    const p = positions.get(v.view_id) ?? { x: 0, y: 0 };
    return {
      id: v.view_id,
      type: v.kind,
      position: { x: snap(p.x), y: snap(p.y) },
      data: v,
    };
  });

  const rfEdges: RfEdge[] = viewEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.sourceHandle,
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
    case "promoted-from":
      return "#a855f7"; // purple — distinct from the trunk
    default:
      return "#475569";
  }
}
