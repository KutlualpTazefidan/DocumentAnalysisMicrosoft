import { describe, expect, it } from "vitest";
import { T } from "../../../src/admin/styles/typography";

describe("typography tokens", () => {
  it("all token strings are non-empty", () => {
    for (const [key, value] of Object.entries(T)) {
      expect(value, `T.${key} should be non-empty`).toBeTruthy();
      expect(value.trim(), `T.${key} should not be whitespace-only`).not.toBe("");
    }
  });

  it("body, tiny, and heading resolve to distinct pixel values", () => {
    // Each token string must contain a bracketed px value — extract and compare.
    const px = (token: string) => {
      const match = token.match(/text-\[(\d+)px\]/);
      expect(match, `expected bracketed px value in: "${token}"`).not.toBeNull();
      return parseInt(match![1], 10);
    };

    const bodyPx = px(T.body);
    const tinyPx = px(T.tiny);
    const headingPx = px(T.heading);

    expect(bodyPx).not.toBe(tinyPx);
    expect(bodyPx).not.toBe(headingPx);
    expect(tinyPx).not.toBe(headingPx);
  });
});
