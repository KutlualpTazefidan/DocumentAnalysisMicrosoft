// frontend/src/admin/components/charts/DiagnosticBar.tsx
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { motion } from "framer-motion";

import { RechartsNavyTheme, useChartPalette } from "./RechartsNavyTheme";
import type { DiagnosticCounts } from "../../hooks/useStatistics";
import { T } from "../../styles/typography";

interface Props {
  data: DiagnosticCounts;
}

function Inner({ data }: Props): JSX.Element {
  const p = useChartPalette();
  const rows = [
    { name: "Diagnose", split: data.split, no_decomposition: data.no_decomposition, clean: data.clean },
  ];
  return (
    <BarChart data={rows} layout="vertical" margin={{ left: 16, right: 16 }}>
      <defs>
        <linearGradient id="gradClean" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={p.success} stopOpacity={0.9} />
          <stop offset="100%" stopColor={p.success} stopOpacity={0.6} />
        </linearGradient>
      </defs>
      <CartesianGrid strokeDasharray="3 3" stroke={p.grid} />
      <XAxis type="number" stroke={p.text} />
      <YAxis dataKey="name" type="category" stroke={p.text} />
      <Tooltip contentStyle={{ background: p.bg, border: `1px solid ${p.grid}`, color: p.text }} />
      <Bar dataKey="clean" stackId="d" fill="url(#gradClean)" />
      <Bar dataKey="no_decomposition" stackId="d" fill={p.danger} />
      <Bar dataKey="split" stackId="d" fill={p.warn} />
    </BarChart>
  );
}

export function DiagnosticBar({ data }: Props): JSX.Element {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <div className={`${T.heading} text-navy-200 mb-1`}>Diagnose-Flags</div>
      <RechartsNavyTheme height={120}>
        <Inner data={data} />
      </RechartsNavyTheme>
    </motion.div>
  );
}
