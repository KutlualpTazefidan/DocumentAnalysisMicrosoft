import { CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { ReflectionView } from "../layout";

const ASSESSMENT_STYLE: Record<
  string,
  { border: string; bg: string; icon: typeof CheckCircle2; tag: string }
> = {
  vollständig: {
    border: "border-emerald-600",
    bg: "bg-emerald-900/30",
    icon: CheckCircle2,
    tag: "vollständig",
  },
  lückenhaft: {
    border: "border-amber-500",
    bg: "bg-amber-900/30",
    icon: AlertTriangle,
    tag: "lückenhaft",
  },
  fehlerhaft: {
    border: "border-rose-600",
    bg: "bg-rose-900/30",
    icon: XCircle,
    tag: "fehlerhaft",
  },
};

/**
 * Self-critique tile — sits next to the action_proposal it reviewed.
 * Three colour variants by self_assessment so the user spots
 * "vollständig" (green) vs "lückenhaft" (amber) vs "fehlerhaft" (rose)
 * at a glance.
 */
export function ReflectionTile({
  data,
}: NodeProps<ReflectionView>): JSX.Element {
  const p = data.reflection.payload as {
    self_assessment?: string;
    missed_statements?: string[];
    concerns?: string[];
    recommendation?: string;
  };
  const assessment = String(p.self_assessment ?? "vollständig");
  const style =
    ASSESSMENT_STYLE[assessment] ?? ASSESSMENT_STYLE.vollständig;
  const Icon = style.icon;
  const missedCount = Array.isArray(p.missed_statements)
    ? p.missed_statements.length
    : 0;
  const recommendation = String(p.recommendation ?? "accept");
  return (
    <div
      className={`rounded-lg border-2 ${style.border} ${style.bg} px-3 py-2 text-white shadow-md w-72`}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-violet-200">
        <Icon className="w-3 h-3" aria-hidden /> Reflektion
        <span className="ml-auto px-1.5 py-px rounded text-[10px] font-semibold bg-violet-700 text-white">
          {style.tag}
        </span>
      </header>
      <p className="text-[11px] text-slate-200 mt-1">
        Empfehlung:{" "}
        <span className="font-mono text-violet-200">{recommendation}</span>
      </p>
      {missedCount > 0 && (
        <p className="text-[10px] text-amber-200 mt-1">
          {missedCount} übersehene{missedCount === 1 ? "r" : ""} Satz
          {missedCount === 1 ? "" : "/Sätze"}
        </p>
      )}
      <p className="text-[10px] italic text-slate-500 mt-1">
        Klicken für Details
      </p>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
