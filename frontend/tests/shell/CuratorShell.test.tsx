import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ToastProvider } from "../../src/shared/components/Toaster";
import { CuratorShell } from "../../src/shell/CuratorShell";

vi.mock("../../src/auth/useAuth", () => ({
  useAuth: () => ({ token: "X", role: "curator", name: "Dr X", logout: () => {} }),
}));

describe("CuratorShell", () => {
  it("renders CURATOR badge with name", () => {
    // CuratorShell calls useToast directly, so ToastProvider is required.
    render(
      <ToastProvider>
        <MemoryRouter initialEntries={["/curate/"]}>
          <Routes>
            <Route path="/curate" element={<CuratorShell />}>
              <Route index element={<div>curator home</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ToastProvider>,
    );
    // RoleMenu button accessible name is "<label> <name> — Menü öffnen".
    expect(
      screen.getByRole("button", { name: /CURATOR Dr X — Menü öffnen/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("curator home")).toBeInTheDocument();
  });
});
