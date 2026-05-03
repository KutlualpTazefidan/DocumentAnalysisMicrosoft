import { beforeEach, describe, expect, it } from "vitest";
import { clearLocalStorageForSlug } from "../../../src/admin/lib/docLocalState";

describe("clearLocalStorageForSlug", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("removes all per-doc keys for the given slug", () => {
    localStorage.setItem("segment.approved.foo", "[1,2]");
    localStorage.setItem("extract.approved.foo", "[3]");
    localStorage.setItem("segment.confThreshold.foo", '{"default":0.7,"perPage":{}}');
    localStorage.setItem("doc.currentPage.foo", "8");

    clearLocalStorageForSlug("foo");

    expect(localStorage.getItem("segment.approved.foo")).toBeNull();
    expect(localStorage.getItem("extract.approved.foo")).toBeNull();
    expect(localStorage.getItem("segment.confThreshold.foo")).toBeNull();
    expect(localStorage.getItem("doc.currentPage.foo")).toBeNull();
  });

  it("preserves entries for other slugs", () => {
    localStorage.setItem("segment.approved.foo", "[1]");
    localStorage.setItem("segment.approved.bar", "[2]");

    clearLocalStorageForSlug("foo");

    expect(localStorage.getItem("segment.approved.foo")).toBeNull();
    expect(localStorage.getItem("segment.approved.bar")).toBe("[2]");
  });

  it("preserves global (non-slug-keyed) entries", () => {
    localStorage.setItem("admin.segment.scale", "1.5");
    localStorage.setItem("admin.extract.scale", "1.2");
    localStorage.setItem("segment.approved.foo", "[1]");

    clearLocalStorageForSlug("foo");

    expect(localStorage.getItem("admin.segment.scale")).toBe("1.5");
    expect(localStorage.getItem("admin.extract.scale")).toBe("1.2");
    expect(localStorage.getItem("segment.approved.foo")).toBeNull();
  });

  it("is a no-op for empty slug", () => {
    localStorage.setItem("segment.approved.foo", "[1]");
    clearLocalStorageForSlug("");
    expect(localStorage.getItem("segment.approved.foo")).toBe("[1]");
  });
});
