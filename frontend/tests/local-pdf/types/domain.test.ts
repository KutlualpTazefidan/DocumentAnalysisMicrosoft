import { describe, expect, it } from "vitest";
import type {
  ModelLoadingEvent,
  ModelLoadedEvent,
  ModelUnloadingEvent,
  ModelUnloadedEvent,
  WorkCompleteEvent,
  WorkFailedEvent,
  WorkProgressEvent,
  WorkerEvent,
} from "../../../src/local-pdf/types/domain";

function narrow(ev: WorkerEvent): string {
  switch (ev.type) {
    case "model-loading":
      return `loading from ${ev.source} (~${ev.vram_estimate_mb}MB)`;
    case "model-loaded":
      return `loaded ${ev.vram_actual_mb}MB in ${ev.load_seconds}s`;
    case "work-progress":
      return `${ev.stage} ${ev.current}/${ev.total}`;
    case "model-unloading":
      return "unloading";
    case "model-unloaded":
      return `freed ${ev.vram_freed_mb}MB`;
    case "work-complete":
      return `done ${ev.items_processed} in ${ev.total_seconds}s`;
    case "work-failed":
      return `failed at ${ev.stage}: ${ev.reason}`;
  }
}

describe("WorkerEvent type narrowing", () => {
  it("narrows ModelLoadingEvent", () => {
    const ev: ModelLoadingEvent = {
      type: "model-loading",
      model: "DocLayout-YOLO",
      timestamp_ms: 1,
      source: "/weights",
      vram_estimate_mb: 700,
    };
    expect(narrow(ev)).toBe("loading from /weights (~700MB)");
  });

  it("narrows ModelLoadedEvent", () => {
    const ev: ModelLoadedEvent = {
      type: "model-loaded",
      model: "DocLayout-YOLO",
      timestamp_ms: 1,
      vram_actual_mb: 612,
      load_seconds: 12.3,
    };
    expect(narrow(ev)).toBe("loaded 612MB in 12.3s");
  });

  it("narrows WorkProgressEvent", () => {
    const ev: WorkProgressEvent = {
      type: "work-progress",
      model: "MinerU 3",
      timestamp_ms: 1,
      stage: "box",
      current: 7,
      total: 10,
      eta_seconds: 4.5,
      throughput_per_sec: 1.5,
      vram_current_mb: 1800,
    };
    expect(narrow(ev)).toBe("box 7/10");
  });

  it("narrows ModelUnloadingEvent", () => {
    const ev: ModelUnloadingEvent = {
      type: "model-unloading",
      model: "MinerU 3",
      timestamp_ms: 1,
    };
    expect(narrow(ev)).toBe("unloading");
  });

  it("narrows ModelUnloadedEvent", () => {
    const ev: ModelUnloadedEvent = {
      type: "model-unloaded",
      model: "MinerU 3",
      timestamp_ms: 1,
      vram_freed_mb: 1800,
    };
    expect(narrow(ev)).toBe("freed 1800MB");
  });

  it("narrows WorkCompleteEvent", () => {
    const ev: WorkCompleteEvent = {
      type: "work-complete",
      model: "DocLayout-YOLO",
      timestamp_ms: 1,
      total_seconds: 30.0,
      items_processed: 47,
      output_summary: { pages: 47 },
    };
    expect(narrow(ev)).toBe("done 47 in 30s");
  });

  it("narrows WorkFailedEvent", () => {
    const ev: WorkFailedEvent = {
      type: "work-failed",
      model: "MinerU 3",
      timestamp_ms: 1,
      stage: "run",
      reason: "OOM",
      recoverable: true,
      hint: "reduce batch size",
    };
    expect(narrow(ev)).toBe("failed at run: OOM");
  });
});
