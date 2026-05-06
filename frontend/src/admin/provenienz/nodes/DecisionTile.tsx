import { Check } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { DecisionView } from "../layout";

const ACCEPT_LABEL: Record<string, string> = {
  recommended: "Empfehlung übernommen",
  alt: "Alternative gewählt",
  override: "Eigene Eingabe",
};

/**
 * Decision tile — sits between a decided proposal and the things that
 * decision spawned. Shows accepted-mode + actor + a snippet of the
 * reason/override so the audit chain reads clearly in the canvas.
 */
export function DecisionTile({
  data,
}: NodeProps<DecisionView>): JSX.Element {
  const p = data.decision.payload as {
    accepted?: string;
    reason?: string;
    override?: string;
  };
  const accepted = String(p.accepted ?? "");
  const reasonText = String(p.reason ?? "").trim();
  const overrideText = String(p.override ?? "").trim();
  const subtitle = overrideText || reasonText;

  return (
    <div className="rounded-lg border border-purple-500/70 bg-purple-900/40 px-3 py-2 text-white shadow w-60">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-purple-200">
        <Check className="w-3 h-3" aria-hidden />
        Entscheidung
      </header>
      <p className="text-xs font-semibold text-purple-50 mt-0.5">
        {ACCEPT_LABEL[accepted] ?? accepted}
      </p>
      {subtitle && (
        <p className="text-[11px] text-purple-100/85 italic line-clamp-2 mt-1">
          {subtitle}
        </p>
      )}
      <p className="text-[9px] text-purple-200/70 mt-1 font-mono">
        {data.decision.actor} · {data.decision.created_at}
      </p>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
