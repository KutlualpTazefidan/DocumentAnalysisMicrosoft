import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { useToast } from "../../../../shared/components/useToast";
import {
  useCreateSkill,
  type CreateSkillRequest,
  type TriggerConditions,
} from "../../../hooks/useSkills";
import { T } from "../../../styles/typography";

interface NoteFormProps {
  open: boolean;
  onClose: () => void;
  token: string;
}

type StepChoice =
  | "extract_claims"
  | "formulate_task"
  | "evaluate"
  | "propose_stop"
  | "all";

const STEP_OPTIONS: { value: StepChoice; label: string }[] = [
  { value: "extract_claims", label: "Aussagen extrahieren" },
  { value: "formulate_task", label: "Aufgabe formulieren" },
  { value: "evaluate", label: "Bewerten" },
  { value: "propose_stop", label: "Stopp vorschlagen" },
  { value: "all", label: "Bei jedem Step" },
];

const ALL_STEPS = [
  "extract_claims",
  "formulate_task",
  "evaluate",
  "propose_stop",
];

const EMPTY_CONDITIONS: TriggerConditions = {
  verdicts: [],
  sentence_regex: [],
  claim_regex: [],
  topic_keywords: [],
  anchor_kinds: [],
  goal_contains: [],
  text_contains: [],
};

/**
 * NoteForm — template "📌 Lehr-Notiz".
 *
 * Simplest template: name + step + free_text. Hidden defaults:
 * skill_kind=note. fires_on is derived from the step radio (or all 4
 * for "Bei jedem Step").
 */
export function NoteForm({
  open,
  onClose,
  token,
}: NoteFormProps): JSX.Element | null {
  const [name, setName] = useState("");
  const [step, setStep] = useState<StepChoice>("evaluate");
  const [freeText, setFreeText] = useState("");
  const createMutation = useCreateSkill(token);
  const { error: toastError, success: toastSuccess } = useToast();

  useEffect(() => {
    if (open) {
      setName("");
      setStep("evaluate");
      setFreeText("");
      createMutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const canSubmit = !!name.trim() && !!freeText.trim();

  function buildSkill(): CreateSkillRequest {
    const fires_on = step === "all" ? [...ALL_STEPS] : [step];
    return {
      name: name.trim(),
      skill_kind: "note",
      fires_on,
      conditions: { ...EMPTY_CONDITIONS },
      parent_skill: "",
      prompt: { free_text: freeText.trim(), questions: [], domain_rules: "" },
      output: { annotation_kind: "", attaches_to: "", consumed_by: [] },
      description: "",
      enabled: true,
    };
  }

  async function handleSubmit(): Promise<void> {
    if (!canSubmit) return;
    try {
      await createMutation.mutateAsync(buildSkill());
      toastSuccess(`Skill "${name.trim()}" erstellt.`);
      onClose();
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler beim Erstellen");
    }
  }

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (
        e.key === "Enter" &&
        (e.metaKey || e.ctrlKey) &&
        canSubmit &&
        !createMutation.isPending
      ) {
        e.preventDefault();
        void handleSubmit();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, canSubmit, createMutation.isPending, name, step, freeText]);

  if (!open) return null;

  const previewSkill = buildSkill();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Lehr-Notiz"
        className="bg-navy-900 border border-navy-600 rounded-lg shadow-2xl w-[min(720px,95vw)] h-[min(640px,90vh)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
          <div className="min-w-0">
            <h2 className={`${T.heading} text-white truncate`}>📌 Lehr-Notiz</h2>
            <p className={`${T.tiny} text-slate-400`}>
              Kurze Regel, die in alle Prompts eines Step-Typs aufgenommen wird.
            </p>
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
            <label htmlFor="note-name" className={`${T.tinyBold} block mb-1`}>
              Name
            </label>
            <input
              id="note-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. einheiten-immer-prüfen"
              className={`w-full px-3 py-2 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
              autoFocus
            />
          </div>

          {/* Step radio */}
          <div>
            <p className={`${T.tinyBold} mb-1`}>
              Bei welchem Schritt soll die Notiz gelten?
            </p>
            <div className="space-y-1">
              {STEP_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-navy-800/40 ${T.body}`}
                >
                  <input
                    type="radio"
                    name="note-step"
                    value={opt.value}
                    checked={step === opt.value}
                    onChange={() => setStep(opt.value)}
                    className="accent-blue-500"
                  />
                  <span className="text-slate-200">{opt.label}</span>
                  <span className={`${T.tiny} text-slate-500 ml-auto font-mono`}>
                    {opt.value === "all" ? "alle 4" : opt.value}
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* Note text */}
          <div>
            <label
              htmlFor="note-free-text"
              className={`${T.tinyBold} block mb-1`}
            >
              Notiz
            </label>
            <textarea
              id="note-free-text"
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              rows={6}
              placeholder={
                "z.B. Always check unit conversion before declaring " +
                "two values equivalent. Beware MW vs MWth vs MWel."
              }
              className={`w-full p-3 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body} resize-y`}
            />
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              Die Notiz wird als zusätzlicher Hinweis in den jeweiligen
              System-Prompt eingespielt.
            </p>
          </div>

          {/* Raw-data accordion */}
          <details className="rounded border border-navy-700 bg-navy-900/30">
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-slate-400`}
            >
              Roh-Daten anzeigen
            </summary>
            <pre
              className={`px-3 pb-3 pt-1 ${T.tiny} text-slate-300 font-mono whitespace-pre-wrap break-all`}
            >
              {JSON.stringify(previewSkill, null, 2)}
            </pre>
          </details>

          {createMutation.error && (
            <p className={`${T.body} text-red-400`}>
              {createMutation.error.message}
            </p>
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
              onClick={() => void handleSubmit()}
              disabled={!canSubmit || createMutation.isPending}
              className={`px-4 py-1.5 rounded bg-blue-500 hover:bg-blue-400 text-white ${T.body} font-semibold disabled:opacity-50`}
            >
              {createMutation.isPending ? "Erstelle…" : "Erstellen"}
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
