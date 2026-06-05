import { Sparkles } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

/**
 * Orchestrator node — the 'Was als nächstes?' meta-planner at the top
 * of the agent topology. Visually larger and accent-coloured so the
 * viewer immediately reads 'this is where every step starts'. Shows
 * the open-ended classification it emits (executable_step,
 * capability_request, manual_review) so the three branches off it
 * are self-explanatory.
 */
export function AgentOrchestratorNode({
  data,
  selected,
}: NodeProps<{
  label: string;
  subagent_count: number;
  active_skills_count: number;
}>): JSX.Element {
  return (
    <div
      className={`rounded-xl px-5 py-3 text-ink shadow-xl w-80 border-2 bg-gradient-to-br from-indigo-50 to-purple-50 border-indigo-500 ${
        selected ? "ring-4 ring-indigo-400/60" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-2">
        <Sparkles className="w-5 h-5" aria-hidden />
        <p className="text-[10px] uppercase tracking-widest text-indigo-700">
          Orchestrator
        </p>
      </header>
      <p className="text-base font-bold mt-0.5">{data.label}</p>
      <p className="text-[11px] text-indigo-900/90 mt-1 leading-snug">
        Liest den aktuellen Knoten und entscheidet welcher Sub-Agent als
        nächstes lauft. Output ist eine Empfehlung mit Begründung +
        Konfidenz.
      </p>
      <div className="flex flex-wrap gap-1.5 mt-2">
        <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 font-medium">
          {data.subagent_count} Sub-Agenten
        </span>
        <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 font-medium">
          {data.active_skills_count} aktive Skills
        </span>
        <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 font-medium">
          🧠 LLM-gesteuert
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
