import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { useRefineEntry } from "../../../src/curator/hooks/useRefineEntry";
import { useDeprecateEntry } from "../../../src/curator/hooks/useDeprecateEntry";
import type { ReactNode } from "react";

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

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const refinedQuestion = {
  question_id: "q-001",
  element_id: "p1-aaa",
  curator_id: "c-alice",
  query: "Original",
  refined_query: "Verfeinert",
  deprecated: false,
  deprecated_reason: null,
  created_at: "2026-04-30T07:00:00Z",
};

const deprecatedQuestion = {
  question_id: "q-001",
  element_id: "p1-aaa",
  curator_id: "c-alice",
  query: "Original",
  refined_query: null,
  deprecated: true,
  deprecated_reason: "Duplikat",
  created_at: "2026-04-30T07:00:00Z",
};

describe("useRefineEntry", () => {
  it("mutates and returns the refined question", async () => {
    server.use(
      http.post("http://localhost/api/curate/docs/doc-a/questions/q-001/refine", () =>
        HttpResponse.json(refinedQuestion),
      ),
    );
    const { result } = renderHook(() => useRefineEntry(), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate({
        slug: "doc-a",
        questionId: "q-001",
        elementId: "p1-aaa",
        body: { query: "Verfeinert" },
      });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.refined_query).toBe("Verfeinert");
  });

  it("surfaces error on 404", async () => {
    server.use(
      http.post("http://localhost/api/curate/docs/doc-a/questions/q-999/refine", () =>
        HttpResponse.json({ detail: "question not found: q-999" }, { status: 404 }),
      ),
    );
    const { result } = renderHook(() => useRefineEntry(), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate({
        slug: "doc-a",
        questionId: "q-999",
        elementId: "p1-aaa",
        body: { query: "whatever" },
      });
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useDeprecateEntry", () => {
  it("mutates and returns the deprecated question", async () => {
    server.use(
      http.post("http://localhost/api/curate/docs/doc-a/questions/q-001/deprecate", () =>
        HttpResponse.json(deprecatedQuestion),
      ),
    );
    const { result } = renderHook(() => useDeprecateEntry(), { wrapper: makeWrapper() });
    act(() => {
      result.current.mutate({
        slug: "doc-a",
        questionId: "q-001",
        elementId: "p1-aaa",
        body: { reason: "Duplikat" },
      });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.deprecated).toBe(true);
    expect(result.current.data?.deprecated_reason).toBe("Duplikat");
  });
});
