import type { CuratorQuestion } from "../api/curatorClient";

interface Props {
  entry: CuratorQuestion;
  onRefine: (entry: CuratorQuestion) => void;
  onDeprecate: (entry: CuratorQuestion) => void;
}

export function EntryItem({ entry, onRefine, onDeprecate }: Props) {
  return (
    <li className="bg-white border border-slate-200 rounded p-4">
      <p className="text-base text-slate-900 mb-2">{entry.query}</p>
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <span className="font-mono">{entry.question_id}</span>
        <span>·</span>
        <span>{entry.curator_id}</span>
        {entry.refined_query ? (
          <>
            <span>·</span>
            <span>verfeinert</span>
          </>
        ) : null}
      </div>
      <div className="flex items-center gap-2 mt-3">
        <button onClick={() => onRefine(entry)} className="btn-secondary text-xs">
          Verfeinern
        </button>
        <button onClick={() => onDeprecate(entry)} className="btn-secondary text-xs">
          Zurückziehen
        </button>
      </div>
    </li>
  );
}
