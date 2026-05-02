import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { T } from "../styles/typography";
import type { ExtractDiagnostic } from "../hooks/useExtract";

interface Props {
  /** undefined = mineru.json has no diagnostics field (stale data, written
   *  by code older than commit df94505). Empty array = doc was extracted with
   *  the new code but no notable events fired. Non-empty = events to display. */
  diagnostics: ExtractDiagnostic[] | undefined;
  currentPage: number;
}

/**
 * Sidebar diagnostic block — surfaces per-page assignment + rescue events:
 *   • split:                  block decomposed into sub-elements
 *   • no_decomposition:       block overlaps multiple bboxes, no split
 *   • caption_rescue:         caption inside a table routed to a heading bbox
 *   • caption_rescue_failed:  adjacent neighbor existed but no caption text
 *                             could be extracted from its HTML
 *
 * Three header states surface the situation to the user:
 *   - "Diagnostics nicht verfügbar — Seite neu extrahieren" when the field
 *     is absent from mineru.json (stale data).
 *   - "Diagnose · Seite N — keine Ereignisse" when the doc has diagnostics
 *     but the current page had no notable events.
 *   - "Diagnose · Seite N · ✓ ⤴ ⚠ ✗" when there are events to expand.
 */
export function ExtractDiagnose({ diagnostics, currentPage }: Props): JSX.Element {
  const [open, setOpen] = useState(false);

  if (diagnostics === undefined) {
    return (
      <div className="flex flex-col gap-1 border-t border-slate-200 pt-2">
        <div className={`${T.tinyBold} text-slate-500`}>Diagnose</div>
        <p className={`${T.tiny} text-slate-500 italic`}>
          Diagnostics nicht verfügbar — diese Seite neu extrahieren, dann erscheinen
          Aufteilungs- und Caption-Rescue-Events hier.
        </p>
      </div>
    );
  }

  const onPage = diagnostics.filter((d) => d.page === currentPage);
  if (onPage.length === 0) {
    return (
      <div className="flex flex-col gap-1 border-t border-slate-200 pt-2">
        <div className={`${T.tinyBold} text-slate-500`}>Diagnose · Seite {currentPage}</div>
        <p className={`${T.tiny} text-slate-500 italic`}>Keine Ereignisse auf dieser Seite.</p>
      </div>
    );
  }

  const splits = onPage.filter((d) => d.kind === "split").length;
  const warnings = onPage.filter((d) => d.kind === "no_decomposition").length;
  const captions = onPage.filter((d) => d.kind === "caption_rescue").length;
  const capFails = onPage.filter((d) => d.kind === "caption_rescue_failed").length;

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
          {captions > 0 && (
            <span className="text-blue-700" title={`${captions} caption rescued`}>
              ⤴ {captions}
            </span>
          )}
          {warnings > 0 && (
            <span className="text-amber-700" title={`${warnings} no-decomposition`}>
              ⚠ {warnings}
            </span>
          )}
          {capFails > 0 && (
            <span className="text-red-700" title={`${capFails} caption rescue failed`}>
              ✗ {capFails}
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
                <DiagItem key={i} d={d} />
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DiagItem({ d }: { d: ExtractDiagnostic }): JSX.Element {
  const cls =
    d.kind === "split"
      ? "border-green-200 bg-green-50 text-green-900"
      : d.kind === "caption_rescue"
      ? "border-blue-200 bg-blue-50 text-blue-900"
      : d.kind === "caption_rescue_failed"
      ? "border-red-200 bg-red-50 text-red-900"
      : "border-amber-200 bg-amber-50 text-amber-900";

  if (d.kind === "split") {
    return (
      <li className={`${T.tiny} rounded border px-2 py-1 ${cls}`}>
        <div className="font-semibold">
          Block aufgeteilt in {d.n_sub_elements} Elemente
        </div>
        <div className={`${T.tinyMuted} mt-0.5`}>
          Type: {d.block_type || "—"} · Boxes: {(d.user_bboxes || []).join(", ")}
        </div>
        <div className="font-mono text-[10px] text-slate-500 mt-0.5 line-clamp-2">
          {d.text_preview || "(no text)"}
        </div>
      </li>
    );
  }
  if (d.kind === "no_decomposition") {
    return (
      <li className={`${T.tiny} rounded border px-2 py-1 ${cls}`}>
        <div className="font-semibold">
          Block überlappt mehrere Bboxen, keine Aufteilung
        </div>
        <div className={`${T.tinyMuted} mt-0.5`}>
          Type: {d.block_type || "—"} · Boxes: {(d.user_bboxes || []).join(", ")}
        </div>
        <div className="font-mono text-[10px] text-slate-500 mt-0.5 line-clamp-2">
          {d.text_preview || "(no text)"}
        </div>
      </li>
    );
  }
  if (d.kind === "caption_rescue") {
    return (
      <li className={`${T.tiny} rounded border px-2 py-1 ${cls}`}>
        <div className="font-semibold">
          Caption von {d.target_visual_bbox} → {d.source_bbox}
        </div>
        <div className={`${T.tinyMuted} mt-0.5`}>
          {d.click_remap ? "Klick auf Caption → Heading-Bbox" : "Klick-Mapping nicht angepasst"}
        </div>
        <div className="font-mono text-[10px] text-slate-500 mt-0.5 line-clamp-2">
          {d.caption_text || "(no caption text)"}
        </div>
      </li>
    );
  }
  // caption_rescue_failed
  return (
    <li className={`${T.tiny} rounded border px-2 py-1 ${cls}`}>
      <div className="font-semibold">
        Caption-Rescue fehlgeschlagen für {d.source_bbox}
      </div>
      <div className={`${T.tinyMuted} mt-0.5`}>
        Nachbar: {d.target_visual_bbox} · keine Caption im HTML gefunden
      </div>
      <div className="font-mono text-[10px] text-slate-500 mt-0.5 line-clamp-2">
        {d.text_preview || "(no preview)"}
      </div>
    </li>
  );
}
