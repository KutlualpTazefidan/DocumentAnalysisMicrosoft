import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { T } from "../styles/typography";

interface Props {
  open: boolean;
  title: string;
  subtitle?: string;
  initialText: string;
  onSave: (text: string) => void;
  onClose: () => void;
  saveLabel?: string;
  /** Optional placeholder shown when initialText is empty. */
  placeholder?: string;
}

/**
 * Fullscreen modal text editor for long heuristic prompts. The narrow
 * side pane keeps the small fields (name, step_kinds checkboxes) but
 * the prompt body — which can run 1000+ chars — opens here in a wide
 * modal with proper monospace + line height.
 *
 * Keyboard:
 *   - Escape           → close (discard)
 *   - Cmd/Ctrl-Enter   → save
 */
export function FullscreenTextEditor({
  open,
  title,
  subtitle,
  initialText,
  onSave,
  onClose,
  saveLabel = "Speichern",
  placeholder,
}: Props): JSX.Element | null {
  const [text, setText] = useState(initialText);

  // Sync local draft when the modal re-opens with a different initial text.
  useEffect(() => {
    if (open) setText(initialText);
  }, [open, initialText]);

  // Esc closes; Cmd/Ctrl-Enter saves.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onSave(text);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose, onSave, text]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="bg-navy-900 border border-navy-600 rounded-lg shadow-2xl w-[min(1100px,95vw)] h-[min(800px,90vh)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
          <div className="min-w-0">
            <h2 className={`${T.heading} text-white truncate`}>{title}</h2>
            {subtitle && (
              <p className={`${T.tiny} text-slate-400 truncate`}>{subtitle}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded"
            aria-label="Schließen"
          >
            <X className="w-5 h-5" />
          </button>
        </header>
        <div className="flex-1 min-h-0 p-4">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={placeholder}
            className="w-full h-full p-4 rounded bg-navy-950 border border-navy-700 text-white text-[14px] leading-relaxed font-mono resize-none"
            autoFocus
          />
        </div>
        <footer className="px-4 py-3 border-t border-navy-700 flex items-center justify-between">
          <span className={`${T.tiny} text-slate-500`}>
            {text.length} Zeichen · Cmd/Ctrl-Enter zum Speichern · Esc zum
            Abbrechen
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              className={`px-3 py-1.5 rounded text-slate-300 hover:bg-navy-700 ${T.body}`}
            >
              Abbrechen
            </button>
            <button
              type="button"
              onClick={() => onSave(text)}
              disabled={!text.trim()}
              className={`px-4 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} font-semibold disabled:opacity-50`}
            >
              {saveLabel}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
