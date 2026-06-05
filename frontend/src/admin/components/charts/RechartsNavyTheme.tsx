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

// BAM light palette — charts now sit on white cards (was the dark navy
// theme). Values sampled from the reference dashboard.
export const DEFAULT_NAVY_PALETTE: NavyPalette = {
  bg: "#ffffff",        // white card
  text: "#333333",      // ink
  accent: "#00aff0",    // BAM cyan
  success: "#006d00",   // BAM dashboard green
  danger: "#d2001f",    // BAM red
  warn: "#ffcb46",      // BAM amber
  grid: "#dbdbdb",      // line — subtle grid on white
  gradientStops: { from: "#00aff0", to: "#0082b8" },  // cyan → cyan-700
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
      <div className="card p-3">
        <ResponsiveContainer width="100%" height={height}>
          {children}
        </ResponsiveContainer>
      </div>
    </PaletteCtx.Provider>
  );
}
