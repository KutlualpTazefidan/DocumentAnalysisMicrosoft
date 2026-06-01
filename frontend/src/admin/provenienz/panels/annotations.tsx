import { type ProvEdge, type ProvNode } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";

/**
 * Generic enrichment-annotation helpers shared by ClaimPanel /
 * SearchResultPanel / future anchor panels.
 *
 * The agent's enrichment dispatcher spawns one annotation Node per
 * enrichment skill output and mirrors it with an `enriches` edge
 * (annotation → anchor). The frontend only needs the edge to find
 * which annotations belong to a given anchor — the kind name and
 * payload shape come from the skill itself.
 */

export interface AnnotationGroup {
  /** Node `kind` — also the enrichment-skill's `output.annotation_kind`. */
  kind: string;
  /** Newest node first. */
  nodes: ProvNode[];
}

/**
 * Human-friendly headings for known annotation kinds. Unknown kinds
 * fall back to the raw `kind` string — that way new enrichment skills
 * surface immediately, just without a translated heading.
 */
export const ANNOTATION_LABEL: Record<string, string> = {
  claim_background: "Aussage-Hintergrund",
};

/**
 * Render-order for annotation kinds. Known kinds first (in this
 * order), unknown kinds appended alphabetically.
 */
export const ANNOTATION_KIND_ORDER: string[] = ["claim_background"];

/**
 * Collect every Node connected to `anchorNodeId` via an `enriches`
 * edge, grouped by Node `kind`, newest-first within each group.
 *
 * Skill-agnostic: any future enrichment skill that follows the
 * dispatcher contract (spawn annotation Node + mirror `enriches`
 * edge → anchor) surfaces here automatically, no frontend change
 * required.
 */
export function groupAnnotationsByKind(
  nodes: ProvNode[],
  edges: ProvEdge[],
  anchorNodeId: string,
): AnnotationGroup[] {
  const annotationIds = new Set<string>();
  for (const e of edges) {
    if (e.kind === "enriches" && e.to_node === anchorNodeId) {
      annotationIds.add(e.from_node);
    }
  }
  if (annotationIds.size === 0) return [];

  const byKind = new Map<string, ProvNode[]>();
  for (const n of nodes) {
    if (!annotationIds.has(n.node_id)) continue;
    if (!byKind.has(n.kind)) byKind.set(n.kind, []);
    byKind.get(n.kind)!.push(n);
  }
  const out: AnnotationGroup[] = [];
  for (const [kind, list] of byKind) {
    list.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    out.push({ kind, nodes: list });
  }
  out.sort((a, b) => {
    const ai = ANNOTATION_KIND_ORDER.indexOf(a.kind);
    const bi = ANNOTATION_KIND_ORDER.indexOf(b.kind);
    if (ai >= 0 && bi >= 0) return ai - bi;
    if (ai >= 0) return -1;
    if (bi >= 0) return 1;
    return a.kind.localeCompare(b.kind);
  });
  return out;
}

/**
 * Cyan-tinted card that shows the latest annotation in a group plus
 * a small attribution line (skill name + version).
 *
 * Returns `null` when the latest node has no payload `text` — keeps
 * empty/half-baked annotations from polluting the panel.
 */
export function AnnotationCard({
  group,
}: {
  group: AnnotationGroup;
}): JSX.Element | null {
  const latest = group.nodes[0];
  if (!latest) return null;
  const text = String(latest.payload.text ?? "").trim();
  if (!text) return null;
  const skillName = String(latest.payload.skill_name ?? "");
  const skillVersion = latest.payload.skill_version;
  const label = ANNOTATION_LABEL[group.kind] ?? group.kind;
  return (
    <div className="rounded border border-cyan-700/40 bg-cyan-950/20 px-3 py-2">
      <p
        className={`${T.tinyBold} text-cyan-300 flex items-center gap-2 flex-wrap`}
      >
        <span>🧠 {label}</span>
        {skillName && (
          <span className="font-normal text-slate-500">
            (von {skillName}
            {typeof skillVersion === "number" ? ` v${skillVersion}` : ""})
          </span>
        )}
      </p>
      <p className={`text-cyan-100 ${T.body} mt-1 whitespace-pre-wrap`}>
        {text}
      </p>
    </div>
  );
}
