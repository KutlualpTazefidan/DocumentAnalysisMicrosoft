import { T } from "../../styles/typography";
import type { ProvNode } from "../../hooks/useProvenienz";

interface Props {
  nodes: ProvNode[];
  anchorId: string;
}

/**
 * Render the pre_reasoning ("warum dieser Schritt jetzt") of the most
 * recent action_proposal anchored on this tile, so the user can see
 * the agent's reasoning without navigating to the proposal-tile.
 *
 * Hidden when no proposal is anchored here yet.
 */
export function PreReasoningSection({ nodes, anchorId }: Props): JSX.Element | null {
  // Walk all action_proposal Nodes whose payload.anchor_node_id matches.
  // Take the most recent one (latest created_at).
  const proposals = nodes
    .filter(
      (n) =>
        n.kind === "action_proposal" &&
        (n.payload as { anchor_node_id?: string }).anchor_node_id === anchorId,
    )
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  const latest = proposals[0];
  if (!latest) return null;
  const preReasoning = String(
    (latest.payload as { pre_reasoning?: string }).pre_reasoning ?? "",
  ).trim();
  if (!preReasoning) return null;
  const stepKind = String(
    (latest.payload as { step_kind?: string }).step_kind ?? "",
  );
  return (
    <div className="rounded border border-amber-700/30 bg-amber-950/10 px-3 py-2">
      <p className={`${T.tinyBold} text-amber-300`}>
        Vor-Reasoning · letzter geplanter Schritt
        {stepKind && (
          <span className="ml-1 font-normal text-amber-300/70">({stepKind})</span>
        )}
      </p>
      <p className={`text-amber-100 ${T.body} italic mt-0.5`}>{preReasoning}</p>
    </div>
  );
}
