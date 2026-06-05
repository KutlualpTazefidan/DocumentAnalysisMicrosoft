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
  extract_claims: "from-amber-50 to-amber-100 border-amber-500",
  formulate_task: "from-cyan-50 to-cyan-100 border-cyan-500",
  search: "from-emerald-50 to-emerald-100 border-emerald-500",
  evaluate: "from-rose-50 to-rose-100 border-rose-500",
  propose_stop: "from-zinc-50 to-zinc-100 border-zinc-300",
  promote_search_result: "from-purple-50 to-purple-100 border-purple-500",
  investigate_table: "from-cyan-50 to-teal-100 border-teal-500",
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
  const accent = STEP_ACCENT[step.kind] ?? "from-blue-50 to-blue-100 border-blue-500";
  const skills = step.rules ?? [];

  const handlePillClick = (e: React.MouseEvent, id: string): void => {
    e.stopPropagation();
    data.onPillClick?.(id);
  };

  return (
    <div
      className={`prov-tile px-3 py-2 w-72 border-2 bg-gradient-to-br ${accent} ${
        selected ? "ring-2 ring-blue-400/60" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <Handle type="target" position={Position.Left} className="opacity-0" id="lt" />
      <Handle type="target" position={Position.Right} className="opacity-0" id="rt" />
      <header className="flex items-center gap-1.5">
        <Icon className="w-4 h-4" aria-hidden />
        <p className="text-[9px] uppercase tracking-widest text-ink-muted">
          Sub-Agent
        </p>
      </header>
      <p className="text-sm font-semibold mt-0.5 leading-tight">{step.label}</p>
      <p className="text-[10px] text-ink-muted mt-0.5 font-mono">
        {step.input_kind} → {step.output_kind}
      </p>
      <div className="flex flex-wrap gap-1 mt-1">
        {step.uses_llm && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/70 border border-line uppercase tracking-wide">
            🧠 LLM
          </span>
        )}
        {!step.uses_llm && (
          <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/70 border border-line uppercase tracking-wide">
            ⚙ deterministisch
          </span>
        )}
      </div>
      {skills.length > 0 && (
        <div className="mt-2">
          <p className="text-[9px] uppercase tracking-wide text-amber-800 font-semibold">
            Skills ({skills.length})
          </p>
          <div className="flex flex-wrap gap-1 mt-0.5">
            {skills.map((sk) => (
              <button
                key={sk}
                type="button"
                onClick={(e) => handlePillClick(e, `rule:${sk}`)}
                title={`Skill: ${sk}`}
                className="text-[9px] px-1.5 py-0.5 rounded bg-amber-100 border border-amber-500 text-amber-800 hover:bg-amber-200 transition-colors max-w-[160px] truncate"
              >
                {sk}
              </button>
            ))}
          </div>
        </div>
      )}
      {data.tools.length > 0 && (
        <div className="mt-2">
          <p className="text-[9px] uppercase tracking-wide text-cyan-800 font-semibold">
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
                    ? "bg-cyan-100 border-cyan-500 text-cyan-800 hover:bg-cyan-200"
                    : "bg-slate-100 border-slate-300 text-ink-muted hover:bg-slate-200 italic"
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
