import { useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  Grid3x3,
  Maximize2,
  MoveVertical,
  MoveHorizontal,
  RotateCcw,
} from "lucide-react";

import type { ProvEdge, ProvNode } from "../hooks/useProvenienz";
import { layoutGraph, type LayoutDirection, type ViewNode } from "./layout";
import { nodeTypes } from "./nodes";
import { usePersistedPositions } from "./usePersistedPositions";

interface Props {
  nodes: ProvNode[];
  edges: ProvEdge[];
  /** Session meta — needed to synthesise the Goal tile + position the
   *  Plan-Vorschlag tile relative to the goal. */
  meta?: { session_id: string; goal: string };
  /** When provided, tile positions persist across tab navigations under
   *  this session id. Pass null to disable persistence. */
  sessionId?: string | null;
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
  meta,
  sessionId,
  onSelectView,
  onViewIndex,
}: Props): JSX.Element {
  const [direction, setDirection] = useState<LayoutDirection>("TB");
  const [snap, setSnap] = useState(true);
  const [resetSignal, setResetSignal] = useState(0);
  const lastResetRef = useRef(0);

  const persisted = usePersistedPositions(sessionId ?? null);

  const laid = useMemo(
    () => layoutGraph(nodes, edges, { direction }, meta),
    [nodes, edges, direction, meta],
  );
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState(laid.nodes);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState(laid.edges);

  // Position pipeline:
  //   1. Reset → discard everything; use fresh dagre positions
  //   2. Otherwise: live drag > persisted > dagre. New tiles take dagre's
  //      position, *translated* by the chunk's drag-delta so a new claim
  //      lands relative to where the user moved the chunk, not where dagre
  //      assumed it was. Fixes the "all tiles stack at the top" symptom
  //      after the user drags the root tile away from its dagre default.
  useEffect(() => {
    const isReset = resetSignal > lastResetRef.current;
    lastResetRef.current = resetSignal;
    setRfNodes((prev) => {
      if (isReset) return laid.nodes;
      const livePos = new Map(prev.map((n) => [n.id, n.position]));

      // Compute the offset the user/persisted positions imposed on the
      // chunk root. New tiles will be shifted by the same vector so the
      // whole subtree visually follows the dragged root.
      const root = laid.nodes.find((n) => n.type === "chunk");
      const rootDagre = root?.position ?? { x: 0, y: 0 };
      const rootEffective =
        (root && (livePos.get(root.id) ?? persisted.loaded.get(root.id))) ??
        rootDagre;
      const offset = {
        x: rootEffective.x - rootDagre.x,
        y: rootEffective.y - rootDagre.y,
      };

      return laid.nodes.map((n) => {
        const live = livePos.get(n.id);
        if (live) return { ...n, position: live };
        const persistedPos = persisted.loaded.get(n.id);
        if (persistedPos) return { ...n, position: persistedPos };
        return {
          ...n,
          position: { x: n.position.x + offset.x, y: n.position.y + offset.y },
        };
      });
    });
    setRfEdges(laid.edges);
  }, [
    laid.nodes,
    laid.edges,
    setRfNodes,
    setRfEdges,
    resetSignal,
    persisted.loaded,
  ]);

  // Save positions whenever they change (debounced inside the hook). Gated
  // on persisted.ready so a fresh remount can't write the dagre defaults
  // back to localStorage before the saved positions get loaded.
  useEffect(() => {
    if (!sessionId || !persisted.ready) return;
    const positions = new Map<string, { x: number; y: number }>();
    for (const n of rfNodes) positions.set(n.id, n.position);
    persisted.save(positions);
  }, [rfNodes, sessionId, persisted]);

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
        <Background
          variant={BackgroundVariant.Lines}
          gap={16}
          color="#334155"
          lineWidth={0.5}
        />
        <Controls />
        <MiniMap pannable zoomable nodeColor={() => "#334155"} />
        <Toolbar
          direction={direction}
          onToggleDirection={() =>
            setDirection((d) => (d === "TB" ? "LR" : "TB"))
          }
          snap={snap}
          onToggleSnap={() => setSnap((s) => !s)}
          onReset={() => {
            persisted.clear();
            setResetSignal((n) => n + 1);
          }}
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
  onReset,
}: {
  direction: LayoutDirection;
  onToggleDirection: () => void;
  snap: boolean;
  onToggleSnap: () => void;
  onReset: () => void;
}): JSX.Element {
  const rf = useReactFlow();
  return (
    <div className="absolute top-3 right-3 z-10 flex flex-col gap-1 bg-navy-800/95 border border-navy-600 rounded shadow-md p-1">
      <ToolbarButton
        title="Layout neu berechnen (alle Positionen verwerfen)"
        onClick={() => {
          onReset();
          // fitView lands on the next frame so it sees the new positions.
          setTimeout(() => rf.fitView({ duration: 250, padding: 0.2 }), 16);
        }}
      >
        <RotateCcw className="w-4 h-4" />
      </ToolbarButton>
      <ToolbarButton
        title="An Bildschirm anpassen"
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
