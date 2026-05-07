import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { useToast } from "../../../../shared/components/useToast";
import {
  useCreateSkill,
  type CreateSkillRequest,
  type TriggerConditions,
} from "../../../hooks/useSkills";
import { T } from "../../../styles/typography";

interface EnrichmentFormProps {
  open: boolean;
  onClose: () => void;
  token: string;
}

/** Split textarea content into one trimmed question per line, dropping empties. */
function parseQuestions(s: string): string[] {
  return s
    .split("\n")
    .map((q) => q.trim())
    .filter(Boolean);
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
 * EnrichmentForm — template "📜 Aussage anreichern".
 *
 * Only 3 visible fields; hides the rest (skill_kind, fires_on, output, etc.).
 * Power-users who need to override defaults use the Custom template (Task 16).
 */
export function EnrichmentForm({
  open,
  onClose,
  token,
}: EnrichmentFormProps): JSX.Element | null {
  const [name, setName] = useState("");
  const [questionsText, setQuestionsText] = useState("");
  const [goalContains, setGoalContains] = useState("");
  const createMutation = useCreateSkill(token);
  const { error: toastError, success: toastSuccess } = useToast();

  // Reset on open and clear any previous mutation error/state.
  useEffect(() => {
    if (open) {
      setName("");
      setQuestionsText("");
      setGoalContains("");
      createMutation.reset();
    }
    // createMutation.reset is stable from react-query; deps lint disabled to avoid
    // adding the whole mutation object as a dep.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const questions = parseQuestions(questionsText);
  const goalList = parseKeywordList(goalContains);
  const canSubmit = !!name.trim() && questions.length > 0;

  function buildSkill(): CreateSkillRequest {
    return {
      name: name.trim(),
      skill_kind: "enrichment",
      fires_on: ["extract_claims"],
      conditions: { ...EMPTY_CONDITIONS, goal_contains: goalList },
      parent_skill: "",
      prompt: { free_text: "", questions, domain_rules: "" },
      output: {
        annotation_kind: "claim_background",
        attaches_to: "claim",
        consumed_by: ["formulate_task", "evaluate"],
      },
      description: "",
      enabled: true,
    };
  }

  async function handleSubmit(): Promise<void> {
    if (!canSubmit) return;
    try {
      await createMutation.mutateAsync(buildSkill());
      toastSuccess(`Fähigkeit "${name.trim()}" erstellt.`);
      onClose();
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler beim Erstellen");
    }
  }

  // ESC closes; Cmd/Ctrl-Enter submits.
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
  }, [open, canSubmit, createMutation.isPending, name, questionsText, goalContains]);

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
        aria-label="Aussage anreichern"
        className="bg-navy-900 border border-navy-600 rounded-lg shadow-2xl w-[min(800px,95vw)] h-[min(720px,90vh)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
          <div className="min-w-0">
            <h2 className={`${T.heading} text-white truncate`}>
              📜 Aussage anreichern
            </h2>
            <p className={`${T.tiny} text-slate-400`}>
              Holt zusätzliche Infos aus dem Chunk und schreibt sie an jede Aussage.
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
            <label htmlFor="enrichment-name" className={`${T.tinyBold} block mb-1`}>
              Name
            </label>
            <input
              id="enrichment-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. reaktor-typ"
              className={`w-full px-3 py-2 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
              autoFocus
            />
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              Eindeutiger Bezeichner — gleicher Name bumpt die Version beim Speichern.
            </p>
          </div>

          {/* Questions */}
          <div>
            <label
              htmlFor="enrichment-questions"
              className={`${T.tinyBold} block mb-1`}
            >
              Welche Fragen soll die Fähigkeit für jede Aussage beantworten?
            </label>
            <textarea
              id="enrichment-questions"
              value={questionsText}
              onChange={(e) => setQuestionsText(e.target.value)}
              rows={6}
              placeholder={
                "Eine Frage pro Zeile. Beispiel:\n\n" +
                "Welcher Reaktor-Typ ist gemeint?\n" +
                "Welche Werte-Klasse ist anwendbar?\n" +
                "Standort / Anlage?"
              }
              className={`w-full p-3 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body} font-mono resize-y`}
            />
            <p className={`${T.tiny} text-slate-500 mt-1`}>
              {questions.length} Frage(n) erkannt.
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
              Optional: Wann soll die Fähigkeit feuern?
            </summary>
            <div className="px-3 pb-3 pt-1">
              <label
                htmlFor="enrichment-goal-contains"
                className={`${T.tinyBold} block mb-1`}
              >
                Ziel enthält (Keywords, Komma-getrennt)
              </label>
              <input
                id="enrichment-goal-contains"
                type="text"
                value={goalContains}
                onChange={(e) => setGoalContains(e.target.value)}
                placeholder="z.B. Reaktor, Wärmeleistung, prüfen"
                className={`w-full px-3 py-1.5 rounded bg-navy-900 border border-navy-600 text-slate-50 placeholder:text-slate-500 caret-blue-300 ${T.body}`}
              />
              <p className={`${T.tiny} text-slate-500 mt-1`}>
                Leer = die Fähigkeit feuert bei jeder extract_claims-Aktion.
              </p>
            </div>
          </details>

          {/* Raw-data accordion (D-3) */}
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
