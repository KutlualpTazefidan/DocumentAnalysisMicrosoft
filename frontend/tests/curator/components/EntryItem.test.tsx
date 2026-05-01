import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EntryItem } from "../../../src/curator/components/EntryItem";
import type { RetrievalEntry } from "../../../src/shared/types/domain";

const baseEntry: RetrievalEntry = {
  entry_id: "e_001",
  query: "Welche Norm gilt für M6?",
  expected_chunk_ids: [],
  chunk_hashes: {},
  review_chain: [
    {
      timestamp_utc: "2026-04-30T07:00:00Z",
      action: "created_from_scratch",
      actor: { kind: "human", pseudonym: "alice", level: "phd" },
      notes: null,
    },
  ],
  deprecated: false,
  refines: null,
  task_type: "retrieval",
  source_element: null,
};

describe("EntryItem", () => {
  it("renders the query and the actor pseudonym", () => {
    render(<EntryItem entry={baseEntry} onRefine={() => {}} onDeprecate={() => {}} />);
    expect(screen.getByText(/welche norm/i)).toBeInTheDocument();
    expect(screen.getByText(/alice/)).toBeInTheDocument();
    expect(screen.getByText(/phd/)).toBeInTheDocument();
  });

  it("calls onRefine when Verfeinern button is clicked", async () => {
    const onRefine = vi.fn();
    const user = userEvent.setup();
    render(<EntryItem entry={baseEntry} onRefine={onRefine} onDeprecate={() => {}} />);
    await user.click(screen.getByRole("button", { name: /verfeinern/i }));
    expect(onRefine).toHaveBeenCalledWith(baseEntry);
  });

  it("calls onDeprecate when Zurückziehen button is clicked", async () => {
    const onDeprecate = vi.fn();
    const user = userEvent.setup();
    render(<EntryItem entry={baseEntry} onRefine={() => {}} onDeprecate={onDeprecate} />);
    await user.click(screen.getByRole("button", { name: /zurückziehen/i }));
    expect(onDeprecate).toHaveBeenCalledWith(baseEntry);
  });

  it("shows refine-chain depth when entry was refined", () => {
    render(
      <EntryItem
        entry={{ ...baseEntry, refines: "e_old" }}
        onRefine={() => {}}
        onDeprecate={() => {}}
      />,
    );
    expect(screen.getByText(/verfeinert von/i)).toBeInTheDocument();
  });
});
