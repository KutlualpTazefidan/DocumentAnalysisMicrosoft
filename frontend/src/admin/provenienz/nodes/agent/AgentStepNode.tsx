import { Brain, Lightbulb, Search } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { AgentStepInfo } from "../../../hooks/useProvenienz";

const STEP_ICON: Record<string, typeof Brain> = {
  extract_claims: Lightbulb,
  formulate_task: Search,
  search: Search,
  evaluate: Brain,
  propose_stop: Lightbulb,
  promote_search_result: Lightbulb,
};

const STEP_COLOR: Record<string, string> = {
  extract_claims: "bg-amber-50 border-amber-500",
  formulate_task: "bg-cyan-50 border-cyan-500",
  search: "bg-emerald-50 border-emerald-500",
  evaluate: "bg-rose-50 border-rose-500",
  propose_stop: "bg-zinc-100 border-zinc-300",
  promote_search_result: "bg-purple-50 border-purple-500",
};

/**
 * Step tile in the agent topology. Shows kind label + LLM/Tool/Rule
 * badges so the user sees at-a-glance which steps call the LLM, which
 * call a tool, and which consult guidance rules.
 */
export function AgentStepNode({
  data,
  selected,
}: NodeProps<{ step: AgentStepInfo }>): JSX.Element {
  const step = data.step;
  const Icon = STEP_ICON[step.kind] ?? Brain;
  const color = STEP_COLOR[step.kind] ?? "bg-blue-50 border-blue-500";
  return (
    <div
      className={`prov-tile px-4 py-2 w-56 border-2 ${color} ${
        selected ? "ring-2 ring-blue-400/60" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <Handle type="target" position={Position.Right} className="opacity-0" id="rt" />
      <Handle type="target" position={Position.Left} className="opacity-0" id="lt" />
      <header className="flex items-center gap-1.5">
        <Icon className="w-4 h-4" aria-hidden />
        <p className="text-[10px] uppercase tracking-wide text-ink-muted">Schritt</p>
      </header>
      <p className="text-sm font-semibold mt-0.5">{step.label}</p>
      <p className="text-[11px] text-ink-muted mt-0.5">
        {step.input_kind} → {step.output_kind}
      </p>
      <div className="flex flex-wrap gap-1 mt-1.5">
        {step.uses_llm && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/70 border border-line uppercase tracking-wide">
            🧠 LLM
          </span>
        )}
        {step.uses_tool && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/70 border border-line uppercase tracking-wide">
            🔧 {step.uses_tool}
          </span>
        )}
        {step.rules.length > 0 && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/70 border border-line uppercase tracking-wide">
            🛡 {step.rules.length} Regel{step.rules.length === 1 ? "" : "n"}
          </span>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
      <Handle type="source" position={Position.Right} className="opacity-0" id="rs" />
      <Handle type="source" position={Position.Left} className="opacity-0" id="ls" />
    </div>
  );
}
