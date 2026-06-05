import { useState } from "react";
import { Sparkles } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteNode,
  useNextStepStream,
  useRegisterLookupStep,
  useSearchStep,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { LiveRunPanel } from "../LiveRunPanel";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";
import { PreReasoningSection } from "./PreReasoningSection";

// Mirror of provenienz/registers.py::_KIND_DETECT_PATTERNS so the panel
// can render a hint like "Verweis erkannt: Tabelle 5" before posting.
// Server re-runs the same detection — this is purely advisory UX.
const _REGISTER_HINT_RES: Array<{ re: RegExp; label: string }> = [
  { re: /\b(?:Tabellen?|Tab\.|Table)\s*(\d+(?:\.\d+)*)/i, label: "Tabelle" },
  { re: /\b(?:Abbildung(?:en)?|Abb\.|Figure|Fig\.)\s*(\d+(?:\.\d+)*)/i, label: "Abbildung" },
  { re: /\[(\d{1,3})\]/, label: "Quelle" },
  {
    re: /\b(?:Kapitel|Abschnitt|Abs\.|Section|Sec\.)\s*(\d+(?:\.\d+)*)/i,
    label: "Kapitel",
  },
];

function detectRegisterHint(query: string): string | null {
  for (const { re, label } of _REGISTER_HINT_RES) {
    const m = re.exec(query);
    if (m) return `${label} ${m[1]}`;
  }
  return null;
}

/**
 * Side panel for a Task tile (the formulated search query). Action:
 * run the search with a configurable top_k. Delete cascades to the
 * results bag + evaluations beneath it.
 */
export function TaskPanel({
  sessionId,
  token,
  view,
  nodes,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  const search = useSearchStep(token, sessionId);
  const registerLookup = useRegisterLookupStep(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const stream = useNextStepStream(token, sessionId);
  const { error: toastError } = useToast();
  const [topK, setTopK] = useState(5);
  if (view.kind !== "task") return <></>;
  const task = view.task;
  const queryText = String(task.payload.query ?? "");
  const registerHint = detectRegisterHint(queryText);
  // Surface the parent claim's research goal alongside the BM25
  // keyword query — they're complementary fields and showing only
  // the keywords made the panel read as cryptic ("Brennelemente TRINO
  // Wärmeleistung 5,6 kW" without context of what's being asked).
  const focusClaimId = String(task.payload.focus_claim_id ?? "");
  const focusClaim = focusClaimId
    ? nodes.find((n) => n.node_id === focusClaimId)
    : undefined;
  const claimGoal = focusClaim
    ? String(focusClaim.payload.goal ?? "").trim()
    : "";
  const claimText = focusClaim
    ? String(focusClaim.payload.text ?? "").trim()
    : "";

  async function handleNextStep(): Promise<void> {
    await stream.start(task.node_id);
  }

  async function handleSearch(): Promise<void> {
    try {
      await search.mutateAsync({ task_node_id: task.node_id, top_k: topK });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleRegisterLookup(): Promise<void> {
    try {
      await registerLookup.mutateAsync({ task_node_id: task.node_id });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleDelete(): Promise<void> {
    if (!window.confirm("Aufgabe und alle Treffer + Bewertungen löschen?")) return;
    try {
      await del.mutateAsync(task.node_id);
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader title="Aufgabe" onClose={() => onSelectView(null)} />
      <div className="p-4 space-y-3 flex-1 overflow-y-auto">
        {(claimGoal || claimText) && (
          <div className="rounded border border-pink-200 bg-pink-50 px-3 py-2 space-y-1">
            {claimGoal && (
              <>
                <p className={`${T.tinyBold} text-pink-700`}>
                  Recherche-Frage zur Aussage
                </p>
                <p className={`text-pink-900 ${T.body}`}>{claimGoal}</p>
              </>
            )}
            {claimText && (
              <p className={`${T.tiny} text-pink-700 italic mt-1`}>
                Aussage: „{claimText}"
              </p>
            )}
          </div>
        )}
        <div>
          <p className={T.tinyBold}>
            Suchanfrage{" "}
            <span className={`${T.tiny} font-normal text-ink-muted`}>
              (BM25-Keywords für den Searcher)
            </span>
          </p>
          <p className={`text-cyan-800 italic ${T.body} whitespace-pre-wrap`}>
            {queryText}
          </p>
        </div>
        {view.hasResults && (
          <p className={`${T.body} text-emerald-700 italic`}>
            Suchtreffer-Bag liegt im nächsten Schritt.
          </p>
        )}
        <PreReasoningSection nodes={nodes} anchorId={task.node_id} />
        {!view.hasResults && (
          <LiveRunPanel
            run={stream}
            anchorPreview={String(task.payload.query ?? "").slice(0, 120)}
            onClose={() => stream.reset()}
          />
        )}
      </div>
      <footer className="p-3 border-t border-line space-y-2">
        {!view.hasResults && (
          <button
            type="button"
            onClick={() => void handleNextStep()}
            disabled={stream.isRunning}
            className={`w-full px-3 py-2 rounded bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold ${T.body} flex items-center justify-center gap-2 disabled:opacity-50`}
          >
            <Sparkles className="w-4 h-4" aria-hidden />
            {stream.isRunning ? "Agent denkt…" : "Was als nächstes?"}
          </button>
        )}
        {!view.hasResults && (
          <details className="rounded border border-line bg-canvas">
            <summary className={`${T.tiny} cursor-pointer px-2 py-1 text-ink-muted`}>
              Manuell suchen
            </summary>
            <div className="p-2 space-y-2">
              <div className="flex items-center gap-2">
                <label className={`${T.tiny} text-ink-muted`}>top_k</label>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={topK}
                  onChange={(e) =>
                    setTopK(Math.max(1, Math.min(20, Number(e.target.value))))
                  }
                  className={`w-16 px-2 py-1 rounded bg-white border border-line text-ink ${T.tiny}`}
                />
              </div>
              <button
                type="button"
                onClick={() => void handleSearch()}
                disabled={search.isPending}
                className={`w-full px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white ${T.tiny} disabled:opacity-50`}
              >
                {search.isPending ? "Suche…" : "Suchen"}
              </button>
              {registerHint && (
                <p className={`${T.tiny} text-amber-700`}>
                  Verweis erkannt: <span className="font-mono">{registerHint}</span>
                </p>
              )}
              <button
                type="button"
                onClick={() => void handleRegisterLookup()}
                disabled={registerLookup.isPending}
                title="Schlägt eine Tabellen-/Abbildungs-/Quellenangabe im jeweiligen Verzeichnis nach. Kein Verweis erkannt → leerer Treffer."
                className={`w-full px-3 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white ${T.tiny} disabled:opacity-50`}
              >
                {registerLookup.isPending ? "Lookup…" : "🔎 Verzeichnis-Lookup"}
              </button>
            </div>
          </details>
        )}
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-bam-red text-bam-red hover:bg-red-50 ${T.body} disabled:opacity-50`}
        >
          {del.isPending ? "…" : "Tile löschen"}
        </button>
        {(search.error || del.error) && (
          <p className={`text-bam-red ${T.tiny}`}>
            {(search.error ?? del.error)?.message}
          </p>
        )}
      </footer>
    </div>
  );
}
