import { CornerDownRight, Sparkles, Trash2 } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteNode,
  useEvaluate,
  useNextStepStream,
  usePromoteSearchResult,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { LiveRunPanel } from "../LiveRunPanel";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

const VERDICT_STYLE: Record<string, string> = {
  "likely-source": "bg-emerald-700 text-emerald-100",
  "partial-support": "bg-amber-600 text-amber-50",
  unrelated: "bg-slate-600 text-slate-200",
  contradicts: "bg-rose-700 text-rose-100",
  manual: "bg-purple-600 text-purple-100",
};

/**
 * Lists every search_result for one task. Per-row "Bewerten" button fires
 * the evaluate route against the upstream claim (which we resolve from the
 * task's focus_claim_id payload field).
 */
export function SearchResultsBagPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "search_results_bag") return <></>;
  const bagView = view;
  const claimId = String(bagView.task.payload.focus_claim_id ?? "");
  const evaluate = useEvaluate(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const promote = usePromoteSearchResult(token, sessionId);
  // Single shared next_step stream for the whole panel — only one
  // agent-run at a time. Per-row buttons set the anchor when fired.
  const stream = useNextStepStream(token, sessionId);
  const { error: toastError } = useToast();

  async function handleEvaluate(resultId: string): Promise<void> {
    if (!claimId) {
      toastError(
        "Kein verknüpfter Claim auf dem Task — kann nicht bewertet werden.",
      );
      return;
    }
    try {
      await evaluate.mutateAsync({
        search_result_node_id: resultId,
        against_claim_id: claimId,
      });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  async function handleDeleteRow(resultId: string): Promise<void> {
    try {
      // Backend cascades — deletes the result + its evaluation + any
      // promoted-chunk subtree rooted at it.
      await del.mutateAsync(resultId);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  async function handlePromote(resultId: string): Promise<void> {
    try {
      const newChunk = await promote.mutateAsync(resultId);
      // Land on the new chunk so the user sees it spawn + can extract from it.
      onSelectView(`view:${newChunk.node_id}`);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  const evaluatedCount = bagView.rows.filter((r) => r.evaluation).length;

  async function handleDeleteBag(): Promise<void> {
    if (!bagView.searchProposalId) {
      toastError(
        "Diese Trefferliste hat keine zugeordnete Such-Aktion (legacy) — " +
          "einzelne Zeilen über Mülleimer löschen.",
      );
      return;
    }
    if (
      !window.confirm(
        `Diese gesamte Suchtreffer-Liste (${bagView.rows.length} Treffer) und alle ` +
          `Bewertungen + ggf. weiterführenden Recherchen entfernen?`,
      )
    )
      return;
    try {
      await del.mutateAsync(bagView.searchProposalId);
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Suchtreffer"
        subtitle={`${bagView.rows.length} Treffer · ${evaluatedCount} bewertet`}
        onClose={() => onSelectView(null)}
      />
      {bagView.searchProposalId && (
        <div className="px-3 pt-2">
          <button
            type="button"
            onClick={() => void handleDeleteBag()}
            disabled={del.isPending}
            className={`w-full px-2 py-1.5 rounded border border-red-700/40 bg-red-900/20 text-red-300 hover:bg-red-900/40 ${T.tiny} flex items-center justify-center gap-1 disabled:opacity-50`}
            title="Diese Suche und alle ihre Treffer + Bewertungen löschen"
          >
            <Trash2 className="w-3 h-3" aria-hidden />
            {del.isPending ? "…" : "Bag löschen"}
          </button>
        </div>
      )}
      <div className="p-3 space-y-2 flex-1 overflow-y-auto">
        {/* Live-Run-Panel sichtbar sobald ein Agent-Lauf für eine
            Zeile gestartet wurde. Header zeigt den Treffer-Text als
            Anker, sodass man sieht für welche Zeile gerade gerechnet
            wird. */}
        <LiveRunPanel
          run={stream}
          anchorPreview={undefined}
          onClose={() => stream.reset()}
        />
        {bagView.rows.map((row) => {
          const result = row.result;
          const evalNode = row.evaluation;
          const verdict = evalNode
            ? String(evalNode.payload.verdict ?? "")
            : null;
          const score = Number(result.payload.score ?? 0);
          const boxId = String(result.payload.box_id ?? "");
          const text = String(result.payload.text ?? "");
          const reasoning = evalNode
            ? String(evalNode.payload.reasoning ?? "")
            : null;
          const confidence = evalNode
            ? Number(evalNode.payload.confidence ?? 0)
            : null;
          return (
            <div
              key={result.node_id}
              className="rounded border border-navy-600 bg-navy-800/60 p-2"
            >
              <div className={`flex items-center gap-2 ${T.tiny}`}>
                <span className="font-mono text-blue-300">{boxId}</span>
                <span className="text-slate-400">
                  Score {score.toFixed(2)}
                </span>
                {verdict && (
                  <span
                    className={`ml-auto px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide ${
                      VERDICT_STYLE[verdict] ?? "bg-slate-600 text-slate-200"
                    }`}
                  >
                    {verdict}
                    {confidence !== null && ` · ${confidence.toFixed(2)}`}
                  </span>
                )}
              </div>
              <p className={`text-slate-200 ${T.body} mt-1 line-clamp-3`}>
                {text}
              </p>
              {reasoning && (
                <p className={`text-slate-400 ${T.tiny} italic mt-1`}>
                  „{reasoning}"
                </p>
              )}
              {/* Agent-Vorschlag (primary) — fragt das Modell ob diese
                  Zeile evaluate, promote oder propose_stop bekommen
                  soll. Manueller Pfad bleibt im Akkordeon erreichbar. */}
              <div className="mt-2 space-y-1.5">
                <button
                  type="button"
                  onClick={() => void stream.start(result.node_id)}
                  disabled={stream.isRunning}
                  className={`w-full px-2 py-1.5 rounded bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold ${T.tiny} flex items-center justify-center gap-1 disabled:opacity-50`}
                >
                  <Sparkles className="w-3 h-3" aria-hidden />
                  {stream.isRunning ? "Agent denkt…" : "Was als nächstes?"}
                </button>
                <details className="rounded border border-navy-700 bg-navy-900/40">
                  <summary
                    className={`${T.tiny} cursor-pointer px-2 py-1 text-slate-400`}
                  >
                    Manuell wählen
                  </summary>
                  <div className="p-2 flex gap-2">
                    {!evalNode && (
                      <button
                        type="button"
                        onClick={() => void handleEvaluate(result.node_id)}
                        disabled={evaluate.isPending}
                        className={`flex-1 px-2 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white ${T.tiny} disabled:opacity-50`}
                      >
                        {evaluate.isPending ? "…" : "Bewerten"}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => void handlePromote(result.node_id)}
                      disabled={promote.isPending}
                      className={`flex-1 px-2 py-1 rounded bg-purple-600 hover:bg-purple-500 text-white ${T.tiny} disabled:opacity-50 flex items-center justify-center gap-1`}
                      title="Diesen Treffer als neuen Chunk öffnen"
                    >
                      <CornerDownRight className="w-3 h-3" aria-hidden />
                      {promote.isPending ? "…" : "Weiter erforschen"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleDeleteRow(result.node_id)}
                      disabled={del.isPending}
                      className={`px-2 py-1 rounded text-red-400 hover:bg-red-900/30 ${T.tiny} disabled:opacity-50`}
                      title="Treffer entfernen"
                      aria-label="Treffer entfernen"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </details>
              </div>
            </div>
          );
        })}
      </div>
      {evaluate.error && (
        <p className={`text-red-400 ${T.tiny} px-3 pb-2`}>
          {evaluate.error.message}
        </p>
      )}
    </div>
  );
}
