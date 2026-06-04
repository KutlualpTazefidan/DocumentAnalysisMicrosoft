import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { useExtractStats, useSyntheseStats } from "../useStatistics";

const server = setupServer(
  http.get("*/api/admin/statistics/extract/:slug", () =>
    HttpResponse.json({
      slug: "doc-a",
      diagnostics: { split: 1, no_decomposition: 0, clean: 9, total: 10 },
      register_boxes: 2,
      total_boxes: 4,
      register_rate: 0.5,
    })
  ),
  http.get("*/api/admin/statistics/synthese/:slug", () =>
    HttpResponse.json({
      slug: "doc-a",
      questions_created: 5,
      questions_deprecated: 1,
      survival_rate: 0.8,
      vote_approved: 3,
      vote_rejected: 1,
      vote_approval_rate: 0.75,
      vote_distribution: [
        { entry_id: "q1", text_short: "Was ist…", approved: 2, rejected: 1 },
      ],
    })
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useStatistics hooks", () => {
  it("fetches extract stats", async () => {
    const { result } = renderHook(() => useExtractStats("doc-a", "tok"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.register_rate).toBe(0.5);
  });

  it("fetches synthese stats", async () => {
    const { result } = renderHook(() => useSyntheseStats("doc-a", "tok"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.vote_approval_rate).toBe(0.75);
  });
});
