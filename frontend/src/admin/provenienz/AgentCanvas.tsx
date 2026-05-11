import { useCallback, useMemo } from "react";
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

import type { AgentInfo, AgentToolInfo } from "../hooks/useProvenienz";
import {
  AgentDataNode,
  AgentOrchestratorNode,
  AgentStepNode,
  AgentSubAgentNode,
  AgentToolNode,
} from "./nodes/agent";

const nodeTypes = {
  data: AgentDataNode,
  step: AgentStepNode,
  subagent: AgentSubAgentNode,
  orchestrator: AgentOrchestratorNode,
  tool: AgentToolNode,
};

interface Props {
  info: AgentInfo;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

/**
 * Layout B: orchestrator-centric topology.
 *
 *   [ORCHESTRATOR — Was als naechstes?]
 *           |
 *      wählt aus
 *     /    |    \
 *  [exec] [cap_req] [manual_review]
 *   |        |          |
 *  the     stub      terminal
 *  six     tools     (Mensch)
 *  sub-
 *  agents
 *
 * Each sub-agent card carries its Skill + Tool pills inline so the
 * reader sees 'orchestrator -> chooses sub-agent -> uses these skills
 * and tools' at one glance. Pipeline data-flow is rendered as
 * desaturated dashed edges along the bottom — useful but secondary.
 */
export function AgentCanvas({ info, selectedId, onSelect }: Props): JSX.Element {
  const onPillClick = useCallback(
    (id: string) => onSelect(id),
    [onSelect],
  );
  const { nodes, edges } = useMemo(
    () => buildAgentGraph(info, onPillClick),
    [info, onPillClick],
  );
  return (
    <div className="w-full h-full bg-navy-900 relative">
      <ReactFlow
        nodes={nodes.map((n) => ({ ...n, selected: n.id === selectedId }))}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_e, n) => onSelect(n.id)}
        onPaneClick={() => onSelect(null)}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        fitView
        fitViewOptions={{ padding: 0.18 }}
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

function buildAgentGraph(
  info: AgentInfo,
  onPillClick: (id: string) => void,
): { nodes: RfNode[]; edges: RfEdge[] } {
  const nodes: RfNode[] = [];
  const edges: RfEdge[] = [];

  // Sub-agents to surface as primary tiles. Order matters: row 1 is the
  // canonical research pipeline (linear data-flow), row 2 carries the
  // branch-off / terminal steps.
  const ROW1_KINDS = [
    "extract_claims",
    "formulate_task",
    "search",
    "evaluate",
  ];
  const ROW2_KINDS = [
    "promote_search_result",
    "investigate_table",
    "propose_stop",
  ];

  const allRegisteredKinds = new Set(info.steps.map((s) => s.kind));
  const presentRow1 = ROW1_KINDS.filter((k) => allRegisteredKinds.has(k));
  const presentRow2 = ROW2_KINDS.filter((k) => allRegisteredKinds.has(k));

  // Active skills across all sub-agents — surfaced on the orchestrator
  // badge so the user sees the system-prompt extension scale at a
  // glance without opening individual sub-agents.
  const activeSkillsCount = new Set(
    info.steps.flatMap((s) => s.rules ?? []),
  ).size;

  // ── 1) Orchestrator (top centre) ─────────────────────────────────────────
  const ORCH_X = 0;
  const ORCH_Y = -360;
  nodes.push({
    id: "step:next_step",
    type: "orchestrator",
    position: { x: ORCH_X, y: ORCH_Y },
    data: {
      label: info.next_step.label,
      subagent_count: presentRow1.length + presentRow2.length,
      active_skills_count: activeSkillsCount,
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });

  // ── 2) Three classification branches (executable / capability / manual) ──
  const BRANCH_Y = ORCH_Y + 180;
  const BRANCH_GAP = 360;
  const branchExecX = ORCH_X;
  const branchCapX = ORCH_X + BRANCH_GAP;
  const branchManX = ORCH_X - BRANCH_GAP;

  nodes.push({
    id: "branch:executable_step",
    type: "data",
    position: { x: branchExecX, y: BRANCH_Y },
    data: {
      label: "executable_step",
      sub: "wählt einen Sub-Agent aus der Liste",
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });
  nodes.push({
    id: "branch:capability_request",
    type: "data",
    position: { x: branchCapX, y: BRANCH_Y },
    data: {
      label: "capability_request",
      sub: "Tool fehlt im Registry",
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });
  nodes.push({
    id: "branch:manual_review",
    type: "data",
    position: { x: branchManX, y: BRANCH_Y },
    data: {
      label: "manual_review",
      sub: "Mensch entscheidet",
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });

  edges.push(
    {
      id: "e:orch->exec",
      source: "step:next_step",
      target: "branch:executable_step",
      type: "smoothstep",
      style: { stroke: "#fbbf24", strokeWidth: 2 },
      label: "passender Sub-Agent existiert",
      labelStyle: { fontSize: 10, fill: "#fde68a" },
      labelBgStyle: { fill: "#1e293b" },
    },
    {
      id: "e:orch->cap",
      source: "step:next_step",
      target: "branch:capability_request",
      type: "smoothstep",
      style: { stroke: "#facc15", strokeDasharray: "4 4" },
      label: "kein Tool deckt das ab",
      labelStyle: { fontSize: 10, fill: "#fde68a" },
      labelBgStyle: { fill: "#1e293b" },
    },
    {
      id: "e:orch->man",
      source: "step:next_step",
      target: "branch:manual_review",
      type: "smoothstep",
      style: { stroke: "#f87171", strokeDasharray: "4 4" },
      label: "nur Mensch löst das",
      labelStyle: { fontSize: 10, fill: "#fecaca" },
      labelBgStyle: { fill: "#1e293b" },
    },
  );

  // ── 3) Sub-agent rows below executable_step branch ───────────────────────
  const SUBAGENT_GAP_X = 320;
  const SUBAGENT_ROW1_Y = BRANCH_Y + 240;
  const SUBAGENT_ROW2_Y = SUBAGENT_ROW1_Y + 360;

  const placeSubAgent = (
    kind: string,
    x: number,
    y: number,
  ): RfNode | null => {
    const step = info.steps.find((s) => s.kind === kind);
    if (!step) return null;
    const tools = info.tools.filter((t) => t.used_by.includes(kind));
    const node: RfNode = {
      id: `step:${kind}`,
      type: "subagent",
      position: { x, y },
      data: { step, tools, onPillClick },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    };
    nodes.push(node);
    return node;
  };

  const row1XStart = branchExecX - ((presentRow1.length - 1) * SUBAGENT_GAP_X) / 2;
  presentRow1.forEach((kind, idx) => {
    const x = row1XStart + idx * SUBAGENT_GAP_X;
    placeSubAgent(kind, x, SUBAGENT_ROW1_Y);
    edges.push({
      id: `e:exec->${kind}`,
      source: "branch:executable_step",
      target: `step:${kind}`,
      type: "smoothstep",
      style: { stroke: "#fbbf24", strokeWidth: 1.5 },
    });
  });

  const row2XStart = branchExecX - ((presentRow2.length - 1) * SUBAGENT_GAP_X) / 2;
  presentRow2.forEach((kind, idx) => {
    const x = row2XStart + idx * SUBAGENT_GAP_X;
    placeSubAgent(kind, x, SUBAGENT_ROW2_Y);
    edges.push({
      id: `e:exec->${kind}`,
      source: "branch:executable_step",
      target: `step:${kind}`,
      type: "smoothstep",
      style: { stroke: "#fbbf24", strokeDasharray: "4 4", strokeWidth: 1.2 },
    });
  });

  // ── 4) Pipeline data-flow below row 1 (desaturated, secondary) ───────────
  // Renders Chunk -> Claim -> Task -> Search Results -> Evaluation as small
  // grey labels with dashed arrows so the reader sees 'this is the data
  // shape between sub-agents'. The orchestrator->sub-agent edges remain
  // the primary visual.
  const DATA_FLOW_Y = SUBAGENT_ROW1_Y + 280;
  const dataLabels: Array<{ id: string; label: string; x: number }> = [
    { id: "data:chunk", label: "Chunk", x: row1XStart - 160 },
    {
      id: "data:claim",
      label: "Claim",
      x: row1XStart - 160 + SUBAGENT_GAP_X,
    },
    {
      id: "data:task",
      label: "Task",
      x: row1XStart - 160 + SUBAGENT_GAP_X * 2,
    },
    {
      id: "data:search_result",
      label: "Search Result",
      x: row1XStart - 160 + SUBAGENT_GAP_X * 3,
    },
    {
      id: "data:evaluation",
      label: "Evaluation",
      x: row1XStart - 160 + SUBAGENT_GAP_X * 4,
    },
  ];
  dataLabels.forEach((d) => {
    nodes.push({
      id: d.id,
      type: "data",
      position: { x: d.x, y: DATA_FLOW_Y },
      data: {
        label: d.label,
        sub: validStepsLabel(info, d.label.toLowerCase().replace(" ", "_")),
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    });
  });
  // Linear data-flow arrows along the bottom row.
  for (let i = 0; i < dataLabels.length - 1; i++) {
    edges.push({
      id: `e:flow:${i}`,
      source: dataLabels[i]!.id,
      target: dataLabels[i + 1]!.id,
      type: "smoothstep",
      style: { stroke: "#475569", strokeDasharray: "3 3", strokeWidth: 1 },
      label: "→",
      labelStyle: { fontSize: 10, fill: "#94a3b8" },
      labelBgStyle: { fill: "#1e293b" },
    });
  }

  // ── 5) capability_request: list disabled tools as candidate stubs ────────
  const disabledTools = info.tools.filter((t) => !t.enabled);
  const CAP_TOOL_Y = SUBAGENT_ROW1_Y;
  const CAP_TOOL_GAP_Y = 130;
  disabledTools.forEach((tool: AgentToolInfo, idx: number) => {
    const toolId = `tool:${tool.name}`;
    nodes.push({
      id: toolId,
      type: "tool",
      position: { x: branchCapX, y: CAP_TOOL_Y + idx * CAP_TOOL_GAP_Y },
      data: { tool },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    });
    edges.push({
      id: `e:cap-stub:${tool.name}`,
      source: "branch:capability_request",
      target: toolId,
      type: "smoothstep",
      style: { stroke: "#facc15", strokeDasharray: "4 4", strokeWidth: 1.2 },
    });
  });

  // ── 6) manual_review terminal ────────────────────────────────────────────
  nodes.push({
    id: "data:manual_review",
    type: "data",
    position: { x: branchManX, y: SUBAGENT_ROW1_Y },
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

  return { nodes, edges };
}

function validStepsLabel(info: AgentInfo, anchorKind: string): string {
  const steps = info.valid_steps_per_anchor?.[anchorKind] ?? [];
  if (steps.length === 0) return "";
  return `Optionen: ${steps.join(" · ")}`;
}
