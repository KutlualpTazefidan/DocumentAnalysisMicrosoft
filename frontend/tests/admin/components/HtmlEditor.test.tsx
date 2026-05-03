import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HtmlEditor } from "../../../src/admin/components/HtmlEditor";

/**
 * HtmlEditor is the in-place editor: a single Shadow DOM mount of the
 * rendered html.html. Click a `[data-source-box]` to highlight; click a
 * second time within 800ms to enter contenteditable mode; blur saves via
 * onElementChange. Tests verify the props contract + the host element
 * attaches a Shadow root.
 */
describe("HtmlEditor", () => {
  it("renders the host element with a Shadow root containing the html", () => {
    render(
      <HtmlEditor
        html='<p data-source-box="p1-b0">hi</p>'
        onClickElement={vi.fn()}
        onElementChange={vi.fn()}
      />,
    );
    const host = screen.getByTestId("html-editor-host");
    expect(host).toBeInTheDocument();
    expect(host.shadowRoot).not.toBeNull();
    // Shadow content includes the box.
    expect(host.shadowRoot!.innerHTML).toContain('data-source-box="p1-b0"');
  });

  it("shows status text when provided", () => {
    render(
      <HtmlEditor
        html="<p>x</p>"
        onClickElement={vi.fn()}
        onElementChange={vi.fn()}
        status="Speichert…"
      />,
    );
    expect(screen.getByText("Speichert…")).toBeInTheDocument();
  });

  it("HTML editor title visible", () => {
    render(
      <HtmlEditor
        html="<p>x</p>"
        onClickElement={vi.fn()}
        onElementChange={vi.fn()}
      />,
    );
    expect(screen.getByText("HTML editor")).toBeInTheDocument();
  });

  it("first click on a [data-source-box] calls onClickElement (highlight)", () => {
    const onClickElement = vi.fn();
    render(
      <HtmlEditor
        html='<p data-source-box="p1-b0">hi</p>'
        onClickElement={onClickElement}
        onElementChange={vi.fn()}
      />,
    );
    const host = screen.getByTestId("html-editor-host");
    const box = host.shadowRoot!.querySelector(
      '[data-source-box="p1-b0"]',
    ) as HTMLElement;
    box.click();
    expect(onClickElement).toHaveBeenCalledWith("p1-b0");
  });

  it("second click on the same box within 800ms enters contenteditable mode", () => {
    const onClickElement = vi.fn();
    render(
      <HtmlEditor
        html='<p data-source-box="p1-b0">hi</p>'
        onClickElement={onClickElement}
        onElementChange={vi.fn()}
      />,
    );
    const host = screen.getByTestId("html-editor-host");
    const box = host.shadowRoot!.querySelector(
      '[data-source-box="p1-b0"]',
    ) as HTMLElement;
    box.click();
    box.click();
    // contenteditable was set; React doesn't track DOM-direct mutations,
    // so we read it off the element.
    expect(box.contentEditable).toBe("true");
  });
});
