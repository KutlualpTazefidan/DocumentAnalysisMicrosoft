import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { CuratorShell } from "../../src/shell/CuratorShell";

vi.mock("../../src/auth/useAuth", () => ({
  useAuth: () => ({ token: "X", role: "curator", name: "Dr X", logout: () => {} }),
}));

describe("CuratorShell", () => {
  it("renders CURATOR badge with name", () => {
    render(
      <MemoryRouter initialEntries={["/curate/"]}>
        <Routes>
          <Route path="/curate" element={<CuratorShell />}>
            <Route index element={<div>curator home</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByText("CURATOR")).toBeInTheDocument();
    expect(screen.getByText("Dr X")).toBeInTheDocument();
    expect(screen.getByText("curator home")).toBeInTheDocument();
  });
});
