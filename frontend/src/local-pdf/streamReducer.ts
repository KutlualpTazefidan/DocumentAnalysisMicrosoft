import type { WorkerEvent } from "./types/domain";

export type StreamStage =
  | "idle"
  | "loading"
  | "ready"
  | "running"
  | "completed"
  | "unloading"
  | "failed";

export interface StreamState {
  stage: StreamStage;
  model: string | null;
  vram_estimate_mb: number;
  vram_mb: number;
  load_seconds: number | null;
  progress: { current: number; total: number; stage: string } | null;
  eta_seconds: number | null;
  throughput_per_sec: number | null;
  items_processed: number;
  total_seconds: number | null;
  errors: WorkerEvent[];
  timeline: WorkerEvent[];
}

export function initialStreamState(): StreamState {
  return {
    stage: "idle",
    model: null,
    vram_estimate_mb: 0,
    vram_mb: 0,
    load_seconds: null,
    progress: null,
    eta_seconds: null,
    throughput_per_sec: null,
    items_processed: 0,
    total_seconds: null,
    errors: [],
    timeline: [],
  };
}

export function applyEvent(prev: StreamState, ev: WorkerEvent): StreamState {
  const timeline = [...prev.timeline, ev];
  switch (ev.type) {
    case "model-loading":
      return {
        ...prev,
        stage: "loading",
        model: ev.model,
        vram_estimate_mb: ev.vram_estimate_mb,
        timeline,
      };
    case "model-loaded":
      return {
        ...prev,
        stage: "ready",
        vram_mb: ev.vram_actual_mb,
        load_seconds: ev.load_seconds,
        timeline,
      };
    case "work-progress":
      return {
        ...prev,
        stage: "running",
        progress: { current: ev.current, total: ev.total, stage: ev.stage },
        eta_seconds: ev.eta_seconds,
        throughput_per_sec: ev.throughput_per_sec,
        vram_mb: ev.vram_current_mb,
        timeline,
      };
    case "work-complete":
      return {
        ...prev,
        stage: "completed",
        items_processed: ev.items_processed,
        total_seconds: ev.total_seconds,
        timeline,
      };
    case "model-unloading":
      return { ...prev, stage: "unloading", timeline };
    case "model-unloaded":
      return { ...prev, stage: "idle", vram_mb: 0, timeline };
    case "work-failed":
      return {
        ...prev,
        stage: "failed",
        errors: [...prev.errors, ev],
        timeline,
      };
  }
}
