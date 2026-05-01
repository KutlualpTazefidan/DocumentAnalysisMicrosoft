import { useState } from "react";
import { ChevronRight } from "lucide-react";

const KINDS: { kind: string; color: string }[] = [
  { kind: "heading", color: "#2563eb" },
  { kind: "paragraph", color: "#16a34a" },
  { kind: "table", color: "#ea580c" },
  { kind: "figure", color: "#0d9488" },
  { kind: "caption", color: "#9333ea" },
  { kind: "formula", color: "#db2777" },
  { kind: "list_item", color: "#4f46e5" },
  { kind: "abandon", color: "#06b6d4" },
  { kind: "discard", color: "#6b7280" },
];

/**
 * Floating colour legend that explains what each box-outline colour means.
 * Sits top-left of the PDF pane (mirroring the zoom widget on the right).
 * Collapses to a single chevron button so it never crowds the page;
 * expanded view shows the 8 kinds with swatches.
 */
export function BoxLegend(): JSX.Element {
  const [open, setOpen] = useState(true);

  if (!open) {
    return (
      <button
        aria-label="Show legend"
        title="Show legend"
        onClick={() => setOpen(true)}
        className="absolute top-4 left-4 z-20 w-7 h-7 flex items-center justify-center rounded bg-white/90 backdrop-blur border border-slate-300 shadow-sm hover:bg-slate-50"
      >
        <ChevronRight className="w-4 h-4 text-slate-700" />
      </button>
    );
  }

  return (
    <div className="absolute top-4 left-4 z-20 bg-white/90 backdrop-blur border border-slate-300 rounded shadow-sm px-3 py-2 text-xs">
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-semibold text-slate-500 uppercase tracking-wide">Legend</span>
        <button
          aria-label="Hide legend"
          onClick={() => setOpen(false)}
          className="text-slate-400 hover:text-slate-700"
        >
          ×
        </button>
      </div>
      <ul className="grid grid-cols-1 gap-1">
        {KINDS.map((k) => (
          <li key={k.kind} className="flex items-center gap-2 text-slate-700">
            <span
              aria-hidden="true"
              className="w-3 h-3 rounded-sm border"
              style={{ background: k.color, borderColor: k.color }}
            />
            <span>{k.kind}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
