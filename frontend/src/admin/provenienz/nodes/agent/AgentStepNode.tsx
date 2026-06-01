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
  extract_claims: "bg-amber-700 border-amber-400",
  formulate_task: "bg-cyan-800 border-cyan-400",
  search: "bg-emerald-800 border-emerald-400",
  evaluate: "bg-rose-800 border-rose-400",
  propose_stop: "bg-zinc-700 border-zinc-400",
  promote_search_result: "bg-purple-800 border-purple-400",
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
  const color = STEP_COLOR[step.kind] ?? "bg-blue-800 border-blue-400";
  return (
    <div
      className={`rounded-lg px-4 py-2 text-white shadow-md w-56 border-2 ${color} ${
        selected ? "ring-2 ring-white/60" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <Handle type="target" position={Position.Right} className="opacity-0" id="rt" />
      <Handle type="target" position={Position.Left} className="opacity-0" id="lt" />
      <header className="flex items-center gap-1.5">
        <Icon className="w-4 h-4" aria-hidden />
        <p className="text-[10px] uppercase tracking-wide text-white/80">Schritt</p>
      </header>
      <p className="text-sm font-semibold mt-0.5">{step.label}</p>
      <p className="text-[11px] text-white/75 mt-0.5">
        {step.input_kind} → {step.output_kind}
      </p>
      <div className="flex flex-wrap gap-1 mt-1.5">
        {step.uses_llm && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/15 uppercase tracking-wide">
            🧠 LLM
          </span>
        )}
        {step.uses_tool && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/15 uppercase tracking-wide">
            🔧 {step.uses_tool}
          </span>
        )}
        {step.rules.length > 0 && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/15 uppercase tracking-wide">
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
