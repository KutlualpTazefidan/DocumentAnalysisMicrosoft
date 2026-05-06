import { Check } from "lucide-react";
import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";

export function DecisionNode({ data }: NodeProps): JSX.Element {
  const payload = (data?.payload as Record<string, unknown>) ?? {};
  const accepted = String(payload.accepted ?? "");
  const reason = payload.reason ? String(payload.reason) : null;
  return (
    <div className="rounded border border-purple-400 bg-purple-700 px-3 py-2 text-white shadow w-56">
      <Handle type="target" position={Position.Top} />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-purple-200">
        <Check className="w-3 h-3" aria-hidden /> decision
      </header>
      <p className="text-xs leading-tight mt-1">
        accepted: <span className="font-mono">{accepted}</span>
      </p>
      {reason && (
        <p className="text-[10px] leading-tight text-purple-100 mt-1 line-clamp-2">
          {reason}
        </p>
      )}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
