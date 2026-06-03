// frontend/src/admin/components/charts/CapabilityWishesSunburst.tsx
//
// Capability-Wünsche hierarchy chart. Recharts 3.8 has no native
// Sunburst — we use <Treemap> with two levels (Skill → Tool) which
// produces a defensible Agent → Skill → Tool reading because Agent
// is constant ("Provenienz-Agent") in v1. A future multi-agent
// topology can either (a) introduce a third Treemap level or (b)
// swap to nested <Pie> rings (commented fallback below).
import { Treemap, Tooltip } from "recharts";
import { motion } from "framer-motion";

import { RechartsNavyTheme, useChartPalette } from "./RechartsNavyTheme";
import type { CapabilityWish } from "../../hooks/useStatistics";
import { T } from "../../styles/typography";

interface Props {
  wishes: CapabilityWish[];
}

interface TreeNode {
  name: string;
  size?: number;
  children?: TreeNode[];
  // Required by Recharts 3.x TreemapDataType (index signature).
  [key: string]: unknown;
}

function buildTree(wishes: CapabilityWish[]): TreeNode {
  const byBucket: Record<string, TreeNode[]> = {};
  for (const w of wishes) {
    (byBucket[w.skill_bucket] ??= []).push({ name: w.name, size: w.count });
  }
  return {
    name: "Provenienz-Agent",
    children: Object.entries(byBucket).map(([bucket, kids]) => ({
      name: bucket,
      children: kids,
    })),
  };
}

function Inner({ wishes }: Props): JSX.Element {
  const p = useChartPalette();
  const data = buildTree(wishes).children ?? [];
  return (
    <Treemap
      data={data}
      dataKey="size"
      stroke={p.bg}
      fill={p.accent}
      isAnimationActive
      animationDuration={500}
      content={undefined}
    >
      <Tooltip contentStyle={{ background: p.bg, border: `1px solid ${p.grid}`, color: p.text }} />
    </Treemap>
  );
}

export function CapabilityWishesSunburst({ wishes }: Props): JSX.Element {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
      <div className={`${T.heading} text-navy-200 mb-1`}>Capability-Wünsche (Über alle Dokumente)</div>
      <RechartsNavyTheme height={320}>
        {wishes.length === 0 ? (
          <div className="flex items-center justify-center h-full text-navy-200">Noch keine Wünsche</div>
        ) : (
          <Inner wishes={wishes} />
        )}
      </RechartsNavyTheme>
    </motion.div>
  );
}
