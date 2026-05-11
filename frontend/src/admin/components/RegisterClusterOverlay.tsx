import type { SegmentBox } from "../types/domain";
import "../styles/box-colors.css";

interface Props {
  /** Boxes on the current page (already filtered by page + visibility). */
  boxes: SegmentBox[];
  /** Same scale BoxOverlay uses, so clusters align pixel-perfectly. */
  scale: number;
}

const REGISTER_KINDS = [
  "toc",
  "list_of_tables",
  "list_of_figures",
  "bibliography",
] as const;

const CLUSTER_PADDING_PX = 6;

/**
 * Renders one wrapping rectangle per (page, register-kind) — a dashed
 * thin border around the bounding box of all boxes of that kind on
 * the current page. Visually groups the Verzeichnis-block (title +
 * column-header + entries) so it reads as one cluster, even though
 * each child still has its own coloured outline.
 *
 * pointer-events: none so the wrapper never intercepts the click
 * targets of the inner boxes.
 */
export function RegisterClusterOverlay({ boxes, scale }: Props): JSX.Element {
  const clusters = REGISTER_KINDS.flatMap((kind) => {
    const members = boxes.filter((b) => b.kind === kind);
    if (members.length === 0) return [];
    const x0 = Math.min(...members.map((b) => b.bbox[0]));
    const y0 = Math.min(...members.map((b) => b.bbox[1]));
    const x1 = Math.max(...members.map((b) => b.bbox[2]));
    const y1 = Math.max(...members.map((b) => b.bbox[3]));
    return [{ kind, x0, y0, x1, y1 }];
  });

  return (
    <>
      {clusters.map(({ kind, x0, y0, x1, y1 }) => (
        <div
          key={kind}
          aria-hidden="true"
          className={`box-${kind}`}
          style={{
            position: "absolute",
            left: x0 * scale - CLUSTER_PADDING_PX,
            top: y0 * scale - CLUSTER_PADDING_PX,
            width: (x1 - x0) * scale + 2 * CLUSTER_PADDING_PX,
            height: (y1 - y0) * scale + 2 * CLUSTER_PADDING_PX,
            border: "1px dashed var(--box-color)",
            borderRadius: 4,
            pointerEvents: "none",
            background: "transparent",
          }}
        />
      ))}
    </>
  );
}
