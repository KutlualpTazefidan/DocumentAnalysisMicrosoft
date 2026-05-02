import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PropertiesSidebar } from "../../src/admin/components/PropertiesSidebar";
import type { SegmentBox } from "../../src/admin/types/domain";

describe("PropertiesSidebar page-button grid", () => {
  const defaultProps = {
    slug: "test-doc",
    selected: null,
    pageBoxCount: 0,
    currentPage: 1,
    totalPages: 5,
    segmentedPages: new Set<number>([1, 2]),
    approvedPages: new Set<number>([3]),
    onToggleApprove: vi.fn(),
    onResetPage: vi.fn(),
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
    perPageThreshold: 0.70,
    hasOverride: false,
    onPerPageChange: vi.fn(),
    onClearPerPage: vi.fn(),
  };

  it("renders a button for each page", () => {
    render(<PropertiesSidebar {...defaultProps} />);
    for (let p = 1; p <= 5; p++) {
      expect(screen.getByTestId(`seg-page-btn-${p}`)).toBeInTheDocument();
    }
  });

  it("active page button has ring class", () => {
    render(<PropertiesSidebar {...defaultProps} currentPage={2} />);
    expect(screen.getByTestId("seg-page-btn-2").className).toContain("ring-2");
    expect(screen.getByTestId("seg-page-btn-1").className).not.toContain("ring-2");
  });

  it("segmented page button is green", () => {
    render(<PropertiesSidebar {...defaultProps} />);
    // page 1 and 2 are segmented → green
    expect(screen.getByTestId("seg-page-btn-1").className).toContain("green");
    expect(screen.getByTestId("seg-page-btn-2").className).toContain("green");
  });

  it("unsegmented page button is red", () => {
    render(<PropertiesSidebar {...defaultProps} />);
    // page 4 and 5 are neither segmented nor approved → red
    expect(screen.getByTestId("seg-page-btn-4").className).toContain("red");
    expect(screen.getByTestId("seg-page-btn-5").className).toContain("red");
  });

  it("approved page button is blue", () => {
    render(<PropertiesSidebar {...defaultProps} />);
    // page 3 is approved → blue
    expect(screen.getByTestId("seg-page-btn-3").className).toContain("blue");
  });

  it("clicking a page button calls onPageChange", async () => {
    const onPageChange = vi.fn();
    render(<PropertiesSidebar {...defaultProps} onPageChange={onPageChange} />);
    await userEvent.click(screen.getByTestId("seg-page-btn-3"));
    expect(onPageChange).toHaveBeenCalledWith(3);
  });

  it("shows 'Diese Seite genehmigen' when page is not approved", () => {
    render(<PropertiesSidebar {...defaultProps} currentPage={1} approvedPages={new Set()} />);
    expect(screen.getByRole("button", { name: /diese seite genehmigen/i })).toBeInTheDocument();
  });

  it("shows 'Genehmigung aufheben' when page is approved", () => {
    render(<PropertiesSidebar {...defaultProps} currentPage={1} approvedPages={new Set([1])} />);
    expect(screen.getByRole("button", { name: /genehmigung aufheben/i })).toBeInTheDocument();
  });

  it("approve button calls onToggleApprove", async () => {
    const onToggleApprove = vi.fn();
    render(<PropertiesSidebar {...defaultProps} onToggleApprove={onToggleApprove} />);
    await userEvent.click(screen.getByRole("button", { name: /diese seite genehmigen/i }));
    expect(onToggleApprove).toHaveBeenCalled();
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
    slug: "test-doc",
    selected: selectedBox,
    pageBoxCount: 1,
    currentPage: 3,
    totalPages: 5,
    segmentedPages: new Set<number>([1, 2, 3]),
    approvedPages: new Set<number>(),
    onToggleApprove: vi.fn(),
    onResetPage: vi.fn(),
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
    perPageThreshold: 0.70,
    hasOverride: false,
    onPerPageChange: vi.fn(),
    onClearPerPage: vi.fn(),
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
    expect(screen.getByLabelText("Unmerge down")).toBeInTheDocument();
    expect(screen.queryByLabelText("Merge down")).not.toBeInTheDocument();
  });

  it("Both merge buttons enabled on a middle page with no links", () => {
    render(<PropertiesSidebar {...baseProps} />);
    expect(screen.getByLabelText("Merge up")).not.toBeDisabled();
    expect(screen.getByLabelText("Merge down")).not.toBeDisabled();
  });
});

describe("PropertiesSidebar per-page confidence slider", () => {
  const defaultProps = {
    slug: "test-doc",
    selected: null,
    pageBoxCount: 2,
    currentPage: 3,
    totalPages: 5,
    segmentedPages: new Set<number>([3]),
    approvedPages: new Set<number>(),
    onToggleApprove: vi.fn(),
    onResetPage: vi.fn(),
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
    perPageThreshold: 0.55,
    hasOverride: true,
    onPerPageChange: vi.fn(),
    onClearPerPage: vi.fn(),
  };

  it("slider renders with the current effective threshold value", () => {
    render(<PropertiesSidebar {...defaultProps} />);
    const slider = screen.getByTestId("per-page-conf-slider") as HTMLInputElement;
    expect(slider).toBeInTheDocument();
    expect(parseFloat(slider.value)).toBeCloseTo(0.55);
  });

  it("reset button is enabled when hasOverride is true", () => {
    render(<PropertiesSidebar {...defaultProps} hasOverride={true} />);
    expect(screen.getByTestId("per-page-conf-reset")).not.toBeDisabled();
  });

  it("reset button is disabled when hasOverride is false", () => {
    render(<PropertiesSidebar {...defaultProps} hasOverride={false} />);
    expect(screen.getByTestId("per-page-conf-reset")).toBeDisabled();
  });

  it("clicking reset button calls onClearPerPage", async () => {
    const onClearPerPage = vi.fn();
    render(<PropertiesSidebar {...defaultProps} hasOverride={true} onClearPerPage={onClearPerPage} />);
    await userEvent.click(screen.getByTestId("per-page-conf-reset"));
    expect(onClearPerPage).toHaveBeenCalled();
  });

  it("slider change calls onPerPageChange with the new numeric value", async () => {
    const onPerPageChange = vi.fn();
    render(<PropertiesSidebar {...defaultProps} onPerPageChange={onPerPageChange} />);
    const slider = screen.getByTestId("per-page-conf-slider");
    fireEvent.change(slider, { target: { value: "0.75" } });
    expect(onPerPageChange).toHaveBeenCalledWith(0.75);
  });
});
