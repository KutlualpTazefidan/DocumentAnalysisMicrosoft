import type { DocumentElement } from "../../shared/types/domain";
import { TableElementView } from "./TableElementView";
import { FigureElementView } from "./FigureElementView";

const TYPE_LABEL: Record<string, string> = {
  paragraph: "Absatz",
  heading: "Überschrift",
  list_item: "Listpunkt",
};

export function ElementBody({ element }: { element: DocumentElement }) {
  if (element.element_type === "table") return <TableElementView element={element} />;
  if (element.element_type === "figure") return <FigureElementView element={element} />;

  const label = TYPE_LABEL[element.element_type] ?? "Element";
  return (
    <div>
      <div className="flex items-center gap-2 text-xs text-slate-500 mb-2">
        <span>{label}</span>
        <span>·</span>
        <span>Seite {element.page_number}</span>
        <span>·</span>
        <span className="font-mono">{element.element_id}</span>
      </div>
      <p className="text-base text-slate-900 whitespace-pre-wrap">{element.content}</p>
    </div>
  );
}
