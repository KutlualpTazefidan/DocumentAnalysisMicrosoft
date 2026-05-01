import type { DocumentElement } from "../../shared/types/domain";

export function FigureElementView({ element }: { element: DocumentElement }) {
  return (
    <div>
      <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
        <span>Abbildung</span>
        <span>·</span>
        <span>Seite {element.page_number}</span>
      </div>
      {element.caption ? (
        <p className="text-sm text-slate-700 mb-1">{element.caption}</p>
      ) : null}
      <p className="text-sm text-slate-500 italic">
        Bild kann im Browser nicht angezeigt werden — siehe PDF Seite {element.page_number}.
      </p>
    </div>
  );
}
