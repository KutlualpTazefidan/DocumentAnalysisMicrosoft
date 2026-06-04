// frontend/src/admin/components/charts/__tests__/MetricGauge.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricGauge } from "../MetricGauge";

describe("MetricGauge", () => {
  it("shows percent label when value is non-null", () => {
    render(<MetricGauge value={0.42} label="Test" />);
    expect(screen.getByText("Test")).toBeInTheDocument();
    expect(screen.getByText("42 %")).toBeInTheDocument();
  });

  it("shows en-dash when value is null", () => {
    render(<MetricGauge value={null} label="Empty" />);
    expect(screen.getByText("Keine Daten")).toBeInTheDocument();
    expect(screen.getByText("–")).toBeInTheDocument();
  });
});
