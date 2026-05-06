import type { ComponentType } from "react";
import type { NodeProps } from "reactflow";

import { ChunkTile } from "./ChunkTile";
import { ClaimWithTaskTile } from "./ClaimWithTaskTile";
import { FallbackNode } from "./FallbackNode";
import { PendingProposalTile } from "./PendingProposalTile";
import { SearchResultsBagTile } from "./SearchResultsBagTile";

/**
 * View-graph renderers. Keys match `ViewNodeKind` in layout.ts. The raw event
 * log's `kind` (claim, task, search_result, action_proposal, decision,
 * evaluation, stop_proposal) never reaches the canvas — those fold into one
 * of these four tiles.
 */
export const nodeTypes: Record<string, ComponentType<NodeProps>> = {
  chunk: ChunkTile,
  claim_with_task: ClaimWithTaskTile,
  search_results_bag: SearchResultsBagTile,
  pending_proposal: PendingProposalTile,
  fallback: FallbackNode,
};

export { FallbackNode };
