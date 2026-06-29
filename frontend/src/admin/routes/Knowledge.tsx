import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../auth/useAuth";
import { getConcept, listBases, listConcepts } from "../api/knowledge";

interface Props {
  /** Override token for testing; production reads it from useAuth(). */
  token?: string;
}

export function Knowledge({ token: tokenProp }: Props = {}): JSX.Element {
  const { token: authToken } = useAuth();
  const token = tokenProp ?? authToken ?? "";

  const [base, setBase] = useState<string | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const basesQ = useQuery({
    queryKey: ["kb-bases"],
    queryFn: () => listBases(token),
    staleTime: 60_000,
  });
  const conceptsQ = useQuery({
    queryKey: ["kb-concepts", base],
    queryFn: () => listConcepts(base as string, token),
    enabled: !!base,
  });
  const conceptQ = useQuery({
    queryKey: ["kb-concept", base, path],
    queryFn: () => getConcept(base as string, path as string, token),
    enabled: !!base && !!path,
  });

  // auto-select the first base
  useEffect(() => {
    if (!base && basesQ.data && basesQ.data.length > 0) setBase(basesQ.data[0].name);
  }, [base, basesQ.data]);

  if (!token) return <div className="p-8 text-slate-500">Bitte anmelden.</div>;

  const concepts = (conceptsQ.data ?? []).filter((c) => {
    const q = filter.trim().toLowerCase();
    if (!q) return true;
    return (
      c.title.toLowerCase().includes(q) ||
      c.type.toLowerCase().includes(q) ||
      c.tags.some((t) => t.toLowerCase().includes(q))
    );
  });

  const grouped = new Map<string, typeof concepts>();
  for (const c of concepts) {
    const key = c.type || "(ohne Typ)";
    (grouped.get(key) ?? grouped.set(key, []).get(key)!).push(c);
  }

  const c = conceptQ.data;

  return (
    <div className="h-full flex">
      {/* Left: base selector + concept list */}
      <aside className="w-80 shrink-0 border-r border-slate-200 overflow-y-auto p-4">
        <select
          className="w-full mb-3 rounded border border-slate-300 px-2 py-1 text-sm"
          value={base ?? ""}
          onChange={(e) => { setBase(e.target.value); setPath(null); }}
        >
          {(basesQ.data ?? []).map((b) => (
            <option key={b.name} value={b.name}>{b.title} ({b.concept_count})</option>
          ))}
        </select>
        <input
          className="w-full mb-3 rounded border border-slate-300 px-2 py-1 text-sm"
          placeholder="Filtern…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        {[...grouped.entries()].map(([type, items]) => (
          <div key={type} className="mb-3">
            <div className="text-xs font-semibold uppercase text-slate-400 mb-1">{type}</div>
            <ul>
              {items.map((it) => (
                <li key={it.path}>
                  <button
                    className={`block w-full text-left px-2 py-1 rounded text-sm hover:bg-slate-100 ${
                      it.path === path ? "bg-cyan-50 text-bam-cyan" : ""
                    }`}
                    onClick={() => setPath(it.path)}
                  >
                    {it.title}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </aside>

      {/* Right: concept view */}
      <main className="flex-1 overflow-y-auto p-6">
        {!c && <div className="text-slate-400">Konzept auswählen.</div>}
        {c && (
          <article className="max-w-3xl">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs px-2 py-0.5 rounded bg-cyan-50 text-bam-cyan border border-bam-cyan">
                {c.type || "(ohne Typ)"}
              </span>
              {c.malformed && (
                <span className="text-xs px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-300">
                  Frontmatter fehlerhaft
                </span>
              )}
              {c.tags.map((t) => (
                <span key={t} className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-500">{t}</span>
              ))}
            </div>
            <h1 className="text-2xl font-semibold mb-1">{c.title}</h1>
            {c.description && <p className="text-slate-500 mb-4">{c.description}</p>}
            <pre className="whitespace-pre-wrap text-sm text-slate-800 mb-6 font-sans">{c.body}</pre>
            {c.links.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-slate-400 uppercase mb-2">Verweise</h2>
                <ul className="space-y-1">
                  {c.links.map((ln) => (
                    <li key={`${ln.text}|${ln.path}`}>
                      <button
                        disabled={!ln.resolved}
                        className={`text-sm ${
                          ln.resolved
                            ? "text-bam-cyan hover:underline"
                            : "text-slate-400 line-through cursor-not-allowed"
                        }`}
                        onClick={() => ln.resolved && setPath(ln.path)}
                      >
                        {ln.text}
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </article>
        )}
      </main>
    </div>
  );
}
