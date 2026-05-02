// frontend/tests/admin/lib/confThreshold.test.ts
import { beforeEach, describe, expect, it } from "vitest";
import {
  loadConf,
  saveConf,
  effectiveThreshold,
  setPageThreshold,
  setDefaultThreshold,
  clearPageOverride,
} from "../../../src/admin/lib/confThreshold";

beforeEach(() => {
  localStorage.clear();
});

describe("loadConf", () => {
  it("returns default state when nothing in localStorage", () => {
    const state = loadConf("test-slug");
    expect(state.default).toBe(0.70);
    expect(state.perPage).toEqual({});
  });

  it("returns parsed state from localStorage", () => {
    localStorage.setItem(
      "segment.confThreshold.test-slug",
      JSON.stringify({ default: 0.50, perPage: { 3: 0.30 } }),
    );
    const state = loadConf("test-slug");
    expect(state.default).toBe(0.50);
    expect(state.perPage[3]).toBe(0.30);
  });

  it("handles malformed JSON gracefully", () => {
    localStorage.setItem("segment.confThreshold.test-slug", "not-json{{{");
    const state = loadConf("test-slug");
    expect(state.default).toBe(0.70);
    expect(state.perPage).toEqual({});
  });
});

describe("saveConf / loadConf round-trip", () => {
  it("persists and retrieves state", () => {
    const toSave = { default: 0.65, perPage: { 2: 0.40, 7: 0.80 } };
    saveConf("my-doc", toSave);
    const loaded = loadConf("my-doc");
    expect(loaded.default).toBe(0.65);
    expect(loaded.perPage[2]).toBe(0.40);
    expect(loaded.perPage[7]).toBe(0.80);
  });
});

describe("effectiveThreshold", () => {
  it("returns default when no per-page override exists", () => {
    const state = { default: 0.70, perPage: {} };
    expect(effectiveThreshold(state, 5)).toBe(0.70);
  });

  it("returns per-page override when one exists", () => {
    const state = { default: 0.70, perPage: { 5: 0.45 } };
    expect(effectiveThreshold(state, 5)).toBe(0.45);
  });

  it("falls back to default for a page without an override", () => {
    const state = { default: 0.70, perPage: { 3: 0.45 } };
    expect(effectiveThreshold(state, 9)).toBe(0.70);
  });
});

describe("setPageThreshold", () => {
  it("creates a per-page override and persists it", () => {
    const next = setPageThreshold("doc1", 4, 0.55);
    expect(next.perPage[4]).toBe(0.55);
    // Verify persistence
    expect(loadConf("doc1").perPage[4]).toBe(0.55);
  });

  it("does not affect the default", () => {
    const next = setPageThreshold("doc1", 4, 0.55);
    expect(next.default).toBe(0.70);
  });
});

describe("setDefaultThreshold", () => {
  it("updates the default and persists it", () => {
    const next = setDefaultThreshold("doc2", 0.30);
    expect(next.default).toBe(0.30);
    expect(loadConf("doc2").default).toBe(0.30);
  });

  it("leaves per-page overrides unchanged", () => {
    localStorage.setItem(
      "segment.confThreshold.doc2",
      JSON.stringify({ default: 0.70, perPage: { 1: 0.50 } }),
    );
    const next = setDefaultThreshold("doc2", 0.30);
    expect(next.perPage[1]).toBe(0.50);
  });
});

describe("state independence", () => {
  it("setting default to 0.5 with perPage[8]=0.7 → effective for page 8 stays 0.7", () => {
    localStorage.setItem(
      "segment.confThreshold.ind-doc",
      JSON.stringify({ default: 0.70, perPage: { 8: 0.70 } }),
    );
    setPageThreshold("ind-doc", 8, 0.70);
    const next = setDefaultThreshold("ind-doc", 0.50);
    // The perPage override for page 8 is untouched
    expect(next.perPage[8]).toBe(0.70);
    // Effective threshold for page 8 uses the override, not the new default
    expect(effectiveThreshold(next, 8)).toBe(0.70);
  });

  it("setting perPage[8]=0.7 with default=0.5 → default stays 0.5", () => {
    localStorage.setItem(
      "segment.confThreshold.ind-doc2",
      JSON.stringify({ default: 0.50, perPage: {} }),
    );
    const next = setPageThreshold("ind-doc2", 8, 0.70);
    // Setting a page override must not modify the default
    expect(next.default).toBe(0.50);
    expect(loadConf("ind-doc2").default).toBe(0.50);
  });
});

describe("clearPageOverride", () => {
  it("removes the override for the specified page", () => {
    localStorage.setItem(
      "segment.confThreshold.doc3",
      JSON.stringify({ default: 0.70, perPage: { 2: 0.40, 5: 0.60 } }),
    );
    const next = clearPageOverride("doc3", 2);
    expect(next.perPage[2]).toBeUndefined();
    // Other page's override untouched
    expect(next.perPage[5]).toBe(0.60);
  });

  it("is a no-op when no override exists for that page", () => {
    const next = clearPageOverride("doc3", 9);
    expect(next.perPage[9]).toBeUndefined();
    expect(next.default).toBe(0.70);
  });

  it("persists the result after removal", () => {
    localStorage.setItem(
      "segment.confThreshold.doc3",
      JSON.stringify({ default: 0.70, perPage: { 2: 0.40 } }),
    );
    clearPageOverride("doc3", 2);
    expect(loadConf("doc3").perPage[2]).toBeUndefined();
  });
});
