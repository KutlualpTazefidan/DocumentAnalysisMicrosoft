import { useCallback, useReducer, useRef } from "react";
import { streamSynthesise, ApiError } from "../api/curatorClient";
import type { SynthLine, SynthesiseRequest } from "../../shared/types/domain";

export type SynthStatus = "idle" | "submitting" | "streaming" | "complete" | "error" | "cancelled";

interface State {
  status: SynthStatus;
  lines: SynthLine[];
  totals: {
    totalElements: number;
    kept: number;
    skipped: number;
    errors: number;
    tokensEstimated: number;
    eventsWritten: number;
  };
  fatalError: string | null;
}

const initial: State = {
  status: "idle",
  lines: [],
  totals: {
    totalElements: 0,
    kept: 0,
    skipped: 0,
    errors: 0,
    tokensEstimated: 0,
    eventsWritten: 0,
  },
  fatalError: null,
};

type Action =
  | { type: "start" }
  | { type: "stream-begun" }
  | { type: "line"; line: SynthLine }
  | { type: "complete" }
  | { type: "fatal"; reason: string }
  | { type: "cancelled" }
  | { type: "reset" };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "start":
      return { ...initial, status: "submitting" };
    case "stream-begun":
      return { ...state, status: "streaming" };
    case "line": {
      const line = action.line;
      const lines = [...state.lines, line];
      const t = { ...state.totals };
      if (line.type === "start") t.totalElements = line.total_elements;
      else if (line.type === "element") {
        t.kept += line.kept;
        if (line.skipped_reason) t.skipped += 1;
        t.tokensEstimated += line.tokens_estimated;
      } else if (line.type === "error") t.errors += 1;
      else if (line.type === "complete") {
        t.eventsWritten = line.events_written;
        t.tokensEstimated = line.prompt_tokens_estimated;
      }
      return { ...state, lines, totals: t };
    }
    case "complete":
      return { ...state, status: "complete" };
    case "fatal":
      return { ...state, status: "error", fatalError: action.reason };
    case "cancelled":
      return { ...state, status: "cancelled" };
    case "reset":
      return initial;
  }
}

interface StartArgs {
  slug: string;
  request: SynthesiseRequest;
}

export function useSynthesise() {
  const [state, dispatch] = useReducer(reducer, initial);
  const abortRef = useRef<AbortController | null>(null);

  const start = useCallback(async ({ slug, request }: StartArgs) => {
    dispatch({ type: "start" });
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const stream = await streamSynthesise(slug, request, ctrl.signal);
      dispatch({ type: "stream-begun" });
      for await (const line of stream) {
        dispatch({ type: "line", line });
      }
      dispatch({ type: "complete" });
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        dispatch({ type: "cancelled" });
        return;
      }
      const reason =
        err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : (err as Error).message ?? "Unbekannter Fehler";
      dispatch({ type: "fatal", reason });
    }
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    dispatch({ type: "reset" });
  }, []);

  return { ...state, start, cancel, reset };
}
