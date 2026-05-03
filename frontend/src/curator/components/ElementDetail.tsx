import { useState } from "react";
import { useElement } from "../hooks/useElement";
import { ElementBody } from "./ElementBody";
import { EntryList } from "./EntryList";
import { NewEntryForm } from "./NewEntryForm";
import { EntryRefineModal } from "./EntryRefineModal";
import { EntryDeprecateModal } from "./EntryDeprecateModal";
import { Spinner } from "../../shared/components/Spinner";
import type { CuratorQuestion } from "../api/curatorClient";

interface Props {
  slug: string;
  elementId: string;
  onWeiter: () => void;
}

export function ElementDetail({ slug, elementId, onWeiter }: Props) {
  const { data, isLoading, error } = useElement(slug, elementId);
  const [refineEntry, setRefineEntry] = useState<CuratorQuestion | null>(null);
  const [deprecateEntry, setDeprecateEntry] = useState<CuratorQuestion | null>(null);

  if (isLoading) return <Spinner label="Lade Element…" />;
  if (error)
    return (
      <p role="alert" className="text-red-600">
        Fehler beim Laden.
      </p>
    );
  if (!data) return null;

  return (
    <section className="space-y-6">
      <ElementBody element={data.element} />
      <div>
        <h3 className="text-sm font-semibold text-slate-700 mb-2">
          Vorhandene Fragen ({data.entries.length})
        </h3>
        <EntryList
          entries={data.entries}
          onRefine={setRefineEntry}
          onDeprecate={setDeprecateEntry}
        />
      </div>
      <NewEntryForm slug={slug} elementId={elementId} onWeiter={onWeiter} />
      <div className="pt-4 border-t border-slate-200">
        <button onClick={onWeiter} className="btn-secondary">
          Weiter →
        </button>
      </div>
      {refineEntry ? (
        <EntryRefineModal
          entry={refineEntry}
          slug={slug}
          elementId={elementId}
          onClose={() => setRefineEntry(null)}
        />
      ) : null}
      {deprecateEntry ? (
        <EntryDeprecateModal
          entry={deprecateEntry}
          slug={slug}
          elementId={elementId}
          onClose={() => setDeprecateEntry(null)}
        />
      ) : null}
    </section>
  );
}
