import { T } from "../../styles/typography";
import type { ProvNode } from "../../hooks/useProvenienz";

interface NodeContext {
  visited_box_ids?: string[];
  visited_doc_slugs?: string[];
  recursion_depth?: number;
  origin_chain?: { node_id: string; kind: string; label: string }[];
}

/**
 * Renders the forward-flowing investigation context that every Node
 * carries on its payload.context: the chain of upstream nodes (chunk
 * → claim → task → …), the boxes / docs the searcher should now
 * skip, and the recursion depth.
 *
 * Intentionally compact — collapses to a single label line when the
 * context is empty so panels don't get a stretched empty section.
 */
export function ContextSection({ node }: { node: ProvNode }): JSX.Element | null {
  const ctx = (node.payload as { context?: NodeContext }).context ?? {};
  const visitedBoxes = ctx.visited_box_ids ?? [];
  const visitedSlugs = ctx.visited_doc_slugs ?? [];
  const depth = ctx.recursion_depth ?? 0;
  const chain = ctx.origin_chain ?? [];
  if (
    visitedBoxes.length === 0 &&
    visitedSlugs.length === 0 &&
    depth === 0 &&
    chain.length === 0
  ) {
    return null;
  }
  return (
    <details className="rounded border border-navy-700 bg-navy-900/40">
      <summary className={`${T.tiny} cursor-pointer px-2 py-1 text-slate-400`}>
        Untersuchungskontext{" "}
        <span className="text-slate-500">
          (Tiefe {depth} · {visitedBoxes.length} Box
          {visitedBoxes.length === 1 ? "" : "en"} · {chain.length}{" "}
          Schritt{chain.length === 1 ? "" : "e"})
        </span>
      </summary>
      <div className="p-2 space-y-2">
        {chain.length > 0 && (
          <div>
            <p className={`${T.tinyBold} text-slate-300`}>Pfad</p>
            <ol className="mt-1 space-y-0.5">
              {chain.map((entry, i) => (
                <li
                  key={`${entry.node_id}-${i}`}
                  className={`${T.tiny} text-slate-300 flex gap-2`}
                >
                  <span className="text-slate-500 w-4 text-right">{i + 1}.</span>
                  <span className="text-slate-500 font-mono w-24 shrink-0">
                    {entry.kind}
                  </span>
                  <span className="text-slate-200 truncate" title={entry.label}>
                    {entry.label || "—"}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
        {visitedBoxes.length > 0 && (
          <div>
            <p className={`${T.tinyBold} text-slate-300`}>
              Bereits durchsuchte Boxen
            </p>
            <p
              className={`${T.tiny} text-slate-400 font-mono break-all`}
              title="Diese Box-IDs sind aus zukünftigen Searcher-Aufrufen ausgeschlossen."
            >
              {visitedBoxes.join(", ")}
            </p>
          </div>
        )}
        {visitedSlugs.length > 1 && (
          <div>
            <p className={`${T.tinyBold} text-slate-300`}>Berührte Dokumente</p>
            <p className={`${T.tiny} text-slate-400 font-mono`}>
              {visitedSlugs.join(", ")}
            </p>
          </div>
        )}
      </div>
    </details>
  );
}
