import { Lightbulb, Sparkles } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { PlanProposalView } from "../layout";

const STEP_LABEL: Record<string, string> = {
  extract_claims: "Aussagen extrahieren",
  formulate_task: "Aufgabe formulieren",
  search: "Suchen",
  evaluate: "Bewerten",
  propose_stop: "Stopp vorschlagen",
  promote_search_result: "Treffer weiter erforschen",
  stop: "Sitzung stoppen",
};

/**
 * Yellow Planner-Vorschlag tile inside the canvas — anchored to the
 * target node the Planner is recommending action for. Click to open
 * the side panel with reasoning + accept/dismiss controls.
 */
export function PlanProposalTile({
  data,
  selected,
}: NodeProps<PlanProposalView>): JSX.Element {
  const p = data.proposal.payload;
  const stepKind = String(p.step_kind ?? p.next_step ?? "");
  const reasoning = String(p.reasoning ?? "");
  const conf =
    typeof p.confidence === "number" ? Math.round(p.confidence * 100) : null;
  const tool = (p.tool as string | null) ?? null;
  const approachId = (p.approach_id as string | null) ?? null;

  return (
    <div
      className={`rounded-lg px-3 py-2 text-white shadow-md w-80 border-2 bg-amber-900/40 border-amber-400 animate-pulse-slow ${
        selected ? "ring-2 ring-amber-200/60" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1.5">
        <Sparkles className="w-4 h-4 text-amber-300" aria-hidden />
        <p className="text-[10px] uppercase tracking-wide text-amber-300">
          Planer-Vorschlag
        </p>
        {conf !== null && (
          <span className="ml-auto text-[10px] text-amber-200">{conf}%</span>
        )}
      </header>
      <p className="text-sm font-semibold text-amber-50 mt-0.5">
        → {STEP_LABEL[String(p.next_step ?? stepKind)] ?? p.next_step}
      </p>
      <p className="text-[11px] text-amber-100/85 mt-1 line-clamp-3">
        <Lightbulb className="w-3 h-3 inline mr-0.5" aria-hidden />
        {reasoning}
      </p>
      <div className="flex flex-wrap gap-1 mt-1.5">
        {tool && (
          <span className="text-[9px] uppercase tracking-wide bg-emerald-700 text-emerald-50 px-1.5 py-0.5 rounded">
            🔧 {tool}
          </span>
        )}
        {approachId && (
          <span className="text-[9px] uppercase tracking-wide bg-purple-700 text-purple-50 px-1.5 py-0.5 rounded">
            ⚙ {approachId}
          </span>
        )}
        <span className="text-[9px] italic text-amber-200/80 ml-auto">
          → klicken zum Akzeptieren
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
