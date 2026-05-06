import { useToast } from "../../../shared/components/useToast";
import { useProposeStop } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

export function EvaluationPanel({
  sessionId,
  token,
  node,
  onSelectNode,
}: PanelCommonProps): JSX.Element {
  const payload = node.payload;
  const verdict = String(payload.verdict ?? "");
  const confidence = payload.confidence;
  const reasoning = payload.reasoning ? String(payload.reasoning) : null;
  const claimId = payload.against_claim_id
    ? String(payload.against_claim_id)
    : null;
  const searchResultId = payload.search_result_node_id
    ? String(payload.search_result_node_id)
    : null;

  const stop = useProposeStop(token, sessionId);
  const { error: toastError } = useToast();

  const stopRelevant =
    verdict === "likely-source" || verdict === "partial-support";

  async function handleStop(): Promise<void> {
    try {
      const proposal = await stop.mutateAsync({ anchor_node_id: node.node_id });
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
          <p className={T.tinyBold}>Verdict</p>
          <p className={`text-white ${T.body} font-semibold`}>{verdict}</p>
        </div>
        {typeof confidence === "number" && (
          <div>
            <p className={T.tinyBold}>Konfidenz</p>
            <p className={`text-slate-200 ${T.mono}`}>
              {confidence.toFixed(3)}
            </p>
          </div>
        )}
        {reasoning && (
          <div>
            <p className={T.tinyBold}>Begründung</p>
            <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
              {reasoning}
            </p>
          </div>
        )}
        {claimId && (
          <div>
            <p className={T.tinyBold}>Aussage</p>
            <button
              type="button"
              onClick={() => onSelectNode(claimId)}
              className={`text-blue-400 hover:text-blue-300 ${T.mono} truncate block max-w-full`}
            >
              {claimId}
            </button>
          </div>
        )}
        {searchResultId && (
          <div>
            <p className={T.tinyBold}>Suchtreffer</p>
            <button
              type="button"
              onClick={() => onSelectNode(searchResultId)}
              className={`text-blue-400 hover:text-blue-300 ${T.mono} truncate block max-w-full`}
            >
              {searchResultId}
            </button>
          </div>
        )}
      </div>
      {stopRelevant && (
        <footer className="p-3 border-t border-navy-700 space-y-2">
          <button
            type="button"
            onClick={() => void handleStop()}
            disabled={stop.isPending}
            className={`w-full px-3 py-2 rounded bg-zinc-600 hover:bg-zinc-500 text-white ${T.body} disabled:opacity-50`}
          >
            {stop.isPending ? "Schlage vor…" : "Stopp vorschlagen"}
          </button>
          {stop.error && (
            <p className={`text-red-400 ${T.tiny}`}>{stop.error.message}</p>
          )}
        </footer>
      )}
    </div>
  );
}
