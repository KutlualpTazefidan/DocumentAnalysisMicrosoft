import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

const ACCEPT_LABEL: Record<string, string> = {
  recommended: "Empfehlung übernommen",
  alt: "Alternative gewählt",
  override: "Eigene Eingabe",
};

/**
 * Read-only audit panel for a decision tile. Shows accepted-mode,
 * actor, timestamp, free-text reason (if any), override text (if any).
 * No actions — decisions are immutable history.
 */
export function DecisionPanel({
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "decision") return <></>;
  const dec = view.decision;
  const p = dec.payload as {
    accepted?: string;
    alt_index?: number;
    reason?: string;
    override?: string;
  };
  const accepted = String(p.accepted ?? "");
  const reason = String(p.reason ?? "").trim();
  const override = String(p.override ?? "").trim();
  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Entscheidung"
        subtitle={ACCEPT_LABEL[accepted] ?? accepted}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div>
          <p className={T.tinyBold}>Modus</p>
          <p className={`text-purple-300 ${T.mono}`}>{accepted}</p>
        </div>
        {accepted === "alt" && p.alt_index !== undefined && (
          <div>
            <p className={T.tinyBold}>Index der Alternative</p>
            <p className={`text-purple-300 ${T.mono}`}>{p.alt_index}</p>
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
            <p className={T.tinyBold}>Begründung des Nutzers</p>
            <p className={`text-slate-200 ${T.body} italic whitespace-pre-wrap`}>
              {reason}
            </p>
          </div>
        )}
        <div>
          <p className={T.tinyBold}>Akteur</p>
          <p className={`text-slate-300 ${T.mono}`}>{dec.actor}</p>
        </div>
        <div>
          <p className={T.tinyBold}>Zeitstempel</p>
          <p className={`text-slate-400 ${T.mono}`}>{dec.created_at}</p>
        </div>
        <div>
          <p className={T.tinyBold}>Knoten-ID</p>
          <p className={`text-slate-400 ${T.mono} text-[11px] break-all`}>
            {dec.node_id}
          </p>
        </div>
      </div>
    </div>
  );
}
