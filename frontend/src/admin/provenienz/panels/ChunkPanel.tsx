import { useToast } from "../../../shared/components/useToast";
import { useExtractClaims } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

export function ChunkPanel({
  sessionId,
  token,
  node,
  onSelectNode,
}: PanelCommonProps): JSX.Element {
  const payload = node.payload;
  const text = String(payload.text ?? "");
  const boxId = payload.box_id ? String(payload.box_id) : null;

  const extract = useExtractClaims(token, sessionId);
  const { error: toastError } = useToast();

  async function handleExtract(): Promise<void> {
    try {
      const proposal = await extract.mutateAsync({ chunk_node_id: node.node_id });
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
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <button
          type="button"
          onClick={() => void handleExtract()}
          disabled={extract.isPending}
          className={`w-full px-3 py-2 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} disabled:opacity-50`}
        >
          {extract.isPending ? "Extrahiere…" : "Aussagen extrahieren"}
        </button>
        {extract.error && (
          <p className={`text-red-400 ${T.tiny}`}>{extract.error.message}</p>
        )}
      </footer>
    </div>
  );
}
