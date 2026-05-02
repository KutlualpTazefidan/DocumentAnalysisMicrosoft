import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { T } from "../styles/typography";
import type { ExtractDiagnostic } from "../hooks/useExtract";

interface Props {
  diagnostics: ExtractDiagnostic[];
  currentPage: number;
}

/**
 * Sidebar diagnostic block — surfaces the worker's per-page assignment
 * decisions (when a MinerU block was split into sub-elements, when an
 * overlap couldn't be decomposed, etc.). Reads `mineru.json.diagnostics`
 * which the backend writes alongside the elements list.
 *
 * Shows only entries for the current page, with a count summary in the
 * collapsed header. Expanding reveals one row per event.
 */
export function ExtractDiagnose({ diagnostics, currentPage }: Props): JSX.Element | null {
  const [open, setOpen] = useState(false);
  const onPage = diagnostics.filter((d) => d.page === currentPage);
  if (onPage.length === 0) return null;

  const splits = onPage.filter((d) => d.kind === "split").length;
  const warnings = onPage.filter((d) => d.kind === "no_decomposition").length;

  return (
    <div className="flex flex-col gap-1 border-t border-slate-200 pt-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((p) => !p)}
        className={`flex items-center justify-between ${T.tinyBold} hover:text-slate-700`}
      >
        <span>Diagnose · Seite {currentPage}</span>
        <span className="flex items-center gap-2">
          {splits > 0 && (
            <span className="text-green-700" title={`${splits} blocks split`}>
              ✓ {splits}
            </span>
          )}
          {warnings > 0 && (
            <span className="text-amber-700" title={`${warnings} no-decomposition`}>
              ⚠ {warnings}
            </span>
          )}
          <motion.span
            aria-hidden="true"
            animate={{ rotate: open ? 180 : 0 }}
            transition={{ duration: 0.15 }}
          >
            ▾
          </motion.span>
        </span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            style={{ overflow: "hidden" }}
          >
            <ul className="flex flex-col gap-1.5 mt-1">
              {onPage.map((d, i) => (
                <li
                  key={i}
                  className={`${T.tiny} rounded border px-2 py-1 ${
                    d.kind === "split"
                      ? "border-green-200 bg-green-50 text-green-900"
                      : "border-amber-200 bg-amber-50 text-amber-900"
                  }`}
                >
                  <div className="font-semibold">
                    {d.kind === "split"
                      ? `Block aufgeteilt in ${d.n_sub_elements} Elemente`
                      : "Block überlappt mehrere Bboxen, keine Aufteilung"}
                  </div>
                  <div className={`${T.tinyMuted} mt-0.5`}>
                    Type: {d.block_type || "—"} · Boxes: {d.user_bboxes.join(", ")}
                  </div>
                  <div className="font-mono text-[10px] text-slate-500 mt-0.5 line-clamp-2">
                    {d.text_preview || "(no text)"}
                  </div>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
