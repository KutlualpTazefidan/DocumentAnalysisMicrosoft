import { useEffect, useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState,
} from "reactflow";
import "reactflow/dist/style.css";

import type { ProvEdge, ProvNode } from "../hooks/useProvenienz";
import { layoutGraph } from "./layout";
import { nodeTypes } from "./nodes";

interface Props {
  nodes: ProvNode[];
  edges: ProvEdge[];
  onSelectNode?: (nodeId: string | null) => void;
}

/**
 * React-Flow wrapper. Receives backend nodes + edges, computes a dagre layout,
 * and feeds the result to React-Flow with the kind-keyed `nodeTypes` registry.
 *
 * Wrap with <ReactFlowProvider> when used together with viewport hooks elsewhere.
 */
export function Canvas({ nodes, edges, onSelectNode }: Props): JSX.Element {
  const laid = useMemo(() => layoutGraph(nodes, edges), [nodes, edges]);
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState(laid.nodes);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState(laid.edges);

  useEffect(() => {
    setRfNodes(laid.nodes);
    setRfEdges(laid.edges);
  }, [laid.nodes, laid.edges, setRfNodes, setRfEdges]);

  return (
    <div className="w-full h-full bg-navy-900">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_e, n) => onSelectNode?.(n.id)}
        onPaneClick={() => onSelectNode?.(null)}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} color="#1e293b" />
        <Controls />
        <MiniMap pannable zoomable nodeColor={() => "#334155"} />
      </ReactFlow>
    </div>
  );
}
