import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StageIndicator } from "../../../src/admin/components/StageIndicator";
import { initialStreamState } from "../../../src/admin/streamReducer";

describe("StageIndicator", () => {
  it("renders nothing when stage is idle and timeline is empty", () => {
    const { container } = render(<StageIndicator state={initialStreamState()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders model name + page progress while running", () => {
    render(
      <StageIndicator
        state={{
          ...initialStreamState(),
          stage: "running",
          model: "DocLayout-YOLO",
          progress: { current: 14, total: 47, stage: "page" },
          eta_seconds: 134,
          throughput_per_sec: 3.6,
          vram_mb: 612,
        }}
      />,
    );
    expect(screen.getByText(/DocLayout-YOLO/)).toBeInTheDocument();
    expect(screen.getByText(/14 \/ 47/)).toBeInTheDocument();
    expect(screen.getByText(/612.?MB/)).toBeInTheDocument();
  });

  it("uses yellow status dot while loading", () => {
    render(
      <StageIndicator
        state={{ ...initialStreamState(), stage: "loading", model: "X" }}
      />,
    );
    const dot = screen.getByTestId("stage-dot");
    expect(dot.className).toMatch(/yellow/);
  });

  it("uses green status dot while running", () => {
    render(
      <StageIndicator
        state={{ ...initialStreamState(), stage: "running", model: "X", progress: { current: 1, total: 2, stage: "page" } }}
      />,
    );
    const dot = screen.getByTestId("stage-dot");
    expect(dot.className).toMatch(/green/);
  });

  it("uses red status dot on failed", () => {
    render(
      <StageIndicator
        state={{
          ...initialStreamState(),
          stage: "failed",
          model: "X",
          errors: [
            {
              type: "work-failed",
              model: "X",
              timestamp_ms: 1,
              stage: "run",
              reason: "OOM",
              recoverable: false,
              hint: null,
            },
          ],
        }}
      />,
    );
    const dot = screen.getByTestId("stage-dot");
    expect(dot.className).toMatch(/red/);
  });

  it("expands timeline drawer on click", () => {
    render(
      <StageIndicator
        state={{
          ...initialStreamState(),
          stage: "running",
          model: "X",
          progress: { current: 2, total: 5, stage: "page" },
          timeline: [
            { type: "model-loading", model: "X", timestamp_ms: 1, source: "/w", vram_estimate_mb: 100 },
            { type: "model-loaded", model: "X", timestamp_ms: 2, vram_actual_mb: 120, load_seconds: 1 },
            {
              type: "work-progress", model: "X", timestamp_ms: 3, stage: "page",
              current: 2, total: 5, eta_seconds: null, throughput_per_sec: null, vram_current_mb: 120,
            },
          ],
        }}
      />,
    );
    expect(screen.queryByTestId("stage-timeline")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("stage-toggle"));
    expect(screen.getByTestId("stage-timeline")).toBeInTheDocument();
    // Timeline shows three entries
    expect(screen.getAllByTestId(/timeline-entry-/)).toHaveLength(3);
  });

  it("formats ETA as m:ss", () => {
    render(
      <StageIndicator
        state={{
          ...initialStreamState(),
          stage: "running",
          model: "X",
          progress: { current: 5, total: 50, stage: "page" },
          eta_seconds: 134,
        }}
      />,
    );
    expect(screen.getByText(/2:14/)).toBeInTheDocument();
  });
});
