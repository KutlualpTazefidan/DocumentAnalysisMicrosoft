// frontend/tests/admin/components/DocStepTabs.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { DocStepTabs } from "../../../src/admin/components/DocStepTabs";

function wrap(initialPath: string) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="*" element={<DocStepTabs slug="foo" />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("DocStepTabs", () => {
  it("renders all four tabs", () => {
    render(wrap("/admin/doc/foo/segment"));
    expect(screen.getByRole("tab", { name: /files/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /segment/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /extract/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /synthesise/i })).toBeInTheDocument();
  });

  it("marks Segment tab active on /admin/doc/foo/segment", () => {
    render(wrap("/admin/doc/foo/segment"));
    expect(screen.getByRole("tab", { name: /segment/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("tab", { name: /extract/i })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("tab", { name: /files/i })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("tab", { name: /synthesise/i })).not.toHaveAttribute("aria-current");
  });

  it("marks Extract tab active on /admin/doc/foo/extract", () => {
    render(wrap("/admin/doc/foo/extract"));
    expect(screen.getByRole("tab", { name: /extract/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("tab", { name: /segment/i })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("tab", { name: /synthesise/i })).not.toHaveAttribute("aria-current");
  });

  it("marks Synthesise tab active on /admin/doc/foo/synthesise", () => {
    render(wrap("/admin/doc/foo/synthesise"));
    expect(screen.getByRole("tab", { name: /synthesise/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("tab", { name: /extract/i })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("tab", { name: /segment/i })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("tab", { name: /files/i })).not.toHaveAttribute("aria-current");
  });

  it("Files tab links to /admin/inbox", () => {
    render(wrap("/admin/doc/foo/segment"));
    const filesTab = screen.getByRole("tab", { name: /files/i });
    expect(filesTab).toHaveAttribute("href", "/admin/inbox");
  });

  it("Segment tab links to /admin/doc/foo/segment given slug=foo", () => {
    render(wrap("/admin/doc/foo/segment"));
    const segmentTab = screen.getByRole("tab", { name: /segment/i });
    expect(segmentTab).toHaveAttribute("href", "/admin/doc/foo/segment");
  });

  it("Extract tab links to /admin/doc/foo/extract given slug=foo", () => {
    render(wrap("/admin/doc/foo/extract"));
    const extractTab = screen.getByRole("tab", { name: /extract/i });
    expect(extractTab).toHaveAttribute("href", "/admin/doc/foo/extract");
  });

  it("Synthesise tab links to /admin/doc/foo/synthesise given slug=foo", () => {
    render(wrap("/admin/doc/foo/synthesise"));
    const synthesiseTab = screen.getByRole("tab", { name: /synthesise/i });
    expect(synthesiseTab).toHaveAttribute("href", "/admin/doc/foo/synthesise");
  });

  it("no tab is marked active when on an unrelated path", () => {
    render(wrap("/admin/inbox"));
    const tabs = screen.getAllByRole("tab");
    tabs.forEach((tab) => expect(tab).not.toHaveAttribute("aria-current"));
  });
});
