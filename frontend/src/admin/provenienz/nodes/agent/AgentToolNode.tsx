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
  const ringClass = selected ? "ring-2 ring-emerald-400/60" : "";
  const colorClass = tool.enabled
    ? "bg-emerald-50 border-emerald-500"
    : "bg-zinc-100 border-zinc-300 opacity-70";
  return (
    <div
      className={`prov-tile px-4 py-2 w-56 border-2 ${colorClass} ${ringClass}`}
    >
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <header className="flex items-center justify-between gap-1.5">
        <span className="flex items-center gap-1.5">
          <Wrench className="w-4 h-4" aria-hidden />
          <p className="text-[10px] uppercase tracking-wide text-emerald-800">Tool</p>
        </span>
        {!tool.enabled && (
          <span className="text-[9px] uppercase tracking-wide bg-zinc-200 text-zinc-700 px-1.5 py-0.5 rounded">
            deaktiviert
          </span>
        )}
      </header>
      <p className="text-sm font-semibold mt-0.5">{tool.label}</p>
      <p className="text-[11px] text-emerald-800/80 mt-0.5">
        {tool.scope} · {tool.cost_hint}
      </p>
    </div>
  );
}
