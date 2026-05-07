import { useState } from "react";
import { CheckCircle2, X } from "lucide-react";

import { useToast } from "../../../shared/components/useToast";
import { useDeleteNode, useReEvaluate } from "../../hooks/useProvenienz";
import { T } from "../../styles/typography";
import { PanelHeader, type PanelCommonProps } from "../SidePanel";

interface DetectedEntry {
  name: string;
  approach_id: string;
  kind: "top" | "sub";
  parent?: string;
  reasons?: string[];
}

/**
 * Side-panel for a capability_gate. Lists detected top-level + sub
 * capabilities with their match-reasons + domain_rules preview. The
 * user picks which to apply (default: all selected) and clicks
 * "Re-evaluieren" — backend spawns a fresh action_proposal with the
 * domain rules injected into the evaluate prompt. Dismiss leaves the
 * gate as-is for audit.
 */
export function CapabilityGatePanel({
  sessionId,
  token,
  view,
  onSelectView,
}: PanelCommonProps): JSX.Element {
  if (view.kind !== "capability_gate") return <></>;
  const node = view.gate;
  const p = node.payload as {
    evaluation_node_id?: string;
    detected?: DetectedEntry[];
    capability_ids?: string[];
    loaded_rules_preview?: string;
    status?: string;
    re_evaluate_proposal_id?: string;
  };
  const detected = Array.isArray(p.detected) ? p.detected : [];
  const initialSelection = new Set(
    Array.isArray(p.capability_ids) ? p.capability_ids : [],
  );
  const [selected, setSelected] = useState<Set<string>>(initialSelection);
  const reEval = useReEvaluate(token, sessionId);
  const del = useDeleteNode(token, sessionId);
  const { error: toastError } = useToast();
  const status = String(p.status ?? "pending");
  const isPending = status === "pending";

  function toggle(id: string): void {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleReEval(): Promise<void> {
    if (selected.size === 0) {
      toastError("Bitte mindestens eine Capability auswählen.");
      return;
    }
    try {
      const result = await reEval.mutateAsync({
        gateNodeId: node.node_id,
        capabilityIds: [...selected],
      });
      // Land on the new action_proposal so the user can decide.
      onSelectView(`view:${result.action_proposal.node_id}`);
    } catch (e) {
      toastError(e instanceof Error ? e.message : "Fehler");
    }
  }

  async function handleDismiss(): Promise<void> {
    if (!window.confirm("Gate verwerfen — Capabilities ignorieren?")) return;
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
        title="Capability-Gate"
        subtitle={
          isPending
            ? `🔧 ${detected.length} Capabilities erkannt`
            : status === "accepted"
              ? "✓ Re-Evaluation gestartet"
              : "verworfen"
        }
        onClose={() => onSelectView(null)}
      />
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {!isPending && p.re_evaluate_proposal_id && (
          <p className={`${T.body} text-emerald-300`}>
            Re-Evaluation läuft als Folge-Knoten — siehe Chain.
          </p>
        )}
        <div>
          <p className={T.tinyBold}>Erkannte Capabilities</p>
          <ul className="mt-1 space-y-1.5">
            {detected.map((d, i) => {
              const isSelected = selected.has(d.approach_id);
              const isSub = d.kind === "sub";
              return (
                <li
                  key={i}
                  className={`rounded border px-2 py-1.5 ${
                    isSelected
                      ? "border-orange-500 bg-orange-950/40"
                      : "border-navy-600 bg-navy-900/40 opacity-70"
                  } ${isSub ? "ml-4" : ""}`}
                >
                  <label className="flex items-start gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      disabled={!isPending}
                      onChange={() => toggle(d.approach_id)}
                      className="mt-1"
                    />
                    <div className="flex-1 min-w-0">
                      <p className={`${T.body} text-slate-100`}>
                        <span className="font-mono text-orange-200">
                          {d.name}
                        </span>
                        {isSub && d.parent && (
                          <span className="text-slate-500 text-[11px]">
                            {" "}
                            · sub von {d.parent}
                          </span>
                        )}
                      </p>
                      {Array.isArray(d.reasons) && d.reasons.length > 0 && (
                        <ul className="mt-0.5 space-y-0.5">
                          {d.reasons.map((r, j) => (
                            <li
                              key={j}
                              className="text-[11px] text-orange-200/80 italic before:content-['→_']"
                            >
                              {r}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </label>
                </li>
              );
            })}
          </ul>
        </div>
        {p.loaded_rules_preview && (
          <details>
            <summary className={`${T.tiny} cursor-pointer text-slate-400`}>
              Domain-Rules-Vorschau ({p.loaded_rules_preview.length} Zeichen)
            </summary>
            <pre className="mt-1 p-2 rounded bg-navy-950 text-[11px] text-slate-300 whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
              {p.loaded_rules_preview}
            </pre>
          </details>
        )}
        {reEval.error && (
          <p className={`${T.body} text-red-400`}>{reEval.error.message}</p>
        )}
      </div>
      <footer className="p-3 border-t border-navy-700 space-y-2">
        {isPending && (
          <>
            <button
              type="button"
              onClick={() => void handleReEval()}
              disabled={reEval.isPending || selected.size === 0}
              className={`w-full px-3 py-2 rounded bg-orange-500 hover:bg-orange-400 text-orange-950 font-semibold ${T.body} flex items-center justify-center gap-2 disabled:opacity-50`}
            >
              <CheckCircle2 className="w-4 h-4" aria-hidden />
              {reEval.isPending
                ? "Re-evaluiert…"
                : `Re-evaluieren mit ${selected.size} Capability${selected.size === 1 ? "" : "s"}`}
            </button>
            <button
              type="button"
              onClick={() => void handleDismiss()}
              disabled={del.isPending}
              className={`w-full px-3 py-2 rounded border border-zinc-600 text-zinc-300 hover:bg-zinc-800/40 ${T.body} flex items-center justify-center gap-2 disabled:opacity-50`}
            >
              <X className="w-4 h-4" aria-hidden />
              {del.isPending ? "…" : "Gate verwerfen"}
            </button>
          </>
        )}
      </footer>
    </div>
  );
}
