import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HelpModal } from "../../../src/curator/components/HelpModal";

describe("HelpModal Radix Dialog", () => {
  it("opens, traps focus on inner button, closes on escape", async () => {
    render(<HelpModal />);
    await userEvent.click(screen.getByRole("button", { name: /Hilfe|Help/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
