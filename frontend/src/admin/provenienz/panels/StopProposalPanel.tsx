import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

export function StopProposalPanel({
  node,
  onSelectNode,
}: PanelCommonProps): JSX.Element {
  const payload = node.payload;
  const reason = String(payload.reason ?? "");
  const closeSession = Boolean(payload.close_session);
  const anchorId = payload.anchor_node_id
    ? String(payload.anchor_node_id)
    : null;

  return (
    <div className="flex flex-col h-full">
      <PanelHeader node={node} onClose={() => onSelectNode(null)} />
      <div className="p-4 space-y-3 flex-1 overflow-y-auto">
        <div>
          <p className={T.tinyBold}>Begründung</p>
          <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
            {reason}
          </p>
        </div>
        <div>
          <p className={T.tinyBold}>Schließt Sitzung</p>
          <p className={`text-slate-200 ${T.body}`}>
            {closeSession ? "ja" : "nein"}
          </p>
        </div>
        {anchorId && (
          <div>
            <p className={T.tinyBold}>Anker</p>
            <button
              type="button"
              onClick={() => onSelectNode(anchorId)}
              className={`text-blue-400 hover:text-blue-300 ${T.mono} truncate block max-w-full`}
            >
              {anchorId}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
