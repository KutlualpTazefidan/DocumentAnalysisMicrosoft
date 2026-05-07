import { useEffect, useRef, useState } from "react";
import { AlertCircle, ChevronDown, Loader2, Play, Square } from "lucide-react";

import {
  useLlmModels,
  useLlmSelectModel,
  useLlmStart,
  useLlmStatus,
  useLlmStop,
  type LlmState,
  type ModelOption,
} from "../hooks/useLlmServer";

interface Props {
  token: string;
}

const STATE_DOT: Record<LlmState, string> = {
  stopped: "bg-slate-400",
  starting: "bg-yellow-400 animate-pulse",
  running: "bg-emerald-400",
  error: "bg-red-500",
};

const STATE_LABEL: Record<LlmState, string> = {
  stopped: "gestoppt",
  starting: "startet",
  running: "läuft",
  error: "Fehler",
};

/**
 * Top-bar widget: status pill + model picker + unified Start/Stop button.
 * Mounted in AdminShell so the LLM is reachable from every page.
 *
 * State-driven button:
 *   stopped → blue ▶ Start  (calls /llm/start)
 *   starting → spinner + "Startet…" (disabled, polls status)
 *   running → red ■ Stop  (calls /llm/stop)
 *   error → orange ⟲ Neu starten (Stop + retry mental model)
 *
 * Click status dot → popover with logs, error detail, vllm-cli warning.
 */
export function LlmTopBarControl({ token }: Props): JSX.Element {
  const status = useLlmStatus(token);
  const models = useLlmModels(token);
  const start = useLlmStart(token);
  const stop = useLlmStop(token);
  const selectModel = useLlmSelectModel(token);

  const [popoverOpen, setPopoverOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement | null>(null);

  // Close popover on outside click. Cheap manual handler — no need
  // to pull in a popover lib for this single instance.
  useEffect(() => {
    if (!popoverOpen) return;
    const onClick = (e: MouseEvent): void => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopoverOpen(false);
      }
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [popoverOpen]);

  const data = status.data;
  const state: LlmState = data?.state ?? "stopped";
  const cliMissing = data?.vllm_cli_available === false;
  const hasError = state === "error" || !!data?.error;

  return (
    <div
      className="relative flex items-center gap-2 text-slate-100"
      data-testid="llm-topbar"
    >
      {/* Status pill (clickable → popover) */}
      <button
        type="button"
        onClick={() => setPopoverOpen((o) => !o)}
        className="flex items-center gap-1.5 px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-xs"
        title="Logs / Details anzeigen"
      >
        <span
          className={`w-2 h-2 rounded-full ${STATE_DOT[state]}`}
          aria-hidden
        />
        <span className="font-medium">vLLM</span>
        <span className="text-white/70">{STATE_LABEL[state]}</span>
        {hasError && <AlertCircle className="w-3.5 h-3.5 text-red-300" aria-hidden />}
      </button>

      {/* Model picker */}
      <ModelPicker
        models={models.data?.models ?? []}
        current={data?.model ?? models.data?.current ?? ""}
        onSelect={(name) => selectModel.mutate(name)}
        disabled={selectModel.isPending}
        running={state === "running" || state === "starting"}
      />

      {/* Unified Start/Stop button */}
      <ActionButton
        state={state}
        startBusy={start.isPending}
        stopBusy={stop.isPending}
        cliMissing={cliMissing}
        onStart={() => start.mutate()}
        onStop={() => stop.mutate()}
      />

      {/* Popover — anchored to this control's right edge so the layout
          works whether the control sits in the top header or a sub-row. */}
      {popoverOpen && (
        <div
          ref={popoverRef}
          className="absolute top-full right-0 mt-2 z-50 w-[480px] max-w-[90vw] rounded-lg border border-slate-300 bg-white text-slate-900 shadow-xl p-3 space-y-2"
          data-testid="llm-topbar-popover"
        >
          <PopoverContent
            state={state}
            model={data?.model ?? null}
            error={data?.error ?? null}
            logs={data?.log_tail ?? []}
            cliMissing={cliMissing}
            selectError={selectModel.error?.message ?? null}
          />
        </div>
      )}
    </div>
  );
}

function ActionButton({
  state,
  startBusy,
  stopBusy,
  cliMissing,
  onStart,
  onStop,
}: {
  state: LlmState;
  startBusy: boolean;
  stopBusy: boolean;
  cliMissing: boolean;
  onStart: () => void;
  onStop: () => void;
}): JSX.Element {
  if (cliMissing) {
    return (
      <button
        type="button"
        disabled
        className="px-2 py-1 rounded bg-slate-300 text-slate-600 text-xs flex items-center gap-1 cursor-not-allowed"
        title="vllm CLI nicht installiert — siehe vllm-server/README.md"
      >
        <AlertCircle className="w-3.5 h-3.5" aria-hidden />
        nicht installiert
      </button>
    );
  }
  if (state === "running") {
    return (
      <button
        type="button"
        onClick={onStop}
        disabled={stopBusy}
        aria-label="vLLM stoppen"
        className="px-2.5 py-1 rounded bg-red-600 hover:bg-red-500 text-white text-xs font-semibold flex items-center gap-1 disabled:opacity-50"
      >
        {stopBusy ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />
        ) : (
          <Square className="w-3.5 h-3.5" aria-hidden />
        )}
        Stop
      </button>
    );
  }
  if (state === "starting") {
    return (
      <button
        type="button"
        disabled
        aria-label="vLLM startet"
        className="px-2.5 py-1 rounded bg-yellow-600/80 text-white text-xs font-semibold flex items-center gap-1 cursor-wait"
      >
        <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />
        Startet…
      </button>
    );
  }
  // stopped or error
  return (
    <button
      type="button"
      onClick={onStart}
      disabled={startBusy}
      aria-label={state === "error" ? "vLLM neu starten" : "vLLM starten"}
      className={`px-2.5 py-1 rounded text-white text-xs font-semibold flex items-center gap-1 disabled:opacity-50 ${
        state === "error"
          ? "bg-orange-600 hover:bg-orange-500"
          : "bg-emerald-600 hover:bg-emerald-500"
      }`}
    >
      {startBusy ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden />
      ) : (
        <Play className="w-3.5 h-3.5" aria-hidden />
      )}
      {state === "error" ? "Neustart" : "Start"}
    </button>
  );
}

function ModelPicker({
  models,
  current,
  onSelect,
  disabled,
  running,
}: {
  models: ModelOption[];
  current: string;
  onSelect: (name: string) => void;
  disabled: boolean;
  running: boolean;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent): void => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  const currentLabel =
    models.find((m) => m.name === current)?.label ??
    (current ? current.split("/").pop() : "Modell wählen");

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={disabled || models.length === 0}
        className="px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-xs flex items-center gap-1 disabled:opacity-50 max-w-[200px]"
        title="Modell auswählen — wirkt erst beim nächsten Start"
      >
        <span className="truncate">{currentLabel}</span>
        <ChevronDown className="w-3 h-3 shrink-0" aria-hidden />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 w-[400px] rounded-lg border border-slate-300 bg-white text-slate-900 shadow-xl py-1">
          {running && (
            <p className="px-3 py-2 text-[11px] text-amber-700 bg-amber-50 italic border-b border-slate-200">
              vLLM läuft — Modellwechsel wirkt erst nach Stop + Start.
            </p>
          )}
          <ul className="max-h-96 overflow-y-auto">
            {models.map((m) => {
              const active = m.name === current;
              return (
                <li key={m.name}>
                  <button
                    type="button"
                    onClick={() => {
                      onSelect(m.name);
                      setOpen(false);
                    }}
                    className={`w-full text-left px-3 py-2 hover:bg-slate-100 ${
                      active ? "bg-blue-50" : ""
                    }`}
                  >
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-[11px] text-slate-500 truncate">
                        {m.name}
                      </span>
                      {active && (
                        <span className="px-1.5 py-px rounded text-[10px] font-semibold bg-blue-700 text-white">
                          aktiv
                        </span>
                      )}
                      {!m.fits_24gb_bf16 && (
                        <span className="px-1.5 py-px rounded text-[10px] font-semibold bg-amber-700 text-white">
                          braucht Quantisierung
                        </span>
                      )}
                    </div>
                    <p className="text-[12px] font-medium text-slate-800 mt-0.5">
                      {m.label}
                    </p>
                    <p className="text-[11px] text-slate-600 mt-0.5">
                      {m.parameters_b}B · ~{m.vram_bf16_gb} GB bf16 · {m.license}
                    </p>
                    <p className="text-[11px] text-slate-500 italic mt-0.5">
                      {m.notes}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function PopoverContent({
  state,
  model,
  error,
  logs,
  cliMissing,
  selectError,
}: {
  state: LlmState;
  model: string | null;
  error: string | null;
  logs: string[];
  cliMissing: boolean;
  selectError: string | null;
}): JSX.Element {
  return (
    <>
      <header className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">vLLM-Server-Details</h3>
        <span className="text-xs text-slate-500">{STATE_LABEL[state]}</span>
      </header>
      {model && (
        <p className="text-xs text-slate-700">
          <span className="text-slate-500">Modell: </span>
          <code>{model}</code>
        </p>
      )}
      {cliMissing && (
        <p className="text-xs text-amber-800 bg-amber-50 rounded p-2">
          ⚠ <code>vllm</code>-CLI nicht gefunden. Setup-Anleitung in
          <code> vllm-server/README.md</code>.
        </p>
      )}
      {error && (
        <div className="text-xs text-red-800 bg-red-50 rounded p-2 break-all">
          <span className="font-semibold">Fehler: </span>
          {error}
        </div>
      )}
      {selectError && (
        <p className="text-xs text-red-800 bg-red-50 rounded p-2 break-all">
          Modell-Wechsel fehlgeschlagen: {selectError}
        </p>
      )}
      <details open={state === "starting" || state === "error"}>
        <summary className="cursor-pointer text-xs text-slate-600 select-none">
          Logs ({logs.length})
        </summary>
        <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded border border-slate-200 bg-slate-50 p-2 text-[10px] leading-snug font-mono text-slate-700">
          {logs.length ? logs.join("\n") : "(noch keine Logs)"}
        </pre>
      </details>
    </>
  );
}
