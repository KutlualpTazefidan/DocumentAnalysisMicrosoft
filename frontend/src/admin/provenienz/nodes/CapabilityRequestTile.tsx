import { Wrench } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { CapabilityRequestView } from "../layout";

/**
 * Yellow-bordered tile: "the agent says we need a capability that doesn't
 * exist yet." Output of /next-step when no registered step + tool fits.
 * Carries the description of what's missing — basis for a future
 * tool/skill implementation.
 */
export function CapabilityRequestTile({
  data,
}: NodeProps<CapabilityRequestView>): JSX.Element {
  const p = data.request.payload as {
    name?: string;
    description?: string;
    reasoning?: string;
  };
  return (
    <div className="rounded-lg border-2 border-yellow-400 bg-yellow-900/30 px-3 py-2 text-white shadow-md w-72">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-yellow-200">
        <Wrench className="w-3 h-3" aria-hidden /> Fehlende Capability
      </header>
      {p.name && (
        <p className="text-sm font-semibold text-yellow-50 mt-0.5">
          {p.name}
        </p>
      )}
      {p.description && (
        <p className="text-[11px] text-yellow-100 mt-1 line-clamp-3">
          {p.description}
        </p>
      )}
      {p.reasoning && (
        <p className="text-[10px] text-yellow-200/70 italic mt-1 line-clamp-2">
          Warum: {p.reasoning}
        </p>
      )}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
