import { useState } from "react";

import type { StreamState } from "../streamReducer";
import { StageTimeline } from "./StageTimeline";
import { T } from "../styles/typography";

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

  // Defensive: a malformed reducer event in the past could leave state
  // undefined; render nothing rather than crashing the whole tree.
  if (!state || (state.stage === "idle" && state.timeline.length === 0)) {
    return null;
  }

  const eta = fmtEta(state.eta_seconds);

  return (
    <div className="fixed bottom-2 left-2 z-30 flex flex-col-reverse">
      <button
        data-testid="stage-toggle"
        onClick={() => setOpen((p) => !p)}
        className={`flex items-center gap-2 bg-white border rounded px-3 py-1 ${T.body} shadow`}
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
        <div className="mb-1 bg-white border rounded shadow w-96 max-h-80 overflow-auto">
          <StageTimeline events={state.timeline} />
        </div>
      ) : null}
    </div>
  );
}
