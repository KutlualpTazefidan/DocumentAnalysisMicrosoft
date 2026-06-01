import { useEffect, useRef, useState } from "react";

import { applyEvent, initialStreamState, type StreamState } from "../streamReducer";
import type { WorkerEvent } from "../types/domain";
import { useLlmStatus, type LlmStatus } from "./useLlmServer";

/**
 * Adapter that maps the local vLLM lifecycle into the same `StreamState`
 * shape the Extract page uses, so the existing `<StageIndicator />`
 * pill (bottom-left) can render vLLM activity verbatim — same layout,
 * same behaviour, no second component to maintain.
 *
 * Mapping:
 *   stopped         → no events (StageIndicator hides itself)
 *   stopped → starting → emits a synthetic model-loading event
 *   starting → running → emits a synthetic model-loaded event
 *   running → stopped → emits unloading + unloaded events
 *   * → error          → emits a work-failed event
 *
 * The vllm log_tail is already polled by useLlmStatus; we don't try
 * to fold every line into the timeline (that would spam) — the
 * StageTimeline shows only the lifecycle markers, while the
 * LlmServerPanel keeps the full log_tail in its <details>.
 */
export function useLlmStream(token: string): StreamState {
  const status = useLlmStatus(token);
  const data: LlmStatus | undefined = status.data;
  const lastStateRef = useRef<string | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const [state, setState] = useState<StreamState>(initialStreamState());

  useEffect(() => {
    if (!data) return;
    const prev = lastStateRef.current;
    const curr = data.state;
    if (prev === curr) return;

    const model = data.model ?? "vLLM";
    const ts = Date.now();

    const events: WorkerEvent[] = [];

    if (curr === "starting" && prev !== "starting") {
      startTimeRef.current = ts;
      events.push({
        type: "model-loading",
        model,
        timestamp_ms: ts,
        source: "vllm-server",
        vram_estimate_mb: 0,
      });
    } else if (curr === "running" && prev !== "running") {
      const loadSeconds = startTimeRef.current ? (ts - startTimeRef.current) / 1000 : 0;
      events.push({
        type: "model-loaded",
        model,
        timestamp_ms: ts,
        vram_actual_mb: 0,
        load_seconds: loadSeconds,
      });
    } else if (curr === "stopped" && (prev === "running" || prev === "starting")) {
      events.push(
        { type: "model-unloading", model, timestamp_ms: ts },
        { type: "model-unloaded", model, timestamp_ms: ts, vram_freed_mb: 0 },
      );
    } else if (curr === "error") {
      events.push({
        type: "work-failed",
        model,
        timestamp_ms: ts,
        stage: prev === "starting" ? "load" : "run",
        reason: data.error ?? "vLLM-Fehler",
        recoverable: true,
        hint: null,
      });
    }

    if (events.length > 0) {
      setState((s) => events.reduce(applyEvent, s));
    }
    lastStateRef.current = curr;
  }, [data]);

  return state;
}
