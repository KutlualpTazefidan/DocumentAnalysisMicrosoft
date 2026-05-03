import { useState } from "react";
import { Edit3, Trash2 } from "../../shared/icons";
import { T } from "../styles/typography";
import type { Question } from "../hooks/useSynthesise";

/**
 * List of generated questions for one box, with inline edit + delete.
 *
 * Each row: question text (click → contenteditable), Save / Cancel
 * buttons while editing, 🗑 button when not editing. Save calls
 * ``onRefine(entry_id, new_text)``. Delete confirms once then calls
 * ``onDeprecate(entry_id)``.
 *
 * Optimistic updates live in the parent — this component is purely
 * presentational + edit-state-local.
 */
interface Props {
  questions: Question[];
  onRefine: (entryId: string, newText: string) => Promise<void> | void;
  onDeprecate: (entryId: string) => Promise<void> | void;
  /** Disable interactions while a global mutation is pending. */
  disabled?: boolean;
}

export function QuestionList({ questions, onRefine, onDeprecate, disabled }: Props): JSX.Element {
  const [editing, setEditing] = useState<{ id: string; draft: string } | null>(null);

  if (questions.length === 0) {
    return (
      <p className={`${T.bodyMuted} italic`}>Noch keine Fragen für diese Box.</p>
    );
  }

  return (
    <ul className="flex flex-col gap-2 list-none p-0">
      {questions.map((q) => {
        const isEditing = editing?.id === q.entry_id;
        return (
          <li
            key={q.entry_id}
            className="rounded border border-slate-200 bg-white p-2 flex flex-col gap-1"
            data-testid={`question-${q.entry_id}`}
          >
            {isEditing ? (
              <>
                <textarea
                  className="text-[14px] leading-snug w-full border border-slate-300 rounded p-1 resize-y"
                  rows={3}
                  value={editing!.draft}
                  onChange={(e) =>
                    setEditing({ id: q.entry_id, draft: e.target.value })
                  }
                  autoFocus
                  disabled={disabled}
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="px-2 py-0.5 rounded bg-blue-600 text-white text-xs hover:bg-blue-700 disabled:opacity-40"
                    disabled={disabled || !editing!.draft.trim()}
                    onClick={async () => {
                      await onRefine(q.entry_id, editing!.draft.trim());
                      setEditing(null);
                    }}
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
                <p className="text-[14px] leading-snug text-slate-800 whitespace-pre-wrap">
                  {q.text}
                </p>
                <div className="flex gap-1 justify-end">
                  <button
                    type="button"
                    title="Frage bearbeiten"
                    aria-label="Frage bearbeiten"
                    className="p-1 rounded text-green-600 hover:bg-green-50 disabled:opacity-40"
                    disabled={disabled}
                    onClick={() =>
                      setEditing({ id: q.entry_id, draft: q.text })
                    }
                  >
                    <Edit3 size={14} aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    title="Frage loeschen"
                    aria-label="Frage loeschen"
                    className="p-1 rounded text-red-600 hover:bg-red-50 disabled:opacity-40"
                    disabled={disabled}
                    onClick={() => {
                      if (window.confirm(`Diese Frage wirklich loeschen?`)) {
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
