import { GitCompare } from "lucide-react";
import { Comparison } from "../../routes/Comparison";
import type { TabDescriptor } from "../types";

const descriptor: TabDescriptor = {
  key: "compare", label: "Vergleich", icon: GitCompare,
  order: 3, requiresFile: true, Component: Comparison,
};
export default descriptor;
