import type { DocStatus } from "../types/domain";
import {
  Circle,
  Clock,
  RefreshCcw,
  CheckCircle2,
  AlertTriangle,
} from "../../shared/icons";
import type { ComponentType } from "react";
import { T } from "../styles/typography";

export type StatusTone =
  | "neutral" // raw / unstarted
  | "info" // intermediate / non-final
  | "progress" // actively running
  | "success" // completed / active
  | "warning" // needs attention but not error
  | "danger" // error / inactive
  | "muted"; // archived / disabled

// BAM semantic fills — success/danger sampled from the reference
// dashboard (green #006d00 on #ceeccc, red #a80019 on #ffdad1); info uses
// the cyan row-tint; warning a light amber.
const TONE_CLASS: Record<StatusTone, string> = {
  neutral: "bg-[#ededed] text-ink",
  info: "bg-rowsel text-[#0072a3]",
  progress: "bg-[#fff3d6] text-warn",
  success: "bg-ok-fill text-ok",
  warning: "bg-[#fff3d6] text-warn",
  danger: "bg-bad-fill text-bad",
  muted: "bg-[#f0f0f0] text-ink-muted",
};

interface Props {
  tone: StatusTone;
  label: string;
  icon?: ComponentType<{ className?: string }>;
}

/**
 * One badge for every discrete state in the UI — doc status, user
 * active flag, future role indicators, etc. Pass a translated label
 * and a semantic tone; supply an icon when one makes the state more
 * scannable. The audit's "five visual languages for status" finding
 * is resolved by routing every state through this primitive.
 *
 * For the doc-status enum specifically, prefer `<DocStatusBadge>` —
 * it owns the German label + tone + icon mapping.
 */
export function StatusBadge({ tone, label, icon: Icon }: Props): JSX.Element {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 ${T.body} rounded ${TONE_CLASS[tone]}`}
    >
      {Icon && <Icon className="w-3 h-3" aria-hidden />}
      {label}
    </span>
  );
}

const DOC_STATUS_TONE: Record<DocStatus, StatusTone> = {
  raw: "neutral",
  segmenting: "progress",
  extracting: "progress",
  extracted: "info",
  synthesising: "progress",
  synthesised: "info",
  "open-for-curation": "success",
  archived: "muted",
  done: "success",
  needs_ocr: "danger",
};

const DOC_STATUS_LABEL: Record<DocStatus, string> = {
  raw: "Roh",
  segmenting: "Segmentierung läuft",
  extracting: "Extraktion läuft",
  extracted: "Extrahiert",
  synthesising: "Synthese läuft",
  synthesised: "Synthetisiert",
  "open-for-curation": "Zur Kuration",
  archived: "Archiviert",
  done: "Fertig",
  needs_ocr: "OCR nötig",
};

const DOC_STATUS_ICON: Record<DocStatus, ComponentType<{ className?: string }>> = {
  raw: Circle,
  segmenting: Clock,
  extracting: RefreshCcw,
  extracted: CheckCircle2,
  synthesising: Clock,
  synthesised: CheckCircle2,
  "open-for-curation": CheckCircle2,
  archived: AlertTriangle,
  done: CheckCircle2,
  needs_ocr: AlertTriangle,
};

export function DocStatusBadge({ status }: { status: DocStatus }): JSX.Element {
  return (
    <StatusBadge
      tone={DOC_STATUS_TONE[status]}
      label={DOC_STATUS_LABEL[status]}
      icon={DOC_STATUS_ICON[status]}
    />
  );
}
