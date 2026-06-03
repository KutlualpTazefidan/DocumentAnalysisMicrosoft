// frontend/src/admin/components/charts/__tests__/MetricCounter.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCounter } from "../MetricCounter";

describe("MetricCounter", () => {
  it("renders label and suffix", () => {
    render(<MetricCounter value={42} label="Boxen" suffix="px" />);
    expect(screen.getByText("Boxen")).toBeInTheDocument();
    expect(screen.getByText("px")).toBeInTheDocument();
  });
});
