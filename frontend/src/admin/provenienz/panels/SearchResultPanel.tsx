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
 * Detail panel for a search_result tile that's been extracted from
 * the bag (because it has downstream agent-flow). Same controls as
 * the per-row block in SearchResultsBagPanel — primary
 * "Was als nächstes?" button + manual-fallback accordion.
 */
export function SearchResultPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "search_result") return <></>;
  const result = view.result;
  const evalNode = view.evaluation;
  const p = result.payload as { box_id?: string; score?: number; text?: string };
  const verdict = evalNode
    ? String((evalNode.payload as { verdict?: string }).verdict ?? "")
    : null;
  const reasoning = evalNode
    ? String((evalNode.payload as { reasoning?: string }).reasoning ?? "")
    : null;
  const confidence = evalNode
    ? Number((evalNode.payload as { confidence?: number }).confidence ?? 0)
    : null;

  const evaluate = useEvaluate(token, sessionId);
  const promote = usePromoteSearchResult(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const stream = useNextStepStream(token, sessionId);
  const { error: toastError } = useToast();

  async function handleEvaluate(): Promise<void> {
    try {
      await evaluate.mutateAsync({ search_result_node_id: result.node_id });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handlePromote(): Promise<void> {
    try {
      const newChunk = await promote.mutateAsync(result.node_id);
      onSelectView(`view:${newChunk.node_id}`);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleDelete(): Promise<void> {
    if (!window.confirm("Treffer + abhängige Bewertung/Chunks löschen?")) return;
    try {
      await del.mutateAsync(result.node_id);
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Suchtreffer"
        subtitle={String(p.box_id ?? "")}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div className={`flex items-center gap-2 ${T.tiny}`}>
          <span className="text-slate-400">
            Score {Number(p.score ?? 0).toFixed(2)}
          </span>
          {verdict && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide ${
                VERDICT_STYLE[verdict] ?? "bg-slate-600 text-slate-200"
              }`}
            >
              {verdict}
              {confidence !== null && ` · ${confidence.toFixed(2)}`}
            </span>
          )}
        </div>
        <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
          {String(p.text ?? "")}
        </p>
        {reasoning && (
          <div>
            <p className={T.tinyBold}>Bewertungs-Begründung</p>
            <p className={`text-slate-300 ${T.body} italic mt-1`}>
              „{reasoning}"
            </p>
          </div>
        )}
        <LiveRunPanel run={stream} onClose={() => stream.reset()} />
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void stream.start(result.node_id)}
          disabled={stream.isRunning}
          className={`w-full px-3 py-2 rounded bg-amber-500 hover:bg-amber-400 text-amber-950 font-semibold ${T.body} flex items-center justify-center gap-2 disabled:opacity-50`}
        >
          <Sparkles className="w-4 h-4" aria-hidden />
          {stream.isRunning ? "Agent denkt…" : "Was als nächstes?"}
        </button>
        <details className="rounded border border-navy-700 bg-navy-900/40">
          <summary className={`${T.tiny} cursor-pointer px-2 py-1 text-slate-400`}>
            Manuell wählen
          </summary>
          <div className="p-2 flex gap-2">
            {!evalNode && (
              <button
                type="button"
                onClick={() => void handleEvaluate()}
                disabled={evaluate.isPending}
                className={`flex-1 px-2 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white ${T.tiny} disabled:opacity-50`}
              >
                {evaluate.isPending ? "…" : "Bewerten"}
              </button>
            )}
            <button
              type="button"
              onClick={() => void handlePromote()}
              disabled={promote.isPending}
              className={`flex-1 px-2 py-1 rounded bg-purple-600 hover:bg-purple-500 text-white ${T.tiny} disabled:opacity-50 flex items-center justify-center gap-1`}
              title="Diesen Treffer als neuen Chunk öffnen"
            >
              <CornerDownRight className="w-3 h-3" aria-hidden />
              {promote.isPending ? "…" : "Weiter erforschen"}
            </button>
          </div>
        </details>
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-red-700 text-red-300 hover:bg-red-900/30 ${T.body} disabled:opacity-50 flex items-center justify-center gap-2`}
        >
          <Trash2 className="w-3.5 h-3.5" />
          {del.isPending ? "…" : "Tile löschen"}
        </button>
      </footer>
    </div>
  );
}
