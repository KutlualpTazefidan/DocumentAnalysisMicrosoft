// frontend/src/admin/components/Pagination.tsx
import { useState } from "react";
import ReactPaginate from "react-paginate";

interface Props {
  page: number;
  totalPages: number;
  onPageChange: (p: number) => void;
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

  return (
    <div className="flex items-center gap-2 text-sm select-none">
      <ReactPaginate
        pageCount={totalPages}
        forcePage={page - 1}
        onPageChange={({ selected }) => onPageChange(selected + 1)}
        marginPagesDisplayed={1}
        pageRangeDisplayed={3}
        previousLabel={<span aria-hidden>‹</span>}
        nextLabel={<span aria-hidden>›</span>}
        breakLabel={<span className="px-1 text-slate-500">…</span>}
        containerClassName="inline-flex items-center gap-1"
        pageClassName=""
        pageLinkClassName="min-w-[1.75rem] px-1 py-0.5 rounded text-xs font-medium text-slate-700 hover:bg-slate-100 inline-flex items-center justify-center"
        activeLinkClassName="!bg-blue-600 !text-white"
        previousClassName=""
        previousLinkClassName="p-1 rounded hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed text-slate-700"
        nextClassName=""
        nextLinkClassName="p-1 rounded hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed text-slate-700"
        breakClassName=""
        breakLinkClassName=""
        disabledClassName="opacity-30 cursor-not-allowed"
        renderOnZeroPageCount={null}
      />

      {/* Jump to page */}
      <form onSubmit={handleJump} className="flex items-center gap-1 ml-1">
        <input
          aria-label="Jump to page"
          type="number"
          min={1}
          max={totalPages}
          value={jumpValue}
          onChange={(e) => setJumpValue(e.target.value)}
          placeholder="Go to"
          className="w-14 text-xs border border-slate-300 rounded px-1 py-0.5 text-center bg-white text-slate-900 placeholder-slate-400 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
        <button
          type="submit"
          className="text-xs px-2 py-0.5 rounded bg-blue-600 text-white hover:bg-blue-700"
        >
          Go
        </button>
      </form>
    </div>
  );
}
