import { Quote } from "lucide-react";
import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";

export function ClaimNode({ data }: NodeProps): JSX.Element {
  const payload = (data?.payload as Record<string, unknown>) ?? {};
  const text = String(payload.text ?? "");
  return (
    <div className="rounded border border-blue-400 bg-blue-700 px-3 py-2 text-white shadow w-56">
      <Handle type="target" position={Position.Top} />
      <header className="flex items-center gap-1 text-[10px] uppercase tracking-wide text-blue-200">
        <Quote className="w-3 h-3" aria-hidden /> claim
      </header>
      <p className="text-xs leading-tight mt-1 line-clamp-3">{text}</p>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
