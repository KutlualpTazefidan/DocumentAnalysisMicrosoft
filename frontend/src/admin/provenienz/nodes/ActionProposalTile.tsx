import { Brain, CheckCircle2, Lightbulb } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { ActionProposalView } from "../layout";

const STEP_LABEL: Record<string, string> = {
  extract_claims: "Aussagen extrahieren",
  formulate_task: "Aufgabe formulieren",
  search: "Suchen",
  evaluate: "Bewerten",
  propose_stop: "Stopp vorschlagen",
};

/**
 * Action-Proposal tile — visible for every proposal in the session,
 * decided or pending. Two visual variants:
 *   - pending  → bright yellow + pulse, "klicken für Entscheidung"
 *   - decided  → dim grey-yellow, "✓ entschieden" marker, click for audit
 */
export function ActionProposalTile({
  data,
}: NodeProps<ActionProposalView>): JSX.Element {
  const p = data.proposal.payload as {
    step_kind?: string;
    recommended?: { label?: string };
    alternatives?: unknown[];
    guidance_consulted?: unknown[];
    pre_reasoning?: string;
    tool_used?: string | null;
  };
  const stepKind = String(p.step_kind ?? "");
  const preReasoning = String(p.pre_reasoning ?? "");
  const recommended = p.recommended;
  const altCount = Array.isArray(p.alternatives) ? p.alternatives.length : 0;
  const guidanceCount = Array.isArray(p.guidance_consulted)
    ? p.guidance_consulted.length
    : 0;
  const tool = p.tool_used ?? null;

  const containerClass = data.decision
    ? "prov-tile border border-amber-200 bg-amber-50 px-3 py-2 w-72 opacity-80"
    : "prov-tile border-2 border-amber-500 bg-amber-50 px-3 py-2 w-72 animate-pulse-slow";

  return (
    <div className={containerClass}>
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center justify-between gap-1 text-[10px] uppercase tracking-wide text-amber-700">
        <span className="flex items-center gap-1">
          <Lightbulb className="w-3 h-3" aria-hidden />
          {STEP_LABEL[stepKind] ?? stepKind}
        </span>
        {data.decision ? (
          <span className="flex items-center gap-1 text-amber-800/80 normal-case">
            <CheckCircle2 className="w-3 h-3" aria-hidden /> entschieden
          </span>
        ) : null}
      </header>
      {preReasoning && (
        <div className="mt-1.5 rounded bg-amber-100 border border-amber-200 px-1.5 py-1">
          <p className="flex items-center gap-1 text-[9px] uppercase tracking-wide text-amber-800">
            <Brain className="w-3 h-3" aria-hidden /> Vor-Reasoning
          </p>
          <p className="text-[11px] text-amber-900 italic line-clamp-2 mt-0.5">
            {preReasoning}
          </p>
        </div>
      )}
      {recommended?.label && (
        <div className="mt-1.5 pt-1.5 border-t border-amber-200">
          <p className="text-[9px] uppercase tracking-wide text-amber-800">
            Empfehlung
          </p>
          <p className="text-xs text-amber-900 line-clamp-2 mt-0.5">
            {recommended.label}
          </p>
        </div>
      )}
      <div className="flex flex-wrap gap-1 mt-1.5">
        {tool && (
          <span className="text-[9px] uppercase tracking-wide bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded">
            🔧 {tool}
          </span>
        )}
        {altCount > 0 && (
          <span className="text-[9px] text-amber-800/85">{altCount} Alt.</span>
        )}
        {guidanceCount > 0 && (
          <span className="text-[9px] text-amber-800/85">🛡 {guidanceCount}</span>
        )}
      </div>
      <p className="text-[10px] italic text-amber-800 mt-1">
        {data.decision
          ? "→ Klicken für Audit"
          : "→ Klicken für Skill-Prompt + Entscheidung"}
      </p>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
