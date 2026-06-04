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
        className="bg-white border border-line rounded-lg shadow-2xl w-[min(1100px,95vw)] h-[min(800px,90vh)] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-line">
          <div>
            <h2 className={`${T.heading} text-bam-navy`}>Verzeichnisse</h2>
            <p className={`${T.tiny} text-ink-muted`}>
              Strukturierte Inhalts-, Tabellen-, Abbildungs- und
              Literaturverzeichnisse — gleiche Daten wie der zukünftige
              RegisterLookup-Agent-Tool.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-ink-muted hover:text-ink p-1 rounded"
            aria-label="Schließen"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        {isPending && (
          <div className={`${T.body} flex-1 flex items-center justify-center text-ink-muted`}>
            Lade Verzeichnisse…
          </div>
        )}

        {isError && (
          <div className={`${T.body} flex-1 flex items-center justify-center text-bam-red`}>
            {error instanceof Error ? error.message : "Fehler beim Laden"}
          </div>
        )}

        {!isPending && !isError && registers.length === 0 && (
          <div className={`${T.body} flex-1 flex flex-col items-center justify-center text-ink-muted gap-2`}>
            <p>Keine Verzeichnisse erkannt.</p>
            <p className={T.tiny}>
              „📑 Verzeichnisse" oben in der Top-Bar drückt die
              Heuristik manuell aus.
            </p>
          </div>
        )}

        {!isPending && !isError && registers.length > 0 && active && (
          <>
            <nav className="flex border-b border-line" role="tablist">
              {registers.map((r) => (
                <button
                  key={r.kind}
                  type="button"
                  role="tab"
                  aria-selected={r.kind === activeKind}
                  onClick={() => setActiveKind(r.kind)}
                  className={`px-4 py-2 ${T.body} flex items-center gap-2 border-b-2 transition-colors ${
                    r.kind === activeKind
                      ? "text-ink border-current"
                      : "text-ink-muted border-transparent hover:text-ink"
                  }`}
                  style={r.kind === activeKind ? { color: _KIND_COLOR[r.kind] } : undefined}
                >
                  <span
                    aria-hidden="true"
                    className="w-2.5 h-2.5 rounded-sm"
                    style={{ background: _KIND_COLOR[r.kind] }}
                  />
                  <span>{r.title}</span>
                  <span className={`${T.tiny} text-ink-muted`}>{r.entries.length}</span>
                </button>
              ))}
            </nav>

            <div className="flex-1 min-h-0 overflow-auto p-4">
              <RegisterTable register={active} />
            </div>

            <footer className="px-4 py-3 border-t border-line flex items-center justify-between">
              <span className={`${T.tiny} text-ink-muted`}>
                {active.entries.length} Einträge · {active.source_box_ids.length}{" "}
                Quellboxen · Esc zum Schließen
              </span>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(active.markdown)}
                className={`btn-secondary ${T.body}`}
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
    <table className={`${T.body} w-full text-ink border-collapse`}>
      <thead>
        <tr>
          <th className="bam-th w-20">Nr.</th>
          <th className="bam-th">{isBib ? "Quelle" : "Eintrag"}</th>
          {!isBib && <th className="bam-th w-20 text-right">Seite</th>}
        </tr>
      </thead>
      <tbody>
        {register.entries.map((e, i) => (
          <tr key={i} className="bam-row">
            <td className="bam-td text-ink-muted align-top">{e.number || "—"}</td>
            <td className="bam-td align-top">{e.title || "—"}</td>
            {!isBib && (
              <td className="bam-td text-ink-muted align-top text-right">
                {e.page || "—"}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
