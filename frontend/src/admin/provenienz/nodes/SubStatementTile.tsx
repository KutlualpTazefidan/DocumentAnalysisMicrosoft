import { Sigma } from "lucide-react";
import { Handle, Position, type NodeProps } from "reactflow";

import type { SubStatementView } from "../layout";

/**
 * One atomic sub-statement extracted from a search_result via
 * decompose_hit. Compact tile so multiple subs from the same parent
 * fit horizontally below it.
 */
export function SubStatementTile({
  data,
}: NodeProps<SubStatementView>): JSX.Element {
  const p = data.sub_statement.payload as { text?: string };
  const text = String(p.text ?? "");
  return (
    <div className="rounded-lg border-2 border-fuchsia-500/70 bg-navy-800 px-3 py-2 text-white shadow-md w-72">
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <header className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-fuchsia-200">
        <Sigma className="w-3 h-3" aria-hidden /> Sub-Aussage
      </header>
      <p className="text-[12px] text-slate-200 mt-1 line-clamp-3 italic">
        „{text}"
      </p>
      <p className="text-[10px] italic text-slate-500 mt-1">
        Klicken für nächsten Schritt
      </p>
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
    </div>
  );
}
