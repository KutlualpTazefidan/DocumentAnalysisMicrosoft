import type { SynthLine } from "../../shared/types/domain";

interface Props {
  lines: SynthLine[];
  totals: {
    totalElements: number;
    kept: number;
    skipped: number;
    errors: number;
    tokensEstimated: number;
    eventsWritten: number;
  };
}

function renderLine(line: SynthLine, idx: number) {
  if (line.type === "start") {
    return (
      <li key={idx} className="text-slate-600">
        ▶ Start ({line.total_elements} elements)
      </li>
    );
  }
  if (line.type === "element") {
    return (
      <li key={idx} className="text-slate-700">
        ✓ <span className="font-mono">{line.element_id}</span>
        {" · "}
        {line.kept} kept
        {line.skipped_reason ? ` · skipped: ${line.skipped_reason}` : ""}
        {" · "}
        {line.tokens_estimated} tokens
      </li>
    );
  }
  if (line.type === "error") {
    return (
      <li key={idx} className="text-red-700">
        ✗ <span className="font-mono">{line.element_id ?? "—"}</span>
        {" · "}
        {line.reason}
      </li>
    );
  }
  return (
    <li key={idx} className="text-green-700 font-medium">
      ◆ Complete · {line.events_written} events written · {line.prompt_tokens_estimated} tokens
    </li>
  );
}

export function SynthProgress({ lines, totals }: Props) {
  return (
    <div className="space-y-3">
      <div className="text-sm text-slate-600">
        {totals.totalElements} elements · {totals.kept} kept · {totals.errors} error
        {totals.errors !== 1 ? "s" : ""} · {totals.tokensEstimated} tokens
      </div>
      <ul className="space-y-1 font-mono text-xs bg-slate-50 rounded p-3 max-h-96 overflow-y-auto">
        {lines.map(renderLine)}
      </ul>
    </div>
  );
}
