import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EntryItem } from "../../../src/curator/components/EntryItem";
import type { CuratorQuestion } from "../../../src/curator/api/curatorClient";

const baseEntry: CuratorQuestion = {
  question_id: "q-001",
  element_id: "p1-aaa",
  curator_id: "c-alice",
  query: "Welche Norm gilt für M6?",
  refined_query: null,
  deprecated: false,
  deprecated_reason: null,
  created_at: "2026-04-30T07:00:00Z",
};

describe("EntryItem", () => {
  it("renders the query and the curator_id", () => {
    render(<EntryItem entry={baseEntry} onRefine={() => {}} onDeprecate={() => {}} />);
    expect(screen.getByText(/welche norm/i)).toBeInTheDocument();
    expect(screen.getByText(/c-alice/)).toBeInTheDocument();
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

  it("shows 'verfeinert' badge when refined_query is set", () => {
    render(
      <EntryItem
        entry={{ ...baseEntry, refined_query: "Verfeinerte Frage?" }}
        onRefine={() => {}}
        onDeprecate={() => {}}
      />,
    );
    expect(screen.getByText(/verfeinert/i)).toBeInTheDocument();
  });
});
