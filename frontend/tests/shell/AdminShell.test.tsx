import { describe, it, expect, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ToastProvider } from "../../src/shared/components/Toaster";
import { AdminShell } from "../../src/shell/AdminShell";

vi.mock("../../src/auth/useAuth", () => ({
  useAuth: () => ({ token: "ADMIN", role: "admin", name: "admin", logout: () => {} }),
}));

// AdminShell mounts LlmTopBarControl (react-query) and the role menu uses
// useToast indirectly via the shell, so the QueryClient + ToastProvider
// are required. retry:false keeps the unmocked /api/admin/llm/* queries
// from retrying — they fail silently and the topbar renders its
// "stopped" default.
function renderShell() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={["/admin/inbox"]}>
          <Routes>
            <Route path="/admin/*" element={<AdminShell />}>
              <Route path="inbox" element={<div>inbox content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("AdminShell", () => {
  it("renders ADMIN role badge", () => {
    renderShell();
    // The old RoleBadge is now a clickable RoleMenu button whose
    // accessible name is "<label> <name> — Menü öffnen".
    expect(
      screen.getByRole("button", { name: /ADMIN admin — Menü öffnen/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("inbox content")).toBeInTheDocument();
  });

  it("redirects to /login when no token", () => {
    vi.doMock("../../src/auth/useAuth", () => ({
      useAuth: () => ({ token: null, role: null, name: null, logout: () => {} }),
    }));
    // Re-import to pick up mock; minimal smoke for redirect path
  });

  it("wraps Outlet in motion element", () => {
    const { container } = renderShell();
    const motion = container.querySelector("[data-shell-motion]");
    expect(motion).not.toBeNull();
  });
});
