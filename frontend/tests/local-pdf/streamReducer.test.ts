import { describe, expect, it } from "vitest";
import {
  applyEvent,
  initialStreamState,
  type StreamState,
} from "../../src/local-pdf/streamReducer";
import type {
  ModelLoadedEvent,
  ModelLoadingEvent,
  ModelUnloadedEvent,
  ModelUnloadingEvent,
  WorkCompleteEvent,
  WorkFailedEvent,
  WorkProgressEvent,
} from "../../src/local-pdf/types/domain";

describe("streamReducer", () => {
  it("starts in idle stage with no model", () => {
    const s = initialStreamState();
    expect(s.stage).toBe("idle");
    expect(s.model).toBeNull();
    expect(s.timeline).toEqual([]);
    expect(s.errors).toEqual([]);
  });

  it("ModelLoadingEvent transitions to loading and records source + estimate", () => {
    const ev: ModelLoadingEvent = {
      type: "model-loading",
      model: "DocLayout-YOLO",
      timestamp_ms: 100,
      source: "/w.pt",
      vram_estimate_mb: 700,
    };
    const s = applyEvent(initialStreamState(), ev);
    expect(s.stage).toBe("loading");
    expect(s.model).toBe("DocLayout-YOLO");
    expect(s.vram_estimate_mb).toBe(700);
    expect(s.timeline).toHaveLength(1);
    expect(s.timeline[0]).toEqual(ev);
  });

  it("ModelLoadedEvent transitions loading → ready (pre-run) and records vram_actual", () => {
    let s = initialStreamState();
    const loading: ModelLoadingEvent = {
      type: "model-loading",
      model: "DocLayout-YOLO",
      timestamp_ms: 100,
      source: "/w.pt",
      vram_estimate_mb: 700,
    };
    s = applyEvent(s, loading);
    const loaded: ModelLoadedEvent = {
      type: "model-loaded",
      model: "DocLayout-YOLO",
      timestamp_ms: 200,
      vram_actual_mb: 612,
      load_seconds: 12.3,
    };
    s = applyEvent(s, loaded);
    expect(s.stage).toBe("ready");
    expect(s.vram_mb).toBe(612);
    expect(s.load_seconds).toBe(12.3);
  });

  it("first WorkProgressEvent transitions ready → running", () => {
    let s: StreamState = {
      ...initialStreamState(),
      stage: "ready",
      model: "DocLayout-YOLO",
      vram_mb: 612,
    };
    const p1: WorkProgressEvent = {
      type: "work-progress",
      model: "DocLayout-YOLO",
      timestamp_ms: 300,
      stage: "page",
      current: 1,
      total: 10,
      eta_seconds: null,
      throughput_per_sec: null,
      vram_current_mb: 612,
    };
    s = applyEvent(s, p1);
    expect(s.stage).toBe("running");
    expect(s.progress).toEqual({ current: 1, total: 10, stage: "page" });
    expect(s.eta_seconds).toBeNull();
  });

  it("subsequent WorkProgressEvents update progress + eta + vram_mb", () => {
    let s: StreamState = {
      ...initialStreamState(),
      stage: "running",
      model: "DocLayout-YOLO",
      vram_mb: 612,
    };
    s = applyEvent(s, {
      type: "work-progress",
      model: "DocLayout-YOLO",
      timestamp_ms: 400,
      stage: "page",
      current: 4,
      total: 10,
      eta_seconds: 6.0,
      throughput_per_sec: 1.0,
      vram_current_mb: 720,
    } satisfies WorkProgressEvent);
    expect(s.progress).toEqual({ current: 4, total: 10, stage: "page" });
    expect(s.eta_seconds).toBe(6.0);
    expect(s.throughput_per_sec).toBe(1.0);
    expect(s.vram_mb).toBe(720);
  });

  it("WorkCompleteEvent transitions to completed", () => {
    let s: StreamState = {
      ...initialStreamState(),
      stage: "running",
      model: "DocLayout-YOLO",
    };
    const done: WorkCompleteEvent = {
      type: "work-complete",
      model: "DocLayout-YOLO",
      timestamp_ms: 999,
      total_seconds: 30.0,
      items_processed: 47,
      output_summary: { pages: 47 },
    };
    s = applyEvent(s, done);
    expect(s.stage).toBe("completed");
    expect(s.items_processed).toBe(47);
  });

  it("ModelUnloadingEvent → unloading; ModelUnloadedEvent → idle and clears VRAM", () => {
    let s: StreamState = {
      ...initialStreamState(),
      stage: "completed",
      model: "DocLayout-YOLO",
      vram_mb: 612,
    };
    s = applyEvent(s, {
      type: "model-unloading",
      model: "DocLayout-YOLO",
      timestamp_ms: 1000,
    } satisfies ModelUnloadingEvent);
    expect(s.stage).toBe("unloading");
    s = applyEvent(s, {
      type: "model-unloaded",
      model: "DocLayout-YOLO",
      timestamp_ms: 1100,
      vram_freed_mb: 612,
    } satisfies ModelUnloadedEvent);
    expect(s.stage).toBe("idle");
    expect(s.vram_mb).toBe(0);
  });

  it("WorkFailedEvent moves to failed and records error", () => {
    let s: StreamState = {
      ...initialStreamState(),
      stage: "running",
      model: "MinerU 3",
    };
    const fail: WorkFailedEvent = {
      type: "work-failed",
      model: "MinerU 3",
      timestamp_ms: 500,
      stage: "run",
      reason: "OOM",
      recoverable: true,
      hint: "free VRAM",
    };
    s = applyEvent(s, fail);
    expect(s.stage).toBe("failed");
    expect(s.errors).toHaveLength(1);
    expect(s.errors[0]).toEqual(fail);
  });

  it("appends every event to timeline in arrival order", () => {
    let s = initialStreamState();
    const events = [
      { type: "model-loading", model: "X", timestamp_ms: 1, source: "/w", vram_estimate_mb: 100 },
      { type: "model-loaded", model: "X", timestamp_ms: 2, vram_actual_mb: 120, load_seconds: 1.0 },
      {
        type: "work-progress", model: "X", timestamp_ms: 3, stage: "page",
        current: 1, total: 1, eta_seconds: null, throughput_per_sec: null, vram_current_mb: 120,
      },
      { type: "work-complete", model: "X", timestamp_ms: 4, total_seconds: 1.0, items_processed: 1, output_summary: {} },
    ] as const;
    for (const ev of events) {
      s = applyEvent(s, ev);
    }
    expect(s.timeline.map((e) => e.type)).toEqual([
      "model-loading",
      "model-loaded",
      "work-progress",
      "work-complete",
    ]);
  });
});
