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
 * Static topology of the Provenienz agent. Renders the open-ended
 * "Was als nächstes?" router at top, branching into:
 *   - executable_step: the existing chain of registered steps
 *   - capability_request: currently disabled tools (stubs) the agent
 *     can flag as missing
 *   - manual_review: terminal escalation to a human
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

function buildAgentGraph(info: AgentInfo): { nodes: RfNode[]; edges: RfEdge[] } {
  const COL_X = 320;
  const ROW_DY = 140;
  const ROUTER_Y = -240;
  const BRANCH_Y = -80;

  const nodes: RfNode[] = [];
  const edges: RfEdge[] = [];

  // ── Top: Was als nächstes? router ──────────────────────────────────────────
  nodes.push({
    id: "step:next_step",
    type: "step",
    position: { x: COL_X, y: ROUTER_Y },
    data: {
      step: {
        kind: "next_step",
        label: info.next_step.label,
        input_kind: info.next_step.input_kind,
        output_kind: info.next_step.output_kind,
        uses_llm: info.next_step.uses_llm,
        uses_tool: info.next_step.uses_tool,
        rules: info.next_step.rules,
        system_prompt: info.next_step.system_prompt,
        user_template: "",
        expected_output: info.next_step.expected_output,
      },
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });

  // ── Three branches: executable_step / capability_request / manual_review ──
  const branchExecX = -40;
  const branchCapX = COL_X;
  const branchManX = COL_X + 360;

  nodes.push({
    id: "branch:executable_step",
    type: "data",
    position: { x: branchExecX, y: BRANCH_Y },
    data: { label: "executable_step", sub: "Agent wählt einen Step" },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });
  nodes.push({
    id: "branch:capability_request",
    type: "data",
    position: { x: branchCapX, y: BRANCH_Y },
    data: { label: "capability_request", sub: "Was fehlt? — TODO" },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });
  nodes.push({
    id: "branch:manual_review",
    type: "data",
    position: { x: branchManX, y: BRANCH_Y },
    data: { label: "manual_review", sub: "Eskalation an Mensch" },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });

  edges.push(
    {
      id: "e:next->exec",
      source: "step:next_step",
      target: "branch:executable_step",
      type: "smoothstep",
      style: { stroke: "#fbbf24" },
      label: "passender Step",
      labelStyle: { fontSize: 10, fill: "#fde68a" },
      labelBgStyle: { fill: "#1e293b" },
    },
    {
      id: "e:next->cap",
      source: "step:next_step",
      target: "branch:capability_request",
      type: "smoothstep",
      style: { stroke: "#facc15" },
      label: "kein Step + Tool ausreicht",
      labelStyle: { fontSize: 10, fill: "#fde68a" },
      labelBgStyle: { fill: "#1e293b" },
    },
    {
      id: "e:next->man",
      source: "step:next_step",
      target: "branch:manual_review",
      type: "smoothstep",
      style: { stroke: "#f87171" },
      label: "nur Mensch löst das",
      labelStyle: { fontSize: 10, fill: "#fecaca" },
      labelBgStyle: { fill: "#1e293b" },
    },
  );

  // ── Branch 1: existing executable trunk under branch:executable_step ─────
  const trunkSpec: {
    id: string;
    type: "data" | "step";
    label: string;
    sub?: string;
    kind?: string;
  }[] = [
    {
      id: "data:chunk",
      type: "data",
      label: "Chunk",
      sub: validStepsLabel(info, "chunk"),
    },
    ...info.steps
      .filter((s) => s.kind === "extract_claims")
      .map((s) => ({
        id: `step:${s.kind}`,
        type: "step" as const,
        label: s.label,
        kind: s.kind,
      })),
    {
      id: "data:claim",
      type: "data",
      label: "Claim",
      sub: validStepsLabel(info, "claim"),
    },
    ...info.steps
      .filter((s) => s.kind === "formulate_task")
      .map((s) => ({
        id: `step:${s.kind}`,
        type: "step" as const,
        label: s.label,
        kind: s.kind,
      })),
    {
      id: "data:task",
      type: "data",
      label: "Task",
      sub: validStepsLabel(info, "task"),
    },
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
      sub: validStepsLabel(info, "search_result"),
    },
    ...info.steps
      .filter((s) => s.kind === "evaluate")
      .map((s) => ({
        id: `step:${s.kind}`,
        type: "step" as const,
        label: s.label,
        kind: s.kind,
      })),
    {
      id: "data:evaluation",
      type: "data",
      label: "Evaluation",
      sub: "Verdict + Confidence",
    },
  ];

  trunkSpec.forEach((t, idx) => {
    const y = idx * ROW_DY;
    if (t.type === "data") {
      nodes.push({
        id: t.id,
        type: "data",
        position: { x: branchExecX, y },
        data: { label: t.label, sub: t.sub },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
      });
    } else if (t.kind) {
      const step = info.steps.find((s) => s.kind === t.kind);
      nodes.push({
        id: t.id,
        type: "step",
        position: { x: branchExecX, y },
        data: { step },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
      });
    }
    if (idx === 0) {
      edges.push({
        id: `e:trunk:0`,
        source: "branch:executable_step",
        target: t.id,
        type: "smoothstep",
        style: { stroke: "#475569", strokeWidth: 1.5 },
      });
    } else {
      edges.push({
        id: `e:trunk:${idx}`,
        source: trunkSpec[idx - 1]!.id,
        target: t.id,
        type: "smoothstep",
        style: { stroke: "#475569", strokeWidth: 1.5 },
      });
    }
  });

  // ── Branch 2: capability_request — list disabled tools as candidates ─────
  const disabledTools = info.tools.filter((t) => !t.enabled);
  disabledTools.forEach((tool, idx) => {
    const toolId = `tool:${tool.name}`;
    nodes.push({
      id: toolId,
      type: "tool",
      position: { x: branchCapX, y: idx * 130 + 40 },
      data: { tool },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    });
    edges.push({
      id: `e:cap-stub:${tool.name}`,
      source: "branch:capability_request",
      target: toolId,
      type: "smoothstep",
      style: { stroke: "#facc15", strokeDasharray: "4 4" },
    });
  });

  // Show the active tools too — they hang off the search step in the
  // executable trunk.
  const enabledTools = info.tools.filter((t) => t.enabled);
  enabledTools.forEach((tool) => {
    const consumerStep = tool.used_by[0];
    const stepId = `step:${consumerStep}`;
    const stepNode = nodes.find((n) => n.id === stepId);
    if (!stepNode) return;
    const toolId = `tool:${tool.name}`;
    nodes.push({
      id: toolId,
      type: "tool",
      position: { x: branchExecX - 320, y: stepNode.position.y },
      data: { tool },
      sourcePosition: Position.Right,
      targetPosition: Position.Right,
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

  // ── Branch 3: manual_review — single terminal tile ────────────────────────
  nodes.push({
    id: "data:manual_review",
    type: "data",
    position: { x: branchManX, y: 40 },
    data: {
      label: "👤 Mensch erledigt",
      sub: "User markiert das Tile als erledigt — kein Auto-Step.",
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });
  edges.push({
    id: "e:branch-man-tile",
    source: "branch:manual_review",
    target: "data:manual_review",
    type: "smoothstep",
    style: { stroke: "#f87171", strokeDasharray: "4 4" },
  });

  // ── Promote loop (existing): search_result → promote → chunk ──────────────
  const promoteStep = info.steps.find(
    (s) => s.kind === "promote_search_result",
  );
  if (promoteStep) {
    const sr = nodes.find((n) => n.id === "data:search_result");
    if (sr) {
      nodes.push({
        id: "step:promote_search_result",
        type: "step",
        position: { x: branchExecX + 360, y: sr.position.y },
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
        label: "neuer Chunk + Kontext",
        labelStyle: { fontSize: 10, fill: "#c4b5fd" },
        labelBgStyle: { fill: "#1e293b" },
      });
    }
  }

  // ── Stop step (still hangs off claim, jederzeit) ──────────────────────────
  const stopStep = info.steps.find((s) => s.kind === "propose_stop");
  if (stopStep) {
    const claim = nodes.find((n) => n.id === "data:claim");
    if (claim) {
      nodes.push({
        id: "step:propose_stop",
        type: "step",
        position: { x: branchExecX - 320, y: claim.position.y + 80 },
        data: { step: stopStep },
        sourcePosition: Position.Right,
        targetPosition: Position.Right,
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
    }
  }

  return { nodes, edges };
}

/**
 * Format the registered next-step options for an anchor kind into a
 * one-line label that hangs under the data tile. Tells the user
 * exactly what the agent considers valid at this kind of node.
 */
function validStepsLabel(info: AgentInfo, anchorKind: string): string {
  const steps = info.valid_steps_per_anchor?.[anchorKind] ?? [];
  if (steps.length === 0) return "(kein Step registriert)";
  return `Optionen: ${steps.join(" · ")}`;
}
