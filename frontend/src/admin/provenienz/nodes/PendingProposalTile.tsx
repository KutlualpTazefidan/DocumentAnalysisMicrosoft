import { Lightbulb } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { PendingProposalView } from "../layout";

const STEP_LABEL: Record<string, string> = {
  extract_claims: "Aussagen extrahieren",
  formulate_task: "Aufgabe formulieren",
  search: "Suchen",
  evaluate: "Bewerten",
  propose_stop: "Stopp vorschlagen",
};

/**
 * Yellow call-to-action tile representing an LLM recommendation that hasn't
 * been resolved yet. Once `/decide` is called, this tile disappears (the
 * spawned children take its place).
 */
export function PendingProposalTile({
  data,
}: NodeProps<PendingProposalView>): JSX.Element {
  const stepKind = String((data.proposal.payload.step_kind as string) ?? "");
  const recommended = data.proposal.payload.recommended as
    | { label?: string }
    | undefined;
  const altCount = Array.isArray(data.proposal.payload.alternatives)
    ? (data.proposal.payload.alternatives as unknown[]).length
    : 0;
  const guidanceCount = Array.isArray(data.proposal.payload.guidance_consulted)
    ? (data.proposal.payload.guidance_consulted as unknown[]).length
    : 0;

  return (
    <div className="rounded-lg border-2 border-amber-400 bg-amber-700 px-3 py-2 text-white shadow-lg w-60 animate-pulse-slow">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-amber-100">
        <Lightbulb className="w-3 h-3" aria-hidden />
        {STEP_LABEL[stepKind] ?? stepKind}
      </header>
      {recommended?.label && (
        <p className="text-xs leading-snug mt-1 line-clamp-2">
          {recommended.label}
        </p>
      )}
      <p className="text-[10px] text-amber-100/70 mt-1">
        {altCount > 0 && `${altCount} Alternative${altCount === 1 ? "" : "n"}`}
        {altCount > 0 && guidanceCount > 0 && " · "}
        {guidanceCount > 0 && `${guidanceCount} Hinweis${guidanceCount === 1 ? "" : "e"}`}
      </p>
      <p className="text-[10px] italic text-amber-200 mt-1">→ Klicken zum Entscheiden</p>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
