import { useMemo } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Position,
  type Edge as RfEdge,
  type Node as RfNode,
} from "reactflow";
import "reactflow/dist/style.css";

import type { AgentInfo } from "../hooks/useProvenienz";
import { AgentDataNode, AgentStepNode, AgentToolNode } from "./nodes/agent";

const nodeTypes = {
  data: AgentDataNode,
  step: AgentStepNode,
  tool: AgentToolNode,
};

interface Props {
  info: AgentInfo;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

/**
 * Static topology of the Provenienz agent. Coordinates are hard-coded —
 * there's no dynamic graph here, just a fixed flowchart of the seven
 * step kinds + their data shapes + the InDocSearcher tool.
 *
 * Click a step → side panel renders the step's prompt, rules, expected
 * output. Click a tool → tool details. Click a data tile → its kind +
 * which steps consume / produce it.
 */
export function AgentCanvas({ info, selectedId, onSelect }: Props): JSX.Element {
  const { nodes, edges } = useMemo(() => buildAgentGraph(info), [info]);
  return (
    <div className="w-full h-full bg-navy-900 relative">
      <ReactFlow
        nodes={nodes.map((n) => ({
          ...n,
          selected: n.id === selectedId,
        }))}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_e, n) => onSelect(n.id)}
        onPaneClick={() => onSelect(null)}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        fitView
        fitViewOptions={{ padding: 0.15 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={16}
          color="#334155"
          size={1}
        />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable nodeColor={() => "#475569"} />
      </ReactFlow>
    </div>
  );
}

/**
 * Hand-laid-out coordinates. The trunk runs vertically (y increases
 * downwards); the search → evaluate fork branches sideways. Tool nodes
 * sit to the right of the steps that use them.
 */
function buildAgentGraph(info: AgentInfo): { nodes: RfNode[]; edges: RfEdge[] } {
  const COL_X = 320; // trunk
  const TOOL_X = 720; // tool column right of trunk
  const ROW_DY = 140;

  const nodes: RfNode[] = [];
  const edges: RfEdge[] = [];

  // Trunk: chunk → extract → claim → formulate → task → search → bag
  // Then bag forks: evaluate → evaluation, and promote → loops back to chunk
  const trunk: { id: string; type: "data" | "step"; label: string; sub?: string; kind?: string }[] =
    [
      { id: "data:chunk", type: "data", label: "Chunk", sub: "Quell-Textabschnitt" },
      ...info.steps
        .filter((s) => s.kind === "extract_claims")
        .map((s) => ({
          id: `step:${s.kind}`,
          type: "step" as const,
          label: s.label,
          kind: s.kind,
        })),
      { id: "data:claim", type: "data", label: "Claim", sub: "Überprüfbare Aussage" },
      ...info.steps
        .filter((s) => s.kind === "formulate_task")
        .map((s) => ({
          id: `step:${s.kind}`,
          type: "step" as const,
          label: s.label,
          kind: s.kind,
        })),
      { id: "data:task", type: "data", label: "Task", sub: "Suchanfrage" },
      ...info.steps
        .filter((s) => s.kind === "search")
        .map((s) => ({
          id: `step:${s.kind}`,
          type: "step" as const,
          label: s.label,
          kind: s.kind,
        })),
      {
        id: "data:search_result",
        type: "data",
        label: "Search Results",
        sub: "Kandidaten aus dem Korpus",
      },
      ...info.steps
        .filter((s) => s.kind === "evaluate")
        .map((s) => ({
          id: `step:${s.kind}`,
          type: "step" as const,
          label: s.label,
          kind: s.kind,
        })),
      { id: "data:evaluation", type: "data", label: "Evaluation", sub: "Verdict + Confidence" },
    ];

  trunk.forEach((t, idx) => {
    const y = idx * ROW_DY;
    if (t.type === "data") {
      nodes.push({
        id: t.id,
        type: "data",
        position: { x: COL_X, y },
        data: { label: t.label, sub: t.sub },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
      });
    } else if (t.kind) {
      const step = info.steps.find((s) => s.kind === t.kind);
      nodes.push({
        id: t.id,
        type: "step",
        position: { x: COL_X, y },
        data: { step },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
      });
    }
    if (idx > 0) {
      edges.push({
        id: `e:trunk:${idx}`,
        source: trunk[idx - 1]!.id,
        target: t.id,
        type: "smoothstep",
        style: { stroke: "#475569", strokeWidth: 1.5 },
      });
    }
  });

  // Side: propose_stop step (orphan-ish, anchored to claim or any)
  const stopStep = info.steps.find((s) => s.kind === "propose_stop");
  if (stopStep) {
    nodes.push({
      id: "step:propose_stop",
      type: "step",
      position: { x: -240, y: 2 * ROW_DY }, // left of claim
      data: { step: stopStep },
      sourcePosition: Position.Right,
      targetPosition: Position.Right,
    });
    nodes.push({
      id: "data:stop_proposal",
      type: "data",
      position: { x: -240, y: 2 * ROW_DY + ROW_DY / 2 + 20 },
      data: { label: "Stop Proposal", sub: "Branch geschlossen" },
      sourcePosition: Position.Right,
      targetPosition: Position.Top,
    });
    edges.push({
      id: "e:claim->stop",
      source: "data:claim",
      target: "step:propose_stop",
      type: "smoothstep",
      style: { stroke: "#64748b", strokeDasharray: "4 4" },
      label: "jederzeit",
      labelStyle: { fontSize: 10, fill: "#94a3b8" },
      labelBgStyle: { fill: "#1e293b" },
    });
    edges.push({
      id: "e:stop->prop",
      source: "step:propose_stop",
      target: "data:stop_proposal",
      type: "smoothstep",
      style: { stroke: "#64748b" },
    });
  }

  // Side: promote_search_result step (loops back to chunk)
  const promoteStep = info.steps.find((s) => s.kind === "promote_search_result");
  if (promoteStep) {
    const promoteY = 6 * ROW_DY; // around search_result row
    nodes.push({
      id: "step:promote_search_result",
      type: "step",
      position: { x: TOOL_X + 80, y: promoteY },
      data: { step: promoteStep },
      sourcePosition: Position.Top,
      targetPosition: Position.Left,
    });
    edges.push({
      id: "e:result->promote",
      source: "data:search_result",
      target: "step:promote_search_result",
      type: "smoothstep",
      style: { stroke: "#a855f7" },
      label: "Weiter erforschen",
      labelStyle: { fontSize: 10, fill: "#c4b5fd" },
      labelBgStyle: { fill: "#1e293b" },
    });
    edges.push({
      id: "e:promote->chunk",
      source: "step:promote_search_result",
      target: "data:chunk",
      type: "smoothstep",
      style: { stroke: "#a855f7", strokeDasharray: "6 4" },
      label: "neuer Chunk + Recherche-Kontext",
      labelStyle: { fontSize: 10, fill: "#c4b5fd" },
      labelBgStyle: { fill: "#1e293b" },
    });
  }

  // Tools column — only enabled tools render on the canvas. Disabled stubs
  // live in the "Verfügbare Werkzeuge" registry section in the right pane,
  // which keeps the topology readable while still surfacing dormant capabilities.
  const enabledTools = info.tools.filter((t) => t.enabled);
  enabledTools.forEach((tool, idx) => {
    const consumerStep = tool.used_by[0];
    const stepId = `step:${consumerStep}`;
    const stepNode = nodes.find((n) => n.id === stepId);
    const y = stepNode?.position.y ?? idx * ROW_DY;
    const toolId = `tool:${tool.name}`;
    nodes.push({
      id: toolId,
      type: "tool",
      position: { x: TOOL_X, y },
      data: { tool },
      sourcePosition: Position.Left,
      targetPosition: Position.Left,
    });
    edges.push({
      id: `e:tool:${tool.name}`,
      source: stepId,
      target: toolId,
      type: "smoothstep",
      style: { stroke: "#10b981" },
      label: "ruft auf",
      labelStyle: { fontSize: 10, fill: "#6ee7b7" },
      labelBgStyle: { fill: "#1e293b" },
    });
  });

  return { nodes, edges };
}
