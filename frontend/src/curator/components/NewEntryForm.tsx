import { useState, type KeyboardEvent } from "react";
import toast from "react-hot-toast";
import { useCreateEntry } from "../hooks/useCreateEntry";
import { ApiError } from "../api/curatorClient";

interface Props {
  slug: string;
  elementId: string;
  onWeiter: () => void;
}

export function NewEntryForm({ slug, elementId, onWeiter }: Props) {
  const [query, setQuery] = useState("");
  const create = useCreateEntry();

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter") {
      const trimmed = query.trim();
      if (trimmed === "") {
        e.preventDefault();
        onWeiter();
        return;
      }
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        submit();
      }
    }
  }

  function submit() {
    const trimmed = query.trim();
    if (!trimmed) return;
    create.mutate(
      { slug, elementId, body: { query: trimmed } },
      {
        onSuccess: () => {
          toast.success("✓ gespeichert");
          setQuery("");
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 422) {
            toast.error("Frage abgelehnt: " + JSON.stringify(err.detail));
          } else {
            toast.error("Speichern fehlgeschlagen.");
          }
        },
      },
    );
  }

  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label className="block">
        <span className="text-sm font-medium text-slate-700">
          Neue Frage zu diesem Element
        </span>
        <textarea
          className="input mt-1 min-h-[80px]"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Tippen + Speichern (oder Ctrl+Enter). Leer + Enter = Weiter."
          aria-label="Neue Frage"
          disabled={create.isPending}
        />
      </label>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          className="btn-primary"
          disabled={create.isPending || !query.trim()}
        >
          {create.isPending ? "Speichere…" : "Speichern"}
        </button>
        <span className="text-xs text-slate-500">Ctrl+Enter zum Speichern</span>
      </div>
    </form>
  );
}
