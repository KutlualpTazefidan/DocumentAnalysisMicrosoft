import type { ProvEdge, ProvNode } from "../hooks/useProvenienz";
import type { ViewNode } from "./layout";

import { ActionProposalPanel } from "./panels/ActionProposalPanel";
import { ChunkPanel } from "./panels/ChunkPanel";
import { ClaimWithTaskPanel } from "./panels/ClaimWithTaskPanel";
import { GoalPanel } from "./panels/GoalPanel";
import { PlanProposalPanel } from "./panels/PlanProposalPanel";
import { SearchResultsBagPanel } from "./panels/SearchResultsBagPanel";
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
      <div className={`p-4 ${T.body} text-slate-500 italic`}>
        Tile auf dem Canvas auswählen, um Details und Aktionen zu sehen.
      </div>
    );
  }
  const view = viewIndex.get(selectedViewId);
  if (!view) {
    return (
      <div className={`p-4 ${T.body} text-slate-500 italic`}>
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
    case "claim_with_task":
      return <ClaimWithTaskPanel {...common} />;
    case "search_results_bag":
      return <SearchResultsBagPanel {...common} />;
    case "pending_proposal":
      return <ActionProposalPanel {...common} />;
    case "plan_proposal":
      return <PlanProposalPanel {...common} />;
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
    <header className="px-4 py-3 border-b border-navy-700 flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className={T.tinyBold}>{title}</p>
        {subtitle && (
          <p className={`text-slate-400 ${T.body} truncate`}>{subtitle}</p>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        className={`text-slate-400 hover:text-white ${T.body}`}
        aria-label="Schließen"
      >
        ✕
      </button>
    </header>
  );
}
