// frontend/src/local-pdf/components/BoxOverlay.tsx
import { useEffect, useState } from "react";
import type { SegmentBox } from "../types/domain";
import "../styles/box-colors.css";

interface Props {
  box: SegmentBox;
  selected: boolean;
  deactivated?: boolean;
  onSelect: (boxId: string, multi: boolean) => void;
  onChange: (boxId: string, bbox: [number, number, number, number]) => void;
  scale: number;
}

export function BoxOverlay({ box, selected, deactivated = false, onSelect, onChange, scale }: Props): JSX.Element {
  const [x0, y0, x1, y1] = box.bbox;
  const [drag, setDrag] = useState<{ corner: string; sx: number; sy: number; orig: [number, number, number, number] } | null>(null);

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
      onChange(box.box_id, n);
    }
    function onUp() {
      setDrag(null);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag, scale, onChange, box.box_id]);

  function startDrag(corner: string, e: React.MouseEvent) {
    e.stopPropagation();
    setDrag({ corner, sx: e.clientX, sy: e.clientY, orig: box.bbox });
  }

  return (
    <div
      data-testid={`box-${box.box_id}`}
      data-deactivated={deactivated ? "true" : undefined}
      className={cls.join(" ")}
      style={style}
      onClick={(e) => onSelect(box.box_id, e.shiftKey)}
      onMouseDown={(e) => selected && startDrag("center", e)}
    >
      <span className="box-label">
        {box.kind} · {box.confidence.toFixed(2)}
      </span>
      {selected && (
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
