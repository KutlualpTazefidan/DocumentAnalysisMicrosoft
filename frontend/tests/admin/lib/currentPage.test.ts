import { describe, it, expect, beforeEach } from "vitest";
import { loadCurrentPage, saveCurrentPage } from "../../../src/admin/lib/currentPage";

describe("currentPage helper", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns 1 when nothing stored", () => {
    expect(loadCurrentPage("foo")).toBe(1);
  });

  it("round-trips a page number", () => {
    saveCurrentPage("foo", 8);
    expect(loadCurrentPage("foo")).toBe(8);
  });

  it("isolates per-slug", () => {
    saveCurrentPage("foo", 8);
    saveCurrentPage("bar", 3);
    expect(loadCurrentPage("foo")).toBe(8);
    expect(loadCurrentPage("bar")).toBe(3);
  });

  it("returns 1 for empty slug", () => {
    expect(loadCurrentPage("")).toBe(1);
  });

  it("ignores invalid stored values", () => {
    localStorage.setItem("doc.currentPage.foo", "garbage");
    expect(loadCurrentPage("foo")).toBe(1);
  });

  it("ignores out-of-range pages on save", () => {
    saveCurrentPage("foo", 0);
    saveCurrentPage("foo", -5);
    expect(loadCurrentPage("foo")).toBe(1);
  });
});
