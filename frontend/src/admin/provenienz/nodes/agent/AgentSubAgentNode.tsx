import { Brain, Lightbulb, Microscope, Search, type LucideIcon } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { AgentStepInfo, AgentToolInfo } from "../../../hooks/useProvenienz";

const STEP_ICON: Record<string, LucideIcon> = {
  extract_claims: Lightbulb,
  formulate_task: Search,
  search: Search,
  evaluate: Brain,
  propose_stop: Lightbulb,
  promote_search_result: Lightbulb,
  investigate_table: Microscope,
};

const STEP_ACCENT: Record<string, string> = {
  extract_claims: "from-amber-800 to-amber-900 border-amber-400",
  formulate_task: "from-cyan-800 to-cyan-900 border-cyan-400",
  search: "from-emerald-800 to-emerald-900 border-emerald-400",
  evaluate: "from-rose-800 to-rose-900 border-rose-400",
  propose_stop: "from-zinc-700 to-zinc-800 border-zinc-400",
  promote_search_result: "from-purple-800 to-purple-900 border-purple-400",
  investigate_table: "from-cyan-700 to-teal-900 border-teal-400",
};

interface SubAgentData {
  step: AgentStepInfo;
  /** Tools registered for this sub-agent's step kind (info.tools
   *  filtered by used_by includes step.kind). Pills are clickable
   *  to drill into the tool inspector. */
  tools: AgentToolInfo[];
  /** onClick handler to bubble pill selections up to the canvas so
   *  selecting a skill/tool pill loads its detail in the inspector
   *  instead of opening the parent sub-agent. */
  onPillClick?: (id: string) => void;
}

/**
 * Sub-agent tile for layout B. Shows the step's identity (icon, label,
 * I/O kinds, LLM hint) plus inline Skill + Tool pills so the viewer
 * sees at a glance "what does this sub-agent know about + what can
 * it call". Pills are individually clickable; the parent canvas
 * forwards the click to the inspector.
 */
export function AgentSubAgentNode({
  data,
  selected,
}: NodeProps<SubAgentData>): JSX.Element {
  const step = data.step;
  const Icon = STEP_ICON[step.kind] ?? Brain;
  const accent = STEP_ACCENT[step.kind] ?? "from-blue-800 to-blue-900 border-blue-400";
  const skills = step.rules ?? [];

  const handlePillClick = (e: React.MouseEvent, id: string): void => {
    e.stopPropagation();
    data.onPillClick?.(id);
  };

  return (
    <div
      className={`rounded-lg px-3 py-2 text-white shadow-md w-64 border-2 bg-gradient-to-br ${accent} ${
        selected ? "ring-2 ring-white/70" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <Handle type="target" position={Position.Left} className="opacity-0" id="lt" />
      <Handle type="target" position={Position.Right} className="opacity-0" id="rt" />
      <header className="flex items-center gap-1.5">
        <Icon className="w-4 h-4" aria-hidden />
        <p className="text-[9px] uppercase tracking-widest text-white/70">
          Sub-Agent
        </p>
      </header>
      <p className="text-sm font-semibold mt-0.5 leading-tight">{step.label}</p>
      <p className="text-[10px] text-white/70 mt-0.5 font-mono">
        {step.input_kind} → {step.output_kind}
      </p>
      <div className="flex flex-wrap gap-1 mt-1">
        {step.uses_llm && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/15 uppercase tracking-wide">
            🧠 LLM
          </span>
        )}
        {!step.uses_llm && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/15 uppercase tracking-wide">
            ⚙ deterministisch
          </span>
        )}
      </div>
      {skills.length > 0 && (
        <div className="mt-2">
          <p className="text-[9px] uppercase tracking-wide text-amber-200/90 font-semibold">
            Skills ({skills.length})
          </p>
          <div className="flex flex-wrap gap-1 mt-0.5">
            {skills.map((sk) => (
              <button
                key={sk}
                type="button"
                onClick={(e) => handlePillClick(e, `rule:${sk}`)}
                title={`Skill: ${sk}`}
                className="text-[9px] px-1.5 py-0.5 rounded bg-amber-900/60 border border-amber-500/60 text-amber-100 hover:bg-amber-700/70 transition-colors max-w-[160px] truncate"
              >
                {sk}
              </button>
            ))}
          </div>
        </div>
      )}
      {data.tools.length > 0 && (
        <div className="mt-2">
          <p className="text-[9px] uppercase tracking-wide text-cyan-200/90 font-semibold">
            Werkzeuge ({data.tools.length})
          </p>
          <div className="flex flex-wrap gap-1 mt-0.5">
            {data.tools.map((tool) => (
              <button
                key={tool.name}
                type="button"
                onClick={(e) => handlePillClick(e, `tool:${tool.name}`)}
                title={`${tool.label}${tool.enabled ? "" : " (deaktiviert)"}`}
                className={`text-[9px] px-1.5 py-0.5 rounded border max-w-[160px] truncate transition-colors ${
                  tool.enabled
                    ? "bg-cyan-900/60 border-cyan-500/60 text-cyan-100 hover:bg-cyan-700/70"
                    : "bg-slate-800/60 border-slate-500/40 text-slate-400 hover:bg-slate-700/60 italic"
                }`}
              >
                {tool.label}
                {!tool.enabled && " ◌"}
              </button>
            ))}
          </div>
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
      <Handle type="source" position={Position.Left} className="opacity-0" id="ls" />
      <Handle type="source" position={Position.Right} className="opacity-0" id="rs" />
    </div>
  );
}
