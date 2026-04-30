import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { useDeprecateEntry } from "../hooks/useDeprecateEntry";
import { ApiError } from "../api/client";
import type { RetrievalEntry } from "../types/domain";

interface Props {
  entry: RetrievalEntry;
  slug: string;
  elementId: string;
  onClose: () => void;
}

export function EntryDeprecateModal({ entry, slug, elementId, onClose }: Props) {
  const [reason, setReason] = useState("");
  const deprecate = useDeprecateEntry();

  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function handleSubmit(e: { preventDefault: () => void }) {
    e.preventDefault();
    deprecate.mutate(
      { entryId: entry.entry_id, slug, elementId, body: { reason: reason.trim() || null } },
      {
        onSuccess: () => {
          toast.success("Eintrag zurückgezogen.");
          onClose();
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 409) {
            toast.error("Bereits zurückgezogen.");
          } else if (err instanceof ApiError && err.status === 404) {
            toast.error("Eintrag nicht gefunden.");
          } else {
            toast.error("Zurückziehen fehlgeschlagen.");
          }
        },
      },
    );
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="deprecate-title"
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <form
        className="bg-white rounded-lg shadow-xl w-full max-w-md p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <h2 id="deprecate-title" className="text-lg font-semibold">
          Eintrag zurückziehen
        </h2>
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
    </div>
  );
}
