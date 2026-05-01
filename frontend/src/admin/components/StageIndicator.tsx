import { useState } from "react";

import type { StreamState } from "../streamReducer";
import { StageTimeline } from "./StageTimeline";

interface Props {
  state: StreamState;
}

const DOT_CLASS: Record<string, string> = {
  idle: "bg-gray-400",
  loading: "bg-yellow-500",
  ready: "bg-yellow-500",
  running: "bg-green-500",
  completed: "bg-gray-500",
  unloading: "bg-yellow-500",
  failed: "bg-red-600",
};

function fmtEta(seconds: number | null | undefined): string | null {
  if (seconds == null) return null;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}

export function StageIndicator({ state }: Props): JSX.Element | null {
  const [open, setOpen] = useState(false);

  if (state.stage === "idle" && state.timeline.length === 0) {
    return null;
  }

  const eta = fmtEta(state.eta_seconds);

  return (
    <div className="absolute top-2 right-2 z-30">
      <button
        data-testid="stage-toggle"
        onClick={() => setOpen((p) => !p)}
        className="flex items-center gap-2 bg-white border rounded px-3 py-1 text-xs shadow"
      >
        <span data-testid="stage-dot" className={`inline-block w-2 h-2 rounded-full ${DOT_CLASS[state.stage] ?? "bg-gray-400"}`} />
        <span className="font-medium">{state.model ?? "—"}</span>
        {state.progress != null ? (
          <span>
            {state.progress.stage} {state.progress.current} / {state.progress.total}
          </span>
        ) : null}
        {eta != null ? <span>• ETA {eta}</span> : null}
        {state.vram_mb > 0 ? <span>• {state.vram_mb}MB</span> : null}
      </button>
      {open ? (
        <div className="mt-1 bg-white border rounded shadow w-96">
          <StageTimeline events={state.timeline} />
        </div>
      ) : null}
    </div>
  );
}
