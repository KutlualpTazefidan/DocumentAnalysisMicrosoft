import { CheckCircle2, Wrench, X } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { CapabilityGateView } from "../layout";

const STATUS_STYLE: Record<
  string,
  { border: string; bg: string; icon: typeof Wrench; tag: string; tagBg: string }
> = {
  pending: {
    border: "border-orange-500",
    bg: "bg-orange-950/40",
    icon: Wrench,
    tag: "pending",
    tagBg: "bg-orange-700",
  },
  accepted: {
    border: "border-emerald-600/70",
    bg: "bg-emerald-950/30",
    icon: CheckCircle2,
    tag: "accepted",
    tagBg: "bg-emerald-700",
  },
  dismissed: {
    border: "border-zinc-600/60",
    bg: "bg-zinc-900/40",
    icon: X,
    tag: "verworfen",
    tagBg: "bg-zinc-700",
  },
};

/**
 * Reactive-Capability gate tile — auto-spawned after evaluate. Click
 * to open the panel which lists detected capabilities + their domain
 * rules + offers re-evaluate / dismiss actions.
 */
export function CapabilityGateTile({
  data,
}: NodeProps<CapabilityGateView>): JSX.Element {
  const p = data.gate.payload as {
    detected?: { name: string; kind: string; parent?: string }[];
    status?: string;
  };
  const status = String(p.status ?? "pending");
  const style = STATUS_STYLE[status] ?? STATUS_STYLE.pending;
  const Icon = style.icon;
  const detected = Array.isArray(p.detected) ? p.detected : [];
  const topCount = detected.filter((d) => d.kind === "top").length;
  const subCount = detected.filter((d) => d.kind === "sub").length;
  return (
    <div className={`rounded-lg border-2 ${style.border} ${style.bg} px-3 py-2 text-white shadow-md w-72`}>
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-orange-200">
        <Icon className="w-3 h-3" aria-hidden /> Capability-Gate
        <span className={`ml-auto px-1.5 py-px rounded text-[10px] font-semibold ${style.tagBg} text-white`}>
          {style.tag}
        </span>
      </header>
      <p className="text-[12px] text-slate-100 mt-1 font-medium">
        🔧 {detected.length} Capabilities erkannt
      </p>
      {(topCount > 0 || subCount > 0) && (
        <p className="text-[11px] text-slate-300 mt-0.5">
          {topCount} top-level
          {subCount > 0 && `, ${subCount} sub-skill${subCount === 1 ? "" : "s"}`}
        </p>
      )}
      <ul className="mt-1 space-y-0.5 max-h-20 overflow-hidden">
        {detected.slice(0, 3).map((d, i) => (
          <li key={i} className="text-[10px] text-orange-200 font-mono truncate">
            {d.kind === "sub" ? "└ " : ""}
            {d.name}
          </li>
        ))}
        {detected.length > 3 && (
          <li className="text-[10px] text-slate-500 italic">
            + {detected.length - 3} weitere
          </li>
        )}
      </ul>
      <p className="text-[10px] italic text-slate-500 mt-1">
        Klicken {status === "pending" ? "→ Re-evaluieren" : "für Audit"}
      </p>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
