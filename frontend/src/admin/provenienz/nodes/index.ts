import type { ComponentType } from "react";
import type { NodeProps } from "reactflow";

import { ActionProposalTile } from "./ActionProposalTile";
import { ChunkTile } from "./ChunkTile";
import { ClaimTile } from "./ClaimTile";
import { DecisionTile } from "./DecisionTile";
import { FallbackNode } from "./FallbackNode";
import { GoalTile } from "./GoalTile";
import { SearchResultsBagTile } from "./SearchResultsBagTile";
import { TaskTile } from "./TaskTile";

/**
 * View-graph renderers. Keys match `ViewNodeKind` in layout.ts.
 *
 * Trace-everything model: every event in events.jsonl that lands on the
 * canvas as a tile here. Folding only happens for 1:1 derivations
 * (claim+task) or for items that cluster naturally (search-results bag).
 * Proposals + decisions are NEVER folded — they are the audit chain.
 */
export const nodeTypes: Record<string, ComponentType<NodeProps>> = {
  goal: GoalTile,
  chunk: ChunkTile,
  claim: ClaimTile,
  task: TaskTile,
  search_results_bag: SearchResultsBagTile,
  action_proposal: ActionProposalTile,
  decision: DecisionTile,
  fallback: FallbackNode,
};

export { FallbackNode };
