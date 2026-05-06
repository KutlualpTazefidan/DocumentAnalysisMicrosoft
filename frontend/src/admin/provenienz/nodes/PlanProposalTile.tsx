import { Brain, Sparkles } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { PlanProposalView } from "../layout";

const STEP_LABEL: Record<string, string> = {
  extract_claims: "Aussagen extrahieren",
  formulate_task: "Aufgabe formulieren",
  search: "Suchen",
  evaluate: "Bewerten",
  propose_stop: "Stopp vorschlagen",
  promote_search_result: "Treffer weiter erforschen",
};

/**
 * Output of /next-step when the agent chose a registered executable step.
 * User clicks Akzeptieren in the side panel → frontend fires the matching
 * step route. Visually a yellow trunk tile with the picked step name +
 * agent's reasoning.
 */
export function PlanProposalTile({
  data,
}: NodeProps<PlanProposalView>): JSX.Element {
  const p = data.plan.payload as {
    name?: string;
    reasoning?: string;
    confidence?: number;
    considered_alternatives?: unknown[];
    tool?: string | null;
  };
  const stepName = String(p.name ?? "");
  const conf =
    typeof p.confidence === "number" ? Math.round(p.confidence * 100) : null;
  const altCount = Array.isArray(p.considered_alternatives)
    ? p.considered_alternatives.length
    : 0;
  return (
    <div className="rounded-lg border-2 border-amber-400 bg-amber-700 px-3 py-2 text-white shadow-lg w-72 animate-pulse-slow">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center justify-between gap-1 text-[10px] uppercase tracking-wide text-amber-100">
        <span className="flex items-center gap-1">
          <Sparkles className="w-3 h-3" aria-hidden /> Agent-Vorschlag
        </span>
        {conf !== null && <span className="text-amber-200">{conf}%</span>}
      </header>
      <p className="text-sm font-semibold text-amber-50 mt-0.5">
        → {STEP_LABEL[stepName] ?? stepName}
      </p>
      {p.reasoning && (
        <div className="mt-1.5 rounded bg-amber-900/30 border border-amber-500/40 px-1.5 py-1">
          <p className="flex items-center gap-1 text-[9px] uppercase tracking-wide text-amber-200">
            <Brain className="w-3 h-3" aria-hidden /> Begründung
          </p>
          <p className="text-[11px] text-amber-50 italic line-clamp-2 mt-0.5">
            {p.reasoning}
          </p>
        </div>
      )}
      <div className="flex flex-wrap gap-1 mt-1.5">
        {p.tool && (
          <span className="text-[9px] uppercase tracking-wide bg-emerald-700 text-emerald-50 px-1.5 py-0.5 rounded">
            🔧 {p.tool}
          </span>
        )}
        {altCount > 0 && (
          <span className="text-[9px] text-amber-100/85">
            {altCount} Alternative{altCount === 1 ? "" : "n"} erwogen
          </span>
        )}
      </div>
      <p className="text-[10px] italic text-amber-200 mt-1">
        → Klicken für Begründung + Akzeptieren
      </p>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
