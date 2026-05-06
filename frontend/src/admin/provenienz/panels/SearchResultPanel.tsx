import { useMemo, useState } from "react";

import { useToast } from "../../../shared/components/useToast";
import { useEvaluate } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

export function SearchResultPanel({
  sessionId,
  token,
  node,
  nodes,
  onSelectNode,
}: PanelCommonProps): JSX.Element {
  const payload = node.payload;
  const boxId = payload.box_id ? String(payload.box_id) : null;
  const text = String(payload.text ?? "");
  const score = payload.score;
  const scoreLabel = typeof score === "number" ? score.toFixed(3) : null;
  const searcher = payload.searcher ? String(payload.searcher) : null;
  const taskNodeId = payload.task_node_id
    ? String(payload.task_node_id)
    : null;

  const claimNodes = useMemo(
    () => nodes.filter((n) => n.kind === "claim"),
    [nodes],
  );

  // Default the picker to the claim that triggered this search:
  // search_result.payload.task_node_id → task.payload.focus_claim_id
  const defaultClaimId = useMemo<string>(() => {
    if (taskNodeId) {
      const taskNode = nodes.find((n) => n.node_id === taskNodeId);
      const focusId = taskNode?.payload.focus_claim_id;
      if (typeof focusId === "string" && focusId) return focusId;
    }
    return claimNodes[0]?.node_id ?? "";
  }, [nodes, taskNodeId, claimNodes]);

  const [claimId, setClaimId] = useState<string>(defaultClaimId);
  const evaluate = useEvaluate(token, sessionId);
  const { error: toastError } = useToast();

  async function handleEvaluate(): Promise<void> {
    if (!claimId) return;
    try {
      const proposal = await evaluate.mutateAsync({
        search_result_node_id: node.node_id,
        against_claim_id: claimId,
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
        {boxId && (
          <div>
            <p className={T.tinyBold}>Box</p>
            <p className={`text-white ${T.mono}`}>{boxId}</p>
          </div>
        )}
        <div>
          <p className={T.tinyBold}>Text</p>
          <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>{text}</p>
        </div>
        {scoreLabel !== null && (
          <div>
            <p className={T.tinyBold}>Score</p>
            <p className={`text-slate-200 ${T.mono}`}>{scoreLabel}</p>
          </div>
        )}
        {searcher && (
          <div>
            <p className={T.tinyBold}>Searcher</p>
            <p className={`text-slate-200 ${T.mono}`}>{searcher}</p>
          </div>
        )}
        <div>
          <label htmlFor="against-claim" className={`${T.tinyBold} block mb-1`}>
            Gegen welche Aussage bewerten?
          </label>
          <select
            id="against-claim"
            value={claimId}
            onChange={(e) => setClaimId(e.target.value)}
            className={`w-full px-2 py-1 rounded bg-navy-900 border border-navy-600 text-white ${T.body}`}
          >
            {claimNodes.length === 0 && (
              <option value="">Keine Aussagen vorhanden</option>
            )}
            {claimNodes.map((c) => {
              const txt = String(c.payload.text ?? "").slice(0, 60);
              return (
                <option key={c.node_id} value={c.node_id}>
                  {txt || c.node_id}
                </option>
              );
            })}
          </select>
        </div>
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleEvaluate()}
          disabled={evaluate.isPending || !claimId}
          className={`w-full px-3 py-2 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} disabled:opacity-50`}
        >
          {evaluate.isPending ? "Bewerte…" : "Bewerten"}
        </button>
        {evaluate.error && (
          <p className={`text-red-400 ${T.tiny}`}>{evaluate.error.message}</p>
        )}
      </footer>
    </div>
  );
}
