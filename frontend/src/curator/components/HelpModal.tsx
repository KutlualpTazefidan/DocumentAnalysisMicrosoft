import { useEffect } from "react";

interface Props {
  onClose: () => void;
}

const SHORTCUTS: Array<[string, string]> = [
  ["Enter (im Textarea)", "Speichern"],
  ["Enter (Textarea leer)", "Weiter"],
  ["Ctrl+Enter / Cmd+Enter", "Speichern (auch wenn Textarea Inhalt hat)"],
  ["Escape", "Modal schließen"],
  ["j / ArrowDown", "Sidebar nach unten"],
  ["k / ArrowUp", "Sidebar nach oben"],
  ["t (auf Tabelle)", "Volle Tabelle ↔ Stub"],
  ["?", "Diese Hilfe"],
];

export function HelpModal({ onClose }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="help-title"
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-xl w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="help-title" className="text-lg font-semibold mb-4">
          Tastatur-Shortcuts
        </h2>
        <dl className="space-y-2 text-sm">
          {SHORTCUTS.map(([k, v]) => (
            <div key={k} className="grid grid-cols-2 gap-4">
              <dt className="font-mono text-slate-700">{k}</dt>
              <dd className="text-slate-600">{v}</dd>
            </div>
          ))}
        </dl>
        <button onClick={onClose} className="btn-secondary mt-4">
          Schließen
        </button>
      </div>
    </div>
  );
}
