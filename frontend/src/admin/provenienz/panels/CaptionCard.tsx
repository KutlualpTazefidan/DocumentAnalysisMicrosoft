import { T } from "../../styles/typography";

interface Props {
  captionText: string | null | undefined;
  captionBoxId?: string | null;
}

/**
 * Cyan caption-info card. Used by ChunkPanel and SearchResultPanel
 * with the same code path; consolidated here so the two stay in
 * sync (label, padding, border tone).
 */
export function CaptionCard({ captionText, captionBoxId }: Props): JSX.Element | null {
  if (!captionText || !String(captionText).trim()) return null;
  return (
    <div className="rounded border border-cyan-700/40 bg-cyan-950/20 px-3 py-2">
      <p className={`${T.tinyBold} text-cyan-300`}>
        📑 Caption{captionBoxId ? ` (${captionBoxId})` : ""}
      </p>
      <p className={`text-cyan-100 ${T.body} mt-0.5`}>{captionText}</p>
    </div>
  );
}
