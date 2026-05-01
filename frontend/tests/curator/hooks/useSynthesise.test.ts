import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http } from "msw";
import { useSynthesise } from "../../../src/curator/hooks/useSynthesise";

const server = setupServer();
beforeEach(() => {
  server.listen();
  sessionStorage.setItem("goldens.api_token", "tok");
});
afterEach(() => {
  server.resetHandlers();
  server.close();
  sessionStorage.clear();
});

function ndjsonResponse(lines: object[]): Response {
  const body = lines.map((l) => JSON.stringify(l)).join("\n") + "\n";
  return new Response(body, {
    headers: { "Content-Type": "application/x-ndjson" },
  });
}

describe("useSynthesise", () => {
  it("transitions idle → submitting → streaming → complete on successful run", async () => {
    server.use(
      http.post("http://localhost/api/docs/foo/synthesise", () =>
        ndjsonResponse([
          { type: "start", total_elements: 2 },
          {
            type: "element",
            element_id: "p1-aaa",
            kept: 3,
            skipped_reason: null,
            tokens_estimated: 30,
          },
          { type: "complete", events_written: 3, prompt_tokens_estimated: 30 },
        ]),
      ),
    );

    const { result } = renderHook(() => useSynthesise());
    expect(result.current.status).toBe("idle");

    act(() => {
      result.current.start({
        slug: "foo",
        request: { llm_model: "gpt-4o-mini", dry_run: true },
      });
    });

    await waitFor(() => expect(result.current.status).toBe("complete"));
    expect(result.current.lines).toHaveLength(3);
    expect(result.current.totals.kept).toBe(3);
    expect(result.current.totals.eventsWritten).toBe(3);
  });

  it("counts errors in the totals when SynthErrorLine is present", async () => {
    server.use(
      http.post("http://localhost/api/docs/foo/synthesise", () =>
        ndjsonResponse([
          { type: "start", total_elements: 1 },
          { type: "error", element_id: "p1-aaa", reason: "rate limit" },
          { type: "complete", events_written: 0, prompt_tokens_estimated: 0 },
        ]),
      ),
    );
    const { result } = renderHook(() => useSynthesise());
    act(() => {
      result.current.start({
        slug: "foo",
        request: { llm_model: "gpt-4o-mini", dry_run: true },
      });
    });
    await waitFor(() => expect(result.current.status).toBe("complete"));
    expect(result.current.totals.errors).toBe(1);
  });
});
