import type { ComponentType } from "react";
import type { NodeProps } from "reactflow";

import { ActionProposalNode } from "./ActionProposalNode";
import { ChunkNode } from "./ChunkNode";
import { ClaimNode } from "./ClaimNode";
import { DecisionNode } from "./DecisionNode";
import { EvaluationNode } from "./EvaluationNode";
import { FallbackNode } from "./FallbackNode";
import { SearchResultNode } from "./SearchResultNode";
import { StopProposalNode } from "./StopProposalNode";
import { TaskNode } from "./TaskNode";

/**
 * React-Flow needs `nodeTypes` keyed by the (string) `type` field on each node.
 * We pass through the backend `kind` directly so unknown kinds also work
 * (callers should fall back to `fallback` when a kind is missing).
 */
export const nodeTypes: Record<string, ComponentType<NodeProps>> = {
  chunk: ChunkNode,
  claim: ClaimNode,
  task: TaskNode,
  search_result: SearchResultNode,
  action_proposal: ActionProposalNode,
  decision: DecisionNode,
  evaluation: EvaluationNode,
  stop_proposal: StopProposalNode,
  fallback: FallbackNode,
};

export { FallbackNode };
