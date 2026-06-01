import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { T } from "../styles/typography";
import { useRegisters } from "../hooks/useSegments";
import type { Register, RegisterKind } from "../types/domain";

interface Props {
  open: boolean;
  slug: string;
  token: string;
  onClose: () => void;
}

const _KIND_COLOR: Record<RegisterKind, string> = {
  toc: "#ca8a04",
  list_of_tables: "#c026d3",
  list_of_figures: "#65a30d",
  bibliography: "#78350f",
};

/**
 * Modal that consolidates the four Verzeichnisse (Inhalts-, Tabellen-,
 * Abbildungs-, Literaturverzeichnis) into one tabbed view. Each tab
 * shows a structured table sourced from the backend's read_register —
 * the same data the future RegisterLookup agent-tool will surface.
 *
 * Tabs are skipped for register kinds that have no boxes on this doc
 * so the panel never shows a "0 entries" empty state.
 */
export function RegistersPanel({ open, slug, token, onClose }: Props): JSX.Element | null {
  const { data, isPending, isError, error } = useRegisters(slug, token, open);
  const [activeKind, setActiveKind] = useState<RegisterKind | null>(null);

  // Auto-select the first available register when data lands. Reset
  // when the panel closes so the next open re-syncs with whatever the
  // current first register is (handles "detected new bibliography" mid-session).
  useEffect(() => {
    if (!open) {
      setActiveKind(null);
      return;
    }
    if (activeKind === null && data && data.registers.length > 0) {
      setActiveKind(data.registers[0].kind);
    }
  }, [open, data, activeKind]);

  // Esc closes the modal. Mirrors FullscreenTextEditor's keyboard contract.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent): void => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  const registers: Register[] = data?.registers ?? [];
  const active = registers.find((r) => r.kind === activeKind) ?? null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className="bg-navy-900 border border-navy-600 rounded-lg shadow-2xl w-[min(1100px,95vw)] h-[min(800px,90vh)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-navy-700">
          <div>
            <h2 className={`${T.heading} text-white`}>Verzeichnisse</h2>
            <p className={`${T.tiny} text-slate-400`}>
              Strukturierte Inhalts-, Tabellen-, Abbildungs- und
              Literaturverzeichnisse — gleiche Daten wie der zukünftige
              RegisterLookup-Agent-Tool.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded"
            aria-label="Schließen"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        {isPending && (
          <div className={`${T.body} flex-1 flex items-center justify-center text-slate-400`}>
            Lade Verzeichnisse…
          </div>
        )}

        {isError && (
          <div className={`${T.body} flex-1 flex items-center justify-center text-rose-300`}>
            {error instanceof Error ? error.message : "Fehler beim Laden"}
          </div>
        )}

        {!isPending && !isError && registers.length === 0 && (
          <div className={`${T.body} flex-1 flex flex-col items-center justify-center text-slate-400 gap-2`}>
            <p>Keine Verzeichnisse erkannt.</p>
            <p className={T.tiny}>
              „📑 Verzeichnisse" oben in der Top-Bar drückt die
              Heuristik manuell aus.
            </p>
          </div>
        )}

        {!isPending && !isError && registers.length > 0 && active && (
          <>
            <nav className="flex border-b border-navy-700" role="tablist">
              {registers.map((r) => (
                <button
                  key={r.kind}
                  type="button"
                  role="tab"
                  aria-selected={r.kind === activeKind}
                  onClick={() => setActiveKind(r.kind)}
                  className={`px-4 py-2 ${T.body} flex items-center gap-2 border-b-2 transition-colors ${
                    r.kind === activeKind
                      ? "text-white border-current"
                      : "text-slate-400 border-transparent hover:text-slate-200"
                  }`}
                  style={r.kind === activeKind ? { color: _KIND_COLOR[r.kind] } : undefined}
                >
                  <span
                    aria-hidden="true"
                    className="w-2.5 h-2.5 rounded-sm"
                    style={{ background: _KIND_COLOR[r.kind] }}
                  />
                  <span>{r.title}</span>
                  <span className={`${T.tiny} text-slate-500`}>{r.entries.length}</span>
                </button>
              ))}
            </nav>

            <div className="flex-1 min-h-0 overflow-auto p-4">
              <RegisterTable register={active} />
            </div>

            <footer className="px-4 py-3 border-t border-navy-700 flex items-center justify-between">
              <span className={`${T.tiny} text-slate-500`}>
                {active.entries.length} Einträge · {active.source_box_ids.length}{" "}
                Quellboxen · Esc zum Schließen
              </span>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(active.markdown)}
                className={`px-3 py-1 rounded bg-navy-800 hover:bg-navy-700 text-slate-200 ${T.body}`}
                title="Markdown-Tabelle in Zwischenablage kopieren"
              >
                Markdown kopieren
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}

function RegisterTable({ register }: { register: Register }): JSX.Element {
  const isBib = register.kind === "bibliography";
  return (
    <table className={`${T.body} w-full text-slate-200 border-collapse`}>
      <thead>
        <tr className="border-b border-navy-600 text-slate-400 text-left">
          <th className="py-2 px-3 w-20 font-semibold">Nr.</th>
          <th className="py-2 px-3 font-semibold">{isBib ? "Quelle" : "Eintrag"}</th>
          {!isBib && <th className="py-2 px-3 w-20 font-semibold text-right">Seite</th>}
        </tr>
      </thead>
      <tbody>
        {register.entries.map((e, i) => (
          <tr key={i} className="border-b border-navy-800 hover:bg-navy-800/40">
            <td className="py-1.5 px-3 text-slate-400 align-top">{e.number || "—"}</td>
            <td className="py-1.5 px-3 align-top">{e.title || "—"}</td>
            {!isBib && (
              <td className="py-1.5 px-3 text-slate-400 align-top text-right">
                {e.page || "—"}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
