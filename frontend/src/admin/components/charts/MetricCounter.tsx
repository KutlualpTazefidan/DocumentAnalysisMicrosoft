// frontend/src/admin/components/charts/MetricCounter.tsx
import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { useEffect } from "react";

import { T } from "../../styles/typography";

interface Props {
  value: number;
  label: string;
  suffix?: string;
}

export function MetricCounter({ value, label, suffix }: Props): JSX.Element {
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (v) => Math.round(v));
  useEffect(() => {
    const controls = animate(mv, value, { duration: 0.8, ease: "easeOut" });
    return () => controls.stop();
  }, [mv, value]);

  return (
    <motion.div
      className="rounded bg-navy-800 p-4 flex flex-col items-start"
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25 }}
    >
      <div className={`${T.tinyBold} text-navy-300`}>{label}</div>
      <div className="text-3xl font-semibold text-white tabular-nums mt-1">
        <motion.span>{rounded}</motion.span>
        {suffix && <span className="text-navy-200 ml-1 text-base">{suffix}</span>}
      </div>
    </motion.div>
  );
}
