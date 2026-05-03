import { useState } from "react";
import { T } from "../styles/typography";
import {
  useLlmStart,
  useLlmStatus,
  useLlmStop,
  type LlmState,
} from "../hooks/useLlmServer";

/**
 * Status pill + Start/Stop button for the local vLLM subprocess.
 *
 * Mounted at the top of the Synthesise sidebar so admins see the
 * vLLM state before clicking any Generate button. Log tail is hidden
 * by default (collapsible <details>) — appears expanded only when
 * the state is "error" so the user immediately sees what went wrong
 * (most common: VRAM OOM, model download failure, port collision).
 */
interface Props {
  token: string;
}

const STATE_STYLE: Record<LlmState, string> = {
  stopped: "bg-slate-200 text-slate-700",
  starting: "bg-yellow-100 text-yellow-800",
  running: "bg-green-100 text-green-800",
  error: "bg-red-100 text-red-800",
};

const STATE_LABEL: Record<LlmState, string> = {
  stopped: "Gestoppt",
  starting: "Startet…",
  running: "Laeuft",
  error: "Fehler",
};

export function LlmServerPanel({ token }: Props): JSX.Element {
  const status = useLlmStatus(token);
  const start = useLlmStart(token);
  const stop = useLlmStop(token);
  const [logsOpen, setLogsOpen] = useState(false);

  const data = status.data;
  const state: LlmState = data?.state ?? "stopped";
  const isRunning = state === "running" || state === "starting";

  // Auto-expand log tail when there's an error so the cause is visible
  // without needing to click open <details>.
  const showLogsByDefault = state === "error";

  return (
    <section
      className="rounded border border-slate-200 bg-slate-50 p-2 flex flex-col gap-2"
      data-testid="llm-server-panel"
    >
      <div className="flex items-center justify-between">
        <span className={T.tinyBold}>vLLM Server</span>
        <span
          className={`px-2 py-0.5 rounded text-xs font-medium ${STATE_STYLE[state]}`}
          data-testid="llm-state-pill"
        >
          {STATE_LABEL[state]}
        </span>
      </div>

      {data?.model && (
        <p className={`${T.body} text-slate-600 truncate`} title={data.model}>
          {data.model}
        </p>
      )}

      {data && data.vllm_cli_available === false && (
        <p className={`${T.body} text-amber-700 bg-amber-50 rounded p-1`}>
          ⚠ <code>vllm</code> CLI nicht gefunden. Siehe vllm-server/README.md.
        </p>
      )}

      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          aria-label="vLLM starten"
          disabled={isRunning || start.isPending}
          onClick={() => start.mutate()}
          className="px-2 py-1 rounded bg-blue-600 text-white text-xs font-medium hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed"
        >
          {start.isPending ? "…" : "Start"}
        </button>
        <button
          type="button"
          aria-label="vLLM stoppen"
          disabled={!isRunning || stop.isPending}
          onClick={() => stop.mutate()}
          className="px-2 py-1 rounded border border-red-300 text-red-700 text-xs font-medium hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {stop.isPending ? "…" : "Stop"}
        </button>
      </div>

      {data?.error && (
        <p className={`${T.body} text-red-700 bg-red-50 rounded p-1 break-all`}>
          {data.error}
        </p>
      )}

      <details
        open={showLogsByDefault || logsOpen}
        onToggle={(e) => setLogsOpen((e.target as HTMLDetailsElement).open)}
      >
        <summary className={`${T.tiny} cursor-pointer text-slate-600 select-none`}>
          Logs ({data?.log_tail?.length ?? 0})
        </summary>
        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded border border-slate-200 bg-white p-1 text-[10px] leading-snug font-mono text-slate-700">
          {data?.log_tail?.length ? data.log_tail.join("\n") : "(noch keine Logs)"}
        </pre>
      </details>
    </section>
  );
}
