import type { DocStatus } from "../types/domain";
import { Circle, Clock, RefreshCcw, CheckCircle2, AlertTriangle } from "../../shared/icons";
import type { ComponentType } from "react";
import { T } from "../styles/typography";

const COLORS: Record<DocStatus, string> = {
  raw: "bg-gray-200 text-gray-800",
  segmenting: "bg-amber-200 text-amber-900",
  extracting: "bg-blue-200 text-blue-900",
  extracted: "bg-blue-300 text-blue-900",
  synthesising: "bg-purple-200 text-purple-900",
  synthesised: "bg-purple-300 text-purple-900",
  "open-for-curation": "bg-green-200 text-green-900",
  archived: "bg-gray-400 text-gray-900",
  done: "bg-green-200 text-green-900",
  needs_ocr: "bg-red-200 text-red-900",
};

const ICONS: Record<DocStatus, ComponentType<{ className?: string }>> = {
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

export function StatusBadge({ status }: { status: DocStatus }): JSX.Element {
  const Icon = ICONS[status];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 ${T.body} rounded ${COLORS[status]}`}>
      <Icon className="w-3 h-3" />
      {status}
    </span>
  );
}
