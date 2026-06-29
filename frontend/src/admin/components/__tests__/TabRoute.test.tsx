// frontend/src/admin/components/__tests__/TabRoute.test.tsx
import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Folder } from "lucide-react";
import { TabRoute } from "../TabRoute";
import type { TabDescriptor } from "../../features/types";

function makeDesc(requiresFile: boolean): TabDescriptor {
  return {
    key: "demo", label: "Demo", icon: Folder, order: 1, requiresFile,
    Component: () => <div>TAB-BODY</div>,
  };
}

describe("TabRoute", () => {
  it("shows the empty state when a file is required but none is selected", () => {
    render(
      <MemoryRouter initialEntries={["/admin/demo"]}>
        <TabRoute descriptor={makeDesc(true)} />
      </MemoryRouter>
    );
    expect(screen.queryByText("TAB-BODY")).not.toBeInTheDocument();
    expect(screen.getByText(/Bitte wählen Sie oben rechts eine Datei/)).toBeInTheDocument();
  });

  it("renders the tab when a file is selected", () => {
    render(
      <MemoryRouter initialEntries={["/admin/demo?file=a"]}>
        <TabRoute descriptor={makeDesc(true)} />
      </MemoryRouter>
    );
    expect(screen.getByText("TAB-BODY")).toBeInTheDocument();
  });

  it("renders a file-agnostic tab regardless of file", () => {
    render(
      <MemoryRouter initialEntries={["/admin/demo"]}>
        <TabRoute descriptor={makeDesc(false)} />
      </MemoryRouter>
    );
    expect(screen.getByText("TAB-BODY")).toBeInTheDocument();
  });
});
