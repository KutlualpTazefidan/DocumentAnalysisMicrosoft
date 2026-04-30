import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SynthProgress } from "../../src/components/SynthProgress";
import type { SynthLine } from "../../src/types/domain";

const lines: SynthLine[] = [
  { type: "start", total_elements: 2 },
  {
    type: "element",
    element_id: "p1-aaa",
    kept: 3,
    skipped_reason: null,
    tokens_estimated: 42,
  },
  { type: "error", element_id: "p1-bbb", reason: "rate limit" },
  { type: "complete", events_written: 3, prompt_tokens_estimated: 42 },
];

describe("SynthProgress", () => {
  it("renders one row per line and styles error rows differently", () => {
    render(
      <SynthProgress
        lines={lines}
        totals={{
          totalElements: 2,
          kept: 3,
          skipped: 0,
          errors: 1,
          tokensEstimated: 42,
          eventsWritten: 3,
        }}
      />,
    );
    expect(screen.getByText(/p1-aaa/)).toBeInTheDocument();
    expect(screen.getByText(/p1-bbb/)).toBeInTheDocument();
    expect(screen.getByText(/rate limit/)).toBeInTheDocument();
    // "2 elements" / "3 kept" / "1 error" appear in both header summary and line list
    expect(screen.getAllByText(/2 elements/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/3 kept/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/1 error/).length).toBeGreaterThanOrEqual(1);
  });
});
