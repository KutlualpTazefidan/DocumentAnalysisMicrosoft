// frontend/src/admin/components/charts/MetricGauge.tsx
import { RadialBar, RadialBarChart, PolarAngleAxis } from "recharts";
import { motion } from "framer-motion";

import { RechartsNavyTheme, useChartPalette } from "./RechartsNavyTheme";
import { T } from "../../styles/typography";

interface Props {
  value: number | null;
  label: string;
  subtitle?: string;
}

function Inner({ value }: { value: number }): JSX.Element {
  const palette = useChartPalette();
  const pct = Math.round(value * 100);
  const fill = value >= 0.7 ? palette.success : value >= 0.4 ? palette.accent : palette.danger;
  return (
    <RadialBarChart
      innerRadius="70%"
      outerRadius="100%"
      data={[{ name: "v", value: pct, fill }]}
      startAngle={90}
      endAngle={-270}
    >
      <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
      <RadialBar background dataKey="value" cornerRadius={6} />
    </RadialBarChart>
  );
}

export function MetricGauge({ value, label, subtitle }: Props): JSX.Element {
  return (
    <motion.div
      className="flex flex-col items-center"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className={`${T.heading} text-bam-navy mb-1`}>{label}</div>
      {/* Explicit width: the parent is `items-center`, which would otherwise
          shrink the chart wrapper to ~0 and collapse the ResponsiveContainer. */}
      <div className="w-full max-w-[200px]">
        <RechartsNavyTheme height={160}>
          {value === null ? (
            <div className="flex items-center justify-center h-full text-ink-muted text-2xl">–</div>
          ) : (
            <Inner value={value} />
          )}
        </RechartsNavyTheme>
      </div>
      <div className={`${T.body} text-ink mt-1`}>
        {value === null ? "Keine Daten" : `${Math.round(value * 100)} %`}
      </div>
      {subtitle && <div className={`${T.tiny} text-ink-muted`}>{subtitle}</div>}
    </motion.div>
  );
}
