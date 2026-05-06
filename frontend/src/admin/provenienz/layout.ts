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
  | "goal"
  | "chunk"
  | "claim"
  | "task"
  | "search_results_bag"
  | "action_proposal"
  | "decision";

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

export interface ClaimView {
  view_id: string;
  kind: "claim";
  claim: ProvNode;
  closedByStop?: ProvNode;
}

export interface TaskView {
  view_id: string;
  kind: "task";
  task: ProvNode;
  /** True if a search has been run on this task. */
  hasResults: boolean;
}

export interface SearchResultsBagView {
  view_id: string;
  kind: "search_results_bag";
  task: ProvNode;
  rows: { result: ProvNode; evaluation?: ProvNode }[];
}

export interface ActionProposalView {
  view_id: string;
  kind: "action_proposal";
  proposal: ProvNode;
  /** True iff a decision Node points at this proposal via decided-by.
   *  Decided proposals render dim; pending ones glow yellow. */
  decided: boolean;
}

export interface DecisionView {
  view_id: string;
  kind: "decision";
  decision: ProvNode;
  /** The proposal this decision resolves, for back-reference in the panel. */
  proposal_node_id: string;
}

export interface GoalView {
  view_id: string;
  kind: "goal";
  /** Latest goal text. Empty string = not yet set. */
  text: string;
  /** session id, so the panel can fire updates. */
  session_id: string;
}

export type ViewNode =
  | GoalView
  | ChunkView
  | ClaimView
  | TaskView
  | SearchResultsBagView
  | ActionProposalView
  | DecisionView;

export interface ViewEdge {
  id: string;
  source: string; // view_id
  target: string; // view_id
  kind: string;
  /** Per-row handle id when the source tile exposes multiple ports
   *  (currently only the SearchResultsBag does this). */
  sourceHandle?: string;
  /** "trunk" defines tree-layout parentage; "side" is rendered as a
   *  visual edge but skipped by the tree-layout walker — used to dock
   *  decision tiles next to their proposal without consuming a tree
   *  slot. Default: "trunk". */
  placement?: "trunk" | "side";
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
  goal: { w: 384, h: 96 },
  chunk: { w: 272, h: 144 },
  claim: { w: 272, h: 144 },
  task: { w: 256, h: 112 },
  search_results_bag: { w: 336, h: 304 },
  action_proposal: { w: 320, h: 200 },
  decision: { w: 224, h: 96 },
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

interface SessionMetaLike {
  session_id: string;
  goal: string;
}

/**
 * Build the collapsed view graph. See module docstring for the rules.
 */
export function buildViewGraph(
  provNodes: ProvNode[],
  provEdges: ProvEdge[],
  meta?: SessionMetaLike,
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

  // ── 0) Goal tile (top of every session) ───────────────────────────────────
  // Synthesised — not a real node in the event log. Reads meta.goal so the
  // user can see the research goal in the canvas alongside everything else.
  let rootChunkViewId: string | null = null;
  if (meta) {
    const rootChunk = provNodes.find(
      (n) => n.kind === "chunk" && !n.payload.promoted_from,
    );
    if (rootChunk) {
      rootChunkViewId = `view:${rootChunk.node_id}`;
      viewNodes.push({
        view_id: `view:goal:${meta.session_id}`,
        kind: "goal",
        text: meta.goal,
        session_id: meta.session_id,
      });
      viewEdges.push({
        id: `e:goal->root`,
        source: `view:goal:${meta.session_id}`,
        target: rootChunkViewId,
        kind: "directs",
      });
    }
  }

  // For each spawned node we look up the proposal that produced it.
  // Decision-via-triggers → proposal-via-decided-by → proposal_node.
  const proposalSpawningNode = new Map<string, ProvNode>(); // spawned_node_id → proposal
  for (const n of provNodes) {
    if (n.kind !== "decision") continue;
    let parentProposalId: string | null = null;
    for (const e of g.outEdges.get(n.node_id) ?? []) {
      if (e.kind === "decided-by") {
        parentProposalId = e.to_node;
        break;
      }
    }
    if (!parentProposalId) continue;
    const proposal = g.byId.get(parentProposalId);
    if (!proposal) continue;
    for (const e of g.outEdges.get(n.node_id) ?? []) {
      if (e.kind === "triggers" && g.byId.has(e.to_node)) {
        proposalSpawningNode.set(e.to_node, proposal);
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

    // Promoted chunks: bag → new chunk (trunk continuation through the loop).
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

  // ── 2) Claims (own tile, spawned by extract_claims action_proposal) ───────
  const claimNodes = provNodes.filter((n) => n.kind === "claim");
  for (const claim of claimNodes) {
    viewNodes.push({
      view_id: `view:${claim.node_id}`,
      kind: "claim",
      claim,
      closedByStop: stopByAnchorId.get(claim.node_id),
    });
    // Trunk: parent = the action_proposal that spawned this claim.
    // Fallback: chunk via extracts-from (e.g. for legacy data without a
    // proposal/decision pair).
    const proposal = proposalSpawningNode.get(claim.node_id);
    if (proposal) {
      viewEdges.push({
        id: `e:claim-from-prop:${claim.node_id}`,
        source: `view:${proposal.node_id}`,
        target: `view:${claim.node_id}`,
        kind: "spawns",
      });
    } else {
      for (const e of g.outEdges.get(claim.node_id) ?? []) {
        if (e.kind === "extracts-from" && g.byId.has(e.to_node)) {
          viewEdges.push({
            id: `e:${e.edge_id}`,
            source: `view:${e.to_node}`,
            target: `view:${claim.node_id}`,
            kind: "extracts-from",
          });
        }
      }
    }
  }

  // ── 3) Tasks (own tile, spawned by formulate_task action_proposal) ────────
  for (const task of provNodes.filter((n) => n.kind === "task")) {
    const results = resultsByTaskId.get(task.node_id) ?? [];
    viewNodes.push({
      view_id: `view:${task.node_id}`,
      kind: "task",
      task,
      hasResults: results.length > 0,
    });
    const proposal = proposalSpawningNode.get(task.node_id);
    if (proposal) {
      viewEdges.push({
        id: `e:task-from-prop:${task.node_id}`,
        source: `view:${proposal.node_id}`,
        target: `view:${task.node_id}`,
        kind: "spawns",
      });
    } else {
      // Fallback: claim via focus_claim_id
      const claimId = task.payload.focus_claim_id as string | undefined;
      if (claimId && g.byId.has(claimId)) {
        viewEdges.push({
          id: `e:task-claim:${task.node_id}`,
          source: `view:${claimId}`,
          target: `view:${task.node_id}`,
          kind: "verifies",
        });
      }
    }
  }

  // ── 4) Search results bags (one per task that has results) ────────────────
  for (const [taskId, results] of resultsByTaskId.entries()) {
    const task = g.byId.get(taskId)!;
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
    // Trunk: parent = the search action_proposal that triggered the search.
    // Fallback: the task itself (if no proposal recorded — legacy path).
    const firstResult = results[0];
    const searchProposal = firstResult
      ? proposalSpawningNode.get(firstResult.node_id)
      : undefined;
    if (searchProposal) {
      viewEdges.push({
        id: `e:bag:${taskId}`,
        source: `view:${searchProposal.node_id}`,
        target: bagViewId,
        kind: "spawns",
      });
    } else if (g.byId.has(taskId)) {
      viewEdges.push({
        id: `e:bag-task:${taskId}`,
        source: `view:${taskId}`,
        target: bagViewId,
        kind: "candidates-for",
      });
    }
  }

  // ── 5) Action-Proposals + Decisions (proposal in trunk, decision aside) ───
  // Every action_proposal becomes a trunk tile under its anchor. Decision
  // tiles dock to the side of their proposal — they don't consume a trunk
  // slot, so the main flow stays linear.
  for (const n of provNodes) {
    if (n.kind !== "action_proposal") continue;
    const proposalViewId = `view:${n.node_id}`;
    const decision = decisionByProposalId.get(n.node_id);
    viewNodes.push({
      view_id: proposalViewId,
      kind: "action_proposal",
      proposal: n,
      decided: !!decision,
    });
    const anchorNodeId = n.payload.anchor_node_id as string | undefined;
    if (anchorNodeId && g.byId.has(anchorNodeId)) {
      // Anchor's view_id depends on what the anchor is. Tasks are now their
      // own tiles, so a search proposal anchored to a task points at the task
      // tile (not the claim tile, as it did when task was folded).
      const anchorViewId = mapAnchorToViewId(anchorNodeId, g, taskByClaimId);
      if (anchorViewId) {
        viewEdges.push({
          id: `e:ap:${n.node_id}`,
          source: anchorViewId,
          target: proposalViewId,
          kind: "proposed",
        });
      }
    }
    if (decision) {
      const decisionViewId = `view:${decision.node_id}`;
      viewNodes.push({
        view_id: decisionViewId,
        kind: "decision",
        decision,
        proposal_node_id: n.node_id,
      });
      // SIDE edge — placed manually after layout, doesn't count as tree
      // parentage. Keeps the trunk linear.
      viewEdges.push({
        id: `e:dec:${decision.node_id}`,
        source: proposalViewId,
        target: decisionViewId,
        kind: "decided-by",
        placement: "side",
      });
    }
  }

  // (plan_proposal nodes used to render as their own canvas tile here.
  // We dropped the separate Vorschlag UI — pre-reasoning is now folded
  // into every action_proposal directly. plan_proposal entries from
  // older sessions are silently ignored on the canvas; they remain in
  // events.jsonl for audit.)

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
    case "task":
      // task is now its own view tile
      return `view:${anchorNodeId}`;
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
  // Trunk edges define tree parentage; side edges are skipped here and
  // post-positioned next to their source after the trunk lands.
  const trunkEdges = viewEdges.filter(
    (e) => (e.placement ?? "trunk") === "trunk",
  );
  const sideEdges = viewEdges.filter((e) => e.placement === "side");
  for (const e of trunkEdges) {
    if (!present.has(e.source) || !present.has(e.target)) continue;
    if (hasParent.has(e.target)) continue; // first edge wins
    if (!childrenOf.has(e.source)) childrenOf.set(e.source, []);
    childrenOf.get(e.source)!.push(e.target);
    hasParent.add(e.target);
  }

  // Roots = nodes with no incoming trunk edge. Lay each out independently.
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

  // Side placement: dock each side-edge target next to its source. For
  // TB direction the target sits to the right of the source at the same
  // vertical centre; for LR direction it sits below.
  const SIDE_GAP = 64;
  for (const e of sideEdges) {
    const sourcePos = positions.get(e.source);
    if (!sourcePos) continue;
    const sourceKind = kindOf.get(e.source);
    const targetKind = kindOf.get(e.target);
    if (!sourceKind || !targetKind) continue;
    const srcDims = NODE_DIMS[sourceKind];
    const tgtDims = NODE_DIMS[targetKind];
    if (direction === "TB") {
      positions.set(e.target, {
        x: sourcePos.x + srcDims.w + SIDE_GAP,
        y: sourcePos.y + (srcDims.h - tgtDims.h) / 2,
      });
    } else {
      positions.set(e.target, {
        x: sourcePos.x + (srcDims.w - tgtDims.w) / 2,
        y: sourcePos.y + srcDims.h + SIDE_GAP,
      });
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
  meta?: SessionMetaLike,
): { nodes: RfNode[]; edges: RfEdge[]; viewNodes: ViewNode[] } {
  const { viewNodes, viewEdges } = buildViewGraph(provNodes, provEdges, meta);
  const laid = layoutViewGraph(viewNodes, viewEdges, opts);
  return { ...laid, viewNodes };
}

function edgeColor(kind: string): string {
  switch (kind) {
    case "extracts-from":
      return "#60a5fa";
    case "candidates-for":
      return "#10b981";
    case "spawns":
      return "#60a5fa"; // blue — proposal spawned this trunk node
    case "verifies":
      return "#06b6d4"; // cyan — task verifies a claim (legacy fallback)
    case "proposed":
      return "#fbbf24"; // amber — anchor proposed an action here
    case "decided-by":
      return "#a78bfa"; // violet — side edge to the decision tile
    case "promoted-from":
      return "#a855f7";
    case "directs":
      return "#f472b6";
    case "planner":
      return "#fbbf24";
    default:
      return "#475569";
  }
}
