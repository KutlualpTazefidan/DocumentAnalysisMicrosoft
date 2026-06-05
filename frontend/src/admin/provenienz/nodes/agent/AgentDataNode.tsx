import { Handle, Position, type NodeProps } from "reactflow";

interface DataData {
  label: string;
  sub?: string;
}

/**
 * Trunk-line tile representing a node *kind* (Chunk, Claim, Task, …).
 * Slim grey card — these are the "things" the steps move through.
 */
export function AgentDataNode({ data, selected }: NodeProps<DataData>): JSX.Element {
  return (
    <div
      className={`prov-tile px-4 py-2 w-56 ${
        selected ? "border-2 border-blue-500" : ""
      }`}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <p className="prov-tile-head">Daten</p>
      <p className="text-sm font-semibold">{data.label}</p>
      {data.sub && <p className="text-[11px] text-ink-muted mt-0.5">{data.sub}</p>}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
      <Handle type="target" position={Position.Right} className="opacity-0" id="r" />
      <Handle type="source" position={Position.Right} className="opacity-0" id="r-s" />
      <Handle type="target" position={Position.Left} className="opacity-0" id="l" />
    </div>
  );
}
