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
 * Layout B (revised): orchestrator-centric topology with strict
 * vertical bands and ample horizontal padding so no two cards overlap
 * and every edge has a clear source/target.
 *
 *  band 0 (top)        ORCHESTRATOR
 *  band 1              wählt-aus classification (3 branches)
 *  band 2              SUB-AGENT row 1 (canonical pipeline)
 *  band 3              SUB-AGENT row 2 (terminal / branch-off)
 *  band 4 (bottom)     data flow strip (Chunk -> ... -> Evaluation)
 *
 *  Side columns:
 *    far left   manual_review tile
 *    far right  capability_request stub tools
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
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.15}
        maxZoom={1.8}
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

// Vertical bands. Each band is wide enough to fit a sub-agent card
// (~320px tall when all pills are present) with ~120px clearance to
// the next band.
const BAND_ORCH_Y = 0;
const BAND_BRANCH_Y = 320;
const BAND_SUBAGENT_ROW1_Y = 640;
const BAND_SUBAGENT_ROW2_Y = 1100;
const BAND_DATAFLOW_Y = 1560;

// Horizontal layout. Sub-agent cards are 288px wide; with a 420px gap
// between centres no two cards overlap horizontally, including their
// children pills which line-wrap inside the card.
const SUBAGENT_GAP_X = 420;
const SUBAGENT_CARD_WIDTH = 288;

// Side columns sit far enough left/right of the central executable
// trunk that capability_request stubs and manual_review never cross
// into sub-agent territory.
const SIDE_COLUMN_OFFSET = 1400;

function buildAgentGraph(
  info: AgentInfo,
  onPillClick: (id: string) => void,
): { nodes: RfNode[]; edges: RfEdge[] } {
  const nodes: RfNode[] = [];
  const edges: RfEdge[] = [];

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

  const registered = new Set(info.steps.map((s) => s.kind));
  const presentRow1 = ROW1_KINDS.filter((k) => registered.has(k));
  const presentRow2 = ROW2_KINDS.filter((k) => registered.has(k));

  const activeSkillsCount = new Set(
    info.steps.flatMap((s) => s.rules ?? []),
  ).size;

  // ── 1) Orchestrator (band 0) — centred on the executable trunk axis.
  const TRUNK_X = 0;
  nodes.push({
    id: "step:next_step",
    type: "orchestrator",
    position: { x: TRUNK_X - 160, y: BAND_ORCH_Y },
    data: {
      label: info.next_step.label,
      subagent_count: presentRow1.length + presentRow2.length,
      active_skills_count: activeSkillsCount,
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });

  // ── 2) Classification branches (band 1) — three options the
  //      orchestrator returns. exec lives on the trunk axis; cap_req
  //      and manual_review live on the side columns.
  const branchExecX = TRUNK_X - 100;
  const branchCapX = TRUNK_X + SIDE_COLUMN_OFFSET;
  const branchManX = TRUNK_X - SIDE_COLUMN_OFFSET;

  nodes.push({
    id: "branch:executable_step",
    type: "data",
    position: { x: branchExecX, y: BAND_BRANCH_Y },
    data: {
      label: "executable_step",
      sub: "Sub-Agent wählen",
    },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
  });
  nodes.push({
    id: "branch:capability_request",
    type: "data",
    position: { x: branchCapX, y: BAND_BRANCH_Y },
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
    position: { x: branchManX, y: BAND_BRANCH_Y },
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
      style: { stroke: "#fbbf24", strokeWidth: 2.5 },
      label: "passender Sub-Agent",
      labelStyle: { fontSize: 11, fill: "#fde68a", fontWeight: 600 },
      labelBgStyle: { fill: "#1e293b" },
    },
    {
      id: "e:orch->cap",
      source: "step:next_step",
      target: "branch:capability_request",
      type: "smoothstep",
      style: { stroke: "#facc15", strokeDasharray: "4 4", strokeWidth: 1.5 },
      label: "kein passendes Tool",
      labelStyle: { fontSize: 11, fill: "#fde68a" },
      labelBgStyle: { fill: "#1e293b" },
    },
    {
      id: "e:orch->man",
      source: "step:next_step",
      target: "branch:manual_review",
      type: "smoothstep",
      style: { stroke: "#f87171", strokeDasharray: "4 4", strokeWidth: 1.5 },
      label: "nur Mensch löst das",
      labelStyle: { fontSize: 11, fill: "#fecaca" },
      labelBgStyle: { fill: "#1e293b" },
    },
  );

  // ── 3) Sub-agent rows (bands 2 + 3). Row 1 = canonical pipeline,
  //      Row 2 = terminal / branch-off. Each card carries its own
  //      Skill + Tool pills inline; the edges from executable_step
  //      use distinct colours so the reader can trace which sub-agent
  //      the orchestrator picked.
  const placeSubAgent = (
    kind: string,
    x: number,
    y: number,
    edgeStyle: React.CSSProperties,
  ): void => {
    const step = info.steps.find((s) => s.kind === kind);
    if (!step) return;
    const tools = info.tools.filter((t) => t.used_by.includes(kind));
    nodes.push({
      id: `step:${kind}`,
      type: "subagent",
      position: { x, y },
      data: { step, tools, onPillClick },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
    });
    edges.push({
      id: `e:exec->${kind}`,
      source: "branch:executable_step",
      target: `step:${kind}`,
      type: "smoothstep",
      style: edgeStyle,
    });
  };

  const row1Width = (presentRow1.length - 1) * SUBAGENT_GAP_X;
  const row1XStart = TRUNK_X - row1Width / 2 - SUBAGENT_CARD_WIDTH / 2;
  presentRow1.forEach((kind, idx) => {
    placeSubAgent(
      kind,
      row1XStart + idx * SUBAGENT_GAP_X,
      BAND_SUBAGENT_ROW1_Y,
      { stroke: "#fbbf24", strokeWidth: 1.8 },
    );
  });

  const row2Width = (presentRow2.length - 1) * SUBAGENT_GAP_X;
  const row2XStart = TRUNK_X - row2Width / 2 - SUBAGENT_CARD_WIDTH / 2;
  presentRow2.forEach((kind, idx) => {
    placeSubAgent(
      kind,
      row2XStart + idx * SUBAGENT_GAP_X,
      BAND_SUBAGENT_ROW2_Y,
      { stroke: "#a78bfa", strokeDasharray: "6 4", strokeWidth: 1.4 },
    );
  });

  // ── 4) Pipeline data-flow strip (band 4). Linear, grey-on-grey so
  //      it reads as 'secondary documentation' under the sub-agents.
  const DATA_NODE_WIDTH = 224;
  const dataLabels: Array<{ id: string; label: string; sub: string }> = [
    { id: "data:chunk", label: "Chunk", sub: validStepsLabel(info, "chunk") },
    { id: "data:claim", label: "Claim", sub: validStepsLabel(info, "claim") },
    { id: "data:task", label: "Task", sub: validStepsLabel(info, "task") },
    {
      id: "data:search_result",
      label: "Search Result",
      sub: validStepsLabel(info, "search_result"),
    },
    {
      id: "data:evaluation",
      label: "Evaluation",
      sub: "Verdict + Konfidenz",
    },
  ];
  const dataFlowWidth = (dataLabels.length - 1) * SUBAGENT_GAP_X;
  const dataFlowXStart = TRUNK_X - dataFlowWidth / 2 - DATA_NODE_WIDTH / 2;
  dataLabels.forEach((d, idx) => {
    nodes.push({
      id: d.id,
      type: "data",
      position: {
        x: dataFlowXStart + idx * SUBAGENT_GAP_X,
        y: BAND_DATAFLOW_Y,
      },
      data: { label: d.label, sub: d.sub },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    });
  });
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

  // ── 5) capability_request stubs — vertical stack on the right column.
  const disabledTools = info.tools.filter((t) => !t.enabled);
  const CAP_TOOL_GAP_Y = 200;
  disabledTools.forEach((tool: AgentToolInfo, idx: number) => {
    const toolId = `tool:${tool.name}`;
    nodes.push({
      id: toolId,
      type: "tool",
      position: {
        x: branchCapX,
        y: BAND_SUBAGENT_ROW1_Y + idx * CAP_TOOL_GAP_Y,
      },
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

  // ── 6) manual_review terminal — far-left column.
  nodes.push({
    id: "data:manual_review",
    type: "data",
    position: { x: branchManX, y: BAND_SUBAGENT_ROW1_Y },
    data: {
      label: "👤 Mensch erledigt",
      sub: "User markiert das Tile als erledigt.",
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
