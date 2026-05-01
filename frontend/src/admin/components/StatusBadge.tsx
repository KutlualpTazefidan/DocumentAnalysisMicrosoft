import type { DocStatus } from "../types/domain";

const COLORS: Record<DocStatus, string> = {
  raw: "bg-gray-200 text-gray-800",
  segmenting: "bg-amber-200 text-amber-900",
  extracting: "bg-blue-200 text-blue-900",
  done: "bg-green-200 text-green-900",
  needs_ocr: "bg-red-200 text-red-900",
};

export function StatusBadge({ status }: { status: DocStatus }): JSX.Element {
  return (
    <span className={`inline-block px-2 py-0.5 text-xs rounded ${COLORS[status]}`}>
      {status}
    </span>
  );
}
