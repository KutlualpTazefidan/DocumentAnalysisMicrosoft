import { useState, type KeyboardEvent } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import toast from "react-hot-toast";
import { useRefineEntry } from "../hooks/useRefineEntry";
import { ApiError } from "../api/curatorClient";
import type { RetrievalEntry } from "../../shared/types/domain";

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
    <Dialog.Root open onOpenChange={onClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-lg">
          <form
            className="bg-white rounded-lg shadow-xl p-6 space-y-4"
            onSubmit={handleSubmit}
          >
            <div className="flex items-center justify-between">
              <Dialog.Title className="text-lg font-semibold">
                Eintrag verfeinern
              </Dialog.Title>
              <Dialog.Close className="text-slate-500 hover:text-slate-700">
                <X className="w-4 h-4" />
              </Dialog.Close>
            </div>
            <Dialog.Description className="sr-only">
              Verfeinern Sie die Frage dieses Eintrags.
            </Dialog.Description>
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
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
