// frontend/src/local-pdf/components/BoxOverlay.tsx
import { useEffect, useRef, useState } from "react";
import type { SegmentBox } from "../types/domain";
import "../styles/box-colors.css";
import { T } from "../styles/typography";

interface Props {
  box: SegmentBox;
  selected: boolean;
  deactivated?: boolean;
  /** Select-only: no drag/resize handles. Used on finished/locked pages
   *  where the geometry (and thus a re-extract) must not change. */
  readOnly?: boolean;
  onSelect: (boxId: string) => void;
  /** Fired ONCE on mouse-up with the final bbox — never per mouse-move — so a
   *  drag persists (and re-extracts) a single time instead of per pixel. */
  onCommit: (boxId: string, bbox: [number, number, number, number]) => void;
  scale: number;
}

export function BoxOverlay({ box, selected, deactivated = false, readOnly = false, onSelect, onCommit, scale }: Props): JSX.Element {
  const [drag, setDrag] = useState<{ corner: string; sx: number; sy: number; orig: [number, number, number, number] } | null>(null);
  // Live drag preview — drives the visual during a drag with no network
  // round-trip; committed + cleared on mouse-up.
  const [preview, setPreview] = useState<[number, number, number, number] | null>(null);
  // Latest onCommit in a ref so the window listeners don't tear down on a
  // parent re-render mid-drag.
  const onCommitRef = useRef(onCommit);
  onCommitRef.current = onCommit;
  // Latest dragged bbox, read on mouse-up. Kept in a ref so the commit
  // happens in the event handler (pure) — never inside a setState updater,
  // which React StrictMode double-invokes (that would re-extract twice).
  const previewRef = useRef<[number, number, number, number] | null>(null);

  const [x0, y0, x1, y1] = preview ?? box.bbox;

  const style: React.CSSProperties = {
    left: x0 * scale,
    top: y0 * scale,
    width: (x1 - x0) * scale,
    height: (y1 - y0) * scale,
    ...(deactivated ? { opacity: 0.35, borderStyle: "dashed" } : {}),
  };
  const cls = ["box-outline", `box-${box.kind}`];
  if (selected) cls.push("selected");
  if (box.confidence < 0.7) cls.push("low-confidence");
  if (deactivated) cls.push("deactivated");

  useEffect(() => {
    if (!drag) return;
    function onMove(e: MouseEvent) {
      const dx = (e.clientX - drag!.sx) / scale;
      const dy = (e.clientY - drag!.sy) / scale;
      const [ox0, oy0, ox1, oy1] = drag!.orig;
      let n: [number, number, number, number] = [ox0, oy0, ox1, oy1];
      if (drag!.corner === "tl") n = [ox0 + dx, oy0 + dy, ox1, oy1];
      else if (drag!.corner === "tr") n = [ox0, oy0 + dy, ox1 + dx, oy1];
      else if (drag!.corner === "bl") n = [ox0 + dx, oy0, ox1, oy1 + dy];
      else if (drag!.corner === "br") n = [ox0, oy0, ox1 + dx, oy1 + dy];
      else n = [ox0 + dx, oy0 + dy, ox1 + dx, oy1 + dy];
      previewRef.current = n;
      setPreview(n);
    }
    function onUp() {
      // Commit exactly once, in the handler (not in a setState updater).
      const final = previewRef.current;
      previewRef.current = null;
      setPreview(null);
      setDrag(null);
      if (final) onCommitRef.current(box.box_id, final);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag, scale, box.box_id]);

  function startDrag(corner: string, e: React.MouseEvent) {
    if (readOnly) return;
    e.stopPropagation();
    setDrag({ corner, sx: e.clientX, sy: e.clientY, orig: box.bbox });
  }

  return (
    <div
      data-testid={`box-${box.box_id}`}
      data-deactivated={deactivated ? "true" : undefined}
      className={cls.join(" ")}
      style={style}
      onClick={() => onSelect(box.box_id)}
      onMouseDown={(e) => selected && !readOnly && startDrag("center", e)}
    >
      <span className="box-label">
        {box.kind} · {box.confidence.toFixed(2)}
      </span>
      {box.continues_from && (
        <span
          data-testid={`continues-from-indicator-${box.box_id}`}
          className={`absolute top-0 right-0 ${T.tiny} text-white bg-slate-700 px-1 rounded`}
          style={{ fontSize: "0.65rem" }}
        >
          ↑ p{box.page - 1}
        </span>
      )}
      {box.continues_to && (
        <span
          data-testid={`continues-to-indicator-${box.box_id}`}
          className={`absolute bottom-0 right-0 ${T.tiny} text-white bg-slate-700 px-1 rounded`}
          style={{ fontSize: "0.65rem" }}
        >
          ↓ p{box.page + 1}
        </span>
      )}
      {selected && !readOnly && (
        <>
          <div data-testid="handle-tl" className="box-handle" style={{ left: -5, top: -5 }} onMouseDown={(e) => startDrag("tl", e)} />
          <div data-testid="handle-tr" className="box-handle" style={{ right: -5, top: -5 }} onMouseDown={(e) => startDrag("tr", e)} />
          <div data-testid="handle-bl" className="box-handle" style={{ left: -5, bottom: -5 }} onMouseDown={(e) => startDrag("bl", e)} />
          <div data-testid="handle-br" className="box-handle" style={{ right: -5, bottom: -5 }} onMouseDown={(e) => startDrag("br", e)} />
        </>
      )}
    </div>
  );
}
