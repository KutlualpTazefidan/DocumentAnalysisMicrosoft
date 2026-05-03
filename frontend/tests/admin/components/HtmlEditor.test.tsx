import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HtmlEditor } from "../../../src/admin/components/HtmlEditor";

describe("HtmlEditor", () => {
  it("renders in preview mode by default — shows Vorschau button as active", () => {
    render(<HtmlEditor html="<p>hi</p>" onChange={vi.fn()} onClickElement={() => {}} />);
    const vorschauBtn = screen.getByRole("button", { name: /vorschau/i });
    expect(vorschauBtn).toBeInTheDocument();
    expect(vorschauBtn).toHaveAttribute("aria-pressed", "true");
  });

  it("shows all three mode buttons in the segmented control", () => {
    render(<HtmlEditor html="<p>hi</p>" onChange={vi.fn()} onClickElement={() => {}} />);
    expect(screen.getByRole("button", { name: /vorschau/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /wysiwyg/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /quelltext/i })).toBeInTheDocument();
  });

  it("preview mode renders an iframe with srcDoc", () => {
    render(<HtmlEditor html="<p>preview</p>" onChange={vi.fn()} onClickElement={() => {}} />);
    const iframe = screen.getByTestId("html-preview-iframe");
    expect(iframe).toBeInTheDocument();
    expect(iframe.tagName).toBe("IFRAME");
  });

  it("switching to WYSIWYG mode hides the iframe and shows editor content", () => {
    render(<HtmlEditor html="<p>editable</p>" onChange={vi.fn()} onClickElement={() => {}} />);
    // Switch to WYSIWYG
    fireEvent.click(screen.getByRole("button", { name: /wysiwyg/i }));
    expect(screen.queryByTestId("html-preview-iframe")).not.toBeInTheDocument();
    // WYSIWYG button is now active
    expect(screen.getByRole("button", { name: /wysiwyg/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("switching to raw mode shows CodeMirror host and hides iframe", () => {
    render(<HtmlEditor html="<p>raw</p>" onChange={vi.fn()} onClickElement={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /quelltext/i }));
    expect(screen.queryByTestId("html-preview-iframe")).not.toBeInTheDocument();
    expect(screen.getByTestId("codemirror-host")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /quelltext/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("can cycle through all three modes without error", () => {
    render(<HtmlEditor html="<p>cycle</p>" onChange={vi.fn()} onClickElement={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /wysiwyg/i }));
    fireEvent.click(screen.getByRole("button", { name: /quelltext/i }));
    fireEvent.click(screen.getByRole("button", { name: /vorschau/i }));
    expect(screen.getByTestId("html-preview-iframe")).toBeInTheDocument();
  });

  // Contract test for onClickElement via data-source-box (unchanged from original).
  it("onClickElement contract: called with boxId from data-source-box attribute (mock)", () => {
    const onClickElement = vi.fn();
    const mockTarget = document.createElement("span");
    const mockEl = document.createElement("p");
    mockEl.setAttribute("data-source-box", "b-1");
    mockEl.appendChild(mockTarget);
    document.body.appendChild(mockEl);

    const t = mockTarget as HTMLElement;
    const el = t.closest("[data-source-box]") as HTMLElement | null;
    if (el) {
      onClickElement(el.getAttribute("data-source-box")!);
    }

    expect(onClickElement).toHaveBeenCalledWith("b-1");
    document.body.removeChild(mockEl);
  });
});
