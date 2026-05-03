import { useState } from "react";
import type { DocumentElement } from "../../shared/types/domain";

export function TableElementView({ element }: { element: DocumentElement }) {
  const [showFull, setShowFull] = useState(false);
  const dims = element.table_dims;
  const body =
    showFull && element.table_full_content ? element.table_full_content : element.content;

  return (
    <div>
      <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
        <span>Tabelle</span>
        <span>·</span>
        <span>Seite {element.page_number}</span>
        {dims ? (
          <>
            <span>·</span>
            <span>
              {dims[0]}
              {"×"}
              {dims[1]}
            </span>
          </>
        ) : null}
      </div>
      <pre className="bg-slate-50 rounded p-3 overflow-x-auto text-sm font-mono whitespace-pre">
        {body}
      </pre>
      {element.table_full_content && element.table_full_content !== element.content ? (
        <button
          onClick={() => setShowFull((s) => !s)}
          className="btn-secondary mt-2 text-sm"
          aria-pressed={showFull}
        >
          {showFull ? "Kompakte Vorschau" : "Volle Tabelle anzeigen"}
        </button>
      ) : null}
    </div>
  );
}
