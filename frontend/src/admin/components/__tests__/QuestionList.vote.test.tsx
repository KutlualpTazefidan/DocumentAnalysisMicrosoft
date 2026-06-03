import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { QuestionList } from "../QuestionList";

const baseQ = {
  entry_id: "q1",
  text: "Was ist X?",
  box_id: "b1",
  answer: null,
} as const;

describe("QuestionList vote UI", () => {
  it("does not render counts before user votes", () => {
    render(
      <QuestionList
        questions={[
          {
            ...baseQ,
            vote_summary: {
              approved_count: 3,
              rejected_count: 1,
              my_vote: null,
            },
          },
        ]}
        onRefine={vi.fn()}
        onDeprecate={vi.fn()}
        onVote={vi.fn()}
      />,
    );
    expect(screen.queryByText(/3 ✓/)).toBeNull();
  });

  it("renders counts and stripe once user votes approved", () => {
    const { container } = render(
      <QuestionList
        questions={[
          {
            ...baseQ,
            vote_summary: {
              approved_count: 3,
              rejected_count: 1,
              my_vote: "approved",
            },
          },
        ]}
        onRefine={vi.fn()}
        onDeprecate={vi.fn()}
        onVote={vi.fn()}
      />,
    );
    expect(screen.getByText(/3 ✓ · 1 ✗/)).toBeInTheDocument();
    expect(container.querySelector(".border-l-emerald-500")).not.toBeNull();
  });

  it("clicking the active approve button toggles to revoked", () => {
    const onVote = vi.fn();
    render(
      <QuestionList
        questions={[
          {
            ...baseQ,
            vote_summary: {
              approved_count: 1,
              rejected_count: 0,
              my_vote: "approved",
            },
          },
        ]}
        onRefine={vi.fn()}
        onDeprecate={vi.fn()}
        onVote={onVote}
      />,
    );
    fireEvent.click(screen.getByLabelText("Einverstanden"));
    expect(onVote).toHaveBeenCalledWith("q1", "revoked");
  });

  it("clicking approve when no vote yet sends 'approved'", () => {
    const onVote = vi.fn();
    render(
      <QuestionList
        questions={[
          {
            ...baseQ,
            vote_summary: {
              approved_count: 0,
              rejected_count: 0,
              my_vote: null,
            },
          },
        ]}
        onRefine={vi.fn()}
        onDeprecate={vi.fn()}
        onVote={onVote}
      />,
    );
    fireEvent.click(screen.getByLabelText("Einverstanden"));
    expect(onVote).toHaveBeenCalledWith("q1", "approved");
  });
});
