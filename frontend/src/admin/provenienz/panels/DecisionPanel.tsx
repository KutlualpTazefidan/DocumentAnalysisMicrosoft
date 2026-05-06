import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

export function DecisionPanel({
  node,
  onSelectNode,
}: PanelCommonProps): JSX.Element {
  const payload = node.payload;
  const accepted = String(payload.accepted ?? "");
  const altIndex = payload.alt_index;
  const reason = payload.reason ? String(payload.reason) : null;
  const override = payload.override ? String(payload.override) : null;
  const proposalId = payload.proposal_node_id
    ? String(payload.proposal_node_id)
    : null;

  return (
    <div className="flex flex-col h-full">
      <PanelHeader node={node} onClose={() => onSelectNode(null)} />
      <div className="p-4 space-y-3 flex-1 overflow-y-auto">
        <div>
          <p className={T.tinyBold}>Akzeptiert</p>
          <p className={`text-white ${T.mono}`}>{accepted}</p>
        </div>
        {typeof altIndex === "number" && (
          <div>
            <p className={T.tinyBold}>Alternative-Index</p>
            <p className={`text-white ${T.mono}`}>{altIndex}</p>
          </div>
        )}
        {override && (
          <div>
            <p className={T.tinyBold}>Eigene Eingabe</p>
            <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
              {override}
            </p>
          </div>
        )}
        {reason && (
          <div>
            <p className={T.tinyBold}>Begründung</p>
            <p className={`text-slate-200 ${T.body} whitespace-pre-wrap`}>
              {reason}
            </p>
          </div>
        )}
        {proposalId && (
          <div>
            <p className={T.tinyBold}>Vorschlag</p>
            <button
              type="button"
              onClick={() => onSelectNode(proposalId)}
              className={`text-blue-400 hover:text-blue-300 ${T.mono} truncate block max-w-full`}
            >
              {proposalId}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
