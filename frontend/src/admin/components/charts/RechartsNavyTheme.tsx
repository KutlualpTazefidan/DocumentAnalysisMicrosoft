// frontend/src/admin/components/charts/RechartsNavyTheme.tsx
//
// Recharts is unstyled by default. This wrapper provides a Context
// with the navy palette so chart components stay declarative.
//
// Verified 2026-06-03 (recharts 3.8.x): Sunburst is NOT exported.
// CapabilityWishesSunburst falls back to <Treemap>; see Task 9.
import { createContext, useContext, type ReactNode } from "react";
import { ResponsiveContainer } from "recharts";

export interface NavyPalette {
  bg: string;
  text: string;
  accent: string;
  success: string;
  danger: string;
  warn: string;
  grid: string;
  gradientStops: { from: string; to: string };
}

export const DEFAULT_NAVY_PALETTE: NavyPalette = {
  bg: "#1e293b",        // navy-800
  text: "#cbd5e1",      // navy-200
  accent: "#3b82f6",    // brand-500
  success: "#10b981",   // emerald-500
  danger: "#ef4444",    // red-500
  warn: "#f59e0b",      // amber-500
  grid: "#475569",      // navy-600
  gradientStops: { from: "#3b82f6", to: "#1d4ed8" },
};

const PaletteCtx = createContext<NavyPalette>(DEFAULT_NAVY_PALETTE);

export function useChartPalette(): NavyPalette {
  return useContext(PaletteCtx);
}

interface Props {
  children: ReactNode;
  height?: number;
  palette?: NavyPalette;
}

/** Wraps a chart in a ResponsiveContainer + navy palette context. */
export function RechartsNavyTheme({ children, height = 240, palette = DEFAULT_NAVY_PALETTE }: Props): JSX.Element {
  return (
    <PaletteCtx.Provider value={palette}>
      <div className="rounded bg-navy-800 p-3">
        <ResponsiveContainer width="100%" height={height}>
          {children as any}
        </ResponsiveContainer>
      </div>
    </PaletteCtx.Provider>
  );
}
