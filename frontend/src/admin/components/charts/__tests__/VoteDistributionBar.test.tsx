import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VoteDistributionBar } from "../VoteDistributionBar";

describe("VoteDistributionBar", () => {
  it("shows empty-state when rows are empty", () => {
    render(<VoteDistributionBar rows={[]} />);
    expect(screen.getByText("Noch keine Reviewer-Stimmen vorhanden.")).toBeInTheDocument();
  });

  it("renders heading when rows are present", () => {
    render(
      <VoteDistributionBar
        rows={[{ entry_id: "q1", text_short: "Was ist X?", approved: 2, rejected: 1 }]}
      />
    );
    expect(screen.getByText(/Stimmen pro Frage/)).toBeInTheDocument();
  });
});
