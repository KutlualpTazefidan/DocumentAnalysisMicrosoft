import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { T } from "../styles/typography";

const STEP_KIND_OPTIONS = [
  "next_step",
  "extract_claims",
  "extract_goal",
  "formulate_task",
  "evaluate",
  "propose_stop",
] as const;

const STEP_KIND_HINT: Record<string, string> = {
  next_step:
    "🧠 Beeinflusst, WIE der Agent den nächsten Schritt wählt — Heuristiken zu " +
    "Kapselregeln (capability_request vs. executable_step), Tool-Wahl, " +
    "Eskalations-Kriterien.",
  extract_goal:
    "Beeinflusst die automatische Ableitung des Sitzungs-Ziels aus Chunk + " +
    "erster Aussage.",
};

export interface ApproachFormValues {
  name: string;
  step_kinds: string[];
  extra_system: string;
}

interface Props {
  open: boolean;
  mode: "create" | "edit";
  initialValues: ApproachFormValues;
  /** Used in the modal title in edit mode (e.g. "v3 → v4"). */
  versionPreview?: string;
  /** Called with the final values when the user clicks Save. */
  onSubmit: (values: ApproachFormValues) => void | Promise<void>;
  onClose: () => void;
  /** While the parent's mutation is pending, the Save button shows a spinner
   *  and is disabled. */
  busy?: boolean;
  /** Surface backend errors inside the modal. */
  errorMessage?: string;
}

/**
 * Full-width modal for the entire Approach form (name + step_kinds +
 * prompt body). Replaces the cramped inline form in the side pane.
 *
 * Keyboard:
 *   - Escape           → close (discard)
 *   - Cmd/Ctrl-Enter   → submit
 */
export function ApproachFormModal({
  open,
  mode,
  initialValues,
  versionPreview,
  onSubmit,
  onClose,
  busy = false,
  errorMessage,
}: Props): JSX.Element | null {
  const [name, setName] = useState(initialValues.name);
  const [stepKinds, setStepKinds] = useState<string[]>(initialValues.step_kinds);
  const [text, setText] = useState(initialValues.extra_system);

  useEffect(() => {
    if (open) {
      setName(initialValues.name);
      setStepKinds(initialValues.step_kinds);
      setText(initialValues.extra_system);
    }
  }, [open, initialValues]);

  const canSubmit = !!(name.trim() && stepKinds.length > 0 && text.trim());

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && canSubmit && !busy) {
        e.preventDefault();
        void onSubmit({
          name: name.trim(),
          step_kinds: stepKinds,
          extra_system: text.trim(),
        });
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose, onSubmit, name, stepKinds, text, canSubmit, busy]);

  if (!open) return null;

  const title = mode === "create" ? "Neue Approach anlegen" : `Approach bearbeiten`;
  const hintsToShow = stepKinds.filter((s) => STEP_KIND_HINT[s]);

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
            {(mode === "edit" || versionPreview) && (
              <p className={`${T.tiny} text-slate-400 truncate`}>
                {versionPreview}
              </p>
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

        <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4 space-y-4">
          {/* Name */}
          <div>
            <label
              htmlFor="approach-name"
              className={`${T.tinyBold} block mb-1`}
            >
              Name
            </label>
            <input
              id="approach-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. umgang-chunk"
              className={`w-full px-3 py-2 rounded bg-navy-950 border border-navy-700 text-white ${T.body}`}
              autoFocus={mode === "create"}
            />
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              Eindeutiger Bezeichner — gleicher Name bei späterem Speichern
              bumpt die Version.
            </p>
          </div>

          {/* Step kinds */}
          <div>
            <label className={`${T.tinyBold} block mb-1`}>
              Anwendbar auf Schritte
            </label>
            <div className="flex flex-wrap gap-2">
              {STEP_KIND_OPTIONS.map((s) => {
                const checked = stepKinds.includes(s);
                const isMeta = s === "next_step" || s === "extract_goal";
                return (
                  <label
                    key={s}
                    className={`px-3 py-1.5 rounded cursor-pointer ${T.body} font-mono ${
                      checked
                        ? isMeta
                          ? "bg-amber-700 text-white"
                          : "bg-blue-700 text-white"
                        : isMeta
                          ? "bg-navy-800 text-amber-300 border border-amber-700/40"
                          : "bg-navy-800 text-slate-300 border border-navy-600"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="hidden"
                      checked={checked}
                      onChange={(e) => {
                        if (e.target.checked) setStepKinds((p) => [...p, s]);
                        else setStepKinds((p) => p.filter((x) => x !== s));
                      }}
                    />
                    {s}
                  </label>
                );
              })}
            </div>
            {hintsToShow.length > 0 && (
              <ul className="mt-2 space-y-1">
                {hintsToShow.map((s) => (
                  <li key={s} className={`${T.tiny} text-amber-300/85 italic`}>
                    {STEP_KIND_HINT[s]}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Big prompt body */}
          <div className="flex flex-col flex-1">
            <div className="flex items-center justify-between mb-1">
              <label
                htmlFor="approach-text"
                className={`${T.tinyBold}`}
              >
                System-Prompt-Erweiterung
              </label>
              <span className={`${T.tiny} text-slate-500`}>
                {text.length} Zeichen
              </span>
            </div>
            <textarea
              id="approach-text"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={
                "Beispiel:\n\n" +
                "ARBEITSWEISE BEI CHUNK-KNOTEN\n\n" +
                "1. Inhalt vollständig erfassen.\n" +
                "2. Mit Sitzungs-Ziel abgleichen.\n" +
                "3. Nächsten Schritt aus den verfügbaren Steps wählen.\n" +
                "..."
              }
              className="min-h-[280px] w-full p-4 rounded bg-navy-950 border border-navy-700 text-white text-[14px] leading-relaxed font-mono resize-y"
            />
          </div>

          {errorMessage && (
            <p className={`${T.body} text-red-400`}>{errorMessage}</p>
          )}
        </div>

        <footer className="px-4 py-3 border-t border-navy-700 flex items-center justify-between">
          <span className={`${T.tiny} text-slate-500`}>
            Cmd/Ctrl-Enter zum Speichern · Esc zum Abbrechen
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
              onClick={() =>
                void onSubmit({
                  name: name.trim(),
                  step_kinds: stepKinds,
                  extra_system: text.trim(),
                })
              }
              disabled={!canSubmit || busy}
              className={`px-4 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} font-semibold disabled:opacity-50`}
            >
              {busy
                ? mode === "create"
                  ? "Erstelle…"
                  : "Speichere…"
                : mode === "create"
                  ? "Erstellen"
                  : "Speichern"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
