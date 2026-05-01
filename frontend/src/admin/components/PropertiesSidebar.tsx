import type { BoxKind, SegmentBox } from "../types/domain";

const KINDS: BoxKind[] = ["heading", "paragraph", "table", "figure", "caption", "formula", "list_item", "discard"];

interface Props {
  selected: SegmentBox | null;
  pageBoxCount: number;
  onChangeKind: (k: BoxKind) => void;
  onMerge: () => void;
  onDelete: () => void;
}

export function PropertiesSidebar({ selected, pageBoxCount, onChangeKind, onMerge, onDelete }: Props): JSX.Element {
  return (
    <aside className="w-1/4 border-l p-4 flex flex-col gap-3 text-sm">
      <h2 className="font-semibold">Properties</h2>
      {selected ? (
        <>
          <div>
            <label className="block text-xs text-gray-500">Kind</label>
            <select className="w-full border rounded p-1" value={selected.kind} onChange={(e) => onChangeKind(e.target.value as BoxKind)}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </div>
          <div>
            <span className="text-xs text-gray-500">bbox</span>
            <pre className="text-xs">{JSON.stringify(selected.bbox)}</pre>
          </div>
          <div>
            <span className="text-xs text-gray-500">confidence</span>{" "}
            <span>{selected.confidence.toFixed(3)}</span>
          </div>
          <div className="flex gap-2">
            <button className="px-2 py-1 border rounded" onClick={onMerge}>Merge (m)</button>
            <button className="px-2 py-1 border rounded" onClick={onDelete}>Delete</button>
          </div>
        </>
      ) : (
        <p className="text-gray-400">Select a box.</p>
      )}
      <div className="border-t pt-3 mt-3">
        <p className="text-xs text-gray-500">{pageBoxCount} boxes on page</p>
      </div>
      <p className="mt-auto text-xs text-gray-400 text-center">Extract via top bar</p>
    </aside>
  );
}
