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
  bg: "#031E31",        // navy-800 (ADMIN_THEME.chrome)
  text: "#cfe6f5",      // navy-200
  accent: "#1E7EB2",    // brand-500 (= navy-600)
  success: "#10b981",   // emerald-500 (Tailwind default; project doesn't customize)
  danger: "#AE1B25",    // danger-500 (project custom red, not stock Tailwind red)
  warn: "#f59e0b",      // amber-500 (Tailwind default; project doesn't customize)
  grid: "#0a2e47",      // navy-700 — subtle grid lines against navy-800 bg
  gradientStops: { from: "#1E7EB2", to: "#154f72" },  // brand-500 → brand-700
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
export function RechartsNavyTheme({
  children,
  height = 240,  // matches the chart-card row baseline used across Statistik sections
  palette = DEFAULT_NAVY_PALETTE,
}: Props): JSX.Element {
  return (
    <PaletteCtx.Provider value={palette}>
      <div className="rounded bg-navy-800 p-3">
        <ResponsiveContainer width="100%" height={height}>
          {children}
        </ResponsiveContainer>
      </div>
    </PaletteCtx.Provider>
  );
}
