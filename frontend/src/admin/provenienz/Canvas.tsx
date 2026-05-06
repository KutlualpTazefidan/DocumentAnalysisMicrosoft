import { useEffect, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "reactflow";
import "reactflow/dist/style.css";
import { Grid3x3, Maximize2, MoveVertical, MoveHorizontal } from "lucide-react";

import type { ProvEdge, ProvNode } from "../hooks/useProvenienz";
import { layoutGraph, type LayoutDirection, type ViewNode } from "./layout";
import { nodeTypes } from "./nodes";

interface Props {
  nodes: ProvNode[];
  edges: ProvEdge[];
  /** Receives the view_id of the clicked tile. */
  onSelectView?: (viewId: string | null) => void;
  /** Map view_id → ViewNode so the side panel can render kind-specific UI. */
  onViewIndex?: (index: Map<string, ViewNode>) => void;
}

/**
 * React-Flow wrapper. Builds a collapsed view-graph (proposal+decision pairs
 * folded, claim+task fused, search_results bagged) before dagre runs. Toolbar
 * gives a reset, layout-direction toggle, and snap-to-grid toggle.
 */
export function Canvas({
  nodes,
  edges,
  onSelectView,
  onViewIndex,
}: Props): JSX.Element {
  const [direction, setDirection] = useState<LayoutDirection>("TB");
  const [snap, setSnap] = useState(true);

  const laid = useMemo(
    () => layoutGraph(nodes, edges, { direction }),
    [nodes, edges, direction],
  );
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState(laid.nodes);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState(laid.edges);

  // Preserve user-dragged positions across refetches: keep the existing
  // position for any tile the user already moved; only new tiles use the
  // dagre-computed coordinates.
  useEffect(() => {
    setRfNodes((prev) => {
      const prevPos = new Map(prev.map((n) => [n.id, n.position]));
      return laid.nodes.map((n) => ({
        ...n,
        position: prevPos.get(n.id) ?? n.position,
      }));
    });
    setRfEdges(laid.edges);
  }, [laid.nodes, laid.edges, setRfNodes, setRfEdges]);

  useEffect(() => {
    if (!onViewIndex) return;
    const idx = new Map<string, ViewNode>();
    for (const v of laid.viewNodes) idx.set(v.view_id, v);
    onViewIndex(idx);
  }, [laid.viewNodes, onViewIndex]);

  return (
    <div className="w-full h-full bg-navy-900 relative">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_e, n) => onSelectView?.(n.id)}
        onPaneClick={() => onSelectView?.(null)}
        snapToGrid={snap}
        snapGrid={[16, 16]}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} color="#1e293b" />
        <Controls />
        <MiniMap pannable zoomable nodeColor={() => "#334155"} />
        <Toolbar
          direction={direction}
          onToggleDirection={() =>
            setDirection((d) => (d === "TB" ? "LR" : "TB"))
          }
          snap={snap}
          onToggleSnap={() => setSnap((s) => !s)}
        />
      </ReactFlow>
    </div>
  );
}

/**
 * Floating toolbar: reset / fit-view, layout-direction toggle, snap toggle.
 * Lives inside <ReactFlow> so it can call `useReactFlow` to access fitView().
 */
function Toolbar({
  direction,
  onToggleDirection,
  snap,
  onToggleSnap,
}: {
  direction: LayoutDirection;
  onToggleDirection: () => void;
  snap: boolean;
  onToggleSnap: () => void;
}): JSX.Element {
  const rf = useReactFlow();
  return (
    <div className="absolute top-3 right-3 z-10 flex flex-col gap-1 bg-navy-800/95 border border-navy-600 rounded shadow-md p-1">
      <ToolbarButton
        title="Layout zurücksetzen"
        onClick={() => rf.fitView({ duration: 250, padding: 0.2 })}
      >
        <Maximize2 className="w-4 h-4" />
      </ToolbarButton>
      <ToolbarButton
        title={direction === "TB" ? "Auf horizontal umschalten" : "Auf vertikal umschalten"}
        onClick={onToggleDirection}
      >
        {direction === "TB" ? (
          <MoveHorizontal className="w-4 h-4" />
        ) : (
          <MoveVertical className="w-4 h-4" />
        )}
      </ToolbarButton>
      <ToolbarButton
        title={snap ? "Snap-to-Grid: an" : "Snap-to-Grid: aus"}
        onClick={onToggleSnap}
        active={snap}
      >
        <Grid3x3 className="w-4 h-4" />
      </ToolbarButton>
    </div>
  );
}

function ToolbarButton({
  title,
  onClick,
  children,
  active = false,
}: {
  title: string;
  onClick: () => void;
  children: React.ReactNode;
  active?: boolean;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      className={`p-1.5 rounded transition-colors ${
        active
          ? "bg-blue-600 text-white"
          : "text-slate-300 hover:bg-navy-700 hover:text-white"
      }`}
    >
      {children}
    </button>
  );
}
