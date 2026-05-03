import type { WorkerEvent } from "../types/domain";
import { T } from "../styles/typography";

interface Props {
  events: WorkerEvent[];
}

function fmtTime(ms: number): string {
  const d = new Date(ms);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}:${d
    .getSeconds()
    .toString()
    .padStart(2, "0")}`;
}

function describeEvent(ev: WorkerEvent): { marker: string; text: string } {
  switch (ev.type) {
    case "model-loading":
      return { marker: "loading", text: `${ev.model} • loading from ${ev.source}` };
    case "model-loaded":
      return {
        marker: "ok",
        text: `${ev.model} • loaded (${ev.load_seconds.toFixed(1)}s, ${ev.vram_actual_mb}MB)`,
      };
    case "work-progress":
      return {
        marker: "running",
        text: `${ev.model} • ${ev.stage} ${ev.current} / ${ev.total}${
          ev.eta_seconds != null ? ` • ETA ${ev.eta_seconds.toFixed(0)}s` : ""
        }`,
      };
    case "model-unloading":
      return { marker: "loading", text: `${ev.model} • unloading` };
    case "model-unloaded":
      return { marker: "ok", text: `${ev.model} • unloaded (freed ${ev.vram_freed_mb}MB)` };
    case "work-complete":
      return {
        marker: "ok",
        text: `${ev.model} • complete (${ev.items_processed} items, ${ev.total_seconds.toFixed(1)}s)`,
      };
    case "work-failed":
      return { marker: "error", text: `${ev.model} • failed at ${ev.stage}: ${ev.reason}` };
  }
}

const MARKER_CLASS: Record<string, string> = {
  loading: "text-yellow-600",
  running: "text-green-600",
  ok: "text-gray-500",
  error: "text-red-600",
};

export function StageTimeline({ events }: Props): JSX.Element {
  return (
    <ul data-testid="stage-timeline" className={`${T.body} space-y-1 p-2 max-h-64 overflow-auto`}>
      {events.map((ev, i) => {
        const { marker, text } = describeEvent(ev);
        return (
          <li
            key={i}
            data-testid={`timeline-entry-${i}`}
            className="flex items-center gap-2"
          >
            <span data-marker={marker} className={MARKER_CLASS[marker] ?? ""}>
              {marker === "ok" ? "✓" : marker === "running" ? "●" : marker === "error" ? "✗" : "●"}
            </span>
            <span className="text-gray-400">{fmtTime(ev.timestamp_ms)}</span>
            <span>{text}</span>
          </li>
        );
      })}
    </ul>
  );
}
