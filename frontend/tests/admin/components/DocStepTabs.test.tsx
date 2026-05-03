// frontend/tests/admin/components/DocStepTabs.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { DocStepTabs } from "../../../src/admin/components/DocStepTabs";

function wrap(initialPath: string, slug?: string) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="*" element={<DocStepTabs slug={slug ?? "foo"} />} />
      </Routes>
    </MemoryRouter>
  );
}

function wrapNoSlug(initialPath: string) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="*" element={<DocStepTabs />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("DocStepTabs", () => {
  it("renders three tabs", () => {
    render(wrap("/admin/doc/foo/extract"));
    expect(screen.getByRole("tab", { name: /files/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /extract/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /synthesise/i })).toBeInTheDocument();
  });

  it("marks Extract tab active on /admin/doc/foo/extract", () => {
    render(wrap("/admin/doc/foo/extract"));
    expect(screen.getByRole("tab", { name: /extract/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("tab", { name: /synthesise/i })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("tab", { name: /files/i })).not.toHaveAttribute("aria-current");
  });

  it("marks Synthesise tab active on /admin/doc/foo/synthesise", () => {
    render(wrap("/admin/doc/foo/synthesise"));
    expect(screen.getByRole("tab", { name: /synthesise/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("tab", { name: /extract/i })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("tab", { name: /files/i })).not.toHaveAttribute("aria-current");
  });

  it("Files tab links to /admin/inbox", () => {
    render(wrap("/admin/doc/foo/extract"));
    const filesTab = screen.getByRole("tab", { name: /files/i });
    expect(filesTab).toHaveAttribute("href", "/admin/inbox");
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

  it("marks Files tab active on /admin/inbox (with slug)", () => {
    render(wrap("/admin/inbox"));
    expect(screen.getByRole("tab", { name: /files/i })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("tab", { name: /extract/i })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("tab", { name: /synthesise/i })).not.toHaveAttribute("aria-current");
  });

  // ── No-slug (inbox) mode ────────────────────────────────────────────────────

  it("no-slug: Files tab is a link to /admin/inbox and is active", () => {
    render(wrapNoSlug("/admin/inbox"));
    const filesTab = screen.getByRole("tab", { name: /files/i });
    expect(filesTab.tagName).toBe("A");
    expect(filesTab).toHaveAttribute("href", "/admin/inbox");
    expect(filesTab).toHaveAttribute("aria-current", "page");
  });

  it("no-slug: Extract tab is rendered as an aria-disabled span", () => {
    render(wrapNoSlug("/admin/inbox"));
    const extractTab = screen.getByRole("tab", { name: /extract/i });
    expect(extractTab.tagName).toBe("SPAN");
    expect(extractTab).toHaveAttribute("aria-disabled", "true");
  });

  it("no-slug: Synthesise tab is rendered as an aria-disabled span", () => {
    render(wrapNoSlug("/admin/inbox"));
    const synthesiseTab = screen.getByRole("tab", { name: /synthesise/i });
    expect(synthesiseTab.tagName).toBe("SPAN");
    expect(synthesiseTab).toHaveAttribute("aria-disabled", "true");
  });

  it("no-slug: all three tabs are still rendered", () => {
    render(wrapNoSlug("/admin/inbox"));
    expect(screen.getByRole("tab", { name: /files/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /extract/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /synthesise/i })).toBeInTheDocument();
  });
});
