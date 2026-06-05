import type { NodeProps } from "reactflow";
import { Handle, Position } from "reactflow";

/**
 * Fallback renderer for unknown node `kind` values. The backend treats `kind`
 * as an open string, so the canvas must render new kinds without crashing.
 */
export function FallbackNode({ data }: NodeProps): JSX.Element {
  const kind = (data?.kind as string) ?? "unknown";
  return (
    <div className="prov-tile px-3 py-2 text-xs w-56">
      <Handle type="target" position={Position.Top} />
      <p className="font-mono prov-tile-head">
        {kind}
      </p>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
