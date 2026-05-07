import { Sparkles, Trash2 } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import {
  useDeleteNode,
  useEvaluate,
  useNextStepStream,
} from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { LiveRunPanel } from "../LiveRunPanel";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

/**
 * Side-panel for an atomic sub-statement. Same agent-flow + manual
 * fallback as SearchResultPanel — but evaluate runs against the
 * SUB-STATEMENT's text (single fact at a time) rather than the
 * full search-hit.
 */
export function SubStatementPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "sub_statement") return <></>;
  const sub = view.sub_statement;
  const text = String((sub.payload as { text?: string }).text ?? "");
  const evaluate = useEvaluate(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const stream = useNextStepStream(token, sessionId);
  const { error: toastError } = useToast();

  async function handleEvaluate(): Promise<void> {
    try {
      await evaluate.mutateAsync({ search_result_node_id: sub.node_id });
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }
  async function handleDelete(): Promise<void> {
    if (!window.confirm("Sub-Aussage + downstream-Bewertungen löschen?")) return;
    try {
      await del.mutateAsync(sub.node_id);
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Sub-Aussage"
        subtitle="atomare Behauptung"
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <p className={`text-fuchsia-100 ${T.body} italic whitespace-pre-wrap`}>
          „{text}"
        </p>
        <LiveRunPanel
          run={stream}
          anchorPreview={text.slice(0, 120)}
          onClose={() => stream.reset()}
        />
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void stream.start(sub.node_id)}
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
          <div className="p-2">
            <button
              type="button"
              onClick={() => void handleEvaluate()}
              disabled={evaluate.isPending}
              className={`w-full px-2 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white ${T.tiny} disabled:opacity-50`}
            >
              {evaluate.isPending ? "…" : "Diese Aussage bewerten"}
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
