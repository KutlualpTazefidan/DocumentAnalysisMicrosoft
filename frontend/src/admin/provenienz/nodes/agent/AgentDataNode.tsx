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
      className={`rounded-lg px-4 py-2 text-white shadow-sm w-56 ${
        selected
          ? "bg-slate-700 border-2 border-blue-400"
          : "bg-slate-700 border border-slate-500"
      }`}
    >
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <p className="text-[10px] uppercase tracking-wide text-slate-300">Daten</p>
      <p className="text-sm font-semibold">{data.label}</p>
      {data.sub && <p className="text-[11px] text-slate-300/80 mt-0.5">{data.sub}</p>}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
      <Handle type="target" position={Position.Right} className="opacity-0" id="r" />
      <Handle type="source" position={Position.Right} className="opacity-0" id="r-s" />
      <Handle type="target" position={Position.Left} className="opacity-0" id="l" />
    </div>
  );
}
