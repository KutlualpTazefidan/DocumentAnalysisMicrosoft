import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useToast } from "../../shared/components/useToast";
import { useDeprecateEntry } from "../hooks/useDeprecateEntry";
import { ApiError } from "../api/curatorClient";
import type { CuratorQuestion } from "../api/curatorClient";

interface Props {
  entry: CuratorQuestion;
  slug: string;
  elementId: string;
  onClose: () => void;
}

export function EntryDeprecateModal({ entry, slug, elementId, onClose }: Props) {
  const [reason, setReason] = useState("");
  const deprecate = useDeprecateEntry();
  const { success, error } = useToast();

  function handleSubmit(e: { preventDefault: () => void }) {
    e.preventDefault();
    deprecate.mutate(
      {
        slug,
        questionId: entry.question_id,
        elementId,
        body: { reason: reason.trim() || null },
      },
      {
        onSuccess: () => {
          success("Eintrag zurückgezogen.");
          onClose();
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 404) {
            error("Eintrag nicht gefunden.");
          } else {
            error("Zurückziehen fehlgeschlagen.");
          }
        },
      },
    );
  }

  return (
    <Dialog.Root open onOpenChange={onClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-md">
          <form
            className="bg-white rounded-lg shadow-xl p-6 space-y-4"
            onSubmit={handleSubmit}
          >
            <div className="flex items-center justify-between">
              <Dialog.Title className="text-lg font-semibold">
                Eintrag zurückziehen
              </Dialog.Title>
              <Dialog.Close className="text-slate-500 hover:text-slate-700">
                <X className="w-4 h-4" />
              </Dialog.Close>
            </div>
            <Dialog.Description className="sr-only">
              Ziehen Sie diesen Eintrag mit optionaler Begründung zurück.
            </Dialog.Description>
            <p className="text-sm text-slate-700">
              <span className="font-medium">Frage:</span> {entry.query}
            </p>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Begründung</span>
              <textarea
                className="input mt-1 min-h-[80px]"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="z.B. Duplikat, falsche Antwort, …"
                autoFocus
              />
            </label>
            <div className="flex items-center justify-end gap-2">
              <button type="button" onClick={onClose} className="btn-secondary">
                Abbrechen
              </button>
              <button type="submit" className="btn-danger" disabled={deprecate.isPending}>
                {deprecate.isPending ? "Ziehe zurück…" : "Zurückziehen"}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
