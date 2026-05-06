import { useState } from "react";

import { useToast } from "../../../shared/components/useToast";
import { useSearchStep } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

export function TaskPanel({
  sessionId,
  token,
  node,
  onSelectNode,
}: PanelCommonProps): JSX.Element {
  const payload = node.payload;
  const query = String(payload.query ?? "");
  const focusClaimId = payload.focus_claim_id
    ? String(payload.focus_claim_id)
    : null;

  const [topK, setTopK] = useState<number>(5);
  const search = useSearchStep(token, sessionId);
  const { error: toastError } = useToast();

  async function handleSearch(): Promise<void> {
    try {
      const proposal = await search.mutateAsync({
        task_node_id: node.node_id,
        top_k: topK,
      });
      onSelectNode(proposal.node_id);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader node={node} onClose={() => onSelectNode(null)} />
      <div className="p-4 space-y-3 flex-1 overflow-y-auto">
        <div>
          <p className={T.tinyBold}>Suchanfrage</p>
          <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>{query}</p>
        </div>
        {focusClaimId && (
          <div>
            <p className={T.tinyBold}>Fokus-Aussage</p>
            <button
              type="button"
              onClick={() => onSelectNode(focusClaimId)}
              className={`text-blue-400 hover:text-blue-300 ${T.mono} truncate block max-w-full`}
            >
              {focusClaimId}
            </button>
          </div>
        )}
        <div>
          <label
            htmlFor="topk"
            className={`${T.tinyBold} block mb-1`}
          >
            Top-K
          </label>
          <input
            id="topk"
            type="number"
            min={1}
            max={20}
            value={topK}
            onChange={(e) => {
              const v = Number(e.target.value);
              if (!Number.isFinite(v)) return;
              setTopK(Math.max(1, Math.min(20, Math.round(v))));
            }}
            className={`w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
          />
        </div>
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleSearch()}
          disabled={search.isPending}
          className={`w-full px-3 py-2 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} disabled:opacity-50`}
        >
          {search.isPending ? "Suche…" : "Suchen"}
        </button>
        {search.error && (
          <p className={`text-red-400 ${T.tiny}`}>{search.error.message}</p>
        )}
      </footer>
    </div>
  );
}
