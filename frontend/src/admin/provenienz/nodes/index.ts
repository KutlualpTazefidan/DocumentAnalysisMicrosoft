import type { ComponentType } from "react";
import type { NodeProps } from "reactflow";

import { ActionProposalTile } from "./ActionProposalTile";
import { CapabilityRequestTile } from "./CapabilityRequestTile";
import { ChunkTile } from "./ChunkTile";
import { ClaimTile } from "./ClaimTile";
import { FallbackNode } from "./FallbackNode";
import { GoalTile } from "./GoalTile";
import { ManualReviewTile } from "./ManualReviewTile";
import { PlanProposalTile } from "./PlanProposalTile";
import { SearchResultsBagTile } from "./SearchResultsBagTile";
import { TaskTile } from "./TaskTile";

export const nodeTypes: Record<string, ComponentType<NodeProps>> = {
  goal: GoalTile,
  chunk: ChunkTile,
  claim: ClaimTile,
  task: TaskTile,
  search_results_bag: SearchResultsBagTile,
  action_proposal: ActionProposalTile,
  plan_proposal: PlanProposalTile,
  capability_request: CapabilityRequestTile,
  manual_review: ManualReviewTile,
  fallback: FallbackNode,
};

export { FallbackNode };
