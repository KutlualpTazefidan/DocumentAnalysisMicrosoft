import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";

/**
 * Fallback renderer for unknown node `kind` values. The backend treats `kind`
 * as an open string, so the canvas must render new kinds without crashing.
 */
export function FallbackNode({ data }: NodeProps): JSX.Element {
  const kind = (data?.kind as string) ?? "unknown";
  return (
    <div className="rounded border border-slate-500 bg-slate-700 px-3 py-2 text-xs text-white shadow w-56">
      <Handle type="target" position={Position.Top} />
      <p className="font-mono text-[10px] uppercase tracking-wide text-slate-300">
        {kind}
      </p>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
