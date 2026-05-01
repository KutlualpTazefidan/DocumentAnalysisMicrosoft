import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StageTimeline } from "../../../src/admin/components/StageTimeline";
import type { WorkerEvent } from "../../../src/admin/types/domain";

describe("StageTimeline", () => {
  it("renders one entry per event with type and model", () => {
    const events: WorkerEvent[] = [
      { type: "model-loading", model: "Y", timestamp_ms: 1000, source: "/w", vram_estimate_mb: 700 },
      { type: "model-loaded", model: "Y", timestamp_ms: 2000, vram_actual_mb: 612, load_seconds: 12.3 },
      {
        type: "work-progress", model: "Y", timestamp_ms: 3000, stage: "page",
        current: 14, total: 47, eta_seconds: 134, throughput_per_sec: 3.6, vram_current_mb: 612,
      },
    ];
    render(<StageTimeline events={events} />);
    const rows = screen.getAllByTestId(/timeline-entry-/);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent(/loaded|loading/i);
    expect(rows[1]).toHaveTextContent(/612.?MB/);
    expect(rows[2]).toHaveTextContent(/14 \/ 47/);
  });

  it("renders failed events with red marker", () => {
    const events: WorkerEvent[] = [
      {
        type: "work-failed",
        model: "Z",
        timestamp_ms: 5000,
        stage: "run",
        reason: "CUDA OOM",
        recoverable: true,
        hint: "free VRAM",
      },
    ];
    render(<StageTimeline events={events} />);
    expect(screen.getByText(/CUDA OOM/)).toBeInTheDocument();
    const marker = screen.getByTestId("timeline-entry-0").querySelector("[data-marker]");
    expect(marker?.getAttribute("data-marker")).toBe("error");
  });

  it("renders empty list with no rows", () => {
    render(<StageTimeline events={[]} />);
    expect(screen.queryAllByTestId(/timeline-entry-/)).toHaveLength(0);
  });
});
