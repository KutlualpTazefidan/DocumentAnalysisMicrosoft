import { useEffect, useState, type KeyboardEvent } from "react";
import toast from "react-hot-toast";
import { useRefineEntry } from "../hooks/useRefineEntry";
import { ApiError } from "../api/client";
import type { RetrievalEntry } from "../types/domain";

interface Props {
  entry: RetrievalEntry;
  slug: string;
  elementId: string;
  onClose: () => void;
}

export function EntryRefineModal({ entry, slug, elementId, onClose }: Props) {
  const [query, setQuery] = useState(entry.query);
  const [notes, setNotes] = useState("");
  const refine = useRefineEntry();

  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function handleSubmit(e: KeyboardEvent | { preventDefault: () => void }) {
    e.preventDefault();
    if (!query.trim()) return;
    refine.mutate(
      {
        entryId: entry.entry_id,
        slug,
        elementId,
        body: {
          query: query.trim(),
          expected_chunk_ids: entry.expected_chunk_ids,
          chunk_hashes: entry.chunk_hashes,
          notes: notes.trim() || null,
        },
      },
      {
        onSuccess: () => {
          toast.success("Eintrag verfeinert.");
          onClose();
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 409) {
            toast.error("Eintrag bereits zurückgezogen.");
          } else if (err instanceof ApiError && err.status === 404) {
            toast.error("Eintrag nicht gefunden.");
          } else {
            toast.error("Verfeinern fehlgeschlagen.");
          }
        },
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="refine-title"
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <form
        className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <h2 id="refine-title" className="text-lg font-semibold">
          Eintrag verfeinern
        </h2>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Neue Frage</span>
          <textarea
            className="input mt-1 min-h-[100px]"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            aria-label="Neue Frage"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Notiz (optional)</span>
          <input
            className="input mt-1"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>
        <div className="flex items-center justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="btn-secondary">
            Abbrechen
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={refine.isPending || !query.trim()}
          >
            {refine.isPending ? "Verfeinere…" : "Verfeinern"}
          </button>
        </div>
      </form>
    </div>
  );
}
