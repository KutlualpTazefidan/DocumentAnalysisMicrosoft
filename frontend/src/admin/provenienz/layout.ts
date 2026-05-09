import {
  MarkerType,
  type Edge as RfEdge,
  type Node as RfNode,
} from "reactflow";

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
  | "search_result"
  | "action_proposal"
  | "plan_proposal"
  | "capability_request"
  | "manual_review"
  | "reflection"
  | "sub_statement"
  | "evaluation"
  | "capability_gate";

export interface ChunkView {
  view_id: string;
  kind: "chunk";
  chunk: ProvNode;
  closedByStop?: ProvNode;
  /** Number of claim children currently extracted from this chunk. */
  claimCount: number;
  /** True if this chunk was created via promote-search-result. */
  promoted: boolean;
  /** True when a newer chunk Node carries a ``refreshes`` edge pointing
   *  at this one — i.e. this chunk was respawned from the current
   *  segments.json. The tile dims so the audit trail visually flows
   *  predecessor → successor; both stay clickable for historical
   *  research. */
  replacedByRefresh?: boolean;
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
  /** node_id of the search-action_proposal that triggered this bag.
   *  Null only for legacy results that pre-date the proposal-spawning
   *  audit. The bag panel uses this id for "Bag löschen" — deleting
   *  the proposal cascades through decision → triggers → results. */
  searchProposalId: string | null;
}

/**
 * Per-row tile, only for results that have a downstream
 * plan_proposal or action_proposal anchored to them. Extracted from
 * the bag so each "actioned" row gets its own audit chain
 * (bag → result_tile → plan_proposal → action_proposal → ...).
 * Unactioned rows stay folded into the bag.
 */
export interface SearchResultTileView {
  view_id: string;
  kind: "search_result";
  result: ProvNode;
  /** The evaluation Node, if one exists for this row. */
  evaluation?: ProvNode;
}

export interface ActionProposalView {
  view_id: string;
  kind: "action_proposal";
  proposal: ProvNode;
  /** When set, the proposal is decided. The decision is folded into
   *  this view (no separate tile) — its panel shows accepted/reason
   *  inline below the proposal audit. */
  decision?: ProvNode;
}

export interface PlanProposalView {
  view_id: string;
  kind: "plan_proposal";
  /** The plan node from /next-step. Carries kind=executable_step plan,
   *  with chosen step name + considered alternatives + reasoning. The
   *  user's "Akzeptieren" fires the underlying step from the panel. */
  plan: ProvNode;
  /** True once a downstream action_proposal has been attached to this
   *  plan in the chain — i.e. the user clicked Akzeptieren and the
   *  step actually fired. Triggers the dimmed/faded tile variant
   *  (same look as decided action_proposals). */
  consumed?: boolean;
}

export interface CapabilityRequestView {
  view_id: string;
  kind: "capability_request";
  /** The capability_request node — agent flagged a missing capability. */
  request: ProvNode;
}

export interface ManualReviewView {
  view_id: string;
  kind: "manual_review";
  /** The manual_review node — agent escalated to human. */
  review: ProvNode;
}

/**
 * Self-critique node attached to an action_proposal. Lives in the
 * canvas as a small tile under the proposal that was reviewed,
 * showing the self_assessment + recommendation.
 */
export interface ReflectionView {
  view_id: string;
  kind: "reflection";
  reflection: ProvNode;
}

/**
 * Atomic sub-statement extracted from a search_result via the
 * decompose_hit step. One self-contained claim per tile, evaluated
 * independently against the upstream claim. Sits below its parent
 * search_result_tile in the canvas.
 */
export interface SubStatementView {
  view_id: string;
  kind: "sub_statement";
  sub_statement: ProvNode;
}

/**
 * Spawned evaluation Node (from /decide on an evaluate action_proposal).
 * Rendered as a Folge-Knoten under the action_proposal so the chain
 * shows ``proposal → evaluation`` explicitly. The verdict + sentences
 * detail are still folded into the parent search_result tile too;
 * this view exposes them as their own clickable audit anchor.
 */
export interface EvaluationView {
  view_id: string;
  kind: "evaluation";
  evaluation: ProvNode;
}

/**
 * Reactive-Capability gate — auto-spawned after an evaluate decision
 * if any approach with non-empty triggers matched. Carries the list
 * of detected top-level + sub capabilities. User accepts the gate to
 * trigger a re-evaluate with the loaded domain rules; or dismisses it.
 */
export interface CapabilityGateView {
  view_id: string;
  kind: "capability_gate";
  gate: ProvNode;
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
  | SearchResultTileView
  | ActionProposalView
  | PlanProposalView
  | CapabilityRequestView
  | ManualReviewView
  | ReflectionView
  | SubStatementView
  | EvaluationView
  | CapabilityGateView;

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
  search_result: { w: 320, h: 144 },
  action_proposal: { w: 320, h: 240 },
  plan_proposal: { w: 320, h: 220 },
  capability_request: { w: 320, h: 180 },
  manual_review: { w: 320, h: 160 },
  reflection: { w: 320, h: 180 },
  sub_statement: { w: 280, h: 112 },
  evaluation: { w: 320, h: 144 },
  capability_gate: { w: 320, h: 168 },
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

  // ── Trail-as-Trunk pre-pass ──────────────────────────────────────────────
  // When a node carries `triggered_from_node_id`, the canvas should render
  // the trunk edge from the trail-parent (the nearest ancestor in the same
  // trail), not from the structural anchor. This produces a single visual
  // strand "Bewertung → plan → action → new_node" instead of branching
  // back to the structural origin.
  //
  // For each trail-bearing node we resolve the trail-parent:
  //   1. Find the spawning proposal (the action_proposal that decided it).
  //      If that proposal carries the SAME trail, use its view as parent.
  //   2. Otherwise the trail-bearing node is the immediate child of the
  //      trail head — use the trail head's view directly. Plan/action
  //      proposal nodes whose `triggered_from_node_id` was set by /next-step
  //      take this path (they're the entry into the trail).
  const trailParentByViewId = new Map<string, string>();
  // Reverse map: when a node has a trail-parent, the structural edge for
  // that node should be skipped (the trail subsumes it). Keyed by viewId.
  const trailCoversNode = new Set<string>();
  for (const n of provNodes) {
    const trail = String(n.payload.triggered_from_node_id ?? "");
    if (!trail) continue;
    const nodeViewId = `view:${n.node_id}`;
    const spawningProposal = proposalSpawningNode.get(n.node_id);
    if (spawningProposal) {
      const proposalTrail = String(
        spawningProposal.payload.triggered_from_node_id ?? "",
      );
      if (proposalTrail === trail) {
        trailParentByViewId.set(nodeViewId, `view:${spawningProposal.node_id}`);
        trailCoversNode.add(nodeViewId);
        continue;
      }
    }
    // No spawning proposal in the same trail — this node IS the immediate
    // child of the trail head (typically a plan_proposal or action_proposal
    // raised from a Folge-Knoten). Parent edge points at the trail head.
    if (g.byId.has(trail)) {
      trailParentByViewId.set(nodeViewId, `view:${trail}`);
      trailCoversNode.add(nodeViewId);
    }
  }

  // ── Bag-bucket data prep (pre-pass) ───────────────────────────────────────
  // Multiple search-runs on the same task each get their own bag,
  // keyed by spawning search-action_proposal. Built BEFORE pass #1 so
  // the chunk + sub-statement edge passes can resolve a result-id to
  // its specific bag-view-id.
  type BagBucket = {
    bagViewId: string;
    task: ProvNode;
    results: ProvNode[];
    searchProposalId: string | null;
    parentEdge: {
      source: string;
      kind: "spawns" | "candidates-for";
      edgeIdSuffix: string;
    } | null;
  };
  const bagViewIdByResultId = new Map<string, string>();
  const bagBuckets = new Map<string, BagBucket>();
  for (const [taskId, results] of resultsByTaskId.entries()) {
    const task = g.byId.get(taskId);
    if (!task) continue;
    for (const r of results) {
      const proposal = proposalSpawningNode.get(r.node_id);
      const key = proposal ? `prop:${proposal.node_id}` : `legacy:${taskId}`;
      let bucket = bagBuckets.get(key);
      if (!bucket) {
        const bagViewId = proposal
          ? `view:bag:${proposal.node_id}`
          : `view:bag:legacy:${taskId}`;
        bucket = {
          bagViewId,
          task,
          results: [],
          searchProposalId: proposal?.node_id ?? null,
          parentEdge: proposal
            ? {
                source: `view:${proposal.node_id}`,
                kind: "spawns",
                edgeIdSuffix: `prop:${proposal.node_id}`,
              }
            : g.byId.has(taskId)
              ? {
                  source: `view:${taskId}`,
                  kind: "candidates-for",
                  edgeIdSuffix: `task:${taskId}`,
                }
              : null,
        };
        bagBuckets.set(key, bucket);
      }
      bucket.results.push(r);
      bagViewIdByResultId.set(r.node_id, bucket.bagViewId);
    }
  }

  // ── 1) Chunks ─────────────────────────────────────────────────────────────
  const chunkNodes = provNodes.filter((n) => n.kind === "chunk");
  // Pre-compute: chunks that have been *replaced* by a newer refresh
  // (i.e. a `refreshes` edge points at them). Used to dim the predecessor
  // tile so the visible chain visually flows old → new.
  const refreshedChunkIds = new Set<string>();
  for (const e of provEdges) {
    if (e.kind === "refreshes") refreshedChunkIds.add(e.to_node);
  }
  for (const chunk of chunkNodes) {
    const promoted = !!chunk.payload.promoted_from;
    viewNodes.push({
      view_id: `view:${chunk.node_id}`,
      kind: "chunk",
      chunk,
      closedByStop: stopByAnchorId.get(chunk.node_id),
      claimCount: claimCountByChunkId.get(chunk.node_id) ?? 0,
      promoted,
      replacedByRefresh: refreshedChunkIds.has(chunk.node_id),
    });

    // Promoted chunks: trunk parent priority is
    //   1. trail-parent (when this chunk inherits a click-trail) — keeps
    //      the visual strand "Bewertung → plan → action → chunk" intact,
    //   2. proposalSpawningNode — the action_proposal that spawned the
    //      chunk via promote_search_result. Without this the chain
    //      visually breaks back to the bag, even though audit-wise the
    //      proposal is the real parent,
    //   3. structural fallback: bag → chunk via `promoted-from` (legacy
    //      data without a spawning proposal/decision triplet).
    // The structural "bag → chunk" relationship stays in the chunk's
    // payload (`promoted_from`) for audit either way.
    const chunkViewId = `view:${chunk.node_id}`;
    if (promoted) {
      const srId = String(chunk.payload.promoted_from);
      const sr = g.byId.get(srId);
      if (sr && sr.kind === "search_result") {
        const trailParent = trailParentByViewId.get(chunkViewId);
        const spawningProposal = proposalSpawningNode.get(chunk.node_id);
        if (trailParent) {
          viewEdges.push({
            id: `e:promoted:${chunk.node_id}`,
            source: trailParent,
            target: chunkViewId,
            kind: "trail-trunk",
          });
        } else if (spawningProposal) {
          viewEdges.push({
            id: `e:promoted:${chunk.node_id}`,
            source: `view:${spawningProposal.node_id}`,
            target: chunkViewId,
            kind: "spawns",
          });
        } else {
          const bagViewId = bagViewIdByResultId.get(srId);
          if (bagViewId) {
            viewEdges.push({
              id: `e:promoted:${chunk.node_id}`,
              source: bagViewId,
              target: chunkViewId,
              kind: "promoted-from",
              sourceHandle: `row-${srId}`,
            });
          }
        }
      }
    }

    // Refresh chain: when this chunk was spawned via /refresh from an
    // older chunk, draw a SIDE edge old_chunk → new_chunk. Side
    // placement keeps both tiles independent in the trunk layout (the
    // new chunk inherits its own claim subtree; the old one keeps its
    // historical descendants).
    for (const e of g.outEdges.get(chunk.node_id) ?? []) {
      if (e.kind === "refreshes" && g.byId.has(e.to_node)) {
        viewEdges.push({
          id: `e:refreshes:${e.edge_id}`,
          source: `view:${e.to_node}`,
          target: `view:${chunk.node_id}`,
          kind: "refreshes",
          placement: "side",
        });
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

  // ── 4) Search results bags ────────────────────────────────────────────────
  // Buckets were built in the pre-pass. Here we just push view nodes +
  // their parent edges.
  for (const bucket of bagBuckets.values()) {
    viewNodes.push({
      view_id: bucket.bagViewId,
      kind: "search_results_bag",
      task: bucket.task,
      rows: bucket.results.map((r) => ({
        result: r,
        evaluation: evaluationByResultId.get(r.node_id),
      })),
      searchProposalId: bucket.searchProposalId,
    });
    if (bucket.parentEdge) {
      viewEdges.push({
        id: `e:bag:${bucket.parentEdge.edgeIdSuffix}`,
        source: bucket.parentEdge.source,
        target: bucket.bagViewId,
        kind: bucket.parentEdge.kind,
      });
    }
  }

  // ── 4.5) Extracted search-result tiles ───────────────────────────────────
  // Any search_result that has a downstream plan_proposal or
  // action_proposal anchored to it gets pulled out of the bag as its
  // own tile. Each one starts an audit chain
  // (bag → result_tile → plan/action). Unactioned rows stay folded
  // into the bag.
  const actionedResultIds = new Set<string>();
  for (const n of provNodes) {
    if (n.kind !== "plan_proposal" && n.kind !== "action_proposal") continue;
    const anchorId = n.payload.anchor_node_id as string | undefined;
    if (!anchorId) continue;
    const anchor = g.byId.get(anchorId);
    if (anchor && anchor.kind === "search_result") {
      actionedResultIds.add(anchorId);
    }
  }
  for (const resultId of actionedResultIds) {
    const result = g.byId.get(resultId);
    if (!result) continue;
    const tileViewId = `view:${resultId}`;
    viewNodes.push({
      view_id: tileViewId,
      kind: "search_result",
      result,
      evaluation: evaluationByResultId.get(resultId),
    });
    const bagViewId = bagViewIdByResultId.get(resultId);
    if (bagViewId) {
      viewEdges.push({
        id: `e:extracted:${resultId}`,
        source: bagViewId,
        target: tileViewId,
        kind: "extracted",
        sourceHandle: `row-${resultId}`,
      });
    }
  }

  // ── 4.6) Sub-Statement tiles (atomare Aussagen aus decompose_hit) ────────
  // Trunk parent priority:
  //   1. trail-parent — when the spawning chain carries a triggered_from
  //      (i.e. the user accepted decompose_hit from a Bewertungs-Trail),
  //      the sub_statement hangs from the trail-parent (the action_proposal
  //      that spawned it) — keeps the visual trail strand intact,
  //   2. proposalSpawningNode — the decompose_hit action_proposal that
  //      decided this sub_statement. Without this lookup the chain
  //      visually breaks back to the structural search_result even when
  //      the audit chain says "proposal spawned this",
  //   3. structural fallback: parent_search_result_id (extracted tile
  //      when actioned, bag otherwise) — legacy data without a spawning
  //      proposal/decision triplet.
  for (const n of provNodes) {
    if (n.kind !== "sub_statement") continue;
    const subViewId = `view:${n.node_id}`;
    viewNodes.push({
      view_id: subViewId,
      kind: "sub_statement",
      sub_statement: n,
    });
    const trailParent = trailParentByViewId.get(subViewId);
    if (trailParent) {
      viewEdges.push({
        id: `e:sub-trail:${n.node_id}`,
        source: trailParent,
        target: subViewId,
        kind: "trail-trunk",
      });
      continue;
    }
    const spawningProposal = proposalSpawningNode.get(n.node_id);
    if (spawningProposal) {
      viewEdges.push({
        id: `e:sub:${n.node_id}`,
        source: `view:${spawningProposal.node_id}`,
        target: subViewId,
        kind: "spawns",
      });
      continue;
    }
    const parentSrId = n.payload.parent_search_result_id as string | undefined;
    if (parentSrId && actionedResultIds.has(parentSrId)) {
      viewEdges.push({
        id: `e:sub:${n.node_id}`,
        source: `view:${parentSrId}`,
        target: subViewId,
        kind: "extracts-from",
      });
    } else if (parentSrId) {
      // Fallback: parent is not yet actioned (rare race) — link from
      // its bag instead.
      const bagViewId = bagViewIdByResultId.get(parentSrId);
      if (bagViewId) {
        viewEdges.push({
          id: `e:sub:${n.node_id}`,
          source: bagViewId,
          target: subViewId,
          kind: "extracts-from",
        });
      }
    }
  }

  // ── 5) Plan-Proposals from /next-step (executable_step path) ─────────────
  // The agent picked a registered step. The user accepts/dismisses to fire
  // the step's existing /extract-claims, /formulate-task, etc. route.
  // Built BEFORE action_proposals so the action-proposal pass can chain
  // through the matching plan_proposal where one exists.
  const planByAnchor = new Map<
    string,
    { node: (typeof provNodes)[number]; viewId: string }[]
  >();
  // We push placeholder PlanProposalView entries here and update them
  // (set ``consumed=true``) in the action_proposal pass below. Keeping
  // a side-map so we can flip the flag without re-finding the entry.
  const planViewByNodeId = new Map<string, PlanProposalView>();
  for (const n of provNodes) {
    if (n.kind !== "plan_proposal") continue;
    const planViewId = `view:${n.node_id}`;
    const view: PlanProposalView = {
      view_id: planViewId,
      kind: "plan_proposal",
      plan: n,
      consumed: false,
    };
    viewNodes.push(view);
    planViewByNodeId.set(n.node_id, view);
    const anchor = n.payload.anchor_node_id as string | undefined;
    // Trail-as-Trunk: when this plan_proposal carries a trail (i.e. was
    // invoked from a Folge-Knoten that re-anchored to its parent — e.g.
    // a Bewertungs-Tile routes its run to the parent search_result),
    // the trunk parent is the trail head itself, NOT the structural
    // anchor. The structural anchor stays in the payload for audit;
    // the canvas renders one continuous trail strand instead of
    // branching back to the structural origin.
    const trailParent = trailParentByViewId.get(planViewId);
    if (trailParent) {
      viewEdges.push({
        id: `e:plan:${n.node_id}`,
        source: trailParent,
        target: planViewId,
        kind: "trail-trunk",
      });
      // Still record the structural anchor for the action_proposal pass
      // below — it uses planByAnchor to chain plan → action via the
      // anchor's tile lookup.
      if (anchor && g.byId.has(anchor)) {
        const list = planByAnchor.get(anchor) ?? [];
        list.push({ node: n, viewId: planViewId });
        planByAnchor.set(anchor, list);
      }
      continue;
    }
    if (anchor && g.byId.has(anchor)) {
      const anchorViewId = mapAnchorToViewId(
        anchor,
        g,
        taskByClaimId,
        actionedResultIds,
        bagViewIdByResultId,
      );
      if (anchorViewId) {
        viewEdges.push({
          id: `e:plan:${n.node_id}`,
          source: anchorViewId,
          target: planViewId,
          kind: "planner",
        });
      }
      const list = planByAnchor.get(anchor) ?? [];
      list.push({ node: n, viewId: planViewId });
      planByAnchor.set(anchor, list);
    }
  }
  // Sort each anchor's plan_proposals by creation time so the chain
  // pass picks the most recent plan that predates each action_proposal.
  for (const list of planByAnchor.values()) {
    list.sort((a, b) => a.node.created_at.localeCompare(b.node.created_at));
  }

  // ── 6) Action-Proposals (decision folded inline) ──────────────────────────
  // Every action_proposal becomes a trunk tile. Source edge:
  //   • If a plan_proposal exists for the same anchor created BEFORE this
  //     action_proposal, edge: plan_proposal → action_proposal (full
  //     audit chain anchor → plan → action).
  //   • Otherwise, edge: anchor → action_proposal (manual-trigger path).
  // When decided, the decision Node is folded INTO the proposal view
  // (passed as `decision` field) — no separate decision tile.
  for (const n of provNodes) {
    if (n.kind !== "action_proposal") continue;
    const proposalViewId = `view:${n.node_id}`;
    const decision = decisionByProposalId.get(n.node_id);
    viewNodes.push({
      view_id: proposalViewId,
      kind: "action_proposal",
      proposal: n,
      decision,
    });
    const anchorNodeId = n.payload.anchor_node_id as string | undefined;
    if (!anchorNodeId || !g.byId.has(anchorNodeId)) continue;
    // Look for the most recent plan_proposal for this anchor that
    // predates the action_proposal — that's the chain link.
    const plans = planByAnchor.get(anchorNodeId) ?? [];
    const linkingPlan = [...plans]
      .reverse()
      .find((p) => p.node.created_at < n.created_at);
    if (linkingPlan) {
      viewEdges.push({
        id: `e:ap:${n.node_id}`,
        source: linkingPlan.viewId,
        target: proposalViewId,
        kind: "proposed",
      });
      // Mark the chained plan as "consumed" so the tile fades.
      const planView = planViewByNodeId.get(linkingPlan.node.node_id);
      if (planView) planView.consumed = true;
    } else {
      // Trail-as-Trunk: action_proposals raised directly from a
      // Folge-Knoten (no plan-proposal in between) get their trunk
      // edge from the trail head. The structural anchor stays in the
      // payload for audit; the canvas renders the trail strand.
      const trailParent = trailParentByViewId.get(proposalViewId);
      if (trailParent) {
        viewEdges.push({
          id: `e:ap:${n.node_id}`,
          source: trailParent,
          target: proposalViewId,
          kind: "trail-trunk",
        });
      } else {
        const anchorViewId = mapAnchorToViewId(
          anchorNodeId,
          g,
          taskByClaimId,
          actionedResultIds,
          bagViewIdByResultId,
        );
        if (anchorViewId) {
          viewEdges.push({
            id: `e:ap:${n.node_id}`,
            source: anchorViewId,
            target: proposalViewId,
            kind: "proposed",
          });
        }
      }
    }
  }

  // ── 7) Capability-Requests (agent says capability is missing) ─────────────
  for (const n of provNodes) {
    if (n.kind !== "capability_request") continue;
    const cvId = `view:${n.node_id}`;
    viewNodes.push({ view_id: cvId, kind: "capability_request", request: n });
    const anchor = n.payload.anchor_node_id as string | undefined;
    if (anchor && g.byId.has(anchor)) {
      const anchorViewId = mapAnchorToViewId(
        anchor,
        g,
        taskByClaimId,
        actionedResultIds,
        bagViewIdByResultId,
      );
      if (anchorViewId) {
        viewEdges.push({
          id: `e:cap:${n.node_id}`,
          source: anchorViewId,
          target: cvId,
          kind: "needs-capability",
        });
      }
    }
  }

  // ── 6.5) Evaluations als Folge-Knoten unter ihrem action_proposal ─────────
  // Die evaluation Node trägt verdict + reasoning + sentences[]. Wir
  // hängen sie als eigenes Tile unter den evaluate-action_proposal,
  // damit die Chain anchor → plan → action → evaluation explizit
  // sichtbar ist (statt nur als Verdict-Badge im search_result Tile).
  for (const n of provNodes) {
    if (n.kind !== "evaluation") continue;
    const evalViewId = `view:${n.node_id}`;
    viewNodes.push({ view_id: evalViewId, kind: "evaluation", evaluation: n });
    const proposalId = n.payload.proposal_node_id as string | undefined;
    if (proposalId && g.byId.has(proposalId)) {
      viewEdges.push({
        id: `e:eval:${n.node_id}`,
        source: `view:${proposalId}`,
        target: evalViewId,
        kind: "spawns",
      });
    }
  }

  // ── 6.6) Capability-Gates (reactive-capability auto-scan) ────────────────
  // Latest gate per (evaluation_node_id) wins — re-evaluate decisions
  // append a new gate-record with status="accepted" so the canvas
  // reflects the current state. Gate hangs off its evaluation.
  const gateByEvaluation = new Map<string, ProvNode>();
  for (const n of provNodes) {
    if (n.kind !== "capability_gate") continue;
    const evalId = String(n.payload.evaluation_node_id ?? "");
    if (!evalId) continue;
    const prev = gateByEvaluation.get(evalId);
    if (!prev || prev.created_at < n.created_at) {
      gateByEvaluation.set(evalId, n);
    }
  }
  for (const [evalId, gateNode] of gateByEvaluation) {
    const gateViewId = `view:${gateNode.node_id}`;
    viewNodes.push({
      view_id: gateViewId,
      kind: "capability_gate",
      gate: gateNode,
    });
    if (g.byId.has(evalId)) {
      viewEdges.push({
        id: `e:gate:${gateNode.node_id}`,
        source: `view:${evalId}`,
        target: gateViewId,
        kind: "triggers-capability",
      });
    }
    // If the gate has a re-evaluate proposal attached, draw the
    // chain edge gate → action_proposal so the audit chain extends.
    const reProposalId = String(gateNode.payload.re_evaluate_proposal_id ?? "");
    if (reProposalId && g.byId.has(reProposalId)) {
      viewEdges.push({
        id: `e:re-eval:${gateNode.node_id}`,
        source: gateViewId,
        target: `view:${reProposalId}`,
        kind: "re-evaluated-with",
      });
    }
  }

  // ── 7.5) Reflections (self-critique nodes) ────────────────────────────────
  // A reflection.payload.anchor_node_id points at the action_proposal
  // it critiqued. Attach as a side branch under the proposal so the
  // audit chain extends but doesn't disrupt the trunk layout.
  for (const n of provNodes) {
    if (n.kind !== "reflection") continue;
    const refViewId = `view:${n.node_id}`;
    viewNodes.push({ view_id: refViewId, kind: "reflection", reflection: n });
    const proposalId = n.payload.anchor_node_id as string | undefined;
    if (proposalId && g.byId.has(proposalId)) {
      viewEdges.push({
        id: `e:reflect:${n.node_id}`,
        source: `view:${proposalId}`,
        target: refViewId,
        kind: "reflects",
      });
    }
  }

  // ── 8) Manual-Review (agent escalates to human) ───────────────────────────
  for (const n of provNodes) {
    if (n.kind !== "manual_review") continue;
    const mvId = `view:${n.node_id}`;
    viewNodes.push({ view_id: mvId, kind: "manual_review", review: n });
    const anchor = n.payload.anchor_node_id as string | undefined;
    if (anchor && g.byId.has(anchor)) {
      const anchorViewId = mapAnchorToViewId(
        anchor,
        g,
        taskByClaimId,
        actionedResultIds,
        bagViewIdByResultId,
      );
      if (anchorViewId) {
        viewEdges.push({
          id: `e:mr:${n.node_id}`,
          source: anchorViewId,
          target: mvId,
          kind: "escalates",
        });
      }
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
  extractedResultIds?: Set<string>,
  bagViewIdByResultId?: Map<string, string>,
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
      // If the result has been actioned (a plan_proposal or
      // action_proposal hangs off it), it has its own extracted tile.
      // Otherwise it stays folded into its bag view.
      if (extractedResultIds?.has(anchorNodeId)) {
        return `view:${anchorNodeId}`;
      }
      return bagViewIdByResultId?.get(anchorNodeId);
    }
    case "sub_statement":
      // sub_statement tiles are always rendered (one per row from the
      // decompose_hit decision). plan_proposals anchored to a sub
      // can therefore link directly.
      return `view:${anchorNodeId}`;
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

// Box-to-box gaps. Tightened to 2rem (32px) for a dense canvas —
// siblings and parent-child rest on the same target so the visual
// grid reads as evenly-spaced. ROOT_SEP stays a notch larger so
// independent subtrees remain distinguishable as separate groups.
// MARGIN is now zero — ReactFlow's viewport padding takes over.
const TILE_SEP = 32; // sibling-to-sibling padding within a level (2rem)
const RANK_SEP = 32; // parent-to-child padding (trunk depth) (2rem)
const ROOT_SEP = 48; // gap between independent root subtrees (also row gap) (3rem)
const MARGIN = 0;
/**
 * Wrap roots onto a new row once the cumulative subtree width on the current
 * row would exceed this. 2400px covers the vast majority of monitors at
 * comfortable zoom; users still pan/zoom freely beyond it. A single
 * oversize subtree still gets a full row to itself — we only wrap when
 * there's at least one root already placed on the current row.
 */
const WRAP_WIDTH = 2400;

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

  // Roots = nodes with no incoming trunk edge.
  const roots: string[] = [];
  for (const v of viewNodes) {
    if (!hasParent.has(v.view_id)) roots.push(v.view_id);
  }

  // ── Subtree X layout (children stay packed under their parent) ─────────
  // We still rely on layoutSubtree for sibling packing along the
  // transverse axis (X for TB, Y for LR). Its longitudinal coordinate
  // (Y for TB, X for LR) is overwritten below by the rank-alignment
  // pass — we only keep the relative-x mapping it produced.
  const subtreeBoxes = new Map<string, SubtreeBox>();
  for (const root of roots) {
    subtreeBoxes.set(root, layoutSubtree(root, childrenOf, kindOf, direction));
  }

  // ── Subtree wrapping: greedy bin-pack roots into rows ──────────────────
  // Each row collects roots until the cumulative width (TB) or height
  // (LR) exceeds WRAP_WIDTH. A single oversized subtree still gets a
  // row to itself.
  interface PackedRow {
    roots: string[];
    /** Per-root local-frame offset along the row's primary axis
     *  (X for TB, Y for LR). The non-primary axis is rank-aligned
     *  within the row in the next pass. */
    rootStart: Map<string, number>;
    /** Row's bounding box in the primary axis (after packing).
     *  Used to position subsequent rows along the secondary axis. */
    rowExtent: number;
  }
  const rows: PackedRow[] = [];
  {
    let current: PackedRow = {
      roots: [],
      rootStart: new Map(),
      rowExtent: 0,
    };
    let cursor = 0;
    for (const root of roots) {
      const box = subtreeBoxes.get(root)!;
      const primary = direction === "TB" ? box.width : box.height;
      const tooWide = cursor + primary > WRAP_WIDTH;
      if (tooWide && current.roots.length > 0) {
        // Close current row, start a new one.
        current.rowExtent = cursor - ROOT_SEP; // last separator wasn't needed
        rows.push(current);
        current = { roots: [], rootStart: new Map(), rowExtent: 0 };
        cursor = 0;
      }
      current.rootStart.set(root, cursor);
      current.roots.push(root);
      cursor += primary + ROOT_SEP;
    }
    if (current.roots.length > 0) {
      current.rowExtent = cursor - ROOT_SEP;
      rows.push(current);
    }
  }

  // ── Rank computation ───────────────────────────────────────────────────
  // BFS from every root assigns each view its depth in the tree.
  const rankOf = new Map<string, number>();
  for (const root of roots) {
    rankOf.set(root, 0);
    const queue: string[] = [root];
    while (queue.length > 0) {
      const v = queue.shift()!;
      const r = rankOf.get(v)!;
      for (const c of childrenOf.get(v) ?? []) {
        if (rankOf.has(c)) continue;
        rankOf.set(c, r + 1);
        queue.push(c);
      }
    }
  }

  // ── Rank-aligned Y (TB) / X (LR) per row ───────────────────────────────
  // Within a row, every node at depth N sits at the same secondary
  // coordinate, regardless of which subtree it belongs to. The rank
  // baseline is row-local — row 2 starts a fresh baseline below row 1.
  const positions = new Map<string, { x: number; y: number }>();
  let rowCursor = MARGIN; // secondary-axis cursor advancing row by row
  for (const row of rows) {
    // Bucket nodes-in-this-row by rank, take the max dim per rank.
    const nodesInRow = new Set<string>();
    for (const root of row.roots) {
      const box = subtreeBoxes.get(root)!;
      for (const k of box.positions.keys()) nodesInRow.add(k);
    }
    const rankSize = new Map<number, number>(); // rank → max secondary-dim
    for (const v of nodesInRow) {
      const r = rankOf.get(v) ?? 0;
      const dims = NODE_DIMS[kindOf.get(v)!];
      const sec = direction === "TB" ? dims.h : dims.w;
      const prev = rankSize.get(r) ?? 0;
      if (sec > prev) rankSize.set(r, sec);
    }
    const ranks = [...rankSize.keys()].sort((a, b) => a - b);
    const rankPos = new Map<number, number>();
    let acc = rowCursor;
    for (const r of ranks) {
      rankPos.set(r, acc);
      acc += rankSize.get(r)! + RANK_SEP;
    }
    // acc now sits one RANK_SEP past the bottom of the last rank.
    // Strip that trailing separator to get the row's true secondary
    // extent (top-of-first-rank to bottom-of-last-rank).
    const rowSecondaryExtent =
      ranks.length > 0 ? acc - RANK_SEP - rowCursor : 0;

    // Apply: primary axis from subtree + row offset; secondary from rank.
    for (const root of row.roots) {
      const box = subtreeBoxes.get(root)!;
      const startPrimary = (row.rootStart.get(root) ?? 0) + MARGIN;
      for (const [k, local] of box.positions) {
        const r = rankOf.get(k) ?? 0;
        const rankSecondary = rankPos.get(r) ?? rowCursor;
        if (direction === "TB") {
          positions.set(k, {
            x: local.x + startPrimary,
            y: rankSecondary,
          });
        } else {
          positions.set(k, {
            x: rankSecondary,
            y: local.y + startPrimary,
          });
        }
      }
    }

    rowCursor += rowSecondaryExtent + ROOT_SEP;
  }

  // Side placement: dock each side-edge target next to its source. For
  // TB direction the target sits to the right of the source at the same
  // vertical centre; for LR direction it sits below.
  const SIDE_GAP = 32; // 2rem — matches TILE_SEP / RANK_SEP for visual consistency
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

  const rfEdges: RfEdge[] = viewEdges.map((e) => {
    const color = edgeColor(e.kind);
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      sourceHandle: e.sourceHandle,
      type: "smoothstep",
      pathOptions: { borderRadius: 8, offset: 24 },
      style: { stroke: color, strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color },
    };
  });

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
    case "needs-capability":
      return "#facc15"; // yellow — capability gap
    case "escalates":
      return "#f87171"; // red-ish — manual review
    case "promoted-from":
      return "#a855f7";
    case "directs":
      return "#f472b6";
    case "planner":
      return "#fbbf24";
    case "extracted":
      return "#06b6d4"; // cyan — search-result row pulled out of the bag
    case "reflects":
      return "#a78bfa"; // violet — self-critique side branch
    case "triggers-capability":
      return "#f97316"; // orange — reactive capability gate
    case "re-evaluated-with":
      return "#fb923c"; // orange-light — re-eval chain after gate
    case "triggered-from":
      return "#fde047"; // yellow-300 — click-trail when "Was als
    // nächstes?" was invoked from a Folge-Knoten and re-anchored
    // to its parent. Distinct hue from amber-400/proposed so the
    // user spots the trail edge instantly.
    case "trail-trunk":
      return "#fde047"; // yellow-300 — same hue as triggered-from so
    // the click-trail reads as one continuous strand. Used for
    // every trunk edge that follows the trail through plan →
    // action → spawned-node, replacing the structural anchor edge.
    case "refreshes":
      return "#fb923c"; // orange-400 — chunk respawned from current
    // segments.json. Old chunk → new chunk, drawn as a side edge so
    // the trunk layout treats both as independent roots while the
    // user still sees "this replaces that".
    default:
      return "#475569";
  }
}
