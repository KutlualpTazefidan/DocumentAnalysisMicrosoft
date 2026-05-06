import type { ProvEdge, ProvNode } from "../hooks/useProvenienz";

import { ActionProposalPanel } from "./panels/ActionProposalPanel";
import { ChunkPanel } from "./panels/ChunkPanel";
import { ClaimPanel } from "./panels/ClaimPanel";
import { DecisionPanel } from "./panels/DecisionPanel";
import { EvaluationPanel } from "./panels/EvaluationPanel";
import { SearchResultPanel } from "./panels/SearchResultPanel";
import { StopProposalPanel } from "./panels/StopProposalPanel";
import { TaskPanel } from "./panels/TaskPanel";
import { T } from "../styles/typography";

export interface PanelCommonProps {
  sessionId: string;
  token: string;
  node: ProvNode;
  nodes: ProvNode[];
  edges: ProvEdge[];
  onSelectNode: (id: string | null) => void;
}

interface Props {
  sessionId: string;
  token: string;
  selectedNodeId: string | null;
  nodes: ProvNode[];
  edges: ProvEdge[];
  onSelectNode: (id: string | null) => void;
}

/**
 * Side-panel dispatch shell. Looks up the selected node and renders
 * the kind-specific detail/action panel. Each per-kind panel takes
 * `PanelCommonProps`, fires the matching backend route, and relies on
 * React Query invalidation to refresh the canvas.
 */
export function SidePanel({
  sessionId,
  token,
  selectedNodeId,
  nodes,
  edges,
  onSelectNode,
}: Props): JSX.Element {
  if (!selectedNodeId) {
    return (
      <div className={`p-4 ${T.body} text-slate-500 italic`}>
        Knoten auf dem Canvas auswählen, um Details und Aktionen zu sehen.
      </div>
    );
  }
  const node = nodes.find((n) => n.node_id === selectedNodeId);
  if (!node) {
    return (
      <div className={`p-4 ${T.body} text-slate-500 italic`}>
        Knoten nicht gefunden.
      </div>
    );
  }

  const common: PanelCommonProps = {
    sessionId,
    token,
    node,
    nodes,
    edges,
    onSelectNode,
  };

  switch (node.kind) {
    case "chunk":
      return <ChunkPanel {...common} />;
    case "claim":
      return <ClaimPanel {...common} />;
    case "task":
      return <TaskPanel {...common} />;
    case "search_result":
      return <SearchResultPanel {...common} />;
    case "action_proposal":
      return <ActionProposalPanel {...common} />;
    case "decision":
      return <DecisionPanel {...common} />;
    case "evaluation":
      return <EvaluationPanel {...common} />;
    case "stop_proposal":
      return <StopProposalPanel {...common} />;
    default:
      return (
        <div className="p-4 text-slate-300">
          <p className={`${T.tinyBold}`}>Unbekannter Knotentyp</p>
          <p className={`${T.mono}`}>{node.kind}</p>
          <pre className="mt-2 text-[11px] whitespace-pre-wrap break-words bg-navy-900 p-2 rounded">
            {JSON.stringify(node.payload, null, 2)}
          </pre>
        </div>
      );
  }
}

/**
 * Reusable header rendered at the top of every per-kind panel. Shows
 * the node kind, id, actor + timestamp, and a close button that calls
 * `onClose` (typically `() => onSelectNode(null)`).
 */
export function PanelHeader({
  node,
  onClose,
}: {
  node: ProvNode;
  onClose: () => void;
}): JSX.Element {
  return (
    <header className="px-4 py-3 border-b border-navy-700 flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className={T.tinyBold}>{node.kind}</p>
        <p className={`text-white ${T.mono} truncate`}>{node.node_id}</p>
        <p className="text-slate-500 text-[10px]">
          {node.actor} · {node.created_at}
        </p>
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
