import { useEffect } from "react";

type Handler = (event: KeyboardEvent) => void;
type Bindings = Record<string, Handler>;

function isTextEntryFocused(): boolean {
  const a = document.activeElement;
  if (!a) return false;
  if (a instanceof HTMLTextAreaElement) return true;
  if (a instanceof HTMLInputElement) {
    return !["button", "submit", "checkbox", "radio"].includes(a.type);
  }
  if (a instanceof HTMLElement && a.isContentEditable) return true;
  return false;
}

export function useKeyboardShortcuts(bindings: Bindings) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (isTextEntryFocused()) return;
      const handler = bindings[e.key];
      if (handler) handler(e);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [bindings]);
}
