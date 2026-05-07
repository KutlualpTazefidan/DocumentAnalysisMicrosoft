import { useToast } from "../../../shared/components/useToast";
import { useDeleteNode } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

const VERDICT_LABEL: Record<string, string> = {
  "likely-source": "stützt — wahrscheinliche Quelle",
  "partial-support": "stützt teilweise",
  unrelated: "nicht relevant",
  contradicts: "widerspricht",
  manual: "manuell vergeben",
  unknown: "unbekannt",
};

const TAG_STYLE: Record<string, string> = {
  STÜTZT: "bg-emerald-900/40 border-emerald-600 text-emerald-100",
  WIDERSPRICHT: "bg-rose-900/40 border-rose-600 text-rose-100",
  "NICHT-RELEVANT": "bg-slate-800/60 border-slate-600 text-slate-300",
};

/**
 * Evaluation Folge-Knoten Panel: full reasoning + per-sentence
 * enumeration from Phase A's EVALUATE_SYSTEM. Read-only view; the
 * evaluation Node is immutable once spawned (re-evaluate spawns a new
 * node rather than mutating).
 */
export function EvaluationPanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "evaluation") return <></>;
  const node = view.evaluation;
  const p = node.payload as {
    verdict?: string;
    confidence?: number;
    reasoning?: string;
    sentences?: { text?: string; tag?: string; why?: string }[];
    capability_scan?: {
      approach_id?: string;
      name?: string;
      parent_capability?: string;
      matched?: boolean;
      reasons?: string[];
    }[];
  };
  const verdict = String(p.verdict ?? "unknown");
  const confidence =
    typeof p.confidence === "number" ? Math.round(p.confidence * 100) : null;
  const reasoning = String(p.reasoning ?? "");
  const sentences = Array.isArray(p.sentences) ? p.sentences : [];
  const capScan = Array.isArray(p.capability_scan) ? p.capability_scan : [];
  const capMatched = capScan.filter((c) => c.matched).length;
  const del = useDeleteNode(token, sessionId);
  const { error: toastError } = useToast();

  async function handleDelete(): Promise<void> {
    if (!window.confirm("Bewertung verwerfen?")) return;
    try {
      await del.mutateAsync(node.node_id);
      onSelectView(null);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  return (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Bewertung"
        subtitle={VERDICT_LABEL[verdict] ?? verdict}
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <div className={`flex items-baseline gap-2 ${T.body}`}>
          <span className="font-mono uppercase font-semibold text-slate-100">
            {verdict}
          </span>
          {confidence !== null && (
            <span className="text-slate-400">{confidence}% Konfidenz</span>
          )}
        </div>
        {reasoning && (
          <div>
            <p className={T.tinyBold}>Begründung</p>
            <p className={`text-slate-200 ${T.body} italic mt-1`}>{reasoning}</p>
          </div>
        )}
        {capScan.length > 0 && (
          <details
            className="rounded border border-orange-700/40 bg-orange-950/10"
            open={capMatched > 0}
          >
            <summary
              className={`${T.tinyBold} cursor-pointer px-3 py-2 text-orange-300 flex items-center gap-2`}
            >
              🔧 Fähigkeiten-Scan: {capMatched}/{capScan.length}{" "}
              {capScan.length === 1 ? "Fähigkeit" : "Fähigkeiten"}{" "}
              getriggert
              {capMatched > 0 && (
                <span className="ml-auto text-emerald-300">
                  → Gate erstellt
                </span>
              )}
            </summary>
            <ul className="px-3 pb-3 pt-1 space-y-1.5">
              {capScan.map((c) => (
                <li
                  key={c.approach_id}
                  className={`rounded px-2 py-1.5 ${
                    c.matched
                      ? "bg-emerald-900/30 border border-emerald-700/50"
                      : "bg-navy-900/50 border border-navy-700"
                  }`}
                >
                  <div className="flex items-baseline gap-2 flex-wrap">
                    <span
                      className={`font-mono ${T.body} ${
                        c.matched ? "text-emerald-200" : "text-slate-400"
                      }`}
                    >
                      {c.matched ? "✓" : "○"} {c.name}
                    </span>
                    {c.parent_capability && (
                      <span
                        className={`${T.tiny} font-mono text-orange-300/80`}
                      >
                        ↳ {c.parent_capability}
                      </span>
                    )}
                  </div>
                  {c.reasons && c.reasons.length > 0 && (
                    <ul
                      className={`mt-1 space-y-0.5 ${T.tiny} ${
                        c.matched ? "text-emerald-200/80" : "text-slate-500"
                      }`}
                    >
                      {c.reasons.map((r, i) => (
                        <li key={i}>· {r}</li>
                      ))}
                    </ul>
                  )}
                  {!c.matched && (!c.reasons || c.reasons.length === 0) && (
                    <p className={`${T.tiny} text-slate-500 italic mt-1`}>
                      Keine Trigger konfiguriert.
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}
        {sentences.length > 0 && (
          <div>
            <p className={T.tinyBold}>Per-Satz-Analyse ({sentences.length})</p>
            <ul className="mt-1 space-y-1.5">
              {sentences.map((s, i) => {
                const tag = String(s.tag ?? "").toUpperCase();
                const tagStyle =
                  TAG_STYLE[tag] ?? "bg-zinc-800 border-zinc-600 text-zinc-200";
                return (
                  <li
                    key={i}
                    className={`rounded border px-2 py-1.5 ${tagStyle}`}
                  >
                    <p className={`${T.body} italic`}>„{s.text ?? ""}"</p>
                    <div
                      className={`flex items-center gap-2 mt-1 ${T.tiny}`}
                    >
                      <span className="font-mono font-semibold uppercase">
                        {tag}
                      </span>
                      <span className="opacity-80">{s.why ?? ""}</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        <p className={`${T.tiny} text-slate-500 italic`}>
          Bewertung ist immutable — re-evaluate erzeugt eine neue Bewertung
          als Folge-Knoten.
        </p>
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={del.isPending}
          className={`w-full px-3 py-2 rounded border border-rose-700 text-rose-300 hover:bg-rose-900/30 ${T.body} disabled:opacity-50`}
        >
          {del.isPending ? "…" : "Bewertung verwerfen"}
        </button>
      </footer>
    </div>
  );
}
