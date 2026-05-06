import { useState } from "react";

import { useToast } from "../../../shared/components/useToast";
import { useDeleteNode, useSearchStep } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

/**
 * Side panel for a Task tile (the formulated search query). Action:
 * run the search with a configurable top_k. Delete cascades to the
 * results bag + evaluations beneath it.
 */
export function TaskPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "task") return <></>;
  const task = view.task;
  const search = useSearchStep(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const { error: toastError } = useToast();
  const [topK, setTopK] = useState(5);

  async function handleSearch(): Promise<void> {
    try {
      await search.mutateAsync({ task_node_id: task.node_id, top_k: topK });
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
        <div>
          <p className={T.tinyBold}>Suchanfrage</p>
          <p className={`text-cyan-200 italic ${T.body} whitespace-pre-wrap`}>
            {String(task.payload.query ?? "")}
          </p>
        </div>
        {view.hasResults && (
          <p className={`${T.body} text-emerald-300 italic`}>
            Suchtreffer-Bag liegt im nächsten Schritt.
          </p>
        )}
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        {!view.hasResults && (
          <>
            <div className="flex items-center gap-2">
              <label className={`${T.tiny} text-slate-300`}>top_k</label>
              <input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(e) =>
                  setTopK(Math.max(1, Math.min(20, Number(e.target.value))))
                }
                className={`w-16 px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
              />
            </div>
            <button
              type="button"
              onClick={() => void handleSearch()}
              disabled={search.isPending}
              className={`w-full px-3 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-white ${T.body} disabled:opacity-50`}
            >
              {search.isPending ? "Suche…" : "Suchen"}
            </button>
          </>
        )}
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-red-700 text-red-300 hover:bg-red-900/30 ${T.body} disabled:opacity-50`}
        >
          {del.isPending ? "…" : "Tile löschen"}
        </button>
        {(search.error || del.error) && (
          <p className={`text-red-400 ${T.tiny}`}>
            {(search.error ?? del.error)?.message}
          </p>
        )}
      </footer>
    </div>
  );
}
