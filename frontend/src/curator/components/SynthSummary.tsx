import { Link } from "react-router-dom";

interface Props {
  slug: string;
  totals: {
    totalElements: number;
    kept: number;
    errors: number;
    eventsWritten: number;
    tokensEstimated: number;
  };
  onReset: () => void;
}

export function SynthSummary({ slug, totals, onReset }: Props) {
  return (
    <div className="space-y-4 max-w-md">
      <h2 className="text-lg font-semibold">Synthesise abgeschlossen.</h2>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-slate-600">Elements</dt>
        <dd>{totals.totalElements}</dd>
        <dt className="text-slate-600">Kept (questions)</dt>
        <dd>{totals.kept}</dd>
        <dt className="text-slate-600">Events written</dt>
        <dd>{totals.eventsWritten}</dd>
        <dt className="text-slate-600">Errors</dt>
        <dd className={totals.errors > 0 ? "text-red-700" : ""}>{totals.errors}</dd>
        <dt className="text-slate-600">Tokens estimated</dt>
        <dd>{totals.tokensEstimated}</dd>
      </dl>
      <div className="flex items-center gap-2">
        <Link
          to={`/curate/doc/${encodeURIComponent(slug)}`}
          className="btn-primary"
        >
          Zurück zu den Elementen
        </Link>
        <button onClick={onReset} className="btn-secondary">
          Nochmal
        </button>
      </div>
    </div>
  );
}
