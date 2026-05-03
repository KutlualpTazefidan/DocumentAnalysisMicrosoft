import type { CuratorQuestion } from "../api/curatorClient";
import { EntryItem } from "./EntryItem";

interface Props {
  entries: CuratorQuestion[];
  onRefine: (entry: CuratorQuestion) => void;
  onDeprecate: (entry: CuratorQuestion) => void;
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
          key={e.question_id}
          entry={e}
          onRefine={onRefine}
          onDeprecate={onDeprecate}
        />
      ))}
    </ul>
  );
}
