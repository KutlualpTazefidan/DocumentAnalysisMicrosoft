import { useState } from "react";
import { Edit3, Trash2 } from "../../shared/icons";
import { T } from "../styles/typography";
import type { Question } from "../hooks/useSynthesise";

/**
 * List of generated questions for one box, with inline edit + delete
 * for the question text AND the (optional) reference answer.
 *
 * Each row:
 *   - question text — double-click or pencil to edit, trash to deprecate
 *   - green "Antwort: …" callout when present — double-click or pencil
 *     to edit; saving an empty string clears the answer (back to null).
 *
 * onRefine     → updates the question text (refine = create-new + deprecate-old)
 * onDeprecate  → deprecates the entry (full row gone)
 * onEditAnswer → patches the sidecar answer; passing empty text deletes it
 */
type EditTarget = { kind: "question" | "answer"; id: string; draft: string };

interface Props {
  questions: Question[];
  onRefine: (entryId: string, newText: string) => Promise<void> | void;
  onDeprecate: (entryId: string) => Promise<void> | void;
  onEditAnswer?: (entryId: string, newText: string) => Promise<void> | void;
  /** Disable interactions while a global mutation is pending. */
  disabled?: boolean;
}

export function QuestionList({
  questions,
  onRefine,
  onDeprecate,
  onEditAnswer,
  disabled,
}: Props): JSX.Element {
  const [editing, setEditing] = useState<EditTarget | null>(null);

  if (questions.length === 0) {
    return (
      <p className={`${T.bodyMuted} italic`}>Noch keine Fragen für diese Box.</p>
    );
  }

  async function commitEdit(target: EditTarget, q: Question) {
    const text = target.draft;
    if (target.kind === "question") {
      const trimmed = text.trim();
      if (!trimmed) return; // empty question is meaningless
      await onRefine(q.entry_id, trimmed);
    } else if (onEditAnswer) {
      // Empty answer is allowed — it deletes the stored answer.
      await onEditAnswer(q.entry_id, text.trim());
    }
    setEditing(null);
  }

  return (
    <ul className="flex flex-col gap-2 list-none p-0">
      {questions.map((q) => {
        const editingQuestion =
          editing?.kind === "question" && editing.id === q.entry_id;
        const editingAnswer =
          editing?.kind === "answer" && editing.id === q.entry_id;
        return (
          <li
            key={q.entry_id}
            className="rounded border border-slate-200 bg-white p-2 flex flex-col gap-1"
            data-testid={`question-${q.entry_id}`}
          >
            {editingQuestion ? (
              <>
                <textarea
                  className="text-[14px] leading-snug w-full border border-slate-300 rounded p-1 resize-y"
                  rows={3}
                  value={editing!.draft}
                  onChange={(e) =>
                    setEditing({ kind: "question", id: q.entry_id, draft: e.target.value })
                  }
                  autoFocus
                  disabled={disabled}
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="px-2 py-0.5 rounded bg-blue-600 text-white text-xs hover:bg-blue-700 disabled:opacity-40"
                    disabled={disabled || !editing!.draft.trim()}
                    onClick={() => void commitEdit(editing!, q)}
                  >
                    Speichern
                  </button>
                  <button
                    type="button"
                    className="px-2 py-0.5 rounded border border-slate-300 text-slate-700 text-xs hover:bg-slate-50"
                    onClick={() => setEditing(null)}
                  >
                    Abbrechen
                  </button>
                </div>
              </>
            ) : (
              <>
                <p
                  className="text-[14px] leading-snug text-slate-800 whitespace-pre-wrap cursor-text select-text"
                  title="Doppelklick zum Bearbeiten"
                  onDoubleClick={() => {
                    if (disabled) return;
                    setEditing({ kind: "question", id: q.entry_id, draft: q.text });
                  }}
                >
                  {q.text}
                </p>

                {/* Answer block — editable when onEditAnswer is provided. */}
                {editingAnswer ? (
                  <div className="mt-1 rounded border border-emerald-200 bg-emerald-50 px-2 py-1 flex flex-col gap-1">
                    <textarea
                      className="text-[13px] leading-snug w-full border border-emerald-300 rounded p-1 resize-y bg-white text-emerald-900"
                      rows={3}
                      value={editing!.draft}
                      onChange={(e) =>
                        setEditing({ kind: "answer", id: q.entry_id, draft: e.target.value })
                      }
                      placeholder="Leer lassen, um die Antwort zu löschen"
                      autoFocus
                      disabled={disabled}
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="px-2 py-0.5 rounded bg-emerald-600 text-white text-xs hover:bg-emerald-700 disabled:opacity-40"
                        disabled={disabled}
                        onClick={() => void commitEdit(editing!, q)}
                      >
                        Speichern
                      </button>
                      <button
                        type="button"
                        className="px-2 py-0.5 rounded border border-slate-300 text-slate-700 text-xs hover:bg-slate-50"
                        onClick={() => setEditing(null)}
                      >
                        Abbrechen
                      </button>
                    </div>
                  </div>
                ) : (
                  q.answer && (
                    <div
                      className="mt-1 rounded border border-emerald-200 bg-emerald-50 px-2 py-1 text-[13px] leading-snug text-emerald-900 whitespace-pre-wrap cursor-text select-text"
                      title={onEditAnswer ? "Doppelklick zum Bearbeiten" : undefined}
                      onDoubleClick={() => {
                        if (disabled || !onEditAnswer) return;
                        setEditing({
                          kind: "answer",
                          id: q.entry_id,
                          draft: q.answer ?? "",
                        });
                      }}
                      data-testid={`question-answer-${q.entry_id}`}
                    >
                      <span className="font-semibold mr-1">Antwort:</span>
                      {q.answer}
                    </div>
                  )
                )}

                <div className="flex gap-1 justify-end">
                  {onEditAnswer && q.answer && !editingAnswer && (
                    <button
                      type="button"
                      title="Antwort bearbeiten"
                      aria-label="Antwort bearbeiten"
                      className="p-1 rounded text-emerald-600 hover:bg-emerald-50 disabled:opacity-40"
                      disabled={disabled}
                      onClick={() =>
                        setEditing({
                          kind: "answer",
                          id: q.entry_id,
                          draft: q.answer ?? "",
                        })
                      }
                    >
                      <Edit3 size={14} aria-hidden="true" />
                    </button>
                  )}
                  <button
                    type="button"
                    title="Frage bearbeiten"
                    aria-label="Frage bearbeiten"
                    className="p-1 rounded text-green-600 hover:bg-green-50 disabled:opacity-40"
                    disabled={disabled}
                    onClick={() =>
                      setEditing({ kind: "question", id: q.entry_id, draft: q.text })
                    }
                  >
                    <Edit3 size={14} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    title="Frage löschen"
                    aria-label="Frage löschen"
                    className="p-1 rounded text-red-600 hover:bg-red-50 disabled:opacity-40"
                    disabled={disabled}
                    onClick={() => {
                      if (window.confirm(`Diese Frage wirklich löschen?`)) {
                        void onDeprecate(q.entry_id);
                      }
                    }}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </div>
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}
