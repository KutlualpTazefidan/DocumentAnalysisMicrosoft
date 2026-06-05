import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";

import { useDocElements, type DocElement } from "../hooks/useProvenienz";
import { T } from "../styles/typography";

interface Props {
  slug: string;
  token: string;
  onPick: (boxId: string) => void;
  onCancel: () => void;
  pending?: boolean;
  errorMessage?: string;
}

export function ChunkPicker({
  slug,
  token,
  onPick,
  onCancel,
  pending = false,
  errorMessage,
}: Props): JSX.Element {
  const { data: elements, isLoading, error } = useDocElements(slug, token);
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    if (!elements) return [];
    const q = query.trim().toLowerCase();
    if (!q) return elements;
    return elements.filter(
      (e) =>
        e.box_id.toLowerCase().includes(q) ||
        e.text_preview.toLowerCase().includes(q),
    );
  }, [elements, query]);

  return (
    <div className="flex flex-col h-full bg-white">
      <header className="flex items-center justify-between px-4 py-3 border-b border-line">
        <div>
          <h2 className={`${T.heading} text-ink`}>Wurzel-Chunk wählen</h2>
          <p className={`${T.body} text-ink-muted`}>
            Eine Sitzung beginnt an einem Chunk. Such oder scroll, dann klicken.
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          className="text-ink-muted hover:text-ink p-1"
          aria-label="Abbrechen"
        >
          <X className="w-4 h-4" />
        </button>
      </header>

      <div className="px-4 py-3 border-b border-line">
        <div className="relative">
          <Search
            className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-muted"
            aria-hidden
          />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Suche nach box_id (z.B. p16) oder Text…"
            className={`w-full pl-8 pr-3 py-2 rounded bg-white border border-line text-ink ${T.body} focus:outline-none focus:border-blue-500`}
            autoFocus
            disabled={pending}
          />
        </div>
        {elements && (
          <p className={`${T.tiny} text-ink-muted mt-2`}>
            {filtered.length} von {elements.length} Chunks
          </p>
        )}
      </div>

      {errorMessage && (
        <div className="px-4 py-2 bg-red-50 border-b border-red-200">
          <p className={`${T.body} text-red-700`}>{errorMessage}</p>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <p className={`px-4 py-3 ${T.body} text-ink-muted`}>Lade Chunks…</p>
        )}
        {error && (
          <p className={`px-4 py-3 ${T.body} text-red-600`}>
            Konnte Chunks nicht laden: {error.message}
          </p>
        )}
        {filtered.length === 0 && !isLoading && elements && (
          <p className={`px-4 py-3 ${T.body} text-ink-muted italic`}>
            Keine Treffer für „{query}".
          </p>
        )}
        <ul className="divide-y divide-line">
          {filtered.map((el) => (
            <ChunkRow
              key={el.box_id}
              el={el}
              onPick={() => onPick(el.box_id)}
              disabled={pending}
            />
          ))}
        </ul>
      </div>
    </div>
  );
}

function ChunkRow({
  el,
  onPick,
  disabled,
}: {
  el: DocElement;
  onPick: () => void;
  disabled: boolean;
}): JSX.Element {
  return (
    <li>
      <button
        type="button"
        onClick={onPick}
        disabled={disabled}
        className="w-full text-left px-4 py-3 hover:bg-rowsel disabled:opacity-50 disabled:cursor-wait flex items-start gap-3"
      >
        <span
          className={`${T.tiny} font-mono text-blue-700 bg-canvas px-1.5 py-0.5 rounded shrink-0`}
        >
          S.{el.page}
        </span>
        <div className="min-w-0 flex-1">
          <p className={`${T.tiny} font-mono text-ink-muted mb-0.5`}>
            {el.box_id}
          </p>
          <p className={`${T.body} text-ink line-clamp-2`}>
            {el.text_preview || (
              <span className="italic text-ink-muted">
                (kein Textinhalt — Bild / Tabelle / Layout)
              </span>
            )}
          </p>
        </div>
      </button>
    </li>
  );
}
