import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { useToast } from "../../../../shared/components/useToast";
import {
  useCreateSkill,
  type CreateSkillRequest,
  type TriggerConditions,
} from "../../../hooks/useSkills";
import { T } from "../../../styles/typography";

interface PromptOverlayFormProps {
  open: boolean;
  onClose: () => void;
  token: string;
}

/** Split a comma-or-newline-separated keyword list. Trims, drops empties + dupes. */
function parseKeywordList(s: string): string[] {
  return Array.from(
    new Set(
      s
        .split(/[\n,]/)
        .map((x) => x.trim())
        .filter(Boolean),
    ),
  );
}

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
 * PromptOverlayForm — template "🔍 Such-Anfrage verbessern".
 *
 * Visible fields: name + free_text guidance + optional goal_contains.
 * Hidden defaults: skill_kind=prompt-overlay, fires_on=[formulate_task].
 */
export function PromptOverlayForm({
  open,
  onClose,
  token,
}: PromptOverlayFormProps): JSX.Element | null {
  const [name, setName] = useState("");
  const [freeText, setFreeText] = useState("");
  const [goalContains, setGoalContains] = useState("");
  const createMutation = useCreateSkill(token);
  const { error: toastError, success: toastSuccess } = useToast();

  useEffect(() => {
    if (open) {
      setName("");
      setFreeText("");
      setGoalContains("");
      createMutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const goalList = parseKeywordList(goalContains);
  const canSubmit = !!name.trim() && !!freeText.trim();

  function buildSkill(): CreateSkillRequest {
    return {
      name: name.trim(),
      skill_kind: "prompt-overlay",
      fires_on: ["formulate_task"],
      conditions: { ...EMPTY_CONDITIONS, goal_contains: goalList },
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
  }, [open, canSubmit, createMutation.isPending, name, freeText, goalContains]);

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
        aria-label="Such-Anfrage verbessern"
        className="bg-navy-900 border border-navy-600 rounded-lg shadow-2xl w-[min(800px,95vw)] h-[min(720px,90vh)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
          <div className="min-w-0">
            <h2 className={`${T.heading} text-white truncate`}>
              🔍 Such-Anfrage verbessern
            </h2>
            <p className={`${T.tiny} text-slate-400`}>
              Lehrt den Agent, wie er Anfragen für ein Thema formuliert.
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
            <label htmlFor="prompt-overlay-name" className={`${T.tinyBold} block mb-1`}>
              Name
            </label>
            <input
              id="prompt-overlay-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. nachzerfallsleistung-suche"
              className={`w-full px-3 py-2 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
              autoFocus
            />
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              Eindeutiger Bezeichner — gleicher Name bumpt die Version beim Speichern.
            </p>
          </div>

          {/* Free text guidance */}
          <div>
            <label
              htmlFor="prompt-overlay-free-text"
              className={`${T.tinyBold} block mb-1`}
            >
              Was soll der Agent beim Formulieren der Suchanfrage beachten?
            </label>
            <textarea
              id="prompt-overlay-free-text"
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              rows={8}
              placeholder={
                "Beispiel:\n\n" +
                "Bei Fragen zur Nachzerfallsleistung sollte die Suche " +
                "die DIN 25463 sowie konservative Auslegungswerte einbeziehen. " +
                "Vermeide den Begriff 'Restwärme' — verwende " +
                "stattdessen 'Nachzerfallswärme'."
              }
              className={`w-full p-3 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body} resize-y`}
            />
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              Wird als zusätzlicher System-Prompt-Block in den formulate_task-Schritt
              eingespielt, wenn der Skill feuert.
            </p>
          </div>

          {/* Optional: goal_contains */}
          <details
            className="rounded border border-navy-700 bg-navy-900/40"
            open={goalContains.trim().length > 0}
          >
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-amber-300`}
            >
              Optional: Wann soll der Skill feuern?
            </summary>
            <div className="px-3 pb-3 pt-1">
              <label
                htmlFor="prompt-overlay-goal-contains"
                className={`${T.tinyBold} block mb-1`}
              >
                Ziel enthält (Keywords, Komma-getrennt)
              </label>
              <input
                id="prompt-overlay-goal-contains"
                type="text"
                value={goalContains}
                onChange={(e) => setGoalContains(e.target.value)}
                placeholder="z.B. Nachzerfallsleistung, Restwärme, Abklingen"
                className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
              />
              <p className={`${T.tiny} text-slate-500 mt-1`}>
                Leer = der Skill feuert bei jeder formulate_task-Aktion.
              </p>
            </div>
          </details>

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
