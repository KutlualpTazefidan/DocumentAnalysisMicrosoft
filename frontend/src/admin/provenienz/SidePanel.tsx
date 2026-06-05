import type { ProvEdge, ProvNode } from "../hooks/useProvenienz";
import type { ViewNode } from "./layout";

import { ActionProposalPanel } from "./panels/ActionProposalPanel";
import { CapabilityGatePanel } from "./panels/CapabilityGatePanel";
import { CapabilityRequestPanel } from "./panels/CapabilityRequestPanel";
import { ChunkPanel } from "./panels/ChunkPanel";
import { ClaimPanel } from "./panels/ClaimPanel";
import { EvaluationPanel } from "./panels/EvaluationPanel";
import { ExpertCorrectionPanel } from "./panels/ExpertCorrectionPanel";
import { GoalPanel } from "./panels/GoalPanel";
import { ManualReviewPanel } from "./panels/ManualReviewPanel";
import { PlanProposalPanel } from "./panels/PlanProposalPanel";
import { ReflectionPanel } from "./panels/ReflectionPanel";
import { SearchResultPanel } from "./panels/SearchResultPanel";
import { SearchResultsBagPanel } from "./panels/SearchResultsBagPanel";
import { SubStatementPanel } from "./panels/SubStatementPanel";
import { TaskPanel } from "./panels/TaskPanel";
import { T } from "../styles/typography";

export interface PanelCommonProps {
  sessionId: string;
  token: string;
  view: ViewNode;
  /** Full raw node list — panels that need cross-references (e.g. the
   *  evaluate-step claim picker) read from here. */
  nodes: ProvNode[];
  edges: ProvEdge[];
  onSelectView: (viewId: string | null) => void;
}

interface Props {
  sessionId: string;
  token: string;
  selectedViewId: string | null;
  viewIndex: Map<string, ViewNode>;
  nodes: ProvNode[];
  edges: ProvEdge[];
  onSelectView: (viewId: string | null) => void;
}

export function SidePanel({
  sessionId,
  token,
  selectedViewId,
  viewIndex,
  nodes,
  edges,
  onSelectView,
}: Props): JSX.Element {
  if (!selectedViewId) {
    return (
      <div className={`p-4 ${T.body} text-ink-muted italic`}>
        Tile auf dem Canvas auswählen, um Details und Aktionen zu sehen.
      </div>
    );
  }
  const view = viewIndex.get(selectedViewId);
  if (!view) {
    return (
      <div className={`p-4 ${T.body} text-ink-muted italic`}>
        Tile nicht gefunden.
      </div>
    );
  }

  const common: PanelCommonProps = {
    sessionId,
    token,
    view,
    nodes,
    edges,
    onSelectView,
  };

  switch (view.kind) {
    case "goal":
      return <GoalPanel {...common} />;
    case "chunk":
      return <ChunkPanel {...common} />;
    case "claim":
      return <ClaimPanel {...common} />;
    case "task":
      return <TaskPanel {...common} />;
    case "search_results_bag":
      return <SearchResultsBagPanel {...common} />;
    case "search_result":
      return <SearchResultPanel {...common} />;
    case "action_proposal":
      return <ActionProposalPanel {...common} />;
    case "plan_proposal":
      return <PlanProposalPanel {...common} />;
    case "expert_step_override":
    case "expert_method_request":
    case "expert_correction":
      // Same panel surface for both Phase-3 kinds + the deprecated
      // legacy kind. The view shape (correction Node + target plan_id)
      // is identical across all three; ExpertCorrectionPanel narrows
      // and renders kind-aware copy/accent inside.
      return <ExpertCorrectionPanel {...common} />;
    case "capability_request":
      return <CapabilityRequestPanel {...common} />;
    case "manual_review":
      return <ManualReviewPanel {...common} />;
    case "reflection":
      return <ReflectionPanel {...common} />;
    case "sub_statement":
      return <SubStatementPanel {...common} />;
    case "evaluation":
      return <EvaluationPanel {...common} />;
    case "capability_gate":
      return <CapabilityGatePanel {...common} />;
  }
}

export function PanelHeader({
  title,
  subtitle,
  onClose,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
}): JSX.Element {
  return (
    <header className="px-4 py-3 border-b border-line flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className={T.tinyBold}>{title}</p>
        {subtitle && (
          <p className={`text-ink-muted ${T.body} truncate`}>{subtitle}</p>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        className={`text-ink-muted hover:text-ink ${T.body}`}
        aria-label="Schließen"
      >
        ✕
      </button>
    </header>
  );
}
