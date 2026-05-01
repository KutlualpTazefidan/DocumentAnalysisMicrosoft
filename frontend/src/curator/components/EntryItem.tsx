import type { RetrievalEntry, Actor } from "../../shared/types/domain";

interface Props {
  entry: RetrievalEntry;
  onRefine: (entry: RetrievalEntry) => void;
  onDeprecate: (entry: RetrievalEntry) => void;
}

function actorLabel(actor: Actor): string {
  if (actor.kind === "human") {
    return `${actor.pseudonym} (${actor.level})`;
  }
  return `LLM ${actor.model}`;
}

export function EntryItem({ entry, onRefine, onDeprecate }: Props) {
  const creator = entry.review_chain[0]?.actor;
  return (
    <li className="bg-white border border-slate-200 rounded p-4">
      <p className="text-base text-slate-900 mb-2">{entry.query}</p>
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <span className="font-mono">{entry.entry_id}</span>
        {creator ? (
          <>
            <span>·</span>
            <span>{actorLabel(creator)}</span>
          </>
        ) : null}
        {entry.refines ? (
          <>
            <span>·</span>
            <span>verfeinert von {entry.refines}</span>
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
