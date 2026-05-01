// frontend/src/local-pdf/hooks/useBoxHotkeys.ts
import { useEffect } from "react";
import type { BoxKind } from "../types/domain";

export interface BoxHotkeyHandlers {
  enabled: boolean;
  setKind: (k: BoxKind) => void;
  merge: () => void;
  split: () => void;
  newBox: () => void;
  del: () => void;
}

const KIND_KEYS: Record<string, BoxKind> = {
  h: "heading",
  p: "paragraph",
  t: "table",
  f: "figure",
  c: "caption",
  q: "formula",
  l: "list_item",
  x: "discard",
};

export function useBoxHotkeys(h: BoxHotkeyHandlers): void {
  useEffect(() => {
    if (!h.enabled) return;
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const k = KIND_KEYS[e.key];
      if (k) {
        e.preventDefault();
        h.setKind(k);
        return;
      }
      if (e.key === "m") {
        e.preventDefault();
        h.merge();
      } else if (e.key === "n") {
        e.preventDefault();
        h.newBox();
      } else if (e.key === "/") {
        e.preventDefault();
        h.split();
      } else if (e.key === "Backspace" || e.key === "Delete") {
        e.preventDefault();
        h.del();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [h.enabled, h.setKind, h.merge, h.split, h.newBox, h.del]);
}
