import { useToast } from "../../../shared/components/useToast";
import { useFormulateTask, useProposeStop } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

export function ClaimPanel({
  sessionId,
  token,
  node,
  onSelectNode,
}: PanelCommonProps): JSX.Element {
  const payload = node.payload;
  const text = String(payload.text ?? "");
  const focusChunkId = payload.focus_chunk_id
    ? String(payload.focus_chunk_id)
    : null;

  const formulate = useFormulateTask(token, sessionId);
  const stop = useProposeStop(token, sessionId);
  const { error: toastError } = useToast();

  async function handleFormulate(): Promise<void> {
    try {
      const proposal = await formulate.mutateAsync({
        claim_node_id: node.node_id,
      });
      onSelectNode(proposal.node_id);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  async function handleStop(): Promise<void> {
    try {
      const proposal = await stop.mutateAsync({ anchor_node_id: node.node_id });
      onSelectNode(proposal.node_id);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  const pending = formulate.isPending || stop.isPending;

  return (
    <div className="flex flex-col h-full">
      <PanelHeader node={node} onClose={() => onSelectNode(null)} />
      <div className="p-4 space-y-3 flex-1 overflow-y-auto">
        <div>
          <p className={T.tinyBold}>Aussage</p>
          <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>{text}</p>
        </div>
        {focusChunkId && (
          <div>
            <p className={T.tinyBold}>Fokus-Chunk</p>
            <button
              type="button"
              onClick={() => onSelectNode(focusChunkId)}
              className={`text-blue-400 hover:text-blue-300 ${T.mono} truncate block max-w-full`}
            >
              {focusChunkId}
            </button>
          </div>
        )}
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleFormulate()}
          disabled={pending}
          className={`w-full px-3 py-2 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} disabled:opacity-50`}
        >
          {formulate.isPending ? "Formuliere…" : "Aufgabe formulieren"}
        </button>
        <button
          type="button"
          onClick={() => void handleStop()}
          disabled={pending}
          className={`w-full px-3 py-2 rounded bg-zinc-600 hover:bg-zinc-500 text-white ${T.body} disabled:opacity-50`}
        >
          {stop.isPending ? "Schlage vor…" : "Stopp vorschlagen"}
        </button>
        {formulate.error && (
          <p className={`text-red-400 ${T.tiny}`}>{formulate.error.message}</p>
        )}
        {stop.error && (
          <p className={`text-red-400 ${T.tiny}`}>{stop.error.message}</p>
        )}
      </footer>
    </div>
  );
}
