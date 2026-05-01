import { useParams, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { listCurateElements, postQuestion } from "../api/curatorClient";
import { useToast } from "../../shared/components/useToast";
import { Plus, ChevronLeft, ChevronRight } from "../../shared/icons";

export function CuratorDocPage() {
  const { slug, elementId } = useParams<{ slug: string; elementId?: string }>();
  const navigate = useNavigate();
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

  const list = els.data ?? [];
  const current = elementId ? list.find((e) => e.element_id === elementId) : list[0];

  const idx = current ? list.findIndex((e) => e.element_id === current.element_id) : -1;
  const next = idx >= 0 && idx + 1 < list.length ? list[idx + 1] : null;
  const prev = idx > 0 ? list[idx - 1] : null;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.target as HTMLElement | null)?.tagName === "INPUT") return;
      if (e.key === "j" && next) navigate(`/curate/doc/${slug}/element/${next.element_id}`);
      if (e.key === "k" && prev) navigate(`/curate/doc/${slug}/element/${prev.element_id}`);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [slug, next, prev, navigate]);

  if (els.isLoading) return <div className="p-6">Lade…</div>;
  if (!current) return <div className="p-6 text-slate-500">Keine Elemente.</div>;

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <h1 className="text-lg font-semibold">{slug}</h1>
        <div className="flex gap-2">
          <button
            className="btn-secondary inline-flex items-center gap-1 px-3 py-2"
            disabled={!prev}
            onClick={() => prev && navigate(`/curate/doc/${slug}/element/${prev.element_id}`)}
            title="Vorheriges Element (k)"
          >
            <ChevronLeft className="w-4 h-4" /> Prev
          </button>
          <button
            className="btn-secondary inline-flex items-center gap-1 px-3 py-2"
            disabled={!next}
            onClick={() => next && navigate(`/curate/doc/${slug}/element/${next.element_id}`)}
            title="Nächstes Element (j)"
          >
            Next <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
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
