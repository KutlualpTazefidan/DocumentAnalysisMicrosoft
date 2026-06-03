import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BarChart, Bar } from "recharts";
import { RechartsNavyTheme, useChartPalette, DEFAULT_NAVY_PALETTE } from "../RechartsNavyTheme";

describe("RechartsNavyTheme", () => {
  it("renders children inside a ResponsiveContainer", () => {
    const { container } = render(
      <RechartsNavyTheme height={200}>
        <BarChart data={[{ x: 1, y: 2 }]}>
          <Bar dataKey="y" />
        </BarChart>
      </RechartsNavyTheme>
    );
    expect(container.querySelector(".recharts-responsive-container")).not.toBeNull();
  });

  it("exposes the palette via useChartPalette", () => {
    function Probe(): JSX.Element {
      const p = useChartPalette();
      return <span data-testid="bg">{p.bg}</span>;
    }
    const { getByTestId } = render(
      <RechartsNavyTheme>
        <Probe />
      </RechartsNavyTheme>
    );
    expect(getByTestId("bg").textContent).toBe(DEFAULT_NAVY_PALETTE.bg);
  });
});
