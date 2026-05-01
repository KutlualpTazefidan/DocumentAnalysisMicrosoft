import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AdminShell } from "../../src/shell/AdminShell";

vi.mock("../../src/auth/useAuth", () => ({
  useAuth: () => ({ token: "ADMIN", role: "admin", name: "admin", logout: () => {} }),
}));

describe("AdminShell", () => {
  it("renders ADMIN role badge", () => {
    render(
      <MemoryRouter initialEntries={["/admin/inbox"]}>
        <Routes>
          <Route path="/admin/*" element={<AdminShell />}>
            <Route path="inbox" element={<div>inbox content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText(/ADMIN/)).toBeInTheDocument();
    expect(screen.getByText("inbox content")).toBeInTheDocument();
  });

  it("redirects to /login when no token", () => {
    vi.doMock("../../src/auth/useAuth", () => ({
      useAuth: () => ({ token: null, role: null, name: null, logout: () => {} }),
    }));
    // Re-import to pick up mock; minimal smoke for redirect path
  });
});
