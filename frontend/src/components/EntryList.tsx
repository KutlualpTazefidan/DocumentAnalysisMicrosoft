import type { RetrievalEntry } from "../types/domain";
import { EntryItem } from "./EntryItem";

interface Props {
  entries: RetrievalEntry[];
  onRefine: (entry: RetrievalEntry) => void;
  onDeprecate: (entry: RetrievalEntry) => void;
}

export function EntryList({ entries, onRefine, onDeprecate }: Props) {
  if (entries.length === 0) {
    return (
      <p className="text-sm text-slate-500 italic">
        Noch keine Fragen zu diesem Element.
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {entries.map((e) => (
        <EntryItem
          key={e.entry_id}
          entry={e}
          onRefine={onRefine}
          onDeprecate={onDeprecate}
        />
      ))}
    </ul>
  );
}
