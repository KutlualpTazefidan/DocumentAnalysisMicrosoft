// frontend/src/admin/hooks/__tests__/useActiveFile.test.tsx
import { MemoryRouter, useLocation } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { useActiveFile } from "../useActiveFile";

function Probe() {
  const { file, setFile } = useActiveFile();
  const loc = useLocation();
  return (
    <div>
      <span data-testid="file">{file ?? "none"}</span>
      <span data-testid="search">{loc.search}</span>
      <button onClick={() => setFile("b")}>set-b</button>
      <button onClick={() => setFile(null)}>clear</button>
    </div>
  );
}

describe("useActiveFile", () => {
  it("reads, sets, and clears the ?file= param", async () => {
    render(
      <MemoryRouter initialEntries={["/admin/extract?file=a"]}>
        <Probe />
      </MemoryRouter>
    );
    expect(screen.getByTestId("file")).toHaveTextContent("a");

    await userEvent.click(screen.getByText("set-b"));
    expect(screen.getByTestId("file")).toHaveTextContent("b");
    expect(screen.getByTestId("search")).toHaveTextContent("file=b");

    await userEvent.click(screen.getByText("clear"));
    expect(screen.getByTestId("file")).toHaveTextContent("none");
    expect(screen.getByTestId("search")).not.toHaveTextContent("file=");
  });
});
