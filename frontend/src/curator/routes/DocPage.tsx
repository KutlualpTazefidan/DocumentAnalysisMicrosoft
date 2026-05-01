import { useParams } from "react-router-dom";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { listCurateElements, postQuestion } from "../api/curatorClient";
import { useToast } from "../../shared/components/useToast";
import { Plus } from "../../shared/icons";

export function CuratorDocPage() {
  const { slug, elementId } = useParams<{ slug: string; elementId?: string }>();
  const { token } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [draft, setDraft] = useState("");

  const els = useQuery({
    queryKey: ["curate", "elements", slug],
    queryFn: () => listCurateElements(slug!, token!),
    enabled: !!slug && !!token,
  });

  const mut = useMutation({
    mutationFn: (body: { element_id: string; query: string }) =>
      postQuestion(slug!, body, token!),
    onSuccess: () => {
      toast.success("Frage gespeichert");
      setDraft("");
      qc.invalidateQueries({ queryKey: ["curate", "elements", slug] });
    },
    onError: (e: Error) => toast.error(`Fehler: ${e.message}`),
  });

  if (els.isLoading) return <div className="p-6">Lade…</div>;
  const list = els.data ?? [];
  const current = elementId ? list.find((e) => e.element_id === elementId) : list[0];
  if (!current) return <div className="p-6 text-slate-500">Keine Elemente.</div>;

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-lg font-semibold mb-3">{slug}</h1>
      <article className="border rounded p-4 mb-4">
        <div className="text-xs text-slate-500 mb-2">
          Seite {current.page_number} · <span className="font-mono">{current.element_id}</span>
        </div>
        <p className="whitespace-pre-wrap">{current.content}</p>
      </article>
      <div className="flex items-end gap-2">
        <label className="flex-1">
          <span className="text-sm text-slate-700">Neue Frage</span>
          <input
            className="input mt-1 w-full"
            placeholder="Frage zu diesem Element…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            aria-label="Frage zu diesem Element"
          />
        </label>
        <button
          className="btn-primary inline-flex items-center gap-1"
          disabled={!draft.trim() || mut.isPending}
          onClick={() => mut.mutate({ element_id: current.element_id, query: draft.trim() })}
        >
          <Plus className="w-4 h-4" /> Senden
        </button>
      </div>
    </div>
  );
}
