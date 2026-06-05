// frontend/src/admin/components/charts/VoteDistributionBar.tsx
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { motion } from "framer-motion";

import { RechartsNavyTheme, useChartPalette } from "./RechartsNavyTheme";
import type { VoteDistributionRow } from "../../hooks/useStatistics";
import { T } from "../../styles/typography";

interface Props {
  rows: VoteDistributionRow[];
}

function Inner({ rows }: Props): JSX.Element {
  const p = useChartPalette();
  return (
    <BarChart data={rows} layout="vertical" margin={{ left: 16, right: 16 }}>
      <CartesianGrid strokeDasharray="3 3" stroke={p.grid} />
      <XAxis type="number" stroke={p.text} />
      <YAxis dataKey="text_short" type="category" stroke={p.text} width={180} />
      <Tooltip contentStyle={{ background: p.bg, border: `1px solid ${p.grid}`, color: p.text }} />
      <Bar dataKey="approved" stackId="v" fill={p.success} />
      <Bar dataKey="rejected" stackId="v" fill={p.danger} />
    </BarChart>
  );
}

export function VoteDistributionBar({ rows }: Props): JSX.Element {
  if (rows.length === 0) {
    return (
      <div className="card p-4 text-ink-muted">
        Noch keine Reviewer-Stimmen vorhanden.
      </div>
    );
  }
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
      <div className={`${T.heading} text-bam-navy mb-1`}>Stimmen pro Frage (Top 20)</div>
      <RechartsNavyTheme height={Math.max(rows.length * 28, 200)}>
        <Inner rows={rows} />
      </RechartsNavyTheme>
    </motion.div>
  );
}
