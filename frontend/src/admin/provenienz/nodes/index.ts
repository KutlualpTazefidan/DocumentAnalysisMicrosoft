import type { ComponentType } from "react";
import type { NodeProps } from "reactflow";

import { ActionProposalTile } from "./ActionProposalTile";
import { CapabilityGateTile } from "./CapabilityGateTile";
import { CapabilityRequestTile } from "./CapabilityRequestTile";
import { ChunkTile } from "./ChunkTile";
import { ClaimTile } from "./ClaimTile";
import { EvaluationTile } from "./EvaluationTile";
import { FallbackNode } from "./FallbackNode";
import { GoalTile } from "./GoalTile";
import { ManualReviewTile } from "./ManualReviewTile";
import { PlanProposalTile } from "./PlanProposalTile";
import { ReflectionTile } from "./ReflectionTile";
import { SearchResultsBagTile } from "./SearchResultsBagTile";
import { SearchResultTile } from "./SearchResultTile";
import { SubStatementTile } from "./SubStatementTile";
import { TaskTile } from "./TaskTile";

export const nodeTypes: Record<string, ComponentType<NodeProps>> = {
  goal: GoalTile,
  chunk: ChunkTile,
  claim: ClaimTile,
  task: TaskTile,
  search_results_bag: SearchResultsBagTile,
  search_result: SearchResultTile,
  action_proposal: ActionProposalTile,
  plan_proposal: PlanProposalTile,
  capability_request: CapabilityRequestTile,
  manual_review: ManualReviewTile,
  reflection: ReflectionTile,
  sub_statement: SubStatementTile,
  evaluation: EvaluationTile,
  capability_gate: CapabilityGateTile,
  fallback: FallbackNode,
};

export { FallbackNode };
