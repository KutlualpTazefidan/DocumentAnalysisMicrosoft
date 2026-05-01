import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { useElement } from "../../../src/curator/hooks/useElement";
import { useElements } from "../../../src/curator/hooks/useElements";
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
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useElements", () => {
  it("returns ElementWithCounts array for a slug", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements", () =>
        HttpResponse.json([
          {
            element: {
              element_id: "p1-aaa",
              page_number: 1,
              element_type: "heading",
              content: "Title",
            },
            count_active_entries: 0,
          },
        ]),
      ),
    );
    const { result } = renderHook(() => useElements("foo"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });
});

describe("useElement", () => {
  it("returns element + entries for a slug + element_id", async () => {
    server.use(
      http.get("http://localhost/api/docs/foo/elements/p1-aaa", () =>
        HttpResponse.json({
          element: {
            element_id: "p1-aaa",
            page_number: 1,
            element_type: "heading",
            content: "Title",
          },
          entries: [],
        }),
      ),
    );
    const { result } = renderHook(() => useElement("foo", "p1-aaa"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.element.element_id).toBe("p1-aaa");
  });

  it("does not fetch when elementId is undefined", () => {
    const { result } = renderHook(() => useElement("foo", undefined), { wrapper: makeWrapper() });
    expect(result.current.isFetching).toBe(false);
  });
});
