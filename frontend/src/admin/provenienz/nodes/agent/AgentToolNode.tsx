import { Wrench } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { AgentToolInfo } from "../../../hooks/useProvenienz";

/**
 * Tool tile — sits to the right of the step that calls it. Disabled tools
 * render dimmer and carry a "deaktiviert" badge so the user sees that the
 * capability *exists* but isn't wired in yet.
 */
export function AgentToolNode({
  data,
  selected,
}: NodeProps<{ tool: AgentToolInfo }>): JSX.Element {
  const tool = data.tool;
  const ringClass = selected ? "ring-2 ring-white/40" : "";
  const colorClass = tool.enabled
    ? "bg-emerald-900/80 border-emerald-600"
    : "bg-zinc-800/60 border-zinc-600 opacity-70";
  return (
    <div
      className={`rounded-lg px-4 py-2 text-white shadow-md w-56 border-2 ${colorClass} ${ringClass}`}
    >
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <header className="flex items-center justify-between gap-1.5">
        <span className="flex items-center gap-1.5">
          <Wrench className="w-4 h-4" aria-hidden />
          <p className="text-[10px] uppercase tracking-wide text-emerald-200">Tool</p>
        </span>
        {!tool.enabled && (
          <span className="text-[9px] uppercase tracking-wide bg-zinc-700 text-zinc-300 px-1.5 py-0.5 rounded">
            deaktiviert
          </span>
        )}
      </header>
      <p className="text-sm font-semibold mt-0.5">{tool.label}</p>
      <p className="text-[11px] text-emerald-100/80 mt-0.5">
        {tool.scope} · {tool.cost_hint}
      </p>
    </div>
  );
}
