import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PropertiesSidebar } from "../../src/admin/components/PropertiesSidebar";

describe("PropertiesSidebar arrow buttons", () => {
  const defaultProps = {
    selected: null,
    pageBoxCount: 0,
    currentPage: 5,
    totalPages: 10,
    confidenceThreshold: 0.7,
    showDeactivated: false,
    onConfidenceChange: vi.fn(),
    onShowDeactivatedChange: vi.fn(),
    onRunExtractThisPage: vi.fn(),
    onResetPage: vi.fn(),
    extractEnabled: true,
    running: false,
    onChangeKind: vi.fn(),
    onNewBox: vi.fn(),
    onDeactivate: vi.fn(),
    onActivate: vi.fn(),
    onResetBox: vi.fn(),
    onPageChange: vi.fn(),
  };

  it("should disable prev button at page 1", () => {
    render(<PropertiesSidebar {...defaultProps} currentPage={1} />);
    const sidebarButtons = screen.getAllByRole("button", { name: "Previous page" });
    // Get the button from the sidebar (not Pagination component)
    const prevButton = sidebarButtons.find((btn) => btn.className.includes("w-7"));
    expect(prevButton).toBeDisabled();
  });

  it("should disable next button at last page", () => {
    render(<PropertiesSidebar {...defaultProps} currentPage={10} totalPages={10} />);
    const sidebarButtons = screen.getAllByRole("button", { name: "Next page" });
    // Get the button from the sidebar (not Pagination component)
    const nextButton = sidebarButtons.find((btn) => btn.className.includes("w-7"));
    expect(nextButton).toBeDisabled();
  });

  it("should call onPageChange with currentPage - 1 when prev button clicked", async () => {
    const onPageChange = vi.fn();
    render(<PropertiesSidebar {...defaultProps} currentPage={5} onPageChange={onPageChange} />);

    const sidebarButtons = screen.getAllByRole("button", { name: "Previous page" });
    const prevButton = sidebarButtons.find((btn) => btn.className.includes("w-7"));
    await userEvent.click(prevButton!);

    expect(onPageChange).toHaveBeenCalledWith(4);
  });

  it("should call onPageChange with currentPage + 1 when next button clicked", async () => {
    const onPageChange = vi.fn();
    render(<PropertiesSidebar {...defaultProps} currentPage={5} onPageChange={onPageChange} />);

    const sidebarButtons = screen.getAllByRole("button", { name: "Next page" });
    const nextButton = sidebarButtons.find((btn) => btn.className.includes("w-7"));
    await userEvent.click(nextButton!);

    expect(onPageChange).toHaveBeenCalledWith(6);
  });
});
