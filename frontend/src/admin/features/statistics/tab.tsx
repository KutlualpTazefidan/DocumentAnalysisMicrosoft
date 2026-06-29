import { BarChart3 } from "lucide-react";
import { Statistics } from "../../routes/Statistics";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "statistics",
  label: "Statistik",
  icon: BarChart3,
  order: 6,
  requiresFile: true,
  Component: Statistics,
};
export default descriptor;
