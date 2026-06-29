// frontend/src/admin/components/__tests__/WorkspaceLayout.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { WorkspaceLayout } from "../WorkspaceLayout";

vi.mock("../../../auth/useAuth", () => ({ useAuth: () => ({ token: "tok" }) }));

const server = setupServer(
  http.get("*/api/admin/docs", () =>
    HttpResponse.json([
      { slug: "doc-a", filename: "A.pdf", pages: 1, status: "raw", last_touched_utc: "t", box_count: 0 },
      { slug: "doc-b", filename: "B.pdf", pages: 2, status: "done", last_touched_utc: "t", box_count: 3 },
    ])
  )
);
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<WorkspaceLayout />}>
            <Route path="admin/files" element={<div>FILES-OUTLET</div>} />
            <Route path="admin/statistics" element={<div>STATS-OUTLET</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WorkspaceLayout", () => {
  it("renders the tab bar, the file dropdown, and the outlet", async () => {
    renderAt("/admin/files?file=doc-a");
    expect(screen.getByText("Dateien")).toBeInTheDocument();
    expect(screen.getByText("Statistik")).toBeInTheDocument();
    expect(screen.getByText("FILES-OUTLET")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("option", { name: "A.pdf" })).toBeInTheDocument());
    // dropdown reflects the active file
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("doc-a");
  });

  it("tab links carry the active ?file=", () => {
    renderAt("/admin/files?file=doc-a");
    const statsLink = screen.getByText("Statistik").closest("a") as HTMLAnchorElement;
    expect(statsLink.getAttribute("href")).toContain("file=doc-a");
  });

  it("changing the dropdown updates ?file= (outlet still mounts)", async () => {
    renderAt("/admin/statistics?file=doc-a");
    await waitFor(() => expect(screen.getByRole("option", { name: "B.pdf" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByRole("combobox"), "doc-b");
    const statsLink = screen.getByText("Statistik").closest("a") as HTMLAnchorElement;
    expect(statsLink.getAttribute("href")).toContain("file=doc-b");
  });
});
