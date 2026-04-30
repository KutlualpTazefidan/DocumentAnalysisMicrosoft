import { useElements } from "../hooks/useElements";
import { Spinner } from "./Spinner";
import type { ElementWithCounts } from "../types/domain";

interface Props {
  slug: string;
  activeElementId: string | undefined;
  onSelect: (elementId: string) => void;
}

const TYPE_GLYPH: Record<string, string> = {
  paragraph: "¶",
  heading: "H",
  table: "▦",
  figure: "🖼",
  list_item: "•",
};

function shorten(s: string, n = 60): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

function rowLabel(item: ElementWithCounts): string {
  const el = item.element;
  if (el.element_type === "figure") return el.caption ?? "(Abbildung)";
  if (el.element_type === "table") return shorten(el.content, 40);
  return shorten(el.content, 60);
}

export function ElementSidebar({ slug, activeElementId, onSelect }: Props) {
  const { data, isLoading, error } = useElements(slug);

  if (isLoading) {
    return (
      <aside className="w-72 border-r border-slate-200 p-4 overflow-y-auto">
        <Spinner label="Lade Elemente…" />
      </aside>
    );
  }
  if (error || !data) {
    return (
      <aside className="w-72 border-r border-slate-200 p-4">
        <p className="text-red-600 text-sm">Fehler.</p>
      </aside>
    );
  }
  return (
    <aside className="w-72 border-r border-slate-200 overflow-y-auto bg-slate-50">
      <ul className="divide-y divide-slate-200">
        {data.map((item) => {
          const isActive = item.element.element_id === activeElementId;
          return (
            <li key={item.element.element_id}>
              <button
                type="button"
                onClick={() => onSelect(item.element.element_id)}
                aria-current={isActive ? "true" : undefined}
                className={`w-full text-left px-3 py-2 hover:bg-white transition ${
                  isActive ? "bg-white border-l-4 border-blue-500" : ""
                }`}
              >
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span title={item.element.element_type}>
                    {TYPE_GLYPH[item.element.element_type]}
                  </span>
                  <span>p.{item.element.page_number}</span>
                  {item.count_active_entries > 0 ? (
                    <span className="ml-auto bg-blue-100 text-blue-800 rounded-full px-2 py-0.5 text-xs">
                      {item.count_active_entries}
                    </span>
                  ) : null}
                </div>
                <p className="text-sm text-slate-700 mt-1 truncate">
                  {rowLabel(item)}
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
