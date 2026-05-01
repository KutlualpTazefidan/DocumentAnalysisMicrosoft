import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PropertiesSidebar } from "../../src/admin/components/PropertiesSidebar";
import type { SegmentBox } from "../../src/admin/types/domain";

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
    onMergeUp: vi.fn(),
    onMergeDown: vi.fn(),
    onUnmergeUp: vi.fn(),
    onUnmergeDown: vi.fn(),
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

describe("PropertiesSidebar merge buttons", () => {
  const selectedBox: SegmentBox = {
    box_id: "p3-x",
    page: 3,
    bbox: [0, 0, 100, 50],
    kind: "paragraph",
    confidence: 0.9,
    reading_order: 0,
    manually_activated: false,
    continues_from: null,
    continues_to: null,
  };

  const baseProps = {
    selected: selectedBox,
    pageBoxCount: 1,
    currentPage: 3,
    totalPages: 5,
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
    onMergeUp: vi.fn(),
    onMergeDown: vi.fn(),
    onUnmergeUp: vi.fn(),
    onUnmergeDown: vi.fn(),
    onPageChange: vi.fn(),
  };

  it("Merge up disabled when on page 1", () => {
    render(
      <PropertiesSidebar
        {...baseProps}
        selected={{ ...selectedBox, page: 1 }}
        currentPage={1}
      />,
    );
    expect(screen.getByLabelText("Merge up")).toBeDisabled();
  });

  it("Merge down disabled when on last page", () => {
    render(
      <PropertiesSidebar
        {...baseProps}
        selected={{ ...selectedBox, page: 5 }}
        currentPage={5}
        totalPages={5}
      />,
    );
    expect(screen.getByLabelText("Merge down")).toBeDisabled();
  });

  it("Unmerge up button shown when continues_from already set", () => {
    render(
      <PropertiesSidebar
        {...baseProps}
        selected={{ ...selectedBox, continues_from: "p2-abc" }}
      />,
    );
    // continues_from set → shows "Unmerge ↑" instead of "Merge up"
    expect(screen.getByLabelText("Unmerge up")).toBeInTheDocument();
    expect(screen.queryByLabelText("Merge up")).not.toBeInTheDocument();
  });

  it("Unmerge down button shown when continues_to already set", () => {
    render(
      <PropertiesSidebar
        {...baseProps}
        selected={{ ...selectedBox, continues_to: "p4-abc" }}
      />,
    );
    // continues_to set → shows "Unmerge ↓" instead of "Merge down"
    expect(screen.getByLabelText("Unmerge down")).toBeInTheDocument();
    expect(screen.queryByLabelText("Merge down")).not.toBeInTheDocument();
  });

  it("Both merge buttons enabled on a middle page with no links", () => {
    render(<PropertiesSidebar {...baseProps} />);
    expect(screen.getByLabelText("Merge up")).not.toBeDisabled();
    expect(screen.getByLabelText("Merge down")).not.toBeDisabled();
  });
});
