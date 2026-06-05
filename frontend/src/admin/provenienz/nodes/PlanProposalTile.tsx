import { Brain, CheckCircle2, Sparkles } from "lucide-react";
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
  const consumed = !!data.consumed;
  // Same two-variant pattern as ActionProposalTile: pending = bright +
  // pulse; consumed (= step fired downstream) = dim + check-mark.
  const containerClass = consumed
    ? "prov-tile border border-amber-200 bg-amber-50 px-3 py-2 w-72 opacity-80"
    : "prov-tile border-2 border-amber-500 bg-amber-50 px-3 py-2 w-72 animate-pulse-slow";
  return (
    <div className={containerClass}>
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center justify-between gap-1 text-[10px] uppercase tracking-wide text-amber-700">
        <span className="flex items-center gap-1">
          <Sparkles className="w-3 h-3" aria-hidden /> Agent-Vorschlag
        </span>
        {consumed ? (
          <span className="flex items-center gap-1 text-amber-800/80 normal-case">
            <CheckCircle2 className="w-3 h-3" aria-hidden /> ausgeführt
          </span>
        ) : (
          conf !== null && <span className="text-amber-800">{conf}%</span>
        )}
      </header>
      <p className="text-sm font-semibold text-amber-900 mt-0.5">
        → {STEP_LABEL[stepName] ?? stepName}
      </p>
      {p.reasoning && (
        <div className="mt-1.5 rounded bg-amber-100 border border-amber-200 px-1.5 py-1">
          <p className="flex items-center gap-1 text-[9px] uppercase tracking-wide text-amber-800">
            <Brain className="w-3 h-3" aria-hidden /> Begründung
          </p>
          <p className="text-[11px] text-amber-900 italic line-clamp-2 mt-0.5">
            {p.reasoning}
          </p>
        </div>
      )}
      <div className="flex flex-wrap gap-1 mt-1.5">
        {p.tool && (
          <span className="text-[9px] uppercase tracking-wide bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded">
            🔧 {p.tool}
          </span>
        )}
        {altCount > 0 && (
          <span className="text-[9px] text-amber-800/85">
            {altCount} Alternative{altCount === 1 ? "" : "n"} erwogen
          </span>
        )}
      </div>
      <p className="text-[10px] italic text-amber-800 mt-1">
        {consumed ? "Klicken für Begründung (Audit)" : "→ Klicken für Begründung + Akzeptieren"}
      </p>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
