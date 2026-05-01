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
        breakLabel={<span className="px-1 text-gray-200">…</span>}
        containerClassName="inline-flex items-center gap-1"
        pageClassName=""
        pageLinkClassName="min-w-[1.75rem] px-1 py-0.5 rounded text-xs font-medium text-gray-200 hover:bg-navy-700 inline-flex items-center justify-center"
        activeLinkClassName="!bg-blue-600 !text-white"
        previousClassName=""
        previousLinkClassName="p-1 rounded hover:bg-navy-700 disabled:opacity-40 disabled:cursor-not-allowed text-gray-200"
        nextClassName=""
        nextLinkClassName="p-1 rounded hover:bg-navy-700 disabled:opacity-40 disabled:cursor-not-allowed text-gray-200"
        breakClassName=""
        breakLinkClassName=""
        disabledClassName="opacity-40 cursor-not-allowed"
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
          className="w-14 text-xs border border-navy-600 rounded px-1 py-0.5 text-center bg-navy-700 text-white placeholder-gray-400 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
        <button
          type="submit"
          className="text-xs px-2 py-0.5 rounded bg-blue-600 text-white hover:bg-blue-500"
        >
          Go
        </button>
      </form>
    </div>
  );
}
