// frontend/src/admin/components/Pagination.tsx
import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface Props {
  page: number;
  totalPages: number;
  onPageChange: (p: number) => void;
}

/** Build the list of page numbers (or "..." sentinels) to render. */
function buildPages(page: number, total: number): (number | "...")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);

  const pages: (number | "...")[] = [];
  // Always show first 3 and last 3; insert ellipsis in gaps > 1.
  const firstBand = new Set([1, 2, 3]);
  const lastBand = new Set([total - 2, total - 1, total]);
  // Always include current ± 1.
  const midBand = new Set([page - 1, page, page + 1].filter((p) => p >= 1 && p <= total));

  const shown = new Set([...firstBand, ...midBand, ...lastBand]);
  const sorted = Array.from(shown).sort((a, b) => a - b);

  let prev: number | null = null;
  for (const n of sorted) {
    if (prev !== null && n - prev > 1) pages.push("...");
    pages.push(n);
    prev = n;
  }
  return pages;
}

export function Pagination({ page, totalPages, onPageChange }: Props): JSX.Element {
  const [jumpValue, setJumpValue] = useState("");

  function handleJump(e: React.FormEvent) {
    e.preventDefault();
    const n = parseInt(jumpValue, 10);
    if (!isNaN(n) && n >= 1 && n <= totalPages) {
      onPageChange(n);
      setJumpValue("");
    }
  }

  const pages = buildPages(page, totalPages);

  return (
    <div className="flex items-center gap-1 text-sm select-none">
      {/* Prev */}
      <button
        aria-label="Previous page"
        className="p-1 rounded hover:bg-navy-700 disabled:opacity-40 disabled:cursor-not-allowed"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
      >
        <ChevronLeft className="w-4 h-4" />
      </button>

      {/* Page number buttons */}
      {pages.map((p, idx) =>
        p === "..." ? (
          <span key={`ellipsis-${idx}`} className="px-1 text-gray-400">
            …
          </span>
        ) : (
          <button
            key={p}
            aria-label={`Page ${p}`}
            aria-current={p === page ? "page" : undefined}
            className={`min-w-[1.75rem] px-1 py-0.5 rounded text-xs font-medium ${
              p === page
                ? "bg-blue-600 text-white"
                : "hover:bg-gray-200 text-gray-700"
            }`}
            onClick={() => onPageChange(p)}
          >
            {p}
          </button>
        ),
      )}

      {/* Next */}
      <button
        aria-label="Next page"
        className="p-1 rounded hover:bg-navy-700 disabled:opacity-40 disabled:cursor-not-allowed"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
      >
        <ChevronRight className="w-4 h-4" />
      </button>

      {/* Jump to page */}
      <form onSubmit={handleJump} className="flex items-center gap-1 ml-2">
        <input
          aria-label="Jump to page"
          type="number"
          min={1}
          max={totalPages}
          value={jumpValue}
          onChange={(e) => setJumpValue(e.target.value)}
          placeholder="Go to"
          className="w-16 text-xs border rounded px-1 py-0.5 text-center [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
        <button
          type="submit"
          className="text-xs px-2 py-0.5 rounded border hover:bg-gray-100"
        >
          Go
        </button>
      </form>
    </div>
  );
}
