import { Wrench } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { AgentToolInfo } from "../../../hooks/useProvenienz";

/**
 * Tool tile — sits to the right of the step that calls it.
 */
export function AgentToolNode({
  data,
  selected,
}: NodeProps<{ tool: AgentToolInfo }>): JSX.Element {
  const tool = data.tool;
  return (
    <div
      className={`rounded-lg px-4 py-2 text-white shadow-md w-56 border-2 bg-emerald-900/80 ${
        selected ? "border-emerald-300 ring-2 ring-white/40" : "border-emerald-600"
      }`}
    >
      <Handle type="target" position={Position.Left} className="opacity-0" />
      <header className="flex items-center gap-1.5">
        <Wrench className="w-4 h-4" aria-hidden />
        <p className="text-[10px] uppercase tracking-wide text-emerald-200">Tool</p>
      </header>
      <p className="text-sm font-semibold mt-0.5">{tool.name}</p>
      <p className="text-[11px] text-emerald-100/80 mt-0.5">
        {tool.type} · {tool.scope}
      </p>
    </div>
  );
}
